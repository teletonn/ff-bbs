#!/usr/bin/env python3
"""
meshchat_telegram.py
--------------------
Bridges a Meshtastic radio (via SerialInterface) with a Telegram chat.

- Meshtastic -> Telegram: forwards received TEXT_MESSAGE_APP packets as messages
- Telegram -> Meshtastic: reads text/commands from a Telegram chat (polling) and
  sends them to the mesh. Supports:
    /help
    /nodes
    /msg !<nodeId> <message>   (private message to a node)
    any other text -> broadcast on current channel

Edit the BOT_TOKEN and CHAT_ID below before running.

Dependencies:
  pip install meshtastic pypubsub requests

Usage:
  python3 meshchat_telegram.py
"""

import threading
import time
from typing import Dict, List, Optional

import requests
from pubsub import pub
from meshtastic.serial_interface import SerialInterface


# ── LOGGING ───────────────────────────────────────────────────────────────────
def _log(msg: str):
    import time, sys

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _log_exc(prefix: str, e: Exception):
    _log(f"{prefix}: {e!r}")


# ── USER CONFIG ────────────────────────────────────────────────────────────────
BOT_TOKEN = "<YOUR:TOKEN>"  # <--- paste your token
CHAT_ID = "<CHATID>"  # target Telegram chat (string or int)
serial_port = "/dev/ttyACM0"  # your serial port
channel_index = 0  # your channel index

# ── TELEGRAM CLIENT ───────────────────────────────────────────────────────────
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
SEND_URL = f"{API_BASE}/sendMessage"
GET_UPDATES_URL = f"{API_BASE}/getUpdates"

POLL_INTERVAL = 2.0  # seconds between polls
OUTBOUND_MIN_DELAY = 0.25  # seconds; gentle throttle to avoid 429


def tg_send(text: str) -> None:
    """Send a message to Telegram chat; basic 429 backoff."""
    if not text:
        _log("[tg_send] skipped: empty text")
        return
    _log(f"[tg_send] → sending: {text!r}")
    time.sleep(OUTBOUND_MIN_DELAY)
    attempt = 1
    while True:
        try:
            r = requests.post(
                SEND_URL,
                data={
                    "chat_id": CHAT_ID,
                    "text": text,
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
            if r.status_code == 200:
                _log("[tg_send] ✓ delivered")
                return
            if r.status_code == 429:
                # crude retry-after
                try:
                    retry_after = r.json().get("parameters", {}).get("retry_after", 1)
                except Exception:
                    retry_after = 1
                _log(f"[tg_send] 429 rate-limited, retry_after={retry_after}s")
                time.sleep(max(1, int(retry_after)))
                attempt += 1
                continue
            # non-retriable; log & drop
            _log(f"[tg_send] ✗ HTTP {r.status_code}: {r.text}")
            return
        except requests.RequestException as e:
            _log(f"[tg_send] RequestException: {e!r} (attempt {attempt})")
            time.sleep(1)
            attempt += 1


def tg_poll_loop(handler):
    _log(f"[tg_poll] starting loop, interval={POLL_INTERVAL}s")
    """
    Poll Telegram for new messages and call handler(text) for messages
    from CHAT_ID only. Keeps an in-memory offset to avoid duplicates.
    """
    offset = None
    while True:
        try:
            params = {"timeout": 0, "limit": 20}
            if offset is not None:
                params["offset"] = offset
            r = requests.get(GET_UPDATES_URL, params=params, timeout=35)
            if r.status_code != 200:
                _log(f"[tg_poll] ✗ HTTP {r.status_code}: {r.text}")
                time.sleep(POLL_INTERVAL)
                continue
            data = r.json()
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or update.get("edited_message")
                if not msg:
                    _log("[tg_poll] skip: no message object")
                    continue
                if str(msg.get("chat", {}).get("id")) != str(CHAT_ID):
                    _log("[tg_poll] skip: not our chat id")
                    continue
                text = msg.get("text")
                if not text:
                    _log("[tg_poll] skip: empty text")
                    continue
                _log(f"[tg_poll] incoming text: {text!r}")
                handler(text.strip())
            time.sleep(POLL_INTERVAL)
        except requests.RequestException as e:
            _log(f"[tg_poll] RequestException: {e!r}")
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            _log(f"[tg_poll] Unexpected error: {e!r}")
            time.sleep(POLL_INTERVAL)


def parse_node_info(node_info: Optional[Dict[str, dict]]) -> List[dict]:
    nodes = []
    if not node_info:
        return nodes
    for node_id, node in node_info.items():
        short_name = "Unknown"
        try:
            short_name = node.get("user", {}).get("shortName", "Unknown")
        except Exception:
            pass
        nodes.append({"num": node_id, "user": {"shortName": short_name}})
    return nodes


# ── ANNOUNCEMENTS ────────────────────────────────────────────────────────────
def announce_nodes(nodes: List[dict]) -> None:
    if not nodes:
        tg_send("No known nodes yet.")
        return
    lines = [f"Known nodes ({len(nodes)}):"] + [
        f"• {n['num']}: {n['user']['shortName']}" for n in nodes
    ]
    tg_send("\n".join(lines))


# ── SERIAL CONNECTION MANAGEMENT ─────────────────────────────────────────────
RECONNECT_INITIAL_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0


class SerialManager:
    def __init__(self, port: str) -> None:
        self.port = port
        self._lock = threading.RLock()
        self._interface: Optional[SerialInterface] = None
        self._connect_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connected_event = threading.Event()
        self._last_status: Optional[str] = None
        self._node_cache: List[dict] = []

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self) -> None:
        pub.subscribe(self._handle_connection_lost, "meshtastic.connection.lost")
        self._connected_event.clear()
        self._ensure_connect_thread()

    def stop(self) -> None:
        self._stop_event.set()
        try:
            pub.unsubscribe(self._handle_connection_lost, "meshtastic.connection.lost")
        except Exception:
            pass
        self._drop_interface(close=True, announce=False)
        thread = None
        with self._lock:
            thread = self._connect_thread
        if thread:
            thread.join(timeout=1.0)

    # ── connection state helpers ────────────────────────────────────────────
    def is_connected(self) -> bool:
        return self._connected_event.is_set()

    def wait_until_connected(self, timeout: Optional[float] = None) -> bool:
        return self._connected_event.wait(timeout)

    def get_interface(self) -> Optional[SerialInterface]:
        with self._lock:
            return self._interface

    def refresh_nodes(self) -> List[dict]:
        interface = self.get_interface()
        nodes: List[dict] = []
        if interface:
            try:
                node_info = getattr(interface, "nodes", None)
                nodes = parse_node_info(node_info)
            except Exception as e:
                _log(f"[manager] refresh_nodes error: {e!r}")
                nodes = []
        with self._lock:
            self._node_cache = nodes
        return list(nodes)

    def get_nodes(self) -> List[dict]:
        with self._lock:
            cached = list(self._node_cache)
        if cached:
            return cached
        return self.refresh_nodes()

    def trigger_reconnect(self) -> None:
        self._drop_interface(close=True)
        self._ensure_connect_thread()

    # ── internal helpers ────────────────────────────────────────────────────
    def _ensure_connect_thread(self) -> None:
        with self._lock:
            if self._connect_thread and self._connect_thread.is_alive():
                return
            self._connect_thread = threading.Thread(
                target=self._connect_worker,
                name="serial-reconnect",
                daemon=True,
            )
            self._connect_thread.start()

    def _connect_worker(self) -> None:
        delay = RECONNECT_INITIAL_DELAY
        try:
            while not self._stop_event.is_set():
                if self.get_interface() is not None:
                    return
                _log(f"[manager] attempting to open {self.port}")
                try:
                    interface = SerialInterface(self.port)
                    self._install_interface(interface)
                    self._connected_event.set()
                    return
                except Exception as e:
                    _log(f"[manager] connect failed: {e!r}")
                    self._connected_event.clear()
                    self._notify_status("offline")
                    if self._stop_event.wait(delay):
                        return
                    delay = min(delay * 2, RECONNECT_MAX_DELAY)
        finally:
            with self._lock:
                self._connect_thread = None

    def _install_interface(self, interface: SerialInterface) -> None:
        old_interface = None
        with self._lock:
            old_interface = self._interface
            self._interface = interface
        if old_interface and old_interface is not interface:
            try:
                old_interface.close()
            except Exception as e:
                _log(f"[manager] error closing old interface: {e!r}")
        self._connected_event.set()
        nodes = self.refresh_nodes()
        self._notify_status("online")
        announce_nodes(nodes)

    def _drop_interface(self, close: bool = False, announce: bool = True) -> None:
        interface = None
        with self._lock:
            interface = self._interface
            self._interface = None
            self._node_cache = []
        self._connected_event.clear()
        if interface and close:
            try:
                interface.close()
            except Exception as e:
                _log(f"[manager] error closing interface: {e!r}")
        if announce:
            self._notify_status("offline")

    def _handle_connection_lost(self, interface=None, **kwargs):  # type: ignore[no-untyped-def]
        if self._stop_event.is_set():
            return
        _log("[manager] connection lost event received; scheduling reconnect")
        self._drop_interface(close=False, announce=True)
        self._ensure_connect_thread()

    def _notify_status(self, status: str) -> None:
        if status == self._last_status:
            return
        self._last_status = status
        if status == "online":
            tg_send("Meshtastic radio connected.")
        elif status == "offline":
            tg_send("Meshtastic radio disconnected. Retrying…")


# ── CHAT COMMANDS ─────────────────────────────────────────────────────────────
HELP_TEXT = (
    "Commands:\n"
    "/help – This help\n"
    "/nodes – Show known nodes\n"
    "/msg !<nodeId> <message> – Send private message to node\n"
    "Any other text will be broadcast on the current channel."
)


def make_command_handler(manager: SerialManager):
    def handle_text(text: str):
        interface = manager.get_interface()
        if interface is None:
            tg_send("Radio offline. Message not sent (still reconnecting).")
            manager.trigger_reconnect()
            return
        try:
            if text == "/help":
                tg_send(HELP_TEXT)
                return
            if text == "/nodes":
                nodes = manager.refresh_nodes()
                if not nodes:
                    tg_send("No nodes known yet.")
                else:
                    lines = [
                        f"Node {n['num']}: {n['user']['shortName']}" for n in nodes
                    ]
                    tg_send("\n".join(lines))
                return
            if text.startswith("/msg !"):
                parts = text.split(maxsplit=2)
                if len(parts) >= 3:
                    node_id = parts[1]
                    msg = parts[2]
                    interface.sendText(msg, node_id, channelIndex=channel_index)
                    tg_send(f"📩 Sent PM to {node_id}: {msg}")
                else:
                    tg_send("Invalid format. Use: /msg !<nodeId> <message>")
                return
            # default: broadcast
            interface.sendText(text, channelIndex=channel_index)
            tg_send(f"↗️ Broadcast: {text}")
        except Exception as e:
            tg_send(f"Error handling command: {e!r}")
            manager.trigger_reconnect()

    return handle_text


# ── RECEIVE FROM MESH ─────────────────────────────────────────────────────────
def on_receive(packet, manager: SerialManager):
    if not packet:
        _log("[recv] skip: packet is None")
        return
    try:
        # if packet.get("channel") != channel_index:
        #     _log(
        #         f"[recv] skip: wrong channel {packet.get('channel')} != {channel_index}"
        #     )
        #     return
        otherChannel = ""
        if packet.get("channel") != channel_index:
            _log(f"[recv] other channel {packet.get('channel')} != {channel_index}")
            otherChannel = f"[ch{packet.get('channel')}] "
            
        _log(f"[recv] packet keys={list(packet.keys())}")
        node_list = manager.get_nodes()
        pNum = packet["decoded"].get("portnum")
        if (
            "decoded" in packet
            and pNum == "TEXT_MESSAGE_APP"
        ):
            payload = packet["decoded"]["payload"]
            if isinstance(payload, (bytes, bytearray)):
                message = payload.decode("utf-8", errors="replace")
            else:
                # sometimes newer libs may already provide str
                message = str(payload)

            fromnum = packet.get("fromId", "unknown")
            to_id = packet.get("toId", "^all")
            shortname = next(
                (n["user"]["shortName"] for n in node_list if n["num"] == fromnum),
                "Unknown",
            )
            is_private_message = to_id != "^all"

            timestamp = time.strftime("%H:%M:%S")
            if is_private_message:
                dest_shortname = next(
                    (n["user"]["shortName"] for n in node_list if n["num"] == to_id),
                    "Unknown",
                )
                formatted = f"{timestamp} {otherChannel}{shortname} -> {to_id} ({dest_shortname}) 📩 {message}"
            else:
                formatted = f"{timestamp} {otherChannel}{shortname}: {message}"

            _log(f"[recv] → forwarding to Telegram: {formatted!r}")
            tg_send(formatted)
        else:
            _log(f"[recv] skip: a '{pNum}' packet")
    except UnicodeDecodeError as e:
        _log(f"[recv] UnicodeDecodeError: {e!r}")
        tg_send(f"UnicodeDecodeError: {e}")
    except Exception as e:
        _log(f"[recv] error: {e!r}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    _log("starting Mesh↔Telegram bridge…")
    _log(
        f"config: serial_port={serial_port}, channel_index={channel_index}, chat_id={CHAT_ID}"
    )
    tg_send("Mesh↔Telegram bridge starting…")
    manager = SerialManager(serial_port)
    manager.start()

    if manager.wait_until_connected(timeout=30):
        _log("[main] initial connection established")
    else:
        _log("[main] radio not yet connected; waiting in background")
        tg_send("Waiting for Meshtastic radio to become available…")

    # Subscribe with keyword-arg-friendly signature
    def recv_wrapper(packet=None, interface=None, **kwargs):
        _log(f"[listener] recv_wrapper called; packet is {type(packet)}")
        on_receive(packet, manager)

    try:
        pub.unsubscribe(recv_wrapper, "meshtastic.receive")
    except Exception:
        pass
    pub.subscribe(recv_wrapper, "meshtastic.receive")
    _log("[main] subscribed to 'meshtastic.receive'")

    tg_send("Subscribed to meshtastic.receive. Send /help to see commands.")

    # Start Telegram poller in a background thread
    handler = make_command_handler(manager)
    t = threading.Thread(target=tg_poll_loop, args=(handler,), daemon=True)
    t.start()
    _log("[main] Telegram poller started")

    # Keep the main thread alive; SerialInterface uses background threads too
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            pub.unsubscribe(recv_wrapper, "meshtastic.receive")
        except Exception:
            pass
        manager.stop()
        tg_send("Mesh↔Telegram bridge stopped.")


if __name__ == "__main__":
    main()
