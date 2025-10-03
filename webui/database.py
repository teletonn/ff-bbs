import sqlite3

def init_db():
    """Инициализирует базу данных и создает таблицы, если они еще не существуют."""
    conn = sqlite3.connect('dashboard.db')
    cursor = conn.cursor()

    # Enable WAL mode for concurrent readers and writers
    cursor.execute('PRAGMA journal_mode=WAL;')

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
        precision_bits INTEGER
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
        password TEXT NOT NULL,
        nickname TEXT,
        node_id TEXT UNIQUE,
        email TEXT,
        role TEXT DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        name TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        radius REAL NOT NULL DEFAULT 100,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Таблица для триггеров (Triggers)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS triggers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        geofence_id INTEGER NOT NULL,
        condition TEXT NOT NULL CHECK (condition IN ('enter', 'exit')),
        action TEXT NOT NULL,
        parameters TEXT DEFAULT '{}',
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (geofence_id) REFERENCES geofences (id) ON DELETE CASCADE
    )
    ''')

    # Таблица для очереди команд (Commands Queue)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command_type TEXT NOT NULL,
            parameters TEXT NOT NULL,  -- JSON
            sender_user_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'executed', 'failed')),
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            executed_at TIMESTAMP,
            FOREIGN KEY (sender_user_id) REFERENCES users (id)
        )
    ''')

    # Таблица для настроек (Settings)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица для групп пользователей (User Groups)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Таблица для связи пользователей и групп (User-Group Assignments)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_group_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (group_id) REFERENCES user_groups (id) ON DELETE CASCADE,
        UNIQUE(user_id, group_id)
    )
    ''')

    # Таблица для системных алертов (Alerts)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        message TEXT NOT NULL,
        severity TEXT DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'error')),
        node_id TEXT,
        user_id INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active' CHECK (status IN ('active', 'acknowledged', 'resolved')),
        FOREIGN KEY (node_id) REFERENCES nodes (node_id),
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # Таблица для конфигурации алертов (Alert Configs)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS alert_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_type TEXT NOT NULL,
        type TEXT,
        condition TEXT NOT NULL,
        enabled BOOLEAN DEFAULT 1,
        user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # Таблица для автоматизированных процессов (Processes)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS processes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        command TEXT NOT NULL,
        schedule TEXT,
        enabled BOOLEAN DEFAULT 1,
        last_run TIMESTAMP,
        next_run TIMESTAMP,
        user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # Таблица для гео-зон (Zones)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS zones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        radius REAL NOT NULL DEFAULT 100,
        active BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Таблица для телеметрии (Telemetry) - для хранения исторических данных о местоположении
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        latitude REAL,
        longitude REAL,
        altitude INTEGER,
        battery_level INTEGER,
        snr REAL,
        rssi INTEGER,
        hop_count INTEGER,
        ground_speed REAL,
        FOREIGN KEY (node_id) REFERENCES nodes (node_id) ON DELETE CASCADE
    )
    ''')

    # Индексы для новых таблиц
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_node_id ON alerts(node_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alert_configs_user_id ON alert_configs(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_processes_user_id ON processes(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_zones_active ON zones(active)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_groups_name ON user_groups(name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_group_assignments_user_id ON user_group_assignments(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_group_assignments_group_id ON user_group_assignments(group_id)')

    # Индексы для телеметрии
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_telemetry_node_id ON telemetry(node_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry(timestamp)')

    # Индексы для существующих таблиц
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_from_node_id ON messages(from_node_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_to_node_id ON messages(to_node_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_last_seen ON nodes(last_seen)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_forum_posts_author_id ON forum_posts(author_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_triggers_geofence_id ON triggers(geofence_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_commands_queue_sender_user_id ON commands_queue(sender_user_id)')

    # Ensure users table has all columns
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'password' not in columns:
        # If password_hash exists, rename it to password
        if 'password_hash' in columns:
            cursor.execute("ALTER TABLE users RENAME COLUMN password_hash TO password")
        else:
            # If neither, add password column (though CREATE should have it)
            cursor.execute("ALTER TABLE users ADD COLUMN password TEXT NOT NULL DEFAULT ''")
    
    if 'nickname' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN nickname TEXT")
    
    if 'node_id' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN node_id TEXT")
        # Add unique constraint separately if needed, but ALTER ADD UNIQUE not direct; assume empty or handle later
        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_node_id ON users(node_id)")
        except sqlite3.OperationalError:
            pass  # If conflict, ignore for now
    
    if 'email' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
    
    if 'created_at' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    if 'group_id' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN group_id INTEGER REFERENCES user_groups(id)")

    # Ensure nodes table has all telemetry columns
    cursor.execute("PRAGMA table_info(nodes)")
    node_columns = [col[1] for col in cursor.fetchall()]

    telemetry_columns = {
        'snr': 'REAL',
        'rssi': 'INTEGER',
        'hop_count': 'INTEGER',
        'pki_status': 'TEXT',
        'hardware_model': 'TEXT',
        'firmware_version': 'TEXT',
        'role': "TEXT DEFAULT 'client'",
        'is_online': 'BOOLEAN DEFAULT 0',
        'last_telemetry': 'TIMESTAMP',
        'ground_speed': 'REAL',
        'precision_bits': 'INTEGER'
    }

    for col_name, col_type in telemetry_columns.items():
        if col_name not in node_columns:
            cursor.execute(f"ALTER TABLE nodes ADD COLUMN {col_name} {col_type}")

    # Ensure messages table has delivery tracking columns
    cursor.execute("PRAGMA table_info(messages)")
    message_columns = [col[1] for col in cursor.fetchall()]

    delivery_columns = {
        'delivered': 'BOOLEAN DEFAULT 0',
        'retry_count': 'INTEGER DEFAULT 0',
        'delivery_attempts': 'INTEGER DEFAULT 0'
    }

    for col_name, col_type in delivery_columns.items():
        if col_name not in message_columns:
            cursor.execute(f"ALTER TABLE messages ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()

    # Ensure WAL mode on all databases
    # from .db_handler import ensure_wal_mode_on_all_dbs
    # ensure_wal_mode_on_all_dbs()

if __name__ == '__main__':
    print("Инициализация базы данных...")
    init_db()
    print("База данных успешно инициализирована.")