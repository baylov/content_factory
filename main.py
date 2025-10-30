import os
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler()
    ]
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
UPBIT_NOTICE_URL = "https://upbit.com/service_center/notice"
LAST_NOTICE_FILE = "last_notice.txt"


def fetch_latest_notice():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(UPBIT_NOTICE_URL, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        first_notice = soup.select_one("ul.notice-list li a")
        if not first_notice:
            first_notice = soup.select_one("table.notice-table tbody tr a")
        if not first_notice:
            first_notice = soup.select_one("div.notice-item a")
        if not first_notice:
            first_notice = soup.select_one("a[href*='/service_center/notice']")
        
        if first_notice:
            title = first_notice.get_text().strip()
            href = first_notice.get("href")
            
            if href:
                if href.startswith("http"):
                    full_link = href
                elif href.startswith("/"):
                    full_link = "https://upbit.com" + href
                else:
                    full_link = "https://upbit.com/" + href
                
                return {"title": title, "link": full_link}
        
        logging.warning("Не удалось найти элементы новостей на странице")
        return None
        
    except requests.exceptions.Timeout:
        logging.error("Таймаут при запросе к Upbit")
        return None
    except requests.exceptions.ConnectionError:
        logging.error("Ошибка соединения с Upbit")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка HTTP запроса: {e}")
        return None
    except Exception as e:
        logging.error(f"Ошибка при парсинге страницы: {e}")
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
