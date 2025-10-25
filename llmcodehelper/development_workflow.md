# Development Workflow Guide

This document outlines the development workflows for common tasks in the Firefly BBS system, optimized for efficient development and maintenance.

## Database Variable Management

### Adding New Database Variables

**Workflow for Schema Changes**:

1. **Plan the Change**:
   - Identify the table and column requirements
   - Consider relationships and constraints
   - Plan migration strategy for existing data

2. **Update Schema Definition**:
   ```python
   # In webui/database.py, add to init_db() function
   cursor.execute('''
   ALTER TABLE nodes ADD COLUMN new_field TEXT DEFAULT 'default_value'
   ''')
   ```

3. **Update Database Handler**:
   ```python
   # In webui/db_handler.py, add CRUD functions
   def get_new_field(node_id):
       conn = get_db_connection()
       cursor = conn.cursor()
       cursor.execute("SELECT new_field FROM nodes WHERE node_id = ?", (node_id,))
       result = cursor.fetchone()
       conn.close()
       return result[0] if result else None
   ```

4. **Update Migration Logic**:
   ```python
   # Add to ensure_nodes_table_columns() function
   if 'new_field' not in node_columns:
       cursor.execute("ALTER TABLE nodes ADD COLUMN new_field TEXT DEFAULT 'default_value'")
   ```

5. **Test the Changes**:
   ```bash
   # Run database update script
   ./update.sh

   # Verify schema
   python3 inspect_schema.py

   # Test functionality
   python3 check_db.py
   ```

### Code Updates for Database Changes

1. **Update Data Models**:
   - Modify any data classes or models
   - Update type hints and validation

2. **Update API Endpoints**:
   ```python
   # In webui/main.py, add new API endpoint
   @app.get("/api/v1/nodes/{node_id}/new_field")
   async def api_get_new_field(node_id: str):
       return get_new_field(node_id)
   ```

3. **Update Web Interface**:
   - Modify templates to display new fields
   - Update JavaScript for dynamic updates

## Feature Development Workflows

### Adding New Bot Commands

1. **Define Command Handler**:
   ```python
   # In mesh_bot.py or new module
   def handle_new_command(message, message_from_id, deviceID):
       """Handle the new command logic."""
       # Command processing logic
       response = "Command executed successfully"
       return response
   ```

2. **Register Command**:
   ```python
   # Add to auto_response function
   "newcommand": lambda: handle_new_command(message, message_from_id, deviceID),
   ```

3. **Update Help System**:
   ```python
   # In modules/system.py, update trap_list and help_message
   trap_list_newcommand = ("newcommand",)
   trap_list = trap_list + trap_list_newcommand
   help_message = help_message + ", newcommand"
   ```

4. **Add Configuration** (if needed):
   ```ini
   # In config.template
   [new_feature]
   enabled = True
   parameter = default_value
   ```

### Deploying Project Updates

#### Full Deployment Process

1. **Pre-Deployment Checks**:
   ```bash
   # Test all functionality
   python3 -m pytest tests/ -v

   # Check database integrity
   python3 check_db.py

   # Backup current state
   cp dashboard.db dashboard.db.backup_$(date +%Y%m%d_%H%M%S)
   cp config.ini config.ini.backup
   ```

2. **Update Code**:
   ```bash
   # Pull latest changes
   git pull origin main

   # Update dependencies if requirements.txt changed
   pip install -r requirements.txt --upgrade
   ```

3. **Database Migration**:
   ```bash
   # Run database update script
   ./update.sh

   # Verify migration success
   python3 inspect_schema.py
   ```

4. **Configuration Update**:
   ```bash
   # Merge configuration changes
   # Edit config.ini as needed for new features
   nano config.ini
   ```

5. **Service Restart**:
   ```bash
   # Restart services
   sudo systemctl restart firefly-bbs
   sudo systemctl restart firefly-web

   # Check service status
   sudo systemctl status firefly-bbs
   sudo systemctl status firefly-web
   ```

6. **Post-Deployment Verification**:
   ```bash
   # Check logs for errors
   sudo journalctl -u firefly-bbs -n 50

   # Test basic functionality
   python3 test_message_sending.py
   python3 test_config_integration.py
   ```

#### Update Rollback Process

1. **Stop Services**:
   ```bash
   sudo systemctl stop firefly-bbs
   sudo systemctl stop firefly-web
   ```

2. **Restore Backups**:
   ```bash
   # Restore database
   cp dashboard.db.backup_TIMESTAMP dashboard.db

   # Restore configuration
   cp config.ini.backup config.ini
   ```

3. **Restart Services**:
   ```bash
   sudo systemctl start firefly-bbs
   sudo systemctl start firefly-web
   ```

### Adding New Features

#### Feature Development Process

1. **Feature Planning**:
   - Define requirements and scope
   - Identify affected modules
   - Plan database changes if needed
   - Consider backward compatibility

2. **Implementation**:
   ```python
   # Create new module or extend existing one
   # Follow established patterns and conventions
   # Add proper error handling and logging
   ```

3. **Configuration Integration**:
   ```ini
   # Add to config.template
   [new_feature]
   enabled = False  # Default to disabled for safety
   parameter1 = default_value
   parameter2 = another_default
   ```

4. **Testing**:
   ```bash
   # Unit tests for new functionality
   python3 -m pytest tests/test_new_feature.py

   # Integration testing
   python3 test_config_integration.py
   ```

5. **Documentation Update**:
   - Update README.md with new features
   - Update this development guide
   - Add code comments and docstrings

#### Code Changes Workflow

1. **Branch Creation**:
   ```bash
   git checkout -b feature/new-feature-name
   ```

2. **Development**:
   - Implement feature following project conventions
   - Add tests for new functionality
   - Update documentation

3. **Code Review**:
   ```bash
   # Run linting and formatting
   python3 -m flake8 modules/ webui/
   python3 -m black modules/ webui/

   # Run tests
   python3 -m pytest tests/
   ```

4. **Merge Process**:
   ```bash
   git checkout main
   git pull origin main
   git merge feature/new-feature-name
   git push origin main
   ```

## Routine Development Operations

### Database Maintenance

#### Regular Cleanup Tasks

```bash
# Clean old command queue entries (older than 7 days)
python3 -c "
from webui.db_handler import cleanup_old_commands
deleted = cleanup_old_commands(7)
print(f'Cleaned up {deleted} old commands')
"

# Optimize database
python3 -c "
import sqlite3
conn = sqlite3.connect('dashboard.db')
conn.execute('VACUUM')
conn.close()
print('Database optimized')
"
```

#### Performance Monitoring

```bash
# Check database performance
python3 -c "
import sqlite3
conn = sqlite3.connect('dashboard.db')
cursor = conn.cursor()

# Check table sizes
cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
tables = cursor.fetchall()

for table in tables:
    cursor.execute(f'SELECT COUNT(*) FROM {table[0]}')
    count = cursor.fetchone()[0]
    print(f'{table[0]}: {count} records')

conn.close()
"

# Monitor message queue
python3 -c "
from webui.db_handler import get_queued_messages, get_undelivered_messages
queued = get_queued_messages()
undelivered = get_undelivered_messages()
print(f'Queued messages: {len(queued)}')
print(f'Undelivered messages: {len(undelivered)}')
"
```

### Configuration Management

#### Dynamic Configuration Updates

```python
# Update configuration via API
from webui.db_handler import set_setting

# Enable/disable features
set_setting('general.ollama', 'True')
set_setting('location.enabled', 'True')

# Update radio settings
set_setting('interface.type', 'tcp')
set_setting('interface.hostname', '192.168.1.100')
```

#### Configuration Validation

```python
# Validate configuration on changes
def validate_config():
    import configparser
    config = configparser.ConfigParser()
    config.read('config.ini')

    # Check required sections
    required_sections = ['interface', 'general', 'location']
    for section in required_sections:
        if not config.has_section(section):
            raise ValueError(f"Missing required section: {section}")

    # Validate radio interfaces
    interface_count = 0
    for i in range(1, 10):
        if config.has_section(f'interface{i}'):
            enabled = config.getboolean(f'interface{i}', 'enabled', fallback=False)
            if enabled:
                interface_count += 1
                # Validate interface has required fields
                interface_type = config.get(f'interface{i}', 'type', fallback='')
                if interface_type not in ['serial', 'tcp', 'ble']:
                    raise ValueError(f"Invalid interface type for interface{i}: {interface_type}")

    if interface_count == 0:
        raise ValueError("At least one interface must be enabled")

    print("Configuration validation passed")
```

### Log Management

#### Log Rotation and Analysis

```bash
# Rotate logs (example cron job)
#!/bin/bash
LOG_DIR="/home/pi/meshing-around"
DATE=$(date +%Y%m%d)

# Rotate main log
if [ -f "$LOG_DIR/mesh_bot.log" ]; then
    mv "$LOG_DIR/mesh_bot.log" "$LOG_DIR/mesh_bot.log.$DATE"
fi

# Compress old logs (older than 7 days)
find "$LOG_DIR" -name "*.log.*" -mtime +7 -exec gzip {} \;

# Clean very old logs (older than 30 days)
find "$LOG_DIR" -name "*.log.*.gz" -mtime +30 -delete

# Restart service to create new log file
sudo systemctl restart firefly-bbs
```

#### Log Analysis

```python
# Analyze logs for patterns
def analyze_logs(log_file='mesh_bot.log', hours=24):
    import datetime
    from collections import Counter

    cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=hours)

    error_count = 0
    warning_count = 0
    command_usage = Counter()

    with open(log_file, 'r') as f:
        for line in f:
            # Parse log line (assuming standard format)
            if 'ERROR' in line:
                error_count += 1
            elif 'WARNING' in line:
                warning_count += 1

            # Count command usage
            if 'Command executed:' in line:
                # Extract command name
                pass

    print(f"Log analysis for last {hours} hours:")
    print(f"Errors: {error_count}")
    print(f"Warnings: {warning_count}")
    print(f"Most used commands: {command_usage.most_common(5)}")
```

### Backup and Recovery

#### Automated Backup System

```bash
# Create comprehensive backup
#!/bin/bash
BACKUP_DIR="/home/pi/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="firefly_backup_$TIMESTAMP"

mkdir -p "$BACKUP_DIR"

# Stop services for consistent backup
sudo systemctl stop firefly-bbs
sudo systemctl stop firefly-web

# Backup database
cp dashboard.db "$BACKUP_DIR/dashboard_$TIMESTAMP.db"

# Backup configuration
cp config.ini "$BACKUP_DIR/config_$TIMESTAMP.ini"

# Backup data directory
tar -czf "$BACKUP_DIR/data_$TIMESTAMP.tar.gz" data/

# Backup source code (optional)
tar -czf "$BACKUP_DIR/code_$TIMESTAMP.tar.gz" --exclude='*.pyc' --exclude='__pycache__' .

# Create backup manifest
cat > "$BACKUP_DIR/manifest_$TIMESTAMP.txt" << EOF
Backup created: $TIMESTAMP
Database: dashboard_$TIMESTAMP.db
Config: config_$TIMESTAMP.ini
Data: data_$TIMESTAMP.tar.gz
Code: code_$TIMESTAMP.tar.gz
Version: $(git rev-parse HEAD 2>/dev/null || echo 'unknown')
EOF

# Compress everything into single archive
tar -czf "$BACKUP_DIR/$BACKUP_NAME.tar.gz" -C "$BACKUP_DIR" \
    "dashboard_$TIMESTAMP.db" \
    "config_$TIMESTAMP.ini" \
    "data_$TIMESTAMP.tar.gz" \
    "code_$TIMESTAMP.tar.gz" \
    "manifest_$TIMESTAMP.txt"

# Clean up individual files
rm "$BACKUP_DIR/dashboard_$TIMESTAMP.db"
rm "$BACKUP_DIR/config_$TIMESTAMP.ini"
rm "$BACKUP_DIR/data_$TIMESTAMP.tar.gz"
rm "$BACKUP_DIR/code_$TIMESTAMP.tar.gz"

# Restart services
sudo systemctl start firefly-bbs
sudo systemctl start firefly-web

# Clean old backups (keep last 10)
ls -t "$BACKUP_DIR"/*.tar.gz | tail -n +11 | xargs -r rm

echo "Backup completed: $BACKUP_DIR/$BACKUP_NAME.tar.gz"
```

#### Recovery Process

```bash
# Recovery script
#!/bin/bash
BACKUP_FILE="$1"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    exit 1
fi

# Stop services
sudo systemctl stop firefly-bbs
sudo systemctl stop firefly-web

# Extract backup
TEMP_DIR="/tmp/firefly_restore"
mkdir -p "$TEMP_DIR"
tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"

# Restore files
cp "$TEMP_DIR/dashboard_*.db" ./dashboard.db
cp "$TEMP_DIR/config_*.ini" ./config.ini
tar -xzf "$TEMP_DIR/data_*.tar.gz"

# Clean up
rm -rf "$TEMP_DIR"

# Restart services
sudo systemctl start firefly-bbs
sudo systemctl start firefly-web

echo "Recovery completed from $BACKUP_FILE"
```

This development workflow guide provides comprehensive procedures for maintaining and extending the Firefly BBS system while ensuring stability and reliability.