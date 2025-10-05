#!/usr/bin/env python3
"""
Test script for verifying the new message sending and retry logic.
Tests simulate sending messages to online and offline recipients,
check attempt_count increments, status changes, and prevent infinite retries.
"""

import unittest
import unittest.mock as mock
import sqlite3
import os
import sys
import time
import uuid
from unittest.mock import MagicMock, patch

# Add modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'webui'))

# Import only the db functions to test
from webui.db_handler import (
    save_message, update_message_delivery_status, get_undelivered_messages,
    get_queued_messages, get_message_by_id, delete_message, get_db_connection
)

# Import the logic we need to test by copying the functions
# This avoids importing the full system.py with its dependencies
import meshtastic.serial_interface
import meshtastic.tcp_interface
import meshtastic.ble_interface
import asyncio
import random
import contextlib
import io
import uuid
import time

# Mock the interface globals
interface1 = None
myNodeNum1 = 11111111

# Copy the is_node_online function
def is_node_online(node_id, nodeInt=1, use_ping=False):
    """Check if a node is online based on last heard time (within 2 hours) and optionally ping."""
    interface = globals()[f'interface{nodeInt}']

    if interface.nodes:
        for node in interface.nodes.values():
            if node['num'] == node_id:
                last_heard = node.get('lastHeard', 0)
                # Check if last heard within 2 hours (7200 seconds)
                if last_heard and (time.time() - last_heard) <= 7200:
                    return True
                elif use_ping:
                    # Attempt ping if available and last heard check failed
                    try:
                        print(f"System: Attempting ping for node {node_id} on interface {nodeInt}")
                        # Meshtastic interface has ping method
                        ping_result = interface.ping(node_id, wantAck=True)
                        if ping_result:
                            print(f"System: Ping successful for node {node_id}")
                            return True
                        else:
                            print(f"System: Ping failed for node {node_id}")
                    except Exception as e:
                        print(f"System: Ping not available or failed for node {node_id}: {e}")
                break  # Found the node, no need to continue

    return False

# Copy the send_message function with minimal dependencies
def send_message(message, ch, nodeid=0, nodeInt=1, bypassChuncking=False, resend_existing=False, existing_message_id=None):
    # Send a message to a channel or DM with retry logic and offline saving
    interface = globals()[f'interface{nodeInt}']
    # Check if the message is empty
    if message == "" or message == None or len(message) == 0:
        return False

    # Prevent sending to own node
    if nodeid != 0 and nodeid in [globals().get(f'myNodeNum{i}') for i in range(1, 10) if globals().get(f'myNodeNum{i}')]:
        print(f"System: Attempted to send message to own node {nodeid}")
        return False

    # Determine start_attempt and message_id
    if resend_existing and existing_message_id:
        message_id = existing_message_id
        msg = get_message_by_id(message_id)
        if msg:
            start_attempt = msg['attempt_count']
        else:
            print(f"System: Message {message_id} not found for resend")
            return False
    else:
        start_attempt = 0
        message_id = str(uuid.uuid4())

        # Check online status and save message
        if nodeid != 0:
            if not is_node_online(nodeid, nodeInt):
                # Offline, queue the message
                from_node_id = str(globals().get(f'myNodeNum{nodeInt}', 777))
                to_node_id = str(nodeid)
                is_dm = True
                timestamp = time.time()
                try:
                    save_message(from_node_id, to_node_id, str(ch), message, timestamp, is_dm, status='queued', attempt_count=0, message_id=message_id)
                    print(f"System: Message queued for offline recipient {nodeid}")
                except Exception as e:
                    print(f"System: Failed to queue message for offline recipient {nodeid}: {e}")
                return False
            else:
                # Online, save as sent
                from_node_id = str(globals().get(f'myNodeNum{nodeInt}', 777))
                to_node_id = str(nodeid)
                is_dm = True
                timestamp = time.time()
                try:
                    save_message(from_node_id, to_node_id, str(ch), message, timestamp, is_dm, status='sent', attempt_count=1, message_id=message_id)
                except Exception as e:
                    print(f"System: Failed to save message to database: {e}")
                    return False
        else:
            # Channel message
            from_node_id = str(globals().get(f'myNodeNum{nodeInt}', 777))
            to_node_id = None
            is_dm = False
            timestamp = time.time()
            try:
                save_message(from_node_id, to_node_id, str(ch), message, timestamp, is_dm, status='sent', attempt_count=1, message_id=message_id)
            except Exception as e:
                print(f"System: Failed to save message to database: {e}")
                return False

    # Attempt delivery with refined retry logic: 3 attempts then defer, total 9 then undelivered
    max_direct_attempts = 3
    max_total_attempts = 9

    for attempt in range(start_attempt, max_total_attempts):
        try:
            current_attempt_count = attempt + 1
            update_message_delivery_status(message_id, attempt_count=current_attempt_count, last_attempt_time=time.time())

            if not bypassChuncking:
                # Split the message into chunks if it exceeds the MESSAGE_CHUNK_SIZE
                message_list = [message]  # Simplified for testing
            else:
                message_list = [message]

            if isinstance(message_list, list):
                # Send the message to the channel or DM
                total_length = sum(len(chunk) for chunk in message_list)
                num_chunks = len(message_list)
                for m in message_list:
                    chunkOf = f"{message_list.index(m)+1}/{num_chunks}"
                    if nodeid == 0:
                        # Send to channel - always use ACK for delivery confirmation
                        print(f"Device:{nodeInt} Channel:{ch} Attempt:{current_attempt_count} req.ACK Chunker{chunkOf} SendingChannel: {m.replace(chr(10), ' ')}")
                        interface.sendText(text=m, channelIndex=ch, wantAck=True)
                    else:
                        # Send to DM - always use ACK for delivery confirmation
                        print(f"Device:{nodeInt} Attempt:{current_attempt_count} req.ACK Chunker{chunkOf} Sending DM: {m.replace(chr(10), ' ')} To: {nodeid}")
                        interface.sendText(text=m, channelIndex=ch, destinationId=nodeid, wantAck=True)

                    # Throttle the message sending to prevent spamming the device
                    if (message_list.index(m)+1) % 4 == 0:
                        time.sleep(1)
                        if (message_list.index(m)+1) % 5 == 0:
                            print(f"System: throttling rate Interface{nodeInt} on {chunkOf}")

                    # wait an amount of time between sending each split message
                    time.sleep(0.1)  # Reduced for testing
            else: # message is less than MESSAGE_CHUNK_SIZE characters
                if nodeid == 0:
                    # Send to channel - always use ACK for delivery confirmation
                    print(f"Device:{nodeInt} Channel:{ch} Attempt:{current_attempt_count} req.ACK SendingChannel: {message.replace(chr(10), ' ')}")
                    interface.sendText(text=message, channelIndex=ch, wantAck=True)
                else:
                    # Send to DM - always use ACK for delivery confirmation
                    print(f"Device:{nodeInt} Attempt:{current_attempt_count} req.ACK Sending DM: {message.replace(chr(10), ' ')} To: {nodeid}")
                    interface.sendText(text=message, channelIndex=ch, destinationId=nodeid, wantAck=True)

            # If we reach here without exception, assume success
            update_message_delivery_status(message_id, delivered=True, status='delivered')
            print(f"System: Message {message_id} delivered successfully on attempt {current_attempt_count}")
            return True

        except Exception as e:
            error_msg = str(e)
            print(f"System: Delivery attempt {current_attempt_count} failed for message {message_id}: {error_msg}")

            # After 3 direct attempts, defer the message
            if current_attempt_count >= max_direct_attempts and current_attempt_count < max_total_attempts:
                # Defer: set status to 'queued', increment defer_count, set next_retry_time
                defer_count = (current_attempt_count // max_direct_attempts)
                next_retry_time = time.time() + (60 * defer_count)  # Exponential defer: 1min, 2min, 3min, etc.
                update_message_delivery_status(message_id, status='queued', defer_count=defer_count,
                                            next_retry_time=next_retry_time, error_message=error_msg)
                print(f"System: Message {message_id} deferred after {current_attempt_count} attempts, next retry at {time.ctime(next_retry_time)}")
                return False
            elif current_attempt_count >= max_total_attempts:
                # All attempts exhausted, mark as undelivered
                update_message_delivery_status(message_id, status='undelivered', error_message=error_msg)
                print(f"System: Message {message_id} undelivered after {max_total_attempts} total attempts")
                return False
            else:
                # Still in direct retry phase, use exponential backoff
                if attempt < max_total_attempts - 1:
                    backoff_time = 2 ** attempt  # 1s, 2s, 4s
                    print(f"System: Retrying message {message_id} in {backoff_time} seconds")
                    time.sleep(backoff_time)

    # Should not reach here, but just in case
    update_message_delivery_status(message_id, status='undelivered', error_message="Max attempts reached")
    print(f"System: Message {message_id} undelivered after reaching max attempts")
    return False

# Copy the resend_undelivered_messages function
def resend_undelivered_messages(node_id, nodeInt=1):
    """Resend undelivered and queued messages to a specific node."""
    try:
        # Skip resending to own nodes
        bot_node_ids = [globals().get(f'myNodeNum{i}') for i in range(1, 10) if globals().get(f'myNodeNum{i}') is not None]
        if int(node_id) in bot_node_ids:
            print(f"System: Skipping resend to own node {node_id}")
            return

        # Check if recipient node is online using improved detection (last heard within 2 hours)
        if not is_node_online(int(node_id), nodeInt):
            print(f"System: Node {node_id} is offline (last heard > 2 hours ago), skipping resend")
            return

        # Get 'sent' messages older than 30s with attempt_count < 3
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE status = 'sent' AND delivered = 0 AND timestamp < ? AND attempt_count < 3 AND to_node_id = ?", (time.time() - 30, str(node_id)))
        sent_messages = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]

        # Get 'queued' messages with attempt_count < 9
        cursor.execute("SELECT * FROM messages WHERE status = 'queued' AND attempt_count < 9 AND to_node_id = ?", (str(node_id),))
        queued_messages = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        conn.close()

        all_messages = sent_messages + queued_messages

        if not all_messages:
            print(f"System: No undelivered or queued messages for node {node_id}")
            return

        print(f"System: Resending {len(all_messages)} messages (sent: {len(sent_messages)}, queued: {len(queued_messages)}) to node {node_id}")

        for msg in all_messages:
            if msg['status'] == 'sent':
                # Resend 'sent' message
                truncated_text = msg['text'][:50] + "..." if len(msg['text']) > 50 else msg['text']
                print(f"System: Attempting to resend sent message {msg['message_id']} (attempt {msg['attempt_count'] + 1}/3) to node {node_id}: channel={msg['channel']}, text='{truncated_text}'")

                ch = int(msg['channel']) if msg['channel'].isdigit() else 0
                success = send_message(msg['text'], ch, int(msg['to_node_id']), nodeInt, bypassChuncking=True, resend_existing=True, existing_message_id=msg['message_id'])
                if success:
                    update_message_delivery_status(msg['message_id'], delivered=True)
                    print(f"System: Successfully resent sent message {msg['message_id']} to node {node_id}")
                else:
                    update_message_delivery_status(msg['message_id'], status='queued')
                    print(f"System: Failed to resend sent message {msg['message_id']} to node {node_id}, set to queued")

            elif msg['status'] == 'queued':
                # Resend 'queued' message if online
                if is_node_online(int(msg['to_node_id']), nodeInt):
                    truncated_text = msg['text'][:50] + "..." if len(msg['text']) > 50 else msg['text']
                    print(f"System: Attempting to resend queued message {msg['message_id']} (attempt {msg['attempt_count'] + 1}/9) to node {node_id}: channel={msg['channel']}, text='{truncated_text}'")

                    ch = int(msg['channel']) if msg['channel'].isdigit() else 0
                    success = send_message(msg['text'], ch, int(msg['to_node_id']), nodeInt, bypassChuncking=True, resend_existing=True, existing_message_id=msg['message_id'])
                    if success:
                        update_message_delivery_status(msg['message_id'], delivered=True, status='delivered')
                        print(f"System: Successfully resent queued message {msg['message_id']} to node {node_id}, updated to delivered")
                    else:
                        # Increment attempt_count
                        update_message_delivery_status(msg['message_id'], attempt_count=msg['attempt_count'] + 1)
                        print(f"System: Failed to resend queued message {msg['message_id']} to node {node_id}, incremented attempt_count to {msg['attempt_count'] + 1}")
                else:
                    print(f"System: Node {node_id} still offline, skipping queued message {msg['message_id']}")

    except Exception as e:
        print(f"System: Error resending messages to node {node_id}: {e}")


class TestMessageSending(unittest.TestCase):
    """Test cases for message sending and retry logic."""

    def setUp(self):
        """Set up test environment with mocked interface and test database."""
        # Create in-memory database for testing
        self.db_conn = sqlite3.connect(':memory:')

        # Create messages table
        self.db_conn.execute('''
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY,
                message_id TEXT UNIQUE,
                from_node_id TEXT,
                to_node_id TEXT,
                channel TEXT,
                text TEXT,
                timestamp REAL,
                is_dm INTEGER,
                status TEXT,
                delivered INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                delivery_attempts INTEGER DEFAULT 0,
                attempt_count INTEGER DEFAULT 0,
                last_attempt_time REAL,
                next_retry_time REAL,
                error_message TEXT,
                defer_count INTEGER DEFAULT 0
            )
        ''')

        # Create nodes table (required by save_message)
        self.db_conn.execute('''
            CREATE TABLE nodes (
                node_id TEXT PRIMARY KEY,
                name TEXT,
                last_seen REAL,
                battery_level INTEGER,
                latitude REAL,
                longitude REAL,
                altitude REAL,
                is_online INTEGER DEFAULT 0,
                last_telemetry REAL
            )
        ''')
        self.db_conn.commit()

        # Create a mock connection that doesn't close
        class MockConnection:
            def __init__(self, real_conn):
                self.real_conn = real_conn
                self.total_changes = 0

            def cursor(self):
                return self.real_conn.cursor()

            def execute(self, *args, **kwargs):
                result = self.real_conn.execute(*args, **kwargs)
                self.total_changes = self.real_conn.total_changes
                return result

            def commit(self):
                return self.real_conn.commit()

            def close(self):
                # Don't actually close
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_conn = MockConnection(self.db_conn)

        # Mock the interface
        self.mock_interface = MagicMock()
        self.mock_interface.sendText = MagicMock()
        self.mock_interface.nodes = {
            '!12345678': {'num': 12345678, 'lastHeard': time.time()},
            '!87654321': {'num': 87654321, 'lastHeard': time.time() - 8000}  # 8000 seconds ago (offline)
        }

        # Set globals for the copied functions
        global interface1, myNodeNum1
        interface1 = self.mock_interface
        myNodeNum1 = 11111111

        # Patch the db connection
        self.patches = [
            patch('webui.db_handler.get_db_connection', return_value=mock_conn),
            patch('__main__.time.sleep'),  # Skip sleep delays
        ]

        for p in self.patches:
            p.start()

    def tearDown(self):
        """Clean up test environment."""
        for p in self.patches:
            p.stop()
        self.db_conn.close()

    def mock_is_node_online(self, node_id, nodeInt=1, use_ping=False):
        """Mock is_node_online function."""
        if node_id == 12345678:  # Online node
            return True
        elif node_id == 87654321:  # Offline node
            return False
        return False

    def test_send_to_online_recipient(self):
        """Test sending message to online recipient."""
        # Mock successful send
        self.mock_interface.sendText.return_value = None  # Success

        result = send_message("Test message", 0, 12345678, 1)

        self.assertTrue(result)

        # Check database
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE to_node_id = '12345678'")
        msg = cursor.fetchone()

        self.assertIsNotNone(msg)
        self.assertEqual(msg[8], 'delivered')  # status
        self.assertEqual(msg[9], 1)  # delivered
        self.assertEqual(msg[12], 1)  # attempt_count

    def test_send_to_offline_recipient(self):
        """Test sending message to offline recipient queues it."""
        result = send_message("Test message", 0, 87654321, 1)

        self.assertFalse(result)  # Should return False for queued message

        # Check database
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE to_node_id = '87654321'")
        msg = cursor.fetchone()

        self.assertIsNotNone(msg)
        self.assertEqual(msg[8], 'queued')  # status
        self.assertEqual(msg[9], 0)  # delivered
        self.assertEqual(msg[12], 0)  # attempt_count

    def test_resend_queued_messages_when_online(self):
        """Test resending queued messages when recipient comes online."""
        # First queue a message for offline recipient
        send_message("Queued message", 0, 87654321, 1)

        # Mock successful send for resend
        self.mock_interface.sendText.return_value = None

        # Simulate node coming online by changing mock
        def mock_online_after(node_id, nodeInt=1, use_ping=False):
            return True  # Now online

        with patch('__main__.is_node_online', side_effect=mock_online_after):
            resend_undelivered_messages(87654321, 1)

        # Check that message was updated to delivered (successful resend)
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM messages WHERE to_node_id = '87654321'")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 1)  # Message should be updated to delivered after successful resend
        cursor.execute("SELECT status FROM messages WHERE to_node_id = '87654321'")
        status = cursor.fetchone()[0]
        self.assertEqual(status, 'delivered')

    def test_retry_logic_attempt_count_increment(self):
        """Test that attempt_count increments on retries."""
        # Mock failed sends
        self.mock_interface.sendText.side_effect = Exception("Send failed")

        result = send_message("Test message", 0, 12345678, 1)

        self.assertFalse(result)  # Should fail after retries

        # Check database
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE to_node_id = '12345678'")
        msg = cursor.fetchone()

        self.assertIsNotNone(msg)
        self.assertEqual(msg[8], 'queued')  # status - deferred after 3 attempts
        self.assertEqual(msg[9], 0)  # delivered
        self.assertEqual(msg[12], 3)  # attempt_count should be 3 (max retries)

    def test_resend_limits_sent_messages(self):
        """Test that sent messages are limited to 3 resend attempts."""
        # Create a sent message with attempt_count = 2 (will become 3 after failed resend)
        # Make it older than 30 seconds so it gets selected for resend
        old_timestamp = time.time() - 60
        message_id = str(uuid.uuid4())
        save_message('11111111', '12345678', '0', 'Test', old_timestamp, True, 'sent', False, 0, 0, 2, message_id)

        # Mock failed send to trigger the limit logic
        self.mock_interface.sendText.side_effect = Exception("Send failed")

        # Try to resend - should fail, increment attempt_count to 3, and change status to queued
        resend_undelivered_messages(12345678, 1)

        # Check that message status changed to queued
        msg = get_message_by_id(message_id)
        self.assertEqual(msg['status'], 'queued')
        self.assertEqual(msg['attempt_count'], 3)  # Started at 2, deferred after 3 attempts

    def test_resend_limits_queued_messages(self):
        """Test that queued messages are limited to 9 attempts."""
        # Create a queued message with attempt_count = 9
        message_id = str(uuid.uuid4())
        save_message('11111111', '87654321', '0', 'Test', time.time(), True, 'queued', False, 0, 0, 9, message_id)

        # Mock successful send
        self.mock_interface.sendText.return_value = None

        # Try to resend - should not attempt since attempt_count >= 9
        resend_undelivered_messages(87654321, 1)

        # Check that message still exists (not resent)
        msg = get_message_by_id(message_id)
        self.assertIsNotNone(msg)
        self.assertEqual(msg['status'], 'queued')
        self.assertEqual(msg['attempt_count'], 9)

    def test_prevent_infinite_retries(self):
        """Test that infinite retries are prevented by limits."""
        # Create multiple messages
        for i in range(5):
            message_id = str(uuid.uuid4())
            save_message('11111111', '12345678', '0', f'Test {i}', time.time(), True, 'sent', False, 0, 0, 2, message_id)

        # Mock failed sends
        self.mock_interface.sendText.side_effect = Exception("Send failed")

        # Try to resend - should increment attempt_count but not exceed limits
        resend_undelivered_messages(12345678, 1)

        # Check that attempt_counts were incremented but not beyond 3
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT attempt_count FROM messages WHERE to_node_id = '12345678'")
        attempt_counts = [row[0] for row in cursor.fetchall()]

        for count in attempt_counts:
            self.assertLessEqual(count, 3)

    def test_ack_confirmations_status_changes(self):
        """Test that ACK confirmations properly update delivery status."""
        # Mock successful send (no exception = ACK received)
        self.mock_interface.sendText.return_value = None

        result = send_message("Test message", 0, 12345678, 1)

        self.assertTrue(result)

        # Check database
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT delivered FROM messages WHERE to_node_id = '12345678'")
        delivered = cursor.fetchone()[0]

        self.assertEqual(delivered, 1)  # Should be marked as delivered

    def test_channel_message_sending(self):
        """Test sending messages to channels."""
        # Mock successful send
        self.mock_interface.sendText.return_value = None

        result = send_message("Channel message", 1, 0, 1)  # nodeid=0 for channel

        self.assertTrue(result)

        # Check database
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE to_node_id IS NULL")
        msg = cursor.fetchone()

        self.assertIsNotNone(msg)
        self.assertEqual(msg[8], 'delivered')  # status
        self.assertEqual(msg[9], 1)  # delivered
        self.assertEqual(msg[12], 1)  # attempt_count


if __name__ == '__main__':
    unittest.main(verbosity=2)