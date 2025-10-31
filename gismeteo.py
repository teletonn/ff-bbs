import requests
import os

# Координаты Краснодара
LAT = 45.035470
LON = 38.975311

# URL и параметры для API Open-Meteo
# Запрашиваем только текущую погоду (current) и метрические единицы (градусы Цельсия, мм рт. ст.)
url = "https://api.open-meteo.com/v1/forecast"
params = {
    "latitude": LAT,
    "longitude": LON,
    "current": ["temperature_2m", "relative_humidity_2m", "pressure_msl", "weather_code", "wind_speed_10m"],
    "wind_speed_unit": "ms",
    "timezone": "Europe/Moscow"
}

# Словарь для перевода WMO кодов погоды в понятное описание с эмодзи
# (упрощенная версия из вашего примера)
weather_codes = {
    0: "Ясно ☀️",
    1: "В основном ясно 🌤️",
    2: "Переменная облачность 🌥️",
    3: "Пасмурно ☁️",
    45: "Туман 🌫️",
    48: "Изморозь 🌫️",
    51: "Легкая морось 💧",
    53: "Морось 💧",
    55: "Сильная морось 💧",
    61: "Легкий дождь 🌦️",
    63: "Дождь 🌧️",
    65: "Сильный дождь 🌧️",
    71: "Легкий снег 🌨️",
    73: "Снег ❄️",
    75: "Сильный снег ❄️",
    80: "Легкий ливень 🌦️",
    81: "Ливень 🌧️",
    82: "Сильный ливень ⛈️",
    95: "Гроза 🌩️",
    96: "Гроза с градом ⛈️🧊",
    99: "Сильная гроза с градом ⛈️🧊"
}

try:
    # 1. Отправляем запрос
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    # 2. Получаем данные
    data = response.json()
    current_weather = data['current']

    temperature = current_weather['temperature_2m']
    humidity = current_weather['relative_humidity_2m']
    pressure_hpa = current_weather['pressure_msl']
    wind_speed = current_weather['wind_speed_10m']
    
    # Конвертируем давление из гПа в мм рт. ст.
    pressure_mmhg = int(pressure_hpa * 0.75006)
    
    # Получаем код погоды и его описание из словаря
    code = current_weather['weather_code']
    description = weather_codes.get(code, "Неизвестно")

    # 3. Формируем итоговую строку
    weather_forecast = (
        f"Краснодар: 🌡️{temperature}°C 💧{humidity}% 💨{wind_speed:.1f}м/с 🌀{pressure_mmhg}мм. {description}"
    )

    # 4. Записываем в файл
    file_path = "/home/al/code/ff-bbs/alert.txt"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as file:
        file.write(weather_forecast)

    print(f"Прогноз погоды успешно записан в файл: {file_path}")
    print(f"Сообщение: {weather_forecast}")
    print(f"Длина сообщения: {len(weather_forecast)} символов")

except requests.exceptions.Timeout:
    print("Ошибка: сервер Open-Meteo не ответил за 10 секунд.")
except requests.exceptions.RequestException as e:
    print(f"Ошибка при запросе к API: {e}")
except (KeyError, IndexError):
    print("Не удалось разобрать ответ от API. Структура данных могла измениться.")
except Exception as e:
    print(f"Произошла непредвиденная ошибка: {e}")