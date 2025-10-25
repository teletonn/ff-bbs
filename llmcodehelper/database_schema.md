# Database Schema Documentation

## Overview

The Firefly BBS system uses SQLite as its primary database with WAL (Write-Ahead Logging) mode enabled for concurrent read/write operations. The database schema is defined in `webui/database.py` and supports all core system functionality.

## Core Tables

### nodes - Network Node Information

**Purpose**: Stores information about all Meshtastic nodes in the network.

```sql
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
    precision_bits INTEGER
)
```

**Key Fields**:
- `node_id`: Unique Meshtastic node identifier
- `last_seen`: Timestamp of last packet reception
- `latitude/longitude`: GPS coordinates
- `is_online`: Online status (updated every 10 minutes)
- `battery_level`: Device battery percentage
- `snr/rssi`: Signal quality metrics

**Indexes**:
- `idx_nodes_last_seen` on `last_seen`

### messages - Message Storage and Routing

**Purpose**: Stores all messages with delivery tracking and queuing.

```sql
CREATE TABLE messages (
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
```

**Key Fields**:
- `message_id`: Unique message identifier (UUID)
- `status`: Delivery status with CHECK constraint
- `attempt_count`: Number of delivery attempts
- `defer_count`: Number of times message was deferred
- `is_dm`: Direct message flag

**Indexes**:
- `idx_messages_timestamp` on `timestamp`
- `idx_messages_from_node_id` on `from_node_id`
- `idx_messages_to_node_id` on `to_node_id`

## User Management Tables

### users - Web Dashboard Users

**Purpose**: Manages web interface users and their permissions.

```sql
CREATE TABLE users (
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
```

**Key Fields**:
- `username/password`: Authentication credentials
- `role`: User role (admin/user)
- `telegram_*`: Telegram integration fields
- `mesh_node_id`: Associated Meshtastic node
- `is_active`: Account status

**Indexes**:
- `idx_users_username` on `username`
- `idx_users_telegram_id` on `telegram_id`
- `idx_users_mesh_node_id` on `mesh_node_id`

### user_groups - User Group Management

**Purpose**: Supports role-based access control through groups.

```sql
CREATE TABLE user_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### user_group_assignments - User-Group Relationships

**Purpose**: Many-to-many relationship between users and groups.

```sql
CREATE TABLE user_group_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES user_groups (id) ON DELETE CASCADE,
    UNIQUE(user_id, group_id)
)
```

**Indexes**:
- `idx_user_group_assignments_user_id` on `user_id`
- `idx_user_group_assignments_group_id` on `group_id`

## Geospatial Features

### geofences - Geographic Zones

**Purpose**: Defines geographic areas for location-based triggers.

```sql
CREATE TABLE geofences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    radius REAL NOT NULL DEFAULT 100,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### zones - Enhanced Geographic Zones

**Purpose**: Extended zone system with descriptions and activation control.

```sql
CREATE TABLE zones (
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
```

**Indexes**:
- `idx_zones_active` on `active`

### triggers - Zone-Based Triggers

**Purpose**: Defines automated actions based on zone entry/exit events.

```sql
CREATE TABLE triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    description TEXT,
    zone_id INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('enter', 'exit')),
    action_type TEXT NOT NULL,
    action_payload TEXT DEFAULT '{}',
    FOREIGN KEY (zone_id) REFERENCES zones (id) ON DELETE CASCADE
)
```

**Indexes**:
- `idx_triggers_zone_id` on `zone_id`

## Alert and Monitoring System

### alerts - System Alerts

**Purpose**: Stores system-wide alerts and notifications.

```sql
CREATE TABLE alerts (
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
```

**Indexes**:
- `idx_alerts_node_id` on `node_id`
- `idx_alerts_user_id` on `user_id`
- `idx_alerts_timestamp` on `timestamp`

### alert_configs - Alert Configuration

**Purpose**: Defines alert generation rules and conditions.

```sql
CREATE TABLE alert_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL,
    type TEXT,
    condition TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    user_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
)
```

**Indexes**:
- `idx_alert_configs_user_id` on `user_id`

## Automation and Scheduling

### processes - Automated Processes

**Purpose**: Defines scheduled or triggered automated processes.

```sql
CREATE TABLE processes (
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
```

**Indexes**:
- `idx_processes_user_id` on `user_id`

### commands_queue - Command Execution Queue

**Purpose**: Queues commands for execution by the bot system.

```sql
CREATE TABLE commands_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_type TEXT NOT NULL,
    parameters TEXT NOT NULL,
    sender_user_id INTEGER NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'executed', 'failed')),
    result TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP,
    FOREIGN KEY (sender_user_id) REFERENCES users (id)
)
```

**Indexes**:
- `idx_commands_queue_sender_user_id` on `sender_user_id`

## Content Management

### forum_posts - Community Forum

**Purpose**: Stores forum posts and discussions.

```sql
CREATE TABLE forum_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    author_id INTEGER,
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    parent_post_id INTEGER,
    FOREIGN KEY (author_id) REFERENCES users (id),
    FOREIGN KEY (parent_post_id) REFERENCES forum_posts (id)
)
```

**Indexes**:
- `idx_forum_posts_author_id` on `author_id`

## Telemetry and Analytics

### telemetry - Historical Position Data

**Purpose**: Stores historical GPS and telemetry data for route tracking.

```sql
CREATE TABLE telemetry (
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
```

**Indexes**:
- `idx_telemetry_node_id` on `node_id`
- `idx_telemetry_timestamp` on `timestamp`

### route_traces - Network Route Analysis

**Purpose**: Stores traceroute results for network analysis.

```sql
CREATE TABLE route_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id TEXT NOT NULL,
    dest_node_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    hops TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
    response_time REAL,
    error_message TEXT,
    FOREIGN KEY (source_node_id) REFERENCES nodes (node_id),
    FOREIGN KEY (dest_node_id) REFERENCES nodes (node_id)
)
```

**Indexes**:
- `idx_route_traces_source_node_id` on `source_node_id`
- `idx_route_traces_dest_node_id` on `dest_node_id`
- `idx_route_traces_timestamp` on `timestamp`
- `idx_route_traces_status` on `status`

## Configuration Management

### settings - Dynamic Configuration

**Purpose**: Stores runtime configuration settings.

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## Database Maintenance and Features

### WAL Mode
The database uses Write-Ahead Logging for improved concurrent access:
```sql
PRAGMA journal_mode=WAL;
```

### Foreign Key Enforcement
Foreign key constraints are enabled for data integrity:
```sql
PRAGMA foreign_keys=ON;
```

### Automatic Initialization
The `init_db()` function in `webui/database.py` creates all tables and indexes on first run.

### Schema Evolution
The database includes migration logic to add new columns and tables without data loss. Key migration functions:
- `ensure_users_table_columns()`: Adds missing user table columns
- `ensure_nodes_table_columns()`: Adds telemetry columns to nodes
- `ensure_messages_table_columns()`: Adds delivery tracking columns

### Backup Strategy
The system creates timestamped backups during updates:
- Format: `dashboard.db.backup_YYYYMMDD_HHMMSS`
- Automatic cleanup of old backups (32 days retention)

## Performance Optimizations

### Indexing Strategy
- Primary keys on all tables
- Foreign key indexes for JOIN performance
- Timestamp indexes for time-based queries
- Composite indexes for complex queries

### Query Patterns
- Paginated queries for large result sets
- Efficient filtering by status and timestamps
- Optimized geospatial queries for zone operations

### Connection Management
- Connection pooling through sqlite3
- Automatic reconnection handling
- Transaction management for data consistency

This schema provides a comprehensive foundation for all Firefly BBS functionality while maintaining performance and data integrity.