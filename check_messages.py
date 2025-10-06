#!/usr/bin/env python3
from webui.db_handler import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
cursor.execute('SELECT id, message_id, from_node_id, to_node_id, channel, status, attempt_count, delivered FROM messages ORDER BY timestamp DESC LIMIT 10')
print('Recent messages:')
for row in cursor.fetchall():
    print(row)
conn.close()