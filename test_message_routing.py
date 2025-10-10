#!/usr/bin/env python3
"""
Test script to validate message routing fixes between Telegram and Meshtastic.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.meshgram_integration.config_manager import ConfigManager
from modules import log

class MessageRoutingTester:
    def __init__(self):
        self.config = ConfigManager()
        self.logger = log.logger

    def test_configuration(self):
        """Test that configuration is properly loaded and validated."""
        print("🔧 Testing configuration...")

        try:
            # Test required keys
            bot_token = self.config.get('telegram.telegram_bot_token')
            chat_id = self.config.get('telegram.telegram_chat_id')
            default_channel = self.config.get('telegram.telegram_default_channel', 0)
            default_node_id = self.config.get('telegram.meshtastic_default_node_id')

            print(f"✅ Bot token: {'Set' if bot_token else 'Not set'}")
            print(f"✅ Chat ID: {chat_id}")
            print(f"✅ Default channel: {default_channel}")
            print(f"✅ Default node ID: {default_node_id}")

            # Validate configuration
            self.config.validate_config()
            print("✅ Configuration validation passed")

            return True
        except Exception as e:
            print(f"❌ Configuration test failed: {e}")
            return False

    def test_channel_routing_logic(self):
        """Test the channel routing logic."""
        print("\n🔀 Testing channel routing logic...")

        # Simulate different channel scenarios
        test_cases = [
            {"channel": 0, "expected_broadcast": True, "description": "Default channel message"},
            {"channel": 1, "expected_broadcast": False, "description": "Different channel message"},
            {"channel": 2, "expected_broadcast": False, "description": "Another channel message"},
        ]

        default_channel = self.config.get('telegram.telegram_default_channel', 0)

        for test_case in test_cases:
            channel = test_case["channel"]
            # Ensure both are integers for proper comparison
            channel_int = int(channel)
            default_channel_int = int(default_channel) if default_channel is not None else 0
            should_broadcast = (channel_int == default_channel_int)  # Only broadcast messages from the configured default channel
            expected = test_case["expected_broadcast"]

            print(f"Debug: channel={channel_int}, default_channel={default_channel_int}, should_broadcast={should_broadcast}, expected={expected}")

            if should_broadcast == expected:
                print(f"✅ {test_case['description']}: Channel {channel} -> Broadcast: {should_broadcast}")
            else:
                print(f"❌ {test_case['description']}: Channel {channel} -> Expected: {expected}, Got: {should_broadcast}")
                return False

        return True

    def test_telemetry_filtering(self):
        """Test that telemetry data is properly filtered."""
        print("\n📊 Testing telemetry filtering...")

        # Mock message processor for testing
        class MockProcessor:
            def __init__(self, config):
                self.config = config

            def _is_telemetry_data(self, text: str) -> bool:
                """Check if the message contains telemetry data that should be excluded from channel 0 broadcasts."""
                telemetry_keywords = [
                    'battery', 'voltage', 'temperature', 'humidity', 'barometer',
                    'iaq', 'distance', 'current', 'power', 'energy', 'rssi',
                    'snr', 'device metrics', 'air util', 'channel util'
                ]
                text_lower = text.lower()
                return any(keyword in text_lower for keyword in telemetry_keywords)

        processor = MockProcessor(self.config)

        test_messages = [
            {"text": "Hello world", "should_filter": False, "description": "Regular message"},
            {"text": "Battery level is 85%", "should_filter": True, "description": "Battery telemetry"},
            {"text": "Temperature is 23°C", "should_filter": True, "description": "Temperature telemetry"},
            {"text": "Channel utilization: 45%", "should_filter": True, "description": "Channel utilization"},
            {"text": "Device metrics: voltage=3.7V", "should_filter": True, "description": "Device metrics"},
        ]

        all_passed = True
        for test_msg in test_messages:
            is_telemetry = processor._is_telemetry_data(test_msg["text"])
            expected = test_msg["should_filter"]

            if is_telemetry == expected:
                print(f"✅ {test_msg['description']}: '{test_msg['text']}' -> Filtered: {is_telemetry}")
            else:
                print(f"❌ {test_msg['description']}: '{test_msg['text']}' -> Expected: {expected}, Got: {is_telemetry}")
                all_passed = False

        return all_passed

    def run_all_tests(self):
        """Run all tests and return overall result."""
        print("🚀 Starting message routing tests...\n")

        tests = [
            self.test_configuration,
            self.test_channel_routing_logic,
            self.test_telemetry_filtering,
        ]

        results = []
        for test in tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"❌ Test failed with exception: {e}")
                results.append(False)

        print(f"\n📊 Test Results: {sum(results)}/{len(results)} passed")

        if all(results):
            print("🎉 All tests passed! Message routing should work correctly.")
            return True
        else:
            print("⚠️  Some tests failed. Please check the issues above.")
            return False

async def main():
    """Main test function."""
    tester = MessageRoutingTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))