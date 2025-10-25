# System Architecture

## High-Level Architecture

The Firefly BBS system follows a modular, event-driven architecture designed for reliability and extensibility in Meshtastic network environments.

### Core Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Meshtastic    │    │   Bot Core      │    │   Web UI        │
│   Radios        │◄──►│   (mesh_bot.py) │◄──►│   (FastAPI)     │
│                 │    │                 │    │                 │
│ • Serial/TCP/BLE│    │ • Command Proc. │    │ • Dashboard     │
│ • Multi-interface│    │ • Message Queue │    │ • REST API      │
│ • Packet Routing │    │ • Event Loop    │    │ • WebSocket     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   Database      │
                    │   (SQLite)      │
                    │                 │
                    │ • Messages      │
                    │ • Nodes         │
                    │ • Users         │
                    │ • Settings      │
                    │ • Telemetry     │
                    └─────────────────┘
```

## Component Details

### 1. Radio Interface Layer

**Purpose**: Handles all communication with Meshtastic radios and network packets.

**Key Components**:
- **Interface Manager**: Supports up to 9 simultaneous radio interfaces (Serial, TCP, BLE)
- **Packet Processor**: Decodes incoming packets and routes them to appropriate handlers
- **Connection Monitor**: Automatic reconnection and health monitoring
- **Multi-Interface Coordination**: Synchronizes operations across multiple radios

**Responsibilities**:
- Raw packet reception and transmission
- Interface health monitoring and reconnection
- Packet routing between different radio networks
- Telemetry data collection

### 2. Bot Core (mesh_bot.py)

**Purpose**: Central intelligence and command processing engine.

**Key Components**:
- **Command Processor**: Parses and executes user commands
- **Message Router**: Handles store-and-forward messaging
- **Event Loop**: Asynchronous task coordination
- **Module Loader**: Dynamic loading of feature modules

**Responsibilities**:
- Command interpretation and execution
- Message queuing and delivery
- Background task management
- Integration with external services

### 3. Web Interface Layer

**Purpose**: Provides web-based management and monitoring capabilities.

**Key Components**:
- **FastAPI Application**: REST API and web serving
- **WebSocket Server**: Real-time data streaming
- **Template Engine**: Dynamic HTML generation
- **Authentication System**: User management and access control

**Responsibilities**:
- User interface serving
- API endpoint handling
- Real-time data broadcasting
- Session management

### 4. Database Layer

**Purpose**: Persistent data storage and retrieval.

**Key Components**:
- **SQLite Database**: Main data store
- **Schema Manager**: Database structure maintenance
- **Connection Pool**: Efficient database access
- **Migration System**: Schema updates and data preservation

**Responsibilities**:
- Data persistence
- Query optimization
- Backup and recovery
- Data integrity maintenance

## Data Flow Architecture

### Message Processing Flow

```
User Message → Radio Interface → Packet Decoder → Command Parser → Module Handler → Response Generation → Message Queue → Radio Transmission
```

### Real-Time Data Flow

```
Radio Telemetry → Packet Processor → Database Storage → WebSocket Broadcast → UI Update
```

### Command Execution Flow

```
Web/API Request → Authentication → Command Queue → Bot Core → Module Execution → Database Update → Response
```

## Module Architecture

The system uses a modular architecture where features are organized into separate modules:

### Core Modules
- **system.py**: Core utilities, interface management, telemetry
- **bbstools.py**: Bulletin board system functionality
- **locationdata.py**: Weather, alerts, and location services
- **llm.py**: AI/LLM integration

### Feature Modules
- **games/**: Entertainment features (Blackjack, DopeWars, etc.)
- **smtp.py**: Email integration
- **radio.py**: Hamlib radio control
- **filemon.py**: File monitoring and alerts

### Integration Modules
- **meshgram_integration/**: Telegram bot integration
- **wx_meteo.py**: Alternative weather API
- **globalalert.py**: International emergency alerts

## Communication Patterns

### Synchronous Communication
- Command processing and immediate responses
- Database queries and updates
- API endpoint responses

### Asynchronous Communication
- Background task processing (alerts, telemetry)
- Message queuing and delivery
- WebSocket broadcasting

### Event-Driven Communication
- Packet reception triggers
- Timer-based operations
- External service integrations

## Security Architecture

### Authentication & Authorization
- **Session-based authentication** for web interface
- **Role-based access control** (admin, user, guest)
- **Telegram integration** for user verification
- **API key management** for external services

### Data Protection
- **Input validation** on all user inputs
- **SQL injection prevention** through parameterized queries
- **XSS protection** in web templates
- **Rate limiting** on API endpoints

### Network Security
- **Interface isolation** between radio networks
- **Message filtering** and spam prevention
- **Emergency override** capabilities
- **Audit logging** for security events

## Scalability Considerations

### Horizontal Scaling
- **Multi-radio support**: Up to 9 simultaneous interfaces
- **Database optimization**: Indexed queries and WAL mode
- **Asynchronous processing**: Non-blocking operations

### Performance Optimization
- **Message chunking**: Large message handling
- **Connection pooling**: Efficient database access
- **Caching**: Frequently accessed data
- **Background processing**: CPU-intensive tasks

## Deployment Architecture

### Single-Node Deployment
```
┌─────────────────────────────────────┐
│         Raspberry Pi / Server       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ │
│  │  Radio  │ │   Bot   │ │  WebUI  │ │
│  │ Interface│ │  Core   │ │         │ │
│  └─────────┘ └─────────┘ └─────────┘ │
│  ┌─────────────────────────────────┐ │
│  │        SQLite Database          │ │
│  └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

### Multi-Node Deployment
```
┌─────────────┐    ┌─────────────┐
│ Node 1      │    │ Node 2      │
│ • Radio Int │    │ • Radio Int │
│ • Bot Core  │◄──►│ • Bot Core  │
│ • Database  │    │ • Database  │
└─────────────┘    └─────────────┘
       │                   │
       └─────────┬─────────┘
                 │
          ┌─────────────┐
          │ Central     │
          │ Web UI      │
          │ Dashboard   │
          └─────────────┘
```

## Error Handling and Resilience

### Fault Tolerance
- **Interface failover**: Automatic reconnection on radio disconnect
- **Message persistence**: Queued messages survive restarts
- **Graceful degradation**: Core functionality preserved during partial failures

### Monitoring and Alerting
- **Health checks**: Regular interface and service monitoring
- **Error logging**: Comprehensive error tracking
- **Alert broadcasting**: Critical issue notification
- **Performance metrics**: System resource monitoring

## Configuration Management

### Configuration Sources
- **config.ini**: Main configuration file
- **Environment variables**: Runtime overrides
- **Database settings**: Dynamic configuration
- **Module-specific configs**: Feature-specific settings

### Configuration Hierarchy
1. **Default values** in code
2. **config.ini** settings
3. **Environment variables**
4. **Database overrides**
5. **Runtime modifications**

This architecture provides a robust, scalable foundation for Meshtastic network enhancement while maintaining flexibility for future expansion and customization.