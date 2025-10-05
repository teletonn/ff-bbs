import sqlite3

def apply_db_changes():
    conn = sqlite3.connect('webui/dashboard.db')
    cursor = conn.cursor()

    # Enable WAL mode
    cursor.execute('PRAGMA journal_mode=WAL;')

    # Since SQLite doesn't support ALTER CONSTRAINT, we need to recreate the table
    # First, backup the data
    cursor.execute("CREATE TABLE messages_backup AS SELECT * FROM messages;")

    # Drop the old table
    cursor.execute("DROP TABLE messages;")

    # Create the new table with correct constraint
    cursor.execute('''
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id TEXT UNIQUE,
        from_node_id TEXT,
        to_node_id TEXT,
        channel TEXT,
        text TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_dm BOOLEAN,
        delivered BOOLEAN DEFAULT 0,
        retry_count INTEGER DEFAULT 0,
        delivery_attempts INTEGER DEFAULT 0,
        status TEXT DEFAULT 'sent' CHECK (status IN ('sent', 'queued', 'delivered', 'undelivered')),
        attempt_count INTEGER DEFAULT 0,
        last_attempt_time TIMESTAMP,
        next_retry_time TIMESTAMP,
        error_message TEXT,
        defer_count INTEGER DEFAULT 0
    )
    ''')

    # Copy data back
    cursor.execute('''
    INSERT INTO messages (
        id, message_id, from_node_id, to_node_id, channel, text, timestamp, is_dm,
        delivered, retry_count, delivery_attempts, status, attempt_count,
        last_attempt_time, next_retry_time, error_message, defer_count
    )
    SELECT
        id, message_id, from_node_id, to_node_id, channel, text, timestamp, is_dm,
        delivered, retry_count, delivery_attempts,
        CASE WHEN status = 'failed' THEN 'undelivered' ELSE status END,
        attempt_count, last_attempt_time, next_retry_time, error_message, defer_count
    FROM messages_backup;
    ''')

    # Drop backup table
    cursor.execute("DROP TABLE messages_backup;")

    # Recreate indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_from_node_id ON messages(from_node_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_to_node_id ON messages(to_node_id)')

    conn.commit()
    conn.close()
    print("Database changes applied successfully.")

if __name__ == '__main__':
    apply_db_changes()