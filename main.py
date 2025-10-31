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


def fetch_notice_from_page_source(driver, *, log_context="Selenium", log_stats=False):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    return extract_latest_notice_from_soup(
        soup,
        log_context=log_context,
        log_stats=log_stats,
    )


def fetch_latest_notice_js_polling(driver, is_first_load=False):
    """
    Быстрая проверка через JavaScript polling (без полного refresh).
    """
    try:
        start_time = time.time()

        if is_first_load:
            logging.info("📡 Подключаемся к Upbit (Selenium)...")
            driver.get(UPBIT_NOTICE_URL)
            wait = WebDriverWait(driver, 15)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
            time.sleep(0.3)

            notice = fetch_notice_from_page_source(driver, log_stats=True)
            if notice is None:
                return None

            elapsed = time.time() - start_time
            notice["check_time"] = elapsed
            notice["source"] = "selenium-initial"
            return notice

        js_code = """
        const links = document.querySelectorAll('tr a[href*="/service_center/notice"]');
        for (const link of links) {
            const tr = link.closest('tr');
            if (!tr) {
                continue;
            }

            const noticeMarker = tr.querySelector('span.css-1y508v5');
            const isNotice = noticeMarker && noticeMarker.textContent.trim() === '공지';

            const pinMarker = tr.querySelector('use[href="#N_pin_fill_24"]');
            const isPinned = pinMarker !== null;

            if (isNotice || isPinned) {
                continue;
            }

            const titleSpan = link.querySelector('span.css-qju2q6');
            const title = titleSpan ? titleSpan.textContent.trim() : link.textContent.trim();

            const href = link.getAttribute('href') || '';

            const timeCell = tr.querySelector('td.css-1w62z3d, td.css-1vopgf5, td.css-1i0gn2z, td:nth-of-type(3), span.css-1w62z3d');
            const publishTime = timeCell ? timeCell.textContent.trim() : null;

            return { title, href, publishTime };
        }
        return null;
        """

        result = driver.execute_script(js_code)

        if not result:
            logging.warning("[JS Polling] Не удалось получить новость")
            return None

        href = (result.get("href") or "").strip()
        title = (result.get("title") or "").strip()
        publish_time_raw = (result.get("publishTime") or "").strip()

        if not href:
            logging.warning("[JS Polling] Получена пустая ссылка на новость")
            return None

        if href.startswith("http"):
            full_link = href
        elif href.startswith("/"):
            full_link = f"https://upbit.com{href}"
        else:
            full_link = f"https://upbit.com/{href}"

        publish_time = parse_publish_time(publish_time_raw) if publish_time_raw else None

        elapsed = time.time() - start_time
        if elapsed > 0.5:
            logging.warning(f"⚠️ Медленная JS проверка: {elapsed:.3f} сек")

        notice = {
            "title": title or full_link,
            "link": full_link,
            "publish_time": publish_time,
            "check_time": elapsed,
            "source": "selenium-js",
        }

        return notice

    except Exception as exc:
        logging.error(f"❌ Ошибка JS polling: {exc}")
        return None


def fetch_latest_notice_smart_refresh(driver, *, is_first_load=False, force_refresh=False):
    """
    Умная проверка:
    - Полный refresh при первой загрузке или когда запрошен.
    - Между ними — быстрая проверка через JavaScript.
    """
    try:
        if is_first_load:
            return fetch_latest_notice_js_polling(driver, is_first_load=True)

        if force_refresh:
            start_time = time.time()
            driver.refresh()
            wait = WebDriverWait(driver, 10)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
            time.sleep(0.2)

            notice = fetch_notice_from_page_source(driver)
            if notice is None:
                return None

            elapsed = time.time() - start_time
            notice["check_time"] = elapsed
            notice["source"] = "selenium-refresh"
            return notice

        notice = fetch_latest_notice_js_polling(driver)

        if notice is not None:
            return notice

        logging.warning("[JS Polling] Не удалось получить новость. Пробуем полный refresh.")
        return fetch_latest_notice_smart_refresh(driver, is_first_load=False, force_refresh=True)

    except Exception as exc:
        logging.error(f"❌ Ошибка smart refresh: {exc}")
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
    logging.info("📡 Режим: Selenium с JavaScript polling")

    driver = init_driver()

    if not driver:
        logging.error("❌ Не удалось запустить браузер")
        return

    is_first_check = True
    check_count = 0
    refresh_interval = 10

    try:
        while True:
            try:
                force_refresh = (check_count % refresh_interval == 0) and not is_first_check

                if force_refresh:
                    logging.info("🔄 Плановый refresh страницы...")

                notice = fetch_latest_notice_smart_refresh(
                    driver,
                    is_first_load=is_first_check,
                    force_refresh=force_refresh
                )

                if notice is None:
                    logging.warning("⚠️ Ошибка получения новости")
                    time.sleep(2)
                    continue

                check_time = notice.get('check_time')
                if check_time is not None and (is_first_check or force_refresh):
                    logging.info(f"⏱️ Проверка заняла {check_time:.3f} сек")

                if is_first_check:
                    logging.info(f"🔔 ПЕРВЫЙ ЗАПУСК - текущая новость: {notice['title']}")
                    logging.info(f"🔗 Ссылка: {notice['link']}")

                    if notice.get('publish_time'):
                        pub_time_str = notice['publish_time'].strftime('%Y-%m-%d %H:%M:%S')
                        logging.info(f"⏰ Время публикации: {pub_time_str}")

                    save_last_notice(notice["link"])
                    send_telegram_notification(notice["title"], notice["link"], notice.get("publish_time"))
                    logging.info("✅ Начинаем мониторинг. Ожидаем новых уведомлений...")
                    is_first_check = False

                elif is_new_notice(notice["link"]):
                    logging.info(f"🔔 НОВОЕ УВЕДОМЛЕНИЕ: {notice['title']}")
                    logging.info(f"🔗 Ссылка: {notice['link']}")

                    save_last_notice(notice["link"])
                    send_telegram_notification(notice["title"], notice["link"], notice.get("publish_time"))

                    logging.info("👀 Продолжаем мониторинг...")

                check_count += 1

                time.sleep(0.3)

            except Exception as exc:
                error_type = type(exc).__name__
                logging.error(f"❌ Ошибка в цикле ({error_type}): {exc}")

                if 'session' in str(exc).lower():
                    logging.warning("⚠️ Потеря сессии, переинициализация...")
                    try:
                        driver.quit()
                    except Exception:
                        pass

                    driver = init_driver()
                    if driver:
                        logging.info("✅ Браузер переинициализирован")
                        is_first_check = True
                        check_count = 0
                    else:
                        logging.error("❌ Не удалось переинициализировать")
                        break

                time.sleep(5)

    except KeyboardInterrupt:
        logging.info("⏹️ Остановка (Ctrl+C)")
    finally:
        if driver:
            driver.quit()
            logging.info("✅ Браузер закрыт")


if __name__ == "__main__":
    main()
