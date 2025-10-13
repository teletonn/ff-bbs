import time
from pycoingecko import CoinGeckoAPI
import schedule

# --- НАСТРОЙКА ---
# Список ID монет для отслеживания (ID с сайта coingecko.com)
TOKENS = ['bitcoin', 'ethereum', 'sui', 'solana', 'aptos']
# Валюта для отображения цены и капитализации
CURRENCY = 'usd'
# Имя файла для сохранения результатов
FILE_NAME = 'alert.txt'
# Пауза между запросами к API в секундах, чтобы не превышать лимиты
API_DELAY_SECONDS = 5

# Инициализация клиента API
cg = CoinGeckoAPI()

def format_price(price):
    """Форматирует цену в зависимости от ее величины."""
    if price >= 1000:
        # Если цена больше 1000, выводим целым числом с разделителями
        return f"{price:,.0f}"
    else:
        # Иначе выводим с 4 знаками после запятой
        return f"{price:.2f}"

def fetch_and_save_data():
    """
    Получает данные по каждому токену, форматирует их и сохраняет одной строкой в файл.
    """
    print("Начинаю сбор данных по токенам...")
    results = []

    for token_id in TOKENS:
        try:
            print(f"Запрашиваю данные для {token_id.capitalize()}...")
            # Запрашиваем рыночные данные для ОДНОГО токена
            market_data = cg.get_coins_markets(vs_currency=CURRENCY, ids=token_id)
            
            if not market_data:
                print(f"Не удалось получить данные для {token_id}. Пропускаю.")
                continue

            # API возвращает список, даже для одного ID, берем первый элемент
            coin_data = market_data[0]
            
            ticker = coin_data['symbol'].upper()
            price = coin_data['current_price']
            market_cap = coin_data['market_cap']

            formatted_price = format_price(price)
            # Форматируем капитализацию с разделителями для читаемости
            formatted_mcap = f"{market_cap:,}"
            
            # Составляем строку для текущей монеты
            result_string = f"{ticker}: ${formatted_price} (MC: ${formatted_mcap})"
            results.append(result_string)

            print(f"Данные для {ticker} получены. Пауза {API_DELAY_SECONDS} секунд...")
            # Делаем паузу перед следующим запросом
            time.sleep(API_DELAY_SECONDS)

        except Exception as e:
            print(f"Произошла ошибка при обработке {token_id}: {e}")
            results.append(f"{token_id.upper()}: ОШИБКА")
            # Все равно ждем, чтобы не нарушать лимиты после сбоя
            time.sleep(API_DELAY_SECONDS)

    # Когда все данные собраны, объединяем их в одну строку
    final_output_string = ", ".join(results)
    
    print("Сбор данных завершен. Запись в файл...")
    try:
        with open(FILE_NAME, 'w', encoding='utf-8') as f:
            f.write(final_output_string)
        print(f"Данные успешно сохранены в файл: {FILE_NAME}")
    except Exception as e:
        print(f"Не удалось записать данные в файл: {e}")

# --- ПЛАНИРОВЩИК ЗАДАЧ ---

# Выполняем функцию один раз при запуске, чтобы сразу получить результат
fetch_and_save_data()

# Планируем запуск функции каждый час
schedule.every().hour.do(fetch_and_save_data)

print(f"\nСкрипт запущен. Данные в файле '{FILE_NAME}'. Следующее обновление через час.")

# Бесконечный цикл для работы планировщика
while True:
    schedule.run_pending()
    time.sleep(1)