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


def fetch_latest_notice():
    """
    Получает последнюю новость с сайта Upbit используя Selenium
    """
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        logging.info("Открываем страницу Upbit...")
        driver.get(UPBIT_NOTICE_URL)
        
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
        
        time.sleep(2)
        
        page_source = driver.page_source
        
        soup = BeautifulSoup(page_source, 'html.parser')
        
        link_tag = soup.select_one('tr a[href*="/service_center/notice"]')
        
        if not link_tag:
            logging.warning("Не удалось найти элементы новостей на странице")
            return None
        
        title_span = link_tag.select_one('span.css-qju2q6')
        if title_span:
            title = title_span.get_text(strip=True)
        else:
            title = link_tag.get_text(strip=True)
        
        href = link_tag.get('href')
        
        if not href:
            logging.warning("Ссылка на новость не содержит атрибут href")
            return None
        
        if href.startswith('http'):
            full_link = href
        else:
            full_link = f"https://upbit.com{href}" if href.startswith('/') else f"https://upbit.com/{href}"
        
        logging.info(f"✅ Найдена новость: {title[:50]}...")
        
        return {
            "title": title,
            "link": full_link
        }
        
    except Exception as e:
        logging.error(f"Ошибка при получении новостей через Selenium: {e}")
        return None
    
    finally:
        if driver:
            driver.quit()


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
    
    first_run = read_last_notice() is None
    
    if first_run:
        notice = fetch_latest_notice()
        if notice:
            save_last_notice(notice["link"])
            logging.info(f"Первый запуск: сохранена текущая новость без отправки уведомления - {notice['title']}")
        time.sleep(2)
    
    try:
        while True:
            try:
                notice = fetch_latest_notice()
                
                if notice is None:
                    time.sleep(5)
                    continue
                
                if is_new_notice(notice["link"]):
                    save_last_notice(notice["link"])
                    send_telegram_notification(notice["title"], notice["link"])
                    logging.info(f"Обнаружена новая новость: {notice['title']}")
                
                time.sleep(random.uniform(1.0, 1.5))
                
            except requests.exceptions.RequestException as e:
                logging.error(f"Ошибка сети: {e}")
                time.sleep(5)
                
            except Exception as e:
                logging.error(f"Неожиданная ошибка: {e}")
                time.sleep(5)
                
    except KeyboardInterrupt:
        logging.info("⏹️ Бот остановлен")


if __name__ == "__main__":
    main()
