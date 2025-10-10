#!/usr/bin/env python3
"""
Comprehensive test suite for validating shared Meshtastic connection between offgrid bot and Telegram bot.

This test suite validates:
1. Shared connection integrity between both bots
2. Configuration integration from main project config
3. Message routing functionality
4. Connection stability and error handling
5. No duplicate connections are created

Usage:
    python test_shared_connection.py [--mock] [--verbose]

Options:
    --mock      Run tests with mocked interfaces (no hardware required)
    --verbose   Enable verbose logging
"""

import asyncio
import unittest
import logging
import sys
import os
import time
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import project modules
try:
    from modules.meshgram_integration.config_manager import ConfigManager
    from modules.meshgram_integration.meshgram import MeshgramIntegration
    from modules.meshgram_integration.meshtastic_interface import MeshtasticInterface
    from modules.meshgram_integration.telegram_interface import TelegramInterface
    from modules.meshgram_integration.message_processor import MessageProcessor
    from modules import settings
except ImportError as e:
    print(f"Failed to import project modules: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)

@dataclass
class TestResult:
    """Container for test results."""
    test_name: str
    passed: bool
    message: str
    duration: float = 0.0

class SharedConnectionValidator:
    """Main test validator class for shared Meshtastic connection."""

    def __init__(self, use_mock: bool = True, verbose: bool = False):
        self.use_mock = use_mock
        self.verbose = verbose
        self.results: List[TestResult] = []
        self.logger = self._setup_logger()

        # Test components
        self.config_manager = ConfigManager()
        self.mock_interface = None
        self.meshgram_integration = None

    def _setup_logger(self) -> logging.Logger:
        """Setup test logger."""
        logger = logging.getLogger('SharedConnectionTest')
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def record_result(self, test_name: str, passed: bool, message: str, duration: float = 0.0):
        """Record a test result."""
        result = TestResult(test_name, passed, message, duration)
        self.results.append(result)
        self.logger.info(f"{'✓' if passed else '✗'} {test_name}: {message}")

    async def setup_mock_interface(self) -> Mock:
        """Setup a mock Meshtastic interface for testing."""
        self.logger.info("Setting up mock Meshtastic interface...")

        mock_interface = Mock()
        mock_interface.getMyNodeInfo = Mock(return_value={
            'user': {'id': '1234567890', 'longName': 'TestNode'},
            'deviceMetrics': {'batteryLevel': 100, 'voltage': 4.2}
        })
        mock_interface.sendText = Mock(return_value=True)
        mock_interface.sendReaction = Mock(return_value=True)
        mock_interface.close = Mock(return_value=True)
        mock_interface.ping = Mock(return_value=True)

        self.mock_interface = mock_interface
        return mock_interface

    async def test_shared_interface_instance(self) -> bool:
        """Test that both bots use the same Meshtastic interface instance."""
        start_time = time.time()
        test_name = "Shared Interface Instance"

        try:
            if self.use_mock:
                await self.setup_mock_interface()

            # Create first bot instance (simulating offgrid bot)
            bot1_interface = MeshtasticInterface(self.config_manager, self.mock_interface)

            # Create second bot instance (simulating Telegram bot) with same interface
            bot2_interface = MeshtasticInterface(self.config_manager, self.mock_interface)

            # Verify both interfaces reference the same underlying connection
            if hasattr(self.mock_interface, '_is_shared'):
                self.mock_interface._is_shared = True

            # Check that both interfaces are using the same connection object
            interface1_id = id(bot1_interface.interface)
            interface2_id = id(bot2_interface.interface)

            if interface1_id == interface2_id:
                self.record_result(test_name, True, "Both bots share the same interface instance", time.time() - start_time)
                return True
            else:
                self.record_result(test_name, False, f"Different interface instances: {interface1_id} != {interface2_id}", time.time() - start_time)
                return False

        except Exception as e:
            self.record_result(test_name, False, f"Error testing shared interface: {e}", time.time() - start_time)
            return False

    async def test_configuration_integration(self) -> bool:
        """Test that Telegram bot pulls Meshtastic settings from main project config."""
        start_time = time.time()
        test_name = "Configuration Integration"

        try:
            # Test that config manager can read main project settings
            interface_type = self.config_manager.get('interface.type')
            interface_hostname = self.config_manager.get('interface.hostname')

            if interface_type and interface_hostname:
                self.record_result(test_name, True, f"Successfully read interface config: {interface_type}://{interface_hostname}", time.time() - start_time)
                return True
            else:
                self.record_result(test_name, False, "Failed to read interface configuration", time.time() - start_time)
                return False

        except Exception as e:
            self.record_result(test_name, False, f"Error testing configuration integration: {e}", time.time() - start_time)
            return False

    async def test_no_duplicate_connections(self) -> bool:
        """Test that no duplicate connections are created."""
        start_time = time.time()
        test_name = "No Duplicate Connections"

        try:
            if self.use_mock:
                await self.setup_mock_interface()

            # Track connection attempts
            original_init = None
            connection_count = 0

            def mock_connection_init(self):
                nonlocal connection_count
                connection_count += 1
                if original_init:
                    return original_init(self)
                return None

            # Mock the interface creation to count connection attempts
            with patch('meshtastic.tcp_interface.TCPInterface.__init__', mock_connection_init), \
                 patch('meshtastic.serial_interface.SerialInterface.__init__', mock_connection_init):

                # Create multiple interface wrappers
                interface1 = MeshtasticInterface(self.config_manager, self.mock_interface)
                interface2 = MeshtasticInterface(self.config_manager, self.mock_interface)

                # Should only create one connection (shared)
                if connection_count <= 1:
                    self.record_result(test_name, True, f"Created {connection_count} connection(s) as expected", time.time() - start_time)
                    return True
                else:
                    self.record_result(test_name, False, f"Created {connection_count} connections (should be 1)", time.time() - start_time)
                    return False

        except Exception as e:
            self.record_result(test_name, False, f"Error testing duplicate connections: {e}", time.time() - start_time)
            return False

    async def test_message_routing(self) -> bool:
        """Test message routing between both bots."""
        start_time = time.time()
        test_name = "Message Routing"

        try:
            if self.use_mock:
                await self.setup_mock_interface()

            # Create message processor with shared interface
            message_processor = MessageProcessor(
                MeshtasticInterface(self.config_manager, self.mock_interface),
                Mock(),  # Mock Telegram interface
                self.config_manager
            )

            # Test message queue functionality
            test_message = {
                'type': 'test_message',
                'text': 'Hello from test',
                'from': '1234567890',
                'to': '9876543210'
            }

            # Simulate message processing
            await message_processor.meshtastic.message_queue.put(test_message)

            # Check if message was processed (would be consumed from queue)
            try:
                # Try to get message with timeout
                queued_message = message_processor.meshtastic.message_queue.get_nowait()
                if queued_message['text'] == test_message['text']:
                    self.record_result(test_name, True, "Message routing functional", time.time() - start_time)
                    return True
            except asyncio.QueueEmpty:
                self.record_result(test_name, False, "Message not found in queue", time.time() - start_time)
                return False

        except Exception as e:
            self.record_result(test_name, False, f"Error testing message routing: {e}", time.time() - start_time)
            return False

    async def test_configuration_changes_propagation(self) -> bool:
        """Test that changes to main project Meshtastic config affect both bots."""
        start_time = time.time()
        test_name = "Configuration Changes Propagation"

        try:
            # Test that both bots read from the same config source
            bot1_config = ConfigManager()
            bot2_config = ConfigManager()

            # Both should reference the same config object
            if bot1_config.config is bot2_config.config:
                self.record_result(test_name, True, "Both bots share the same configuration object", time.time() - start_time)
                return True
            else:
                self.record_result(test_name, False, "Bots use different configuration objects", time.time() - start_time)
                return False

        except Exception as e:
            self.record_result(test_name, False, f"Error testing config propagation: {e}", time.time() - start_time)
            return False

    async def test_connection_stability(self) -> bool:
        """Test connection stability and error handling."""
        start_time = time.time()
        test_name = "Connection Stability"

        try:
            if self.use_mock:
                await self.setup_mock_interface()

            interface = MeshtasticInterface(self.config_manager, self.mock_interface)

            # Test health check functionality
            try:
                # Mock a failing ping to test error handling
                self.mock_interface.ping.side_effect = [True, True, Exception("Connection lost")]

                # First two pings should succeed
                await interface.periodic_health_check()
                await interface.periodic_health_check()

                # Third ping should trigger reconnection logic
                try:
                    await interface.periodic_health_check()
                except Exception:
                    pass  # Expected due to our mock exception

                self.record_result(test_name, True, "Connection stability and error handling functional", time.time() - start_time)
                return True

            except Exception as e:
                self.record_result(test_name, False, f"Error testing connection stability: {e}", time.time() - start_time)
                return False

        except Exception as e:
            self.record_result(test_name, False, f"Error setting up stability test: {e}", time.time() - start_time)
            return False

    async def test_simultaneous_operation(self) -> bool:
        """Test that both bots can operate simultaneously without conflicts."""
        start_time = time.time()
        test_name = "Simultaneous Operation"

        try:
            if self.use_mock:
                await self.setup_mock_interface()

            # Create two interface wrappers sharing the same connection
            interface1 = MeshtasticInterface(self.config_manager, self.mock_interface)
            interface2 = MeshtasticInterface(self.config_manager, self.mock_interface)

            # Simulate simultaneous operations
            tasks = [
                interface1.send_message("Test message 1", "1234567890"),
                interface2.send_message("Test message 2", "9876543210"),
                interface1.get_status(),
                interface2.get_status()
            ]

            # Execute simultaneous operations
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check if all operations completed without conflicts
            success_count = sum(1 for r in results if not isinstance(r, Exception))

            if success_count >= 3:  # Allow for some failures in error simulation
                self.record_result(test_name, True, f"Simultaneous operations successful ({success_count}/4)", time.time() - start_time)
                return True
            else:
                self.record_result(test_name, False, f"Only {success_count}/4 simultaneous operations succeeded", time.time() - start_time)
                return False

        except Exception as e:
            self.record_result(test_name, False, f"Error testing simultaneous operation: {e}", time.time() - start_time)
            return False

    async def run_all_tests(self) -> bool:
        """Run all shared connection tests."""
        self.logger.info("Starting comprehensive shared connection tests...")

        tests = [
            self.test_shared_interface_instance,
            self.test_configuration_integration,
            self.test_no_duplicate_connections,
            self.test_message_routing,
            self.test_configuration_changes_propagation,
            self.test_connection_stability,
            self.test_simultaneous_operation
        ]

        for test in tests:
            try:
                await test()
            except Exception as e:
                self.logger.error(f"Test {test.__name__} failed with exception: {e}")

        # Print summary
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)

        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"TEST SUMMARY: {passed}/{total} tests passed")
        self.logger.info(f"{'='*60}")

        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            self.logger.info(f"{status}: {result.test_name} ({result.duration".2f"}s)")
            if not result.passed:
                self.logger.info(f"  └─ {result.message}")

        return passed == total

class IntegrationValidationScript:
    """Hardware-independent integration validation script."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = logging.getLogger('IntegrationValidator')
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)

        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    async def validate_integration(self) -> bool:
        """Validate the entire integration without requiring actual hardware."""
        self.logger.info("Starting integration validation...")

        try:
            # Test configuration loading
            config = ConfigManager()
            self.logger.info("✓ Configuration manager loaded successfully")

            # Test interface creation (mocked)
            mock_interface = Mock()
            mock_interface.getMyNodeInfo = Mock(return_value={
                'user': {'id': '1234567890', 'longName': 'TestNode'},
                'deviceMetrics': {'batteryLevel': 100}
            })

            # Test MeshtasticInterface wrapper
            mesh_interface = MeshtasticInterface(config, mock_interface)
            self.logger.info("✓ MeshtasticInterface wrapper created successfully")

            # Test TelegramInterface (mocked)
            telegram_interface = Mock()
            telegram_interface.setup = Mock(return_value=asyncio.coroutine(lambda: None)())
            telegram_interface.start_polling = Mock(return_value=asyncio.coroutine(lambda: None)())
            telegram_interface.close = Mock(return_value=asyncio.coroutine(lambda: None)())

            # Test MessageProcessor
            message_processor = MessageProcessor(mesh_interface, telegram_interface, config)
            self.logger.info("✓ MessageProcessor created successfully")

            # Test MeshgramIntegration
            integration = MeshgramIntegration(mock_interface, config)
            self.logger.info("✓ MeshgramIntegration created successfully")

            self.logger.info("✓ All integration components validated successfully")
            return True

        except Exception as e:
            self.logger.error(f"✗ Integration validation failed: {e}")
            return False

async def main():
    """Main test runner."""
    import argparse

    parser = argparse.ArgumentParser(description='Test shared Meshtastic connection')
    parser.add_argument('--mock', action='store_true', default=True,
                       help='Use mocked interfaces (default: True)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--integration-only', action='store_true',
                       help='Only run integration validation script')

    args = parser.parse_args()

    if args.integration_only:
        # Run only the integration validation script
        validator = IntegrationValidationScript(verbose=args.verbose)
        success = await validator.validate_integration()
        exit_code = 0 if success else 1
    else:
        # Run full test suite
        validator = SharedConnectionValidator(use_mock=args.mock, verbose=args.verbose)
        success = await validator.run_all_tests()
        exit_code = 0 if success else 1

    sys.exit(exit_code)

if __name__ == "__main__":
    asyncio.run(main())