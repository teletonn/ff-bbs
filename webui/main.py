import uvicorn
from fastapi import FastAPI, Request, Query, Path, HTTPException, Depends, Form, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import secrets
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone, timedelta
from .database import init_db
import asyncio
from .db_handler import (
    get_db_connection, insert_command, get_nodes,
    get_geofences, get_geofence, create_geofence, update_geofence, delete_geofence,
    get_triggers, get_trigger, create_trigger, update_trigger, delete_trigger,
    register_user, authenticate_user, get_users, get_user, update_user, delete_user,
    get_all_settings, set_setting, sync_config_to_db,
    get_total_users, get_active_users, get_today_messages, get_bot_status, get_recent_activity,
    get_groups, get_group, create_group, update_group, delete_group,
    get_user_groups, assign_user_to_group, remove_user_from_group, get_group_users,
    get_bot_uptime, get_bot_last_activity, get_command_usage_stats, get_response_time_stats,
    get_error_stats, get_bot_settings, set_bot_settings,
    get_alerts, get_alert, create_alert, update_alert_status, delete_alert,
    get_alert_configs, get_alert_config, create_alert_config, update_alert_config, delete_alert_config,
    get_processes, get_process, create_process, update_process, delete_process, update_process_run_count,
    get_zones, get_zone, create_zone, update_zone, delete_zone, get_active_zones, get_active_triggers,
    update_message_status, retry_message, delete_message_by_user, update_node_on_packet,
    update_old_sent_messages_to_delivered, mark_sent_messages_as_undelivered,
    get_fimesh_transfers, create_fimesh_transfer, update_fimesh_transfer_status
)
import sqlite3
import json
import configparser
import logging
import os
import asyncio
from typing import List
import json
import re
from modules.log import logger

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                # Remove broken connections
                self.active_connections.remove(connection)

manager = ConnectionManager()

# Background task for message retry mechanism
async def message_retry_task():
    """Periodic task to mark sent messages as undelivered after timeout."""
    while True:
        try:
            mark_sent_messages_as_undelivered()
        except Exception as e:
            print(f"Error in message retry task: {e}")
        # Run every 5 minutes
        await asyncio.sleep(300)

app = FastAPI(
    title="Firefly-BBS Web Dashboard",
    description="Веб-интерфейс для управления и мониторинга сети 'Светлячок'.",
    version="0.1.0"
)

# Инициализация базы данных при старте
try:
    init_db()
    sync_config_to_db()
    print("База данных успешно инициализирована.")

    # Create initial admin user if no users exist
    if not get_users(None):
        admin_id = register_user('admin', 'admin123', role='admin')
        if admin_id:
            # Ensure admin has node_id
            user = get_user(admin_id)
            if not user.get('node_id'):
                node_id = f"web_{admin_id}"
                update_user(admin_id, node_id=node_id)
                print(f"Assigned virtual node_id {node_id} to admin user {admin_id}")
            print("Created initial admin user: username=admin, password=admin")
        else:
            print("Failed to create initial admin user")

except Exception as e:
    logger.error(f"Ошибка при инициализации базы данных: {e}")
    print(f"Ошибка при инициализации базы данных: {e}")

@app.on_event("startup")
async def startup_event():
    """Start background tasks when the application starts."""
    try:
        asyncio.create_task(message_retry_task())
        print("Message retry background task started")
        logger.info("Message retry background task started")
    except Exception as e:
        print(f"Failed to start message retry task: {e}")
        logger.error(f"Failed to start message retry task: {e}")

app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32), max_age=86400*30)  # 30 days persistence

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Allow access to login, register, static files, and API endpoints
        public_paths = ["/login", "/register", "/static", "/api"]
        if not any(request.url.path.startswith(path) for path in public_paths):
            if "session" in request.scope and 'user_id' not in request.scope["session"]:
                return RedirectResponse(url="/login")
        response = await call_next(request)
        return response

app.add_middleware(AuthMiddleware)

# Подключение статических файлов (CSS, JS, изображения)
app.mount("/static", StaticFiles(directory="webui/static"), name="static")

# Подключение шаблонизатора Jinja2
templates = Jinja2Templates(directory="webui/templates")

# Список страниц для навигационного меню
# (название, путь)
menu_items = [
    ("Сводка", "/dashboard"),
    ("Сообщения", "/messages"),
    ("Карта", "/map"),
    ("Ноды", "/nodes"),
    ("Пользователи", "/users"),
    ("Форум", "/forum"),
    ("Геозоны", "/zones"),
    ("Триггеры", "/triggers"),
    ("Оповещения", "/alerts"),
    ("Процессы", "/processes"),
    ("Бот", "/bot"),
    ("Конфиг Оповещений", "/alert_config"),
    ("FiMesh", "/fimesh"),
    ("Настройки", "/settings"),
]

def get_current_user(request: Request):
    user_id = request.session.get('user_id')
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_user(user_id)
    if not user:
        request.session.clear()
        raise HTTPException(status_code=401, detail="User not found")
    return user

def login_required(current_user: dict = Depends(get_current_user)):
    return current_user

def render_template(template_name: str, request: Request, **kwargs):
    """Хелпер для рендеринга шаблонов с добавлением общих данных."""
    user_agent = request.headers.get('User-Agent', '')
    is_mobile = 'Android' in user_agent or 'iPhone' in user_agent or 'iPad' in user_agent or 'Mobile' in user_agent
    context = {
        "request": request,
        "menu_items": menu_items,
        "page_title": kwargs.get("page_title", "Дашборд"),
        "is_authenticated": 'user_id' in request.session,
        "is_mobile": is_mobile
    }
    context.update(kwargs)
    return templates.TemplateResponse(template_name, context)

@app.get("/", response_class=RedirectResponse, include_in_schema=False)
async def root(request: Request):
    """Перенаправляет с корневого URL на login если не авторизован, иначе на дашборд."""
    if 'user_id' in request.session:
        return RedirectResponse(url="/dashboard")
    else:
        return RedirectResponse(url="/login")

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Отображает главную страницу-сводку."""
    return render_template("dashboard.html", request, page_title="Сводка")

@app.get("/messages", response_class=HTMLResponse)
async def get_messages(request: Request):
    """Отображает страницу с сообщениями."""
    return render_template("messages.html", request, page_title="Сообщения")

@app.get("/nodes", response_class=HTMLResponse)
async def get_nodes_page(request: Request):
    """Отображает страницу со списком узлов сети."""
    nodes_list = get_nodes(request)
    return render_template("nodes.html", request, page_title="Ноды", nodes=nodes_list)

@app.get("/mobile/nodes", response_class=HTMLResponse)
async def get_mobile_nodes_page(request: Request):
    """Отображает мобильную страницу со списком узлов сети."""
    nodes_list = get_nodes(request)
    return render_template("mobile/nodes.html", request, page_title="Ноды", nodes=nodes_list)

@app.get("/mobile/alerts", response_class=HTMLResponse)
async def get_mobile_alerts_page(request: Request, current_user: dict = Depends(login_required)):
    """Отображает мобильную страницу оповещений."""
    return render_template("mobile/alerts.html", request, page_title="Оповещения")

@app.get("/mobile/processes", response_class=HTMLResponse)
async def get_mobile_processes_page(request: Request, current_user: dict = Depends(login_required)):
    """Отображает мобильную страницу автоматизированных процессов."""
    return render_template("mobile/processes.html", request, page_title="Автоматизированные Процессы")

@app.get("/mobile/settings", response_class=HTMLResponse)
async def get_mobile_settings(request: Request, current_user: dict = Depends(login_required)):
    """Отображает мобильную страницу настроек."""
    settings = get_all_settings()
    sections = {}
    for key, value in settings.items():
        if '.' in key:
            sec, opt = key.split('.', 1)
            if sec not in sections:
                sections[sec] = {}
            sections[sec][opt] = {'value': value, 'key': key}
        else:
            if 'default' not in sections:
                sections['default'] = {}
            sections['default'][key] = {'value': value, 'key': key}
    return render_template("mobile/settings.html", request, page_title="Настройки", sections=sections)

@app.get("/mobile/triggers", response_class=HTMLResponse)
def get_mobile_triggers_page(request: Request):
    """Отображает мобильную страницу управления триггерами."""
    triggers_list = get_triggers(request)
    return render_template("mobile/triggers.html", request, page_title="Триггеры", triggers=triggers_list)

@app.get("/mobile/users", response_class=HTMLResponse)
async def get_mobile_users_page(request: Request):
    """Отображает мобильную страницу управления пользователями дашборда."""
    users_list = get_users(request)
    return render_template("mobile/users.html", request, page_title="Пользователи", users=users_list)

@app.get("/mobile/zones", response_class=HTMLResponse)
async def get_mobile_zones_page(request: Request, current_user: dict = Depends(login_required)):
    """Отображает мобильную страницу гео-зон."""
    return render_template("mobile/zones.html", request, page_title="Гео-зоны")

@app.get("/mobile/alert_config", response_class=HTMLResponse)
async def get_mobile_alert_config_page(request: Request, current_user: dict = Depends(login_required)):
    """Отображает мобильную страницу конфигурации оповещений."""
    return render_template("mobile/alert_config.html", request, page_title="Конфигурация Оповещений")

@app.get("/users", response_class=HTMLResponse)
async def get_users_page(request: Request):
    """Отображает страницу управления пользователями дашборда."""
    users_list = get_users(request)
    return render_template("users.html", request, page_title="Пользователи", users=users_list)

@app.get("/forum", response_class=HTMLResponse)
async def get_forum(request: Request):
    """Отображает форум."""
    return render_template("forum.html", request, page_title="Форум")

@app.get("/map", response_class=HTMLResponse)
async def get_map(request: Request):
    """Отображает карту сети."""
    return render_template("map.html", request, page_title="Карта")

@app.get("/geofences", response_class=HTMLResponse)
def get_geofences_page(request: Request):
    """Отображает страницу управления гео-зонами."""
    geofences_list = get_geofences(request)
    return render_template("geofences.html", request, page_title="Зоны", geofences=geofences_list)

@app.get("/triggers", response_class=HTMLResponse)
def get_triggers_page(request: Request):
    """Отображает страницу управления триггерами."""
    triggers_list = get_triggers(request)
    return render_template("triggers.html", request, page_title="Триггеры", triggers=triggers_list)

@app.get("/bot", response_class=HTMLResponse)
async def get_bot(request: Request, current_user: dict = Depends(login_required)):
    """Отображает страницу управления ботом."""
    return render_template("bot.html", request, page_title="Управление Ботом")

@app.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request, current_user: dict = Depends(login_required)):
    """Отображает страницу настроек."""
    settings = get_all_settings()
    sections = {}
    for key, value in settings.items():
        if '.' in key:
            sec, opt = key.split('.', 1)
            if sec not in sections:
                sections[sec] = {}
            sections[sec][opt] = {'value': value, 'key': key}
        else:
            if 'default' not in sections:
                sections['default'] = {}
            sections['default'][key] = {'value': value, 'key': key}
    return render_template("settings.html", request, page_title="Настройки", sections=sections)

@app.get("/alerts", response_class=HTMLResponse)
async def get_alerts_page(request: Request, current_user: dict = Depends(login_required)):
    """Отображает страницу оповещений."""
    return render_template("alerts.html", request, page_title="Оповещения")

@app.get("/alert_config", response_class=HTMLResponse)
async def get_alert_config_page(request: Request, current_user: dict = Depends(login_required)):
    """Отображает страницу конфигурации оповещений."""
    return render_template("alert_config.html", request, page_title="Конфигурация Оповещений")

@app.get("/processes", response_class=HTMLResponse)
async def get_processes_page(request: Request, current_user: dict = Depends(login_required)):
    """Отображает страницу автоматизированных процессов."""
    return render_template("processes.html", request, page_title="Автоматизированные Процессы")

@app.get("/zones", response_class=HTMLResponse)
async def get_zones_page(request: Request, current_user: dict = Depends(login_required)):
    """Отображает страницу гео-зон."""
    return render_template("zones.html", request, page_title="Гео-зоны")

@app.get("/fimesh", response_class=HTMLResponse)
async def get_fimesh_page(request: Request):
    """Отображает страницу FiMesh."""
    return render_template("fimesh.html", request, page_title="FiMesh")

# WebSocket endpoint for real-time updates
@app.websocket("/ws/map")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, data is pushed from mesh_bot
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Route to serve service-worker.js
@app.get("/service-worker.js")
async def get_service_worker():
    return FileResponse("webui/static/service-worker.js", media_type="application/javascript")

# Function to broadcast map updates
async def broadcast_map_update(update_type: str, data: dict):
    """Broadcast map data updates to all connected WebSocket clients."""
    message = {
        "type": update_type,
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    await manager.broadcast(json.dumps(message))

# Function to broadcast message updates
async def broadcast_message_update(update_type: str, data: dict):
    """Broadcast message data updates to all connected WebSocket clients."""
    message = {
        "type": update_type,
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    await manager.broadcast(json.dumps(message))

# Auth routes
@app.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    return render_template("login.html", request, page_title="Вход")

@app.post("/login")
async def post_login(
    username: str = Form(...),
    password: str = Form(...),
    request: Request = None
):
    if len(username) < 3 or len(username) > 20:
        raise HTTPException(400, "Username must be 3-20 characters")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    
    request.session['user_id'] = user['id']
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/register", response_class=HTMLResponse)
async def get_register(request: Request):
    return render_template("register.html", request, page_title="Регистрация")

@app.post("/register")
async def post_register(
    username: str = Form(...),
    password: str = Form(...),
    nickname: str = Form(None),
    email: str = Form(None),
    request: Request = None
):
    if len(username) < 3 or len(username) > 20:
        raise HTTPException(400, "Username must be 3-20 characters")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    user_id = register_user(username, password, nickname, email=email)
    if not user_id:
        raise HTTPException(400, "Username already exists")

    # Ensure user has node_id for message sending
    user = get_user(user_id)
    if not user.get('node_id'):
        node_id = f"web_{user_id}"
        update_user(user_id, node_id=node_id)
        logging.info(f"Assigned virtual node_id {node_id} to user {user_id}")

    request.session['user_id'] = user_id
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/api/v1/users/register", dependencies=[Depends(login_required)])
async def api_register_user(request: Request, current_user: dict = Depends(get_current_user)):
    """Manual user registration via API (admin only)."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")

    try:
        body = await request.json()
        username = body.get('username')
        password = body.get('password')
        nickname = body.get('nickname')
        node_id = body.get('node_id')
        email = body.get('email')
        telegram_id = body.get('telegram_id')
        telegram_first_name = body.get('telegram_first_name')
        telegram_last_name = body.get('telegram_last_name')
        telegram_username = body.get('telegram_username')
        mesh_node_id = body.get('mesh_node_id')
        is_active = body.get('is_active', 1)
        role = body.get('role', 'user')  # Registration always creates users, admin role only via edit

        if not username or not password:
            raise HTTPException(400, "Username and password are required")

        if len(username) < 3 or len(username) > 20:
            raise HTTPException(400, "Username must be 3-20 characters")
        if len(password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")

        # Validate node_id format if provided
        if node_id and not node_id.isdigit():
            raise HTTPException(400, "Node ID must contain only digits")

        # Validate mesh_node_id format if provided
        if mesh_node_id and not re.match(r'^![0-9a-fA-F]{8}$', mesh_node_id):
            raise HTTPException(400, "Mesh Node ID must be in format !12345678 (exclamation mark followed by 8 hexadecimal digits)")

        user_id = register_user(username, password, nickname, node_id, email, role)
        if not user_id:
            raise HTTPException(400, "Username or node_id already exists")

        # Update additional fields
        update_data = {}
        if telegram_id is not None:
            update_data['telegram_id'] = telegram_id
        if telegram_first_name is not None:
            update_data['telegram_first_name'] = telegram_first_name
        if telegram_last_name is not None:
            update_data['telegram_last_name'] = telegram_last_name
        if telegram_username is not None:
            update_data['telegram_username'] = telegram_username
        if mesh_node_id is not None:
            update_data['mesh_node_id'] = mesh_node_id
        if is_active is not None:
            update_data['is_active'] = is_active

        if update_data:
            update_user(user_id, **update_data)

        return {"success": True, "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error registering user: {e}")
        raise HTTPException(500, "Internal server error")

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# API v1 Routes for Phase 2

@app.get("/api/v1/nodes")
async def api_get_nodes():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT n.node_id as id, n.name, n.last_seen, n.battery_level, n.latitude as lat, n.longitude as lng, n.altitude,
                    n.snr, n.rssi, n.hop_count, n.pki_status, n.hardware_model, n.firmware_version, n.role, n.is_online, n.last_telemetry,
                    n.ground_speed, n.precision_bits,
                    u.username, u.nickname, u.email, u.role as user_role
            FROM nodes n
            LEFT JOIN users u ON n.node_id = u.node_id
            ORDER BY n.last_seen DESC
        """)
        rows = cursor.fetchall()
        nodes = []
        for row in rows:
            node = dict(zip(['id', 'name', 'last_seen', 'battery_level', 'lat', 'lng', 'altitude',
                            'snr', 'rssi', 'hop_count', 'pki_status', 'hardware_model', 'firmware_version', 'role', 'is_online', 'last_telemetry',
                            'ground_speed', 'precision_bits',
                            'username', 'nickname', 'email', 'user_role'], row))
            nodes.append(node)
        return nodes
    except sqlite3.Error as e:
        print(f"Database error in /api/v1/nodes: {e}")
        return []
    finally:
        conn.close()

@app.get("/api/v1/routes")
async def api_get_routes(hours: int = Query(24, ge=0), node_id: str = Query(None)):
    """Get route data from telemetry table with time-based filtering."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Calculate time threshold
        if hours == 0:  # All time
            time_filter = ""
            params = []
        else:
            time_threshold = datetime.now() - timedelta(hours=hours)
            time_filter = " AND t.timestamp >= ?"
            params = [time_threshold.timestamp()]

        # Filter by node if specified
        node_filter = ""
        if node_id:
            node_filter = " AND t.node_id = ?"
            params.append(node_id)

        query = f"""
            SELECT t.node_id, t.timestamp, t.latitude, t.longitude, t.altitude,
                   n.name, n.last_seen
            FROM telemetry t
            LEFT JOIN nodes n ON t.node_id = n.node_id
            WHERE t.latitude IS NOT NULL AND t.longitude IS NOT NULL{time_filter}{node_filter}
            ORDER BY t.node_id, t.timestamp ASC
        """

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Group by node_id
        routes = {}
        for row in rows:
            node_id_val, timestamp, lat, lng, alt, name, last_seen = row
            if node_id_val not in routes:
                routes[node_id_val] = {
                    'node_id': node_id_val,
                    'name': name or f'Node {node_id_val}',
                    'last_seen': last_seen,
                    'points': []
                }
            routes[node_id_val]['points'].append({
                'timestamp': timestamp,
                'lat': lat,
                'lng': lng,
                'alt': alt
            })

        return list(routes.values())
    except sqlite3.Error as e:
        print(f"Database error in /api/v1/routes: {e}")
        return []
    finally:
        conn.close()

@app.post("/api/v1/register_node")
async def api_register_node(request: Request):
    try:
        body = await request.json()
        node_id = body.get('node_id')
        username = body.get('username')
        password = body.get('password')
        nickname = body.get('nickname')
        email = body.get('email')

        if not all([node_id, username, password]):
            raise HTTPException(400, "node_id, username, password required")

        if len(username) < 3 or len(username) > 20:
            raise HTTPException(400, "Username must be 3-20 characters")
        if len(password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")

        # Check if node_id taken
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE node_id = ?", (node_id,))
        if cursor.fetchone():
            raise HTTPException(400, "Node ID already registered")

        user_id = register_user(username, password, nickname, node_id, email)
        if not user_id:
            raise HTTPException(400, "Username already exists")

        return {"success": True, "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in register_node: {e}")
        raise HTTPException(500, "Internal server error")

@app.get("/api/v1/messages")
async def api_get_messages(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    msg_type: str = Query(None, alias="type"),
    source: str = Query(None),
    dm_only: bool = Query(False),
    channel_only: bool = Query(False)
):
    # Removed: No longer auto-marking sent messages as delivered after timeout
    # update_old_sent_messages_to_delivered()

    offset = (page - 1) * limit
    conn = get_db_connection()
    try:
        base_query = """
            SELECT m.id, m.message_id, m.from_node_id as from_id, m.to_node_id as to_id, m.channel, m.text, m.timestamp, m.is_dm,
                   m.status, m.attempt_count, m.last_attempt_time, m.next_retry_time, m.error_message, m.defer_count,
                   fn.name as from_name, tn.name as to_name
            FROM messages m
            LEFT JOIN nodes fn ON m.from_node_id = fn.node_id
            LEFT JOIN nodes tn ON m.to_node_id = tn.node_id
            ORDER BY m.timestamp DESC
        """
        params = []
        where_clauses = []
        if msg_type:
            where_clauses.append("m.channel = ?")
            params.append(msg_type)
        if source:
            where_clauses.append("m.from_node_id = ?")
            params.append(source)
        if dm_only:
            where_clauses.append("m.is_dm = 1")
        if channel_only:
            where_clauses.append("m.is_dm = 0")
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)
        base_query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = conn.cursor()
        cursor.execute(base_query, params)
        rows = cursor.fetchall()
        keys = ['id', 'message_id', 'from_id', 'to_id', 'channel', 'text', 'timestamp', 'is_dm', 'status', 'attempt_count', 'last_attempt_time', 'next_retry_time', 'error_message', 'defer_count', 'from_name', 'to_name']
        messages = [dict(zip(keys, row)) for row in rows]
        for msg in messages:
            msg["is_dm"] = bool(msg["is_dm"])
            if msg['timestamp']:
                if isinstance(msg['timestamp'], str):
                    # Parse string timestamp in format '2025-10-05 10:52:26' as UTC
                    dt_utc = datetime.strptime(msg['timestamp'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                else:
                    # Assume numeric unix timestamp
                    dt_utc = datetime.fromtimestamp(float(msg['timestamp']), tz=timezone.utc)
                moscow_tz = timezone(timedelta(hours=3))
                dt_moscow = dt_utc.astimezone(moscow_tz)
                msg['timestamp'] = dt_moscow.strftime('%d.%m.%Y %H:%M:%S')
        return messages
    except sqlite3.Error as e:
        print(f"Database error in /api/v1/messages: {e}")
        return []
    finally:
        conn.close()

@app.post("/api/v1/messages/{message_id}/retry", dependencies=[Depends(login_required)])
async def api_retry_message(message_id: str, current_user: dict = Depends(get_current_user)):
    """Retry sending a message."""
    try:
        success = retry_message(message_id)
        if not success:
            raise HTTPException(status_code=404, detail="Message not found or retry failed")
        return {"success": True, "message": "Message queued for retry"}
    except Exception as e:
        print(f"Error retrying message {message_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/v1/messages/{message_id}", dependencies=[Depends(login_required)])
async def api_delete_message(message_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a message by the user who sent it."""
    try:
        success = delete_message_by_user(message_id, current_user['id'])
        if not success:
            raise HTTPException(status_code=404, detail="Message not found or access denied")
        return {"success": True, "message": "Message deleted"}
    except Exception as e:
        print(f"Error deleting message {message_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/forum/topics")
async def api_get_topics():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT topic as id, topic as title, MIN(timestamp) as timestamp
            FROM forum_posts
            GROUP BY topic
            ORDER BY MIN(timestamp) DESC
        """)
        rows = cursor.fetchall()
        topics = []
        for row in rows:
            topic_dict = dict(zip(['id', 'title', 'timestamp'], row))
            topic_dict['author'] = 'Unknown'
            topics.append(topic_dict)
        return topics
    except sqlite3.Error as e:
        print(f"Database error in /api/v1/forum/topics: {e}")
        return []
    finally:
        conn.close()

@app.get("/api/v1/forum/posts/{topic_id}")
async def api_get_posts(topic_id: str = Path(...)):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, content, author_id as author, timestamp
            FROM forum_posts
            WHERE topic = ?
            ORDER BY timestamp ASC
        """, (topic_id,))
        rows = cursor.fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="Topic not found")
        keys = ['id', 'content', 'author', 'timestamp']
        posts = [dict(zip(keys, row)) for row in rows]
        for post in posts:
            post['author'] = 'Unknown' if post['author'] is None else post['author']
        return posts
    except sqlite3.Error as e:
        print(f"Database error in /api/v1/forum/posts/{topic_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()

@app.get("/api/v1/stats")
async def api_get_stats():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM nodes")
        total_nodes = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM messages")
        total_messages = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT topic) FROM forum_posts")
        active_topics = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT from_node_id) FROM messages")
        active_users = cursor.fetchone()[0]

        # New metrics for Phase 3
        total_users = get_total_users()
        active_users_24h = get_active_users(24)
        today_messages = get_today_messages()
        bot_status = get_bot_status()

        return {
            "total_nodes": total_nodes,
            "total_messages": total_messages,
            "active_topics": active_topics,
            "active_users": active_users,
            "total_users": total_users,
            "active_users_24h": active_users_24h,
            "today_messages": today_messages,
            "bot_status": bot_status
        }
    except sqlite3.Error as e:
        print(f"Database error in /api/v1/stats: {e}")
        return {
            "total_nodes": 0,
            "total_messages": 0,
            "active_topics": 0,
            "active_users": 0,
            "total_users": 0,
            "active_users_24h": 0,
            "today_messages": 0,
            "bot_status": "unknown"
        }
    finally:
        conn.close()

@app.get("/api/v1/activity")
async def api_get_activity(limit: int = Query(20, ge=1, le=100)):
    """Get recent activity feed."""
    try:
        activity = get_recent_activity(limit)
        # Format the activity for JSON response
        formatted_activity = []
        for item in activity:
            formatted_activity.append({
                "type": item[0],
                "source": item[1],
                "content": item[2],
                "timestamp": item[3]
            })
        return formatted_activity
    except Exception as e:
        print(f"Error in /api/v1/activity: {e}")
        return []


@app.get("/api/v1/geofences", dependencies=[Depends(login_required)])
async def api_get_geofences():
    """GET: Retrieve list of geofences."""
    return get_geofences(None)

@app.get("/api/v1/triggers", dependencies=[Depends(login_required)])
async def api_get_triggers():
    """GET: Retrieve list of triggers."""
    return get_triggers(None)

@app.post("/api/v1/geofences", dependencies=[Depends(login_required)])
async def api_create_geofence(request: Request):
    """POST: Create a new geofence."""
    try:
        body = await request.json()
        name = body.get('name')
        latitude = body.get('latitude')
        longitude = body.get('longitude')
        radius = body.get('radius', 100)
        active = body.get('active', 1)

        if not name or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)) or not isinstance(radius, (int, float)):
            raise HTTPException(status_code=400, detail="Missing or invalid required fields: name (str), latitude (float), longitude (float), radius (float > 0)")

        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180) or radius <= 0:
            raise HTTPException(status_code=400, detail="Invalid coordinates: lat [-90,90], lon [-180,180], radius > 0")

        geofence_id = create_geofence(name, latitude, longitude, radius, active)
        if geofence_id:
            return {"id": geofence_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to create geofence")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error creating geofence: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/geofences/{geofence_id}", dependencies=[Depends(login_required)])
async def api_get_geofence(geofence_id: int):
    """GET: Retrieve a single geofence."""
    geofence = get_geofence(geofence_id)
    if not geofence:
        raise HTTPException(status_code=404, detail="Geofence not found")
    return geofence

@app.put("/api/v1/geofences/{geofence_id}", dependencies=[Depends(login_required)])
async def api_update_geofence(geofence_id: int, request: Request):
    """PUT: Update a geofence (full update)."""
    try:
        body = await request.json()
        name = body.get('name')
        latitude = body.get('latitude')
        longitude = body.get('longitude')
        radius = body.get('radius')
        active = body.get('active', 1)

        if name is None or latitude is None or longitude is None or radius is None:
            raise HTTPException(status_code=400, detail="Required fields: name, latitude, longitude, radius")

        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180) or radius <= 0:
            raise HTTPException(status_code=400, detail="Invalid coordinates: lat [-90,90], lon [-180,180], radius > 0")

        updated = update_geofence(geofence_id, name, latitude, longitude, radius, active)
        if not updated:
            raise HTTPException(status_code=404, detail="Geofence not found")
        return {"success": True}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error updating geofence: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/v1/geofences/{geofence_id}", dependencies=[Depends(login_required)])
async def api_delete_geofence(geofence_id: int):
    """DELETE: Remove a geofence."""
    deleted = delete_geofence(geofence_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Geofence not found")
    return {"success": True}

@app.post("/api/v1/triggers", dependencies=[Depends(login_required)])
async def api_create_trigger(request: Request):
    """POST: Create a new trigger."""
    try:
        body = await request.json()
        logging.info(f"POST /api/v1/triggers payload: {body}")
        zone_id = body.get('zone_id')
        event_type = body.get('event_type')
        action_type = body.get('action_type')
        action_payload = json.dumps(body.get('action_payload', {}))
        name = body.get('name', '')
        description = body.get('description', '')
        active = body.get('active', 1)

        logging.info(f"Extracted zone_id: {zone_id} (type: {type(zone_id)})")
        logging.info(f"event_type: {event_type}, action_type: {action_type}")

        if not zone_id or event_type not in ['enter', 'exit'] or not action_type:
            raise HTTPException(status_code=400, detail="Required: zone_id (int), event_type ('enter' or 'exit'), action_type (str)")

        # Validate zone exists
        zone_exists = get_zone(zone_id)
        logging.info(f"Zone exists check for zone_id {zone_id}: {zone_exists is not None}")
        if zone_exists:
            logging.info(f"Zone data: {zone_exists}")
        if not zone_exists:
            logging.error(f"Zone {zone_id} does not exist in database")
            raise HTTPException(status_code=400, detail="Invalid zone_id")

        # Basic validation for action_payload JSON
        try:
            json.loads(action_payload)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="action_payload must be valid JSON")

        logging.info(f"About to create trigger with zone_id={zone_id}, event_type={event_type}, action_type={action_type}")
        trigger_id = create_trigger(zone_id, event_type, action_type, action_payload, name, description, active)
        logging.info(f"create_trigger returned: {trigger_id}")
        if trigger_id:
            return {"id": trigger_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to create trigger")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logging.error(f"Error creating trigger: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/triggers/{trigger_id}", dependencies=[Depends(login_required)])
async def api_get_trigger(trigger_id: int):
    """GET: Retrieve a single trigger."""
    trigger = get_trigger(trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return trigger

@app.put("/api/v1/triggers/{trigger_id}", dependencies=[Depends(login_required)])
async def api_update_trigger(trigger_id: int, request: Request):
    """PUT: Update a trigger (full update)."""
    try:
        body = await request.json()
        zone_id = body.get('zone_id')
        event_type = body.get('event_type')
        action_type = body.get('action_type')
        action_payload = json.dumps(body.get('action_payload', {}))
        name = body.get('name', '')
        description = body.get('description', '')
        active = body.get('active', 1)

        if zone_id is None or event_type is None or action_type is None:
            raise HTTPException(status_code=400, detail="Required: zone_id, event_type, action_type")

        if event_type not in ['enter', 'exit']:
            raise HTTPException(status_code=400, detail="event_type must be 'enter' or 'exit'")

        if not get_zone(zone_id):
            raise HTTPException(status_code=400, detail="Invalid zone_id")

        try:
            json.loads(action_payload)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="action_payload must be valid JSON")

        updated = update_trigger(trigger_id, zone_id, event_type, action_type, action_payload, name, description, active)
        if not updated:
            raise HTTPException(status_code=404, detail="Trigger not found")
        return {"success": True}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error updating trigger: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.patch("/api/v1/triggers/{trigger_id}/toggle_active", dependencies=[Depends(login_required)])
async def api_toggle_trigger_active(trigger_id: int, request: Request):
    """PATCH: Toggle active status of a trigger."""
    try:
        body = await request.json()
        active = body.get('active')
        if active is None:
            raise HTTPException(status_code=400, detail="active field is required")

        # Get current trigger to update only active field
        trigger = get_trigger(trigger_id)
        if not trigger:
            raise HTTPException(status_code=404, detail="Trigger not found")

        updated = update_trigger(trigger_id, trigger['zone_id'], trigger['event_type'],
                                trigger['action_type'], json.dumps(trigger['action_payload']),
                                trigger.get('name', ''), trigger.get('description', ''), active)
        if not updated:
            raise HTTPException(status_code=404, detail="Trigger not found")
        return {"success": True}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error toggling trigger active status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/v1/triggers/{trigger_id}", dependencies=[Depends(login_required)])
async def api_delete_trigger(trigger_id: int):
    """DELETE: Remove a trigger."""
    deleted = delete_trigger(trigger_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return {"success": True}

@app.get("/api/v1/users", dependencies=[Depends(login_required)])
async def api_get_users(current_user: dict = Depends(get_current_user)):
    users = get_users(None)
    # Include all new fields in the response
    logger.info(f"Retrieved {len(users)} users from database")
    for user in users[:3]:  # Log first 3 users for debugging
        logger.info(f"User {user.get('id')}: telegram_id={user.get('telegram_id')}, telegram_username={user.get('telegram_username')}, telegram_first_name={user.get('telegram_first_name')}, telegram_last_name={user.get('telegram_last_name')}, mesh_node_id={user.get('mesh_node_id')}")
    return users

@app.put("/api/v1/users/{user_id}", dependencies=[Depends(login_required)])
async def api_update_user(user_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()

        # Validate node_id format if provided
        if 'node_id' in body and body['node_id'] and not str(body['node_id']).isdigit():
            raise HTTPException(400, "Node ID must contain only digits")

        # Validate mesh_node_id format if provided
        if 'mesh_node_id' in body and body['mesh_node_id'] and not str(body['mesh_node_id']).isdigit():
            raise HTTPException(400, "Mesh Node ID must contain only digits")

        updated = update_user(user_id, **body)
        if not updated:
            raise HTTPException(404, "User not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating user: {e}")
        raise HTTPException(500, "Internal server error")

@app.put("/api/v1/users/{user_id}/toggle_active", dependencies=[Depends(login_required)])
async def api_toggle_user_active(user_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    """Toggle user active status."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()
        is_active = body.get('is_active', 0)
        updated = update_user(user_id, is_active=is_active)
        if not updated:
            raise HTTPException(404, "User not found")
        return {"success": True}
    except Exception as e:
        print(f"Error toggling user active status: {e}")
        raise HTTPException(500, "Internal server error")

@app.delete("/api/v1/users/{user_id}", dependencies=[Depends(login_required)])
async def api_delete_user(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    if user_id == current_user['id']:
        raise HTTPException(400, "Cannot delete self")
    deleted = delete_user(user_id)
    if not deleted:
        raise HTTPException(404, "User not found")
    return {"success": True}

# Group API endpoints
@app.get("/api/v1/groups", dependencies=[Depends(login_required)])
async def api_get_groups():
    """GET: Retrieve list of all groups."""
    return get_groups()

@app.post("/api/v1/groups", dependencies=[Depends(login_required)])
async def api_create_group(request: Request, current_user: dict = Depends(get_current_user)):
    """POST: Create a new group."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()
        name = body.get('name')
        description = body.get('description', '')

        if not name or not name.strip():
            raise HTTPException(status_code=400, detail="Group name is required")

        group_id = create_group(name.strip(), description)
        if group_id:
            return {"id": group_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to create group")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error creating group: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/groups/{group_id}", dependencies=[Depends(login_required)])
async def api_get_group(group_id: int):
    """GET: Retrieve a single group."""
    group = get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group

@app.put("/api/v1/groups/{group_id}", dependencies=[Depends(login_required)])
async def api_update_group(group_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    """PUT: Update a group."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()
        name = body.get('name')
        description = body.get('description')

        if name is not None and not name.strip():
            raise HTTPException(status_code=400, detail="Group name cannot be empty")

        updated = update_group(group_id, name=name.strip() if name else None, description=description)
        if not updated:
            raise HTTPException(status_code=404, detail="Group not found")
        return {"success": True}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error updating group: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/v1/groups/{group_id}", dependencies=[Depends(login_required)])
async def api_delete_group(group_id: int, current_user: dict = Depends(get_current_user)):
    """DELETE: Remove a group."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    deleted = delete_group(group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"success": True}

# User-Group assignment endpoints
@app.get("/api/v1/users/{user_id}/groups", dependencies=[Depends(login_required)])
async def api_get_user_groups(user_id: int, current_user: dict = Depends(get_current_user)):
    """GET: Get groups for a user."""
    if current_user['role'] != 'admin' and current_user['id'] != user_id:
        raise HTTPException(403, "Access denied")
    return get_user_groups(user_id)

@app.post("/api/v1/users/{user_id}/groups/{group_id}", dependencies=[Depends(login_required)])
async def api_assign_user_to_group(user_id: int, group_id: int, current_user: dict = Depends(get_current_user)):
    """POST: Assign user to group."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    assigned = assign_user_to_group(user_id, group_id)
    if not assigned:
        raise HTTPException(status_code=400, detail="Assignment failed (user or group not found, or already assigned)")
    return {"success": True}

@app.delete("/api/v1/users/{user_id}/groups/{group_id}", dependencies=[Depends(login_required)])
async def api_remove_user_from_group(user_id: int, group_id: int, current_user: dict = Depends(get_current_user)):
    """DELETE: Remove user from group."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    removed = remove_user_from_group(user_id, group_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return {"success": True}

@app.get("/api/v1/groups/{group_id}/users", dependencies=[Depends(login_required)])
async def api_get_group_users(group_id: int):
    """GET: Get users in a group."""
    return get_group_users(group_id)

@app.get("/api/v1/users")
async def api_get_users():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role FROM users")
        rows = cursor.fetchall()
        keys = ['id', 'username', 'role']
        return [dict(zip(keys, row)) for row in rows]
    except sqlite3.Error as e:
        print(f"Database error in /api/v1/users: {e}")
        return []
    finally:
        conn.close()

@app.get("/api/v1/channels")
async def api_get_channels():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT channel FROM messages ORDER BY channel")
        rows = cursor.fetchall()
        channels = [row[0] for row in rows if row[0]]
        return channels
    except sqlite3.Error as e:
        print(f"Database error in /api/v1/channels: {e}")
        return []
    finally:
        conn.close()


@app.get("/api/v1/settings", dependencies=[Depends(login_required)])
async def api_get_settings(current_user: dict = Depends(get_current_user)):
    """GET: Retrieve all settings."""
    return get_all_settings()

@app.put("/api/v1/settings/{key}")
async def api_update_setting(key: str, request: Request, current_user: dict = Depends(get_current_user)):
    """PUT: Update a specific setting key."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()
        value = body.get('value')
        if value is None:
            raise HTTPException(400, "Value is required")
        
        # Basic validation: try to cast to int if key suggests numeric (e.g., port)
        if any(suffix in key.lower() for suffix in ['port', 'interval', 'limit', 'radius']):
            try:
                value = int(value)
            except ValueError:
                raise HTTPException(400, "Value must be an integer for this key")
        
        description = body.get('description', '')
        success = set_setting(key, str(value), description)
        if not success:
            raise HTTPException(404, "Setting not found or update failed")
        return {"success": True, "key": key, "value": value}
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")
    except Exception as e:
        logging.error(f"Error updating setting: {e}")
        raise HTTPException(500, "Internal server error")

@app.post("/export_config", dependencies=[Depends(login_required)])
async def export_config(request: Request, current_user: dict = Depends(get_current_user)):
    """Export settings to config.ini, admin only."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        settings = get_all_settings()
        config = configparser.ConfigParser()
        
        # Parse settings keys like 'section.key' and populate config
        for full_key, value in settings.items():
            if '.' in full_key:
                section, option = full_key.split('.', 1)
                if not config.has_section(section):
                    config.add_section(section)
                config.set(section, option, value)
            else:
                # Default section
                if not config.has_section('DEFAULT'):
                    config.add_section('DEFAULT')
                config.set('DEFAULT', full_key, value)
        
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.ini')
        with open(config_path, 'w') as f:
            config.write(f)
        
        return {"success": True, "message": "Config exported successfully"}
    except Exception as e:
        logging.error(f"Error exporting config: {e}")
        raise HTTPException(500, "Export failed")


# Alerts API endpoints
@app.get("/api/v1/alerts", dependencies=[Depends(login_required)])
async def api_get_alerts(status: str = Query(None), type_filter: str = Query(None), limit: int = Query(50, ge=1, le=100)):
    """GET: Retrieve alerts with optional filtering."""
    return get_alerts(limit, status, type_filter)

@app.get("/api/v1/alerts/{alert_id}", dependencies=[Depends(login_required)])
async def api_get_alert(alert_id: int):
    """GET: Retrieve a single alert."""
    alert = get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

@app.post("/api/v1/alerts", dependencies=[Depends(login_required)])
async def api_create_alert(request: Request, current_user: dict = Depends(get_current_user)):
    """POST: Create a new alert."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()
        alert_type = body.get('type')
        message = body.get('message')
        severity = body.get('severity', 'info')
        node_id = body.get('node_id')
        user_id = body.get('user_id')

        if not alert_type or not message:
            raise HTTPException(status_code=400, detail="type and message are required")

        alert_id = create_alert(alert_type, message, severity, node_id, user_id)
        if alert_id:
            return {"id": alert_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to create alert")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error creating alert: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.put("/api/v1/alerts/{alert_id}/status", dependencies=[Depends(login_required)])
async def api_update_alert_status(alert_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    """PUT: Update alert status."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()
        status = body.get('status')

        if not status:
            raise HTTPException(status_code=400, detail="status is required")

        updated = update_alert_status(alert_id, status)
        if not updated:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"success": True}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error updating alert status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/v1/alerts/{alert_id}", dependencies=[Depends(login_required)])
async def api_delete_alert(alert_id: int, current_user: dict = Depends(get_current_user)):
    """DELETE: Remove an alert."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    deleted = delete_alert(alert_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"success": True}

# Alert Config API endpoints
@app.get("/api/v1/alert_configs", dependencies=[Depends(login_required)])
async def api_get_alert_configs():
    """GET: Retrieve all alert configurations."""
    return get_alert_configs()

@app.get("/api/v1/alert_configs/{config_id}", dependencies=[Depends(login_required)])
async def api_get_alert_config(config_id: int):
    """GET: Retrieve a single alert configuration."""
    config = get_alert_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Alert config not found")
    return config

@app.post("/api/v1/alert_configs", dependencies=[Depends(login_required)])
async def api_create_alert_config(request: Request, current_user: dict = Depends(get_current_user)):
    """POST: Create a new alert configuration."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()
        alert_type = body.get('type')
        condition = body.get('condition', {})

        if not alert_type:
            raise HTTPException(status_code=400, detail="type is required")

        config_id = create_alert_config(alert_type, condition, current_user['id'])
        if config_id:
            return {"id": config_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to create alert config")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error creating alert config: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.put("/api/v1/alert_configs/{config_id}", dependencies=[Depends(login_required)])
async def api_update_alert_config(config_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    """PUT: Update an alert configuration."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()
        alert_type = body.get('type')
        condition = body.get('condition')
        enabled = body.get('enabled')

        updated = update_alert_config(config_id, alert_type, condition, enabled)
        if not updated:
            raise HTTPException(status_code=404, detail="Alert config not found")
        return {"success": True}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error updating alert config: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/v1/alert_configs/{config_id}", dependencies=[Depends(login_required)])
async def api_delete_alert_config(config_id: int, current_user: dict = Depends(get_current_user)):
    """DELETE: Remove an alert configuration."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    deleted = delete_alert_config(config_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert config not found")
    return {"success": True}

# Processes API endpoints
@app.get("/api/v1/processes", dependencies=[Depends(login_required)])
async def api_get_processes():
    """GET: Retrieve all processes."""
    return get_processes()

@app.get("/api/v1/processes/{process_id}", dependencies=[Depends(login_required)])
async def api_get_process(process_id: int):
    """GET: Retrieve a single process."""
    process = get_process(process_id)
    if not process:
        raise HTTPException(status_code=404, detail="Process not found")
    return process

@app.post("/api/v1/processes", dependencies=[Depends(login_required)])
async def api_create_process(request: Request, current_user: dict = Depends(get_current_user)):
    """POST: Create a new process."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()
        name = body.get('name')
        command = body.get('command')
        schedule = body.get('schedule')

        if not name or not command or not schedule:
            raise HTTPException(status_code=400, detail="name, command, and schedule are required")

        process_id = create_process(name, command, schedule, current_user['id'])
        if process_id:
            return {"id": process_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to create process")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error creating process: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.put("/api/v1/processes/{process_id}", dependencies=[Depends(login_required)])
async def api_update_process(process_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    """PUT: Update a process."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()
        name = body.get('name')
        command = body.get('command')
        schedule = body.get('schedule')
        enabled = body.get('enabled')

        updated = update_process(process_id, name, command, schedule, enabled)
        if not updated:
            raise HTTPException(status_code=404, detail="Process not found")
        return {"success": True}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error updating process: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/v1/processes/{process_id}", dependencies=[Depends(login_required)])
async def api_delete_process(process_id: int, current_user: dict = Depends(get_current_user)):
    """DELETE: Remove a process."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    deleted = delete_process(process_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Process not found")
    return {"success": True}

# Zones API endpoints
@app.get("/api/v1/zones", dependencies=[Depends(login_required)])
async def api_get_zones():
    """GET: Retrieve all zones."""
    zones = get_zones()
    logging.info(f"GET /api/v1/zones returned {len(zones)} zones: {[z['id'] for z in zones]}")
    return zones

@app.get("/api/v1/zones/{zone_id}", dependencies=[Depends(login_required)])
async def api_get_zone(zone_id: int):
    """GET: Retrieve a single zone."""
    zone = get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone

@app.post("/api/v1/zones", dependencies=[Depends(login_required)])
async def api_create_zone(request: Request, current_user: dict = Depends(get_current_user)):
    """POST: Create a new zone."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()
        name = body.get('name')
        latitude = body.get('latitude')
        longitude = body.get('longitude')
        radius = body.get('radius', 100)
        description = body.get('description', '')
        active = body.get('active', 1)

        if not name or latitude is None or longitude is None:
            raise HTTPException(status_code=400, detail="name, latitude, and longitude are required")

        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise HTTPException(status_code=400, detail="Invalid coordinates")

        zone_id = create_zone(name, latitude, longitude, radius, description, active)
        if zone_id:
            return {"id": zone_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to create zone")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error creating zone: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.put("/api/v1/zones/{zone_id}", dependencies=[Depends(login_required)])
async def api_update_zone(zone_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    """PUT: Update a zone."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    try:
        body = await request.json()
        name = body.get('name')
        latitude = body.get('latitude')
        longitude = body.get('longitude')
        radius = body.get('radius')
        description = body.get('description')
        active = body.get('active')

        updated = update_zone(zone_id, name, latitude, longitude, radius, description, active)
        if not updated:
            raise HTTPException(status_code=404, detail="Zone not found")
        return {"success": True}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error updating zone: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/v1/zones/{zone_id}", dependencies=[Depends(login_required)])
async def api_delete_zone(zone_id: int, current_user: dict = Depends(get_current_user)):
    """DELETE: Remove a zone."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")
    deleted = delete_zone(zone_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Zone not found")
    return {"success": True}

# Bot API endpoints
@app.get("/api/v1/bot/status", dependencies=[Depends(login_required)])
async def api_get_bot_status():
    """Get bot status information."""
    return {
        "status": get_bot_status(),
        "uptime": get_bot_uptime(),
        "last_activity": get_bot_last_activity(),
        "version": "1.0.0"
    }

@app.get("/api/v1/bot/settings", dependencies=[Depends(login_required)])
async def api_get_bot_settings():
    """Get bot settings."""
    return get_bot_settings()

@app.put("/api/v1/bot/settings", dependencies=[Depends(login_required)])
async def api_update_bot_settings(request: Request, current_user: dict = Depends(get_current_user)):
    """Update bot settings."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")

    try:
        body = await request.json()
        llm_model = body.get('llm_model')
        enabled_tools = body.get('enabled_tools', [])

        if not llm_model:
            raise HTTPException(status_code=400, detail="llm_model is required")

        set_bot_settings(llm_model, enabled_tools)
        return {"success": True}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error updating bot settings: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/bot/analytics", dependencies=[Depends(login_required)])
async def api_get_bot_analytics():
    """Get bot analytics data."""
    return {
        "command_usage": get_command_usage_stats(),
        "response_times": get_response_time_stats(),
        "error_stats": get_error_stats()
    }

@app.post("/api/v1/bot/commands", dependencies=[Depends(login_required)])
async def api_execute_bot_command(request: Request, current_user: dict = Depends(get_current_user)):
    """Execute a bot command."""
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")

    try:
        body = await request.json()
        command = body.get('command')

        if not command:
            raise HTTPException(status_code=400, detail="command is required")

        # Map commands to actual bot commands
        command_mapping = {
            'restart': 'restart_bot',
            'clear_cache': 'clear_cache',
            'reload_config': 'reload_config',
            'update_modules': 'update_modules'
        }

        bot_command = command_mapping.get(command)
        if not bot_command:
            raise HTTPException(status_code=400, detail="Unknown command")

        # Insert command into queue
        cmd_id = insert_command(bot_command, {}, current_user['id'])

        return {"success": True, "command_id": cmd_id, "message": f"Command '{command}' queued for execution"}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        print(f"Error executing bot command: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Load config for commands whitelist
config = configparser.ConfigParser()
config.read('config.ini')
allowed_types = config.get('commands', 'allowed_types', fallback='').split(',')


@app.post("/api/v1/commands", dependencies=[Depends(login_required)])
async def api_post_command(request: Request, current_user: dict = Depends(get_current_user)):
    """Endpoint to insert a new command into the queue."""
    sender_user_id = current_user['id']
    if current_user['role'] != 'admin':
        raise HTTPException(403, "Admin role required")

    try:
        body = await request.json()
        command_type = body.get('command_type')
        parameters = body.get('parameters', {})

        if not command_type:
            raise HTTPException(status_code=400, detail="command_type is required")

        # Validate command_type in whitelist
        if command_type not in [t.strip() for t in allowed_types]:
            raise HTTPException(status_code=403, detail="Command type not allowed")

        # Validate parameters: dict, JSON size <1KB, no code (basic check)
        if not isinstance(parameters, dict):
            raise HTTPException(status_code=400, detail="parameters must be a dict")
        params_json = json.dumps(parameters)
        if len(params_json) > 1024:
            raise HTTPException(status_code=400, detail="Parameters too large (>1KB)")
        if 'code' in parameters or 'exec' in parameters:  # Basic security check
            raise HTTPException(status_code=400, detail="Invalid parameters")

        # Assume user is admin for now; in real impl, check user.role == 'admin'
        # if get_current_user(request).role != 'admin':
        #     raise HTTPException(status_code=403, detail="Admin role required")

        cmd_id = insert_command(command_type, parameters, sender_user_id)

        logging.info(f"Command inserted: ID={cmd_id}, type={command_type}, user={sender_user_id}")

        return {"id": cmd_id, "status": "pending"}

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error inserting command: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/v1/messages/send", dependencies=[Depends(login_required)])
async def api_send_message(request: Request, current_user: dict = Depends(get_current_user)):
    """Endpoint to send a message via the command queue."""
    sender_user_id = current_user['id']

    try:
        body = await request.json()
        mode = body.get('mode', '').strip()  # 'channel' or 'dm'
        recipient = body.get('recipient', '').strip()  # prefixed recipient like "channel:0" or "node:123"
        message = body.get('message', '').strip()

        if not mode or mode not in ['channel', 'dm']:
            raise HTTPException(status_code=400, detail="Mode must be 'channel' or 'dm'")
        if not recipient:
            raise HTTPException(status_code=400, detail="Recipient is required")
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        if len(message) > 500:
            raise HTTPException(status_code=400, detail="Message must be 500 characters or less")

        # Parse recipient
        parts = recipient.split(':')
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Invalid recipient format")
        type_ = parts[0]
        value = parts[1]

        # Basic sanitization: remove potential HTML/JS (simple check)
        if '<script' in message.lower() or 'javascript:' in message.lower():
            raise HTTPException(status_code=400, detail="Invalid message content")

        # TODO: Implement rate-limiting (e.g., using slowapi or similar) to prevent spam

        # Validate command_type in whitelist (assuming 'send_message' is allowed as per config.ini)
        if 'send_message' not in [t.strip() for t in allowed_types]:
            raise HTTPException(status_code=403, detail="Command type not allowed")

        if type_ == 'channel':
            # For channel: target=0 (broadcast), channel=value
            parameters = {'target': '0', 'message': message, 'channel': value}
        else:  # node or user, treat as dm
            # For DM: target=value (node_id), channel=0
            parameters = {'target': value, 'message': message, 'channel': '0'}

        cmd_id = insert_command('send_message', parameters, sender_user_id)

        logging.info(f"Message command inserted: ID={cmd_id}, mode={mode}, type={type_}, value={value}, user={sender_user_id}, node_id={current_user.get('node_id')}")

        return {"success": True, "command_id": cmd_id}

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/v1/traceroute")
async def api_initiate_traceroute(request: Request):
    """Endpoint to initiate a traceroute to a destination node."""
    try:
        body = await request.json()
        dest_node_id = body.get('dest_node_id', '').strip()

        if not dest_node_id:
            raise HTTPException(status_code=400, detail="dest_node_id is required")

        # Validate that destination node exists
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT node_id FROM nodes WHERE node_id = ?", (dest_node_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Destination node not found")

        # Insert new route trace record
        cursor.execute("""
            INSERT INTO route_traces (source_node_id, dest_node_id, status)
            VALUES (?, ?, 'pending')
        """, ('1127918448', dest_node_id))

        trace_id = cursor.lastrowid

        conn.commit()

        # Queue traceroute command
        parameters = {'dest_node_id': dest_node_id, 'trace_id': trace_id}
        cmd_id = insert_command('traceroute', parameters, 1)

        logging.info(f"Traceroute initiated: trace_id={trace_id}, dest_node_id={dest_node_id}")

        return {"success": True, "trace_id": trace_id, "command_id": cmd_id}

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error initiating traceroute: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()

@app.get("/api/v1/traceroute/{trace_id}")
async def api_get_traceroute_status(trace_id: int):
    """Endpoint to get traceroute status and results."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, source_node_id, dest_node_id, timestamp, hops, status, response_time, error_message
            FROM route_traces
            WHERE id = ?
        """, (trace_id,))

        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Traceroute not found")

        trace_data = {
            'id': row[0],
            'source_node_id': row[1],
            'dest_node_id': row[2],
            'timestamp': row[3],
            'hops': row[4],
            'status': row[5],
            'response_time': row[6],
            'error_message': row[7]
        }

        # Parse hops if it's a JSON string
        if trace_data['hops'] and isinstance(trace_data['hops'], str):
            try:
                trace_data['hops'] = json.loads(trace_data['hops'])
            except json.JSONDecodeError:
                trace_data['hops'] = []

        return trace_data

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting traceroute status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()

# FiMesh API endpoints
@app.get("/api/v1/fimesh/transfers")
async def api_get_fimesh_transfers(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    """GET: Retrieve list of FiMesh transfers with pagination."""
    try:
        transfers = get_fimesh_transfers(limit, offset)
        return transfers
    except Exception as e:
        logging.error(f"Error getting FiMesh transfers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/v1/fimesh/upload")
async def api_upload_fimesh_file(file: UploadFile = File(...), node_id: str = Form(...)):
    """POST: Upload a file for FiMesh transfer."""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        if not node_id:
            raise HTTPException(status_code=400, detail="node_id is required")

        # Validate node_id format (should be numeric)
        if not node_id.isdigit():
            raise HTTPException(status_code=400, detail="node_id must be numeric")

        # Validate file size (max 1MB for FiMesh)
        file_content = await file.read()
        if len(file_content) > 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 1MB)")

        # Validate file type (basic check)
        allowed_extensions = ['.txt', '.jpg', '.png', '.pdf', '.zip']
        if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
            raise HTTPException(status_code=400, detail="Unsupported file type")

        # Create filename with node_id suffix
        name_parts = file.filename.rsplit('.', 1)
        if len(name_parts) == 2:
            new_filename = f"{name_parts[0]}___{node_id}.{name_parts[1]}"
        else:
            new_filename = f"{file.filename}___{node_id}"

        # Ensure fimesh/out directory exists
        os.makedirs('fimesh/out', exist_ok=True)

        # Save file to fimesh/out/
        file_path = os.path.join('fimesh/out', new_filename)
        with open(file_path, 'wb') as f:
            f.write(file_content)

        # Create transfer record in database
        transfer_id = create_fimesh_transfer({
            'session_id': f"upload_{int(time.time())}_{node_id}",
            'file_name': new_filename,
            'file_size': len(file_content),
            'from_node_id': 'web',  # Web upload
            'to_node_id': node_id,
            'status': 'pending',
            'start_time': datetime.now().isoformat()
        })

        return {"success": True, "filename": new_filename, "file_path": file_path, "size": len(file_content), "transfer_id": transfer_id}

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error uploading FiMesh file: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/v1/fimesh/transfers/{session_id}/cancel")
async def api_cancel_fimesh_transfer(session_id: str):
    """POST: Cancel a FiMesh transfer by session_id."""
    try:
        # Update transfer status to cancelled
        success = update_fimesh_transfer_status(session_id, 'cancelled')
        if not success:
            raise HTTPException(status_code=404, detail="Transfer not found")

        # Broadcast WebSocket update
        try:
            from .main import broadcast_map_update
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(broadcast_map_update("fimesh_update", {
                    "session_id": session_id,
                    "status": "cancelled",
                    "timestamp": datetime.now().isoformat()
                }))
            except RuntimeError:
                # No running event loop, skip broadcasting
                logger.debug("No running event loop, skipping WebSocket broadcast for FiMesh cancel")
        except ImportError:
            logger.debug("WebSocket broadcasting not available for FiMesh cancel")

        return {"success": True, "message": f"Transfer {session_id} cancelled"}

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error cancelling FiMesh transfer: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    # Запуск сервера для локальной разработки
    # Для продакшена используйте Gunicorn или другой ASGI-сервер
    uvicorn.run(app, host="0.0.0.0", port=8000)