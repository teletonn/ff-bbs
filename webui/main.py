import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .database import init_db

# Инициализация базы данных при старте
try:
    init_db()
    print("База данных успешно инициализирована.")
except Exception as e:
    print(f"Ошибка при инициализации базы данных: {e}")


app = FastAPI(
    title="Firefly-BBS Web Dashboard",
    description="Веб-интерфейс для управления и мониторинга сети 'Светлячок'.",
    version="0.1.0"
)

# Подключение статических файлов (CSS, JS, изображения)
app.mount("/static", StaticFiles(directory="webui/static"), name="static")

# Подключение шаблонизатора Jinja2
templates = Jinja2Templates(directory="webui/templates")

# Список страниц для навигационного меню
# (название, путь)
menu_items = [
    ("Сводка", "/dashboard"),
    ("Сообщения", "/messages"),
    ("Ноды", "/nodes"),
    ("Пользователи", "/users"),
    ("Форум", "/forum"),
    ("Карта", "/map"),
    ("Зоны", "/geofences"),
    ("Триггеры", "/triggers"),
    ("Настройки", "/settings"),
]

def render_template(template_name: str, request: Request, **kwargs):
    """Хелпер для рендеринга шаблонов с добавлением общих данных."""
    context = {
        "request": request,
        "menu_items": menu_items,
        "page_title": kwargs.get("page_title", "Дашборд")
    }
    context.update(kwargs)
    return templates.TemplateResponse(template_name, context)

@app.get("/", response_class=RedirectResponse, include_in_schema=False)
async def root():
    """Перенаправляет с корневого URL на главную страницу дашборда."""
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Отображает главную страницу-сводку."""
    return render_template("dashboard.html", request, page_title="Сводка")

@app.get("/messages", response_class=HTMLResponse)
async def get_messages(request: Request):
    """Отображает страницу с сообщениями."""
    return render_template("messages.html", request, page_title="Сообщения")

@app.get("/nodes", response_class=HTMLResponse)
async def get_nodes(request: Request):
    """Отображает страницу со списком узлов сети."""
    return render_template("nodes.html", request, page_title="Ноды")

@app.get("/users", response_class=HTMLResponse)
async def get_users(request: Request):
    """Отображает страницу управления пользователями дашборда."""
    return render_template("users.html", request, page_title="Пользователи")

@app.get("/forum", response_class=HTMLResponse)
async def get_forum(request: Request):
    """Отображает форум."""
    return render_template("forum.html", request, page_title="Форум")

@app.get("/map", response_class=HTMLResponse)
async def get_map(request: Request):
    """Отображает карту сети."""
    return render_template("map.html", request, page_title="Карта")

@app.get("/geofences", response_class=HTMLResponse)
async def get_geofences(request: Request):
    """Отображает страницу управления гео-зонами."""
    return render_template("geofences.html", request, page_title="Зоны")

@app.get("/triggers", response_class=HTMLResponse)
async def get_triggers(request: Request):
    """Отображает страницу управления триггерами."""
    return render_template("triggers.html", request, page_title="Триггеры")

@app.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    """Отображает страницу настроек."""
    return render_template("settings.html", request, page_title="Настройки")

if __name__ == "__main__":
    # Запуск сервера для локальной разработки
    # Для продакшена используйте Gunicorn или другой ASGI-сервер
    uvicorn.run(app, host="0.0.0.0", port=8000)