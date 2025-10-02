import sqlite3

def init_db():
    """Инициализирует базу данных и создает таблицы, если они еще не существуют."""
    conn = sqlite3.connect('webui/dashboard.db')
    cursor = conn.cursor()

    # Таблица для узлов сети (Nodes)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id TEXT UNIQUE NOT NULL,
        name TEXT,
        last_seen TIMESTAMP,
        battery_level INTEGER,
        latitude REAL,
        longitude REAL,
        altitude INTEGER
    )
    ''')

    # Таблица для сообщений (Messages)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id TEXT UNIQUE,
        from_node_id TEXT,
        to_node_id TEXT,
        channel TEXT,
        text TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_dm BOOLEAN
    )
    ''')

    # Таблица для пользователей дашборда (Users)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'user'
    )
    ''')

    # Таблица для сообщений форума (Forum)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS forum_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL,
        author_id INTEGER,
        content TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        parent_post_id INTEGER,
        FOREIGN KEY (author_id) REFERENCES users (id),
        FOREIGN KEY (parent_post_id) REFERENCES forum_posts (id)
    )
    ''')

    # Таблица для гео-зон (Geofences)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS geofences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        shape_type TEXT, -- 'circle' или 'polygon'
        coordinates TEXT -- JSON-строка с координатами
    )
    ''')

    # Таблица для триггеров (Triggers)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS triggers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        geofence_id INTEGER,
        event_type TEXT, -- 'enter', 'exit'
        action_type TEXT, -- 'notify', 'run_script'
        action_payload TEXT,
        FOREIGN KEY (geofence_id) REFERENCES geofences (id)
    )
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    print("Инициализация базы данных...")
    init_db()
    print("База данных успешно инициализирована.")