import os
import time
import logging
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
UPBIT_NOTICE_URL = "https://upbit.com/service_center/notice"
LAST_NOTICE_FILE = "last_notice.txt"


def init_driver():
    """
    Инициализирует и возвращает WebDriver для переиспользования
    """
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        logging.info("✅ Браузер Chrome запущен в оптимизированном режиме")
        return driver
        
    except Exception as e:
        logging.error(f"Ошибка инициализации браузера: {e}")
        return None


def parse_publish_time(time_str):
    """
    Парсит время публикации, указанное на сайте Upbit.

    Поддерживаемые форматы:
    - "2025.10.31 10:25"
    - "2025.10.31 10:25:43"
    - "2025-10-31 10:25"
    - "2025-10-31 10:25:43"
    - "2025.10.31"
    - "2025-10-31"
    - "10:25"
    - "10:25:43"
    """
    if not time_str:
        return None

    time_str = time_str.strip()
    if not time_str:
        return None

    full_formats = [
        "%Y.%m.%d %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]

    last_error = None
    for fmt in full_formats:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError as exc:
            last_error = exc

    date_only_formats = ["%Y.%m.%d", "%Y-%m-%d"]
    for fmt in date_only_formats:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError as exc:
            last_error = exc

    now = datetime.now()
    time_only_formats = ["%H:%M:%S", "%H:%M"]
    for fmt in time_only_formats:
        try:
            time_part = datetime.strptime(time_str, fmt)
            return datetime(
                now.year,
                now.month,
                now.day,
                time_part.hour,
                time_part.minute,
                time_part.second,
            )
        except ValueError as exc:
            last_error = exc

    if last_error:
        logging.warning(f"⚠️ Не удалось распарсить время: {time_str} ({last_error})")
    else:
        logging.warning(f"⚠️ Не удалось распарсить время: {time_str}")

    return None


def fetch_latest_notice(driver, is_first_load=False):
    """
    Получает последнюю новость с сайта Upbit используя существующий драйвер
    Пропускает закрепленные записи по маркеру «공지»
    
    Args:
        driver: Экземпляр WebDriver (уже запущенный)
        is_first_load: True при первой загрузке, False при обновлении
    """
    try:
        wait_timeout = 3

        if is_first_load:
            # Первая загрузка страницы
            logging.info("📡 Подключаемся к Upbit...")
            driver.get(UPBIT_NOTICE_URL)
            
            # Ждем загрузки элементов
            wait = WebDriverWait(driver, wait_timeout)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
            time.sleep(0.3)
        else:
            # Последующие проверки - обновляем страницу и ждем загрузки
            driver.refresh()
            
            # Ждем загрузки элементов после refresh
            try:
                wait = WebDriverWait(driver, wait_timeout)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
            except Exception as e:
                logging.warning(f"⚠️ Таймаут ожидания загрузки после refresh: {e}")
            
            # Дополнительная задержка для полной загрузки JavaScript
            time.sleep(0.2)
        
        # Получаем HTML страницы
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Находим ВСЕ ссылки на новости
        all_notice_links = soup.select('tr a[href*="/service_center/notice"]')
        
        if not all_notice_links:
            logging.warning("⚠️ Не удалось найти элементы новостей на странице")
            return None
        
        # Если первая загрузка - показываем статистику
        if is_first_load:
            total_notices = len(all_notice_links)
            logging.info(f"🔍 Найдено новостей на странице: {total_notices}")
        
        # Ищем первую НЕ закрепленную новость
        link_tag = None
        selected_tr = None
        pinned_count = 0
        for notice_link in all_notice_links:
            parent_tr = notice_link.find_parent('tr')

            if parent_tr:
                # Проверка 1: Маркер объявления "공지" (notice)
                notice_marker = parent_tr.select_one('span.css-1y508v5')
                is_notice = notice_marker and notice_marker.get_text(strip=True) == '공지'

                # Проверка 2: Иконка закрепления (pin)
                pin_marker = parent_tr.select_one('use[href="#N_pin_fill_24"]')
                is_pinned = pin_marker is not None

                # Если любой из маркеров найден - пропускаем
                if is_notice or is_pinned:
                    pinned_count += 1
                    continue

                # Нашли первую незакрепленную новость!
                link_tag = notice_link
                selected_tr = parent_tr
                break
        
        # Если первая загрузка и были закреплённые - сообщаем
        if is_first_load and pinned_count > 0:
            logging.info(f"⏭️ Пропущено закреплённых: {pinned_count}")
        
        if not link_tag:
            logging.warning("⚠️ Все новости закреплены, реальных новостей не найдено")
            return None
        
        # Извлекаем заголовок
        title_span = link_tag.select_one('span.css-qju2q6')
        if title_span:
            title = title_span.get_text(strip=True)
        else:
            title = link_tag.get_text(strip=True)
        
        # Извлекаем ссылку
        href = link_tag.get('href')
        
        if not href:
            logging.warning("Ссылка на новость не содержит атрибут href")
            return None
        
        # Формируем полную ссылку
        if href.startswith('http'):
            full_link = href
        else:
            full_link = f"https://upbit.com{href}" if href.startswith('/') else f"https://upbit.com/{href}"
        
        publish_time = None
        if selected_tr:
            time_selectors = [
                'td.css-1w62z3d',
                'td.css-1vopgf5',
                'td.css-1i0gn2z',
                'td:nth-of-type(3)',
                'span.css-1w62z3d',
            ]

            for selector in time_selectors:
                time_elem = selected_tr.select_one(selector)
                if not time_elem:
                    continue

                publish_time_str = time_elem.get_text(strip=True)
                if not publish_time_str:
                    continue

                parsed_time = parse_publish_time(publish_time_str)
                if parsed_time:
                    publish_time = parsed_time
                    break

            if publish_time is None:
                time_cells = selected_tr.find_all('td')
                if time_cells:
                    candidate_text = time_cells[-1].get_text(strip=True)
                    if candidate_text and candidate_text != title:
                        publish_time = parse_publish_time(candidate_text)

        return {
            "title": title,
            "link": full_link,
            "publish_time": publish_time,
        }
        
    except Exception as e:
        logging.error(f"❌ Ошибка при получении новостей: {e}")
        return None


def read_last_notice():
    try:
        if os.path.exists(LAST_NOTICE_FILE):
            with open(LAST_NOTICE_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return content if content else None
        return None
    except Exception as e:
        logging.error(f"Ошибка чтения файла last_notice.txt: {e}")
        return None


def save_last_notice(link):
    try:
        with open(LAST_NOTICE_FILE, "w", encoding="utf-8") as f:
            f.write(link)
    except Exception as e:
        logging.error(f"Ошибка записи в файл last_notice.txt: {e}")


def is_new_notice(current_link):
    last_link = read_last_notice()
    
    if last_link is None:
        return False
    
    return current_link != last_link


def send_telegram_notification(title, link, publish_time=None):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_TOKEN или TELEGRAM_CHAT_ID не установлены в .env")
        return

    if publish_time and not isinstance(publish_time, datetime):
        logging.warning("⚠️ Время публикации передано в неподдерживаемом формате")
        publish_time = None

    send_time = datetime.now()
    effective_publish_time = publish_time
    delay_value = None

    if publish_time:
        delay_value = (send_time - effective_publish_time).total_seconds()

        if delay_value < 0:
            if abs(delay_value) > 12 * 3600:
                logging.warning("⚠️ Время публикации позже времени отправки. Корректируем на предыдущий день.")
                effective_publish_time = publish_time - timedelta(days=1)
                delay_value = (send_time - effective_publish_time).total_seconds()
            else:
                logging.warning("⚠️ Вычисленная задержка получилась отрицательной, берём абсолютное значение")
                delay_value = abs(delay_value)

        publish_str = effective_publish_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        delay_text = f"\n⚡ <b>Задержка:</b> {delay_value:.3f} сек"
    else:
        publish_str = "неизвестно"
        delay_text = ""

    send_str = send_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    logging.info(f"⏰ Время публикации: {publish_str}")
    logging.info(f"📤 Время отправки: {send_str}")
    if delay_value is not None:
        logging.info(f"⚡ Задержка: {delay_value:.3f} сек")

    api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    message = (
        "🔔 <b>Новое уведомление на Upbit!</b>\n\n"
        f"<b>Заголовок:</b> {title}\n"
        f"<b>Ссылка:</b> {link}\n\n"
        f"⏰ <b>Время публикации:</b> {publish_str}\n"
        f"📤 <b>Время отправки:</b> {send_str}{delay_text}"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(api_url, json=data, timeout=10)

        if response.status_code != 200:
            logging.error(f"❌ Ошибка отправки в Telegram: {response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Ошибка отправки в Telegram: {e}")


def main():
    logging.info("🚀 Upbit Notice Bot запущен")
    
    # Инициализируем браузер ОДИН РАЗ
    driver = init_driver()
    
    if not driver:
        logging.error("❌ Не удалось запустить браузер. Завершение работы.")
        return
    
    is_first_check = True
    check_count = 0
    
    try:
        while True:
            try:
                # Получаем последнюю новость (передаем существующий драйвер)
                notice = fetch_latest_notice(driver, is_first_load=is_first_check)
                
                if notice is None:
                    logging.warning("⚠️ Ошибка получения новости, повтор через 5 секунд...")
                    time.sleep(5)
                    continue
                
                # При первом запуске отправляем уведомление и сохраняем текущую новость
                if is_first_check:
                    logging.info(f"🔔 ПЕРВЫЙ ЗАПУСК - текущая новость: {notice['title']}")
                    logging.info(f"🔗 Ссылка: {notice['link']}")
                    save_last_notice(notice["link"])
                    send_telegram_notification(
                        notice["title"],
                        notice["link"],
                        notice.get("publish_time"),
                    )
                    logging.info("✅ Начинаем мониторинг. Ожидаем новых уведомлений...")
                    is_first_check = False
                # При последующих проверках - отправляем уведомление если новость изменилась
                elif is_new_notice(notice["link"]):
                    logging.info(f"🔔 НОВОЕ УВЕДОМЛЕНИЕ: {notice['title']}")
                    logging.info(f"🔗 Ссылка: {notice['link']}")
                    save_last_notice(notice["link"])
                    send_telegram_notification(
                        notice["title"],
                        notice["link"],
                        notice.get("publish_time"),
                    )
                    logging.info("👀 Продолжаем мониторинг...")
                
                # Увеличиваем счётчик проверок
                check_count += 1
                
                # Каждые 200 проверок делаем профилактическую паузу
                if check_count % 200 == 0:
                    pause = 1.0
                    logging.info(f"💤 Профилактическая пауза {pause:.1f} сек (защита от блокировок)")
                    time.sleep(pause)
                    check_count = 0
                
                # Фиксированный интервал проверки
                time.sleep(0.5)
                
            except Exception as e:
                logging.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(5)
                
    except KeyboardInterrupt:
        logging.info("⏹️ Получен сигнал остановки (Ctrl+C)")
    finally:
        # ВСЕГДА закрываем браузер при завершении
        if driver:
            driver.quit()
            logging.info("✅ Браузер закрыт. Бот остановлен.")


if __name__ == "__main__":
    main()
