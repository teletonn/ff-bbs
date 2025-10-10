#!/usr/bin/env python3
"""
Test script for Telegram bot integration functionality.
Tests the integration without requiring actual hardware or external services.
"""

import asyncio
import sys
import os
import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import configparser
from datetime import datetime, timezone

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestTelegramIntegration(unittest.TestCase):
    """Test cases for Telegram bot integration."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary config file for testing
        self.temp_config = tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False)
        self.temp_config.write("""
[interface]
type = tcp
hostname = 192.168.1.245

[telegram]
telegram_bot_token = 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
telegram_chat_id = -1001234567890
telegram_authorized_users = 123456789,987654321
meshtastic_default_node_id = !4e1a832c

[general]
respond_by_dm_only = True
defaultChannel = 3
""")
        self.temp_config.close()

        # Mock the config file path
        self.original_config = None

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_config.name):
            os.unlink(self.temp_config.name)

    def test_config_loading(self):
        """Test that configuration loads correctly."""
        print("Testing configuration loading...")

        # Test config file parsing
        config = configparser.ConfigParser()
        config.read(self.temp_config.name)

        # Verify telegram section exists
        self.assertIn('telegram', config.sections())
        self.assertEqual(config.get('telegram', 'telegram_bot_token'), '123456789:ABCdefGHIjklMNOpqrsTUVwxyz')
        self.assertEqual(config.get('telegram', 'telegram_chat_id'), '-1001234567890')
        self.assertEqual(config.get('telegram', 'telegram_authorized_users'), '123456789,987654321')

        print("✓ Configuration loading test passed")

    def test_module_imports(self):
        """Test that all required modules can be imported."""
        print("Testing module imports...")

        try:
            # Test main integration modules
            from modules.meshgram_integration.config_manager import ConfigManager
            from modules.meshgram_integration.meshgram import MeshgramIntegration
            from modules.meshgram_integration.telegram_interface import TelegramInterface
            from modules.meshgram_integration.message_processor import MessageProcessor
            from modules.meshgram_integration.meshtastic_interface import MeshtasticInterface
            from modules.meshgram_integration.node_manager import NodeManager

            print("✓ All integration modules imported successfully")

            # Test that classes can be instantiated (without full initialization)
            config_manager = ConfigManager()
            self.assertIsNotNone(config_manager)

            print("✓ ConfigManager instantiated successfully")

        except ImportError as e:
            self.fail(f"Failed to import required modules: {e}")

    def test_config_manager_functionality(self):
        """Test ConfigManager functionality."""
        print("Testing ConfigManager functionality...")

        from modules.meshgram_integration.config_manager import ConfigManager

        # Mock settings module
        with patch('modules.meshgram_integration.config_manager.settings') as mock_settings:
            mock_settings.config = configparser.ConfigParser()
            mock_settings.config.read(self.temp_config.name)

            config_manager = ConfigManager()

            # Test getting telegram configuration
            token = config_manager.get('telegram.telegram_bot_token')
            self.assertEqual(token, '123456789:ABCdefGHIjklMNOpqrsTUVwxyz')

            chat_id = config_manager.get('telegram.telegram_chat_id')
            self.assertEqual(chat_id, '-1001234567890')

            # Test authorized users
            authorized_users = config_manager.get_authorized_users()
            self.assertEqual(authorized_users, [123456789, 987654321])

            print("✓ ConfigManager functionality test passed")

    def test_telegram_interface_commands(self):
        """Test Telegram interface command definitions."""
        print("Testing Telegram interface commands...")

        from modules.meshgram_integration.telegram_interface import TelegramInterface
        from modules.meshgram_integration.config_manager import ConfigManager

        # Mock config manager
        mock_config = Mock(spec=ConfigManager)
        mock_config.get.side_effect = lambda key: {
            'telegram.telegram_bot_token': '123456789:ABCdefGHIjklMNOpqrsTUVwxyz',
            'telegram.telegram_chat_id': -1001234567890
        }.get(key)

        telegram_interface = TelegramInterface(mock_config)

        # Test command definitions
        expected_commands = ['start', 'help', 'status', 'bell', 'node', 'user']
        self.assertEqual(list(telegram_interface.commands.keys()), expected_commands)

        # Test command descriptions
        for command in expected_commands:
            self.assertIn(command, telegram_interface.commands)
            self.assertIn('description', telegram_interface.commands[command])
            self.assertIn('handler', telegram_interface.commands[command])

        print("✓ Telegram interface commands test passed")

    def test_message_processor_commands(self):
        """Test MessageProcessor command handlers."""
        print("Testing MessageProcessor command handlers...")

        from modules.meshgram_integration.message_processor import MessageProcessor
        from modules.meshgram_integration.telegram_interface import TelegramInterface
        from modules.meshgram_integration.meshtastic_interface import MeshtasticInterface
        from modules.meshgram_integration.config_manager import ConfigManager
        from modules.meshgram_integration.node_manager import NodeManager

        # Create mock objects
        mock_config = Mock(spec=ConfigManager)
        mock_telegram = Mock(spec=TelegramInterface)
        mock_meshtastic = Mock(spec=MeshtasticInterface)
        mock_node_manager = Mock(spec=NodeManager)

        mock_meshtastic.node_manager = mock_node_manager

        # Create message processor
        processor = MessageProcessor(mock_meshtastic, mock_telegram, mock_config)

        # Test that command handler methods exist
        command_methods = [
            'cmd_start', 'cmd_help', 'cmd_status', 'cmd_bell',
            'cmd_node', 'cmd_user'
        ]

        for method_name in command_methods:
            self.assertTrue(hasattr(processor, method_name))
            self.assertTrue(callable(getattr(processor, method_name)))

        print("✓ MessageProcessor command handlers test passed")

    def test_command_handler_logic(self):
        """Test command handler logic without external dependencies."""
        print("Testing command handler logic...")

        from modules.meshgram_integration.message_processor import MessageProcessor
        from modules.meshgram_integration.telegram_interface import TelegramInterface
        from modules.meshgram_integration.meshtastic_interface import MeshtasticInterface
        from modules.meshgram_integration.config_manager import ConfigManager
        from modules.meshgram_integration.node_manager import NodeManager
        from telegram import Update, User, Message
        from unittest.mock import AsyncMock

        # Create mock objects
        mock_config = Mock(spec=ConfigManager)
        mock_telegram = Mock(spec=TelegramInterface)
        mock_meshtastic = Mock(spec=MeshtasticInterface)
        mock_node_manager = Mock(spec=NodeManager)

        mock_meshtastic.node_manager = mock_node_manager
        mock_meshtastic.send_bell = AsyncMock()
        mock_node_manager.format_node_info = Mock(return_value="Node info")
        mock_node_manager.get_node_telemetry = Mock(return_value="Telemetry info")
        mock_node_manager.get_node_position = Mock(return_value="Position info")
        mock_node_manager.format_node_routing = Mock(return_value="Routing info")
        mock_node_manager.format_node_neighbors = Mock(return_value="Neighbors info")
        mock_node_manager.get_node_sensor_info = Mock(return_value="Sensor info")

        # Create message processor
        processor = MessageProcessor(mock_meshtastic, mock_telegram, mock_config)

        # Test start command
        mock_update = Mock(spec=Update)
        mock_update.message.reply_text = AsyncMock()

        async def test_start_command():
            await processor.cmd_start([], 123456789, mock_update)
            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            self.assertIn("Welcome to Meshgram", call_args)

        asyncio.run(test_start_command())

        # Test help command
        mock_update.message.reply_text.reset_mock()
        async def test_help_command():
            await processor.cmd_help([], 123456789, mock_update)
            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            self.assertIn("/start", call_args)
            self.assertIn("/help", call_args)
            self.assertIn("/status", call_args)

        asyncio.run(test_help_command())

        # Test user command
        mock_update.message.reply_text.reset_mock()
        mock_user = Mock(spec=User)
        mock_user.id = 123456789
        mock_user.username = "testuser"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.is_bot = False
        mock_update.effective_user = mock_user

        async def test_user_command():
            await processor.cmd_user([], 123456789, mock_update)
            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            self.assertIn("123456789", call_args)
            self.assertIn("testuser", call_args)

        asyncio.run(test_user_command())

        print("✓ Command handler logic test passed")

    def test_integration_initialization(self):
        """Test that integration can be initialized without external services."""
        print("Testing integration initialization...")

        from modules.meshgram_integration.meshgram import MeshgramIntegration
        from modules.meshgram_integration.config_manager import ConfigManager

        # Mock the config manager to avoid file dependencies
        with patch('modules.meshgram_integration.config_manager.settings') as mock_settings:
            mock_settings.config = configparser.ConfigParser()
            mock_settings.config.read(self.temp_config.name)

            # Mock meshtastic interface
            mock_meshtastic_interface = Mock()

            # Create integration instance
            integration = MeshgramIntegration(mock_meshtastic_interface)

            # Test that integration is not enabled without proper config
            # Create integration with no config to test disabled state
            integration_no_config = MeshgramIntegration(mock_meshtastic_interface)
            integration_no_config.config.get = Mock(side_effect=KeyError("Configuration key 'telegram.telegram_bot_token' not found and no default value provided"))
            self.assertFalse(integration_no_config.is_enabled())

            # Mock config to return valid token
            integration.config.get = Mock(side_effect=lambda key: {
                'telegram.telegram_bot_token': '123456789:ABCdefGHIjklMNOpqrsTUVwxyz',
                'telegram.telegram_chat_id': -1001234567890,
                'telegram.telegram_authorized_users': '123456789,987654321'
            }.get(key, ''))

            # Test that integration is enabled with proper config
            self.assertTrue(integration.is_enabled())

            print("✓ Integration initialization test passed")

    def test_main_bot_integration(self):
        """Test that main bot file properly handles Telegram integration."""
        print("Testing main bot integration...")

        # Check that mesh_bot.py has the necessary imports and initialization code
        with open('mesh_bot.py', 'r') as f:
            content = f.read()

        # Verify that Telegram integration code is present
        self.assertIn('create_meshgram_integration', content)
        self.assertIn('telegram_bot_token', content)
        self.assertIn('telegram_integration', content)

        print("✓ Main bot integration test passed")

    def test_requirements_satisfied(self):
        """Test that all required dependencies are in requirements.txt."""
        print("Testing requirements...")

        with open('requirements.txt', 'r') as f:
            requirements_content = f.read()

        required_packages = [
            'meshtastic',
            'python-telegram-bot',
            'envyaml'
        ]

        for package in required_packages:
            self.assertIn(package, requirements_content,
                         f"Required package '{package}' not found in requirements.txt")

        print("✓ Requirements test passed")

def run_tests():
    """Run all tests and report results."""
    print("Starting Telegram Integration Tests...")
    print("=" * 50)

    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestTelegramIntegration)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("=" * 50)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")

    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")

    if result.failures or result.errors:
        print("\n❌ Some tests failed")
        return False
    else:
        print("\n✅ All tests passed!")
        return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)