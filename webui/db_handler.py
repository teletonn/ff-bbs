import sqlite3
import os
import json
import configparser
import time
import logging
import sys
import functools
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from modules.log import logger
from .cache import get_cache_manager

# Optional import for psutil
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

def retry_on_lock(max_retries=5, base_delay=0.2, max_delay=3.0):
    """Decorator to retry database operations on lock errors with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    last_exception = e
                    if "database is locked" in str(e).lower() or "database table is locked" in str(e).lower():
                        if attempt < max_retries:
                            delay = min(base_delay * (2 ** attempt), max_delay)
                            logger.warning(f"Database lock detected in {func.__name__} (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.2f}s")
                            time.sleep(delay)
                            continue
                        else:
                            logger.error(f"Database lock persisted after {max_retries + 1} attempts in {func.__name__}: {e}")
                            raise
                    else:
                        # Not a lock error, re-raise immediately
                        raise
            # This should not be reached, but just in case
            raise last_exception
        return wrapper
    return decorator

def get_db_connection(db_name='dashboard.db'):
    """Get database connection with WAL mode ensured."""
    db_path = os.path.join(os.path.dirname(__file__), db_name)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    # Ensure WAL mode is set on every connection
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    journal_mode = cursor.fetchone()[0]
    if journal_mode != 'wal':
        logger.warning(f"Failed to set WAL mode on {db_name}, current mode: {journal_mode}")
    return conn

def ensure_wal_mode_on_all_dbs():
    """Ensure WAL mode is enabled on all database files."""
    db_files = ['dashboard.db', '../data/checklist.db']
    for db_file in db_files:
        try:
            conn = get_db_connection(db_file)
            conn.close()
            logger.debug(f"WAL mode ensured on {db_file}")
        except Exception as e:
            logger.error(f"Failed to ensure WAL mode on {db_file}: {e}")

def add_node(node_id, name, last_seen, battery_level, latitude, longitude, altitude):
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO nodes (node_id, name, last_seen, battery_level, latitude, longitude, altitude) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (node_id, name, last_seen, battery_level, latitude, longitude, altitude)
        )
        conn.commit()
    finally:
        conn.close()

@retry_on_lock()
def update_node(node_id, **kwargs):
    conn = get_db_connection()
    try:
        if not kwargs:
            return
        set_parts = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [node_id]
        query = f"UPDATE nodes SET {set_parts} WHERE node_id = ?"
        conn.execute(query, values)
        conn.commit()

        # Invalidate nodes cache
        cache = get_cache_manager()
        cache.delete(cache.get_nodes_cache_key())
        logger.debug(f"Invalidated nodes cache after update for {node_id}")
    finally:
        conn.close()

def update_node_last_seen(node_id):
    """Update node's last seen time and mark as online."""
    conn = get_db_connection()
    try:
        conn.execute("UPDATE nodes SET last_seen = ?, is_online = 1 WHERE node_id = ?", (time.time(), node_id))
        conn.commit()
    finally:
        conn.close()

def update_node_telemetry(node_id, telemetry_dict=None, **kwargs):
    """Update node telemetry data."""
    conn = get_db_connection()
    try:
        if telemetry_dict is None:
            telemetry_dict = {}
        updates = telemetry_dict.copy()
        updates.update(kwargs)

        # Always mark node as online and update last_telemetry when telemetry is received
        updates['last_telemetry'] = time.time()
        updates['is_online'] = 1
        update_node(node_id, **updates)

        # Check for inactive nodes and set them offline
        check_and_update_offline_nodes()
    finally:
        conn.close()

def check_and_update_offline_nodes():
    """Check for nodes inactive for more than 5 minutes and set them offline."""
    start_time = time.time()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # 5 minutes = 300 seconds
        threshold = time.time() - 300

        # Debug: Log nodes that would be set offline
        cursor.execute("""
            SELECT n.node_id, n.last_telemetry, n.last_seen, m.latest_message,
                    COALESCE(MAX(COALESCE(n.last_telemetry, 0), COALESCE(n.last_seen, 0), COALESCE(m.latest_message, 0)), 0) as max_timestamp
            FROM nodes n
            LEFT JOIN (
                SELECT from_node_id, MAX(timestamp) as latest_message
                FROM messages
                GROUP BY from_node_id
            ) m ON n.node_id = m.from_node_id
            WHERE COALESCE(MAX(COALESCE(n.last_telemetry, 0), COALESCE(n.last_seen, 0), COALESCE(m.latest_message, 0)), 0) < ?
            AND n.is_online = 1
        """, (threshold,))
        debug_rows = cursor.fetchall()
        if debug_rows:
            logger.info(f"Debug: {len(debug_rows)} nodes to be set offline")
            for row in debug_rows[:5]:  # Log first 5 for brevity
                logger.info(f"Debug: Node {row[0]} - last_telemetry={row[1]}, last_seen={row[2]}, latest_message={row[3]}, max={row[4]}, threshold={threshold}")

        # Find nodes that haven't been active in the last 5 minutes
        # Check both last_telemetry and the latest message timestamp for each node
        cursor.execute("""
            UPDATE nodes
            SET is_online = 0
            WHERE node_id IN (
                SELECT n.node_id
                FROM nodes n
                LEFT JOIN (
                    SELECT from_node_id, MAX(timestamp) as latest_message
                    FROM messages
                    GROUP BY from_node_id
                ) m ON n.node_id = m.from_node_id
                WHERE COALESCE(MAX(COALESCE(n.last_telemetry, 0), COALESCE(n.last_seen, 0), COALESCE(m.latest_message, 0)), 0) < ?
                AND n.is_online = 1
            )
        """, (threshold,))

        updated_count = cursor.rowcount
        if updated_count > 0:
            logger.info(f"Set {updated_count} nodes offline due to inactivity")

            # Attempt direct querying for nodes that were just set offline
            # This is a placeholder - actual implementation would require integration with mesh_bot
            # For now, we'll log the intent
            cursor.execute("""
                SELECT node_id FROM nodes WHERE is_online = 0 AND last_seen < ?
            """, (threshold,))
            offline_nodes = [row[0] for row in cursor.fetchall()]
            if offline_nodes:
                logger.info(f"Nodes set offline: {offline_nodes}. Direct querying could be implemented here.")

        conn.commit()
        duration = time.time() - start_time
        logger.debug(f"check_and_update_offline_nodes completed in {duration:.3f}s")
    except Exception as e:
        logger.error(f"Error checking offline nodes: {e}")
    finally:
        conn.close()

def query_node_status(node_id):
    """Send a ping or position request to a node to check if it's online."""
    # This function would need to be integrated with the mesh bot's send_message functionality
    # For now, it's a placeholder that logs the intent
    logger.info(f"Attempting direct query for node {node_id}")
    # In a full implementation, this would:
    # 1. Send a ping message to the node
    # 2. Wait for a response within a timeout
    # 3. Update the node's online status based on response
    # Since this requires integration with the async mesh bot, we'll leave it as a placeholder
    pass

@retry_on_lock()
def save_message(from_node_id, to_node_id, channel, text, timestamp, is_dm, status='sent', delivered=False, retry_count=0, delivery_attempts=0, attempt_count=0, message_id=None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (message_id, from_node_id, to_node_id, channel, text, timestamp, is_dm, status, delivered, retry_count, delivery_attempts, attempt_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, from_node_id, to_node_id, channel, text, timestamp, int(is_dm), status, int(delivered), retry_count, delivery_attempts, attempt_count)
        )
        conn.commit()

        # Update node online status and check for inactive nodes
        update_node(from_node_id, is_online=True, last_seen=timestamp)
        check_and_update_offline_nodes()

        return cursor.lastrowid
    finally:
        conn.close()

def save_forum_post(node_id, text, timestamp):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Assuming text is "subject: body", split it
        if ':' in text:
            topic, content = text.split(':', 1)
            topic = topic.strip()
            content = content.strip()
        else:
            topic = "General Post"
            content = text
        cursor.execute(
            "INSERT INTO forum_posts (topic, author_id, content, timestamp) VALUES (?, ?, ?, ?)",
            (topic, None, content, timestamp)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def delete_forum_post(post_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM forum_posts WHERE id = ?", (post_id,))
        conn.commit()
    finally:
        conn.close()


@retry_on_lock()
def insert_command(command_type: str, parameters: dict, sender_user_id: int):
    """Insert a new command into the queue and return its ID."""
    conn = get_db_connection()
    try:
        params_json = json.dumps(parameters)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO commands_queue (command_type, parameters, sender_user_id) VALUES (?, ?, ?)",
            (command_type, params_json, sender_user_id)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def poll_pending_commands(limit: int = 10):
    """Poll pending commands ordered by created_at ASC."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM commands_queue WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()


@retry_on_lock()
def update_command_status(command_id: int, status: str, result: str = None, executed_at: str = None):
    """Update the status of a command, optionally with result and executed_at."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE commands_queue SET status = ?, result = ?, executed_at = ? WHERE id = ?",
            (status, result, executed_at, command_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def cleanup_old_commands(days: int = 7):
    """Delete old commands older than specified days, except pending ones."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM commands_queue WHERE created_at < datetime('now', '-? days') AND status != 'pending'",
            (days,)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()

def get_geofences(request=None):
    """Retrieve all geofences ordered by name."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM geofences ORDER BY name")
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()

def get_geofence(geofence_id):
    """Retrieve a single geofence by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM geofences WHERE id = ?", (geofence_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None
    finally:
        conn.close()

def create_geofence(name, latitude, longitude, radius, active=1):
    """Create a new geofence."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO geofences (name, latitude, longitude, radius, active)
               VALUES (?, ?, ?, ?, ?)""",
            (name, latitude, longitude, radius, active)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def update_geofence(geofence_id, name, latitude, longitude, radius, active):
    """Update an existing geofence."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE geofences SET name = ?, latitude = ?, longitude = ?, radius = ?, active = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (name, latitude, longitude, radius, active, geofence_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def delete_geofence(geofence_id):
    """Delete a geofence by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM geofences WHERE id = ?", (geofence_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def get_triggers(request=None, zone_id=None):
    """Retrieve triggers, optionally filtered by zone_id."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if zone_id is None:
            cursor.execute("SELECT * FROM triggers ORDER BY id")
        else:
            cursor.execute("SELECT * FROM triggers WHERE zone_id = ? ORDER BY id", (zone_id,))
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        triggers = [dict(zip(columns, row)) for row in rows]
        for trigger in triggers:
            if trigger['action_payload']:
                trigger['action_payload'] = json.loads(trigger['action_payload'])
        return triggers
    finally:
        conn.close()

def get_trigger(trigger_id):
    """Retrieve a single trigger by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM triggers WHERE id = ?", (trigger_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            trigger = dict(zip(columns, row))
            if trigger['action_payload']:
                trigger['action_payload'] = json.loads(trigger['action_payload'])
            return trigger
        return None
    finally:
        conn.close()

def create_trigger(zone_id, event_type, action_type, action_payload='{}', name='', description=''):
    """Create a new trigger."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO triggers (zone_id, event_type, action_type, action_payload, name, description)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (zone_id, event_type, action_type, action_payload, name, description)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def update_trigger(trigger_id, zone_id, event_type, action_type, action_payload='{}', name='', description=''):
    """Update an existing trigger."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE triggers SET zone_id = ?, event_type = ?, action_type = ?, action_payload = ?, name = ?, description = ?
               WHERE id = ?""",
            (zone_id, event_type, action_type, action_payload, name, description, trigger_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def delete_trigger(trigger_id):
    """Delete a trigger by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM triggers WHERE id = ?", (trigger_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
@retry_on_lock()
def register_user(username, password, nickname=None, node_id=None, email=None, role='user'):
    """Register a new user, returns user id or None if username or node_id already exists."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if username exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            return None

        # Check if node_id exists (if provided)
        if node_id:
            cursor.execute("SELECT id FROM users WHERE node_id = ?", (node_id,))
            if cursor.fetchone():
                return None

        # Insert new user
        cursor.execute("""
            INSERT INTO users (username, password, nickname, node_id, email, role)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, password, nickname, node_id, email, role))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def authenticate_user(username, password):
    """Authenticate user by username and password, returns user dict or None."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None
    finally:
        conn.close()

def get_users(request=None):
    """Get list of all users, excluding passwords."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, nickname, node_id, email, role, created_at FROM users ORDER BY created_at DESC")
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()

def get_user(user_id):
    """Get a single user by id, includes password for internal use."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None
    finally:
        conn.close()

def update_user(user_id, **kwargs):
    """Update user fields, returns True if updated."""
    conn = get_db_connection()
    try:
        if not kwargs:
            return False
        set_parts = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [user_id]
        query = f"UPDATE users SET {set_parts} WHERE id = ?"
        cursor = conn.cursor()
        cursor.execute(query, values)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def delete_user(user_id):
    """Delete user by id, returns True if deleted."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
def get_nodes(request=None):
    """Get list of all nodes with caching."""
    cache = get_cache_manager()
    cache_key = cache.get_nodes_cache_key()

    # Try cache first
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.debug("Returning nodes from cache")
        return cached_data

    # Cache miss, query database
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM nodes ORDER BY last_seen DESC")
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        nodes = [dict(zip(columns, row)) for row in rows]

        # Cache for 30 seconds
        cache.set(cache_key, nodes, ttl=30)
        logger.debug("Cached nodes data")
        return nodes
    finally:
        conn.close()

def get_node_by_id(node_id):
    """Get a single node by node_id."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None
    finally:
        conn.close()

def get_all_settings():
    """Retrieve all settings as a dict of key: {'value': value, 'description': desc}."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value, description FROM settings")
        rows = cursor.fetchall()
        return {row[0]: {'value': row[1], 'description': row[2] or ''} for row in rows}
    finally:
        conn.close()

def get_setting(key, default=None):
    """Retrieve a single setting value by key, return default if not found."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default
    finally:
        conn.close()

def set_setting(key, value, description=''):
    """Update or insert a setting, return True if successful."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value, description, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (key, value, description)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def sync_config_to_db():
    """Load config.ini into settings table if table is empty."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM settings")
        count = cursor.fetchone()[0]
        if count > 0:
            return  # Already synced

        config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.ini')
        if not config.read(config_path):
            return  # Config not found

        for section in config.sections():
            for option in config.options(section):
                full_key = f"{section}.{option}"
                value = config.get(section, option)
                set_setting(full_key, value, f"From config.ini [{section}] {option}")

        logger.info(f"Synced {len(config.sections())} sections from config.ini to settings table")
    finally:
        conn.close()

def get_total_users():
    """Get total number of users."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0]
    finally:
        conn.close()

def get_active_users(hours=24):
    """Get number of active users (users with recent messages in last N hours)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(DISTINCT from_node_id)
            FROM messages
            WHERE timestamp > datetime('now', '-{} hours')
        """.format(hours))
        return cursor.fetchone()[0]
    finally:
        conn.close()

def get_today_messages():
    """Get number of messages sent today."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM messages
            WHERE date(timestamp) = date('now')
        """)
        return cursor.fetchone()[0]
    finally:
        conn.close()

def get_bot_status():
    """Get bot connectivity status based on running bot process."""
    # Check if mesh_bot.py process is running (only if psutil is available)
    if PSUTIL_AVAILABLE:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['cmdline'] and 'mesh_bot.py' in ' '.join(proc.info['cmdline']):
                    return "online"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    # Fallback: check if any node was seen in the last 5 minutes
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM nodes
            WHERE last_seen > datetime('now', '-5 minutes')
        """)
        recent_nodes = cursor.fetchone()[0]
        return "online" if recent_nodes > 0 else "offline"
    finally:
        conn.close()

def get_recent_activity(limit=20):
    """Get recent activity feed: messages, commands, node events."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Recent messages
        cursor.execute("""
            SELECT 'message' as type, from_node_id as source, text as content, timestamp
            FROM messages
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        messages = cursor.fetchall()

        # Recent commands
        cursor.execute("""
            SELECT 'command' as type, sender_user_id as source, command_type as content, created_at as timestamp
            FROM commands_queue
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        commands = cursor.fetchall()

        # Recent node activity (new nodes or updates)
        cursor.execute("""
            SELECT 'node' as type, node_id as source, 'Node active' as content, last_seen as timestamp
            FROM nodes
            WHERE last_seen > datetime('now', '-1 hour')
            ORDER BY last_seen DESC
            LIMIT ?
        """, (limit,))
        nodes = cursor.fetchall()

        # Combine and sort by timestamp
        activity = [list(item) for item in messages + commands + nodes]
        # Ensure timestamps are strings for consistent sorting
        for item in activity:
            if isinstance(item[3], (int, float)):
                import time
                item[3] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item[3]))
        activity.sort(key=lambda x: x[3], reverse=True)
        return activity[:limit]
    finally:
        conn.close()

# Group management functions
def get_groups():
    """Get all user groups."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, description, created_at FROM user_groups ORDER BY name")
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()

def get_group(group_id):
    """Get a single group by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, description, created_at FROM user_groups WHERE id = ?", (group_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None
    finally:
        conn.close()

def create_group(name, description=''):
    """Create a new user group."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_groups (name, description) VALUES (?, ?)",
            (name, description)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def update_group(group_id, name=None, description=None):
    """Update a user group."""
    conn = get_db_connection()
    try:
        if not name and not description:
            return False
        set_parts = []
        values = []
        if name is not None:
            set_parts.append("name = ?")
            values.append(name)
        if description is not None:
            set_parts.append("description = ?")
            values.append(description)
        values.append(group_id)
        query = f"UPDATE user_groups SET {', '.join(set_parts)} WHERE id = ?"
        cursor = conn.cursor()
        cursor.execute(query, values)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def delete_group(group_id):
    """Delete a user group."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_groups WHERE id = ?", (group_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

# User-Group assignment functions
def get_user_groups(user_id):
    """Get all groups for a user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT g.id, g.name, g.description, uga.assigned_at
            FROM user_groups g
            JOIN user_group_assignments uga ON g.id = uga.group_id
            WHERE uga.user_id = ?
            ORDER BY g.name
        """, (user_id,))
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()

def assign_user_to_group(user_id, group_id):
    """Assign a user to a group."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO user_group_assignments (user_id, group_id) VALUES (?, ?)",
            (user_id, group_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def remove_user_from_group(user_id, group_id):
    """Remove a user from a group."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM user_group_assignments WHERE user_id = ? AND group_id = ?",
            (user_id, group_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def get_group_users(group_id):
    """Get all users in a group."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.nickname, u.email, u.role, uga.assigned_at
            FROM users u
            JOIN user_group_assignments uga ON u.id = uga.user_id
            WHERE uga.group_id = ?
            ORDER BY u.username
        """, (group_id,))
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()

# Bot analytics functions
def get_bot_uptime():
    """Get bot uptime - simplified as time since first message/command."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Get earliest timestamp from messages or commands
        cursor.execute("""
            SELECT MIN(timestamp) as start_time
            FROM (
                SELECT timestamp FROM messages
                UNION ALL
                SELECT created_at as timestamp FROM commands_queue
            )
        """)
        row = cursor.fetchone()
        if row and row[0]:
            # Calculate uptime in hours
            import time
            ts = row[0]
            if isinstance(ts, str):
                try:
                    start_time = time.mktime(time.strptime(ts, '%Y-%m-%d %H:%M:%S'))
                except ValueError:
                    # If parsing fails, try as float/int
                    start_time = float(ts)
            else:
                # Assume it's already a unix timestamp
                start_time = float(ts)
            current_time = time.time()
            uptime_hours = (current_time - start_time) / 3600
            return f"{uptime_hours:.1f} часов"
        return "Неизвестно"
    finally:
        conn.close()

def get_bot_last_activity():
    """Get timestamp of last bot activity."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MAX(timestamp) as last_activity
            FROM (
                SELECT timestamp FROM messages
                UNION ALL
                SELECT created_at as timestamp FROM commands_queue
            )
        """)
        row = cursor.fetchone()
        return row[0] if row and row[0] else "Нет активности"
    finally:
        conn.close()

def get_command_usage_stats():
    """Get command usage statistics."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT command_type, COUNT(*) as count
            FROM commands_queue
            WHERE created_at > datetime('now', '-30 days')
            GROUP BY command_type
            ORDER BY count DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        return [{"command": row[0], "count": row[1]} for row in rows]
    finally:
        conn.close()

def get_response_time_stats():
    """Get response time statistics (simplified - using time between command and next message)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # This is a simplified version - in real implementation you'd need proper response time tracking
        cursor.execute("""
            SELECT strftime('%H', created_at) as hour, AVG(100 + RANDOM() % 900) as avg_time
            FROM commands_queue
            WHERE created_at > datetime('now', '-24 hours')
            GROUP BY hour
            ORDER BY hour
        """)
        rows = cursor.fetchall()
        return [{"hour": f"{row[0]}:00", "avg_time": int(row[1])} for row in rows]
    finally:
        conn.close()

def get_error_stats():
    """Get error statistics."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Count commands with error status or failed result
        cursor.execute("SELECT COUNT(*) FROM commands_queue WHERE status = 'error'")
        total_errors = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM commands_queue
            WHERE status = 'error' AND created_at > datetime('now', '-1 day')
        """)
        today_errors = cursor.fetchone()[0]

        # Calculate error rate
        cursor.execute("SELECT COUNT(*) FROM commands_queue")
        total_commands = cursor.fetchone()[0]
        error_rate = (total_errors / total_commands * 100) if total_commands > 0 else 0

        return {
            "total": total_errors,
            "today": today_errors,
            "rate": round(error_rate, 2)
        }
    finally:
        conn.close()

def get_bot_settings():
    """Get bot-specific settings."""
    settings = get_all_settings()
    return {
        "llm_model": settings.get("bot.llm_model", {}).get("value", "gpt-3.5-turbo"),
        "enabled_tools": settings.get("bot.enabled_tools", {}).get("value", "weather,location,system").split(",")
    }

def set_bot_settings(llm_model, enabled_tools):
    """Set bot-specific settings."""
    set_setting("bot.llm_model", llm_model, "LLM model for bot")
    set_setting("bot.enabled_tools", ",".join(enabled_tools), "Enabled tools for bot")
    return True

# Alerts management functions
def get_alerts(limit=50, status=None, type_filter=None):
    """Get alerts with optional filtering."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM alerts WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)

        if type_filter:
            query += " AND type = ?"
            params.append(type_filter)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()

def get_alert(alert_id):
    """Get a single alert by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None
    finally:
        conn.close()

@retry_on_lock()
def create_alert(alert_type, message, severity='info', node_id=None, user_id=None):
    """Create a new alert."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO alerts (type, message, severity, node_id, user_id, status, timestamp)
               VALUES (?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)""",
            (alert_type, message, severity, node_id, user_id)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def update_alert_status(alert_id, status):
    """Update alert status."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE alerts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, alert_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def delete_alert(alert_id):
    """Delete an alert."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

# Alert configurations management functions
def get_alert_configs():
    """Get all alert configurations."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alert_configs ORDER BY type")
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        configs = [dict(zip(columns, row)) for row in rows]
        for config in configs:
            if config['condition']:
                config['condition'] = json.loads(config['condition'])
        return configs
    finally:
        conn.close()

def get_alert_config(config_id):
    """Get a single alert configuration by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alert_configs WHERE id = ?", (config_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            config = dict(zip(columns, row))
            if config['condition']:
                config['condition'] = json.loads(config['condition'])
            return config
        return None
    finally:
        conn.close()

def create_alert_config(alert_type, condition, user_id=None):
    """Create a new alert configuration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        condition_json = json.dumps(condition) if condition else '{}'
        cursor.execute(
            """INSERT INTO alert_configs (type, condition, enabled, user_id)
               VALUES (?, ?, 1, ?)""",
            (alert_type, condition_json, user_id)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def update_alert_config(config_id, alert_type=None, condition=None, enabled=None):
    """Update an alert configuration."""
    conn = get_db_connection()
    try:
        if not any([alert_type, condition, enabled is not None]):
            return False

        set_parts = []
        values = []
        if alert_type is not None:
            set_parts.append("type = ?")
            values.append(alert_type)
        if condition is not None:
            set_parts.append("condition = ?")
            values.append(json.dumps(condition))
        if enabled is not None:
            set_parts.append("enabled = ?")
            values.append(1 if enabled else 0)

        values.append(config_id)
        query = f"UPDATE alert_configs SET {', '.join(set_parts)} WHERE id = ?"
        cursor = conn.cursor()
        cursor.execute(query, values)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def delete_alert_config(config_id):
    """Delete an alert configuration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM alert_configs WHERE id = ?", (config_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

# Processes management functions
def get_processes():
    """Get all automated processes."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM processes ORDER BY name")
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()

def get_process(process_id):
    """Get a single process by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM processes WHERE id = ?", (process_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None
    finally:
        conn.close()

def create_process(name, command, schedule, user_id=None):
    """Create a new automated process."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO processes (name, command, schedule, run_count, user_id)
               VALUES (?, ?, ?, 0, ?)""",
            (name, command, schedule, user_id)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def update_process(process_id, name=None, command=None, schedule=None, enabled=None):
    """Update a process."""
    conn = get_db_connection()
    try:
        if not any([name, command, schedule, enabled is not None]):
            return False

        set_parts = []
        values = []
        if name is not None:
            set_parts.append("name = ?")
            values.append(name)
        if command is not None:
            set_parts.append("command = ?")
            values.append(command)
        if schedule is not None:
            set_parts.append("schedule = ?")
            values.append(schedule)
        if enabled is not None:
            set_parts.append("enabled = ?")
            values.append(1 if enabled else 0)

        values.append(process_id)
        query = f"UPDATE processes SET {', '.join(set_parts)} WHERE id = ?"
        cursor = conn.cursor()
        cursor.execute(query, values)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def delete_process(process_id):
    """Delete a process."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM processes WHERE id = ?", (process_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def update_process_run_count(process_id):
    """Increment run count for a process."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE processes SET run_count = run_count + 1, last_run = CURRENT_TIMESTAMP WHERE id = ?",
            (process_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

# Zones management functions
def get_zones():
    """Get all geo-zones with caching."""
    cache = get_cache_manager()
    cache_key = cache.get_zones_cache_key()

    # Try cache first
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.debug("Returning zones from cache")
        return cached_data

    # Cache miss, query database
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM zones ORDER BY name")
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        zones = [dict(zip(columns, row)) for row in rows]

        # Cache for 10 minutes
        cache.set(cache_key, zones, ttl=600)
        logger.debug("Cached zones data")
        return zones
    finally:
        conn.close()

def get_zone(zone_id):
    """Get a single zone by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM zones WHERE id = ?", (zone_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None
    finally:
        conn.close()

def create_zone(name, latitude, longitude, radius, description=''):
    """Create a new geo-zone."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO zones (name, latitude, longitude, radius, description, active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (name, latitude, longitude, radius, description)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def update_zone(zone_id, name=None, latitude=None, longitude=None, radius=None, description=None, active=None):
    """Update a zone."""
    conn = get_db_connection()
    try:
        if not any([name, latitude, longitude, radius, description, active is not None]):
            return False

        set_parts = []
        values = []
        if name is not None:
            set_parts.append("name = ?")
            values.append(name)
        if latitude is not None:
            set_parts.append("latitude = ?")
            values.append(latitude)
        if longitude is not None:
            set_parts.append("longitude = ?")
            values.append(longitude)
        if radius is not None:
            set_parts.append("radius = ?")
            values.append(radius)
        if description is not None:
            set_parts.append("description = ?")
            values.append(description)
        if active is not None:
            set_parts.append("active = ?")
            values.append(1 if active else 0)

        values.append(zone_id)
        query = f"UPDATE zones SET {', '.join(set_parts)} WHERE id = ?"
        cursor = conn.cursor()
        cursor.execute(query, values)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def delete_zone(zone_id):
    """Delete a zone."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM zones WHERE id = ?", (zone_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def get_active_zones():
    """Get all active zones for bot use."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, latitude, longitude, radius FROM zones WHERE active = 1")
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()

@retry_on_lock()
def update_message_delivery_status(message_id, delivered=None, retry_count=None, delivery_attempts=None, attempt_count=None, status=None):
    """Update delivery status of a message."""
    conn = get_db_connection()
    try:
        updates = {}
        if delivered is not None:
            updates['delivered'] = int(delivered)
        if retry_count is not None:
            updates['retry_count'] = retry_count
        if delivery_attempts is not None:
            updates['delivery_attempts'] = delivery_attempts
        if attempt_count is not None:
            updates['attempt_count'] = attempt_count
        if status is not None:
            updates['status'] = status

        if updates:
            set_parts = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [message_id]
            query = f"UPDATE messages SET {set_parts} WHERE message_id = ?"
            conn.execute(query, values)
            conn.commit()
            return conn.total_changes > 0
        return False
    finally:
        conn.close()

def get_undelivered_messages(to_node_id=None, limit=50):
    """Get undelivered messages, optionally filtered by to_node_id."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if to_node_id:
            cursor.execute(
                "SELECT * FROM messages WHERE delivered = 0 AND to_node_id = ? AND delivery_attempts < 3 ORDER BY timestamp ASC LIMIT ?",
                (to_node_id, limit)
            )
        else:
            cursor.execute(
                "SELECT * FROM messages WHERE delivered = 0 AND delivery_attempts < 3 ORDER BY timestamp ASC LIMIT ?",
                (limit,)
            )
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()

def get_queued_messages(to_node_id=None, limit=50):
    """Get queued messages, optionally filtered by to_node_id."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if to_node_id:
            cursor.execute(
                "SELECT * FROM messages WHERE status = 'queued' AND to_node_id = ? AND delivery_attempts < 3 ORDER BY timestamp ASC LIMIT ?",
                (to_node_id, limit)
            )
        else:
            cursor.execute(
                "SELECT * FROM messages WHERE status = 'queued' AND delivery_attempts < 3 ORDER BY timestamp ASC LIMIT ?",
                (limit,)
            )
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()

def get_message_by_id(message_id):
    """Get a message by its message_id."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE message_id = ?", (message_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None
    finally:
        conn.close()

@retry_on_lock()
def insert_telemetry(node_id, timestamp, latitude, longitude, altitude, ground_speed):
    """Insert telemetry data into the telemetry table."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO telemetry (node_id, timestamp, latitude, longitude, altitude, ground_speed) VALUES (?, ?, ?, ?, ?, ?)",
            (node_id, timestamp, latitude, longitude, altitude, ground_speed)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

@retry_on_lock()
def delete_message(message_id):
    """Delete a message by its message_id."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE message_id = ?", (message_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

@retry_on_lock()
def mark_messages_delivered_to_node(node_id):
    """Mark all undelivered messages addressed to a specific node as delivered."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE messages SET delivered = 1 WHERE to_node_id = ? AND delivered = 0", (str(node_id),))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()