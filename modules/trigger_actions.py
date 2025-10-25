#!/usr/bin/env python3
"""
Trigger Actions Module

Handles execution of different trigger actions for zone events.
"""

import logging
import json
import asyncio
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

# Import send_message later to avoid circular import
from webui.db_handler import get_db_connection

logger = logging.getLogger(__name__)

class TriggerAction(ABC):
    """Base class for trigger actions."""

    def __init__(self, action_payload: str):
        """
        Initialize the action.

        Args:
            action_payload: JSON string containing action configuration
        """
        self.action_payload = action_payload
        self.config = self._parse_payload()

    def _parse_payload(self) -> Dict[str, Any]:
        """Parse the action payload JSON."""
        try:
            return json.loads(self.action_payload) if self.action_payload else {}
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in action payload: {self.action_payload}")
            return {}

    @abstractmethod
    async def execute(self, event_data: Dict[str, Any]) -> bool:
        """
        Execute the action.

        Args:
            event_data: Event data containing trigger, node, zone, position info

        Returns:
            True if action executed successfully
        """
        pass

class MessageAction(TriggerAction):
    """Action that sends a message."""

    async def execute(self, event_data: Dict[str, Any]) -> bool:
        """Send a message to specified channel or DM."""
        try:
            # Import send_message here to avoid circular import
            from modules.system import send_message

            channel = self.config.get('channel', 0)
            message = self.config.get('message', '')

            # Replace placeholders in message
            message = self._format_message(message, event_data)

            node_id = event_data.get('node_id', '')
            if channel == 0:
                # DM to the node that triggered
                target_node_id = int(node_id) if node_id.isdigit() else 0
                if target_node_id:
                    success = send_message(message, 0, target_node_id, 1)  # Default to interface 1
                    return success
            else:
                # Broadcast to channel
                success = send_message(message, int(channel), 0, 1)  # Default to interface 1
                return success

            return False

        except Exception as e:
            logger.error(f"Failed to execute message action: {e}")
            return False

    def _format_message(self, message: str, event_data: Dict[str, Any]) -> str:
        """Format message with event data placeholders."""
        zone = event_data.get('zone')
        trigger = event_data.get('trigger')
        node_id = event_data.get('node_id', '')
        position = event_data.get('position')

        replacements = {
            '{zone_name}': zone.name if zone else 'Unknown Zone',
            '{node_id}': node_id,
            '{event_type}': event_data.get('event_type', ''),
            '{latitude}': f"{position.latitude:.6f}" if position else 'N/A',
            '{longitude}': f"{position.longitude:.6f}" if position else 'N/A',
            '{altitude}': f"{position.altitude:.0f}m" if position and position.altitude else 'N/A',
            '{trigger_name}': trigger.name if trigger else 'Unknown Trigger'
        }

        for placeholder, value in replacements.items():
            message = message.replace(placeholder, str(value))

        return message

class AlertAction(TriggerAction):
    """Action that creates an alert in the system."""

    async def execute(self, event_data: Dict[str, Any]) -> bool:
        """Create an alert in the alerts table."""
        try:
            severity = self.config.get('severity', 'info')
            message = self.config.get('message', 'Zone trigger activated')

            # Format message
            message = self._format_message(message, event_data)

            node_id = event_data.get('node_id', '')
            zone = event_data.get('zone')

            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO alerts (type, message, severity, node_id, timestamp)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, ('zone_trigger', message, severity, node_id))

                conn.commit()
                logger.info(f"Created alert for zone trigger: {message}")
                return True

            except Exception as e:
                logger.error(f"Failed to create alert: {e}")
                return False
            finally:
                conn.close()

        except Exception as e:
            logger.error(f"Failed to execute alert action: {e}")
            return False

    def _format_message(self, message: str, event_data: Dict[str, Any]) -> str:
        """Format alert message with event data."""
        zone = event_data.get('zone')
        trigger = event_data.get('trigger')
        node_id = event_data.get('node_id', '')

        replacements = {
            '{zone_name}': zone.name if zone else 'Unknown Zone',
            '{node_id}': node_id,
            '{event_type}': event_data.get('event_type', ''),
            '{trigger_name}': trigger.name if trigger else 'Unknown Trigger'
        }

        for placeholder, value in replacements.items():
            message = message.replace(placeholder, str(value))

        return message

class CommandAction(TriggerAction):
    """Action that executes a system command."""

    async def execute(self, event_data: Dict[str, Any]) -> bool:
        """Execute a system command."""
        try:
            command = self.config.get('command', '')
            if not command:
                logger.error("No command specified in command action")
                return False

            # Format command with event data
            command = self._format_command(command, event_data)

            # Execute command asynchronously
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"Command executed successfully: {command}")
                if stdout:
                    logger.debug(f"Command output: {stdout.decode().strip()}")
                return True
            else:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                logger.error(f"Command failed: {command}, error: {error_msg}")
                return False

        except Exception as e:
            logger.error(f"Failed to execute command action: {e}")
            return False

    def _format_command(self, command: str, event_data: Dict[str, Any]) -> str:
        """Format command with event data placeholders."""
        zone = event_data.get('zone')
        trigger = event_data.get('trigger')
        node_id = event_data.get('node_id', '')
        position = event_data.get('position')

        replacements = {
            '{zone_name}': zone.name if zone else 'Unknown Zone',
            '{node_id}': node_id,
            '{event_type}': event_data.get('event_type', ''),
            '{latitude}': f"{position.latitude:.6f}" if position else 'N/A',
            '{longitude}': f"{position.longitude:.6f}" if position else 'N/A',
            '{altitude}': f"{position.altitude:.0f}" if position and position.altitude else 'N/A',
            '{trigger_name}': trigger.name if trigger else 'Unknown Trigger'
        }

        for placeholder, value in replacements.items():
            command = command.replace(placeholder, str(value))

        return command

class TelegramAction(TriggerAction):
    """Action that sends a message via Telegram."""

    async def execute(self, event_data: Dict[str, Any]) -> bool:
        """Send a message via Telegram integration."""
        try:
            # Import telegram interface if available
            try:
                from modules.meshgram_integration.telegram_interface import send_telegram_message
            except ImportError:
                logger.error("Telegram integration not available")
                return False

            chat_id = self.config.get('chat_id')
            message = self.config.get('message', '')

            if not chat_id or not message:
                logger.error("Missing chat_id or message in Telegram action")
                return False

            # Format message
            message = self._format_message(message, event_data)

            # Send via Telegram
            success = await send_telegram_message(chat_id, message)
            if success:
                logger.info(f"Telegram message sent to chat {chat_id}")
            return success

        except Exception as e:
            logger.error(f"Failed to execute Telegram action: {e}")
            return False

    def _format_message(self, message: str, event_data: Dict[str, Any]) -> str:
        """Format Telegram message with event data."""
        zone = event_data.get('zone')
        trigger = event_data.get('trigger')
        node_id = event_data.get('node_id', '')

        replacements = {
            '{zone_name}': zone.name if zone else 'Unknown Zone',
            '{node_id}': node_id,
            '{event_type}': event_data.get('event_type', ''),
            '{trigger_name}': trigger.name if trigger else 'Unknown Trigger'
        }

        for placeholder, value in replacements.items():
            message = message.replace(placeholder, str(value))

        return message

class ActionExecutor:
    """Executes trigger actions based on action type."""

    def __init__(self):
        self.action_types = {
            'message': MessageAction,
            'alert': AlertAction,
            'command': CommandAction,
            'telegram': TelegramAction
        }

    async def execute_action(self, action_type: str, action_payload: str, event_data: Dict[str, Any]) -> bool:
        """
        Execute an action of the specified type.

        Args:
            action_type: Type of action to execute
            action_payload: JSON payload for the action
            event_data: Event data for formatting

        Returns:
            True if action executed successfully
        """
        try:
            action_class = self.action_types.get(action_type)
            if not action_class:
                logger.error(f"Unknown action type: {action_type}")
                return False

            action = action_class(action_payload)
            return await action.execute(event_data)

        except Exception as e:
            logger.error(f"Failed to execute action {action_type}: {e}")
            return False

    def get_supported_action_types(self) -> list:
        """Get list of supported action types."""
        return list(self.action_types.keys())

# Global action executor instance
action_executor = ActionExecutor()