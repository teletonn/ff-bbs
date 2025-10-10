#!/usr/bin/python3
# Meshtastic FF-BBS MESH Bot

try:
    from pubsub import pub
except ImportError:
    print(f"Important dependencies are not met, try install.sh\n\n Did you mean to './launch.sh mesh' using a virtual environment.")
    exit(1)

import asyncio
import time # for sleep, get some when you can :)
import random
import json
import configparser
import logging
from modules.log import *
from modules.system import *
from webui import db_handler
import json
from datetime import datetime
import math
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'webui'))
try:
    from main import broadcast_map_update
except ImportError:
    # If import fails, create a dummy function
    async def broadcast_map_update(update_type, data):
        pass

# --- Localization ---

ACTIVE_GEOFENCES = []
ACTIVE_TRIGGERS = {}
ACTIVE_ZONES = []  # New zones table
NODE_ZONES = {}
config = configparser.ConfigParser()
config.read('config.ini')

# Commands configuration
poll_interval = config.getint('commands', 'poll_interval', fallback=5)

def handle_send_message(cmd):
    params = json.loads(cmd['parameters'])
    sender_user_id = cmd['sender_user_id']
    user = db_handler.get_user(sender_user_id)
    sender_node_id = user.get('node_id') if user else None
    logging.info(f"Handling send_message from user {sender_user_id}, node_id {sender_node_id}, params {params}")
    return send_message(params['message'], int(params.get('channel', 0)), int(params.get('target', 0)), 1)

def handle_traceroute(cmd):
    import sqlite3
    params = json.loads(cmd['parameters'])
    dest_node_id = int(params['dest_node_id'])
    trace_id = params['trace_id']

    # Use interface1 for traceroute (can be improved to select appropriate interface)
    interface = interface1
    try:
        start_time = time.time()
        result = interface.sendTraceRoute(dest_node_id, wantResponse=True)
        response_time = time.time() - start_time

        # Parse the result - result is a RouteDiscovery message
        hops = []
        if result and hasattr(result, 'route'):
            for hop in result.route:
                hops.append({
                    'node_id': str(hop.node_id),
                    'snr': float(hop.snr) if hop.snr else None
                })

        # Update database
        conn = db_handler.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE route_traces
            SET status = 'completed', hops = ?, response_time = ?, timestamp = ?
            WHERE id = ?
        """, (json.dumps(hops), response_time, time.time(), trace_id))
        conn.commit()
        conn.close()

        logging.info(f"Traceroute completed for trace_id {trace_id}, dest {dest_node_id}")

    except Exception as e:
        # Update database with failure
        conn = db_handler.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE route_traces
            SET status = 'failed', error_message = ?, timestamp = ?
            WHERE id = ?
        """, (str(e), time.time(), trace_id))
        conn.commit()
        conn.close()

        logging.error(f"Traceroute failed for trace_id {trace_id}: {e}")

HANDLERS = {
    'send_message': handle_send_message,
    'restart_bot': lambda params: restart_bot(),
    'traceroute': handle_traceroute,
    # New handlers for user groups, alerts, processes, zones
    'create_user_group': lambda params: create_user_group(params),
    'send_alert': lambda params: send_alert(params),
    'create_process': lambda params: create_process(params),
    'create_zone': lambda params: create_zone(params)
}

def restart_bot():
    """Restart the bot process."""
    # Optional: Save any state here
    import os
    import sys
    os.execv(sys.executable, [sys.executable] + sys.argv)

# Placeholder handlers for new features
def create_user_group(params):
    """Placeholder for creating user group."""
    # TODO: Implement user group creation logic
    logger.info(f"Creating user group: {params}")
    pass

def send_alert(params):
    """Placeholder for sending alert."""
    # TODO: Implement alert sending logic
    logger.info(f"Sending alert: {params}")
    pass

def create_process(params):
    """Placeholder for creating automated process."""
    # TODO: Implement process creation logic
    logger.info(f"Creating process: {params}")
    pass

def create_zone(params):
    """Placeholder for creating zone."""
    # TODO: Implement zone creation logic
    logger.info(f"Creating zone: {params}")
    pass

try:
    language = config.get('localization', 'language')
except (configparser.NoSectionError, configparser.NoOptionError):
    language = 'ru' # Default to English if not set

# Load the language file
try:
    with open(f'localization/{language}.json', 'r', encoding='utf-8') as f:
        translations = json.load(f)
except FileNotFoundError:
    print(f"Language file for '{language}' not found. Falling back to English.")
    with open('localization/en.json', 'r', encoding='utf-8') as f:
        translations = json.load(f)

def _(key, **kwargs):
    """Translate a key using the loaded language file."""
    message = translations.get(key, key) # Fallback to key if not found
    # Change network name for Russian localization
    if language == 'ru':
        message = message.replace("MeshBot", "Светлячок")
    return message.format(**kwargs)

# list of commands to remove from the default list for DM only
restrictedCommands = ["blackjack", "videopoker", "dopewars", "lemonstand", "golfsim", "mastermind", "hangman", "hamtest"]
restrictedResponse = _("restricted_response") # "" for none
cmdHistory = [] # list to hold the command history for lheard and history commands

def auto_response(message, snr, rssi, hop, pkiStatus, message_from_id, channel_number, deviceID, isDM):
    global cmdHistory
    #Auto response to messages
    message_lower = message.lower()
    bot_response = _("cant_do_that")

    # Command List processes system.trap_list. system.messageTrap() sends any commands to here
    default_commands = {
    "ack": lambda: handle_ping(message_from_id, deviceID, message, hop, snr, rssi, isDM, channel_number),
    "ask:": lambda: handle_llm(message_from_id, channel_number, deviceID, message, publicChannel),
    "askai": lambda: handle_llm(message_from_id, channel_number, deviceID, message, publicChannel),
    "bbsack": lambda: bbs_sync_posts(message, message_from_id, deviceID),
    "bbsdelete": lambda: handle_bbsdelete(message, message_from_id),
    "bbshelp": bbs_help,
    "bbsinfo": lambda: get_bbs_stats(),
    "bbslink": lambda: bbs_sync_posts(message, message_from_id, deviceID),
    "bbslist": bbs_list_messages,
    "bbspost": lambda: handle_bbspost(message, message_from_id, deviceID),
    "bbsread": lambda: handle_bbsread(message),
    "blackjack": lambda: handleBlackJack(message, message_from_id, deviceID),
    "checkin": lambda: handle_checklist(message, message_from_id, deviceID),
    "checklist": lambda: handle_checklist(message, message_from_id, deviceID),
    "checkout": lambda: handle_checklist(message, message_from_id, deviceID),
    "clearsms": lambda: handle_sms(message_from_id, message),
    "cmd": lambda: handle_cmd(message, message_from_id, deviceID),
    "cq": lambda: handle_ping(message_from_id, deviceID, message, hop, snr, rssi, isDM, channel_number),
    "cqcq": lambda: handle_ping(message_from_id, deviceID, message, hop, snr, rssi, isDM, channel_number),
    "cqcqcq": lambda: handle_ping(message_from_id, deviceID, message, hop, snr, rssi, isDM, channel_number),
    "dopewars": lambda: handleDopeWars(message, message_from_id, deviceID),
    "ea": lambda: handle_emergency_alerts(message, message_from_id, deviceID),
    "echo": lambda: handle_echo(message, message_from_id, deviceID, isDM, channel_number),
    "ealert": lambda: handle_emergency_alerts(message, message_from_id, deviceID),
    "earthquake": lambda: handleEarthquake(message, message_from_id, deviceID),
    "email:": lambda: handle_email(message_from_id, message),
    "games": lambda: gamesCmdList,
    "globalthermonuclearwar": lambda: handle_gTnW(),
    "golfsim": lambda: handleGolf(message, message_from_id, deviceID),
    "hamtest": lambda: handleHamtest(message, message_from_id, deviceID),
    "hangman": lambda: handleHangman(message, message_from_id, deviceID),
    "hfcond": hf_band_conditions,
    "history": lambda: handle_history(message, message_from_id, deviceID, isDM),
    "howfar": lambda: handle_howfar(message, message_from_id, deviceID, isDM),
    "howtall": lambda: handle_howtall(message, message_from_id, deviceID, isDM),
    "joke": lambda: tell_joke(message_from_id),
    "lemonstand": lambda: handleLemonade(message, message_from_id, deviceID),
    "lheard": lambda: handle_lheard(message, message_from_id, deviceID, isDM),
    "mastermind": lambda: handleMmind(message, message_from_id, deviceID),
    "messages": lambda: handle_messages(message, deviceID, channel_number, msg_history, publicChannel, isDM),
    "moon": lambda: handle_moon(message_from_id, deviceID, channel_number),
    "motd": lambda: handle_motd(message, message_from_id, isDM),
    "mwx": lambda: handle_mwx(message_from_id, deviceID, channel_number),
    "ping": lambda: handle_ping(message_from_id, deviceID, message, hop, snr, rssi, isDM, channel_number),
    "пинг": lambda: handle_ping(message_from_id, deviceID, message, hop, snr, rssi, isDM, channel_number),
    "pinging": lambda: handle_ping(message_from_id, deviceID, message, hop, snr, rssi, isDM, channel_number),
    "pong": lambda: "🏓PING!!🛜",
    "readnews": lambda: read_news(),
    "riverflow": lambda: handle_riverFlow(message, message_from_id, deviceID),
    "rlist": lambda: handle_repeaterQuery(message_from_id, deviceID, channel_number),
    "satpass": lambda: handle_satpass(message_from_id, deviceID, channel_number, message),
    "setemail": lambda: handle_email(message_from_id, message),
    "setsms": lambda: handle_sms( message_from_id, message),
    "sitrep": lambda: handle_lheard(message, message_from_id, deviceID, isDM),
    "sms:": lambda: handle_sms(message_from_id, message),
    "solar": lambda: drap_xray_conditions() + "\n" + solar_conditions(),
    "sun": lambda: handle_sun(message_from_id, deviceID, channel_number),
    "sysinfo": lambda: sysinfo(message, message_from_id, deviceID),
    "test": lambda: handle_ping(message_from_id, deviceID, message, hop, snr, rssi, isDM, channel_number),
    "testing": lambda: handle_ping(message_from_id, deviceID, message, hop, snr, rssi, isDM, channel_number),
    "tide": lambda: handle_tide(message_from_id, deviceID, channel_number),
    "valert": lambda: get_volcano_usgs(),
    "videopoker": lambda: handleVideoPoker(message, message_from_id, deviceID),
    "whereami": lambda: handle_whereami(message_from_id, deviceID, channel_number),
    "whoami": lambda: handle_whoami(message_from_id, deviceID, hop, snr, rssi, pkiStatus),
    "whois": lambda: handle_whois(message, deviceID, channel_number, message_from_id),
    "wiki:": lambda: handle_wiki(message, isDM),
    "wx": lambda: handle_wxc(message_from_id, deviceID, 'wx'),
    "wxa": lambda: handle_wxalert(message_from_id, deviceID, message),
    "wxalert": lambda: handle_wxalert(message_from_id, deviceID, message),
    "wxc": lambda: handle_wxc(message_from_id, deviceID, 'wxc'),
    "📍": lambda: handle_whoami(message_from_id, deviceID, hop, snr, rssi, pkiStatus),
    "🔔": lambda: handle_alertBell(message_from_id, deviceID, message),
    "🐝": lambda: read_file("bee.txt", True),
    # any value from system.py:trap_list_emergency will trigger the emergency function
    "112": lambda: handle_emergency(message_from_id, deviceID, message),
    "911": lambda: handle_emergency(message_from_id, deviceID, message),
    "999": lambda: handle_emergency(message_from_id, deviceID, message),
    "ambulance": lambda: handle_emergency(message_from_id, deviceID, message),
    "emergency": lambda: handle_emergency(message_from_id, deviceID, message),
    "fire": lambda: handle_emergency(message_from_id, deviceID, message),
    "police": lambda: handle_emergency(message_from_id, deviceID, message),
    "rescue": lambda: handle_emergency(message_from_id, deviceID, message),
    }

    # set the command handler
    command_handler = default_commands
    cmds = [] # list to hold the commands found in the message
    # check the message for commands words list, processed after system.messageTrap
    for key in command_handler:
        word = message_lower.split(' ')
        if cmdBang:
            # strip the !
            if word[0].startswith("!"):
                word[0] = word[0][1:]
        if key in word:
            # append all the commands found in the message to the cmds list
            cmds.append({'cmd': key, 'index': message_lower.index(key)})
        # check for commands with a question mark
        if key + "?" in word:
            # append all the commands found in the message to the cmds list
            cmds.append({'cmd': key, 'index': message_lower.index(key)})

    if len(cmds) > 0:
        # sort the commands by index value
        cmds = sorted(cmds, key=lambda k: k['index'])
        logger.debug(f"System: Bot detected Commands:{cmds} From: {get_name_from_number(message_from_id)}")
        # check the command isnt a isDM only command
        if cmds[0]['cmd'] in restrictedCommands and not isDM:
            bot_response = restrictedResponse
        else:
            # run the first command after sorting
            bot_response = command_handler[cmds[0]['cmd']]()
            # append the command to the cmdHistory list for lheard and history
            if len(cmdHistory) > 50:
                cmdHistory.pop(0)
            cmdHistory.append({'nodeID': message_from_id, 'cmd':  cmds[0]['cmd'], 'time': time.time()})

    # wait a responseDelay to avoid message collision from lora-ack
    time.sleep(responseDelay)
    return bot_response

def handle_cmd(message, message_from_id, deviceID):
    # why CMD? its just a command list. a terminal would normally use "Help"
    # I didnt want to invoke the word "help" in Meshtastic due to its possible emergency use
    if " " in message and message.split(" ")[1] in trap_list:
        return _("cmd_direct_chat")
    return help_message
    
def handle_ping(message_from_id, deviceID,  message, hop, snr, rssi, isDM, channel_number):
    global multiPing
    myNodeNum = globals().get(f'myNodeNum{deviceID}', 777)
    if  "?" in message and isDM:
        return message.split("?")[0].title() + " " + _("ping_help")
    
    msg = ""
    type = ''

    if "ping" in message.lower():
        msg = _("ping_response")
        type = "🏓PING"
    elif "test" in message.lower() or "testing" in message.lower():
        msg = random.choice([_("test_response_1"), _("test_response_2"), _("test_response_3"), _("test_response_4"), _("test_response_5"), _("test_response_6")])
        type = "🎙TEST"
    elif "ack" in message.lower():
        msg = random.choice([_("ack_response_1"), _("ack_response_2")])
        type = "✋ACK"
    elif "cqcq" in message.lower() or "cq" in message.lower() or "cqcqcq" in message.lower():
        myname = get_name_from_number(myNodeNum, 'short', deviceID)
        msg = _("cq_response", myname=myname)
    else:
        msg = _("hearing_distance")

    if hop == "Direct" or hop == "MQTT":
        msg = msg + f"SNR:{snr} RSSI:{rssi}"
    else:
        msg = msg + hop

    if "@" in message:
        msg = msg + " @" + message.split("@")[1]
        type = type + " @" + message.split("@")[1]
    elif "#" in message:
        msg = msg + " #" + message.split("#")[1]
        type = type + " #" + message.split("#")[1]


    # check for multi ping request
    if " " in message:
        # if stop multi ping
        if "stop" in message.lower():
            for i in range(0, len(multiPingList)):
                if multiPingList[i].get('message_from_id') == message_from_id:
                    multiPingList.pop(i)
                    msg = _("stop_auto_ping")


        # if 3 or more entries (2 or more active), throttle the multi-ping for congestion
        if len(multiPingList) > 2:
            msg = _("auto_ping_busy")
            pingCount = -1
        else:
            # set inital pingCount
            try:
                pingCount = int(message.split(" ")[1])
                if pingCount == 123 or pingCount == 1234:
                    pingCount =  1
                elif not autoPingInChannel and not isDM:
                    # no autoping in channels
                    pingCount = 1

                if pingCount > 51:
                    pingCount = 50
            except:
                pingCount = -1
    
        if pingCount > 1:
            multiPingList.append({'message_from_id': message_from_id, 'count': pingCount + 1, 'type': type, 'deviceID': deviceID, 'channel_number': channel_number, 'startCount': pingCount})
            if type == "🎙TEST":
                msg = _("buffer_test_init", chunk_size=int(maxBuffer // pingCount), max_buffer=maxBuffer, ping_count=pingCount)
            else:
                msg = _("auto_ping_init", ping_count=pingCount)

    # if not a DM add the username to the beginning of msg
    if not useDMForResponse and not isDM:
        msg = "@" + get_name_from_number(message_from_id, 'short', deviceID) + " " + msg
            
    return msg

def handle_alertBell(message_from_id, deviceID, message):
    msg = [_("cowbell_response_1"), _("cowbell_response_2"), _("cowbell_response_3")]
    return random.choice(msg)

def handle_emergency(message_from_id, deviceID, message):
    myNodeNum = globals().get(f'myNodeNum{deviceID}', 777)
    # if user in bbs_ban_list return
    if str(message_from_id) in bbs_ban_list:
        # silent discard
        logger.warning(f"System: {message_from_id} on spam list, no emergency responder alert sent")
        return ''
    # trgger alert to emergency_responder_alert_channel
    if message_from_id != 0:
        nodeLocation = get_node_location(message_from_id, deviceID)
        # if default location is returned set to Unknown
        if nodeLocation[0] == latitudeValue and nodeLocation[1] == longitudeValue:
            nodeLocation = ["?", "?"]
        nodeInfo = f"{get_name_from_number(message_from_id, 'short', deviceID)} detected by {get_name_from_number(myNodeNum, 'short', deviceID)} lastGPS {nodeLocation[0]}, {nodeLocation[1]}"
        msg = _("emergency_assistance_needed", nodeInfo=nodeInfo)
        # alert the emergency_responder_alert_channel
        time.sleep(responseDelay)
        send_message(msg, emergency_responder_alert_channel, 0, emergency_responder_alert_interface)
        logger.warning(f"System: {message_from_id} Emergency Assistance Requested in {message}")
        # send the message out via email/sms
        if enableSMTP:
            for user in sysopEmails:
                send_email(user, f"Emergency Assistance Requested by {nodeInfo} in {message}", message_from_id)
        # respond to the user
        time.sleep(responseDelay + 2)
        return _("emergency_response_ack")

def handle_motd(message, message_from_id, isDM):
    global MOTD
    isAdmin = False
    msg = ""
    # check if the message_from_id is in the bbs_admin_list
    if bbs_admin_list != ['']:
        for admin in bbs_admin_list:
            if str(message_from_id) == admin:
                isAdmin = True
                break
    else:
        isAdmin = True

    # admin help via DM
    if  "?" in message and isDM and isAdmin:
        msg = _("motd_help_admin")
    elif  "?" in message and isDM and not isAdmin:
        # non-admin help via DM
        msg = _("motd_help_user")
    elif "$" in message and isAdmin:
        motd = message.split("$")[1]
        MOTD = motd.rstrip()
        logger.debug(f"System: {message_from_id} changed MOTD: {MOTD}")
        msg = _("motd_changed", motd=MOTD)
    else:
        msg = _("motd_prefix") + MOTD
    return msg

def handle_echo(message, message_from_id, deviceID, isDM, channel_number):
    if "?" in message.lower():
        return _("echo_help")
    elif "echo " in message.lower():
        parts = message.lower().split("echo ", 1)
        if len(parts) > 1 and parts[1].strip() != "":
            echo_msg = parts[1]
            if channel_number != echoChannel:
                echo_msg = "@" + get_name_from_number(message_from_id, 'short', deviceID) + " " + echo_msg
            return echo_msg
        else:
            return _("echo_empty")
    else:
        return _("echo_empty")

def handle_wxalert(message_from_id, deviceID, message):
    if use_meteo_wxApi:
        return _("wxalert_not_supported")
    else:
        location = get_node_location(message_from_id, deviceID)
        if "wxalert" in message:
            # Detailed weather alert
            weatherAlert = getActiveWeatherAlertsDetailNOAA(str(location[0]), str(location[1]))
        else:
            weatherAlert = getWeatherAlertsNOAA(str(location[0]), str(location[1]))
        
        if NO_ALERTS not in weatherAlert:
            weatherAlert = weatherAlert[0]
        return weatherAlert

def handle_howfar(message, message_from_id, deviceID, isDM):
    msg = ''
    location = get_node_location(message_from_id, deviceID)
    lat = location[0]
    lon = location[1]
    # if ? in message
    if "?" in message.lower():
        return _("howfar_help")
    
    # if no GPS location return
    if lat == latitudeValue and lon == longitudeValue:
        logger.debug(f"System: HowFar: No GPS location for {message_from_id}")
        return _("no_gps_location")
    
    if "reset" in message.lower():
        msg = distance(lat,lon,message_from_id, reset=True)
    else:
        msg = distance(lat,lon,message_from_id)
    
    # if not a DM add the username to the beginning of msg
    if not useDMForResponse and not isDM:
        msg = "@" + get_name_from_number(message_from_id, 'short', deviceID) + " " + msg

    return msg

def handle_howtall(message, message_from_id, deviceID, isDM):
    msg = ''
    location = get_node_location(message_from_id, deviceID)
    lat = location[0]
    lon = location[1]
    if lat == latitudeValue and lon == longitudeValue:
        logger.debug(f"System: HowTall: No GPS location for {message_from_id}")
        return _("no_gps_location")
    if use_metric:
            measure = "meters" 
    else:
            measure = "feet"
    # if ? in message
    if "?" in message.lower():
        return _("howtall_help", measure=measure)
    # get the shadow length from the message split after howtall
    try:
        shadow_length = float(message.lower().split("howtall ")[1].split(" ")[0])
    except:
        return _("howtall_help", measure=measure)
    
    # get data
    msg = measureHeight(lat, lon, shadow_length)

    # if data has NO_ALERTS return help
    if NO_ALERTS in msg:
        return _("howtall_help", measure=measure)
    
    return msg

def handle_wiki(message, isDM):
    # location = get_node_location(message_from_id, deviceID)
    msg = _("wiki_help")
    try:
        if "wiki:?" in message.lower() or "wiki: ?" in message.lower() or "wiki?" in message.lower() or "wiki ?" in message.lower():
            return msg
        if "wiki" in message.lower():
            search = message.split(":")[1]
            search = search.strip()
            if search:
                return get_wikipedia_summary(search)
            return _("wiki_no_term")
    except Exception as e:
        logger.error(f"System: Wiki Exception {e}")
        msg = _("wiki_error")
        
    return msg

# Runtime Variables for LLM
llmRunCounter = 0
llmTotalRuntime = []
llmLocationTable = [{'nodeID': 1234567890, 'location': 'No Location'},]

def handle_satpass(message_from_id, deviceID, channel_number, message):
    location = get_node_location(message_from_id, deviceID)
    passes = ''
    satList = satListConfig
    message = message.lower()

    # if user has a NORAD ID in the message
    if "satpass " in message:
        try:
            userList = message.split("satpass ")[1].split(" ")[0]
            #split userList and make into satList overrided the config.ini satList
            satList = userList.split(",")
        except:
            return _("satpass_example")

    # Detailed satellite pass
    for bird in satList:
        satPass = getNextSatellitePass(bird, str(location[0]), str(location[1]))
        if satPass:
            # append to passes
            passes = passes + satPass + "\n"
    # remove the last newline
    passes = passes[:-1]

    if passes == '':
        passes = _("no_sat_passes")
    return passes
        
def handle_llm(message_from_id, channel_number, deviceID, message, publicChannel):
    global llmRunCounter, llmLocationTable, llmTotalRuntime, cmdHistory, seenNodes
    location_name = 'no location provided'
    msg = ''
    
    if location_enabled:
        # if message_from_id is is the llmLocationTable use the location from the list to save on API calls
        for i in range(0, len(llmLocationTable)):
            if llmLocationTable[i].get('nodeID') == message_from_id:
                logger.debug(f"System: LLM: Found {message_from_id} in location table")
                location_name = llmLocationTable[i].get('location')
                break
        else:
            location = get_node_location(message_from_id, deviceID)
            location_name = where_am_i(str(location[0]), str(location[1]), short = True)

    if NO_DATA_NOGPS in location_name:
        location_name = "no location provided"

    if "ask:" in message.lower():
        user_input = message.split(":")[1]
    elif "askai" in message.lower():
        user_input = message.replace("askai", "")
    else:
        # likely a DM
        user_input = message
        # consider this a command use for the cmdHistory list
        cmdHistory.append({'nodeID': message_from_id, 'cmd':  'llm-use', 'time': time.time()})

        # check for a welcome message (is this redundant?)
        if not any(node['nodeID'] == message_from_id and node['welcome'] == True for node in seenNodes):
            if (channel_number == publicChannel and antiSpam) or useDMForResponse:
                # send via DM
                send_message(welcome_message, channel_number, message_from_id, deviceID)
                time.sleep(responseDelay)
            else:
                # send via channel
                send_message(welcome_message, channel_number, 0, deviceID)
                time.sleep(responseDelay)
            # mark the node as welcomed
            for node in seenNodes:
                if node['nodeID'] == message_from_id:
                    node['welcome'] = True
    
    # update the llmLocationTable for future use
    for i in range(0, len(llmLocationTable)):
        if llmLocationTable[i].get('nodeID') == message_from_id:
            llmLocationTable[i]['location'] = location_name

    # if not in table add the location
    if not any(d['nodeID'] == message_from_id for d in llmLocationTable):
        llmLocationTable.append({'nodeID': message_from_id, 'location': location_name})

    user_input = user_input.strip()
        
    if len(user_input) < 1:
        return _("llm_ask_question")

    # information for the user on how long the query will take on average
    if llmRunCounter > 0:
        averageRuntime = sum(llmTotalRuntime) / len(llmTotalRuntime)
        msg = _("llm_wait_time", average_runtime=int(averageRuntime)) if averageRuntime > 25 else ''
    else:
        msg = _("llm_wait_long")

    if msg != '':
        if (channel_number == publicChannel and antiSpam) or useDMForResponse:
            # send via DM
            send_message(msg, channel_number, message_from_id, deviceID)
        else:
            # send via channel
            send_message(msg, channel_number, 0, deviceID)
        time.sleep(responseDelay)
    
    start = time.time()

    #response = asyncio.run(llm_query(user_input, message_from_id))
    response = llm_query(user_input, message_from_id, location_name)

    # handle the runtime counter
    end = time.time()
    llmRunCounter += 1
    llmTotalRuntime.append(end - start)
    
    return response

def handleDopeWars(message, nodeID, rxNode):
    global dwPlayerTracker, dwHighScore
    
    # get player's last command
    last_cmd = None
    for i in range(0, len(dwPlayerTracker)):
        if dwPlayerTracker[i].get('userID') == nodeID:
            last_cmd = dwPlayerTracker[i].get('cmd')
    
    # welcome new player
    if not last_cmd and nodeID != 0:
        msg = _("welcome_dopewars", total_days=total_days)
        high_score = getHighScoreDw()
        msg += _("dopewars_highscore", cash="{:,}".format(high_score.get('cash')), user=get_name_from_number(high_score.get('userID') , 'short', rxNode))
        msg += playDopeWars(nodeID, message)
    else:
        logger.debug(f"System: {nodeID} PlayingGame dopewars last_cmd: {last_cmd}")
        msg = playDopeWars(nodeID, message)
    # wait a second to keep from message collision
    time.sleep(responseDelay + 1)
    return msg

def handle_gTnW():
    response = [_("gtnw_response_1"), _("gtnw_response_2"), _("gtnw_response_3"), _("gtnw_response_4"), _("gtnw_response_5"), _("gtnw_response_6"), _("gtnw_response_7"), _("gtnw_response_8"), _("gtnw_response_9"), _("gtnw_response_10")]
    length = len(response)
    indices = list(range(length))
    # Shuffle the indices using a convoluted method
    for i in range(length):
        swap_idx = random.randint(0, length - 1)
        indices[i], indices[swap_idx] = indices[swap_idx], indices[i]
    # Select a random response from the shuffled list. anyone enjoy the game, killerbunnies(.com)
    selected_index = random.choice(indices)
    return response[selected_index]

def handleLemonade(message, nodeID, deviceID):
    global lemonadeTracker, lemonadeCups, lemonadeLemons, lemonadeSugar, lemonadeWeeks, lemonadeScore, lemon_starting_cash, lemon_total_weeks
    msg = ""
    def create_player(nodeID):
        # create new player
        logger.debug("System: Lemonade: New Player: " + str(nodeID))
        lemonadeTracker.append({'nodeID': nodeID, 'cups': 0, 'lemons': 0, 'sugar': 0, 'cash': lemon_starting_cash, 'start': lemon_starting_cash, 'cmd': 'new', 'time': time.time()})
        lemonadeCups.append({'nodeID': nodeID, 'cost': 2.50, 'count': 25, 'min': 0.99, 'unit': 0.00})
        lemonadeLemons.append({'nodeID': nodeID, 'cost': 4.00, 'count': 8, 'min': 2.00, 'unit': 0.00})
        lemonadeSugar.append({'nodeID': nodeID, 'cost': 3.00, 'count': 15, 'min': 1.50, 'unit': 0.00})
        lemonadeScore.append({'nodeID': nodeID, 'value': 0.00, 'total': 0.00})
        lemonadeWeeks.append({'nodeID': nodeID, 'current': 1, 'total': lemon_total_weeks, 'sales': 99, 'potential': 0, 'unit': 0.00, 'price': 0.00, 'total_sales': 0})
    
    # get player's last command from tracker if not new player
    last_cmd = ""
    for i in range(len(lemonadeTracker)):
        if lemonadeTracker[i]['nodeID'] == nodeID:
            last_cmd = lemonadeTracker[i]['cmd']

    logger.debug(f"System: {nodeID} PlayingGame lemonstand last_cmd: {last_cmd}")
    # create new player if not in tracker
    if last_cmd == "" and nodeID != 0:
        create_player(nodeID)
        msg += _("welcome_lemonade")

        # high score
        highScore = {"userID": 0, "cash": 0, "success": 0}
        highScore = getHighScoreLemon()
        if highScore != 0:
            if highScore['userID'] != 0:
                nodeName = get_name_from_number(highScore['userID'])
                if nodeName.isnumeric() and multiple_interface:
                    logger.debug(f"System: TODO is multiple interface fix mention this please nodeName: {nodeName}")
                    #nodeName = get_name_from_number(highScore['userID'], 'long', 2)
                msg += _("lemonade_highscore", nodeName=nodeName, cash=round(highScore['cash'], 2))
    
    msg += start_lemonade(nodeID=nodeID, message=message, celsius=False)
    # wait a second to keep from message collision
    time.sleep(responseDelay + 1)
    return msg

def handleBlackJack(message, nodeID, deviceID):
    global jackTracker
    msg = ""

    # get player's last command from tracker
    last_cmd = ""
    for i in range(len(jackTracker)):
        if jackTracker[i]['nodeID'] == nodeID:
            last_cmd = jackTracker[i]['cmd']

    # if player sends a L for leave table
    if message.lower().startswith("l"):
        logger.debug(f"System: BlackJack: {nodeID} is leaving the table")
        msg = _("blackjack_leave_table")
        for i in range(len(jackTracker)):
            if jackTracker[i]['nodeID'] == nodeID:
                jackTracker.pop(i)
        return msg

    else:  
        # Play BlackJack
        msg = playBlackJack(nodeID=nodeID, message=message)
    
        if last_cmd != "" and nodeID != 0:
            logger.debug(f"System: {nodeID} PlayingGame blackjack last_cmd: {last_cmd}")
        else:
            highScore = {'nodeID': 0, 'highScore': 0}
            highScore = loadHSJack()
            if highScore != 0:
                if highScore['nodeID'] != 0:
                    nodeName = get_name_from_number(highScore['nodeID'])
                    if nodeName.isnumeric() and multiple_interface:
                        logger.debug(f"System: TODO is multiple interface fix mention this please nodeName: {nodeName}")
                        #nodeName = get_name_from_number(highScore['nodeID'], 'long', 2)
                    msg += _("blackjack_highscore", nodeName=nodeName, highScore=highScore['highScore'])
    time.sleep(responseDelay + 1) # short answers with long replies can cause message collision added wait
    return msg

def handleVideoPoker(message, nodeID, deviceID):
    global vpTracker
    msg = ""

    # if player sends a L for leave table
    if message.lower().startswith("l"):
        logger.debug(f"System: VideoPoker: {nodeID} is leaving the table")
        msg = _("videopoker_leave_table")
        for i in range(len(vpTracker)):
            if vpTracker[i]['nodeID'] == nodeID:
                vpTracker.pop(i)
        return msg
    else:
        # Play Video Poker
        msg = playVideoPoker(nodeID=nodeID, message=message)

        # get player's last command from tracker
        last_cmd = ""
        for i in range(len(vpTracker)):
            if vpTracker[i]['nodeID'] == nodeID:
                last_cmd = vpTracker[i]['cmd']

        # find higest dollar amount in tracker for high score
        if last_cmd == "new":
            highScore = {'nodeID': 0, 'highScore': 0}
            highScore = loadHSVp()
            if highScore != 0:
                if highScore['nodeID'] != 0:
                    nodeName = get_name_from_number(highScore['nodeID'])
                    if nodeName.isnumeric() and multiple_interface:
                        logger.debug(f"System: TODO is multiple interface fix mention this please nodeName: {nodeName}")
                        #nodeName = get_name_from_number(highScore['nodeID'], 'long', 2)
                    msg += _("videopoker_highscore", nodeName=nodeName, highScore=highScore['highScore'])
    
        if last_cmd != "" and nodeID != 0:
            logger.debug(f"System: {nodeID} PlayingGame videopoker last_cmd: {last_cmd}")
    time.sleep(responseDelay + 1) # short answers with long replies can cause message collision added wait
    return msg

def handleMmind(message, nodeID, deviceID):
    global mindTracker
    msg = ''

    if "end" in message.lower() or message.lower().startswith("e"):
        logger.debug(f"System: MasterMind: {nodeID} is leaving the game")
        msg = _("mastermind_leave_game")
        for i in range(len(mindTracker)):
            if mindTracker[i]['nodeID'] == nodeID:
                mindTracker.pop(i)
        highscore = getHighScoreMMind(0, 0, 'n')
        if highscore != 0:
            nodeName = get_name_from_number(highscore[0]['nodeID'],'long',deviceID)
            msg += _("mastermind_highscore", nodeName=nodeName, turns=highscore[0]['turns'], diff=highscore[0]['diff'].upper())
        return msg

    # get player's last command from tracker if not new player
    last_cmd = ""
    for i in range(len(mindTracker)):
        if mindTracker[i]['nodeID'] == nodeID:
            last_cmd = mindTracker[i]['cmd']

    logger.debug(f"System: {nodeID} PlayingGame mastermind last_cmd: {last_cmd}")

    if last_cmd == "" and nodeID != 0:
        # create new player
        logger.debug("System: MasterMind: New Player: " + str(nodeID))
        mindTracker.append({'nodeID': nodeID, 'last_played': time.time(), 'cmd': 'new', 'secret_code': 'RYGB', 'diff': 'n', 'turns': 1})
        msg = _("welcome_mastermind")
        msg += _("mastermind_instructions")
        msg += _("mastermind_turns")
        return msg

    msg += start_mMind(nodeID=nodeID, message=message)
    # wait a second to keep from message collision
    time.sleep(responseDelay + 1)
    return msg

def handleGolf(message, nodeID, deviceID):
    global golfTracker
    msg = ''

    # get player's last command from tracker if not new player
    last_cmd = ""
    for i in range(len(golfTracker)):
        if golfTracker[i]['nodeID'] == nodeID:
            last_cmd = golfTracker[i]['cmd']

    if "end" in message.lower() or message.lower().startswith("e"):
        logger.debug(f"System: GolfSim: {nodeID} is leaving the game")
        msg = _("golf_leave_game")
        for i in range(len(golfTracker)):
            if golfTracker[i]['nodeID'] == nodeID:
                golfTracker.pop(i)
        return msg

    logger.debug(f"System: {nodeID} PlayingGame golfsim last_cmd: {last_cmd}")

    if last_cmd == "" and nodeID != 0:
        # create new player
        logger.debug("System: GolfSim: New Player: " + str(nodeID))
        golfTracker.append({'nodeID': nodeID, 'last_played': time.time(), 'cmd': 'new', 'hole': 1, 'distance_remaining': 0, 'hole_shots': 0, 'hole_strokes': 0, 'hole_to_par': 0, 'total_strokes': 0, 'total_to_par': 0, 'par': 0, 'hazard': ''})
        msg = _("welcome_golf")
        msg += _("golf_clubs")
    
    msg += playGolf(nodeID=nodeID, message=message)
    # wait a second to keep from message collision
    time.sleep(responseDelay + 1)
    return msg

def handleHangman(message, nodeID, deviceID):
    global hangmanTracker
    index = 0
    msg = ''
    for i in range(len(hangmanTracker)):
        if hangmanTracker[i]['nodeID'] == nodeID:
            hangmanTracker[i]["last_played"] = time.time()
            index = i+1
            break

    if index and "end" in message.lower():
        hangman.end(nodeID)
        hangmanTracker.pop(index-1)
        return _("hangman_end")

    if not index:
        hangmanTracker.append(
            {
                "nodeID": nodeID,
                "last_played": time.time()
            }
        )
        msg = _("welcome_hangman")
    msg += hangman.play(nodeID, message)

    time.sleep(responseDelay + 1)
    return msg

def handleHamtest(message, nodeID, deviceID):
    global hamtestTracker
    index = 0
    msg = ''
    response = message.split(' ')
    for i in range(len(hamtestTracker)):
        if hamtestTracker[i]['nodeID'] == nodeID:
            hamtestTracker[i]["last_played"] = time.time()
            index = i+1
            break

    if not index:
        hamtestTracker.append({"nodeID": nodeID,"last_played": time.time()})

    if "end" in response[0].lower():
        msg = hamtest.endGame(nodeID)
    elif "score" in response[0].lower():
        msg = hamtest.getScore(nodeID)

    if "hamtest" in response[0].lower():
        if len(response) > 1:
            if "gen" in response[1].lower():
                msg = hamtest.newGame(nodeID, 'general')
            elif "ex" in response[1].lower():
                msg = hamtest.newGame(nodeID, 'extra')
        else:
            msg = hamtest.newGame(nodeID, 'technician')

    # if the message is an answer A B C or D upper or lower case
    if response[0].upper() in ['A', 'B', 'C', 'D']:
        msg = hamtest.answer(nodeID, response[0])

    time.sleep(responseDelay + 1)
    return msg

def handle_riverFlow(message, message_from_id, deviceID):
    location = get_node_location(message_from_id, deviceID)
    userRiver = message.lower()
    
    if "riverflow " in userRiver:
        userRiver = userRiver.split("riverflow ")[1] if "riverflow " in userRiver else riverListDefault
    else:
        userRiver = userRiver.split(",") if "," in userRiver else riverListDefault
    
    # return river flow data
    if use_meteo_wxApi:
        return get_flood_openmeteo(location[0], location[1])
    else:
        # if userRiver a list
        if type(userRiver) == list:
            msg = ""
            for river in userRiver:
                msg += get_flood_noaa(location[0], location[1], river)
            return msg
        # if single river
        msg = get_flood_noaa(location[0], location[1], userRiver)
        return msg

def handle_mwx(message_from_id, deviceID, cmd):
    # NOAA Coastal and Marine Weather
    if myCoastalZone is None:
        logger.warning("System: Coastal Zone not set, please set in config.ini")
        return NO_ALERTS
    return get_nws_marine(zone=myCoastalZone, days=coastalForecastDays)

def handle_wxc(message_from_id, deviceID, cmd):
    location = get_node_location(message_from_id, deviceID)
    if use_meteo_wxApi and not "wxc" in cmd and not use_metric:
        #logger.debug("System: Bot Returning Open-Meteo API for weather imperial")
        weather = get_wx_meteo(str(location[0]), str(location[1]))
    elif use_meteo_wxApi:
        #logger.debug("System: Bot Returning Open-Meteo API for weather metric")
        weather = get_wx_meteo(str(location[0]), str(location[1]), 1)
    elif not use_meteo_wxApi and "wxc" in cmd or use_metric:
        #logger.debug("System: Bot Returning NOAA API for weather metric")
        weather = get_NOAAweather(str(location[0]), str(location[1]), 1)
    else:
        #logger.debug("System: Bot Returning NOAA API for weather imperial")
        weather = get_NOAAweather(str(location[0]), str(location[1]))
    return weather

def handle_emergency_alerts(message, message_from_id, deviceID):
    location = get_node_location(message_from_id, deviceID)
    if enableDEalerts:
        # nina Alerts
        return get_nina_alerts()
    if message.lower().startswith("ealert"):
        # Detailed alert FEMA
        return getIpawsAlert(str(location[0]), str(location[1]))
    else:
        # Headlines only FEMA
        return getIpawsAlert(str(location[0]), str(location[1]), shortAlerts=True)

def handleEarthquake(message, message_from_id, deviceID):
    location = get_node_location(message_from_id, deviceID)
    if "earthquake" in message.lower():
        return checkUSGSEarthQuake(str(location[0]), str(location[1]))
    
def handle_checklist(message, message_from_id, deviceID):
    name = get_name_from_number(message_from_id, 'short', deviceID)
    location = get_node_location(message_from_id, deviceID)
    return process_checklist_command(message_from_id, message, name, location)

def handle_bbspost(message, message_from_id, deviceID):
    if "$" in message and not "example:" in message:
        subject = message.split("$")[1].split("#")[0]
        subject = subject.rstrip()
        if "#" in message:
            body = message.split("#")[1]
            body = body.rstrip()
            logger.info(f"System: BBS Post: {subject} Body: {body}")
            return bbs_post_message(subject, body, message_from_id)
        elif not "example:" in message:
            return _("bbs_post_example_subject")
    elif "@" in message and not "example:" in message:
        toNode = message.split("@")[1].split("#")[0]
        toNode = toNode.rstrip()
        if toNode.startswith("!") and len(toNode) == 9:
            # mesh !hex
            try:
                toNode = int(toNode.strip("!"),16)
            except ValueError as e:
                toNode = 0
        elif toNode.isalpha() or not toNode.isnumeric() or len(toNode) < 5:
            # try short name
            toNode = get_num_from_short_name(toNode, deviceID)

        if "#" in message:
            if toNode == 0:
                return _("node_not_found", node=message.split("@")[1].split("#")[0])
            body = message.split("#")[1]
            return bbs_post_dm(toNode, body, message_from_id)
        else:
            return _("bbs_post_example_dm")
    elif not "example:" in message:
        return _("bbs_post_example")

def handle_bbsread(message):
    if "#" in message and not "example:" in message:
        messageID = int(message.split("#")[1])
        return bbs_read_message(messageID)
    elif not "example:" in message:
        return _("bbs_read_example")

def handle_bbsdelete(message, message_from_id):
    if "#" in message and not "example:" in message:
        messageID = int(message.split("#")[1])
        return bbs_delete_message(messageID, message_from_id)
    elif not "example:" in message:
        return _("bbs_delete_example")

def handle_messages(message, deviceID, channel_number, msg_history, publicChannel, isDM):
    if  "?" in message and isDM:
        return message.split("?")[0].title() + " " + _("messages_history_help", storeFlimit=storeFlimit)
    else:
        response = ""
        for msgH in msg_history:
            if msgH[4] == deviceID:
                if msgH[2] == channel_number or msgH[2] == publicChannel:
                    response += f"\n{msgH[0]}: {msgH[1]}"
        if len(response) > 0:
            return _("messages_history_title") + response
        else:
            return _("no_messages_history")

def handle_sun(message_from_id, deviceID, channel_number):
    location = get_node_location(message_from_id, deviceID, channel_number)
    return get_sun(str(location[0]), str(location[1]))

def sysinfo(message, message_from_id, deviceID):
    if "?" in message:
        return _("sysinfo_help")
    else:
        if enable_runShellCmd and file_monitor_enabled:
            # get the system information from the shell script
            # this is an example of how to run a shell script and return the data
            shellData = call_external_script(None, "script/sysEnv.sh")
            # check if the script returned data
            if shellData == "" or shellData == None:
                # no data returned from the script
                shellData = _("sysinfo_shell_error")
            return get_sysinfo(message_from_id, deviceID) + "\n" + shellData.rstrip()
        else:
            return get_sysinfo(message_from_id, deviceID)

def handle_lheard(message, nodeid, deviceID, isDM):
    if  "?" in message and isDM:
        return message.split("?")[0].title() + " " + _("lheard_help")

    # display last heard nodes add to response
    bot_response = _("lheard_title")
    bot_response += str(get_node_list(1))

    # show last users of the bot with the cmdHistory list
    history = handle_history(message, nodeid, deviceID, isDM, lheard=True)
    if history:
        bot_response += f'{_("lheard_users_title")}{history}'
    else:
        # trim the last \n
        bot_response = bot_response[:-1]
    
    # get count of nodes heard
    bot_response += _("lheard_mesh_nodes", count=len(seenNodes))

    # bot_response += getNodeTelemetry(deviceID)
    return bot_response

def handle_history(message, nodeid, deviceID, isDM, lheard=False):
    global cmdHistory, lheardCmdIgnoreNode, bbs_admin_list
    msg = ""
    buffer = []
    
    if  "?" in message and isDM:
        return message.split("?")[0].title() + " " + _("history_help")

    # show the last commands from the user to the bot
    if not lheard:
        for i in range(len(cmdHistory)):
            cmdTime = round((time.time() - cmdHistory[i]['time']) / 600) * 5
            prettyTime = getPrettyTime(cmdTime)

            # history display output
            if str(nodeid) in bbs_admin_list and cmdHistory[i]['nodeID'] not in lheardCmdIgnoreNode:
                buffer.append((get_name_from_number(cmdHistory[i]['nodeID'], 'short', deviceID), cmdHistory[i]['cmd'], prettyTime))
            elif cmdHistory[i]['nodeID'] == nodeid and cmdHistory[i]['nodeID'] not in lheardCmdIgnoreNode:
                buffer.append((get_name_from_number(nodeid, 'short', deviceID), cmdHistory[i]['cmd'], prettyTime))
        # message for output of the last commands
        buffer.reverse()
        # only return the last 4 commands
        if len(buffer) > 4:
            buffer = buffer[-4:]
        # create the message from the buffer list
        for i in range(0, len(buffer)):
            msg += f"{buffer[i][0]}: {buffer[i][1]} :{buffer[i][2]} ago"
            if i < len(buffer) - 1: msg += "\n" # add a new line if not the last line
    else:
        # sort the cmdHistory list by time, return the username and time into a new list which used for display
        for i in range(len(cmdHistory)):
            cmdTime = round((time.time() - cmdHistory[i]['time']) / 600) * 5
            prettyTime = getPrettyTime(cmdTime)

            if cmdHistory[i]['nodeID'] not in lheardCmdIgnoreNode:
                # add line to a new list for display
                nodeName = get_name_from_number(cmdHistory[i]['nodeID'], 'short', deviceID)
                if not any(d[0] == nodeName for d in buffer):
                    buffer.append((nodeName, prettyTime))
                else:
                    # update the time for the node in the buffer for the latest time in cmdHistory
                    for j in range(len(buffer)):
                        if buffer[j][0] == nodeName:
                            buffer[j] = (nodeName, prettyTime)
    
        # create the message from the buffer list
        buffer.reverse() # reverse the list to show the latest first
        for i in range(0, len(buffer)):
            msg += f"{buffer[i][0]}, {buffer[i][1]} ago"
            if i < len(buffer) - 1: msg += "\n" # add a new line if not the last line
            if i > 3: break # only return the last 4 nodes
    return msg

def handle_whereami(message_from_id, deviceID, channel_number):
    location = get_node_location(message_from_id, deviceID, channel_number)
    return where_am_i(str(location[0]), str(location[1]))

def handle_repeaterQuery(message_from_id, deviceID, channel_number):
    location = get_node_location(message_from_id, deviceID, channel_number)
    if repeater_lookup == "rbook":
        return getRepeaterBook(str(location[0]), str(location[1]))
    elif repeater_lookup == "artsci":
        return getArtSciRepeaters(str(location[0]), str(location[1]))
    else:
        return _("repeater_lookup_not_enabled")

def handle_tide(message_from_id, deviceID, channel_number):
    location = get_node_location(message_from_id, deviceID, channel_number)
    return get_NOAAtide(str(location[0]), str(location[1]))

def handle_moon(message_from_id, deviceID, channel_number):
    location = get_node_location(message_from_id, deviceID, channel_number)
    return get_moon(str(location[0]), str(location[1]))


def handle_whoami(message_from_id, deviceID, hop, snr, rssi, pkiStatus):
    try:
        loc = []
        msg = _("whoami_response", message_from_id=message_from_id, long_name=get_name_from_number(message_from_id, 'long', deviceID), short_name=get_name_from_number(message_from_id, 'short', deviceID), hex_id=decimal_to_hex(message_from_id))
        msg += _("signal_info", rssi=rssi, snr=snr, hop=hop)
        if pkiStatus[1] != 'ABC':
            msg += _("pki_info", pki_bit=pkiStatus[0], pub_key=pkiStatus[1])
    
        loc = get_node_location(message_from_id, deviceID)
        if loc != [latitudeValue, longitudeValue]:
            msg += _("location_info", lat=loc[0], lon=loc[1])
    
            # check the positionMetadata for nodeID and get metadata
            if positionMetadata and message_from_id in positionMetadata:
                metadata = positionMetadata[message_from_id]
                msg += f" alt:{metadata.get('altitude')}, speed:{metadata.get('groundSpeed')} bit:{metadata.get('precisionBits')}"
    except Exception as e:
        logger.error(f"System: Error in whoami: {e}")
        msg = _("whoami_error")
    return msg

def remove_self_message(message_from_id, message_string, timestamp):
    """Remove self-directed messages from the database to prevent loops."""
    try:
        # For self-messages, we need to find and delete the message that was sent to ourselves
        # This could be a DM to own node or a broadcast that looped back
        conn = db_handler.get_db_connection()
        cursor = conn.cursor()

        # Delete messages where from_node_id equals to_node_id (self DMs)
        # or where the message matches our own sent messages (looped broadcasts)
        cursor.execute("""
            DELETE FROM messages
            WHERE (from_node_id = to_node_id AND from_node_id = ?)
               OR (from_node_id = ? AND text = ? AND timestamp >= ?)
        """, (str(message_from_id), str(message_from_id), message_string, timestamp - 10))  # 10 second window

        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logger.info(f"Removed {deleted_count} self-message(s) from database to prevent loops")

        conn.commit()
    except Exception as e:
        logger.error(f"Error removing self-message: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def handle_whois(message, deviceID, channel_number, message_from_id):
    #return data on a node name or number
    if  "?" in message:
        return message.split("?")[0].title() + " " + _("whois_help")
    else:
        # get the nodeID from the message
        msg = ''
        node = ''
        # find the requested node in db
        if " " in message:
            node = message.split(" ")[1]
        if node.startswith("!") and len(node) == 9:
            # mesh !hex
            try:
                node = int(node.strip("!"),16)
            except ValueError as e:
                node = 0
        elif node.isalpha() or not node.isnumeric():
            # try short name
            node = get_num_from_short_name(node, deviceID)

        # get details on the node
        for i in range(len(seenNodes)):
            if seenNodes[i]['nodeID'] == int(node):
                msg = _("whois_node_info", nodeID=seenNodes[i]['nodeID'], long_name=get_name_from_number(seenNodes[i]['nodeID'], 'long', deviceID))
                msg += _("whois_last_seen", last_seen=time.ctime(seenNodes[i]['lastSeen']))
                break

        if msg == '':
            msg = _("whois_not_found")
        else:
            # if the user is an admin show the channel and interface and location
            if str(message_from_id) in bbs_admin_list:
                location = get_node_location(seenNodes[i]['nodeID'], deviceID, channel_number)
                msg += _("whois_admin_info", channel=seenNodes[i]['channel'], interface=seenNodes[i]['rxInterface'], lat=location[0], lon=location[1])
                if location != [latitudeValue, longitudeValue]:
                    msg += f"Loc: {where_am_i(str(location[0]), str(location[1]))}"
        return msg

def load_geofences_and_triggers():
    global ACTIVE_GEOFENCES, ACTIVE_TRIGGERS, ACTIVE_ZONES
    try:
        geofences = db_handler.get_geofences()
        ACTIVE_GEOFENCES = [g for g in geofences if g.get('active', 0) == 1]
        logger.debug(f"System: Loaded {len(ACTIVE_GEOFENCES)} active geofences")
        # Load zones (new table, assuming get_zones added to db_handler)
        try:
            zones = db_handler.get_zones()
            ACTIVE_ZONES = [z for z in zones if z.get('active', 0) == 1]
            logger.debug(f"System: Loaded {len(ACTIVE_ZONES)} active zones")
        except AttributeError:
            ACTIVE_ZONES = []  # get_zones not implemented yet
            logger.warning("System: get_zones not implemented in db_handler")
        ACTIVE_TRIGGERS = {}
        for gf in ACTIVE_GEOFENCES:
            gf_id = gf['id']
            triggers = db_handler.get_triggers()
            active_trigs = [t for t in triggers if t.get('zone_id') == gf_id and t.get('active', 0) == 1]
            for t in active_trigs:
                t['parameters'] = json.loads(t.get('parameters', '{}'))
            ACTIVE_TRIGGERS[gf_id] = active_trigs
        logger.info(f"Loaded geofences, zones, and triggers successfully: {len(ACTIVE_GEOFENCES)} geofences, {len(ACTIVE_TRIGGERS)} trigger sets")
    except Exception as e:
        logger.error(f"Failed to load geofences, zones, and triggers: {e}")
        ACTIVE_GEOFENCES = []
        ACTIVE_ZONES = []
        ACTIVE_TRIGGERS = {}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def is_in_zone(node_lat, node_lon, zone):
    distance = haversine(node_lat, node_lon, zone['latitude'], zone['longitude'])
    return distance <= zone['radius']

def execute_triggers_for_zone(zone_id, node_id, condition):
    triggers = ACTIVE_TRIGGERS.get(zone_id, [])
    zone = next((z for z in ACTIVE_GEOFENCES if z['id'] == zone_id), None)
    zone_name = zone['name'] if zone else 'Unknown'
    for trigger in [t for t in triggers if t['condition'] == condition]:
        action = trigger['action']
        params = trigger['parameters']
        if action == 'send_alert':
            msg = params.get('message', f"{condition.title()}ed {zone_name}")
            send_message(node_id, msg, 0, 1)  # Placeholder: adapt to existing send_message
        # Add more placeholder actions as needed

def check_and_execute_triggers(node_id, node_lat, node_lon):
    global NODE_ZONES, ACTIVE_GEOFENCES, ACTIVE_TRIGGERS
    previous_zones = NODE_ZONES.get(node_id, set())
    current_zones = set()
    for zone in ACTIVE_GEOFENCES:
        if is_in_zone(node_lat, node_lon, zone):
            current_zones.add(zone['id'])
    entered = current_zones - previous_zones
    exited = previous_zones - current_zones
    for zone_id in entered:
        execute_triggers_for_zone(zone_id, node_id, 'enter')
    for zone_id in exited:
        execute_triggers_for_zone(zone_id, node_id, 'exit')
    NODE_ZONES[node_id] = current_zones

def check_and_play_game(tracker, message_from_id, message_string, rxNode, channel_number, game_name, handle_game_func):
    global llm_enabled

    for i in range(len(tracker)):
        if tracker[i].get('nodeID') == message_from_id or tracker[i].get('userID') == message_from_id:
            last_played_key = 'last_played' if 'last_played' in tracker[i] else 'time'
            if tracker[i].get(last_played_key) > (time.time() - GAMEDELAY):
                if llm_enabled:
                    logger.debug(f"System: LLM Disabled for {message_from_id} for duration of {game_name}")

                # play the game
                send_message(handle_game_func(message_string, message_from_id, rxNode), channel_number, message_from_id, rxNode)
                return True, game_name
            else:
                # pop if the time exceeds 8 hours
                tracker.pop(i)
                return False, game_name
    return False, "None"

def checkPlayingGame(message_from_id, message_string, rxNode, channel_number):
    playingGame = False
    game = "None"

    trackers = [
        (dwPlayerTracker, "DopeWars", handleDopeWars) if 'dwPlayerTracker' in globals() else None,
        (lemonadeTracker, "LemonadeStand", handleLemonade) if 'lemonadeTracker' in globals() else None,
        (vpTracker, "VideoPoker", handleVideoPoker) if 'vpTracker' in globals() else None,
        (jackTracker, "BlackJack", handleBlackJack) if 'jackTracker' in globals() else None,
        (mindTracker, "MasterMind", handleMmind) if 'mindTracker' in globals() else None,
        (golfTracker, "GolfSim", handleGolf) if 'golfTracker' in globals() else None,
        (hangmanTracker, "Hangman", handleHangman) if 'hangmanTracker' in globals() else None,
        (hamtestTracker, "HamTest", handleHamtest) if 'hamtestTracker' in globals() else None,
    ]
    trackers = [tracker for tracker in trackers if tracker is not None]

    for tracker, game_name, handle_game_func in trackers:
        playingGame, game = check_and_play_game(tracker, message_from_id, message_string, rxNode, channel_number, game_name, handle_game_func)
        if playingGame:
            break

    return playingGame

def onReceive(packet, interface):
    global seenNodes
    # Priocess the incoming packet, handles the responses to the packet with auto_response()
    # Sends the packet to the correct handler for processing

    # extract interface details from inbound packet
    rxType = type(interface).__name__

    # Valies assinged to the packet
    rxNode, message_from_id, snr, rssi, hop, hop_away, channel_number = 0, 0, 0, 0, 0, 0, 0
    pkiStatus = (False, 'ABC')
    replyIDset = False
    emojiSeen = False
    isDM = False
    playingGame = False

    if DEBUGpacket:
        # Debug print the interface object
        for item in interface.__dict__.items(): intDebug = f"{item}\n"
        logger.debug(f"System: Packet Received on {rxType} Interface\n {intDebug} \n END of interface \n")
        # Debug print the packet for debugging
        logger.debug(f"Packet Received\n {packet} \n END of packet \n")

    # set the value for the incomming interface
    if rxType == 'SerialInterface':
        rxInterface = interface.__dict__.get('devPath', 'unknown')
        if port1 in rxInterface: rxNode = 1
        elif multiple_interface and port2 in rxInterface: rxNode = 2
        elif multiple_interface and port3 in rxInterface: rxNode = 3
        elif multiple_interface and port4 in rxInterface: rxNode = 4
        elif multiple_interface and port5 in rxInterface: rxNode = 5
        elif multiple_interface and port6 in rxInterface: rxNode = 6
        elif multiple_interface and port7 in rxInterface: rxNode = 7
        elif multiple_interface and port8 in rxInterface: rxNode = 8
        elif multiple_interface and port9 in rxInterface: rxNode = 9

    if rxType == 'TCPInterface':
        rxHost = interface.__dict__.get('hostname', 'unknown')
        if rxHost and hostname1 in rxHost and interface1_type == 'tcp': rxNode = 1
        elif multiple_interface and rxHost and hostname2 in rxHost and interface2_type == 'tcp': rxNode = 2
        elif multiple_interface and rxHost and hostname3 in rxHost and interface3_type == 'tcp': rxNode = 3
        elif multiple_interface and rxHost and hostname4 in rxHost and interface4_type == 'tcp': rxNode = 4
        elif multiple_interface and rxHost and hostname5 in rxHost and interface5_type == 'tcp': rxNode = 5
        elif multiple_interface and rxHost and hostname6 in rxHost and interface6_type == 'tcp': rxNode = 6
        elif multiple_interface and rxHost and hostname7 in rxHost and interface7_type == 'tcp': rxNode = 7
        elif multiple_interface and rxHost and hostname8 in rxHost and interface8_type == 'tcp': rxNode = 8
        elif multiple_interface and rxHost and hostname9 in rxHost and interface9_type == 'tcp': rxNode = 9
    if rxType == 'BLEInterface':
        if interface1_type == 'ble': rxNode = 1
        elif multiple_interface and interface2_type == 'ble': rxNode = 2
        elif multiple_interface and interface3_type == 'ble': rxNode = 3
        elif multiple_interface and interface4_type == 'ble': rxNode = 4
        elif multiple_interface and interface5_type == 'ble': rxNode = 5
        elif multiple_interface and interface6_type == 'ble': rxNode = 6
        elif multiple_interface and interface7_type == 'ble': rxNode = 7
        elif multiple_interface and interface8_type == 'ble': rxNode = 8
        elif multiple_interface and interface9_type == 'ble': rxNode = 9
    
    # check if the packet has a channel flag use it
    if packet.get('channel'):
        channel_number = packet.get('channel', 0)

    # set the message_from_id
    message_from_id = packet['from']

    # if message_from_id is not in the seenNodes list add it
    if not any(node['nodeID'] == message_from_id for node in seenNodes):
        seenNodes.append({'nodeID': message_from_id, 'rxInterface': rxNode, 'channel': channel_number, 'welcome': False, 'lastSeen': time.time()})
        # Ensure node exists in database
        try:
            existing_node = db_handler.get_nodes()  # This gets all nodes, inefficient but works
            node_exists = any(n['node_id'] == str(message_from_id) for n in existing_node)
            if not node_exists:
                name = get_name_from_number(message_from_id, 'long', rxNode)
                db_handler.add_node(message_from_id, name, time.time(), None, None, None, None)
                logger.debug(f"System: Added new node {message_from_id} to database")
        except Exception as e:
            logger.error(f"System: Failed to add new node {message_from_id} to database: {e}")

    # Update last_seen for the node on every reception
    for node in seenNodes:
        if node['nodeID'] == message_from_id:
            node['lastSeen'] = time.time()
            # Update last_seen in database
            try:
                db_handler.update_node_last_seen(message_from_id)
                # Broadcast node activity update
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(broadcast_map_update("node_activity", {
                        "node_id": str(message_from_id),
                        "last_seen": time.time(),
                        "is_online": True
                    }))
                except RuntimeError:
                    # No running event loop, skip broadcast
                    pass
            except Exception as e:
                logger.error(f"System: Failed to update last_seen for node {message_from_id}: {e}")
            break

    # BBS DM MAIL CHECKER
    if bbs_enabled and 'decoded' in packet:
        
        msg = bbs_check_dm(message_from_id)
        if msg:
            # wait a responseDelay to avoid message collision from lora-ack.
            time.sleep(responseDelay)
            logger.info(f"System: BBS DM Delivery: {msg[1]} For: {get_name_from_number(message_from_id, 'long', rxNode)}")
            message = _("bbs_dm_delivery", body=msg[1], from_user=get_name_from_number(msg[2], 'long', rxNode))
            bbs_delete_dm(msg[0], msg[1])
            send_message(message, channel_number, message_from_id, rxNode)
            
    # handle TEXT_MESSAGE_APP
    try:
        if 'decoded' in packet and packet['decoded']['portnum'] == 'TEXT_MESSAGE_APP':
            message_bytes = packet['decoded']['payload']
            message_string = message_bytes.decode('utf-8')
            via_mqtt = packet['decoded'].get('viaMqtt', False)
            rx_time = packet['decoded'].get('rxTime', time.time())

            # Save incoming text message to database
            from_node_id = str(message_from_id)
            to_id = packet.get('to', 0)
            to_node_id = 'broadcast' if to_id == 0 else str(to_id)
            channel = 'general' if channel_number == 0 else str(channel_number)
            text = message_string
            timestamp = int(time.time())
            is_dm = 1 if to_id != 0 else 0

            # Determine if message is addressed to bot's own node IDs
            bot_node_ids = [globals().get(f'myNodeNum{i}') for i in range(1, 10) if globals().get(f'myNodeNum{i}') is not None]
            is_to_bot = to_node_id != 'broadcast' and int(to_node_id) in bot_node_ids
            status = 'delivered' if is_to_bot else 'sent'
            delivered = True if is_to_bot else False

            try:
                message_id = db_handler.save_message(from_node_id, to_node_id, channel, text, timestamp, is_dm, status=status, delivered=delivered)
                logger.debug(f"System: Saved message from {from_node_id} to {to_node_id} in channel {channel} with status {status}")
            except Exception as e:
                logger.error(f"System: Failed to save message from {from_node_id}: {e}")
                message_id = None

            # check if the packet is from us
            if message_from_id in [myNodeNum1, myNodeNum2, myNodeNum3, myNodeNum4, myNodeNum5, myNodeNum6, myNodeNum7, myNodeNum8, myNodeNum9]:
                logger.warning(_("loop_detected", message_from_id=message_from_id))
                # Remove self-message from send queue to prevent infinite loops
                remove_self_message(message_from_id, message_string, timestamp)
                return

            # get the signal strength and snr if available
            hop_count = 0
            if packet.get('rxSnr') or packet.get('rxRssi'):
                snr = packet.get('rxSnr', 0)
                rssi = packet.get('rxRssi', 0)
                # Update telemetry data
                try:
                    db_handler.update_node_telemetry(message_from_id, snr=snr, rssi=rssi, hop_count=hop_count)
                except Exception as e:
                    logger.error(f"System: Failed to update telemetry for node {message_from_id}: {e}")

            # check if the packet has a publicKey flag use it
            if packet.get('publicKey'):
                pkiStatus = packet.get('pkiEncrypted', False), packet.get('publicKey', 'ABC')
                # Update PKI status in telemetry
                try:
                    db_handler.update_node_telemetry(message_from_id, pki_status=str(pkiStatus[1]))
                except Exception as e:
                    logger.error(f"System: Failed to update PKI status for node {message_from_id}: {e}")
            
            # check if the packet has replyId flag // currently unused in the code
            if packet.get('replyId'):
                replyIDset = packet.get('replyId', False)
            
            # check if the packet has emoji flag set it // currently unused in the code
            if packet.get('emoji'):
                emojiSeen = packet.get('emoji', False)

            # check if the packet has a hop count flag use it
            if packet.get('hopsAway'):
                hop_away = packet.get('hopsAway', 0)
            else:
                # if the packet does not have a hop count try other methods
                if packet.get('hopLimit'):
                    hop_limit = packet.get('hopLimit', 0)
                else:
                    hop_limit = 0
                
                if packet.get('hopStart'):
                    hop_start = packet.get('hopStart', 0)
                else:
                    hop_start = 0
            
            if enableHopLogs:
                logger.debug(f"System: Packet HopDebugger: hop_away:{hop_away} hop_limit:{hop_limit} hop_start:{hop_start}")
            
            if hop_away == 0 and hop_limit == 0 and hop_start == 0:
                hop = "Last Hop"
                hop_count = 0
            
            if hop_start == hop_limit:
                hop = "Direct"
                hop_count = 0
            elif hop_start == 0 and hop_limit > 0 or via_mqtt:
                hop = "MQTT"
                hop_count = 0
            else:
                # set hop to Direct if the message was sent directly otherwise set the hop count
                if hop_away > 0:
                    hop_count = hop_away
                else:
                    hop_count = hop_start - hop_limit
                    #print (f"calculated hop count: {hop_start} - {hop_limit} = {hop_count}")

                hop = f"{hop_count} hops"
            
            if help_message in message_string or welcome_message in message_string or "CMD?:" in message_string:
                # ignore help and welcome messages
                logger.warning(_("ignore_welcome_message", user=get_name_from_number(message_from_id, 'long', rxNode)))
                return
        
            # If the packet is a DM (Direct Message) respond to it, otherwise validate its a message for us on the channel
            if packet['to'] in [myNodeNum1, myNodeNum2, myNodeNum3, myNodeNum4, myNodeNum5, myNodeNum6, myNodeNum7, myNodeNum8, myNodeNum9]:
                # message is DM to us
                isDM = True
                # check if the message contains a trap word, DMs are always responded to
                if (messageTrap(message_string) and not llm_enabled) or messageTrap(message_string.split()[0]):
                    # log the message to stdout
                    logger.info(f"Device:{rxNode} Channel: {channel_number} " + CustomFormatter.green + f"Received DM: " + CustomFormatter.white + f"{message_string} " + CustomFormatter.purple +\
                                "From: " + CustomFormatter.white + f"{get_name_from_number(message_from_id, 'long', rxNode)}")
                    # respond with DM
                    send_message(auto_response(message_string, snr, rssi, hop, pkiStatus, message_from_id, channel_number, rxNode, isDM), channel_number, message_from_id, rxNode)
                else:
                    # DM is useful for games or LLM
                    if games_enabled and (hop == "Direct" or hop_count < game_hop_limit):
                        playingGame = checkPlayingGame(message_from_id, message_string, rxNode, channel_number)
                    else:
                        if games_enabled:
                            logger.warning(f"Device:{rxNode} Ignoring Request to Play Game: {message_string} From: {get_name_from_number(message_from_id, 'long', rxNode)} with hop count: {hop}")
                            send_message(_("game_hop_limit_exceeded", hop_count=hop_count), channel_number, message_from_id, rxNode)
                            time.sleep(responseDelay)
                        else:
                            playingGame = False

                    if not playingGame:
                        if llm_enabled and llmReplyToNonCommands:
                            # respond with LLM
                            llm = handle_llm(message_from_id, channel_number, rxNode, message_string, publicChannel)
                            send_message(llm, channel_number, message_from_id, rxNode)
                            time.sleep(responseDelay)
                        else:
                            # respond with welcome message on DM
                            logger.warning(f"Device:{rxNode} Ignoring DM: {message_string} From: {get_name_from_number(message_from_id, 'long', rxNode)}")
                            
                            # if seenNodes list is not marked as welcomed send welcome message
                            if not any(node['nodeID'] == message_from_id and node['welcome'] == True for node in seenNodes):
                                # send welcome message
                                send_message(welcome_message, channel_number, message_from_id, rxNode)
                                time.sleep(responseDelay)
                                # mark the node as welcomed
                                for node in seenNodes:
                                    if node['nodeID'] == message_from_id:
                                        node['welcome'] = True
                            else:
                                if dad_jokes_enabled:
                                    # respond with a dad joke on DM
                                    send_message(tell_joke(), channel_number, message_from_id, rxNode)
                                else:
                                    # respond with help message on DM
                                    send_message(help_message, channel_number, message_from_id, rxNode)

                            time.sleep(responseDelay)
                            
                    # log the message to the message log
                    if log_messages_to_file:
                        msgLogger.info(f"Device:{rxNode} Channel:{channel_number} | {get_name_from_number(message_from_id, 'long', rxNode)} | DM | " + message_string.replace('\n', '-nl-'))
            else:
                # message is on a channel
                if messageTrap(message_string):
                    # message is for us to respond to, or is it...
                    if ignoreDefaultChannel and channel_number == publicChannel:
                        logger.debug(f"System: Ignoring CMD:{message_string} From: {get_name_from_number(message_from_id, 'short', rxNode)} Default Channel:{channel_number}")
                    elif str(message_from_id) in bbs_ban_list:
                        logger.debug(f"System: Ignoring CMD:{message_string} From: {get_name_from_number(message_from_id, 'short', rxNode)} Cantankerous Node")
                    elif str(channel_number) in ignoreChannels:
                        logger.debug(f"System: Ignoring CMD:{message_string} From: {get_name_from_number(message_from_id, 'short', rxNode)} Ignored Channel:{channel_number}")
                    elif cmdBang and not message_string.startswith("!"):
                        logger.debug(f"System: Ignoring CMD:{message_string} From: {get_name_from_number(message_from_id, 'short', rxNode)} Didnt sound like they meant it")
                    else:
                        # message is for bot to respond to, seriously this time..
                        logger.info(f"Device:{rxNode} Channel:{channel_number} " + CustomFormatter.green + "ReceivedChannel: " + CustomFormatter.white + f"{message_string} " + CustomFormatter.purple +\
                                    "From: " + CustomFormatter.white + f"{get_name_from_number(message_from_id, 'long', rxNode)}")
                        if useDMForResponse:
                            # respond to channel message via direct message
                            send_message(auto_response(message_string, snr, rssi, hop, pkiStatus, message_from_id, channel_number, rxNode, isDM), channel_number, message_from_id, rxNode)
                        else:
                            # or respond to channel message on the channel itself
                            if channel_number == publicChannel and antiSpam:
                                # warning user spamming default channel
                                logger.warning(_("antispam_warning", user=get_name_from_number(message_from_id, 'long', rxNode)))
                            
                                # respond to channel message via direct message
                                send_message(auto_response(message_string, snr, rssi, hop, pkiStatus, message_from_id, channel_number, rxNode, isDM), channel_number, message_from_id, rxNode)
                            else:
                                # respond to channel message on the channel itself
                                send_message(auto_response(message_string, snr, rssi, hop, pkiStatus, message_from_id, channel_number, rxNode, isDM), channel_number, 0, rxNode)

                else:
                    # message is not for us to respond to
                    # ignore the message but add it to the message history list
                    if zuluTime:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S%p")
                    
                    if len(msg_history) < storeFlimit:
                        msg_history.append((get_name_from_number(message_from_id, 'long', rxNode), message_string, channel_number, timestamp, rxNode))
                    else:
                        msg_history.pop(0)
                        msg_history.append((get_name_from_number(message_from_id, 'long', rxNode), message_string, channel_number, timestamp, rxNode))

                    # print the message to the log and sdout
                    logger.info(f"Device:{rxNode} Channel:{channel_number} " + CustomFormatter.green + "Ignoring Message:" + CustomFormatter.white +\
                                f" {message_string} " + CustomFormatter.purple + "From:" + CustomFormatter.white + f" {get_name_from_number(message_from_id)}")
                    if log_messages_to_file:
                        msgLogger.info(f"Device:{rxNode} Channel:{channel_number} | {get_name_from_number(message_from_id, 'long', rxNode)} | " + message_string.replace('\n', '-nl-'))

                     # repeat the message on the other device
                    if repeater_enabled and multiple_interface:         
                        # wait a responseDelay to avoid message collision from lora-ack.
                        time.sleep(responseDelay)
                        rMsg = (f"{message_string} From:{get_name_from_number(message_from_id, 'short', rxNode)}")
                        # if channel found in the repeater list repeat the message
                        if str(channel_number) in repeater_channels:
                            for i in range(1, 10):
                                if globals().get(f'interface{i}_enabled', False) and i != rxNode:
                                    logger.debug(f"Repeating message on Device{i} Channel:{channel_number}")
                                    send_message(rMsg, channel_number, 0, i)
                                    time.sleep(responseDelay)
                    
                    # if QRZ enabled check if we have said hello
                    if qrz_hello_enabled:
                        if never_seen_before(message_from_id):
                            name = get_name_from_number(message_from_id, 'short', rxNode)
                            if isinstance(name, str) and name.startswith("!") and len(name) == 9:
                                # we didnt get a info packet yet so wait and ingore this go around
                                logger.debug(_("qrz_ignored"))
                            else:
                                # add to qrz_hello list
                                hello(message_from_id, name)
                                # send a hello message as a DM
                                if not train_qrz:
                                    time.sleep(responseDelay)
                                    send_message(f"Hello {name} {qrz_hello_string}", channel_number, message_from_id, rxNode)
                                    time.sleep(responseDelay)
        elif 'decoded' in packet and packet['decoded']['portnum'] == 'ROUTING_APP':
            # Handle ACK packets for message delivery confirmation
            routing = packet['decoded'].get('routing', {})
            if routing.get('errorReason') == 'NONE':
                # This is a successful ACK
                request_id = routing.get('requestId')
                if request_id:
                    # Find the message by request_id (which should match message_id)
                    try:
                        message_info = db_handler.get_message_by_id(str(request_id))
                        if message_info:
                            db_handler.update_message_delivery_status(str(request_id), delivered=True, status='delivered')
                            # Update node info on packet reception
                            packet_data = {'snr': packet.get('rxSnr'), 'rssi': packet.get('rxRssi'), 'last_telemetry': time.time()}
                            db_handler.update_node_on_packet(message_from_id, packet_data)
                            logger.info(f"System: Message {request_id} delivery confirmed via ACK")
                    except Exception as e:
                        logger.error(f"System: Failed to update message delivery status for ACK {request_id}: {e}")
        else:
            # Evaluate non TEXT_MESSAGE_APP packets
            consumeMetadata(packet, rxNode)
            # Check for position packets
            if 'decoded' in packet and 'position' in packet['decoded']:
                pos = packet['decoded']['position']
                lat = pos.get('latitude', 0)
                lon = pos.get('longitude', 0)
                if lat != 0 and lon != 0:  # Valid position
                    # Persist node metadata to database
                    name = get_name_from_number(message_from_id, 'long', rxNode)
                    battery = pos.get('batteryLevel')
                    altitude = pos.get('altitude', 0)
                    ground_speed = pos.get('groundSpeed')
                    precision_bits = pos.get('precisionBits')
                    try:
                        db_handler.update_node_last_seen(message_from_id)
                        db_handler.update_node(message_from_id, name=name, battery_level=battery, latitude=lat, longitude=lon, altitude=altitude)
                        # Update telemetry data
                        db_handler.update_node_telemetry(
                            message_from_id,
                            ground_speed=ground_speed,
                            precision_bits=precision_bits
                        )
                        logger.debug(f"System: Updated node {message_from_id} position: {lat},{lon}")
                    except Exception as e:
                        logger.error(f"System: Failed to update node {message_from_id} position: {e}")
                    check_and_execute_triggers(message_from_id, lat, lon)

                    # Broadcast position update to WebSocket clients
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(broadcast_map_update("node_position", {
                            "node_id": str(message_from_id),
                            "lat": lat,
                            "lng": lon,
                            "altitude": altitude,
                            "last_seen": time.time()
                        }))
                    except RuntimeError:
                        # No running event loop, skip broadcast
                        pass

                    # Broadcast position update to WebSocket clients
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(broadcast_map_update("node_position", {
                            "node_id": str(message_from_id),
                            "lat": lat,
                            "lng": lon,
                            "altitude": altitude,
                            "last_seen": time.time()
                        }))
                    except RuntimeError:
                        # No running event loop, skip broadcast
                        pass
    except KeyError as e:
        logger.critical(f"System: Error processing packet: {e} Device:{rxNode}")
        logger.debug(f"System: Error Packet = {packet}")

async def start_rx():
    print (CustomFormatter.bold_white + _("bot_exit") + CustomFormatter.reset)

    # Start the receive subscriber using pubsub via meshtastic library
    pub.subscribe(onReceive, 'meshtastic.receive')
    pub.subscribe(onDisconnect, 'meshtastic.connection.lost')

    global db_conn
    db_conn = db_handler.get_db_connection()

    for i in range(1, 10):
        if globals().get(f'interface{i}_enabled', False):
            myNodeNum = globals().get(f'myNodeNum{i}', 0)
            logger.info(_("autostart_message", device_id=i, long_name=get_name_from_number(myNodeNum, 'long', i), short_name=get_name_from_number(myNodeNum, 'short', i), node_num=myNodeNum, hex_id=decimal_to_hex(myNodeNum)))

    # Resend undelivered messages to online nodes at startup
    try:
        all_nodes = db_handler.get_nodes()
        online_nodes = [n for n in all_nodes if n.get('is_online', 0) == 1]
        if online_nodes:
            logger.info(f"System: Checking for undelivered messages to {len(online_nodes)} online nodes at startup")
            for node in online_nodes:
                resend_undelivered_messages(node['node_id'])
        else:
            logger.debug("System: No online nodes found at startup for message resend")
    except Exception as e:
        logger.error(f"System: Error during startup message resend: {e}")

    if llm_enabled:
        logger.debug(_("llm_model_loading", llm_model=llmModel))
        llmLoad = llm_query(" ")
        if "trouble" not in llmLoad:
            logger.debug(_("llm_model_loaded", llm_model=llmModel))

    if log_messages_to_file:
        logger.debug(_("log_to_disk"))
    if syslog_to_file:
        logger.debug(_("syslog_to_disk"))
    if bbs_enabled:
        logger.debug(_("bbs_enabled", bbsdb=bbsdb, count=len(bbs_messages), dm_count=(len(bbs_dm) - 1)))
        if bbs_link_enabled:
            if len(bbs_link_whitelist) > 0:
                logger.debug(_("bbs_link_enabled_peers", count=len(bbs_link_whitelist)))
            else:
                logger.debug(_("bbs_link_enabled_all"))
    if solar_conditions_enabled:
        logger.debug(_("celestial_telemetry_enabled"))
    if location_enabled:
        if use_meteo_wxApi:
            logger.debug(_("location_telemetry_open_meteo"))
        else:
            logger.debug(_("location_telemetry_noaa"))
    if dad_jokes_enabled:
        logger.debug(_("dad_jokes_enabled"))
    if coastalEnabled:
        logger.debug(_("coastal_forecast_enabled"))
    if games_enabled:
        logger.debug(_("games_enabled"))
    if wikipedia_enabled:
        logger.debug(_("wikipedia_enabled"))
    if motd_enabled:
        logger.debug(_("motd_enabled", motd=MOTD))
    if sentry_enabled:
        logger.debug(_("sentry_mode_enabled", radius=sentry_radius, channel=secure_channel))
    if highfly_enabled:
        logger.debug(_("highfly_enabled", altitude=highfly_altitude, channel=highfly_channel))
    if store_forward_enabled:
        logger.debug(_("store_forward_enabled", limit=storeFlimit))
    if useDMForResponse:
        logger.debug(_("respond_by_dm_only"))
    if enableEcho:
        logger.debug(_("echo_enabled"))
    if repeater_enabled and multiple_interface:
        logger.debug(_("repeater_enabled", channels=repeater_channels))
    if radio_detection_enabled:
        logger.debug(_("radio_detection_enabled", address=rigControlServerAddress, channels=sigWatchBroadcastCh, freq=get_freq_common_name(get_hamlib('f'))))
    if file_monitor_enabled:
        logger.debug(_("file_monitor_enabled", path=file_monitor_file_path, channels=file_monitor_broadcastCh))
        if enable_runShellCmd:
            logger.debug(_("shell_command_monitor_enabled"))
        if read_news_enabled:
            logger.debug(_("news_reader_enabled", path=news_file_path))
        if bee_enabled:
            logger.debug(_("bee_monitor_enabled"))
    if wxAlertBroadcastEnabled:
        logger.debug(_("weather_alert_broadcast_enabled", channels=wxAlertBroadcastChannel))
    if emergencyAlertBrodcastEnabled:
        logger.debug(_("emergency_alert_broadcast_enabled", channels=emergencyAlertBroadcastCh, fips=myStateFIPSList))
        # check if the FIPS codes are set
        if myStateFIPSList == ['']:
            logger.warning(_("no_fips_codes"))
    if emergency_responder_enabled:
        logger.debug(_("emergency_responder_enabled", channels=emergency_responder_alert_channel, interface=emergency_responder_alert_interface))
    if volcanoAlertBroadcastEnabled:
        logger.debug(_("volcano_alert_broadcast_enabled", channels=volcanoAlertBroadcastChannel))
    if qrz_hello_enabled and train_qrz:
        logger.debug(_("qrz_welcome_training"))
    if qrz_hello_enabled and not train_qrz:
        logger.debug(_("qrz_welcome_enabled"))
    if checklist_enabled:
        logger.debug(_("checklist_enabled"))
    if ignoreChannels != []:
        logger.debug(_("ignoring_channels", channels=ignoreChannels))
    if noisyNodeLogging:
        logger.debug(_("noisy_node_logging_enabled"))
    if enableSMTP:
        if enableImap:
            logger.debug(_("smtp_imap_enabled"))
        else:
            logger.debug(_("smtp_enabled"))
    if scheduler_enabled:
        # Reminder Scheduler is enabled every Monday at noon send a log message
        schedule.every().monday.at("12:00").do(lambda: logger.info(_("scheduler_reminder")))

        # basic scheduler
        if schedulerValue != '':
            logger.debug(_("scheduler_started_config"))
            if schedulerValue.lower() == 'day':
                if schedulerTime != '':
                    # Send a message every day at the time set in schedulerTime
                    schedule.every().day.at(schedulerTime).do(lambda: send_message(schedulerMessage, schedulerChannel, 0, schedulerInterface))
                else:
                    # Send a message every day at the time set in schedulerInterval
                    schedule.every(int(schedulerInterval)).days.do(lambda: send_message(schedulerMessage, schedulerChannel, 0, schedulerInterface))
            elif 'mon' in schedulerValue.lower() and schedulerTime != '':
                # Send a message every Monday at the time set in schedulerTime
                schedule.every().monday.at(schedulerTime).do(lambda: send_message(schedulerMessage, schedulerChannel, 0, schedulerInterface))
            elif 'tue' in schedulerValue.lower() and schedulerTime != '':
                # Send a message every Tuesday at the time set in schedulerTime
                schedule.every().tuesday.at(schedulerTime).do(lambda: send_message(schedulerMessage, schedulerChannel, 0, schedulerInterface))
            elif 'wed' in schedulerValue.lower() and schedulerTime != '':
                # Send a message every Wednesday at the time set in schedulerTime
                schedule.every().wednesday.at(schedulerTime).do(lambda: send_message(schedulerMessage, schedulerChannel, 0, schedulerInterface))
            elif 'thu' in schedulerValue.lower() and schedulerTime != '':
                # Send a message every Thursday at the time set in schedulerTime
                schedule.every().thursday.at(schedulerTime).do(lambda: send_message(schedulerMessage, schedulerChannel, 0, schedulerInterface))
            elif 'fri' in schedulerValue.lower() and schedulerTime != '':
                # Send a message every Friday at the time set in schedulerTime
                schedule.every().friday.at(schedulerTime).do(lambda: send_message(schedulerMessage, schedulerChannel, 0, schedulerInterface))
            elif 'sat' in schedulerValue.lower() and schedulerTime != '':
                # Send a message every Saturday at the time set in schedulerTime
                schedule.every().saturday.at(schedulerTime).do(lambda: send_message(schedulerMessage, schedulerChannel, 0, schedulerInterface))
            elif 'sun' in schedulerValue.lower() and schedulerTime != '':
                # Send a message every Sunday at the time set in schedulerTime
                schedule.every().sunday.at(schedulerTime).do(lambda: send_message(schedulerMessage, schedulerChannel, 0, schedulerInterface))
            elif 'hour' in schedulerValue.lower():
                # Send a message every hour at the time set in schedulerTime
                schedule.every(int(schedulerInterval)).hours.do(lambda: send_message(schedulerMessage, schedulerChannel, 0, schedulerInterface))
            elif 'min' in schedulerValue.lower():
                # Send a message every minute at the time set in schedulerTime
                schedule.every(int(schedulerInterval)).minutes.do(lambda: send_message(schedulerMessage, schedulerChannel, 0, schedulerInterface))
        else:
            logger.debug(_("scheduler_started"))

        # Enhanced Examples of using the scheduler, Times here are in 24hr format
        # https://schedule.readthedocs.io/en/stable/

        # Good Morning Every day at 09:00 using send_message function to channel 2 on device 1
        #schedule.every().day.at("09:00").do(lambda: send_message("Good Morning", 2, 0, 1))

        # Send WX every Morning at 08:00 using handle_wxc function to channel 2 on device 1
        #schedule.every().day.at("08:00").do(lambda: send_message(handle_wxc(0, 1, 'wx'), 2, 0, 1))
        
        # Send Weather Channel Notice Wed. Noon on channel 2, device 1
        #schedule.every().wednesday.at("12:00").do(lambda: send_message("Weather alerts available on 'Alerts' channel with default 'AQ==' key.", 2, 0, 1))

        # Send config URL for Medium Fast Network Use every other day at 10:00 to default channel 2 on device 1
        #schedule.every(2).days.at("10:00").do(lambda: send_message("Join us on Medium Fast https://meshtastic.org/e/#CgcSAQE6AggNEg4IARAEOAFAA0gBUB5oAQ", 2, 0, 1))

        # Send a Net Starting Now Message Every Wednesday at 19:00 using send_message function to channel 2 on device 1
        #schedule.every().wednesday.at("19:00").do(lambda: send_message("Net Starting Now", 2, 0, 1))

        # Send a Welcome Notice for group on the 15th and 25th of the month at 12:00 using send_message function to channel 2 on device 1
        #schedule.every().day.at("12:00").do(lambda: send_message("Welcome to the group", 2, 0, 1)).day(15, 25)

        # Send a joke every 6 hours using tell_joke function to channel 2 on device 1
        #schedule.every(6).hours.do(lambda: send_message(tell_joke(), 2, 0, 1))

        # Send a joke every 2 minutes using tell_joke function to channel 2 on device 1
        #schedule.every(2).minutes.do(lambda: send_message(tell_joke(), 2, 0, 1))

        # Send the Welcome Message every other day at 08:00 using send_message function to channel 2 on device 1
        #schedule.every(2).days.at("08:00").do(lambda: send_message(welcome_message, 2, 0, 1))

        # Send the MOTD every day at 13:00 using send_message function to channel 2 on device 1
        #schedule.every().day.at("13:00").do(lambda: send_message(MOTD, 2, 0, 1))

        # Send bbslink looking for peers every other day at 10:00 using send_message function to channel 3 on device 1
        #schedule.every(2).days.at("10:00").do(lambda: send_message("bbslink MeshBot looking for peers", 3, 0, 1))
        await BroadcastScheduler()

    # here we go loopty loo
    while True:
        await asyncio.sleep(0.5)
        pass

# Hello World
async def reload_task():
    while True:
        await asyncio.sleep(1800)  # 30 minutes
        load_geofences_and_triggers()

async def command_poller():
    """Poll and process pending commands."""
    while True:
        try:
            cmds = db_handler.poll_pending_commands()
            logging.debug(f"Command poller found {len(cmds)} pending commands")
            for cmd in cmds:
                max_retries = 5  # Increased from 3
                for attempt in range(max_retries):
                    conn = db_handler.get_db_connection()
                    start_time = time.time()
                    try:
                        logging.debug(f"Starting transaction for command {cmd['id']} (attempt {attempt + 1})")
                        # Use BEGIN DEFERRED instead of BEGIN IMMEDIATE to reduce lock conflicts
                        conn.execute("BEGIN DEFERRED")
                        cursor = conn.cursor()

                        handler = HANDLERS.get(cmd['command_type'])
                        if handler:
                            result = handler(cmd)
                            db_handler.update_command_status(cmd['id'], 'executed', str(result), datetime.now().isoformat())
                            logging.info(f"Command {cmd['id']} executed successfully")
                        else:
                            db_handler.update_command_status(cmd['id'], 'failed', 'Unknown command type')
                            logging.warning(f"Unknown command type: {cmd['command_type']}")

                        conn.commit()
                        transaction_time = time.time() - start_time
                        logging.debug(f"Command {cmd['id']} transaction completed in {transaction_time:.3f}s")
                        break  # Success, exit retry loop
                    except Exception as e:
                        conn.rollback()
                        transaction_time = time.time() - start_time
                        error_str = str(e)
                        if "database is locked" in error_str.lower() and attempt < max_retries - 1:
                            # Increased backoff delay
                            delay = min(0.2 * (2 ** attempt), 3.0)  # 0.2, 0.4, 0.8, 1.6, 3.0
                            logging.warning(f"Command {cmd['id']} failed due to database lock after {transaction_time:.3f}s, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})")
                            await asyncio.sleep(delay)
                            continue
                        else:
                            db_handler.update_command_status(cmd['id'], 'failed', f"Execution error: {error_str}")
                            logging.error(f"Command {cmd['id']} failed after {transaction_time:.3f}s: {e}")
                            break  # Final failure or non-lock error
                    finally:
                        conn.close()

            await asyncio.sleep(poll_interval)
        except Exception as e:
            logging.error(f"Error in command poller: {e}")
            await asyncio.sleep(poll_interval)


async def cleanup_task():
    """Daily cleanup of old commands."""
    while True:
        try:
            await asyncio.sleep(86400)  # 24 hours
            deleted = db_handler.cleanup_old_commands(7)
            logging.info(f"Cleaned up {deleted} old commands")
        except Exception as e:
            logging.error(f"Error in cleanup task: {e}")


async def node_status_check_task():
    """Periodic check for offline nodes every 10 minutes."""
    while True:
        try:
            await asyncio.sleep(600)  # 10 minutes
            db_handler.check_and_update_offline_nodes()
            logging.debug("Performed periodic node status check")
        except Exception as e:
            logging.error(f"Error in node status check task: {e}")


async def message_resend_task():
    """Periodic check for undelivered messages and attempt resend to online recipients every 30 seconds."""
    while True:
        try:
            await asyncio.sleep(30)  # 30 seconds
            all_nodes = db_handler.get_nodes()
            online_nodes = [n for n in all_nodes if n.get('is_online', 0) == 1]

            # Filter out bot's own nodes to prevent self-resending
            bot_node_ids = [globals().get(f'myNodeNum{i}') for i in range(1, 10) if globals().get(f'myNodeNum{i}') is not None]
            online_nodes = [n for n in online_nodes if int(n['node_id']) not in bot_node_ids]

            if online_nodes:
                logging.debug(f"System: Checking for undelivered messages to {len(online_nodes)} online nodes")
                for node in online_nodes:
                    resend_undelivered_messages(node['node_id'])
            else:
                logging.debug("System: No online nodes found for periodic message resend")
        except Exception as e:
            logging.error(f"Error in message resend task: {e}")


async def main():
    load_geofences_and_triggers()

    # Initialize Telegram bot integration if enabled
    telegram_integration = None
    try:
        # Check if Telegram bot integration is enabled by looking for bot token in config
        telegram_bot_token = config.get('telegram', 'telegram_bot_token', fallback='')
        if telegram_bot_token and telegram_bot_token != 'YOUR_TELEGRAM_BOT_TOKEN':
            logger.info("Telegram bot integration enabled, initializing...")

            # Import the integration module
            from modules.meshgram_integration.meshgram import create_meshgram_integration

            # Use interface1 as the primary Meshtastic interface for the integration
            if interface1 is not None:
                telegram_integration = await create_meshgram_integration(interface1)
                logger.info("Telegram bot integration initialized successfully")
            else:
                logger.warning("Telegram bot integration enabled but no primary interface available")
        else:
            logger.debug("Telegram bot integration disabled or not configured")
    except Exception as e:
        logger.error(f"Failed to initialize Telegram bot integration: {e}")
        logger.error("Continuing without Telegram integration")

    meshRxTask = asyncio.create_task(start_rx())
    watchdogTask = asyncio.create_task(watchdog())
    commandPollerTask = asyncio.create_task(command_poller())
    cleanupTask = asyncio.create_task(cleanup_task())
    reloadTask = asyncio.create_task(reload_task())

    # Add Telegram integration task if available
    telegram_task = None
    if telegram_integration is not None:
        telegram_task = asyncio.create_task(telegram_integration.start())

    if file_monitor_enabled:
        fileMonTask: asyncio.Task = asyncio.create_task(handleFileWatcher())
    if radio_detection_enabled:
        hamlibTask = asyncio.create_task(handleSignalWatcher())

    nodeStatusTask = asyncio.create_task(node_status_check_task())
    messageResendTask = asyncio.create_task(message_resend_task())

    # Gather all tasks
    tasks = [meshRxTask, watchdogTask, commandPollerTask, cleanupTask, reloadTask, nodeStatusTask, messageResendTask]

    if telegram_task is not None:
        tasks.append(telegram_task)
    if radio_detection_enabled:
        tasks.append(hamlibTask)
    if file_monitor_enabled:
        tasks.append(fileMonTask)

    await asyncio.gather(*tasks)

    await asyncio.sleep(0.1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        exit_handler()
    except SystemExit:
        pass
# EOF
