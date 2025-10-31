import os
import time
import random
import logging
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


def fetch_latest_notice(driver, is_first_load=False):
    """
    Получает последнюю новость с сайта Upbit используя существующий драйвер
    Пропускает закрепленные записи по маркеру «공지»
    
    Args:
        driver: Экземпляр WebDriver (уже запущенный)
        is_first_load: True при первой загрузке, False при обновлении
    """
    try:
        if is_first_load:
            # Первая загрузка страницы
            logging.info("📡 Подключаемся к Upbit...")
            driver.get(UPBIT_NOTICE_URL)
            
            # Ждем загрузки элементов
            wait = WebDriverWait(driver, 10)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
            time.sleep(random.uniform(1.5, 2.5))  # Случайная задержка при первой загрузке
        else:
            # Последующие проверки - обновляем страницу и ждем загрузки
            driver.refresh()
            
            # Ждем загрузки элементов после refresh
            try:
                wait = WebDriverWait(driver, 10)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
            except Exception as e:
                logging.warning(f"⚠️ Таймаут ожидания загрузки после refresh: {e}")
            
            # Дополнительная задержка для полной загрузки JavaScript
            time.sleep(random.uniform(1.5, 2.0))
        
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
                else:
                    # Нашли первую незакрепленную новость!
                    link_tag = notice_link
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
        
        return {
            "title": title,
            "link": full_link
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


def send_telegram_notification(title, link):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_TOKEN или TELEGRAM_CHAT_ID не установлены в .env")
        return
    
    api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    message = f"🔔 Новое уведомление на Upbit!\n\n<b>Заголовок:</b> {title}\n<b>Ссылка:</b> {link}"
    
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
                    send_telegram_notification(notice["title"], notice["link"])
                    logging.info("📤 Уведомление отправлено в Telegram")
                    logging.info("✅ Начинаем мониторинг. Ожидаем новых уведомлений...")
                    is_first_check = False
                # При последующих проверках - отправляем уведомление если новость изменилась
                elif is_new_notice(notice["link"]):
                    logging.info(f"🔔 НОВОЕ УВЕДОМЛЕНИЕ: {notice['title']}")
                    logging.info(f"🔗 Ссылка: {notice['link']}")
                    save_last_notice(notice["link"])
                    send_telegram_notification(notice["title"], notice["link"])
                    logging.info("📤 Уведомление отправлено в Telegram")
                    logging.info("👀 Продолжаем мониторинг...")
                
                # Увеличиваем счётчик проверок
                check_count += 1
                
                # Каждые 50-100 проверок делаем дополнительную паузу
                if check_count % random.randint(50, 100) == 0:
                    pause = random.uniform(3, 7)
                    logging.info(f"💤 Профилактическая пауза {pause:.1f} сек (защита от блокировок)")
                    time.sleep(pause)
                    check_count = 0
                
                # Случайная задержка 1.0-1.5 секунд
                time.sleep(random.uniform(1.0, 1.5))
                
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
