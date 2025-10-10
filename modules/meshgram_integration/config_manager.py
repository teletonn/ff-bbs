import logging
import re
import shutil
from datetime import datetime
from typing import Any, Optional, List
from pathlib import Path
from modules import settings
from modules import log

class ConfigManager:
    def __init__(self):
        self.config = settings.config
        self.logger = log.logger
        self.config_path = getattr(settings, 'config_file_path', 'config.ini')
        self.backup_dir = Path('config_backups')
        self.backup_dir.mkdir(exist_ok=True)

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        key_parts = key.split('.', 1)
        if len(key_parts) != 2:
            if default is not None:
                return default
            raise KeyError(f"Configuration key '{key}' must be in format 'section.option'")

        section, option = key_parts
        try:
            value = self.config.get(section, option)
            if value == '' and default is not None: # Handle empty string as default if provided
                return default
            return value
        except Exception:
            if default is not None:
                return default
            raise KeyError(f"Configuration key '{key}' not found and no default value provided")

    def get_authorized_users(self) -> List[int]:
        users_str = self.get('telegram.telegram_authorized_users', '')
        if users_str:
            return [int(user.strip()) for user in users_str.split(',') if user.strip().isdigit()]
        return []

    def validate_config(self) -> None:
        required_keys = [
            'telegram.telegram_bot_token',
            'telegram.telegram_chat_id',
        ]
        missing_keys = []
        for key in required_keys:
            try:
                self.get(key)
            except KeyError:
                missing_keys.append(key)

        if missing_keys:
            raise ValueError(f"Missing required configuration: {', '.join(missing_keys)}")

        # Validate telegram_chat_id (should be a valid chat ID)
        try:
            chat_id = self.get('telegram.telegram_chat_id')
            if isinstance(chat_id, str):
                chat_id = int(chat_id)
            if not isinstance(chat_id, int):
                raise ValueError(f"telegram_chat_id must be an integer, got: {chat_id}")

            # Validate chat ID format: negative for groups/channels, positive for private chats
            if chat_id > 0:
                self.logger.warning(f"telegram_chat_id {chat_id} appears to be a private chat ID. For groups/channels, use negative values (e.g., -1001234567890)")
            elif chat_id < -1000000000000:  # Channels start with -100
                self.logger.info(f"telegram_chat_id {chat_id} detected as a channel ID")
            elif chat_id < 0:  # Groups are negative but not starting with -100
                self.logger.info(f"telegram_chat_id {chat_id} detected as a group ID")
            else:
                raise ValueError(f"telegram_chat_id {chat_id} appears to be invalid. Groups/channels should be negative, private chats positive.")

        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid telegram_chat_id configuration: {e}")

        # Validate telegram_default_channel (Meshtastic channel number)
        try:
            default_channel = self.get('telegram.telegram_default_channel', 0)
            if isinstance(default_channel, str):
                default_channel = int(default_channel)
            if not isinstance(default_channel, int) or default_channel < 0:
                raise ValueError(f"telegram_default_channel must be a non-negative integer, got: {default_channel}")
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid telegram_default_channel configuration: {e}")

        # Validate meshtastic_default_node_id if present
        try:
            node_id = self.get('telegram.meshtastic_default_node_id')
            if node_id and not isinstance(node_id, str):
                raise ValueError(f"meshtastic_default_node_id must be a string, got: {node_id}")
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid meshtastic_default_node_id configuration: {e}")

    def create_backup(self, reason: str = "manual_backup") -> str:
        """Create a backup of the current configuration file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"config_{timestamp}_{reason}.ini"
        backup_path = self.backup_dir / backup_filename

        try:
            shutil.copy2(self.config_path, backup_path)
            self.logger.info(f"Configuration backup created: {backup_path}")
            return str(backup_path)
        except Exception as e:
            self.logger.error(f"Failed to create configuration backup: {e}")
            raise

    def rollback_config(self, backup_path: str) -> None:
        """Rollback configuration to a backup file."""
        backup_file = Path(backup_path)
        if not backup_file.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        try:
            shutil.copy2(backup_file, self.config_path)
            self.logger.info(f"Configuration rolled back from: {backup_path}")
            # Reload configuration
            import importlib
            importlib.reload(settings)
            self.config = settings.config
        except Exception as e:
            self.logger.error(f"Failed to rollback configuration: {e}")
            raise

    def list_backups(self) -> list[str]:
        """List all available configuration backups."""
        return [str(f) for f in self.backup_dir.glob("config_*.ini")]

class SensitiveFormatter(logging.Formatter):
    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        super().__init__(fmt, datefmt)
        self.sensitive_patterns = [
            (re.compile(r'(https://api\.telegram\.org/bot)([A-Za-z0-9:_-]{35,})(/\w+)'), r'\1[redacted]\3')
        ]

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        for pattern, replacement in self.sensitive_patterns:
            message = pattern.sub(replacement, message)
        return message

def get_logger(name: str) -> logging.Logger:
    return log.logger