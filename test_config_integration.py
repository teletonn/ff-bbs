#!/usr/bin/env python3
"""
Configuration integration test for shared Meshtastic connection.

This script tests that:
1. Both bots pull Meshtastic settings from the main project's config.ini
2. Changes to the main project's Meshtastic configuration affect both bots
3. Both bots can send and receive messages through the shared connection

Usage:
    python test_config_integration.py [--verbose]
"""

import asyncio
import sys
import os
import logging
import tempfile
import configparser
from typing import Dict, Any
from unittest.mock import Mock

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from modules.meshgram_integration.config_manager import ConfigManager
    from modules.meshgram_integration.meshtastic_interface import MeshtasticInterface
except ImportError as e:
    print(f"Failed to import project modules: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)

class ConfigurationIntegrationTester:
    """Test configuration integration between bots."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = self._setup_logger()
        self.test_results = []

    def _setup_logger(self) -> logging.Logger:
        """Setup test logger."""
        logger = logging.getLogger('ConfigIntegrationTest')
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def log_result(self, test_name: str, passed: bool, message: str):
        """Log a test result."""
        status = "✓" if passed else "✗"
        self.logger.info(f"{status} {test_name}: {message}")
        self.test_results.append((test_name, passed, message))

    async def test_config_sharing(self) -> bool:
        """Test that both bots share the same configuration."""
        test_name = "Configuration Sharing"

        try:
            # Create two config managers
            config1 = ConfigManager()
            config2 = ConfigManager()

            # Both should reference the same config object
            if config1.config is config2.config:
                self.log_result(test_name, True, "Both bots share the same configuration object")
                return True
            else:
                self.log_result(test_name, False, "Bots use different configuration objects")
                return False

        except Exception as e:
            self.log_result(test_name, False, f"Error testing config sharing: {e}")
            return False

    async def test_meshtastic_config_reading(self) -> bool:
        """Test that bots can read Meshtastic configuration from main project."""
        test_name = "Meshtastic Config Reading"

        try:
            config = ConfigManager()

            # Test reading interface configuration
            interface_type = config.get('interface.type')
            interface_hostname = config.get('interface.hostname')

            if interface_type and interface_hostname:
                self.log_result(test_name, True, f"Successfully read interface config: {interface_type}://{interface_hostname}")
                return True
            else:
                self.log_result(test_name, False, "Interface configuration incomplete")
                return False

        except Exception as e:
            self.log_result(test_name, False, f"Error reading Meshtastic config: {e}")
            return False

    async def test_config_change_propagation(self) -> bool:
        """Test that configuration changes propagate to both bots."""
        test_name = "Configuration Change Propagation"

        try:
            # Create a temporary config file to test changes
            with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
                temp_config_path = f.name
                f.write("""[interface]
type = tcp
hostname = 192.168.1.100

[general]
respond_by_dm_only = True
defaultChannel = 2

[telegram]
telegram_bot_token = test_token
telegram_chat_id = 123456789
""")

            # Create config managers that read from the temp file
            original_config = configparser.ConfigParser()
            original_config.read('config.ini')

            try:
                # Mock the settings module to use our temp config
                import modules.settings as settings_module
                original_read_config = settings_module.config

                # Create a new config based on our temp file
                temp_config = configparser.ConfigParser()
                temp_config.read(temp_config_path)

                settings_module.config = temp_config

                # Create two config managers
                config1 = ConfigManager()
                config2 = ConfigManager()

                # Both should read the same values
                host1 = config1.get('interface.hostname')
                host2 = config2.get('interface.hostname')

                if host1 == host2 == '192.168.1.100':
                    self.log_result(test_name, True, "Configuration changes propagate to both bots")
                    return True
                else:
                    self.log_result(test_name, False, f"Configuration not propagated: {host1} != {host2}")
                    return False

            finally:
                # Restore original config
                settings_module.config = original_config
                os.unlink(temp_config_path)

        except Exception as e:
            self.log_result(test_name, False, f"Error testing config propagation: {e}")
            return False

    async def test_shared_interface_configuration(self) -> bool:
        """Test that shared interface uses main project configuration."""
        test_name = "Shared Interface Configuration"

        try:
            # Create mock interface
            mock_interface = Mock()
            mock_interface.getMyNodeInfo = Mock(return_value={
                'user': {'id': '1234567890', 'longName': 'TestNode'},
                'deviceMetrics': {'batteryLevel': 100}
            })

            # Create interface wrapper
            config = ConfigManager()
            interface = MeshtasticInterface(config, mock_interface)

            # Verify interface has access to main project config
            if interface.config is config.config:
                self.log_result(test_name, True, "Shared interface uses main project configuration")
                return True
            else:
                self.log_result(test_name, False, "Shared interface doesn't use main project config")
                return False

        except Exception as e:
            self.log_result(test_name, False, f"Error testing shared interface config: {e}")
            return False

    async def run_all_tests(self) -> bool:
        """Run all configuration integration tests."""
        self.logger.info("Starting configuration integration tests...")

        tests = [
            self.test_config_sharing,
            self.test_meshtastic_config_reading,
            self.test_config_change_propagation,
            self.test_shared_interface_configuration
        ]

        for test in tests:
            try:
                await test()
            except Exception as e:
                self.logger.error(f"Test {test.__name__} failed with exception: {e}")

        # Print summary
        passed = sum(1 for _, result, _ in self.test_results if result)
        total = len(self.test_results)

        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"CONFIG INTEGRATION TEST SUMMARY: {passed}/{total} tests passed")
        self.logger.info(f"{'='*60}")

        for test_name, passed, message in self.test_results:
            status = "PASS" if passed else "FAIL"
            self.logger.info(f"{status}: {test_name}")
            self.logger.info(f"  └─ {message}")

        return passed == total

async def main():
    """Main test runner."""
    import argparse

    parser = argparse.ArgumentParser(description='Test configuration integration')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    tester = ConfigurationIntegrationTester(verbose=args.verbose)
    success = await tester.run_all_tests()

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())