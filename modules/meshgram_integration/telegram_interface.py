import asyncio
from typing import Dict, Any, Optional, Callable, TypedDict, NotRequired
from collections.abc import Awaitable
from telegram import Bot, Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, MessageReactionHandler, filters
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from telegram.error import BadRequest
from modules.meshgram_integration.config_manager import ConfigManager
from modules import log

class CommandData(TypedDict):
    description: str
    handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]

class TelegramInterface:
    def __init__(self, config: ConfigManager) -> None:
        self.config: ConfigManager = config
        self.logger = log.logger
        self.bot: Bot | None = None
        self.application: Application | None = None
        self.message_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._stop_event: asyncio.Event = asyncio.Event()
        self.chat_id: int | None = None
        self.last_messages: Dict[str, int] = {}
        self.user_location_node: Dict[int, str] = {}
        self.commands: Dict[str, CommandData] = {
            'start': {'description': 'Start the bot and see available commands', 'handler': self.start_command},
            'help': {'description': 'Show help message', 'handler': self.help_command},
            'status': {'description': 'Check the current status', 'handler': self.handle_command},
            'bell': {'description': 'Send a bell to the meshtastic user', 'handler': self.handle_command},
            'node': {'description': 'Get information about a specific node', 'handler': self.handle_command},
            'location': {'description': 'Share your location with the Meshtastic network', 'handler': self.handle_command},
            'user': {'description': 'Get information about your Telegram user', 'handler': self.user_command},
        }
        self.is_polling: bool = False

    async def setup(self) -> None:
        self.logger.info("Setting up telegram interface...")
        try:
            token = self.config.get('telegram.telegram_bot_token')
            if not token:
                raise ValueError("Telegram bot token not found in configuration")
            self.bot = Bot(token=token)
            self.application = Application.builder().token(token).build()
            self._setup_handlers()
            await self.bot.set_my_commands([(cmd, data['description']) for cmd, data in self.commands.items()])
            self.chat_id = self.config.get('telegram.telegram_chat_id')
            if not self.chat_id:
                raise ValueError("Telegram chat id not found in configuration")

            # Validate chat accessibility
            try:
                chat = await self.bot.get_chat(self.chat_id)
                self.logger.info(f"Successfully validated chat access: {chat.title or chat.username or 'Private Chat'} (ID: {self.chat_id})")
                if hasattr(chat, 'type'):
                    chat_type = chat.type
                    if chat_type == 'private':
                        self.logger.warning(f"Chat ID {self.chat_id} is a private chat. Ensure this is intentional for your use case.")
                    elif chat_type in ['group', 'supergroup']:
                        self.logger.info(f"Chat ID {self.chat_id} is a {chat_type}. Bot permissions validated.")
                    elif chat_type == 'channel':
                        self.logger.info(f"Chat ID {self.chat_id} is a channel. Ensure bot has posting permissions.")
            except BadRequest as e:
                if "Chat not found" in str(e):
                    raise ValueError(f"Chat with ID {self.chat_id} not found. Ensure the bot is added to the chat and the ID is correct.")
                elif "Not enough rights" in str(e):
                    raise ValueError(f"Bot lacks sufficient permissions in chat {self.chat_id}. Ensure bot is added as admin for groups/channels.")
                else:
                    raise ValueError(f"Cannot access chat {self.chat_id}: {e}")

            self.logger.info("Telegram interface set up successfully")
        except Exception as e:
            self.logger.exception(f"Failed to set up telegram: {e}")
            raise

    def _setup_handlers(self) -> None:
        if self.application is None:
            raise RuntimeError("Application not initialized")
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_telegram_message))
        self.application.add_handler(MessageHandler(filters.LOCATION, self.on_telegram_location_request))
        self.application.add_handler(MessageReactionHandler(self.on_telegram_reaction))
        for command, data in self.commands.items():
            self.application.add_handler(CommandHandler(command, data['handler']))

    async def start_polling(self) -> None:
        if not self.application:
            self.logger.error("Telegram application not initialized")
            return

        self.logger.info("Starting telegram polling...")
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
            self.is_polling = True
            await self._stop_event.wait()
        except Exception as e:
            self.logger.error(f"Error in Telegram polling: {e}", exc_info=True)
        finally:
            await self._shutdown_polling()

    async def _shutdown_polling(self) -> None:
        self.logger.info("Stopping telegram polling...")
        if self.application and self.is_polling:
            try:
                self.is_polling = False
                await self.application.stop()
                await self.application.shutdown()
            except Exception as e:
                self.logger.error(f"Error during Telegram shutdown: {e}", exc_info=True)
        self.logger.info("Telegram polling stopped")

    async def on_telegram_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.effective_user is None:
            return
        await self.message_queue.put({
            'text': update.message.text,
            'sender': update.effective_user.username or update.effective_user.first_name,
            'type': 'telegram',
            'message_id': update.message.message_id,
            'user_id': update.effective_user.id,
            'chat_type': update.message.chat.type
        })


    async def on_telegram_reaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.message.reaction is None or update.effective_user is None:
            return
        self.logger.info(f"Received reaction: {update.message.reaction}")
        if update.message.reply_to_message:
            await self.message_queue.put({
                'type': 'reaction',
                'emoji': update.message.reaction.emoji,
                'user_id': update.effective_user.id,
                'original_message_id': update.message.reply_to_message.message_id
            })

    async def send_or_edit_message(self, message_type: str, node_id: str, content: str) -> None:
        message_key = f"{message_type}:{node_id}"
        if message_key in self.last_messages:
            success = await self.edit_message(self.last_messages[message_key], content)
            if not success:
                # If editing fails, send a new message
                message_id = await self.send_message(content)
                if message_id:
                    self.last_messages[message_key] = message_id
        else:
            message_id = await self.send_message(content)
            if message_id:
                self.last_messages[message_key] = message_id

    async def send_message(self, text: str, disable_notification: bool = False) -> int | None:
        if self.bot is None or self.chat_id is None:
            self.logger.error("Bot or chat_id not initialized")
            return None
        try:
            escaped_text = escape_markdown(text, version=2)
            message = await self.bot.send_message(
                chat_id=self.chat_id,
                disable_notification=disable_notification,
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN_V2,
                text=escaped_text
            )
            self.logger.debug(f"Successfully sent message to Telegram chat {self.chat_id}")
            return message.message_id
        except BadRequest as e:
            if "Chat not found" in str(e):
                self.logger.error(f"Chat not found error - chat_id {self.chat_id} may be incorrect or bot not added to chat")
            elif "Message text is empty" in str(e):
                self.logger.error("Attempted to send empty message to Telegram")
            else:
                self.logger.error(f"BadRequest error sending Telegram message: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to send Telegram message: {e}", exc_info=True)
            return None

    async def send_message_to_chat(self, chat_id: int, text: str, disable_notification: bool = False) -> int | None:
        if self.bot is None:
            self.logger.error("Bot not initialized")
            return None
        try:
            escaped_text = escape_markdown(text, version=2)
            message = await self.bot.send_message(
                chat_id=chat_id,
                disable_notification=disable_notification,
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN_V2,
                text=escaped_text
            )
            self.logger.debug(f"Successfully sent message to Telegram chat {chat_id}")
            return message.message_id
        except BadRequest as e:
            if "Chat not found" in str(e):
                self.logger.error(f"Chat not found error - chat_id {chat_id} may be incorrect")
            elif "Message text is empty" in str(e):
                self.logger.error("Attempted to send empty message to Telegram")
            else:
                self.logger.error(f"BadRequest error sending Telegram message: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to send Telegram message: {e}", exc_info=True)
            return None

    async def edit_message(self, message_id: int, text: str) -> bool:
        if self.bot is None or self.chat_id is None:
            self.logger.error("Bot or chat_id not initialized")
            return False
        try:
            escaped_text = escape_markdown(text, version=2)
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=message_id,
                parse_mode=ParseMode.MARKDOWN_V2,
                text=escaped_text
            )
            return True
        except BadRequest as e:
            if "Message to edit not found" in str(e):
                self.logger.warning(f"Message {message_id} not found for editing. Will send as new message.")
                return False
            else:
                self.logger.error(f"BadRequest error when editing message: {e}", exc_info=True)
                return False
        except Exception as e:
            self.logger.error(f"Failed to edit Telegram message: {e}", exc_info=True)
            return False

    def is_user_authorized(self, user_id: int) -> bool:
        authorized_users = self.config.get_authorized_users()
        return not authorized_users or user_id in authorized_users

    async def add_reaction(self, message_id: int, emoji: str) -> None:
        if self.bot is None or self.chat_id is None:
            self.logger.error("Bot or chat_id not initialized")
            return
        try:
            await self.bot.set_message_reaction(
                chat_id=self.chat_id,
                message_id=message_id,
                reaction=[emoji]
            )
        except Exception as e:
            self.logger.error(f"Failed to add reaction to Telegram message: {e}", exc_info=True)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.help_command(update, context)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        help_text = "📚 Available commands:\n\n"
        help_text += "\n".join(f"/{command} - {data['description']}" for command, data in self.commands.items())
        escaped_help_text = escape_markdown(help_text, version=2)
        await update.message.reply_text(escaped_help_text, parse_mode=ParseMode.MARKDOWN_V2)

    async def user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.effective_user is None:
            return
        user = update.effective_user
        user_info = (
            f"🆔 ID: {user.id}\n"
            f"👤 Username: @{user.username}\n"
            f"📛 Name: {user.full_name}\n"
            f"🤖 Is Bot: {'Yes' if user.is_bot else 'No'}"
        )
        escaped_user_info = escape_markdown(user_info, version=2)
        await update.message.reply_text(escaped_user_info, parse_mode=ParseMode.MARKDOWN_V2)

    async def handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.effective_user is None:
            return
        command = update.message.text.split()[0][1:].partition('@')[0]
        args = context.args or []
        user_id = update.effective_user.id

        if not self.is_user_authorized(user_id) and command not in ['start', 'help', 'user']:
            await update.message.reply_text(
                escape_markdown("You are not authorized to use this command.", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        # Handle location command specially - it needs access to user's location
        if command == 'location':
            await self.handle_location_command(update, context)
            return

        await self.message_queue.put({
            'type': 'command',
            'command': command,
            'args': args,
            'user_id': user_id,
            'update': update
        })

    async def handle_location_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the location command by requesting user's location."""
        if update.message is None or update.effective_user is None:
            return

        user_id = update.effective_user.id
        if not self.is_user_authorized(user_id):
            await update.message.reply_text(
                escape_markdown("You are not authorized to use this command.", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        # Parse args for node_id
        args = context.args or []
        node_id = args[0] if args else self.config.get('telegram.meshtastic_default_node_id') or "^all"

        # Store node_id for this user
        self.user_location_node[user_id] = node_id

        # Create a location request button
        keyboard = [[KeyboardButton("📍 Share Location", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(
            escape_markdown("Please share your location to send it to the Meshtastic network:", version=2),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )

    async def on_telegram_location_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle location requests from the location button."""
        if update.message is None or update.message.location is None or update.effective_user is None:
            return

        # Check if user is authorized
        user_id = update.effective_user.id
        if not self.is_user_authorized(user_id):
            await update.message.reply_text(
                escape_markdown("You are not authorized to share locations.", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        # Get node_id for this user
        node_id = self.user_location_node.pop(user_id, self.config.get('telegram.meshtastic_default_node_id') or "^all")

        # Send location data to message processor for handling
        await self.message_queue.put({
            'location': {
                'latitude': update.message.location.latitude,
                'longitude': update.message.location.longitude,
                'accuracy': getattr(update.message.location, 'horizontal_accuracy', None)
            },
            'sender': update.effective_user.username or update.effective_user.first_name,
            'type': 'location_request',
            'message_id': update.message.message_id,
            'user_id': user_id,
            'node_id': node_id
        })

    async def close(self) -> None:
        self.logger.info("Stopping telegram interface...")
        self._stop_event.set()
        await self._shutdown_polling()
        self.logger.info("Telegram interface stopped.")