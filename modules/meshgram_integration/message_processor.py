from __future__ import annotations

import asyncio
from typing import TypedDict, Literal, Protocol, Any, NotRequired
from collections.abc import Awaitable
from datetime import datetime, timezone, timedelta
from telegram import Update
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from modules.meshgram_integration.meshtastic_interface import MeshtasticInterface
from modules.meshgram_integration.telegram_interface import TelegramInterface
from modules.meshgram_integration.config_manager import ConfigManager
from modules import log
from modules.meshgram_integration.node_manager import NodeManager

class CommandHandler(Protocol):
    async def __call__(self, args: list[str], user_id: int, update: Update) -> None:
        ...

class MeshtasticPacket(TypedDict):
    fromId: str
    toId: str
    decoded: dict[str, Any]
    id: str

class TelegramMessage(TypedDict):
    type: Literal['command', 'telegram', 'location', 'reaction']
    text: NotRequired[str]
    sender: NotRequired[str]
    message_id: NotRequired[int]
    user_id: NotRequired[int]
    command: NotRequired[str]
    args: NotRequired[list[str]]
    update: NotRequired[Update]
    location: NotRequired[dict[str, float]]
    emoji: NotRequired[str]
    original_message_id: NotRequired[int]

class PendingAck(TypedDict):
    telegram_message_id: int
    timestamp: datetime

class MessageProcessor:
    def __init__(self, meshtastic: MeshtasticInterface, telegram: TelegramInterface, config: ConfigManager) -> None:
        self.config: ConfigManager = config
        self.logger = log.logger
        self.meshtastic: MeshtasticInterface = meshtastic
        self.telegram: TelegramInterface = telegram
        self.node_manager: NodeManager = meshtastic.node_manager
        self.start_time: datetime = datetime.now(timezone.utc)
        local_nodes_str = config.get('telegram.meshtastic_local_nodes', '')
        self.local_nodes: list[str] = [node.strip() for node in local_nodes_str.split(',') if node.strip()] if local_nodes_str else []
        self.is_closing: bool = False
        self.processing_tasks: list[asyncio.Task] = []
        self.message_id_map: dict[int, str] = {}
        self.reverse_message_id_map: dict[str, int] = {}
        self.pending_acks: dict[int, PendingAck] = {}
        self.ack_timeout: int = 60  # seconds
        self.bell_rate_limit: dict[int, datetime] = {}  # Track bell command usage per user
        self.bell_cooldown_seconds: int = 120  # 2 minutes cooldown for non-authorized users

    async def process_messages(self) -> None:
        self.processing_tasks = [
            asyncio.create_task(self.process_meshtastic_messages()),
            asyncio.create_task(self.process_telegram_messages()),
            asyncio.create_task(self.process_pending_acks())
        ]
        try:
            await asyncio.gather(*self.processing_tasks)
        except asyncio.CancelledError:
            self.logger.info("Message processing tasks cancelled.")
        finally:
            await self.close()

    async def process_meshtastic_messages(self) -> None:
        while not self.is_closing:
            try:
                message: MeshtasticPacket = await self.meshtastic.message_queue.get()
                self.logger.debug(f"Processing Meshtastic message: {message=}")
                match message.get('type'):
                    case 'ack':
                        await self.handle_ack(message)
                    case _:
                        await self.handle_meshtastic_message(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing Meshtastic message: {e=}", exc_info=True)
            await asyncio.sleep(0.1)

    async def process_telegram_messages(self) -> None:
        while not self.is_closing:
            try:
                message: TelegramMessage = await self.telegram.message_queue.get()
                self.logger.info(f"Processing Telegram message: {message=}")
                await self.handle_telegram_message(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing Telegram message: {e=}", exc_info=True)
            await asyncio.sleep(0.1)

    async def handle_meshtastic_message(self, packet: Dict[str, Any]) -> None:
        self.logger.debug(f"Received Meshtastic message: {packet=}")
        
        if packet.get('type') == 'ack':
            await self.handle_ack(packet)
        else:
            portnum = packet.get('decoded', {}).get('portnum', '')
            handler = getattr(self, f"handle_{portnum.lower()}", None)
            if handler:
                self.logger.info(f"Handling Meshtastic message type {portnum=} from {packet.get('fromId')=}")
                await handler(packet)
            else:
                self.logger.warning(f"Unhandled Meshtastic message type: {portnum=} from: {packet.get('fromId')=}")

    async def handle_ack(self, packet: Dict[str, Any]) -> None:
        message_id = packet.get('id')
        if message_id is None:
            self.logger.warning("Received ACK without message ID")
            return

        pending_message = self.pending_acks.pop(message_id, None)
        if pending_message:
            telegram_message_id = pending_message.get('telegram_message_id')
            if telegram_message_id:
                await self.telegram.add_reaction(telegram_message_id, '✅')
                self.logger.info(f"ACK processed for message ID: {message_id}, Telegram message ID: {telegram_message_id}")
            else:
                self.logger.warning(f"ACK received for message ID {message_id}, but no Telegram message ID found")
        else:
            self.logger.warning(f"Received ACK for unknown message ID: {message_id}")

    async def handle_text_message_app(self, packet: Dict[str, Any]) -> None:
        text: str = packet['decoded']['payload'].decode('utf-8')
        sender, recipient = packet.get('fromId', 'unknown'), packet.get('toId', 'unknown')
        channel = packet.get('channel', 0)  # Default to channel 0 if not specified

        # Get configured default channel for broadcasting to Telegram
        configured_channel = self.config.get('telegram.telegram_default_channel', 0)
        if isinstance(configured_channel, str):
            configured_channel = int(configured_channel)

        # Only forward broadcast messages from the specified channel to Telegram (excluding telemetry data)
        if channel == configured_channel and recipient == "^all" and not self._is_telemetry_data(text):
            message: str = f"📡 Meshtastic CH{configured_channel}: {sender} → {recipient}\n💬 {text}"
            self.logger.info(f"Broadcasting channel {configured_channel} message to Telegram: {message=}")
            await self.telegram.send_message(message, disable_notification=False)

    async def handle_telegram_text(self, message: Dict[str, Any]) -> None:
        self.logger.info(f"Handling Telegram text message: {message}")
        sender = message['sender'][:10]
        text = message['text']
        telegram_message_id = message['message_id']
        user_id = message.get('user_id')
        chat_type = message.get('chat_type', 'group')  # default to group if not provided

        # Get the default node ID for routing messages to Meshtastic
        default_node_id = self.config.get('telegram.meshtastic_default_node_id')

        if chat_type == 'private':
            # For DM messages, send to "^all"
            recipient = "^all"
        else:
            # Check if user is authorized to send to default node (which represents channel 0)
            if default_node_id and self._is_default_node_id(default_node_id) and user_id and not self.telegram.is_user_authorized(user_id):
                self.logger.warning(f"Unauthorized user {user_id} attempted to send message to default node/channel 0")
                await self.telegram.send_message("❌ You are not authorized to send messages to the Meshtastic default channel.")
                return

            # Use default node ID if available, otherwise send to broadcast
            recipient = default_node_id if default_node_id else "^all"

        meshtastic_message = f"[TG:{sender}] {text}"
        self.logger.info(f"Preparing to send Telegram message to Meshtastic: {meshtastic_message} -> {recipient}")
        try:
            meshtastic_message_id = await self.meshtastic.send_message(meshtastic_message, recipient)
            self.logger.info(f"Successfully sent message to Meshtastic: {meshtastic_message} -> {recipient}")

            self.pending_acks[meshtastic_message_id] = {
                'telegram_message_id': telegram_message_id,
                'timestamp': datetime.now(timezone.utc)
            }

            asyncio.create_task(self.remove_pending_ack(meshtastic_message_id))
        except Exception as e:
            self.logger.error(f"Failed to send message to Meshtastic: {e}", exc_info=True)
            await self.telegram.send_message("Failed to send message to Meshtastic. Please try again.")

    async def remove_pending_ack(self, message_id: str) -> None:
        await asyncio.sleep(self.ack_timeout)
        if message_id in self.pending_acks:
            self.logger.warning(f"ACK timeout for message ID: {message_id}")
            del self.pending_acks[message_id]

    async def process_pending_acks(self) -> None:
        while True:
            now = datetime.now(timezone.utc)
            for message_id, data in list(self.pending_acks.items()):
                if (now - data['timestamp']).total_seconds() > self.ack_timeout:
                    self.logger.warning(f"ACK timeout for message ID: {message_id}")
                    del self.pending_acks[message_id]
            await asyncio.sleep(10)  # Check every 10 seconds

    async def handle_telegram_message(self, message: TelegramMessage) -> None:
        handlers: dict[str, CommandHandler] = {
            'command': self.handle_telegram_command,
            'telegram': self.handle_telegram_text,
            'location_request': self.handle_telegram_location_request,
            'reaction': self.handle_telegram_reaction
        }
        handler = handlers.get(message['type'])
        if handler:
            await handler(message)
        else:
            self.logger.warning(f"Received unknown message type: {message['type']=}")

    def _store_message_id_mapping(self, telegram_id: int, meshtastic_id: str) -> None:
        self.message_id_map[telegram_id] = meshtastic_id
        self.reverse_message_id_map[meshtastic_id] = telegram_id

    def _get_meshtastic_message_id(self, telegram_message_id: int) -> str | None:
        return self.message_id_map.get(telegram_message_id)

    def _get_telegram_message_id(self, meshtastic_message_id: str) -> int | None:
        return self.reverse_message_id_map.get(meshtastic_message_id)

    async def update_message_status(self, meshtastic_message_id: str, status: str) -> None:
        telegram_message_id = self._get_telegram_message_id(meshtastic_message_id)
        if telegram_message_id:
            await self.telegram.update_message_status(telegram_message_id, status)
        else:
            self.logger.warning(f"Could not find corresponding Telegram message for Meshtastic message ID: {meshtastic_message_id}")

    async def handle_telegram_location_request(self, message: TelegramMessage) -> None:
        location = message.get('location', {})
        lat, lon = location.get('latitude'), location.get('longitude')
        accuracy = location.get('accuracy')
        sender = message.get('sender', 'unknown')
        user_id = message.get('user_id')
        node_id = message.get('node_id', self.config.get('telegram.meshtastic_default_node_id') or "^all")

        try:
            if not self.is_valid_coordinate(lat, lon, 0):
                raise ValueError("Invalid coordinates")

            # Use the node_id from message
            recipient = node_id

            location_msg = f"[TG:{sender}] 📍 lat={lat:.6f}, lon={lon:.6f}"
            if accuracy:
                location_msg += f", accuracy={accuracy:.1f}m"

            await self.meshtastic.send_message(location_msg, recipient)
            # Send confirmation to user's DM
            confirmation = f"📍 Location sent to Meshtastic node {recipient}: lat={lat:.6f}, lon={lon:.6f}"
            await self.telegram.send_message_to_chat(user_id, confirmation)
        except ValueError as e:
            self.logger.error(f"Invalid location data: {e}")
            await self.telegram.send_message_to_chat(user_id, f"Failed to send location to Meshtastic. Invalid data: {e}")
        except Exception as e:
            self.logger.error(f"Failed to send location to Meshtastic: {e}", exc_info=True)
            await self.telegram.send_message_to_chat(user_id, "Failed to send location to Meshtastic. Please try again.")

    def is_valid_coordinate(self, lat: float | None, lon: float | None, alt: float) -> bool:
        return (lat is not None and lon is not None and
                -90 <= lat <= 90 and -180 <= lon <= 180 and -1000 <= alt <= 50000)

    async def handle_telegram_command(self, message: TelegramMessage) -> None:
        try:
            command = message.get('command', '').partition('@')[0]
            args = message.get('args', [])
            user_id = message.get('user_id')
            update = message.get('update')

            if not user_id or not update:
                self.logger.error("Missing user_id or update in command message")
                return

            # Check if this is a DM (not a group message)
            is_dm = update.message.chat.type == 'private'

            # Commands allowed in DM for unauthorized users
            dm_allowed_commands = ['start', 'help', 'user']

            # Check authorization for DM messages
            if is_dm and not self.telegram.is_user_authorized(user_id) and command not in dm_allowed_commands:
                await update.message.reply_text(
                    "❌ Unauthorized DM usage. Only /start, /help, and /user commands are available in DM for unauthorized users.\n\n"
                    "Please use group chat for other commands or contact an administrator for authorization."
                )
                return

            # Check authorization for group messages (existing logic)
            if not is_dm and not self.telegram.is_user_authorized(user_id) and command not in ['start', 'help', 'user']:
                await update.message.reply_text("You are not authorized to use this command.")
                return

            handler = getattr(self, f"cmd_{command}", None)
            if handler:
                await handler(args, user_id, update)
            else:
                await update.message.reply_text(f"Unknown command: {command}")
        except Exception as e:
            self.logger.error(f'Error handling Telegram command: {e}', exc_info=True)
            if update and update.message:
                await update.message.reply_text(f"Error executing command: {e}")

    async def handle_telegram_reaction(self, message: TelegramMessage) -> None:
        self.logger.info(f"Processing reaction: {message}")
        emoji = message.get('emoji')
        original_message_id = message.get('original_message_id')
        
        if not emoji or not original_message_id:
            self.logger.error("Missing emoji or original_message_id in reaction message")
            return

        meshtastic_message_id = self._get_meshtastic_message_id(original_message_id)
        
        if meshtastic_message_id:
            await self.meshtastic.send_reaction(emoji, meshtastic_message_id)
        else:
            self.logger.warning(f"Could not find corresponding Meshtastic message for Telegram message ID: {original_message_id}")

    async def cmd_start(self, args: list[str], user_id: int, update: Update) -> None:
        welcome_message = (
            "Welcome! 🌐📱\n\n"
            "This bot bridges Telegram chat with a Meshtastic mesh network.\n"
            "Use /help to see available commands."
        )
        await update.message.reply_text(escape_markdown(welcome_message, version=2), parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_help(self, args: list[str], user_id: int, update: Update) -> None:
        help_text = (
            "Available commands:\n\n"
            "/start - Start the bot and see welcome message\n"
            "/help - Show this help message\n"
            "/status - Check the current status of Meshgram and Meshtastic\n"
            "/bell [node_id] - Send a bell notification to a Meshtastic node\n"
            "/node <node_id> [message] - Get information about a specific node or send message to node\n"
            "/location - Share your location with the Meshtastic network\n"
            "/user - Get information about your Telegram user"
        )
        await update.message.reply_text(escape_markdown(help_text, version=2), parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_status(self, args: list[str], user_id: int, update: Update) -> None:
        status: str = await self.get_status()
        await update.message.reply_text(status, parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_bell(self, args: list[str], user_id: int, update: Update) -> None:
        # Check rate limiting for non-authorized users
        is_limited, seconds_remaining = self._is_rate_limited(user_id)
        if is_limited:
            await update.message.reply_text(
                f"⏳ Rate limited. Please wait {seconds_remaining} seconds before using /bell again."
            )
            return

        dest_id = "^all"  # Send to all nodes

        # Check if this is a group chat
        is_group = update.message.chat.type in ['group', 'supergroup']
        is_authorized = self.telegram.is_user_authorized(user_id)

        self.logger.info(f"Sending bell to {dest_id} from {'group' if is_group else 'DM'} by {'authorized' if is_authorized else 'unauthorized'} user {user_id}")

        try:
            await self.meshtastic.send_bell(dest_id)

            # Update rate limit timestamp
            self._update_bell_rate_limit(user_id)

            # Enhanced response for group chats
            if is_group:
                user_mention = update.message.from_user.first_name or update.message.from_user.username or "User"
                base_message = f"🔔 Bell sent to all nodes by {user_mention}"

                # Add rate limit info for non-authorized users
                if not is_authorized:
                    next_use_time = (datetime.now(timezone.utc) + timedelta(seconds=self.bell_cooldown_seconds)).strftime("%H:%M:%S UTC")
                    base_message += f"\n⏰ Next /bell available at {next_use_time} (2min cooldown)"

                await update.message.reply_text(
                    escape_markdown(base_message, version=2),
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_notification=False  # Notify in groups for bell commands
                )
            else:
                # DM response
                await update.message.reply_text(
                    escape_markdown(f"🔔 Bell sent to all nodes.", version=2),
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_notification=True
                )
        except Exception as e:
            self.logger.error(f"Failed to send bell to {dest_id}: {e=}", exc_info=True)
            await update.message.reply_text(
                escape_markdown(f"Failed to send bell to all nodes. Error: {str(e)}", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )

    async def cmd_node(self, args: list[str], user_id: int, update: Update) -> None:
        if not args:
            await update.message.reply_text("Usage: /node <node_id> [message] - Get node info or send message to node")
            return

        node_id: str = args[0]
        message_text: str = " ".join(args[1:]) if len(args) > 1 else None

        # Check if user is authorized for group messaging
        if message_text and not self.telegram.is_user_authorized(user_id):
            await update.message.reply_text(
                escape_markdown("You are not authorized to send messages to nodes.", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        # If message provided, send it to the node (group message)
        if message_text:
            try:
                await self.meshtastic.send_message(f"[TG:{update.effective_user.first_name}] {message_text}", node_id)
                await update.message.reply_text(
                    escape_markdown(f"📡 Message sent to node {node_id}: {message_text}", version=2),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception as e:
                self.logger.error(f"Failed to send message to node {node_id}: {e}", exc_info=True)
                await update.message.reply_text(
                    escape_markdown(f"Failed to send message to node {node_id}. Error: {str(e)}", version=2),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            return

        # Otherwise, show node information
        node_info: str = self.node_manager.format_node_info(node_id)
        telemetry_info: str = self.node_manager.get_node_telemetry(node_id)
        position_info: str = self.node_manager.get_node_position(node_id)
        routing_info: str = self.node_manager.format_node_routing(node_id)
        neighbor_info: str = self.node_manager.format_node_neighbors(node_id)
        sensor_info: str = self.node_manager.get_node_sensor_info(node_id)

        full_info: str = f"{node_info}\n\n{telemetry_info}\n\n{position_info}\n\n{routing_info}\n\n{neighbor_info}\n\n{sensor_info}"
        await update.message.reply_text(escape_markdown(full_info, version=2), parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_user(self, args: list[str], user_id: int, update: Update) -> None:
        user = update.effective_user
        user_info = (
            f"User Information:\n"
            f"ID: {user.id}\n"
            f"Username: @{user.username}\n"
            f"First Name: {user.first_name}\n"
            f"Last Name: {user.last_name}\n"
            f"Is Bot: {'Yes' if user.is_bot else 'No'}\n"
            f"Language Code: {user.language_code}\n"
            f"Is Authorized: {'Yes' if self.telegram.is_user_authorized(user.id) else 'No'}"
        )
        await update.message.reply_text(escape_markdown(user_info, version=2), parse_mode=ParseMode.MARKDOWN_V2)

    async def get_status(self) -> str:
        uptime: timedelta = datetime.now(timezone.utc) - self.start_time
        meshtastic_status: str = await self.meshtastic.get_status()
        num_nodes: int = len(self.node_manager.get_all_nodes())
        
        status_lines: list[str] = [
            "📊 *Meshgram Status*:",
            f"⏱️ Uptime: `{self._format_uptime(uptime.total_seconds())}`",
            f"🔢 Connected Nodes: `{num_nodes}`",
            "",
            "📡 *Meshtastic Status*:"
        ]
        
        for line in meshtastic_status.split('\n'):
            key, value = line.split(': ', 1)
            status_lines.append(f"{key}: `{escape_markdown(value, version=2)}`")
        
        return "\n".join(status_lines)

    async def close(self) -> None:
        if self.is_closing:
            self.logger.info("MessageProcessor is already closing, skipping.")
            return

        self.is_closing = True
        self.logger.info("Closing MessageProcessor...")
        
        for task in self.processing_tasks:
            if not task.done():
                task.cancel()
        
        if self.processing_tasks:
            await asyncio.gather(*self.processing_tasks, return_exceptions=True)
        
        self.processing_tasks.clear()
        self.is_closing = False
        self.logger.info("MessageProcessor closed.")

    def _format_uptime(self, seconds: float) -> str:
        days, remainder = divmod(int(seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{days}d {hours:02d}h {minutes:02d}m"

    def _format_channel_utilization(self, value: float) -> str:
        return f"{value:.2f}%" if isinstance(value, (int, float)) else str(value)

    def _is_telemetry_data(self, text: str) -> bool:
        """Check if the message contains telemetry data that should be excluded from channel 0 broadcasts."""
        telemetry_keywords = [
            'battery', 'voltage', 'temperature', 'humidity', 'barometer',
            'iaq', 'distance', 'current', 'power', 'energy', 'rssi',
            'snr', 'device metrics', 'air util', 'channel util'
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in telemetry_keywords)

    def _is_default_node_id(self, node_id: str) -> bool:
        """Check if the node ID is the default node ID (representing channel 0)."""
        default_node_id = self.config.get('telegram.meshtastic_default_node_id')
        return node_id == default_node_id

    def _is_rate_limited(self, user_id: int) -> tuple[bool, int]:
        """
        Check if a user is rate limited for bell command.
        Returns (is_limited, seconds_remaining).
        Authorized users bypass rate limiting.
        """
        # Authorized users can bypass rate limiting
        if self.telegram.is_user_authorized(user_id):
            return False, 0

        now = datetime.now(timezone.utc)
        last_bell_time = self.bell_rate_limit.get(user_id)

        if last_bell_time is None:
            return False, 0

        time_diff = (now - last_bell_time).total_seconds()
        if time_diff < self.bell_cooldown_seconds:
            remaining = int(self.bell_cooldown_seconds - time_diff)
            return True, remaining

        return False, 0

    def _update_bell_rate_limit(self, user_id: int) -> None:
        """Update the rate limit timestamp for a user."""
        self.bell_rate_limit[user_id] = datetime.now(timezone.utc)

    async def _update_telemetry_message(self, node_id: str, telemetry_data: dict[str, Any]) -> None:
        self.node_manager.update_node_telemetry(node_id, telemetry_data)
        telemetry_info = self.node_manager.get_node_telemetry(node_id)
        await self.telegram.send_or_edit_message('telemetry', node_id, telemetry_info)

    async def _update_location_message(self, node_id: str, position_data: dict[str, Any]) -> None:
        self.node_manager.update_node_position(node_id, position_data)
        position_info = self.node_manager.get_node_position(node_id)
        await self.telegram.send_or_edit_message('location', node_id, position_info)

    def _get_battery_status(self, battery_level: int) -> str:
        return "PWR" if battery_level == 101 else f"{battery_level}%"

    async def handle_nodeinfo_app(self, packet: MeshtasticPacket) -> None:
        node_id: str = packet.get('fromId', 'unknown')
        node_info: dict[str, Any] = packet['decoded']
        self.node_manager.update_node(node_id, {
            'shortName': node_info.get('user', {}).get('shortName', 'unknown'),
            'longName': node_info.get('user', {}).get('longName', 'unknown'),
            'hwModel': node_info.get('user', {}).get('hwModel', 'unknown')
        })
        info_text: str = self.node_manager.format_node_info(node_id)

    async def handle_position_app(self, packet: MeshtasticPacket) -> None:
        position = packet['decoded'].get('position', {})
        node_id = packet.get('fromId', 'unknown')
        self.node_manager.update_node_position(node_id, position)
        position_info = self.node_manager.get_node_position(node_id)

        # Removed automatic location sending to Telegram - users must explicitly request via /location command

    async def handle_telemetry_app(self, packet: MeshtasticPacket) -> None:
        node_id = packet.get('fromId', 'unknown')
        telemetry = packet.get('decoded', {}).get('telemetry', {})
        device_metrics = telemetry.get('deviceMetrics', {})
        self.node_manager.update_node_telemetry(node_id, device_metrics)
        telemetry_info = self.node_manager.get_node_telemetry(node_id)

    async def handle_admin_app(self, packet: dict[str, Any]) -> None:
        admin_message = packet.get('decoded', {}).get('admin', {})
        if 'getRouteReply' in admin_message:
            await self._handle_route_reply(admin_message, packet.get('toId', 'unknown'))
        elif 'deviceMetrics' in admin_message:
            await self._handle_device_metrics(packet.get('fromId', 'unknown'), admin_message['deviceMetrics'])
        elif 'position' in admin_message:
            await self._handle_position(packet.get('fromId', 'unknown'), admin_message['position'])
        else:
            self.logger.warning(f"Received unexpected admin message: {admin_message}")

    async def _handle_route_reply(self, admin_message: dict[str, Any], dest_id: str) -> None:
        route = admin_message['getRouteReply'].get('route', [])
        if route:
            route_str = " → ".join(f"!{node:08x}" for node in route)
            traceroute_result = f"🔍 Traceroute to {dest_id}:\n{route_str}"
        else:
            traceroute_result = f"🔍 Traceroute to {dest_id}: No route found"
        await self.telegram.send_message(escape_markdown(traceroute_result, version=2), parse_mode=ParseMode.MARKDOWN_V2)

    async def _handle_device_metrics(self, node_id: str, device_metrics: dict[str, Any]) -> None:
        self.node_manager.update_node_telemetry(node_id, device_metrics)
        telemetry_info = self.node_manager.get_node_telemetry(node_id)
        await self.telegram.send_or_edit_message('telemetry', node_id, telemetry_info)

    async def _handle_position(self, node_id: str, position: dict[str, Any]) -> None:
        self.node_manager.update_node_position(node_id, position)
        position_info = self.node_manager.get_node_position(node_id)
        await self.telegram.send_or_edit_message('location', node_id, position_info)

    def start_background_tasks(self) -> None:
        self.processing_tasks.append(asyncio.create_task(self.process_pending_acks()))