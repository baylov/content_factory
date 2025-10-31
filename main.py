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
    Инициализирует Selenium WebDriver с настройками для скорости и стабильности.
    """
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        chrome_options.add_argument('--disable-dev-tools')
        chrome_options.add_argument('--disable-extensions')

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.set_page_load_timeout(30)
        driver.implicitly_wait(10)

        logging.info("✅ Браузер Chrome запущен в оптимизированном режиме")
        return driver

    except Exception as e:
        logging.error(f"❌ Ошибка инициализации браузера: {e}")
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


def extract_latest_notice_from_soup(soup, *, log_context="", log_stats=False):
    prefix = f"[{log_context}] " if log_context else ""

    all_notice_links = soup.select('tr a[href*="/service_center/notice"]')

    if not all_notice_links:
        logging.warning(f"{prefix}Не найдены элементы новостей на странице")
        return None

    if log_stats:
        logging.info(f"{prefix}🔍 Найдено новостей на странице: {len(all_notice_links)}")

    link_tag = None
    selected_tr = None
    pinned_count = 0

    for notice_link in all_notice_links:
        parent_tr = notice_link.find_parent('tr')

        if parent_tr:
            notice_marker = parent_tr.select_one('span.css-1y508v5')
            is_notice = notice_marker and notice_marker.get_text(strip=True) == '공지'

            pin_marker = parent_tr.select_one('use[href="#N_pin_fill_24"]')
            is_pinned = pin_marker is not None

            if is_notice or is_pinned:
                pinned_count += 1
                continue

            link_tag = notice_link
            selected_tr = parent_tr
            break

    if link_tag is None:
        if pinned_count:
            logging.warning(f"{prefix}Все найденные записи закреплены ({pinned_count})")
        else:
            logging.warning(f"{prefix}Все новости закреплены, реальные записи не найдены")
        return None

    if log_stats and pinned_count > 0:
        logging.info(f"{prefix}⏭️ Пропущено закреплённых: {pinned_count}")

    title_span = link_tag.select_one('span.css-qju2q6')
    title = title_span.get_text(strip=True) if title_span else link_tag.get_text(strip=True)

    href = link_tag.get('href')
    if not href:
        logging.warning(f"{prefix}Ссылка на новость не содержит атрибут href")
        return None

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


def fetch_latest_notice_fast():
    """
    Быстрая проверка через requests (без браузера).
    """
    try:
        start_time = time.time()

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8',
        }

        response = requests.get(UPBIT_NOTICE_URL, headers=headers, timeout=5)

        if response.status_code != 200:
            logging.warning(f"⚠️ Requests вернул статус {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        notice = extract_latest_notice_from_soup(soup, log_context="Requests")

        if notice is None:
            return None

        elapsed = time.time() - start_time
        notice["check_time"] = elapsed
        notice["source"] = "requests"

        if elapsed > 0.5:
            logging.warning(f"⚠️ Медленная проверка (requests): {elapsed:.3f} сек")

        return notice

    except requests.exceptions.Timeout:
        logging.warning("⚠️ Requests timeout")
        return None
    except requests.exceptions.RequestException as exc:
        logging.warning(f"⚠️ Requests ошибка: {exc}")
        return None
    except Exception as exc:
        logging.error(f"❌ Ошибка в fetch_latest_notice_fast: {exc}")
        return None


def fetch_latest_notice_selenium(driver, is_first_load=False):
    """
    Selenium версия (fallback для сложных случаев).
    """
    max_retries = 3
    retry_count = 0
    first_cycle = is_first_load

    while retry_count < max_retries:
        try:
            start_time = time.time()

            if first_cycle:
                logging.info("📡 Подключаемся к Upbit (Selenium)...")
                driver.get(UPBIT_NOTICE_URL)
                wait = WebDriverWait(driver, 15)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
                time.sleep(0.3)
                first_cycle = False
            else:
                driver.refresh()

                try:
                    wait = WebDriverWait(driver, 10)
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
                except Exception as exc:
                    logging.warning(f"⚠️ Selenium timeout: {exc}")
                    retry_count += 1
                    if retry_count < max_retries:
                        time.sleep(2)
                        continue
                    return None

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            notice = extract_latest_notice_from_soup(
                soup,
                log_context="Selenium",
                log_stats=is_first_load and retry_count == 0,
            )

            if notice is None:
                retry_count += 1
                if retry_count < max_retries:
                    logging.warning(f"⚠️ Не найдены новости, повтор {retry_count}/{max_retries}")
                    time.sleep(2)
                    continue
                return None

            elapsed = time.time() - start_time
            notice["check_time"] = elapsed
            notice["source"] = "selenium"

            if elapsed > 1.5:
                logging.warning(f"⚠️ Медленная проверка (Selenium): {elapsed:.3f} сек")

            return notice

        except Exception as exc:
            retry_count += 1
            error_type = type(exc).__name__
            logging.error(f"❌ Selenium ошибка (попытка {retry_count}/{max_retries}, {error_type}): {exc}")
            if retry_count < max_retries:
                time.sleep(3)
            else:
                return None

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
    delay_indicator = ""

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
        delay_indicator = "✅" if delay_value <= 1.0 else "⚠️"
        delay_text = f"\n⚡ <b>Задержка:</b> {delay_value:.3f} сек {delay_indicator}"
    else:
        publish_str = "неизвестно"
        delay_text = ""

    detection_str = send_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    logging.info(f"⏰ Время публикации: {publish_str}")
    logging.info(f"📤 Время обнаружения: {detection_str}")
    if delay_value is not None:
        if delay_value > 1.0:
            logging.warning(f"⚠️ ЗАДЕРЖКА ПРЕВЫШЕНА: {delay_value:.3f} сек (цель: < 1 сек)")
        else:
            logging.info(f"⚡ Задержка: {delay_value:.3f} сек ✅")

    api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    message = (
        "🔔 <b>Новое уведомление на Upbit!</b>\n\n"
        f"<b>Заголовок:</b> {title}\n"
        f"<b>Ссылка:</b> {link}\n\n"
        f"⏰ <b>Время публикации:</b> {publish_str}\n"
        f"📤 <b>Время обнаружения:</b> {detection_str}{delay_text}"
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
    logging.info("📡 Режим: быстрые проверки через requests")

    use_requests = True
    requests_fail_count = 0
    max_requests_fails = 5
    requests_retry_interval = 10
    last_requests_attempt = 0.0

    driver = None
    selenium_first_load = True

    is_first_check = True
    check_count = 0

    try:
        while True:
            try:
                notice = None
                now_monotonic = time.monotonic()

                should_try_requests = use_requests or (
                    not use_requests and (now_monotonic - last_requests_attempt) >= requests_retry_interval
                )

                if should_try_requests:
                    if not use_requests:
                        logging.info("♻️ Пробуем снова использовать requests...")
                    last_requests_attempt = now_monotonic
                    notice = fetch_latest_notice_fast()

                    if notice is None:
                        if use_requests:
                            requests_fail_count += 1
                            logging.warning(f"⚠️ Requests failed ({requests_fail_count}/{max_requests_fails})")

                            if requests_fail_count >= max_requests_fails:
                                logging.warning("⚠️ Слишком много ошибок requests, переключаемся на Selenium")
                                use_requests = False
                                requests_fail_count = 0

                                if driver is None:
                                    driver = init_driver()
                                    if driver:
                                        selenium_first_load = True
                                    else:
                                        logging.error("❌ Не удалось запустить Selenium")
                                        time.sleep(10)
                                        continue
                        else:
                            logging.warning("⚠️ Requests недоступен, используем Selenium")
                    else:
                        check_time = notice.get("check_time")
                        if check_time is not None:
                            logging.info(f"⏱️ Проверка (requests) заняла {check_time:.3f} сек")

                        if not use_requests:
                            logging.info("✅ Requests восстановлен, возвращаемся к быстрому режиму")

                        use_requests = True
                        requests_fail_count = 0

                if notice is None:
                    if driver is None:
                        driver = init_driver()
                        selenium_first_load = True
                        if not driver:
                            logging.error("❌ Не удалось запустить Selenium")
                            time.sleep(10)
                            continue

                    notice = fetch_latest_notice_selenium(driver, is_first_load=selenium_first_load)

                    if selenium_first_load:
                        selenium_first_load = False

                    if notice is None:
                        logging.warning("⚠️ Ошибка получения новости (Selenium), повтор через 5 секунд...")
                        time.sleep(5)
                        continue

                    check_time = notice.get("check_time")
                    if check_time is not None:
                        logging.info(f"⏱️ Проверка (Selenium) заняла {check_time:.3f} сек")

                if notice is None:
                    time.sleep(0.5)
                    continue

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

                check_count += 1
                if check_count % 200 == 0:
                    pause = 1.0
                    logging.info(f"💤 Профилактическая пауза {pause:.1f} сек (защита от блокировок)")
                    time.sleep(pause)
                    check_count = 0

                time.sleep(0.3)

            except Exception as exc:
                error_type = type(exc).__name__
                logging.error(f"❌ Ошибка в цикле мониторинга ({error_type}): {exc}")

                if driver and "session" in str(exc).lower():
                    logging.warning("⚠️ Потеря сессии Selenium, переинициализация...")
                    try:
                        driver.quit()
                    except Exception:
                        pass

                    driver = init_driver()
                    selenium_first_load = True

                    if driver:
                        logging.info("✅ Selenium переинициализирован")
                    else:
                        logging.error("❌ Не удалось переинициализировать Selenium")
                        use_requests = True
                        requests_fail_count = 0

                time.sleep(5)

    except KeyboardInterrupt:
        logging.info("⏹️ Получен сигнал остановки (Ctrl+C)")
    finally:
        if driver:
            driver.quit()
            logging.info("✅ Браузер закрыт. Бот остановлен.")


if __name__ == "__main__":
    main()
