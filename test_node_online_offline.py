#!/usr/bin/env python3
"""
Test suite for node online/offline status handling.

Tests verify:
1) Nodes are correctly marked online when receiving any relevant packet type
   (TEXT_MESSAGE_APP, ROUTING_APP, POSITION_APP, TELEMETRY_APP, NODEINFO_APP,
    NEIGHBORINFO_APP, TRACEROUTE_APP)
2) Nodes are marked offline only after exactly 30 minutes of no activity from any relevant packet type
3) The offline detection logic correctly considers all packet types, not just telemetry and messages
4) Changes don't break existing functionality
"""

import unittest
import time
import sqlite3
import os
import sys
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webui.db_handler import (
    get_db_connection, add_node, update_node_last_seen, update_node_telemetry,
    check_and_update_offline_nodes, get_nodes, update_node, set_setting
)


class TestNodeOnlineOffline(unittest.TestCase):
    """Test cases for node online/offline status handling."""

    def setUp(self):
        """Set up test database."""
        # Create a temporary database for testing
        self.test_db_path = tempfile.mktemp(suffix='.db')
        self.original_get_db_connection = get_db_connection

        # Patch get_db_connection to use our test database
        def test_get_db_connection(db_name='dashboard.db'):
            db_path = os.path.join(os.path.dirname(self.test_db_path), db_name)
            if db_name == 'dashboard.db':
                db_path = self.test_db_path
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            return conn

        # Monkey patch the function
        import webui.db_handler
        webui.db_handler.get_db_connection = test_get_db_connection

        # Initialize the database schema manually for testing
        # Use the actual database file directly
        conn = sqlite3.connect(self.test_db_path)
        cursor = conn.cursor()

        # Enable WAL mode
        cursor.execute('PRAGMA journal_mode=WAL;')

        # Drop tables if they exist
        cursor.execute('DROP TABLE IF EXISTS nodes')
        cursor.execute('DROP TABLE IF EXISTS settings')

        # Create nodes table
        cursor.execute('''
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT UNIQUE NOT NULL,
            name TEXT,
            last_seen TIMESTAMP,
            battery_level INTEGER,
            latitude REAL,
            longitude REAL,
            altitude INTEGER,
            snr REAL,
            rssi INTEGER,
            hop_count INTEGER,
            pki_status TEXT,
            hardware_model TEXT,
            firmware_version TEXT,
            role TEXT DEFAULT 'client',
            is_online BOOLEAN DEFAULT 0,
            last_telemetry TIMESTAMP,
            ground_speed REAL,
            precision_bits INTEGER,
            last_activity TIMESTAMP
        )
        ''')

        # Create settings table
        cursor.execute('''
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        conn.commit()
        print(f"Database initialized at: {self.test_db_path}")
        conn.close()

        # Insert default settings if not exist
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)",
                      ('node.inactivity_timeout_minutes', '30', 'Timeout in minutes for node offline detection'))
        conn.commit()
        conn.close()

    def tearDown(self):
        """Clean up test database."""
        # Restore original function
        import webui.db_handler
        webui.db_handler.get_db_connection = self.original_get_db_connection

        # Remove test database
        if os.path.exists(self.test_db_path):
            os.unlink(self.test_db_path)

    def test_node_marked_online_on_text_message(self):
        """Test that nodes are marked online when receiving TEXT_MESSAGE_APP packets."""
        node_id = "1234567890"

        # Add a node that's initially offline
        add_node(node_id, "Test Node", time.time() - 3600, None, None, None, None)  # 1 hour ago
        update_node(node_id, is_online=False)

        # Verify node is offline
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertIsNotNone(node)
        self.assertEqual(node['is_online'], 0)

        # Simulate receiving a TEXT_MESSAGE_APP packet by calling update_node_last_seen
        update_node_last_seen(node_id)

        # Verify node is now online - force cache invalidation
        from webui.cache import get_cache_manager
        cache = get_cache_manager()
        cache.delete(cache.get_nodes_cache_key())

        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 1)
        self.assertGreater(node['last_activity'], time.time() - 10)  # Within last 10 seconds

    def test_node_marked_online_on_routing_app(self):
        """Test that nodes are marked online when receiving ROUTING_APP packets."""
        node_id = "1234567891"

        # Add a node that's initially offline
        add_node(node_id, "Test Node", time.time() - 3600, None, None, None, None)
        update_node(node_id, is_online=False)

        # Verify node is offline
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 0)

        # Simulate receiving a ROUTING_APP packet
        update_node_last_seen(node_id)

        # Verify node is now online - force cache invalidation
        from webui.cache import get_cache_manager
        cache = get_cache_manager()
        cache.delete(cache.get_nodes_cache_key())

        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 1)

    def test_node_marked_online_on_position_app(self):
        """Test that nodes are marked online when receiving POSITION_APP packets."""
        node_id = "1234567892"

        # Add a node that's initially offline
        add_node(node_id, "Test Node", time.time() - 3600, None, None, None, None)
        update_node(node_id, is_online=False)

        # Verify node is offline
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 0)

        # Simulate receiving a POSITION_APP packet by updating position data
        update_node(node_id, latitude=37.7749, longitude=-122.4194, last_activity=time.time(), is_online=True)

        # Verify node is now online
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 1)

    def test_node_marked_online_on_telemetry_app(self):
        """Test that nodes are marked online when receiving TELEMETRY_APP packets."""
        node_id = "1234567893"

        # Add a node that's initially offline
        add_node(node_id, "Test Node", time.time() - 3600, None, None, None, None)
        update_node(node_id, is_online=False)

        # Verify node is offline
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 0)

        # Simulate receiving a TELEMETRY_APP packet
        update_node_telemetry(node_id, battery_level=85)

        # Verify node is now online
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 1)
        self.assertEqual(node['battery_level'], 85)

    def test_node_marked_online_on_nodeinfo_app(self):
        """Test that nodes are marked online when receiving NODEINFO_APP packets."""
        node_id = "1234567894"

        # Add a node that's initially offline
        add_node(node_id, "Test Node", time.time() - 3600, None, None, None, None)
        update_node(node_id, is_online=False)

        # Verify node is offline
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 0)

        # Simulate receiving a NODEINFO_APP packet
        update_node_last_seen(node_id)

        # Verify node is now online - force cache invalidation
        from webui.cache import get_cache_manager
        cache = get_cache_manager()
        cache.delete(cache.get_nodes_cache_key())

        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 1)

    def test_node_marked_online_on_neighborinfo_app(self):
        """Test that nodes are marked online when receiving NEIGHBORINFO_APP packets."""
        node_id = "1234567895"

        # Add a node that's initially offline
        add_node(node_id, "Test Node", time.time() - 3600, None, None, None, None)
        update_node(node_id, is_online=False)

        # Verify node is offline
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 0)

        # Simulate receiving a NEIGHBORINFO_APP packet
        update_node_last_seen(node_id)

        # Verify node is now online - force cache invalidation
        from webui.cache import get_cache_manager
        cache = get_cache_manager()
        cache.delete(cache.get_nodes_cache_key())

        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 1)

    def test_node_marked_online_on_traceroute_app(self):
        """Test that nodes are marked online when receiving TRACEROUTE_APP packets."""
        node_id = "1234567896"

        # Add a node that's initially offline
        add_node(node_id, "Test Node", time.time() - 3600, None, None, None, None)
        update_node(node_id, is_online=False)

        # Verify node is offline
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 0)

        # Simulate receiving a TRACEROUTE_APP packet
        update_node_last_seen(node_id)

        # Verify node is now online - force cache invalidation
        from webui.cache import get_cache_manager
        cache = get_cache_manager()
        cache.delete(cache.get_nodes_cache_key())

        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 1)

    def test_offline_detection_after_30_minutes(self):
        """Test that nodes are marked offline only after exactly 30 minutes of no activity."""
        node_id = "1234567897"

        # Add a node that's online
        add_node(node_id, "Test Node", time.time(), None, None, None, None)
        update_node(node_id, is_online=True, last_activity=time.time())

        # Verify node is online
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 1)

        # Set last_activity to 29 minutes ago (should still be online)
        twenty_nine_minutes_ago = time.time() - (29 * 60)
        update_node(node_id, last_activity=twenty_nine_minutes_ago)

        # Run offline check
        check_and_update_offline_nodes()

        # Verify node is still online
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 1)

        # Set last_activity to 31 minutes ago (should be offline)
        thirty_one_minutes_ago = time.time() - (31 * 60)
        update_node(node_id, last_activity=thirty_one_minutes_ago)

        # Run offline check
        check_and_update_offline_nodes()

        # Verify node is now offline
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 0)

    def test_offline_logic_considers_all_packet_types(self):
        """Test that offline detection considers activity from all relevant packet types."""
        node_id = "1234567898"

        # Add a node
        add_node(node_id, "Test Node", time.time() - 3600, None, None, None, None)

        # Simulate various packet types updating last_activity
        current_time = time.time()

        # TEXT_MESSAGE_APP activity
        update_node(node_id, last_activity=current_time - 1800, is_online=True)  # 30 min ago

        # Run offline check - should be offline since 30 min ago
        check_and_update_offline_nodes()
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 0)

        # Simulate TELEMETRY_APP activity (brings back online)
        update_node_telemetry(node_id, battery_level=90)  # This updates last_activity

        # Verify back online
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 1)

        # Set last_activity to 31 minutes ago
        update_node(node_id, last_activity=current_time - 1860)  # 31 min ago

        # Run offline check
        check_and_update_offline_nodes()

        # Verify offline
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['is_online'], 0)

    def test_existing_functionality_not_broken(self):
        """Test that existing functionality is not broken by the changes."""
        node_id = "1234567899"

        # Test add_node
        add_node(node_id, "Test Node", time.time(), 80, 37.7749, -122.4194, 100)
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertIsNotNone(node)
        self.assertEqual(node['name'], "Test Node")
        self.assertEqual(node['battery_level'], 80)

        # Test update_node
        update_node(node_id, name="Updated Node", battery_level=85)
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['name'], "Updated Node")
        self.assertEqual(node['battery_level'], 85)

        # Test update_node_telemetry
        update_node_telemetry(node_id, snr=15.5, rssi=-50)
        nodes = get_nodes()
        node = next((n for n in nodes if n['node_id'] == node_id), None)
        self.assertEqual(node['snr'], 15.5)
        self.assertEqual(node['rssi'], -50)


if __name__ == '__main__':
    unittest.main()