#!/usr/bin/env python3
"""
Comprehensive test script for message sending functionality in meshgram integration.
Tests chunking, message formatting, routing logic, and send_message_to_chat method.
"""
import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'modules', 'meshgram_integration'))

from message_processor import MessageProcessor, TelegramMessage
from telegram import Update, Message, User, Chat
from telegram.constants import ChatType

class MockConfig:
    def __init__(self):
        self.data = {
            'telegram.meshtastic_local_nodes': '',
            'telegram.telegram_default_channel': 0,
            'telegram.meshtastic_default_node_id': '!12345678',
            'telegram_authorized_users': []
        }

    def get(self, key, default=None):
        return self.data.get(key, default)

    def get_authorized_users(self):
        return self.data.get('telegram_authorized_users', [])

class MockNodeManager:
    def __init__(self):
        self.nodes = {}

    def get_node_id(self, node_id):
        if node_id.startswith('!'):
            return int(node_id[1:], 16)
        return node_id

class MockMeshtasticInterface:
    def __init__(self):
        self.node_manager = MockNodeManager()
        self.sent_messages = []
        self.message_queue = asyncio.Queue()

    async def send_message(self, text, recipient):
        message_id = f"msg_{len(self.sent_messages)}"
        self.sent_messages.append({
            'text': text,
            'recipient': recipient,
            'id': message_id
        })
        return {'id': message_id}

    async def get_status(self):
        return "Mock Meshtastic Status: Connected"

class MockTelegramInterface:
    def __init__(self):
        self.sent_messages = []
        self.message_queue = asyncio.Queue()
        self.reactions = []

    def is_user_authorized(self, user_id):
        return True  # Mock all users as authorized for testing

    async def send_message(self, text, disable_notification=False):
        message_id = len(self.sent_messages) + 1
        self.sent_messages.append({
            'text': text,
            'message_id': message_id,
            'disable_notification': disable_notification
        })
        return message_id

    async def send_message_to_chat(self, chat_id, text, disable_notification=False):
        message_id = len(self.sent_messages) + 1
        self.sent_messages.append({
            'chat_id': chat_id,
            'text': text,
            'message_id': message_id,
            'disable_notification': disable_notification
        })
        return message_id

    async def add_reaction(self, message_id, emoji):
        self.reactions.append({
            'message_id': message_id,
            'emoji': emoji
        })

def create_mock_update(text, user_id=12345, message_id=100, chat_type='group'):
    """Create a mock Telegram Update object"""
    user = User(id=user_id, first_name="TestUser", is_bot=False, username="testuser")
    chat = Chat(id=12345, type=chat_type)
    message = Message(message_id=message_id, date=None, chat=chat, from_user=user, text=text)
    update = Update(update_id=1, message=message)
    return update

async def test_chunking_mechanism():
    """Test the chunk_message method with various inputs"""
    print("\n=== Testing Chunking Mechanism ===")

    config = MockConfig()
    meshtastic = MockMeshtasticInterface()
    telegram = MockTelegramInterface()
    processor = MessageProcessor(meshtastic, telegram, config)

    test_cases = [
        # Short message
        ("Hello world", 1),
        # Exactly 110 chars
        ("x" * 110, 1),
        # Over 110 chars - should chunk
        ("x" * 200, 2),  # 200 chars / 110 chars per chunk = 2 chunks
        # Very long message (should be truncated to 1000 chars and chunked)
        ("x" * 1200, 10),  # 1000 chars / ~110 chars per chunk = ~10 chunks
        # Message with spaces (should break at word boundaries)
        ("This is a very long message that should be split into multiple chunks for testing purposes and demonstrate word boundary breaking functionality in the chunking algorithm.",
          2)  # Should break into 2 chunks at word boundaries
    ]

    for message, expected_chunks in test_cases:
        chunks = processor.chunk_message(message)
        print(f"Message length: {len(message)}, Expected chunks: {expected_chunks}, Actual chunks: {len(chunks)}")

        # Verify chunk count
        assert len(chunks) == expected_chunks, f"Expected {expected_chunks} chunks, got {len(chunks)}"

        # Verify no chunk exceeds 120 chars (110 + counter length)
        for i, chunk in enumerate(chunks):
            assert len(chunk) <= 120, f"Chunk {i} too long: {len(chunk)} > 120"
            print(f"  Chunk {i+1}: {chunk[:50]}{'...' if len(chunk) > 50 else ''}")

        # Verify total content reconstructs properly
        if len(chunks) > 1:
            # Remove counters for content check
            import re
            content_no_counters = re.sub(r'\d+/\d+ ', '', "".join(chunks))
            assert len(content_no_counters) <= 1000, f"Total content too long: {len(content_no_counters)} > 1000"

    print("✅ Chunking mechanism tests passed!")

async def test_message_formatting_and_routing():
    """Test message formatting and routing logic"""
    print("\n=== Testing Message Formatting and Routing ===")

    config = MockConfig()
    meshtastic = MockMeshtasticInterface()
    telegram = MockTelegramInterface()
    processor = MessageProcessor(meshtastic, telegram, config)

    # Test DM message (should go to ^all)
    dm_message = TelegramMessage(
        type='telegram',
        text='Test DM message',
        sender='TestUser',
        message_id=100,
        user_id=12345,
        chat_type='private'
    )

    # Mock asyncio.sleep to avoid delays
    with patch('asyncio.sleep', return_value=None):
        await processor.handle_telegram_text(dm_message)

    # Check that message was sent to ^all
    assert len(meshtastic.sent_messages) == 1
    assert meshtastic.sent_messages[0]['recipient'] == '^all'
    assert '[TG:TestUser] Test DM message' in meshtastic.sent_messages[0]['text']
    print("✅ DM message routing test passed!")

    # Reset for group message test
    meshtastic.sent_messages.clear()

    # Test group message (should use default node)
    group_message = TelegramMessage(
        type='telegram',
        text='Test group message',
        sender='TestUser',
        message_id=101,
        user_id=12345,
        chat_type='group'
    )

    # Mock asyncio.sleep to avoid delays
    with patch('asyncio.sleep', return_value=None):
        await processor.handle_telegram_text(group_message)

    # Check that message was sent to default node
    assert len(meshtastic.sent_messages) == 1
    assert meshtastic.sent_messages[0]['recipient'] == '!12345678'
    assert '[TG:TestUser] Test group message' in meshtastic.sent_messages[0]['text']
    print("✅ Group message routing test passed!")

async def test_send_message_to_chat():
    """Test the send_message_to_chat method"""
    print("\n=== Testing send_message_to_chat Method ===")

    config = MockConfig()
    meshtastic = MockMeshtasticInterface()
    telegram = MockTelegramInterface()
    processor = MessageProcessor(meshtastic, telegram, config)

    # Test sending confirmation message to user DM
    await processor.telegram.send_message_to_chat(12345, "Test confirmation message")

    assert len(telegram.sent_messages) == 1
    assert telegram.sent_messages[0]['chat_id'] == 12345
    assert telegram.sent_messages[0]['text'] == "Test confirmation message"
    print("✅ send_message_to_chat test passed!")

async def test_ack_handling():
    """Test ACK handling and pending message tracking"""
    print("\n=== Testing ACK Handling ===")

    config = MockConfig()
    meshtastic = MockMeshtasticInterface()
    telegram = MockTelegramInterface()
    processor = MessageProcessor(meshtastic, telegram, config)

    # Send a message to create a pending ACK
    message = TelegramMessage(
        type='telegram',
        text='Test message for ACK',
        sender='TestUser',
        message_id=102,
        user_id=12345,
        chat_type='group'
    )

    # Mock asyncio.sleep to avoid delays
    with patch('asyncio.sleep', return_value=None):
        await processor.handle_telegram_text(message)

    # Check that we have a pending ACK
    assert len(processor.pending_acks) == 1
    message_id = list(processor.pending_acks.keys())[0]
    assert processor.pending_acks[message_id]['telegram_message_id'] == 102

    # Simulate ACK receipt
    ack_packet = {
        'type': 'ack',
        'fromId': '!87654321',
        'toId': '!12345678',
        'message_id': message_id
    }

    await processor.handle_ack(ack_packet)

    # Check that ACK was processed and pending ACK removed
    assert len(processor.pending_acks) == 0
    assert len(telegram.reactions) == 1
    assert telegram.reactions[0]['message_id'] == 102
    assert telegram.reactions[0]['emoji'] == '✅'
    print("✅ ACK handling test passed!")

async def test_chunked_message_ack():
    """Test ACK handling for chunked messages"""
    print("\n=== Testing Chunked Message ACK ===")

    config = MockConfig()
    meshtastic = MockMeshtasticInterface()
    telegram = MockTelegramInterface()
    processor = MessageProcessor(meshtastic, telegram, config)

    # Send a long message that will be chunked
    long_message = "x" * 200  # This creates 3 chunks due to word boundary breaking with the prefix
    message = TelegramMessage(
        type='telegram',
        text=long_message,
        sender='TestUser',
        message_id=103,
        user_id=12345,
        chat_type='group'
    )

    # Mock asyncio.sleep to avoid 5-second delays between chunks
    with patch('asyncio.sleep', return_value=None):
        await processor.handle_telegram_text(message)

    # Check that we have 3 pending ACKs (one per chunk)
    assert len(processor.pending_acks) == 3
    message_ids = list(processor.pending_acks.keys())

    # Simulate ACK for first chunk
    ack_packet1 = {
        'type': 'ack',
        'fromId': '!87654321',
        'toId': '!12345678',
        'message_id': message_ids[0]
    }

    await processor.handle_ack(ack_packet1)

    # Should still have 2 pending ACKs and 1 reaction (ACK processed for first chunk)
    assert len(processor.pending_acks) == 2
    assert len(telegram.reactions) == 1

    # Simulate ACK for second chunk
    ack_packet2 = {
        'type': 'ack',
        'fromId': '!87654321',
        'toId': '!12345678',
        'message_id': message_ids[1]
    }

    await processor.handle_ack(ack_packet2)

    # Should still have 1 pending ACK and 2 reactions
    assert len(processor.pending_acks) == 1
    assert len(telegram.reactions) == 2

    # Simulate ACK for third chunk
    ack_packet3 = {
        'type': 'ack',
        'fromId': '!87654321',
        'toId': '!12345678',
        'message_id': message_ids[2]
    }

    await processor.handle_ack(ack_packet3)

    # All ACKs should be processed
    assert len(processor.pending_acks) == 0
    assert len(telegram.reactions) == 3  # One reaction per chunk
    print("✅ Chunked message ACK test passed!")

async def main():
    """Run all tests"""
    print("Starting comprehensive message sending integration tests...")

    try:
        await test_chunking_mechanism()
        await test_message_formatting_and_routing()
        await test_send_message_to_chat()
        await test_ack_handling()
        await test_chunked_message_ack()

        print("\n🎉 All tests passed successfully!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)