# Deployment Guide

## Prerequisites

### Hardware Requirements
- **Raspberry Pi 4/5** (recommended) or any Linux server
- **Meshtastic-compatible radios** (1-9 devices)
- **USB ports** for radio connections
- **Internet connection** (optional, for external services)
- **8GB RAM minimum** (16GB recommended for AI features)

### Software Requirements
- **Ubuntu/Debian Linux** (or compatible distribution)
- **Python 3.8+**
- **Meshtastic firmware** on radios
- **Git** for repository cloning

### Network Requirements
- **Meshtastic radio network** properly configured
- **Static IP** recommended for server deployment
- **Firewall configuration** for web access
- **DNS resolution** for external API calls

## Installation Methods

### Method 1: Automated Installation (Recommended)

```bash
# Clone the repository
git clone https://github.com/spudgunman/meshing-around
cd meshing-around

# Run automated installation
./install.sh
```

The install script will:
- Create Python virtual environment
- Install all dependencies
- Set up basic configuration
- Initialize database

### Method 2: Manual Installation

```bash
# Install system dependencies
sudo apt update
sudo apt install python3 python3-pip python3-venv git

# Clone repository
git clone https://github.com/spudgunman/meshing-around
cd meshing-around

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### Method 3: Docker Deployment

```bash
# Build Docker image
docker build -t firefly-bbs .

# Run container
docker run -d \
  --name firefly-bbs \
  --device /dev/ttyUSB0:/dev/ttyUSB0 \
  -p 8000:8000 \
  -v $(pwd)/config.ini:/app/config.ini \
  -v $(pwd)/data:/app/data \
  firefly-bbs
```

## Configuration Setup

### Basic Configuration

1. **Copy configuration template**:
```bash
cp config.template config.ini
```

2. **Edit configuration file**:
```bash
nano config.ini
```

### Radio Interface Configuration

Configure your Meshtastic radio connections:

```ini
[interface]
type = serial
port = /dev/ttyUSB0

[interface2]
enabled = False
type = tcp
hostname = 192.168.1.100
```

**Interface Types**:
- `serial`: Direct USB connection
- `tcp`: Network-connected radio
- `ble`: Bluetooth connection (limited to 1)

### Network Settings

```ini
[general]
respond_by_dm_only = True
defaultChannel = 0
ignoreDefaultChannel = False
```

### Location Configuration

Set your bot's location for weather and alert services:

```ini
[location]
enabled = True
lat = 45.100001
lon = 38.100001
UseMeteoWxAPI = True
```

## Feature-Specific Setup

### Web Dashboard Setup

1. **Initialize database**:
```bash
python3 webui/database.py
```

2. **Create admin user**:
```bash
python3 -c "
from webui.database import init_db
from webui.db_handler import register_user
init_db()
register_user('admin', 'admin123', role='admin')
"
```

3. **Start web server**:
```bash
python3 webui/main.py
```

Access dashboard at `http://localhost:8000`

### Telegram Integration Setup

1. **Create Telegram bot**:
   - Message @BotFather on Telegram
   - Use `/newbot` command
   - Get your bot token

2. **Configure Telegram settings**:
```ini
[telegram]
telegram_bot_token = YOUR_BOT_TOKEN
telegram_chat_id = YOUR_CHAT_ID
telegram_authorized_users = 123456789,987654321
```

### AI/LLM Setup

1. **Install Ollama**:
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

2. **Start Ollama service**:
```bash
sudo systemctl start ollama
```

3. **Pull AI model**:
```bash
ollama pull gemma3:270m
```

4. **Configure AI settings**:
```ini
[general]
ollama = True
ollamaModel = gemma3:270m
ollamaHostName = http://localhost:11434
```

### Email Integration Setup

```ini
[smtp]
enableSMTP = True
SMTP_SERVER = smtp.gmail.com
SMTP_PORT = 587
SMTP_AUTH = True
FROM_EMAIL = your-email@gmail.com
SMTP_USERNAME = your-email@gmail.com
SMTP_PASSWORD = your-app-password
```

## Service Deployment

### Systemd Service Setup

1. **Create service file**:
```bash
sudo nano /etc/systemd/system/firefly-bbs.service
```

2. **Service configuration**:
```ini
[Unit]
Description=Firefly BBS Meshtastic Bot
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/meshing-around
ExecStart=/home/pi/meshing-around/venv/bin/python3 mesh_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. **Enable and start service**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable firefly-bbs
sudo systemctl start firefly-bbs
```

### Web Dashboard Service

```bash
sudo nano /etc/systemd/system/firefly-web.service
```

```ini
[Unit]
Description=Firefly BBS Web Dashboard
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/meshing-around
ExecStart=/home/pi/meshing-around/venv/bin/python3 webui/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### Nginx Reverse Proxy (Optional)

1. **Install Nginx**:
```bash
sudo apt install nginx
```

2. **Create site configuration**:
```bash
sudo nano /etc/nginx/sites-available/firefly-bbs
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

3. **Enable site**:
```bash
sudo ln -s /etc/nginx/sites-available/firefly-bbs /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

## Security Configuration

### Firewall Setup

```bash
# Allow SSH
sudo ufw allow ssh

# Allow web access
sudo ufw allow 8000

# Enable firewall
sudo ufw enable
```

### SSL/TLS Setup (Recommended)

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com
```

### User Access Control

1. **Create limited user**:
```bash
sudo useradd -m -s /bin/bash meshbot
sudo usermod -aG dialout meshbot  # For serial access
```

2. **Configure sudo access** (if needed):
```bash
sudo visudo
# Add: meshbot ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart firefly-bbs
```

## Monitoring and Maintenance

### Log Management

```bash
# View logs
sudo journalctl -u firefly-bbs -f

# Web dashboard logs
tail -f webui.log
```

### Database Maintenance

```bash
# Backup database
cp dashboard.db dashboard.db.backup_$(date +%Y%m%d_%H%M%S)

# Update database schema
python3 update.sh
```

### Performance Monitoring

```bash
# Check system resources
htop

# Monitor radio connections
python3 check_db.py

# Test message routing
python3 test_message_routing.py
```

## Troubleshooting

### Common Issues

1. **Radio Connection Failed**:
   - Check USB device permissions: `ls -la /dev/ttyUSB*`
   - Add user to dialout group: `sudo usermod -aG dialout $USER`

2. **Web Interface Not Accessible**:
   - Check if service is running: `sudo systemctl status firefly-web`
   - Verify port availability: `netstat -tlnp | grep 8000`

3. **Database Errors**:
   - Check file permissions: `ls -la dashboard.db`
   - Run integrity check: `sqlite3 dashboard.db "PRAGMA integrity_check;"`

4. **AI Features Not Working**:
   - Verify Ollama is running: `sudo systemctl status ollama`
   - Check model availability: `ollama list`

### Recovery Procedures

1. **Service Restart**:
```bash
sudo systemctl restart firefly-bbs
sudo systemctl restart firefly-web
```

2. **Configuration Reset**:
```bash
cp config.template config.ini
# Edit configuration as needed
```

3. **Database Recovery**:
```bash
# Restore from backup
cp dashboard.db.backup_YYYYMMDD_HHMMSS dashboard.db
python3 webui/database.py  # Reinitialize schema
```

## Scaling and High Availability

### Multi-Radio Setup

```ini
[interface]
type = serial
port = /dev/ttyUSB0

[interface2]
enabled = True
type = serial
port = /dev/ttyUSB1

[interface3]
enabled = True
type = tcp
hostname = 192.168.1.101
```

### Load Balancing (Advanced)

For high-traffic deployments, consider:
- Nginx load balancer for web interface
- Database replication for read-heavy workloads
- Redis for session storage and caching

## Backup Strategy

### Automated Backups

```bash
# Create backup script
cat > backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/pi/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
cp dashboard.db $BACKUP_DIR/dashboard_$DATE.db

# Backup configuration
cp config.ini $BACKUP_DIR/config_$DATE.ini

# Backup logs (last 7 days)
find . -name "*.log" -mtime -7 -exec cp {} $BACKUP_DIR/ \;

# Compress backup
tar -czf $BACKUP_DIR/backup_$DATE.tar.gz -C $BACKUP_DIR .

# Clean old backups (keep last 30)
find $BACKUP_DIR -name "backup_*.tar.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_DIR/backup_$DATE.tar.gz"
EOF

chmod +x backup.sh
```

### Scheduled Backups

```bash
# Add to crontab for daily backups at 2 AM
crontab -e
# Add: 0 2 * * * /home/pi/meshing-around/backup.sh
```

This deployment guide provides a comprehensive setup for production deployment of the Firefly BBS system with proper security, monitoring, and maintenance procedures.