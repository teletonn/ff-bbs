# Modules Description

This document provides comprehensive descriptions of all modules in the Firefly BBS system, their functions, classes, key methods, and interdependencies.

## Core System Modules

### system.py - Core System Utilities

**Purpose**: Provides fundamental system-level functions, interface management, and core bot operations.

**Key Classes & Functions**:
- `decimal_to_hex(decimal_number)`: Converts decimal node IDs to hexadecimal format
- `get_name_from_number(number, type='long', nodeInt=1)`: Retrieves node names from IDs
- `send_message(message, ch, nodeid, nodeInt, ...)`: Core message sending with retry logic
- `messageChunker(message)`: Splits large messages into chunks for transmission
- `consumeMetadata(packet, rxNode)`: Processes telemetry and position packets

**Dependencies**: meshtastic, asyncio, logging, webui.db_handler

**Interactions**: Used by all other modules for basic radio communication and system utilities.

### mesh_bot.py - Main Bot Logic

**Purpose**: Central command processing engine and event loop coordinator.

**Key Components**:
- `auto_response(message, snr, rssi, hop, pkiStatus, message_from_id, channel_number, deviceID, isDM)`: Main command dispatcher
- `handle_ping()`, `handle_cmd()`, `handle_lheard()`: Core command handlers
- `main()`: Async main event loop
- Command handler mappings for all bot features

**Dependencies**: All feature modules, system.py, webui components

**Interactions**: Imports and coordinates all feature modules, manages command processing pipeline.

## Communication Modules

### bbstools.py - Bulletin Board System

**Purpose**: Implements BBS functionality for community messaging and announcements.

**Key Functions**:
- `handle_bbspost(message, message_from_id, deviceID)`: Posts messages to BBS
- `handle_bbsread(message)`: Reads BBS messages by ID
- `handle_bbsdelete(message, message_from_id)`: Deletes BBS messages
- `bbs_list_messages()`: Lists all BBS messages
- `save_bbsdb()`, `load_bbsdb()`: BBS data persistence

**Configuration**: `[bbs]` section in config.ini
- `enabled`: Enable/disable BBS functionality
- `bbs_admin_list`: List of admin node IDs
- `bbs_ban_list`: List of banned node IDs

**Dependencies**: system.py, database access

### meshgram_integration/ - Telegram Integration

**Purpose**: Bridges Meshtastic network with Telegram messaging.

**Key Files**:
- `telegram_interface.py`: Telegram bot interface and message handling
- `message_processor.py`: Processes messages between Telegram and Meshtastic
- `node_manager.py`: Manages user-node associations
- `meshgram.py`: Main integration coordinator

**Key Classes**:
- `TelegramInterface`: Handles Telegram API interactions
- `MessageProcessor`: Routes messages between platforms
- `NodeManager`: Manages user registrations

**Configuration**: `[telegram]` section
- `telegram_bot_token`: Bot API token
- `telegram_chat_id`: Target chat ID
- `telegram_authorized_users`: Pre-authorized users

**Dependencies**: python-telegram-bot, asyncio, system.py

## Data and Information Modules

### locationdata.py - Weather and Location Services

**Purpose**: Provides weather data, alerts, and location-based information.

**Key Functions**:
- `handle_wxc(message_from_id, deviceID, 'wx')`: Weather information
- `handle_wxalert(message_from_id, deviceID, message)`: Weather alerts
- `handleEarthquake(message, message_from_id, deviceID)`: Earthquake data
- `get_volcano_usgs()`: Volcano alerts from USGS
- `handle_tide(message_from_id, deviceID, channel_number)`: Tide information

**Configuration**: `[location]` section
- `UseMeteoWxAPI`: Use Open-Meteo instead of NOAA
- `coastalEnabled`: Enable coastal weather forecasts
- `riverList`: USGS river monitoring stations

**Dependencies**: requests, geopy, datetime

### wx_meteo.py - Alternative Weather API

**Purpose**: Provides weather data from Open-Meteo API as alternative to NOAA.

**Key Functions**:
- Weather data fetching and formatting functions
- Integration with locationdata.py for fallback weather service

**Dependencies**: requests, locationdata.py

### globalalert.py - International Emergency Alerts

**Purpose**: Fetches emergency alerts from international sources.

**Key Functions**:
- `get_nina_alerts()`: German NINA emergency alerts
- `get_govUK_alerts()`: UK government alerts
- Emergency alert processing and formatting

**Configuration**: Various alert service configurations

**Dependencies**: requests, locationdata.py

### space.py - Solar and Space Weather

**Purpose**: Provides solar activity and space weather information.

**Key Functions**:
- `solar_conditions()`: Solar activity data
- `hf_band_conditions()`: HF radio propagation
- `handle_sun()`, `handle_moon()`: Celestial data

**Configuration**: `[general].spaceWeather = True`

**Dependencies**: pyephem, requests

## AI and Search Modules

### llm.py - Large Language Model Integration

**Purpose**: Provides AI-powered responses using Ollama LLM.

**Key Functions**:
- `handle_llm(message_from_id, channel_number, deviceID, message, publicChannel)`: Main LLM query handler
- `ask_ai(query)`: Direct AI query interface
- Context management and response formatting

**Configuration**: `[general]` section
- `ollama = True`: Enable Ollama integration
- `ollamaModel`: Model to use (default: gemma3:270m)
- `ollamaHostName`: Ollama server URL

**Dependencies**: requests (for Ollama API), googlesearch-python

### wikipedia.py integration - Wikipedia Search

**Purpose**: Provides Wikipedia search and summary functionality.

**Key Functions**:
- `handle_wiki(message, isDM)`: Wikipedia search handler
- `get_wikipedia_summary(search_term)`: Core search function

**Configuration**: `[general].wikipedia = True`

**Dependencies**: wikipedia API library

## Utility and Monitoring Modules

### smtp.py - Email Integration

**Purpose**: Enables email sending and receiving capabilities.

**Key Functions**:
- `handle_email(message_from_id, message)`: Email sending
- `send_email(to, subject, body)`: Core email function
- SMTP server management and authentication

**Configuration**: `[smtp]` section
- `enableSMTP = True`: Enable SMTP functionality
- `SMTP_SERVER`, `SMTP_PORT`: Server settings
- `SMTP_AUTH`, credentials: Authentication

**Dependencies**: smtplib, imaplib

### radio.py - Hamlib Radio Control

**Purpose**: Interfaces with Hamlib for radio control and monitoring.

**Key Functions**:
- `signalWatcher()`: Monitors radio signal strength
- `handleSignalWatcher()`: Processes signal alerts
- Radio control and frequency monitoring

**Configuration**: `[radioMon]` section
- `enabled = True`: Enable radio monitoring
- `rigControlServerAddress`: Hamlib server address

**Dependencies**: Hamlib/rigctld system service

### filemon.py - File Monitoring

**Purpose**: Monitors files for changes and broadcasts content.

**Key Functions**:
- `watch_file()`: File change monitoring
- `handleFileWatcher()`: File alert processing
- News file reading and broadcasting

**Configuration**: `[fileMon]` section
- `filemon_enabled = True`: Enable file monitoring
- `file_path = alert.txt`: File to monitor

**Dependencies**: watchdog library (implied)

### qrz.py - QRZ Callsign Database

**Purpose**: Provides amateur radio callsign lookup and greeting functionality.

**Key Functions**:
- New node detection and greeting
- Callsign database management

**Configuration**: `[qrz]` section
- `enabled = True`: Enable QRZ functionality
- `training = True`: Learning mode for database building

**Dependencies**: Database access

### checklist.py - Asset Tracking

**Purpose**: Manages check-in/check-out system for assets and personnel.

**Key Functions**:
- `handle_checklist(message, message_from_id, deviceID)`: Check-in/out processing
- Asset tracking and reporting

**Configuration**: `[checklist]` section
- `enabled = True`: Enable checklist functionality

**Dependencies**: Database access

## Entertainment Modules

### games/ - Game Modules

**Purpose**: Provides various games for user entertainment.

**Individual Game Modules**:
- `blackjack.py`: Blackjack card game
- `dopewar.py`: Classic drug dealing simulation
- `lemonade.py`: Lemonade stand business game
- `videopoker.py`: Video poker game
- `golfsim.py`: Golf simulation game
- `hangman.py`: Word guessing game
- `hamtest.py`: FCC/ARRL exam practice
- `mastermind.py`: Code-breaking game

**Configuration**: `[games]` section with individual enable flags

**Dependencies**: random, database for score tracking

## Web Interface Modules

### webui/main.py - Web Dashboard

**Purpose**: FastAPI-based web interface for system management.

**Key Components**:
- REST API endpoints for all system functions
- WebSocket real-time updates
- User authentication and session management
- Template rendering for web pages

**Key Endpoints**:
- `/api/v1/nodes`: Node management
- `/api/v1/messages`: Message operations
- `/api/v1/users`: User management
- `/api/v1/alerts`: Alert system
- `/ws/map`: Real-time map updates

**Dependencies**: fastapi, uvicorn, jinja2, starlette

### webui/database.py - Database Schema

**Purpose**: Defines and manages SQLite database schema.

**Key Functions**:
- `init_db()`: Database initialization and table creation
- Schema migration and updates
- Table definitions for all data entities

**Tables Created**:
- nodes, messages, users, forum_posts
- geofences, triggers, commands_queue
- alerts, alert_configs, processes, zones
- telemetry, route_traces, settings

**Dependencies**: sqlite3

### webui/db_handler.py - Database Operations

**Purpose**: Provides high-level database operations and queries.

**Key Functions**:
- CRUD operations for all entities
- Query builders and data processors
- Connection management and optimization

**Dependencies**: sqlite3, webui.database

## Configuration and Settings

### settings.py - Configuration Management

**Purpose**: Manages system configuration and settings.

**Key Functions**:
- Configuration loading and validation
- Dynamic setting updates
- Environment variable integration

**Dependencies**: configparser, os

## Module Dependencies Overview

```
mesh_bot.py (main)
├── system.py (core)
├── All feature modules
│   ├── bbstools.py
│   ├── locationdata.py
│   │   ├── wx_meteo.py
│   │   └── globalalert.py
│   ├── space.py
│   ├── llm.py
│   ├── smtp.py
│   ├── radio.py
│   ├── filemon.py
│   ├── qrz.py
│   ├── checklist.py
│   ├── games/*.py
│   └── meshgram_integration/*.py
└── webui/
    ├── main.py
    ├── database.py
    └── db_handler.py
```

## Module Loading and Initialization

Modules are loaded conditionally based on configuration settings in `config.ini`. Each module:

1. Checks its enable flag in configuration
2. Imports required dependencies
3. Registers its command handlers with the main bot
4. Initializes any background tasks or services
5. Sets up database tables if needed

This modular architecture allows for easy feature addition, removal, and maintenance while maintaining system stability.