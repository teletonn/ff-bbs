# Project Overview

## Project Name
Станция Светлячок BBS LLM WEB-UI (Firefly BBS Station with LLM and Web UI)

## Purpose and Goals

This project is a comprehensive Meshtastic network enhancement system that extends the capabilities of Meshtastic mesh networks through intelligent automation, web-based management, and AI integration. The system transforms basic Meshtastic radios into powerful communication hubs with advanced features for emergency response, data collection, and community networking.

### Primary Objectives
- **Network Enhancement**: Extend Meshtastic network functionality beyond basic messaging
- **Intelligent Automation**: Provide AI-powered responses and automated network management
- **Web-Based Management**: Offer comprehensive web interface for network monitoring and control
- **Emergency Response**: Enable rapid emergency communication and alert broadcasting
- **Data Analytics**: Collect and analyze network telemetry and usage patterns

## Main Features

### Core Communication Features
- **Intelligent Chat Bot**: Responds to commands and provides network services
- **Message Routing**: Store-and-forward messaging for offline recipients
- **Multi-Interface Support**: Simultaneous monitoring of up to 9 radio interfaces
- **Cross-Network Communication**: Bridge between different Meshtastic networks

### AI and Data Integration
- **LLM Integration**: Ollama-powered AI responses for complex queries
- **Wikipedia Search**: Automated information retrieval from Wikipedia
- **Weather Data**: NOAA and Open-Meteo weather information and alerts
- **Emergency Alerts**: FEMA, NOAA, USGS, and international emergency broadcasting

### Web Dashboard Features
- **Real-Time Map**: Live visualization of network nodes and their positions
- **User Management**: Role-based access control with Telegram integration
- **Message Monitoring**: Comprehensive message tracking and delivery status
- **System Analytics**: Network performance metrics and usage statistics

### Advanced Network Tools
- **BBS System**: Bulletin board system for community messaging
- **Check-in/Check-out**: Asset and personnel tracking system
- **Geofencing**: Location-based triggers and alerts
- **Telemetry Monitoring**: Comprehensive network health monitoring

## Technologies Used

### Core Technologies
- **Python 3.8+**: Primary programming language
- **Meshtastic Python API**: Radio communication interface
- **SQLite**: Database for persistent storage
- **FastAPI**: Web API framework
- **Jinja2**: Template engine for web interface

### Web Technologies
- **HTML5/CSS3/JavaScript**: Frontend interface
- **WebSocket**: Real-time data updates
- **Leaflet.js**: Interactive mapping
- **Chart.js**: Data visualization

### External Integrations
- **Ollama**: Local LLM for AI responses
- **Telegram Bot API**: User authentication and messaging
- **SMTP/IMAP**: Email integration
- **Hamlib**: Radio control interface
- **Various APIs**: Weather, emergency alerts, satellite data

### Key Dependencies
- `meshtastic`: Core radio communication
- `fastapi`: Web framework
- `uvicorn`: ASGI server
- `websockets`: Real-time communication
- `python-telegram-bot`: Telegram integration
- `requests`: HTTP client for APIs
- `schedule`: Task scheduling

## Project Structure

### Main Components
- **Bot Core** (`mesh_bot.py`): Main bot logic and command processing
- **Web Interface** (`webui/`): FastAPI-based dashboard and API
- **Modules** (`modules/`): Feature-specific functionality
- **Database** (`webui/database.py`): Data persistence layer
- **Configuration** (`config.ini`): System configuration

### Module Organization
- **Communication**: BBS, messaging, routing
- **Data Sources**: Weather, alerts, external APIs
- **Games**: Entertainment features
- **System**: Core utilities and helpers
- **Integration**: Telegram, email, external services

## Target Environment

### Hardware Requirements
- **Raspberry Pi** (recommended) or any Linux system
- **Meshtastic-compatible radios** (up to 9 simultaneous)
- **Internet connection** (optional, for external data services)

### Software Requirements
- **Linux OS** (Ubuntu/Debian recommended)
- **Python 3.8+**
- **Meshtastic firmware** on radios
- **Optional**: Ollama for AI features

## Development Status

The project is in active development with core functionality working. The system provides a stable platform for Meshtastic network enhancement with ongoing feature additions and improvements.

### Current Capabilities
- ✅ Basic bot functionality and command processing
- ✅ Web dashboard with real-time monitoring
- ✅ Message routing and delivery tracking
- ✅ Multi-radio interface support
- ✅ User management and authentication
- ✅ Emergency alert broadcasting

### Future Development Areas
- Enhanced AI integration
- Mobile application development
- Advanced analytics and reporting
- Plugin system for extensibility

## Community and Usage

This project serves the Meshtastic community by providing advanced tools for network operators, emergency responders, and outdoor enthusiasts. It enables more effective communication in areas with limited infrastructure and provides valuable data collection capabilities for network analysis and improvement.