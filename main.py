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
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--window-size=1920,1080')
        
        # Реалистичный User-Agent
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Убираем признаки автоматизации
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        logging.info("✅ Браузер Chrome запущен в оптимизированном режиме")
        return driver
        
    except Exception as e:
        logging.error(f"❌ Ошибка инициализации браузера: {e}")
        return None


def fetch_latest_notice(driver, is_first_load=False):
    """
    Получает последнюю новость с сайта Upbit используя существующий драйвер
    
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
            # Последующие проверки - просто обновляем страницу
            driver.refresh()
            time.sleep(random.uniform(0.5, 1.0))  # Короткая случайная задержка
        
        # Получаем HTML страницы
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Находим первую ссылку на новость
        link_tag = soup.select_one('tr a[href*="/service_center/notice"]')
        
        if not link_tag:
            logging.warning("⚠️ Не удалось найти элементы новостей на странице")
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
            logging.warning("⚠️ Ссылка на новость не содержит атрибут href")
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
        
        if response.status_code == 200:
            logging.info(f"Уведомление отправлено: {title}")
        else:
            logging.error(f"Ошибка отправки в Telegram: {response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при отправке в Telegram: {e}")


def main():
    logging.info("🚀 Upbit Notice Bot запущен")
    
    # Инициализируем браузер ОДИН РАЗ
    driver = init_driver()
    
    if not driver:
        logging.error("❌ Не удалось запустить браузер. Завершение работы.")
        return
    
    check_count = 0  # Счетчик проверок для случайных пауз
    
    try:
        # ПЕРВАЯ ПРОВЕРКА: сразу запоминаем текущую новость
        logging.info("🔍 Получаем текущую новость для начала мониторинга...")
        notice = fetch_latest_notice(driver, is_first_load=True)
        
        if notice:
            save_last_notice(notice["link"])
            logging.info(f"✅ Начинаем мониторинг с новости: {notice['title'][:50]}...")
            logging.info("👀 Ожидаем появления новых уведомлений...")
        else:
            logging.error("❌ Не удалось получить начальную новость. Завершение.")
            return
        
        # ОСНОВНОЙ ЦИКЛ МОНИТОРИНГА
        while True:
            try:
                check_count += 1
                
                # Каждые 50-100 проверок делаем дополнительную паузу (имитация реального поведения)
                if check_count % random.randint(50, 100) == 0:
                    pause = random.uniform(3, 7)
                    logging.info(f"💤 Профилактическая пауза {pause:.1f} сек (защита от блокировок)")
                    time.sleep(pause)
                
                # Получаем последнюю новость
                notice = fetch_latest_notice(driver, is_first_load=False)
                
                if notice is None:
                    logging.warning("⚠️ Ошибка получения новости, повтор через 5 секунд...")
                    time.sleep(5)
                    continue
                
                # Проверяем, новая ли новость
                if is_new_notice(notice["link"]):
                    # НОВАЯ НОВОСТЬ ОБНАРУЖЕНА!
                    save_last_notice(notice["link"])
                    
                    # Отправляем уведомление в Telegram
                    send_telegram_notification(notice["title"], notice["link"])
                    logging.info(f"🔔 НОВОЕ УВЕДОМЛЕНИЕ: {notice['title']}")
                    logging.info(f"🔗 Ссылка: {notice['link']}")
                    logging.info("👀 Продолжаем мониторинг...")
                
                # Случайная задержка между проверками (0.8-1.5 секунды)
                delay = random.uniform(0.8, 1.5)
                time.sleep(delay)
                
            except Exception as e:
                logging.error(f"❌ Ошибка в цикле мониторинга: {e}")
                time.sleep(5)
                
    except KeyboardInterrupt:
        logging.info("\n⏹️ Получен сигнал остановки (Ctrl+C)")
    finally:
        # ВСЕГДА закрываем браузер при завершении
        if driver:
            try:
                driver.quit()
                logging.info("✅ Браузер закрыт. Бот остановлен.")
            except:
                pass


if __name__ == "__main__":
    main()
