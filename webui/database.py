import sqlite3

def init_db():
    """Инициализирует базу данных и создает таблицы, если они еще не существуют."""
    conn = sqlite3.connect('dashboard.db')
    init_db_on_connection(conn)
    conn.close()

def check_and_update_schema():
    """Checks the database schema and applies missing tables or columns."""
    # This is a simplified migration helper. For complex migrations, a full tool like Alembic would be better.

    # Get the full schema from init_db by creating a temporary in-memory DB
    mem_conn = sqlite3.connect(':memory:')
    init_db_on_connection(mem_conn)

    # Get the list of tables and their columns from the ideal schema
    mem_cursor = mem_conn.cursor()
    mem_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    ideal_tables = {row[0] for row in mem_cursor.fetchall()}

    ideal_schema = {}
    for table in ideal_tables:
        mem_cursor.execute(f"PRAGMA table_info({table})")
        ideal_schema[table] = {row[1]: row[2] for row in mem_cursor.fetchall()} # name: type
    mem_conn.close()

    # Now connect to the real database and check against the ideal schema
    conn = sqlite3.connect('dashboard.db')
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    current_tables = {row[0] for row in cursor.fetchall()}

    # Create missing tables
    missing_tables = ideal_tables - current_tables
    if missing_tables:
        # Re-run init_db to create missing tables (it uses CREATE IF NOT EXISTS)
        init_db_on_connection(conn)
        print(f"Created missing tables: {', '.join(missing_tables)}")

    # Check for and add missing columns
    for table in ideal_tables:
        if table in current_tables:
            cursor.execute(f"PRAGMA table_info({table})")
            current_columns = {row[1] for row in cursor.fetchall()}
            ideal_columns = ideal_schema[table]

            missing_columns = set(ideal_columns.keys()) - current_columns
            for col in missing_columns:
                col_type = ideal_columns[col]
                # Simplified ALTER TABLE, no constraints or defaults for now
                try:
                    cursor.execute(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}')
                    print(f"Added column '{col}' to table '{table}'")
                except sqlite3.OperationalError as e:
                    print(f"Could not add column '{col}' to '{table}': {e}")

    conn.commit()
    conn.close()

def init_db_on_connection(conn):
    """Initializes the database schema on a given connection."""
    cursor = conn.cursor()
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
        is_dm BOOLEAN,
        status TEXT DEFAULT 'sent' CHECK (status IN ('sent', 'queued', 'delivered', 'undelivered', 'failed')),
        attempt_count INTEGER DEFAULT 0,
        last_attempt_time TIMESTAMP,
        next_retry_time TIMESTAMP,
        error_message TEXT,
        defer_count INTEGER DEFAULT 0,
        delivered BOOLEAN DEFAULT 0,
        retry_count INTEGER DEFAULT 0,
        delivery_attempts INTEGER DEFAULT 0
    )
    ''')

    # Таблица для пользователей дашборда (Users)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        nickname TEXT,
        node_id TEXT UNIQUE,
        email TEXT,
        role TEXT DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        group_id INTEGER REFERENCES user_groups(id),
        telegram_id INTEGER UNIQUE,
        telegram_first_name TEXT,
        telegram_last_name TEXT,
        telegram_username TEXT,
        mesh_node_id TEXT UNIQUE,
        is_active BOOLEAN DEFAULT 1
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
        name TEXT,
        description TEXT,
        zone_id INTEGER NOT NULL,
        event_type TEXT NOT NULL CHECK (event_type IN ('enter', 'exit')),
        action_type TEXT NOT NULL,
        action_payload TEXT DEFAULT '{}',
        active BOOLEAN DEFAULT 1,
        FOREIGN KEY (zone_id) REFERENCES zones (id) ON DELETE CASCADE
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

    # Таблица для трассировки маршрутов (Route Traces)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS route_traces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_node_id TEXT NOT NULL,
        dest_node_id TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        hops TEXT,  -- JSON array of hop data with node_id and snr
        status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
        response_time REAL,
        error_message TEXT,
        FOREIGN KEY (source_node_id) REFERENCES nodes (node_id),
        FOREIGN KEY (dest_node_id) REFERENCES nodes (node_id)
    )
    ''')

    # Таблица для отслеживания узлов в зонах (Node Zones)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS node_zones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id TEXT NOT NULL,
        zone_id INTEGER NOT NULL,
        entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_currently_in BOOLEAN DEFAULT 1,
        FOREIGN KEY (node_id) REFERENCES nodes (node_id) ON DELETE CASCADE,
        FOREIGN KEY (zone_id) REFERENCES zones (id) ON DELETE CASCADE,
        UNIQUE(node_id, zone_id)
    )
    ''')

    # Таблица для логов триггеров (Trigger Logs)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trigger_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trigger_id INTEGER NOT NULL,
        node_id TEXT NOT NULL,
        event_type TEXT NOT NULL CHECK (event_type IN ('enter', 'exit')),
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        zone_name TEXT,
        node_name TEXT,
        action_taken TEXT,
        action_result TEXT,
        FOREIGN KEY (trigger_id) REFERENCES triggers (id) ON DELETE CASCADE,
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
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_triggers_zone_id ON triggers(zone_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_commands_queue_sender_user_id ON commands_queue(sender_user_id)')

    # Индексы для route_traces
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_route_traces_source_node_id ON route_traces(source_node_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_route_traces_dest_node_id ON route_traces(dest_node_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_route_traces_timestamp ON route_traces(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_route_traces_status ON route_traces(status)')

    # Индексы для node_zones
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_node_zones_node_id ON node_zones(node_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_node_zones_zone_id ON node_zones(zone_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_node_zones_is_currently_in ON node_zones(is_currently_in)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_node_zones_last_seen ON node_zones(last_seen)')

    # Таблица для FiMesh transfers
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS fimesh_transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT UNIQUE NOT NULL,
        file_name TEXT NOT NULL,
        file_size INTEGER,
        total_chunks INTEGER,
        direction TEXT NOT NULL CHECK (direction IN ('upload', 'download')),
        from_node_id TEXT NOT NULL,
        to_node_id TEXT NOT NULL,
        status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'manifest', 'transferring', 'completed', 'failed', 'cancelled')),
        progress INTEGER DEFAULT 0,
        window_size INTEGER DEFAULT 2,
        start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        end_time TIMESTAMP
    )
    ''')

    # Индексы для trigger_logs
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trigger_logs_trigger_id ON trigger_logs(trigger_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trigger_logs_node_id ON trigger_logs(node_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trigger_logs_timestamp ON trigger_logs(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trigger_logs_event_type ON trigger_logs(event_type)')

    # Индексы для fimesh_transfers
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fimesh_transfers_status ON fimesh_transfers(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fimesh_transfers_start_time ON fimesh_transfers(start_time)')

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

    if 'telegram_id' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN telegram_id INTEGER")
        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)")
        except sqlite3.OperationalError:
            pass

    if 'telegram_first_name' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN telegram_first_name TEXT")

    if 'telegram_last_name' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN telegram_last_name TEXT")

    if 'telegram_username' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN telegram_username TEXT")

    if 'mesh_node_id' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN mesh_node_id TEXT")
        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_mesh_node_id ON users(mesh_node_id)")
        except sqlite3.OperationalError:
            pass

    if 'is_active' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")


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
        'status': "TEXT DEFAULT 'sent' CHECK (status IN ('sent', 'queued', 'delivered', 'undelivered'))",
        'attempt_count': 'INTEGER DEFAULT 0',
        'last_attempt_time': 'TIMESTAMP',
        'next_retry_time': 'TIMESTAMP',
        'error_message': 'TEXT',
        'defer_count': 'INTEGER DEFAULT 0'
    }

    for col_name, col_type in delivery_columns.items():
        if col_name not in message_columns:
            cursor.execute(f"ALTER TABLE messages ADD COLUMN {col_name} {col_type}")

    # Ensure triggers table has active column
    cursor.execute("PRAGMA table_info(triggers)")
    trigger_columns = [col[1] for col in cursor.fetchall()]
    if 'active' not in trigger_columns:
        cursor.execute("ALTER TABLE triggers ADD COLUMN active BOOLEAN DEFAULT 1")

    # Ensure default settings for messaging
    cursor.execute("SELECT key FROM settings WHERE key = 'messaging.undelivered_timeout_minutes'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO settings (key, value, description) VALUES (?, ?, ?)",
                      ('messaging.undelivered_timeout_minutes', '10', 'Timeout in minutes after which sent messages are marked as undelivered'))

    conn.commit()


if __name__ == '__main__':
    print("Checking and updating database schema...")
    check_and_update_schema()
    print("Database is up to date.")
