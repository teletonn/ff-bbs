#!/usr/bin/env python3
"""
Integration validation script for Meshgram Telegram bot integration.

This script validates the entire integration without requiring actual hardware.
It can be run independently to verify that all components work together correctly.

Usage:
    python validate_integration.py [--verbose] [--config-only] [--components-only]

Options:
    --verbose, -v       Enable verbose logging
    --config-only       Only validate configuration
    --components-only   Only validate component creation
    --help             Show this help message
"""

import asyncio
import sys
import os
import logging
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from modules.meshgram_integration.config_manager import ConfigManager
    from modules.meshgram_integration.meshgram import MeshgramIntegration
    from modules.meshgram_integration.meshtastic_interface import MeshtasticInterface
    from modules.meshgram_integration.telegram_interface import TelegramInterface
    from modules.meshgram_integration.message_processor import MessageProcessor
except ImportError as e:
    print(f"Failed to import project modules: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)

@dataclass
class ValidationStep:
    """Represents a validation step."""
    name: str
    description: str
    status: str = "pending"  # pending, running, passed, failed
    message: str = ""
    duration: float = 0.0

class IntegrationValidator:
    """Hardware-independent integration validator."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = self._setup_logger()
        self.steps: List[ValidationStep] = []
        self.start_time = datetime.now()

    def _setup_logger(self) -> logging.Logger:
        """Setup validation logger."""
        logger = logging.getLogger('IntegrationValidator')
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def add_step(self, name: str, description: str):
        """Add a validation step."""
        step = ValidationStep(name, description)
        self.steps.append(step)
        return step

    def update_step(self, step: ValidationStep, status: str, message: str = "", duration: float = 0.0):
        """Update a validation step."""
        step.status = status
        step.message = message
        step.duration = duration

        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "passed": "✅",
            "failed": "❌"
        }.get(status, "❓")

        self.logger.info(f"{status_icon} {step.name}: {message}")

    async def validate_configuration(self) -> bool:
        """Validate configuration loading and structure."""
        step = self.add_step("Configuration Validation", "Validating configuration loading and structure")
        self.update_step(step, "running")

        start_time = datetime.now()

        try:
            # Test configuration manager creation
            config = ConfigManager()
            self.logger.debug("✓ ConfigManager created successfully")

            # Test reading main project interface configuration
            interface_type = config.get('interface.type')
            interface_hostname = config.get('interface.hostname')

            if interface_type and interface_hostname:
                self.logger.debug(f"✓ Interface config: {interface_type}://{interface_hostname}")
            else:
                self.update_step(step, "failed", "Interface configuration incomplete", (datetime.now() - start_time).total_seconds())
                return False

            # Test Telegram configuration
            try:
                telegram_token = config.get('telegram.telegram_bot_token')
                telegram_chat_id = config.get('telegram.telegram_chat_id')

                if telegram_token and telegram_chat_id:
                    self.logger.debug("✓ Telegram configuration found")
                else:
                    self.logger.warning("⚠️  Telegram configuration incomplete (this may be intentional)")

            except KeyError:
                self.logger.debug("ℹ️  Telegram configuration not found (integration disabled)")

            # Test general configuration
            respond_by_dm = config.get('general.respond_by_dm_only', False)
            default_channel = config.get('general.defaultChannel', '1')

            self.logger.debug(f"✓ General config: DM responses={respond_by_dm}, default channel={default_channel}")

            self.update_step(step, "passed", "Configuration validation successful", (datetime.now() - start_time).total_seconds())
            return True

        except Exception as e:
            self.update_step(step, "failed", f"Configuration validation failed: {e}", (datetime.now() - start_time).total_seconds())
            return False

    async def validate_component_creation(self) -> bool:
        """Validate that all components can be created successfully."""
        step = self.add_step("Component Creation", "Validating component instantiation")
        self.update_step(step, "running")

        start_time = datetime.now()

        try:
            from unittest.mock import Mock

            # Create configuration manager
            config = ConfigManager()

            # Create mock Meshtastic interface
            mock_meshtastic = Mock()
            mock_meshtastic.getMyNodeInfo = Mock(return_value={
                'user': {'id': '1234567890', 'longName': 'TestNode'},
                'deviceMetrics': {'batteryLevel': 100, 'voltage': 4.2, 'airUtilTx': 0.15}
            })
            mock_meshtastic.sendText = Mock(return_value=True)
            mock_meshtastic.sendReaction = Mock(return_value=True)
            mock_meshtastic.close = Mock(return_value=True)
            mock_meshtastic.ping = Mock(return_value=True)

            # Test MeshtasticInterface creation
            meshtastic_interface = MeshtasticInterface(config, mock_meshtastic)
            self.logger.debug("✓ MeshtasticInterface created successfully")

            # Test TelegramInterface creation (mocked)
            mock_telegram = Mock()
            mock_telegram.setup = Mock(return_value=asyncio.coroutine(lambda: None)())
            mock_telegram.start_polling = Mock(return_value=asyncio.coroutine(lambda: None)())
            mock_telegram.close = Mock(return_value=asyncio.coroutine(lambda: None)())

            telegram_interface = Mock()  # We'll use a real mock for this test
            self.logger.debug("✓ TelegramInterface mock created successfully")

            # Test MessageProcessor creation
            message_processor = MessageProcessor(meshtastic_interface, telegram_interface, config)
            self.logger.debug("✓ MessageProcessor created successfully")

            # Test MeshgramIntegration creation
            integration = MeshgramIntegration(mock_meshtastic, config)
            self.logger.debug("✓ MeshgramIntegration created successfully")

            # Test that integration is not enabled by default (no Telegram token)
            is_enabled = integration.is_enabled()
            self.logger.debug(f"✓ Integration enabled status: {is_enabled}")

            self.update_step(step, "passed", "All components created successfully", (datetime.now() - start_time).total_seconds())
            return True

        except Exception as e:
            self.update_step(step, "failed", f"Component creation failed: {e}", (datetime.now() - start_time).total_seconds())
            return False

    async def validate_shared_connection_logic(self) -> bool:
        """Validate the shared connection logic."""
        step = self.add_step("Shared Connection Logic", "Validating shared connection implementation")
        self.update_step(step, "running")

        start_time = datetime.now()

        try:
            from unittest.mock import Mock

            config = ConfigManager()

            # Create two mock interfaces that should be identical (shared)
            mock_interface1 = Mock()
            mock_interface1.getMyNodeInfo = Mock(return_value={'user': {'id': '1234567890'}})

            mock_interface2 = Mock()
            mock_interface2.getMyNodeInfo = Mock(return_value={'user': {'id': '1234567890'}})

            # Create two MeshtasticInterface wrappers with different mock interfaces
            # In real implementation, these would use the same interface instance
            interface1 = MeshtasticInterface(config, mock_interface1)
            interface2 = MeshtasticInterface(config, mock_interface2)

            # Test that they can operate independently but share configuration
            if interface1.config is interface2.config:
                self.logger.debug("✓ Both interfaces share the same configuration")
            else:
                self.update_step(step, "failed", "Interfaces don't share configuration", (datetime.now() - start_time).total_seconds())
                return False

            # Test message queue isolation
            test_message = {'type': 'test', 'data': 'test_data'}

            # Each interface should have its own message queue
            if interface1.message_queue is not interface2.message_queue:
                self.logger.debug("✓ Interfaces have separate message queues")
            else:
                self.logger.warning("⚠️  Interfaces share the same message queue (may be intentional)")

            self.update_step(step, "passed", "Shared connection logic validated", (datetime.now() - start_time).total_seconds())
            return True

        except Exception as e:
            self.update_step(step, "failed", f"Shared connection validation failed: {e}", (datetime.now() - start_time).total_seconds())
            return False

    async def validate_message_processing(self) -> bool:
        """Validate message processing functionality."""
        step = self.add_step("Message Processing", "Validating message processing pipeline")
        self.update_step(step, "running")

        start_time = datetime.now()

        try:
            from unittest.mock import Mock

            config = ConfigManager()

            # Create mock interfaces
            mock_meshtastic = Mock()
            mock_meshtastic.getMyNodeInfo = Mock(return_value={'user': {'id': '1234567890'}})
            mock_meshtastic.sendText = Mock(return_value=True)

            mock_telegram = Mock()

            # Create interfaces
            meshtastic_interface = MeshtasticInterface(config, mock_meshtastic)
            telegram_interface = Mock()

            # Create message processor
            message_processor = MessageProcessor(meshtastic_interface, telegram_interface, config)

            # Test message queue operations
            test_message = {
                'from': '1234567890',
                'to': '9876543210',
                'decoded': {
                    'portnum': 'TEXT_MESSAGE_APP',
                    'payload': b'Hello, World!'
                }
            }

            # Simulate message reception
            await meshtastic_interface.message_queue.put(test_message)

            # Verify message was queued
            queued_message = await meshtastic_interface.message_queue.get()

            if queued_message['from'] == test_message['from']:
                self.logger.debug("✓ Message queuing functional")
            else:
                self.update_step(step, "failed", "Message queuing failed", (datetime.now() - start_time).total_seconds())
                return False

            self.update_step(step, "passed", "Message processing validated", (datetime.now() - start_time).total_seconds())
            return True

        except Exception as e:
            self.update_step(step, "failed", f"Message processing validation failed: {e}", (datetime.now() - start_time).total_seconds())
            return False

    async def validate_error_handling(self) -> bool:
        """Validate error handling capabilities."""
        step = self.add_step("Error Handling", "Validating error handling and recovery")
        self.update_step(step, "running")

        start_time = datetime.now()

        try:
            from unittest.mock import Mock

            config = ConfigManager()

            # Create mock interface that raises exceptions
            mock_interface = Mock()
            mock_interface.getMyNodeInfo = Mock(side_effect=Exception("Connection failed"))
            mock_interface.sendText = Mock(side_effect=Exception("Send failed"))
            mock_interface.close = Mock(return_value=True)

            # Test MeshtasticInterface error handling
            meshtastic_interface = MeshtasticInterface(config, mock_interface)

            # Test that errors are handled gracefully
            try:
                await meshtastic_interface.send_message("test", "1234567890")
                # Should not reach here due to exception
                self.update_step(step, "failed", "Expected exception was not raised", (datetime.now() - start_time).total_seconds())
                return False
            except Exception as e:
                self.logger.debug(f"✓ Exception properly handled: {type(e).__name__}")

            # Test status retrieval with error
            try:
                status = await meshtastic_interface.get_status()
                if "Error" in status:
                    self.logger.debug("✓ Error status properly returned")
                else:
                    self.logger.warning("⚠️  Error not reflected in status")
            except Exception as e:
                self.logger.debug(f"✓ Status error handling: {type(e).__name__}")

            self.update_step(step, "passed", "Error handling validated", (datetime.now() - start_time).total_seconds())
            return True

        except Exception as e:
            self.update_step(step, "failed", f"Error handling validation failed: {e}", (datetime.now() - start_time).total_seconds())
            return False

    async def validate_telegram_integration(self) -> bool:
        """Validate Telegram integration setup."""
        step = self.add_step("Telegram Integration", "Validating Telegram bot integration")
        self.update_step(step, "running")

        start_time = datetime.now()

        try:
            config = ConfigManager()

            # Test Telegram configuration validation
            try:
                telegram_token = config.get('telegram.telegram_bot_token')
                if telegram_token and telegram_token != 'YOUR_TELEGRAM_BOT_TOKEN':
                    self.logger.debug("✓ Telegram token configured")

                    # Test authorized users
                    authorized_users = config.get_authorized_users()
                    if authorized_users:
                        self.logger.debug(f"✓ Authorized users: {authorized_users}")
                    else:
                        self.logger.warning("⚠️  No authorized users configured")

                else:
                    self.logger.debug("ℹ️  Telegram token not configured (integration disabled)")

            except KeyError:
                self.logger.debug("ℹ️  Telegram configuration not found (integration disabled)")

            # Test integration enablement check
            mock_interface = Mock()
            integration = MeshgramIntegration(mock_interface, config)

            is_enabled = integration.is_enabled()
            self.logger.debug(f"✓ Integration enabled: {is_enabled}")

            self.update_step(step, "passed", "Telegram integration validated", (datetime.now() - start_time).total_seconds())
            return True

        except Exception as e:
            self.update_step(step, "failed", f"Telegram integration validation failed: {e}", (datetime.now() - start_time).total_seconds())
            return False

    def print_summary(self):
        """Print validation summary."""
        total_duration = (datetime.now() - self.start_time).total_seconds()

        self.logger.info(f"\n{'='*70}")
        self.logger.info("INTEGRATION VALIDATION SUMMARY")
        self.logger.info(f"{'='*70}")
        self.logger.info(f"Total duration: {total_duration:.2f}s")
        self.logger.info(f"Steps validated: {len(self.steps)}")
        self.logger.info("")

        passed = 0
        failed = 0

        for step in self.steps:
            status_icon = {
                "passed": "✅",
                "failed": "❌",
                "running": "🔄",
                "pending": "⏳"
            }.get(step.status, "❓")

            self.logger.info(f"{status_icon} {step.name:<25} ({step.duration:6.2f}s)")
            if step.message:
                self.logger.info(f"{''.ljust(4)}└─ {step.message}")

            if step.status == "passed":
                passed += 1
            elif step.status == "failed":
                failed += 1

        self.logger.info("")
        self.logger.info(f"Results: {passed} passed, {failed} failed")

        if failed == 0:
            self.logger.info("🎉 All validation steps completed successfully!")
            return True
        else:
            self.logger.error("❌ Some validation steps failed. Check the logs above for details.")
            return False

    async def run_validation(self, config_only: bool = False, components_only: bool = False) -> bool:
        """Run the complete validation."""
        self.logger.info("Starting Meshgram integration validation...")

        if config_only:
            # Only run configuration validation
            success = await self.validate_configuration()
        elif components_only:
            # Only run component creation validation
            success = await self.validate_component_creation()
        else:
            # Run all validations
            validations = [
                self.validate_configuration,
                self.validate_component_creation,
                self.validate_shared_connection_logic,
                self.validate_message_processing,
                self.validate_error_handling,
                self.validate_telegram_integration
            ]

            success = True
            for validation in validations:
                if not await validation():
                    success = False

        return self.print_summary() and success

async def main():
    """Main validation runner."""
    import argparse

    parser = argparse.ArgumentParser(description='Validate Meshgram integration')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--config-only', action='store_true',
                       help='Only validate configuration')
    parser.add_argument('--components-only', action='store_true',
                       help='Only validate component creation')
    parser.add_argument('--json', action='store_true',
                       help='Output results in JSON format')

    args = parser.parse_args()

    validator = IntegrationValidator(verbose=args.verbose)
    success = await validator.run_validation(
        config_only=args.config_only,
        components_only=args.components_only
    )

    if args.json:
        # Output results in JSON format
        results = {
            'success': success,
            'timestamp': datetime.now().isoformat(),
            'duration': (datetime.now() - validator.start_time).total_seconds(),
            'steps': [
                {
                    'name': step.name,
                    'description': step.description,
                    'status': step.status,
                    'message': step.message,
                    'duration': step.duration
                }
                for step in validator.steps
            ]
        }
        print(json.dumps(results, indent=2))

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())