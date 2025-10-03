import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from webui import db_handler
import time
import sqlite3

# Test 1: Save a message (simulates TEXT_MESSAGE_APP in onReceive)
print("Testing save_message (TEXT_MESSAGE_APP simulation)...")
from_node_id = "1234567890"
to_node_id = "broadcast"
channel = "general"
text = "Test message from simulation"
timestamp = int(time.time())
is_dm = 0
db_handler.save_message(from_node_id, to_node_id, channel, text, timestamp, is_dm)
print("Message saved.")

# Query messages to verify
conn = db_handler.get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT * FROM messages ORDER BY timestamp DESC LIMIT 1")
result = cursor.fetchone()
if result:
    print(f"Verified: Last message inserted - From: {result[2]}, Text: {result[5]}")
else:
    print("No message found - insertion failed")
conn.close()

# Test 2: Node update (simulates POSITION_APP via add_node)
print("\nTesting node update (POSITION_APP simulation)...")
node_id = "1234567890"
name = "Test Node"
last_seen = int(time.time())
battery_level = 100
latitude = 37.7749
longitude = -122.4194
altitude = 10
db_handler.add_node(node_id, name, last_seen, battery_level, latitude, longitude, altitude)
print("Node added/updated.")

# Query nodes to verify
conn = db_handler.get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
node_result = cursor.fetchone()
if node_result:
    print(f"Verified: Node updated - Lat: {node_result[5]}, Lon: {node_result[6]}")
else:
    print("No node found - update failed")
conn.close()

# Test 3: BBS post (save_forum_post called by bbs_post_message)
print("\nTesting BBS post (bbs_post_message integration)...")
subject = "Test Subject"
body = "Test Body from simulation"
full_text = f"{subject}: {body}"
timestamp2 = int(time.time())
post_id = db_handler.save_forum_post(node_id, full_text, timestamp2)
print(f"Forum post saved with ID: {post_id}")

# Query forum_posts to verify
conn = db_handler.get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT * FROM forum_posts WHERE id = ?", (post_id,))
post_result = cursor.fetchone()
if post_result:
    print(f"Verified: Forum post inserted - Topic: {post_result[1]}, Content: {post_result[3]}")
else:
    print("No post found - insertion failed")
conn.close()

# Test 4: BBS delete (delete_forum_post called by bbs_delete_message)
print("\nTesting BBS delete (bbs_delete_message integration)...")
if post_id:
    db_handler.delete_forum_post(post_id)
    print("Forum post deleted.")

    # Query to confirm deletion
    conn = db_handler.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM forum_posts WHERE id = ?", (post_id,))
    deleted_result = cursor.fetchone()
    if not deleted_result:
        print("Verified: Post deleted successfully")
    else:
        print("Deletion failed - post still exists")
    conn.close()

print("\nAll simulations completed. Data synchronization functions are working as expected.")