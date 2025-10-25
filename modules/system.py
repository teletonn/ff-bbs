# helper functions and init for system related tasks
# K7MHI Kelly Keeton 2024
import logging
logging.basicConfig(level=logging.INFO)
logging.info("Attempting to import modules in system.py")

import meshtastic.serial_interface #pip install meshtastic or use launch.sh for venv
import meshtastic.tcp_interface
import meshtastic.ble_interface
import time
import asyncio
import random
import contextlib # for suppressing output on watchdog
import io # for suppressing output on watchdog
import uuid
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from webui.db_handler import save_message, update_message_delivery_status, get_undelivered_messages, get_queued_messages, update_node_telemetry, get_node_by_id, mark_messages_delivered_to_node, insert_telemetry, delete_message, get_db_connection, get_message_by_id, update_message_status, retry_message, delete_message_by_user, update_node_on_packet

# Import trigger system modules
try:
    from modules.trigger_engine import TriggerEngine, Position
    from modules.trigger_actions import action_executor
    trigger_system_enabled = True
    logging.info("System: Trigger system modules imported successfully")
except ImportError as e:
    trigger_system_enabled = False
    logging.warning(f"System: Trigger system modules not available: {e}")
from modules.log import *

# Import broadcast_map_update for real-time updates
try:
    from webui.main import broadcast_map_update
except ImportError:
    async def broadcast_map_update(update_type, data):
        pass

# Global Variables
trap_list = ("cmd","cmd?") # default trap list
help_message = "Bot CMD?:"
asyncLoop = asyncio.new_event_loop()
games_enabled = False
multiPingList = [{'message_from_id': 0, 'count': 0, 'type': '', 'deviceID': 0, 'channel_number': 0, 'startCount': 0}]
interface_retry_count = 3

# Trigger system global variables
trigger_engine = None

# Ping Configuration
if ping_enabled:
    # ping, pinging, ack, testing, test, pong
    trap_list_ping = ("ping", "пинг", "pinging", "ack", "testing", "test", "pong", "🔔", "cq","cqcq", "cqcqcq")
    trap_list = trap_list + trap_list_ping
    help_message = help_message + "ping"

# Echo Configuration
if enableEcho:
    trap_list_echo = ("echo",)
    trap_list = trap_list + trap_list_echo
    help_message = help_message + ", echo"

# Sitrep Configuration
if sitrep_enabled:
    trap_list_sitrep = ("sitrep", "lheard", "sysinfo")
    trap_list = trap_list + trap_list_sitrep
    help_message = help_message + ", sitrep, sysinfo"

# MOTD Configuration
if motd_enabled:
    trap_list_motd = ("motd",)
    trap_list = trap_list + trap_list_motd
    help_message = help_message + ", motd"

# SMTP Configuration
if enableSMTP:
    from modules.smtp import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + trap_list_smtp
    help_message = help_message + ", email:, sms:"

# Emergency Responder Configuration
if emergency_responder_enabled:
    trap_list_emergency = ("emergency", "911", "112", "999", "police", "fire", "ambulance", "rescue")
    trap_list = trap_list + trap_list_emergency
    
# whoami Configuration
if whoami_enabled:
    trap_list_whoami = ("whoami", "📍", "whois")
    trap_list = trap_list + trap_list_whoami
    help_message = help_message + ", whoami"

# Solar Conditions Configuration
if solar_conditions_enabled:
    from modules.space import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + trap_list_solarconditions # items hfcond, solar, sun, moon
    help_message = help_message + ", sun, hfcond, solar, moon, howtall"
    if n2yoAPIKey != "":
        help_message = help_message + ", satpass"
else:
    hf_band_conditions = False

# Command History Configuration
if enableCmdHistory:
    trap_list = trap_list + ("history",)
    #help_message = help_message + ", history"
    
# Location Configuration
if location_enabled:
    from modules.locationdata import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + trap_list_location
    help_message = help_message + ", whereami, wx, rlist, howfar"
    if enableGBalerts and not enableDEalerts:
        from modules.globalalert import * # from the spudgunman/meshing-around repo
        logger.warning(f"System: GB Alerts not functional at this time need to find a source API")
        #help_message = help_message + ", ukalert, ukwx, ukflood"
    if enableDEalerts and not enableGBalerts:
        from modules.globalalert import * # from the spudgunman/meshing-around repo
        trap_list = trap_list + trap_list_location_de
        #help_message = help_message + ", dealert, dewx, deflood"
    
    # Open-Meteo Configuration for worldwide weather
    if use_meteo_wxApi:
        trap_list = trap_list + ("wxc",)
        help_message = help_message + ", wxc"
        from modules.wx_meteo import * # from the spudgunman/meshing-around repo
    else:
        # NOAA only features
        help_message = help_message + ", wxa, wxalert"

    # USGS riverFlow Configuration
    if riverListDefault != ['']:
        help_message = help_message + ", riverflow"

# NOAA alerts needs location module
if wxAlertBroadcastEnabled or emergencyAlertBrodcastEnabled or volcanoAlertBroadcastEnabled:
    from modules.locationdata import * # from the spudgunman/meshing-around repo
    # limited subset, this should be done better but eh..
    trap_list = trap_list + ("wx", "wxa", "wxalert", "ea", "ealert", "valert")
    help_message = help_message + ", ealert, valert"

# NOAA Coastal Waters Forecasts
if coastalEnabled:
    from modules.locationdata import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + ("mwx","tide",)
    help_message = help_message + ", mwx, tide"
        
# BBS Configuration
if bbs_enabled:
    from modules.bbstools import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + trap_list_bbs # items bbslist, bbspost, bbsread, bbsdelete, bbshelp
    help_message = help_message + ", bbslist, bbshelp"
else:
    bbs_help = False
    bbs_list_messages = False

# Dad Jokes Configuration
if dad_jokes_enabled:
    from modules.games.joke import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + ("joke",)
    help_message = help_message + ", joke"

# Wikipedia Search Configuration
if wikipedia_enabled:
    import wikipedia # pip install wikipedia
    trap_list = trap_list + ("wiki:", "wiki?",)
    help_message = help_message + ", wiki:"

# LLM Configuration
if llm_enabled:
    from modules.llm import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + trap_list_llm # items ask:
    help_message = help_message + ", askai"

# DopeWars Configuration
if dopewars_enabled:
    from modules.games.dopewar import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + ("dopewars",)
    games_enabled = True

# Lemonade Stand Configuration
if lemonade_enabled:
    from modules.games.lemonade import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + ("lemonstand",)
    games_enabled = True

# BlackJack Configuration
if blackjack_enabled:
    from modules.games.blackjack import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + ("blackjack",)
    games_enabled = True

# Video Poker Configuration
if videoPoker_enabled:
    from modules.games.videopoker import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + ("videopoker",)
    games_enabled = True

if mastermind_enabled:
    from modules.games.mmind import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + ("mastermind",)
    games_enabled = True

if golfSim_enabled:
    from modules.games.golfsim import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + ("golfsim",)
    games_enabled = True

if hangman_enabled:
    from modules.games.hangman import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + ("hangman",)
    games_enabled = True

if hamtest_enabled:
    from modules.games.hamtest import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + ("hamtest",)
    games_enabled = True

# Games Configuration
if games_enabled is True:
    help_message = help_message + ", games"
    trap_list = trap_list + ("games",)
    gTnW_enabled = True
    gamesCmdList = "Play via DM🕹️ CMD: "
    if dopewars_enabled:
        gamesCmdList += "dopeWars, "
    if lemonade_enabled:
        gamesCmdList += "lemonStand, "
    if gTnW_enabled:
        trap_list = trap_list + ("globalthermonuclearwar",)
    if blackjack_enabled:
        gamesCmdList += "blackJack, "
    if videoPoker_enabled:
        gamesCmdList += "videoPoker, "
    if mastermind_enabled:
        gamesCmdList += "masterMind, "
    if golfSim_enabled:
        gamesCmdList += "golfSim, "
    if hangman_enabled:
        gamesCmdList += "hangman, "
    if hamtest_enabled:
        gamesCmdList += "hamTest, "
    gamesCmdList = gamesCmdList[:-2] # remove the last comma
else:
    gamesCmdList = ""

# Scheduled Broadcast Configuration
if scheduler_enabled:
    import schedule # pip install schedule

# Sentry Configuration
if sentry_enabled:
    from math import sqrt
    import geopy.distance # pip install geopy

# Store and Forward Configuration
if store_forward_enabled:
    trap_list = trap_list + ("messages",)
    help_message = help_message + ", messages"

# QRZ Configuration
if qrz_hello_enabled:
    from modules.qrz import * # from the spudgunman/meshing-around repo
    #trap_list = trap_list + trap_list_qrz # items qrz, qrz?, qrzcall
    #help_message = help_message + ", qrz"

# CheckList Configuration
if checklist_enabled:
    from modules.checklist import * # from the spudgunman/meshing-around repo
    trap_list = trap_list + trap_list_checklist # items checkin, checkout, checklist, purgein, purgeout
    help_message = help_message + ", checkin, checkout"

# Radio Monitor Configuration
if radio_detection_enabled:
    from modules.radio import * # from the spudgunman/meshing-around repo

# File Monitor Configuration
if file_monitor_enabled or read_news_enabled or bee_enabled:
    from modules.filemon import * # from the spudgunman/meshing-around repo
    if read_news_enabled:
        trap_list = trap_list + trap_list_filemon # items readnews
        help_message = help_message + ", readnews"
    # Bee Configuration uses file monitor module
    if bee_enabled:
        trap_list = trap_list + ("🐝",)

# clean up the help message
help_message = help_message.split(", ")
help_message.sort()
if len(help_message) > 20:
    # split in half for formatting
    help_message = help_message[:len(help_message)//2] + ["\nCMD?"] + help_message[len(help_message)//2:]
help_message = ", ".join(help_message)

# Initialize trigger system if enabled
if trigger_system_enabled:
    try:
        trigger_engine = TriggerEngine()
        logger.info("System: Trigger engine initialized successfully")
    except Exception as e:
        logger.error(f"System: Failed to initialize trigger engine: {e}")
        trigger_engine = None

# BLE dual interface prevention
ble_count = sum(1 for i in range(1, 10) if globals().get(f'interface{i}_type') == 'ble')
if ble_count > 1:
    logger.critical(f"System: Multiple BLE interfaces detected. Only one BLE interface is allowed. Exiting")
    exit()

# Initialize interfaces
logger.debug(f"System: Initializing Interfaces")
interface1 = interface2 = interface3 = interface4 = interface5 = interface6 = interface7 = interface8 = interface9 = None
retry_int1 = retry_int2 = retry_int3 = retry_int4 = retry_int5 = retry_int6 = retry_int7 = retry_int8 = retry_int9 = False
myNodeNum1 = myNodeNum2 = myNodeNum3 = myNodeNum4 = myNodeNum5 = myNodeNum6 = myNodeNum7 = myNodeNum8 = myNodeNum9 = 777
max_retry_count1 = max_retry_count2 = max_retry_count3 = max_retry_count4 = max_retry_count5 = max_retry_count6 = max_retry_count7 = max_retry_count8 = max_retry_count9 = interface_retry_count
for i in range(1, 10):
    interface_type = globals().get(f'interface{i}_type')
    if not interface_type or interface_type == 'none' or globals().get(f'interface{i}_enabled') == False:
        # no valid interface found
        continue
    try:
        if globals().get(f'interface{i}_enabled'):
            if interface_type == 'serial':
                globals()[f'interface{i}'] = meshtastic.serial_interface.SerialInterface(globals().get(f'port{i}'))
            elif interface_type == 'tcp':
                globals()[f'interface{i}'] = meshtastic.tcp_interface.TCPInterface(globals().get(f'hostname{i}'))
            elif interface_type == 'ble':
                globals()[f'interface{i}'] = meshtastic.ble_interface.BLEInterface(globals().get(f'mac{i}'))
            else:
                logger.critical(f"System: Interface Type: {interface_type} not supported. Validate your config against config.template Exiting")
                exit()
    except Exception as e:
        logger.critical(f"System: abort. Initializing Interface{i} {e}")
        exit()

# Get the node number of the devices, check if the devices are connected meshtastic devices
for i in range(1, 10):
    if globals().get(f'interface{i}') and globals().get(f'interface{i}_enabled'):
        try:
            globals()[f'myNodeNum{i}'] = globals()[f'interface{i}'].getMyNodeInfo()['num']
            logger.debug(f"System: Initalized Radio Device{i} Node Number: {globals()[f'myNodeNum{i}']}")
        except Exception as e:
            logger.critical(f"System: critical error initializing interface{i} {e}")
    else:
        globals()[f'myNodeNum{i}'] = 777

#### FUN-ctions ####

def decimal_to_hex(decimal_number):
    return f"!{decimal_number:08x}"

def get_name_from_number(number, type='long', nodeInt=1):
    interface = globals()[f'interface{nodeInt}']
    name = ""
    
    for node in interface.nodes.values():
        if number == node['num']:
            if type == 'long':
                name = node['user']['longName']
                return name
            elif type == 'short':
                name = node['user']['shortName']
                return name
        else:
            name =  str(decimal_to_hex(number))  # If name not found, use the ID as string
    return name


def get_num_from_short_name(short_name, nodeInt=1):
    interface = globals()[f'interface{nodeInt}']
    # Get the node number from the short name, converting all to lowercase for comparison (good practice?)
    logger.debug(f"System: Getting Node Number from Short Name: {short_name} on Device: {nodeInt}")
    for node in interface.nodes.values():
        #logger.debug(f"System: Checking Node: {node['user']['shortName']} against {short_name} for number {node['num']}")
        if short_name == node['user']['shortName']:
            return node['num']
        elif str(short_name.lower()) == node['user']['shortName'].lower():
            return node['num']
        else:
            for int in range(1, 10):
                if globals().get(f'interface{int}_enabled') and int != nodeInt:
                    other_interface = globals().get(f'interface{int}')
                    for node in other_interface.nodes.values():
                        if short_name == node['user']['shortName']:
                            return node['num']
                        elif str(short_name.lower()) == node['user']['shortName'].lower():
                            return node['num']
    return 0
    
def get_node_list(nodeInt=1):
    interface = globals()[f'interface{nodeInt}']
    # Get a list of nodes on the device
    node_list = ""
    node_list1 = []
    node_list2 = []
    short_node_list = []
    last_heard = 0
    if interface.nodes:
        for node in interface.nodes.values():
            # ignore own
            if all(node['num'] != globals().get(f'myNodeNum{i}') for i in range(1, 10)):
                node_name = get_name_from_number(node['num'], 'short', nodeInt)
                snr = node.get('snr', 0)

                # issue where lastHeard is not always present
                last_heard = node.get('lastHeard', 0)
                
                # make a list of nodes with last heard time and SNR
                item = (node_name, last_heard, snr)
                node_list1.append(item)
    else:
        logger.warning(f"System: No nodes found")
        return ERROR_FETCHING_DATA
    
    try:
        #print (f"Node List: {node_list1[:5]}\n")
        node_list1.sort(key=lambda x: x[1] if x[1] is not None else 0, reverse=True)
        #print (f"Node List: {node_list1[:5]}\n")
        if multiple_interface:
            logger.debug(f"System: FIX ME line 327 Multiple Interface Node List")
            node_list2.sort(key=lambda x: x[1] if x[1] is not None else 0, reverse=True)
    except Exception as e:
        logger.error(f"System: Error sorting node list: {e}")
        logger.debug(f"Node List1: {node_list1[:5]}\n")
        if multiple_interface:
            logger.debug(f"FIX ME MULTI INTERFACE Node List2: {node_list2[:5]}\n")
        node_list = ERROR_FETCHING_DATA

    try:
        # make a nice list for the user
        for x in node_list1[:SITREP_NODE_COUNT]:
            short_node_list.append(f"{x[0]} SNR:{x[2]}")
        for x in node_list2[:SITREP_NODE_COUNT]:
            short_node_list.append(f"{x[0]} SNR:{x[2]}")

        for x in short_node_list:
            if x != "" or x != '\n':
                node_list += x + "\n"
    except Exception as e:
        logger.error(f"System: Error creating node list: {e}")
        node_list = ERROR_FETCHING_DATA
    
    return node_list

def get_node_location(nodeID, nodeInt=1, channel=0):
    interface = globals()[f'interface{nodeInt}']
    # Get the location of a node by its number from nodeDB on device
    # if no location data, return default location
    latitude = latitudeValue
    longitude = longitudeValue
    position = [latitudeValue,longitudeValue]
    if interface.nodes:
        for node in interface.nodes.values():
            if nodeID == node['num']:
                if 'position' in node and node['position'] is not {}:
                    try:
                        latitude = node['position']['latitude']
                        longitude = node['position']['longitude']
                        logger.debug(f"System: location data for {nodeID} is {latitude},{longitude}")
                        position = [latitude,longitude]
                    except Exception as e:
                        logger.debug(f"System: No location data for {nodeID} use default location")
                    return position
                else:
                    logger.debug(f"System: No location data for {nodeID} using default location")
                    # request location data
                    # try:
                    #     logger.debug(f"System: Requesting location data for {number}")
                    #     interface.sendPosition(destinationId=number, wantResponse=False, channelIndex=channel)
                    # except Exception as e:
                    #     logger.error(f"System: Error requesting location data for {number}. Error: {e}")
                    return position
        else:
            logger.warning(f"System: Location for NodeID {nodeID} not found in nodeDb")
            return position


def is_node_online(node_id, nodeInt=1, use_ping=False):
    """Check if a node is online based on last heard time (within 2 hours) and optionally ping."""
    interface = globals()[f'interface{nodeInt}']

    if interface.nodes:
        for node in interface.nodes.values():
            if node['num'] == node_id:
                last_heard = node.get('lastHeard', 0)
                # Check if last heard within 2 hours (7200 seconds)
                if last_heard and (time.time() - last_heard) <= 1800:
                    return True
                elif use_ping:
                    # Attempt ping if available and last heard check failed
                    try:
                        logger.debug(f"System: Attempting ping for node {node_id} on interface {nodeInt}")
                        # Meshtastic interface has ping method
                        ping_result = interface.ping(node_id, wantAck=True)
                        if ping_result:
                            logger.debug(f"System: Ping successful for node {node_id}")
                            return True
                        else:
                            logger.debug(f"System: Ping failed for node {node_id}")
                    except Exception as e:
                        logger.debug(f"System: Ping not available or failed for node {node_id}: {e}")
                break  # Found the node, no need to continue

    return False

def get_closest_nodes(nodeInt=1,returnCount=3):
    interface = globals()[f'interface{nodeInt}']
    node_list = []

    if interface.nodes:
        for node in interface.nodes.values():
            if 'position' in node:
                try:
                    nodeID = node['num']
                    latitude = node['position']['latitude']
                    longitude = node['position']['longitude']

                    #lastheard time in unix time
                    lastheard = node.get('lastHeard', 0)
                    #if last heard is over 24 hours ago, ignore the node
                    if lastheard < (time.time() - 86400):
                        continue

                    # Calculate distance to node from config.ini location
                    distance = round(geopy.distance.geodesic((latitudeValue, longitudeValue), (latitude, longitude)).m, 2)

                    if (distance < sentry_radius):
                        if (nodeID not in [globals().get(f'myNodeNum{i}') for i in range(1, 10)]) and str(nodeID) not in sentryIgnoreList:
                            node_list.append({'id': nodeID, 'latitude': latitude, 'longitude': longitude, 'distance': distance})

                except Exception as e:
                    pass
            # else:
            #     # request location data
            #     try:
            #         logger.debug(f"System: Requesting location data for {node['id']}")
            #         interface.sendPosition(destinationId=node['id'], wantResponse=False, channelIndex=publicChannel)
            #     except Exception as e:
            #         logger.error(f"System: Error requesting location data for {node['id']}. Error: {e}")

        # sort by distance closest
        #node_list.sort(key=lambda x: (x['latitude']-latitudeValue)**2 + (x['longitude']-longitudeValue)**2)
        node_list.sort(key=lambda x: x['distance'])
        # return the first 3 closest nodes by default
        return node_list[:returnCount]
    else:
        logger.warning(f"System: No nodes found in closest_nodes on interface {nodeInt}")
        return ERROR_FETCHING_DATA
    
def handleFavoritNode(nodeInt=1, nodeID=0, aor=False):
    #aor is add or remove if True add, if False remove
    interface = globals()[f'interface{nodeInt}']
    myNodeNumber = globals().get(f'myNodeNum{nodeInt}')
    if aor:
        interface.getNode(myNodeNumber).setFavorite(nodeID)
        logger.info(f"System: Added {nodeID} to favorites for device {nodeInt}")
    else:
        interface.getNode(myNodeNumber).removeFavorite(nodeID)
        logger.info(f"System: Removed {nodeID} from favorites for device {nodeInt}")
    
def getFavoritNodes(nodeInt=1):
    interface = globals()[f'interface{nodeInt}']
    myNodeNumber = globals().get(f'myNodeNum{nodeInt}')
    favList = []
    for node in interface.getNode(myNodeNumber).favorites:
        favList.append(node)
    return favList

def handleSentinelIgnore(nodeInt=1, nodeID=0, aor=False):
    #aor is add or remove if True add, if False remove
    if aor:
        sentryIgnoreList.append(str(nodeID))
        logger.info(f"System: Added {nodeID} to sentry ignore list")
    else:
        sentryIgnoreList.remove(str(nodeID))
        logger.info(f"System: Removed {nodeID} from sentry ignore list")

def messageChunker(message):
    if len(message) <= MESSAGE_CHUNK_SIZE:
        return [message]

    message_list = []
    while len(message) > 0:
        if len(message) <= MESSAGE_CHUNK_SIZE:
            message_list.append(message)
            break

        # Find the last space within the chunk size
        split_pos = message.rfind(' ', 0, MESSAGE_CHUNK_SIZE)
        
        if split_pos == -1:
            # No space found, split at the chunk size
            split_pos = MESSAGE_CHUNK_SIZE
        
        chunk = message[:split_pos]
        message_list.append(chunk)
        message = message[split_pos:].lstrip()

    logger.debug(f"System: Splitting #chunks: {len(message_list)}, Total length: {sum(len(c) for c in message_list)}")
    return message_list
        
def send_message(message, ch, nodeid=0, nodeInt=1, bypassChuncking=False, resend_existing=False, existing_message_id=None):
    # Send a message to a channel or DM with retry logic and offline saving
    interface = globals()[f'interface{nodeInt}']
    # Check if the message is empty
    if message == "" or message == None or len(message) == 0:
        return False

    # Prevent sending to own node
    if nodeid != 0 and nodeid in [globals().get(f'myNodeNum{i}') for i in range(1, 10) if globals().get(f'myNodeNum{i}')]:
        logger.warning(f"System: Attempted to send message to own node {nodeid}")
        return False

    # Determine start_attempt and message_id
    if resend_existing and existing_message_id:
        message_id = existing_message_id
        msg = get_message_by_id(message_id)
        if msg:
            start_attempt = msg['attempt_count']
        else:
            logger.error(f"System: Message {message_id} not found for resend")
            return False
    else:
        start_attempt = 0
        message_id = str(uuid.uuid4())

        # Check online status and save message
        if nodeid != 0:
            if not is_node_online(nodeid, nodeInt):
                # Offline, queue the message
                from_node_id = str(globals().get(f'myNodeNum{nodeInt}', 777))
                to_node_id = str(nodeid)
                is_dm = True
                timestamp = time.time()
                try:
                    save_message(from_node_id, to_node_id, str(ch), message, timestamp, is_dm, status='queued', attempt_count=0, message_id=message_id)
                    logger.info(f"System: Message queued for offline recipient {nodeid}")
                except Exception as e:
                    logger.error(f"System: Failed to queue message for offline recipient {nodeid}: {e}")
                return False
            else:
                # Online, save as sent
                from_node_id = str(globals().get(f'myNodeNum{nodeInt}', 777))
                to_node_id = str(nodeid)
                is_dm = True
                timestamp = time.time()
                try:
                    save_message(from_node_id, to_node_id, str(ch), message, timestamp, is_dm, status='sent', attempt_count=1, message_id=message_id)
                except Exception as e:
                    logger.error(f"System: Failed to save message to database: {e}")
                    return False
        else:
            # Channel message
            from_node_id = str(globals().get(f'myNodeNum{nodeInt}', 777))
            to_node_id = None
            is_dm = False
            timestamp = time.time()
            try:
                save_message(from_node_id, to_node_id, str(ch), message, timestamp, is_dm, status='sent', attempt_count=1, message_id=message_id)
            except Exception as e:
                logger.error(f"System: Failed to save message to database: {e}")
                return False

    # Attempt delivery with refined retry logic: 3 attempts then defer, total 9 then undelivered
    max_direct_attempts = 3
    max_total_attempts = 9

    for attempt in range(start_attempt, max_total_attempts):
        try:
            current_attempt_count = attempt + 1
            update_message_delivery_status(message_id, attempt_count=current_attempt_count, last_attempt_time=time.time())

            if not bypassChuncking:
                # Split the message into chunks if it exceeds the MESSAGE_CHUNK_SIZE
                message_list = messageChunker(message)
            else:
                message_list = [message]

            # Send the message to the channel or DM
            total_length = sum(len(chunk) for chunk in message_list)
            num_chunks = len(message_list)
            for m in message_list:
                chunkOf = f"{message_list.index(m)+1}/{num_chunks}"
                if nodeid == 0:
                    # Send to channel - always use ACK for delivery confirmation
                    logger.info(f"Device:{nodeInt} Channel:{ch} Attempt:{current_attempt_count} " + CustomFormatter.red + f"req.ACK " + f"Chunker{chunkOf} SendingChannel: " + CustomFormatter.white + m.replace('\n', ' '))
                    interface.sendText(text=m, channelIndex=ch, wantAck=True)
                else:
                    # Send to DM - always use ACK for delivery confirmation
                    logger.info(f"Device:{nodeInt} Attempt:{current_attempt_count} " + CustomFormatter.red + f"req.ACK " + f"Chunker{chunkOf} Sending DM: " + CustomFormatter.white + m.replace('\n', ' ') + CustomFormatter.purple +\
                                  " To: " + CustomFormatter.white + f"{get_name_from_number(nodeid, 'long', nodeInt)}")
                    interface.sendText(text=m, channelIndex=ch, destinationId=nodeid, wantAck=True)

                # Throttle the message sending to prevent spamming the device
                if (message_list.index(m)+1) % 4 == 0:
                    time.sleep(responseDelay + 1)
                    if (message_list.index(m)+1) % 5 == 0:
                        logger.warning(f"System: throttling rate Interface{nodeInt} on {chunkOf}")

                # wait an amount of time between sending each split message
                time.sleep(splitDelay)

            # If we reach here without exception, assume success
            update_message_delivery_status(message_id, delivered=True, status='delivered')
            logger.info(f"System: Message {message_id} delivered successfully on attempt {current_attempt_count}")
            return True

        except Exception as e:
            error_msg = str(e)
            # Check for specific connection errors
            if "Broken pipe" in error_msg or "Errno 32" in error_msg:
                logger.error(f"System: BrokenPipeError detected on interface{nodeInt} during message {message_id} delivery attempt {current_attempt_count}: {error_msg}")
                # Trigger reconnection for this interface
                globals()[f'retry_int{nodeInt}'] = True
                logger.warning(f"System: Set retry flag for interface{nodeInt} due to BrokenPipeError")
            elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                logger.warning(f"System: Timeout detected on interface{nodeInt} during message {message_id} delivery attempt {current_attempt_count}: {error_msg}")
            else:
                logger.warning(f"System: Delivery attempt {current_attempt_count} failed for message {message_id}: {error_msg}")

            # After 3 direct attempts, defer the message
            if current_attempt_count >= start_attempt + max_direct_attempts and current_attempt_count < max_total_attempts:
                # Defer: set status to 'queued', increment defer_count, set next_retry_time
                defer_count = (current_attempt_count // max_direct_attempts)
                next_retry_time = time.time() + (60 * defer_count)  # Exponential defer: 1min, 2min, 3min, etc.
                update_message_delivery_status(message_id, status='queued', defer_count=defer_count,
                                            next_retry_time=next_retry_time, error_message=error_msg)
                logger.info(f"System: Message {message_id} deferred after {current_attempt_count} attempts, next retry at {time.ctime(next_retry_time)}")
                return False
            elif current_attempt_count >= max_total_attempts:
                # All attempts exhausted, mark as undelivered
                update_message_delivery_status(message_id, status='undelivered', error_message=error_msg)
                logger.error(f"System: Message {message_id} undelivered after {max_total_attempts} total attempts")
                return False
            else:
                # Still in direct retry phase, use exponential backoff
                if attempt < max_total_attempts - 1:
                    backoff_time = 2 ** attempt  # 1s, 2s, 4s
                    logger.info(f"System: Retrying message {message_id} in {backoff_time} seconds")
                    time.sleep(backoff_time)

    # Should not reach here, but just in case
    update_message_delivery_status(message_id, status='undelivered', error_message="Max attempts reached")
    logger.error(f"System: Message {message_id} undelivered after reaching max attempts")
    return False

def resend_undelivered_messages(node_id, nodeInt=1):
    """Resend undelivered and queued messages to a specific node."""
    try:
        # Skip resending to own nodes
        bot_node_ids = [globals().get(f'myNodeNum{i}') for i in range(1, 10) if globals().get(f'myNodeNum{i}') is not None]
        if int(node_id) in bot_node_ids:
            logger.debug(f"System: Skipping resend to own node {node_id}")
            return

        # Check if recipient node is online using improved detection (last heard within 2 hours)
        if not is_node_online(int(node_id), nodeInt):
            logger.debug(f"System: Node {node_id} is offline (last heard > 2 hours ago), skipping resend")
            return

        # Get 'sent' messages older than 30s with attempt_count < 3
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE status = 'sent' AND delivered = 0 AND timestamp < ? AND attempt_count < 3 AND to_node_id = ?", (time.time() - 30, str(node_id)))
        sent_messages = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]

        # Get 'queued' messages with attempt_count < 9 and next_retry_time <= current time
        cursor.execute("SELECT * FROM messages WHERE status = 'queued' AND attempt_count < 9 AND to_node_id = ? AND (next_retry_time IS NULL OR next_retry_time <= ?)", (str(node_id), time.time()))
        queued_messages = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        conn.close()

        all_messages = sent_messages + queued_messages

        if not all_messages:
            logger.debug(f"System: No undelivered or queued messages for node {node_id}")
            return

        logger.info(f"System: Resending {len(all_messages)} messages (sent: {len(sent_messages)}, queued: {len(queued_messages)}) to node {node_id}")

        for msg in all_messages:
            if msg['status'] == 'sent':
                # Resend 'sent' message
                truncated_text = msg['text'][:50] + "..." if len(msg['text']) > 50 else msg['text']
                logger.debug(f"System: Attempting to resend sent message {msg['message_id']} (attempt {msg['attempt_count'] + 1}/3) to node {node_id}: channel={msg['channel']}, text='{truncated_text}'")

                ch = int(msg['channel']) if msg['channel'].isdigit() else 0
                success = send_message(msg['text'], ch, int(msg['to_node_id']), nodeInt, bypassChuncking=True, resend_existing=True, existing_message_id=msg['message_id'])
                if success:
                    update_message_delivery_status(msg['message_id'], delivered=True)
                    logger.info(f"System: Successfully resent sent message {msg['message_id']} to node {node_id}")
                else:
                    # Check if attempt_count >= 3
                    updated_msg = get_message_by_id(msg['message_id'])
                    if updated_msg and updated_msg['attempt_count'] >= 3:
                        update_message_delivery_status(msg['message_id'], status='queued')
                        logger.info(f"System: Changed sent message {msg['message_id']} to queued after 3 attempts")

            elif msg['status'] == 'queued':
                # Resend 'queued' message if online
                if is_node_online(int(msg['to_node_id']), nodeInt):
                    truncated_text = msg['text'][:50] + "..." if len(msg['text']) > 50 else msg['text']
                    logger.debug(f"System: Attempting to resend queued message {msg['message_id']} (attempt {msg['attempt_count'] + 1}/9) to node {node_id}: channel={msg['channel']}, text='{truncated_text}'")

                    ch = int(msg['channel']) if msg['channel'].isdigit() else 0
                    success = send_message(msg['text'], ch, int(msg['to_node_id']), nodeInt, bypassChuncking=True, resend_existing=True, existing_message_id=msg['message_id'])
                    if success:
                        delete_message(msg['message_id'])
                        logger.info(f"System: Successfully resent queued message {msg['message_id']} to node {node_id}, deleted original")
                    else:
                        # Increment attempt_count
                        update_message_delivery_status(msg['message_id'], attempt_count=msg['attempt_count'] + 1)
                        logger.warning(f"System: Failed to resend queued message {msg['message_id']} to node {node_id}, incremented attempt_count to {msg['attempt_count'] + 1}")
                else:
                    logger.debug(f"System: Node {node_id} still offline, skipping queued message {msg['message_id']}")

    except Exception as e:
        logger.error(f"System: Error resending messages to node {node_id}: {e}")

def get_wikipedia_summary(search_term):
    wikipedia_search = wikipedia.search(search_term, results=3)
    wikipedia_suggest = wikipedia.suggest(search_term)
    #wikipedia_aroundme = wikipedia.geosearch(location[0], location[1], results=3)
    #logger.debug(f"System: Wikipedia Nearby:{wikipedia_aroundme}")
    
    if len(wikipedia_search) == 0:
        logger.warning(f"System: No Wikipedia Results for:{search_term}")
        return ERROR_FETCHING_DATA
    
    try:
        logger.debug(f"System: Searching Wikipedia for:{search_term}, First Result:{wikipedia_search[0]}, Suggest Word:{wikipedia_suggest}")
        summary = wikipedia.summary(search_term, sentences=wiki_return_limit, auto_suggest=False, redirect=True)
    except wikipedia.DisambiguationError as e:
        logger.warning(f"System: Disambiguation Error for:{search_term} trying {wikipedia_search[0]}")
        summary = wikipedia.summary(wikipedia_search[0], sentences=wiki_return_limit, auto_suggest=True, redirect=True)
    except wikipedia.PageError as e:
        logger.warning(f"System: Wikipedia Page Error for:{search_term} {e} trying {wikipedia_search[0]}")
        summary = wikipedia.summary(wikipedia_search[0], sentences=wiki_return_limit, auto_suggest=True, redirect=True)
    except Exception as e:
        logger.warning(f"System: Error with Wikipedia for:{search_term} {e}")
        return ERROR_FETCHING_DATA
    
    return summary

def messageTrap(msg):
    # Check if the message contains a trap word, this is the first filter for listning to messages
    # after this the message is passed to the command_handler in the bot.py which is switch case filter for applying word to function

    # Split Message on assumed words spaces m for m = msg.split(" ")
    # t in trap_list, built by the config and system.py not the user
    message_list=msg.split(" ")
    
    if cmdBang:
        # check for ! at the start of the message to force a command
        if not message_list[0].startswith('!'):
            return False
        else:
            message_list[0] = message_list[0][1:]

    for m in message_list:
        for t in trap_list:
            if not explicitCmd:
                # if word in message is in the trap list, return True
                if t.lower() == m.lower():
                    return True
            else:
                # if the index 0 of the message is a word in the trap list, return True
                if t.lower() == m.lower() and message_list.index(m) == 0:
                    return True
    # if no trap words found, run a search for near misses like ping? or cmd?
    for m in message_list:
        for t in range(len(trap_list)):
            if m.endswith('?') and m[:-1].lower() == trap_list[t]:
                return True
    return False

def handleMultiPing(nodeID=0, deviceID=1):
    global multiPingList
    if len(multiPingList) > 1:
        mPlCpy = multiPingList.copy()
        for i in range(len(mPlCpy)):
            message_id_from = mPlCpy[i]['message_from_id']
            count = mPlCpy[i]['count']
            type = mPlCpy[i]['type']
            deviceID = mPlCpy[i]['deviceID']
            channel_number = mPlCpy[i]['channel_number']
            start_count = mPlCpy[i]['startCount']

            if count > 1:
                count -= 1
                # update count in the list
                for i in range(len(multiPingList)):
                    if multiPingList[i]['message_from_id'] == message_id_from:
                        multiPingList[i]['count'] = count

                # handle bufferTest
                if type == '🎙TEST':
                    buffer = ''.join(random.choice(['0', '1']) for i in range(maxBuffer))
                    # divide buffer by start_count and get resolution
                    resolution = maxBuffer // start_count
                    slice = resolution * count
                    if slice > maxBuffer:
                        slice = maxBuffer
                    # set the type as a portion of the buffer
                    type = buffer[slice - resolution:]
                    # if exceed the maxBuffer, remove the excess
                    count = len(type + "🔂    ")
                    if count > maxBuffer:
                        type = type[:maxBuffer - count]
                    # final length count of the message for display
                    count = len(type + "🔂    ")
                    if count < 99:
                        count -= 1

                # send the DM
                send_message(f"🔂{count} {type}", channel_number, message_id_from, deviceID, bypassChuncking=True)
                time.sleep(responseDelay + 1)
                if count < 2:
                    # remove the item from the list
                    for j in range(len(multiPingList)):
                        if multiPingList[j]['message_from_id'] == message_id_from:
                            multiPingList.pop(j)
                            break

priorVolcanoAlert = ""
priorEmergencyAlert = ""
priorWxAlert = ""
def handleAlertBroadcast(deviceID=1):
    global priorVolcanoAlert, priorEmergencyAlert, priorWxAlert
    alertUk = NO_ALERTS
    alertDe = NO_ALERTS
    alertFema = NO_ALERTS
    wxAlert = NO_ALERTS
    volcanoAlert = NO_ALERTS
    alertWx = False
    # only allow API call every 20 minutes
    # the watchdog will call this function 3 times, seeing possible throttling on the API
    clock = datetime.now()
    if clock.minute % 20 != 0:
        return False
    if clock.second > 17:
        return False
    
    # check for alerts
    if wxAlertBroadcastEnabled:
        alertWx = alertBrodcastNOAA()

    if emergencyAlertBrodcastEnabled:
        if enableDEalerts:
            alertDe = get_nina_alerts()
        if enableGBalerts:
            alertUk = get_govUK_alerts()
        else:
            # default USA alerts
            alertFema = getIpawsAlert(latitudeValue,longitudeValue, shortAlerts=True)

    # format alert
    if alertWx:
        wxAlert = f"🚨 {alertWx[1]} EAS-WX ALERT: {alertWx[0]}"
    else:
        wxAlert = False

    femaAlert = alertFema
    ukAlert = alertUk
    deAlert = alertDe

    if emergencyAlertBrodcastEnabled:
        if NO_ALERTS not in femaAlert and ERROR_FETCHING_DATA not in femaAlert:
            if femaAlert != priorEmergencyAlert:
                priorEmergencyAlert = femaAlert
            else:
                return False
            if isinstance(emergencyAlertBroadcastCh, list):
                for channel in emergencyAlertBroadcastCh:
                    send_message(femaAlert, int(channel), 0, deviceID)
            else:
                send_message(femaAlert, emergencyAlertBroadcastCh, 0, deviceID)
            return True
        if NO_ALERTS not in ukAlert:
            if ukAlert != priorEmergencyAlert:
                priorEmergencyAlert = ukAlert
            else:
                return False
            if isinstance(emergencyAlertBroadcastCh, list):
                for channel in emergencyAlertBroadcastCh:
                    send_message(ukAlert, int(channel), 0, deviceID)
            else:
                send_message(ukAlert, emergencyAlertBroadcastCh, 0, deviceID)
            return True

        if NO_ALERTS not in alertDe:
            if deAlert != priorEmergencyAlert:
                priorEmergencyAlert = deAlert
            else:
                return False
            if isinstance(emergencyAlertBroadcastCh, list):
                for channel in emergencyAlertBroadcastCh:
                    send_message(deAlert, int(channel), 0, deviceID)
            else:
                send_message(deAlert, emergencyAlertBroadcastCh, 0, deviceID)
            return True
        
    # pause for traffic
    time.sleep(5)

    if wxAlertBroadcastEnabled:
        if wxAlert:
            if wxAlert != priorWxAlert:
                priorWxAlert = wxAlert
            else:
                return False
            if isinstance(wxAlertBroadcastChannel, list):
                for channel in wxAlertBroadcastChannel:
                    send_message(wxAlert, int(channel), 0, deviceID)
            else:
                send_message(wxAlert, wxAlertBroadcastChannel, 0, deviceID)
            return True
    
    # pause for traffic
    time.sleep(5)

    if volcanoAlertBroadcastEnabled:
        volcanoAlert = get_volcano_usgs(latitudeValue, longitudeValue)
        if volcanoAlert and NO_ALERTS not in volcanoAlert and ERROR_FETCHING_DATA not in volcanoAlert:
            # check if the alert is different from the last one
            if volcanoAlert != priorVolcanoAlert:
                priorVolcanoAlert = volcanoAlert
                if isinstance(volcanoAlertBroadcastChannel, list):
                    for channel in volcanoAlertBroadcastChannel:
                        send_message(volcanoAlert, int(channel), 0, deviceID)
                else:
                    send_message(volcanoAlert, volcanoAlertBroadcastChannel, 0, deviceID)
                return True

def onDisconnect(interface):
    # Handle disconnection of the interface
    # Identify which interface disconnected
    interface_id = None
    for i in range(1, 10):
        if globals().get(f'interface{i}') is interface:
            interface_id = i
            break
    logger.warning(f"System: Abrupt Disconnection of Interface{interface_id if interface_id else 'unknown'} detected - triggering immediate reconnection check")
    interface.close()
    # Set retry flag to initiate reconnection
    if interface_id:
        globals()[f'retry_int{interface_id}'] = True
        logger.info(f"System: Set retry flag for Interface{interface_id} due to disconnect event")

# Telemetry Functions
telemetryData = {}
def initialize_telemetryData():
    telemetryData[0] = {f'interface{i}': 0 for i in range(1, 10)}
    telemetryData[0].update({f'lastAlert{i}': '' for i in range(1, 10)})
    for i in range(1, 10):
        telemetryData[i] = {'numPacketsTx': 0, 'numPacketsRx': 0, 'numOnlineNodes': 0, 'numPacketsTxErr': 0, 'numPacketsRxErr': 0, 'numTotalNodes': 0}

# indented to be called from the main loop
initialize_telemetryData()

def getNodeFirmware(nodeID=0, nodeInt=1):
    interface = globals()[f'interface{nodeInt}']
    # get the firmware version of the node
    # this is a workaround because .localNode.getMetadata spits out a lot of debug info which cant be suppressed
    # Create a StringIO object to capture the 
    output_capture = io.StringIO()
    with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(output_capture):
        interface.localNode.getMetadata()
    console_output = output_capture.getvalue()
    if "firmware_version" in console_output:
        fwVer = console_output.split("firmware_version: ")[1].split("\n")[0]
        return fwVer
    return -1

def compileFavoriteList():
    # build a list of favorite nodes to add to the device
    fav_list = []
    if (bbs_admin_list != [0] or favoriteNodeList != ['']) or bbs_link_whitelist != [0]:
        logger.debug(f"System: Collecting Favorite Nodes to add to device(s)")
         # loop through each interface and add the favorite nodes
        for i in range(1, 10):
            if globals().get(f'interface{i}') and globals().get(f'interface{i}_enabled'):
                for fav in bbs_admin_list + favoriteNodeList + bbs_link_whitelist:
                    if fav != 0 and fav != '' and fav is not None:
                        object = {'nodeID': fav, 'deviceID': i}
                        # check object not already in the list
                        if object not in fav_list:
                            fav_list.append(object)
                            logger.debug(f"System: Adding Favorite Node {fav} to Device {i}")
    return fav_list

def displayNodeTelemetry(nodeID=0, rxNode=0, userRequested=False):
    interface = globals()[f'interface{rxNode}']
    myNodeNum = globals().get(f'myNodeNum{rxNode}')
    global telemetryData

    # throttle the telemetry requests to prevent spamming the device
    if 1 <= rxNode <= 9:
        if time.time() - telemetryData[0][f'interface{rxNode}'] < 600 and not userRequested:
            return -1
        telemetryData[0][f'interface{rxNode}'] = time.time()

    # some telemetry data is not available in python-meshtastic?
    # bring in values from the last telemetry dump for the node
    numPacketsTx = telemetryData[rxNode]['numPacketsTx']
    numPacketsRx = telemetryData[rxNode]['numPacketsRx']
    numPacketsTxErr = telemetryData[rxNode]['numPacketsTxErr']
    numPacketsRxErr = telemetryData[rxNode]['numPacketsRxErr']
    numTotalNodes = telemetryData[rxNode]['numTotalNodes']
    totalOnlineNodes = telemetryData[rxNode]['numOnlineNodes']

    # get the telemetry data for a node
    chutil = round(interface.nodes.get(decimal_to_hex(myNodeNum), {}).get("deviceMetrics", {}).get("channelUtilization", 0), 1)
    airUtilTx = round(interface.nodes.get(decimal_to_hex(myNodeNum), {}).get("deviceMetrics", {}).get("airUtilTx", 0), 1)
    uptimeSeconds = interface.nodes.get(decimal_to_hex(myNodeNum), {}).get("deviceMetrics", {}).get("uptimeSeconds", 0)
    batteryLevel = interface.nodes.get(decimal_to_hex(myNodeNum), {}).get("deviceMetrics", {}).get("batteryLevel", 0)
    voltage = interface.nodes.get(decimal_to_hex(myNodeNum), {}).get("deviceMetrics", {}).get("voltage", 0)
    #numPacketsRx = interface.nodes.get(decimal_to_hex(myNodeNum), {}).get("localStats", {}).get("numPacketsRx", 0)
    #numPacketsTx = interface.nodes.get(decimal_to_hex(myNodeNum), {}).get("localStats", {}).get("numPacketsTx", 0)
    numTotalNodes = len(interface.nodes) 
    
    dataResponse = f"Telemetry:{rxNode}"

    # packet info telemetry
    dataResponse += f" numPacketsRx:{numPacketsRx} numPacketsRxErr:{numPacketsRxErr} numPacketsTx:{numPacketsTx} numPacketsTxErr:{numPacketsTxErr}"

    # Channel utilization and airUtilTx
    dataResponse += " ChUtil%:" + str(round(chutil, 2)) + " AirTx%:" + str(round(airUtilTx, 2))

    if chutil > 40:
        logger.warning(f"System: High Channel Utilization {chutil}% on Device: {rxNode}")

    if airUtilTx > 25:
        logger.warning(f"System: High Air Utilization {airUtilTx}% on Device: {rxNode}")

    # Number of nodes
    dataResponse += " totalNodes:" + str(numTotalNodes) + " Online:" + str(totalOnlineNodes)

    # Uptime
    uptimeSeconds = getPrettyTime(uptimeSeconds)
    dataResponse += " Uptime:" + str(uptimeSeconds)

    # add battery info to the response
    emji = "🔌" if batteryLevel == 101 else "🪫" if batteryLevel < 10 else "🔋"
    dataResponse += f" Volt:{round(voltage, 1)}"

    if batteryLevel < 25:
        logger.warning(f"System: Low Battery Level: {batteryLevel}{emji} on Device: {rxNode}")
        send_message(f"Low Battery Level: {batteryLevel}{emji} on Device: {rxNode}", secure_channel, 0, secure_interface)
    elif batteryLevel < 10:
        logger.critical(f"System: Critical Battery Level: {batteryLevel}{emji} on Device: {rxNode}")
    return dataResponse

positionMetadata = {}
def consumeMetadata(packet, rxNode=0):
    try:
        # keep records of recent telemetry data
        hop_count = 0
        packet_type = ''
        if packet.get('decoded'):
            packet_type = packet['decoded']['portnum']
            nodeID = packet['from']

        # TELEMETRY packets
        if packet_type == 'TELEMETRY_APP':
            if debugMetadata: print(f"DEBUG TELEMETRY_APP: {packet}\n\n")
            # get the telemetry data
            telemetry_packet = packet['decoded']['telemetry']
            hop_count = 0
            if telemetry_packet.get('deviceMetrics'):
                deviceMetrics = telemetry_packet['deviceMetrics']
            if telemetry_packet.get('localStats'):
                localStats = telemetry_packet['localStats']
                # Check if 'numPacketsTx' and 'numPacketsRx' exist and are not zero
                if localStats.get('numPacketsTx') is not None and localStats.get('numPacketsRx') is not None and localStats['numPacketsTx'] != 0:
                    # Assign the values to the telemetry dictionary
                    keys = [
                        'numPacketsTx', 'numPacketsRx', 'numOnlineNodes',
                        'numOfflineNodes', 'numPacketsTxErr', 'numPacketsRxErr', 'numTotalNodes']

                    for key in keys:
                        if localStats.get(key) is not None:
                            telemetryData[rxNode][key] = localStats.get(key)

                    # Update database with telemetry timestamp and online status
                    try:
                        update_node_telemetry(nodeID, {'last_telemetry': time.time()})
                        # Update node with packet data
                        packet_data = {'snr': packet.get('rxSnr'), 'rssi': packet.get('rxRssi'), 'hop_count': hop_count, 'last_telemetry': time.time()}
                        update_node_on_packet(nodeID, packet_data)
                        logger.debug(f"System: Updated telemetry timestamp for node {nodeID}")
                    except Exception as e:
                        logger.error(f"System: Failed to update telemetry timestamp for node {nodeID}: {e}")

                    # Node is online, try to resend undelivered messages (skip for bot's own nodes)
                    if nodeID not in [globals().get(f'myNodeNum{i}') for i in range(1, 10) if globals().get(f'myNodeNum{i}') is not None]:
                        resend_undelivered_messages(nodeID, rxNode)
        
        # POSITION_APP packets
        if packet_type == 'POSITION_APP':
            if debugMetadata: print(f"DEBUG POSITION_APP: {packet}\n\n")
            # get the position data
            keys = ['altitude', 'groundSpeed', 'precisionBits']
            position_data = packet['decoded']['position']
            try:
                if nodeID not in positionMetadata:
                    positionMetadata[nodeID] = {}

                for key in keys:
                    positionMetadata[nodeID][key] = position_data.get(key, 0)

                # Update database with telemetry timestamp for position packets
                try:
                    update_node_telemetry(nodeID, {'last_telemetry': time.time()})
                    # Update node with position packet data
                    packet_data = {
                        'latitude': position_data.get('latitude'),
                        'longitude': position_data.get('longitude'),
                        'altitude': position_data.get('altitude'),
                        'ground_speed': position_data.get('groundSpeed'),
                        'last_telemetry': time.time()
                    }
                    update_node_on_packet(nodeID, packet_data)
                    logger.debug(f"System: Updated telemetry timestamp for position packet from node {nodeID}")
                except Exception as e:
                    logger.error(f"System: Failed to update telemetry timestamp for position packet from node {nodeID}: {e}")

                # Insert telemetry data into telemetry table
                try:
                    lat = position_data.get('latitude')
                    lng = position_data.get('longitude')
                    alt = position_data.get('altitude')
                    ground_speed = position_data.get('groundSpeed')
                    if lat is not None and lng is not None:
                        insert_telemetry(str(nodeID), time.time(), lat, lng, alt, ground_speed)
                        logger.debug(f"System: Inserted telemetry data for node {nodeID}")
                except Exception as e:
                    logger.error(f"System: Failed to insert telemetry data for node {nodeID}: {e}")

                # Process position update for trigger system
                if trigger_engine and lat is not None and lng is not None:
                    try:
                        position = Position(
                            latitude=lat,
                            longitude=lng,
                            altitude=alt,
                            timestamp=time.time()
                        )
                        events = trigger_engine.process_position_update(str(nodeID), position)

                        # Execute trigger actions asynchronously
                        if events:
                            loop = asyncio.get_running_loop()
                            for event in events:
                                loop.create_task(execute_trigger_action(event))

                    except Exception as e:
                        logger.error(f"System: Failed to process position update for triggers: {e}")

                # if altitude is over highfly_altitude send a log and message for high-flying nodes and not in highfly_ignoreList
                if position_data.get('altitude', 0) > highfly_altitude and highfly_enabled and str(nodeID) not in highfly_ignoreList:
                    logger.info(f"System: High Altitude {position_data['altitude']}m on Device: {rxNode} NodeID: {nodeID}")
                    altFeet = round(position_data['altitude'] * 3.28084, 2)
                    msg = f"🚀 High Altitude Detected! NodeID:{nodeID} Alt:{altFeet:,.0f}ft/{position_data['altitude']:,.0f}m"

                    if highfly_check_openskynetwork:
                          # check get_openskynetwork to see if the node is an aircraft
                          if 'latitude' in position_data and 'longitude' in position_data:
                            flight_info = get_openskynetwork(position_data.get('latitude', 0), position_data.get('longitude', 0))
                            if flight_info and NO_ALERTS not in flight_info and ERROR_FETCHING_DATA not in flight_info:
                                msg += f"\n✈️Detected near:\n{flight_info}"

                    send_message(msg, highfly_channel, 0, highfly_interface)
                    time.sleep(responseDelay)

                # Keep the positionMetadata dictionary at a maximum size of 20
                if len(positionMetadata) > 20:
                    # Remove the oldest entry
                    oldest_nodeID = next(iter(positionMetadata))
                    del positionMetadata[oldest_nodeID]

                # add a packet count to the positionMetadata for the node
                if 'packetCount' in positionMetadata[nodeID]:
                    positionMetadata[nodeID]['packetCount'] += 1
                else:
                    positionMetadata[nodeID]['packetCount'] = 1

                # If position packet is from self, mark all undelivered messages addressed to this node as delivered
                if nodeID == globals().get(f'myNodeNum{rxNode}'):
                    try:
                        marked_count = mark_messages_delivered_to_node(nodeID)
                        if marked_count > 0:
                            logger.debug(f"System: Marked {marked_count} undelivered messages to self node {nodeID} as delivered")
                    except Exception as e:
                        logger.error(f"System: Failed to mark messages as delivered for node {nodeID}: {e}")

            except Exception as e:
                logger.debug(f"System: POSITION_APP decode error: {e} packet {packet}")

            # Broadcast position update to WebSocket clients
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(broadcast_map_update("node_position", {
                    "node_id": str(nodeID),
                    "lat": lat,
                    "lng": lng,
                    "altitude": alt,
                    "last_seen": time.time()
                }))
            except RuntimeError:
                # No running event loop, skip broadcast
                pass

        # WAYPOINT_APP packets
        if packet_type ==  'WAYPOINT_APP':
            if debugMetadata: print(f"DEBUG WAYPOINT_APP: {packet['decoded']['waypoint']}\n\n")
            # get the waypoint data
            waypoint_data = packet['decoded']

        # NEIGHBORINFO_APP
        if packet_type ==  'NEIGHBORINFO_APP':
            if debugMetadata: print(f"DEBUG NEIGHBORINFO_APP: {packet}\n\n")
            # get the neighbor info data
            neighbor_data = packet['decoded']
        
        # TRACEROUTE_APP
        if packet_type ==  'TRACEROUTE_APP':
            if debugMetadata: print(f"DEBUG TRACEROUTE_APP: {packet}\n\n")
            # get the traceroute data
            traceroute_data = packet['decoded']

        # DETECTION_SENSOR_APP
        if packet_type ==  'DETECTION_SENSOR_APP':
            if debugMetadata: print(f"DEBUG DETECTION_SENSOR_APP: {packet}\n\n")
            # get the detection sensor data
            detection_data = packet['decoded']
            detction_text = detection_data.get('text', '')
            if detction_text != '':
                logger.info(f"System: Detection Sensor Data from NodeID:{nodeID} Text:{detction_text}")
                #send_message(f"📡Detection Sensor Data from NodeID:{nodeID} Text:{detction_text}", detection_sensor_channel, 0, detection_sensor_interface)
                #time.sleep(responseDelay)

        # PAXCOUNTER_APP
        if packet_type ==  'PAXCOUNTER_APP':
            if debugMetadata: print(f"DEBUG PAXCOUNTER_APP: {packet}\n\n")
            # get the paxcounter data
            paxcounter_data = packet['decoded']

        # REMOTE_HARDWARE_APP
        if packet_type == 'REMOTE_HARDWARE_APP':
            if debugMetadata: print(f"DEBUG REMOTE_HARDWARE_APP: {packet}\n\n")
            # get the remote hardware data
            remote_hardware_data = packet['decoded']

        # TEXT_MESSAGE_APP
        if packet_type == 'TEXT_MESSAGE_APP':
            hop_count = 0

    except KeyError as e:
        logger.critical(f"System: Error consuming metadata: {e} Device:{rxNode}")
        logger.debug(f"System: Error Packet = {packet}")

def noisyTelemetryCheck():
    global positionMetadata
    if len(positionMetadata) == 0:
        return
    # sort the positionMetadata by packetCount
    sorted_positionMetadata = dict(sorted(positionMetadata.items(), key=lambda item: item[1].get('packetCount', 0), reverse=True))
    top_three = list(sorted_positionMetadata.items())[:3]
    for nodeID, data in top_three:
        if data.get('packetCount', 0) > noisyTelemetryLimit:
            logger.warning(f"System: Noisy Telemetry Detected from NodeID:{nodeID} ShortName:{get_name_from_number(nodeID, 'short', 1)} Packets:{data.get('packetCount', 0)}")
            # reset the packet count for the node
            positionMetadata[nodeID]['packetCount'] = 0

def get_sysinfo(nodeID=0, deviceID=1):
    # Get the system telemetry data for return on the sysinfo command
    sysinfo = ''
    stats = str(displayNodeTelemetry(nodeID, deviceID, userRequested=True)) + " 🤖👀" + str(len(seenNodes))
    if "numPacketsRx:0" in stats or stats == -1:
        return "Gathering Telemetry try again later⏳"
    # replace Telemetry with Int in string
    stats = stats.replace("Telemetry", "Int")
    sysinfo += f"📊{stats}"
    return sysinfo

async def BroadcastScheduler():
    # handle schedule checks for the broadcast of messages
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

async def handleSignalWatcher():
    global lastHamLibAlert
    # monitor rigctld for signal strength and frequency
    while True:
        msg =  await signalWatcher()
        if msg != ERROR_FETCHING_DATA and msg is not None:
            logger.debug(f"System: Detected Alert from Hamlib {msg}")
            
            # check we are not spammig the channel limit messages to once per minute
            if time.time() - lastHamLibAlert > 60:
                lastHamLibAlert = time.time()
                # if sigWatchBrodcastCh list contains multiple channels, broadcast to all
                if type(sigWatchBroadcastCh) is list:
                    for ch in sigWatchBroadcastCh:
                        if antiSpam and ch != publicChannel:
                            send_message(msg, int(ch), 0, 1)
                            time.sleep(responseDelay)
                            if multiple_interface:
                                for i in range(2, 10):
                                    if globals().get(f'interface{i}_enabled'):
                                        send_message(msg, int(ch), 0, i)
                                        time.sleep(responseDelay)
                        else:
                            logger.warning(f"System: antiSpam prevented Alert from Hamlib {msg}")
                else:
                    if antiSpam and sigWatchBroadcastCh != publicChannel:
                        send_message(msg, int(sigWatchBroadcastCh), 0, 1)
                        time.sleep(responseDelay)
                        if multiple_interface:
                            for i in range(2, 10):
                                if globals().get(f'interface{i}_enabled'):
                                    send_message(msg, int(sigWatchBroadcastCh), 0, i)
                                    time.sleep(responseDelay)
                    else:
                        logger.warning(f"System: antiSpam prevented Alert from Hamlib {msg}")

        await asyncio.sleep(1)
        pass

async def handleFileWatcher():
    global lastFileAlert
    # monitor the file system for changes
    while True:
        msg =  await watch_file()
        if msg != ERROR_FETCHING_DATA and msg is not None:
            logger.debug(f"System: Detected Alert from FileWatcher on file {file_monitor_file_path}")

            # check we are not spammig the channel limit messages to once per minute
            if time.time() - lastFileAlert > 60:
                lastFileAlert = time.time()
                # if fileWatchBroadcastCh list contains multiple channels, broadcast to all
                if type(file_monitor_broadcastCh) is list:
                    for ch in file_monitor_broadcastCh:
                        if antiSpam and int(ch) != publicChannel:
                            send_message(msg, int(ch), 0, 1)
                            time.sleep(responseDelay)
                            if multiple_interface:
                                for i in range(2, 10):
                                    if globals().get(f'interface{i}_enabled'):
                                        send_message(msg, int(ch), 0, i)
                                        time.sleep(responseDelay)
                        else:
                            logger.warning(f"System: antiSpam prevented Alert from FileWatcher")
                else:
                    if antiSpam and file_monitor_broadcastCh != publicChannel:
                        send_message(msg, int(file_monitor_broadcastCh), 0, 1)
                        time.sleep(responseDelay)
                        if multiple_interface:
                            for i in range(2, 10):
                                if globals().get(f'interface{i}_enabled'):
                                    send_message(msg, int(file_monitor_broadcastCh), 0, i)
                                    time.sleep(responseDelay)
                    else:
                        logger.warning(f"System: antiSpam prevented Alert from FileWatcher")

        await asyncio.sleep(1)
        pass

async def execute_trigger_action(event_data: dict):
    """Execute a trigger action asynchronously."""
    try:
        action_type = event_data.get('trigger', {}).get('action_type', '')
        action_payload = event_data.get('trigger', {}).get('action_payload', '')

        if action_type and action_payload:
            success = await action_executor.execute_action(action_type, action_payload, event_data)
            if success:
                logger.info(f"System: Trigger action executed successfully: {action_type}")
            else:
                logger.warning(f"System: Trigger action failed: {action_type}")
        else:
            logger.error("System: Invalid trigger action configuration")

    except Exception as e:
        logger.error(f"System: Failed to execute trigger action: {e}")

async def trigger_maintenance_loop():
    """Background loop for trigger system maintenance."""
    while True:
        try:
            if trigger_engine:
                # Clean up old position data
                trigger_engine.cleanup_old_states()

                # Reload configuration periodically (every 5 minutes)
                if int(time.time()) % 300 == 0:
                    trigger_engine.reload_configuration()
                    logger.debug("System: Trigger configuration reloaded")

        except Exception as e:
            logger.error(f"System: Error in trigger maintenance loop: {e}")

        await asyncio.sleep(60)  # Run every minute

async def retry_interface(nodeID):
    global retry_int1, retry_int2, retry_int3, retry_int4, retry_int5, retry_int6, retry_int7, retry_int8, retry_int9
    global max_retry_count1, max_retry_count2, max_retry_count3, max_retry_count4, max_retry_count5, max_retry_count6, max_retry_count7, max_retry_count8, max_retry_count9
    interface = globals()[f'interface{nodeID}']
    retry_int = globals()[f'retry_int{nodeID}']

    if dont_retry_disconnect:
        logger.critical(f"System: dont_retry_disconnect is set, not retrying interface{nodeID}")
        exit_handler()

    if interface is not None:
        globals()[f'retry_int{nodeID}'] = True
        globals()[f'max_retry_count{nodeID}'] -= 1
        logger.warning(f"System: Initiating retry for interface{nodeID}, {globals()[f'max_retry_count{nodeID}']} attempts remaining")
        try:
            interface.close()
            logger.debug(f"System: Closed interface{nodeID} for retry, waiting 15 seconds")
        except Exception as e:
            logger.error(f"System: Error closing interface{nodeID}: {e}")

    if globals()[f'max_retry_count{nodeID}'] == 0:
        logger.critical(f"System: Max retry count reached for interface{nodeID}, exiting")
        exit_handler()

    await asyncio.sleep(1)

    try:
        if retry_int:
            interface = None
            globals()[f'interface{nodeID}'] = None
            interface_type = globals()[f'interface{nodeID}_type']
            logger.info(f"System: Attempting to reopen interface{nodeID} of type {interface_type}")
            if interface_type == 'serial':
                logger.debug(f"System: Retrying Interface{nodeID} Serial on port: {globals().get(f'port{nodeID}')}")
                globals()[f'interface{nodeID}'] = meshtastic.serial_interface.SerialInterface(globals().get(f'port{nodeID}'))
            elif interface_type == 'tcp':
                logger.debug(f"System: Retrying Interface{nodeID} TCP on hostname: {globals().get(f'hostname{nodeID}')}")
                globals()[f'interface{nodeID}'] = meshtastic.tcp_interface.TCPInterface(globals().get(f'hostname{nodeID}'))
            elif interface_type == 'ble':
                logger.debug(f"System: Retrying Interface{nodeID} BLE on mac: {globals().get(f'mac{nodeID}')}")
                globals()[f'interface{nodeID}'] = meshtastic.ble_interface.BLEInterface(globals().get(f'mac{nodeID}'))
            logger.info(f"System: Successfully reopened interface{nodeID}")
            # reset the retry_int and retry_count
            globals()[f'max_retry_count{nodeID}'] = interface_retry_count
            globals()[f'retry_int{nodeID}'] = False
    except Exception as e:
        logger.error(f"System: Failed to reopen interface{nodeID}: {e}")
        # Do not reset retry_int here, let watchdog handle next attempt

handleSentinel_spotted = []
handleSentinel_loop = 0
async def handleSentinel(deviceID):
    global handleSentinel_spotted, handleSentinel_loop
    detectedNearby = ""
    resolution = "unknown"
    closest_nodes = get_closest_nodes(deviceID)
    closest_node = closest_nodes[0]['id'] if closest_nodes != ERROR_FETCHING_DATA and closest_nodes else None
    closest_distance = closest_nodes[0]['distance'] if closest_nodes != ERROR_FETCHING_DATA and closest_nodes else None

    # check if the handleSentinel_spotted list contains the closest node already
    if closest_node in [i['id'] for i in handleSentinel_spotted]:
        # check if the distance is closer than the last time, if not just return
        for i in range(len(handleSentinel_spotted)):
            if handleSentinel_spotted[i]['id'] == closest_node and closest_distance is not None and closest_distance < handleSentinel_spotted[i]['distance']:
                handleSentinel_spotted[i]['distance'] = closest_distance
                break
            else:
                return
    
    if closest_nodes != ERROR_FETCHING_DATA and closest_nodes:
        if closest_nodes[0]['id'] is not None:
            detectedNearby = get_name_from_number(closest_node, 'long', deviceID)
            detectedNearby += ", " + get_name_from_number(closest_nodes[0]['id'], 'short', deviceID)
            detectedNearby += ", " + str(closest_nodes[0]['id'])
            detectedNearby += ", " + decimal_to_hex(closest_nodes[0]['id'])
            detectedNearby += f" at {closest_distance}m"

    if handleSentinel_loop >= sentry_holdoff and detectedNearby not in ["", None]:
        if closest_nodes and positionMetadata and closest_nodes[0]['id'] in positionMetadata:
            metadata = positionMetadata[closest_nodes[0]['id']]
            if metadata.get('precisionBits') is not None:
                resolution = metadata.get('precisionBits')

        logger.warning(f"System: {detectedNearby} is close to your location on Interface{deviceID} Accuracy is {resolution}bits")
        send_message(f"Sentry{deviceID}: {detectedNearby}", secure_channel, 0, secure_interface)
        time.sleep(responseDelay + 1)
        if enableSMTP and email_sentry_alerts:
            for email in sysopEmails:
                send_email(email, f"Sentry{deviceID}: {detectedNearby}")
        handleSentinel_loop = 0
        handleSentinel_spotted.append({'id': closest_node, 'distance': closest_distance})
    else:
        handleSentinel_loop += 1

async def watchdog():
    global telemetryData, retry_int1, retry_int2, retry_int3, retry_int4, retry_int5, retry_int6, retry_int7, retry_int8, retry_int9
    counter = 0
    while True:
        await asyncio.sleep(1)
        counter += 1

        # Check for retries every second for immediate reconnection
        for i in range(1, 10):
            if globals().get(f'retry_int{i}') and globals().get(f'interface{i}_enabled'):
                try:
                    await retry_interface(i)
                except Exception as e:
                    logger.error(f"System: retrying interface{i}: {e}")

        # Perform full interface checks every 20 seconds
        if counter % 20 == 0:
            # check all interfaces
            for i in range(1, 10):
                interface = globals().get(f'interface{i}')
                retry_int = globals().get(f'retry_int{i}')
                if interface is not None and not retry_int and globals().get(f'interface{i}_enabled'):
                    try:
                        firmware = getNodeFirmware(0, i)
                    except Exception as e:
                        logger.error(f"System: Failed to communicate with interface{i}, error: {e} - initiating reconnection")
                        globals()[f'retry_int{i}'] = True

                    if not globals()[f'retry_int{i}']:
                        if sentry_enabled:
                            await handleSentinel(i)

                        handleMultiPing(0, i)

                        if wxAlertBroadcastEnabled or emergencyAlertBrodcastEnabled or volcanoAlertBroadcastEnabled:
                            handleAlertBroadcast(i)

                        intData = displayNodeTelemetry(0, i)
                        if intData != -1 and telemetryData[0][f'lastAlert{i}'] != intData:
                            logger.debug(intData + f" Firmware:{firmware}")
                            telemetryData[0][f'lastAlert{i}'] = intData

            # check for noisy telemetry
            if noisyNodeLogging:
                noisyTelemetryCheck()

def exit_handler():
    # Close the interface and save the BBS messages
    logger.debug(f"System: Closing Autoresponder")
    try:
        logger.debug(f"System: Closing Interface1")
        interface1.close()
        if multiple_interface:
            for i in range(2, 10):
                if globals().get(f'interface{i}_enabled'):
                    logger.debug(f"System: Closing Interface{i}")
                    globals()[f'interface{i}'].close()
    except Exception as e:
        logger.error(f"System: closing: {e}")
    if bbs_enabled:
        save_bbsdb()
        save_bbsdm()
        logger.debug(f"System: BBS Messages Saved")
    logger.debug(f"System: Exiting")
    asyncLoop.stop()
    asyncLoop.close()
    exit (0)
