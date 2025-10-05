import sqlite3

def check_db():
    conn = sqlite3.connect('webui/dashboard.db')
    cursor = conn.cursor()

    # Get table info
    cursor.execute("PRAGMA table_info(messages)")
    columns = cursor.fetchall()
    print("Messages table columns:")
    for col in columns:
        print(col)

    # Check for constraints
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='messages'")
    create_sql = cursor.fetchone()
    print("\nMessages table CREATE statement:")
    print(create_sql[0])

    # Check current statuses
    cursor.execute("SELECT DISTINCT status FROM messages")
    statuses = cursor.fetchall()
    print("\nCurrent statuses in messages:")
    for status in statuses:
        print(status[0])

    conn.close()

if __name__ == '__main__':
    check_db()