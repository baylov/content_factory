import os
import time
import logging
from datetime import datetime
import re
from logging.handlers import RotatingFileHandler

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


class MetricsLogger:
    """
    Логгер для записи детальных метрик производительности обработки новостей
    """
    def __init__(self, log_file="logs/performance_metrics.log", max_bytes=10*1024*1024, backup_count=5):
        self.log_file = log_file
        self.logger = logging.getLogger("MetricsLogger")
        self.logger.setLevel(logging.INFO)
        
        # Создаем RotatingFileHandler для автоматической ротации логов
        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,  # 10MB по умолчанию
            backupCount=backup_count,  # Сохраняем 5 старых файлов
            encoding='utf-8'
        )
        
        # Формат без префикса уровня - чистый вывод
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        
        # Удаляем существующие handlers, если есть
        self.logger.handlers.clear()
        self.logger.addHandler(handler)
        self.logger.propagate = False  # Не передавать логи в root logger
    
    def log_article_metrics(self, notice_id, title, source, detected_at, processing_started, 
                           processing_completed, telegram_sent):
        """
        Логирует полные метрики обработки одной новости
        
        Args:
            notice_id: ID новости
            title: Заголовок новости
            source: Источник (например, "Upbit Notice")
            detected_at: datetime - момент обнаружения
            processing_started: datetime - начало обработки
            processing_completed: datetime - завершение обработки
            telegram_sent: datetime - отправка в Telegram
        """
        # Вычисляем метрики
        detection_lag = (processing_started - detected_at).total_seconds()
        processing_time = (processing_completed - processing_started).total_seconds()
        total_latency = (telegram_sent - detected_at).total_seconds()
        
        # Форматируем временные метки с миллисекундами
        detected_str = detected_at.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        started_str = processing_started.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        completed_str = processing_completed.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        sent_str = telegram_sent.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # Формируем сообщение по шаблону
        log_message = f"""
[{detected_at.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] ━━━ NEW ARTICLE ━━━
Source: {source}
ID: {notice_id} | Title: "{title}"
Detected at: {detected_str}
Processing started: {started_str} (lag: {detection_lag:.3f}s)
Processing completed: {completed_str} (duration: {processing_time:.3f}s)
Sent to Telegram: {sent_str}
⚡️ TOTAL LATENCY: {total_latency:.3f}s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        self.logger.info(log_message.strip())
    
    def log_error(self, notice_id, title, error_message):
        """
        Логирует ошибку обработки новости
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        log_message = f"""
[{timestamp}] ━━━ ERROR ━━━
ID: {notice_id} | Title: "{title}"
Error: {error_message}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        self.logger.error(log_message.strip())


# Создаем глобальный экземпляр MetricsLogger
metrics_logger = MetricsLogger()

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

    return {
        "title": title,
        "link": full_link,
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

            return { title, href };
        }
        return null;
        """

        result = driver.execute_script(js_code)

        if not result:
            logging.warning("[JS Polling] Не удалось получить новость")
            return None

        href = (result.get("href") or "").strip()
        title = (result.get("title") or "").strip()

        if not href:
            logging.warning("[JS Polling] Получена пустая ссылка на новость")
            return None

        if href.startswith("http"):
            full_link = href
        elif href.startswith("/"):
            full_link = f"https://upbit.com{href}"
        else:
            full_link = f"https://upbit.com/{href}"

        elapsed = time.time() - start_time
        if elapsed > 0.5:
            logging.warning(f"⚠️ Медленная JS проверка: {elapsed:.3f} сек")

        notice = {
            "title": title or full_link,
            "link": full_link,
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


def setup_mutation_observer(driver):
    """
    Устанавливает JavaScript MutationObserver для мгновенного обнаружения новых новостей
    """
    js_code = """
    if (window.noticeObserver) {
        window.noticeObserver.disconnect();
    }
    
    window.noticeChanged = false;
    
    const table = document.querySelector('table');
    if (!table) {
        console.error('[MutationObserver] Таблица не найдена!');
        return false;
    }
    
    window.noticeObserver = new MutationObserver(function(mutations) {
        if (!mutations || mutations.length === 0) {
            return;
        }
        window.noticeChanged = true;
    });
    
    window.noticeObserver.observe(table, {
        childList: true,
        subtree: true
    });
    
    console.log('[MutationObserver] Наблюдение установлено (по всей таблице)');
    return true;
    """
    
    try:
        result = driver.execute_script(js_code)
        if result:
            logging.info("✅ MutationObserver установлен")
        else:
            logging.error("❌ MutationObserver не установлен (таблица не найдена)")
        return bool(result)
    except Exception as e:
        logging.error(f"❌ Ошибка установки MutationObserver: {e}")
        return False


def check_for_changes(driver):
    """
    Проверяет был ли обнаружен MutationObserver изменения
    МГНОВЕННО (без refresh, без парсинга)
    """
    try:
        result = driver.execute_script("return window.noticeChanged;")
        
        if result:
            # Сбрасываем флаг
            driver.execute_script("window.noticeChanged = false;")
            return True
        
        return False
    except:
        return False


def fetch_latest_notice_instant(driver):
    """
    Получает данные новости после обнаружения изменений
    """
    js_code = """
    const links = document.querySelectorAll('tr a[href*="/service_center/notice"]');
    
    for (let link of links) {
        const tr = link.closest('tr');
        if (!tr) continue;
        
        const noticeMarker = tr.querySelector('span.css-1y508v5');
        const isNotice = noticeMarker && noticeMarker.textContent.trim() === '공지';
        
        const pinMarker = tr.querySelector('use[href="#N_pin_fill_24"]');
        const isPinned = pinMarker !== null;
        
        if (!isNotice && !isPinned) {
            const titleSpan = link.querySelector('span.css-qju2q6');
            const title = titleSpan ? titleSpan.textContent.trim() : link.textContent.trim();
            const href = link.getAttribute('href');
            
            return { title, href };
        }
    }
    return null;
    """
    
    try:
        result = driver.execute_script(js_code)
        
        if not result:
            logging.warning("[fetch_latest_notice_instant] JavaScript не вернул результат")
            return None
        
        href = result.get('href', '')
        full_link = f"https://upbit.com{href}" if href.startswith('/') else href
        
        return {
            "title": result['title'],
            "link": full_link,
        }
    except Exception as e:
        logging.error(f"❌ Ошибка получения новости: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return None


def get_all_notice_ids(driver):
    """
    Получает все ID новостей со страницы (включая закрепленные)
    Возвращает список ID: [5710, 5709, 5701, 5696, ...]
    """
    js_code = """
    const links = document.querySelectorAll('tr a[href*="/service_center/notice"]');
    const ids = [];
    
    links.forEach(link => {
        const href = link.getAttribute('href');
        const match = href.match(/id=(\\d+)/);
        if (match) {
            ids.push(parseInt(match[1]));
        }
    });
    
    return ids;
    """
    
    try:
        ids = driver.execute_script(js_code)
        if ids and len(ids) > 0:
            logging.info(f"[get_all_notice_ids] Найдено ID: {ids[:5]}... (всего {len(ids)})")
            return ids
        else:
            logging.warning("[get_all_notice_ids] ID не найдены")
            return []
    except Exception as e:
        logging.error(f"[get_all_notice_ids] Ошибка: {e}")
        return []


def get_notice_by_id(driver, notice_id):
    """
    Получает данные конкретной новости по её ID
    """
    js_code = f"""
    const links = document.querySelectorAll('tr a[href*="/service_center/notice"]');
    
    for (let link of links) {{
        const href = link.getAttribute('href');
        if (href.includes('id={notice_id}')) {{
            const tr = link.closest('tr');
            if (!tr) continue;
            
            const titleSpan = link.querySelector('span.css-qju2q6') || link.querySelector('span.css-twx20f');
            const title = titleSpan ? titleSpan.textContent.trim() : link.textContent.trim();
            
            return {{ title, href }};
        }}
    }}
    return null;
    """
    
    try:
        result = driver.execute_script(js_code)
        
        if not result:
            return None
        
        href = result['href']
        full_link = f"https://upbit.com{href}" if href.startswith('/') else href
        
        return {
            "id": notice_id,
            "title": result['title'],
            "link": full_link
        }
    except Exception as e:
        logging.error(f"[get_notice_by_id] Ошибка для ID {notice_id}: {e}")
        return None


def get_last_max_id():
    """
    Читает максимальный известный ID из файла
    Возвращает int или None
    """
    try:
        if os.path.exists(LAST_NOTICE_FILE):
            with open(LAST_NOTICE_FILE, "r") as f:
                content = f.read().strip()
                # Если в файле ссылка - извлекаем ID
                if "id=" in content:
                    match = re.search(r'id=(\d+)', content)
                    if match:
                        max_id = int(match.group(1))
                        logging.info(f"[get_last_max_id] Прочитан max_id из ссылки: {max_id}")
                        return max_id
                # Если просто число
                elif content.isdigit():
                    max_id = int(content)
                    logging.info(f"[get_last_max_id] Прочитан max_id: {max_id}")
                    return max_id
        
        logging.info("[get_last_max_id] Файл отсутствует или пустой")
        return None
    except Exception as e:
        logging.error(f"[get_last_max_id] Ошибка чтения: {e}")
        return None


def save_max_id(max_id):
    """
    Сохраняет максимальный ID в файл
    """
    try:
        with open(LAST_NOTICE_FILE, "w") as f:
            f.write(str(max_id))
        logging.info(f"[save_max_id] Сохранён max_id: {max_id}")
    except Exception as e:
        logging.error(f"[save_max_id] Ошибка записи: {e}")


def notify_about_new_ids(driver, new_ids, *, detection_start=None, pause_between=0.5):
    """
    Отправляет уведомления о новых новостях по их ID.
    Возвращает количество успешно обработанных новостей.
    """
    if not new_ids:
        return 0
    
    processed = 0
    sorted_ids = sorted(new_ids)
    
    for index, notice_id in enumerate(sorted_ids):
        # Время обнаружения
        detection_time = detection_start if detection_start is not None else datetime.now()
        
        # Начало обработки
        processing_start = datetime.now()
        
        # Получаем данные новости
        notice = get_notice_by_id(driver, notice_id)
        
        # Завершение обработки
        processing_completed = datetime.now()
        
        if not notice:
            logging.error(f"❌ Не удалось получить данные новости ID {notice_id}")
            metrics_logger.log_error(notice_id, "Unknown", "Failed to fetch notice data")
            continue
        
        logging.info(f"🔔 НОВАЯ НОВОСТЬ (ID {notice_id}): {notice['title']}")
        logging.info(f"🔗 Ссылка: {notice['link']}")
        
        # Отправляем в Telegram и получаем время отправки
        telegram_sent = send_telegram_notification(
            notice["title"],
            notice["link"],
            detection_time=detection_time,
            processing_completed_time=processing_completed
        )
        
        # Логируем метрики в отдельный файл
        try:
            metrics_logger.log_article_metrics(
                notice_id=notice_id,
                title=notice['title'],
                source="Upbit Notice",
                detected_at=detection_time,
                processing_started=processing_start,
                processing_completed=processing_completed,
                telegram_sent=telegram_sent
            )
        except Exception as e:
            logging.error(f"❌ Ошибка записи метрик: {e}")
        
        bot_latency = (telegram_sent - detection_time).total_seconds()
        
        logging.info(f"⏱️ Обнаружено: {detection_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        logging.info(f"📤 Отправлено: {telegram_sent.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        logging.info(f"⚡ Задержка бота: {bot_latency:.3f} сек")
        
        if bot_latency < 0.5:
            logging.info("✅ ОТЛИЧНО: Задержка < 0.5 сек")
        elif bot_latency < 1.0:
            logging.info("✅ ХОРОШО: Задержка < 1 сек")
        elif bot_latency < 2.0:
            logging.warning("⚠️ ПРИЕМЛЕМО: Задержка 1-2 сек")
        else:
            logging.error(f"❌ МЕДЛЕННО: Задержка {bot_latency:.3f} сек")
        
        processed += 1
        
        if pause_between and index < len(sorted_ids) - 1:
            time.sleep(pause_between)
    
    return processed


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


def send_telegram_notification(title, link, detection_time=None, processing_completed_time=None):
    """
    Отправляет уведомление в Telegram с точными метриками времени
    
    Args:
        title: Заголовок новости
        link: Ссылка на новость
        detection_time: datetime - время обнаружения новости
        processing_completed_time: datetime - время завершения обработки (опционально)
    
    Returns:
        datetime - время отправки в Telegram
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_TOKEN или TELEGRAM_CHAT_ID не установлены в .env")
        return datetime.now()
    
    # Момент отправки
    send_time = datetime.now()
    
    # Базовое сообщение
    message = f"""🔔 <b>Новое уведомление на Upbit!</b>

<b>Заголовок:</b> {title}
<b>Ссылка:</b> {link}"""
    
    # Добавляем футер с метриками (согласно требованию)
    if detection_time:
        bot_latency = (send_time - detection_time).total_seconds()
        
        # Форматируем времена
        detection_str = detection_time.strftime('%H:%M:%S')
        send_str = send_time.strftime('%H:%M:%S')
        
        # Футер с метриками
        message += f"""

─────────────────
⏱ Обнаружено: {detection_str}
📤 Отправлено: {send_str}
⚡️ Задержка: {bot_latency:.2f} сек"""
    else:
        # Если не передано время обнаружения
        send_str = send_time.strftime('%H:%M:%S')
        message += f"""

─────────────────
📤 Отправлено: {send_str}"""
    
    api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(api_url, json=data, timeout=10)
        
        if response.status_code == 200:
            logging.info("✅ Уведомление отправлено в Telegram")
        else:
            logging.error(f"❌ Ошибка отправки в Telegram: {response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Ошибка отправки в Telegram: {e}")
    
    return send_time


def main():
    logging.info("🚀 Upbit Notice Bot запущен")
    logging.info("📡 Режим: MutationObserver (мгновенное обнаружение)")
    logging.info("🔢 Логика: Отслеживание по максимальному ID")
    
    driver = init_driver()
    if not driver:
        logging.error("❌ Не удалось запустить браузер")
        return
    
    try:
        # Первая загрузка
        logging.info("📡 Подключаемся к Upbit...")
        driver.get(UPBIT_NOTICE_URL)
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
        time.sleep(0.5)
        
        # Получаем все ID со страницы
        all_ids = get_all_notice_ids(driver)
        
        if not all_ids:
            logging.error("❌ Не удалось получить ID новостей")
            return
        
        # Находим максимальный ID на странице
        page_max_id = max(all_ids)
        logging.info(f"🔢 Максимальный ID на странице: {page_max_id}")
        
        # Читаем последний известный max_id
        last_known_max_id = get_last_max_id()
        tracked_max_id = last_known_max_id if last_known_max_id is not None else page_max_id
        
        if last_known_max_id is None:
            # ПЕРВЫЙ ЗАПУСК - отправляем уведомление о текущей максимальной новости
            logging.info("🆕 ПЕРВЫЙ ЗАПУСК - инициализация")
            
            # Время обнаружения
            detection_start = datetime.now()
            
            # Начало обработки
            processing_start = datetime.now()
            
            notice = get_notice_by_id(driver, page_max_id)
            
            # Завершение обработки
            processing_completed = datetime.now()
            
            if not notice:
                logging.error(f"❌ Не удалось получить данные новости ID {page_max_id}")
                return
            
            logging.info(f"🔔 ПЕРВЫЙ ЗАПУСК - текущая новость (ID {page_max_id}): {notice['title']}")
            logging.info(f"🔗 Ссылка: {notice['link']}")
            
            telegram_sent = send_telegram_notification(
                notice["title"],
                notice["link"],
                detection_time=detection_start,
                processing_completed_time=processing_completed
            )
            
            # Логируем метрики
            try:
                metrics_logger.log_article_metrics(
                    notice_id=page_max_id,
                    title=notice['title'],
                    source="Upbit Notice",
                    detected_at=detection_start,
                    processing_started=processing_start,
                    processing_completed=processing_completed,
                    telegram_sent=telegram_sent
                )
            except Exception as e:
                logging.error(f"❌ Ошибка записи метрик: {e}")
            
            bot_latency = (telegram_sent - detection_start).total_seconds()
            
            logging.info(f"⏱️ Обнаружено: {detection_start.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
            logging.info(f"📤 Отправлено: {telegram_sent.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
            logging.info(f"⚡ Задержка бота: {bot_latency:.3f} сек")
            
            if bot_latency < 0.5:
                logging.info("✅ ОТЛИЧНО: Задержка < 0.5 сек")
            elif bot_latency < 1.0:
                logging.info("✅ ХОРОШО: Задержка < 1 сек")
            elif bot_latency < 2.0:
                logging.warning("⚠️ ПРИЕМЛЕМО: Задержка 1-2 сек")
            else:
                logging.error(f"❌ МЕДЛЕННО: Задержка {bot_latency:.3f} сек")
            
            save_max_id(page_max_id)
            tracked_max_id = page_max_id
            logging.info("✅ Начинаем мониторинг...")
        
        elif page_max_id > last_known_max_id:
            # ЕСТЬ НОВЫЕ НОВОСТИ - отправляем все, которых не было
            logging.info(f"🆕 ОБНАРУЖЕНЫ НОВЫЕ НОВОСТИ!")
            logging.info(f"📊 Последний известный ID: {last_known_max_id}")
            logging.info(f"📊 Максимальный ID сейчас: {page_max_id}")
            
            # Находим все новые ID
            new_ids = [nid for nid in all_ids if nid > last_known_max_id]
            new_ids.sort()  # От меньшего к большему
            
            logging.info(f"🔔 Новых новостей: {len(new_ids)} → ID: {new_ids}")
            
            # Отправляем уведомления для каждой новой новости
            notify_about_new_ids(driver, new_ids, pause_between=1.0)
            
            # Обновляем max_id
            save_max_id(page_max_id)
            logging.info("✅ Начинаем мониторинг...")
            tracked_max_id = page_max_id
        
        else:
            # НЕТ НОВЫХ НОВОСТЕЙ
            logging.info(f"📊 Последний известный ID: {last_known_max_id}")
            logging.info(f"📊 Максимальный ID сейчас: {page_max_id}")
            logging.info("✅ Новых новостей нет. Начинаем мониторинг...")
            tracked_max_id = max(page_max_id, last_known_max_id)
        
        # Устанавливаем MutationObserver
        if not setup_mutation_observer(driver):
            logging.error("❌ Не удалось установить MutationObserver")
            return
        
        # Цикл мониторинга
        check_count = 0
        refresh_interval = 3000
        current_max_id = tracked_max_id  # Текущий известный max_id
        
        while True:
            try:
                # Периодический refresh
                if check_count > 0 and check_count % refresh_interval == 0:
                    refresh_minutes = (refresh_interval * 0.1) / 60
                    logging.info(f"🔄 Плановый refresh (каждые {refresh_interval} проверок ≈ {refresh_minutes:.1f} мин)...")
                    driver.refresh()
                    wait = WebDriverWait(driver, 10)
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
                    time.sleep(0.3)
                    if not setup_mutation_observer(driver):
                        logging.error("❌ Не удалось переустановить MutationObserver после refresh")
                        continue
                    
                    refreshed_ids = get_all_notice_ids(driver)
                    if refreshed_ids:
                        all_ids = refreshed_ids
                        page_max_id = max(all_ids)
                        if page_max_id > current_max_id:
                            logging.info("🆕 Refresh: обнаружены новые ID!")
                            logging.info(f"📊 Было max_id: {current_max_id}")
                            logging.info(f"📊 Стало max_id: {page_max_id}")
                            new_ids = [nid for nid in all_ids if nid > current_max_id]
                            new_ids.sort()
                            logging.info(f"🔔 Новых новостей: {len(new_ids)} → ID: {new_ids}")
                            detection_start = datetime.now()
                            notify_about_new_ids(driver, new_ids, detection_start=detection_start, pause_between=0.5)
                            current_max_id = page_max_id
                            save_max_id(current_max_id)
                            logging.info("👀 Продолжаем мониторинг...")
                    else:
                        logging.warning("[refresh] Не удалось получить ID после обновления страницы")
                
                # Проверка через MutationObserver
                if check_for_changes(driver):
                    detection_start = datetime.now()
                    
                    # Получаем все ID
                    all_ids = get_all_notice_ids(driver)
                    
                    if all_ids:
                        page_max_id = max(all_ids)
                        
                        # Есть новые новости?
                        if page_max_id > current_max_id:
                            logging.info(f"🆕 MutationObserver: обнаружены новые ID!")
                            logging.info(f"📊 Было max_id: {current_max_id}")
                            logging.info(f"📊 Стало max_id: {page_max_id}")
                            
                            # Находим все новые ID
                            new_ids = [nid for nid in all_ids if nid > current_max_id]
                            new_ids.sort()
                            
                            logging.info(f"🔔 Новых новостей: {len(new_ids)} → ID: {new_ids}")
                            
                            # Отправляем уведомления
                            notify_about_new_ids(driver, new_ids, detection_start=detection_start, pause_between=0.5)
                            
                            # Обновляем текущий max_id
                            current_max_id = page_max_id
                            save_max_id(current_max_id)
                            
                            logging.info("👀 Продолжаем мониторинг...")
                
                check_count += 1
                time.sleep(0.1)
                
            except Exception as exc:
                error_type = type(exc).__name__
                logging.error(f"❌ Ошибка ({error_type}): {exc}")

                if 'session' in str(exc).lower():
                    logging.warning("⚠️ Переинициализация...")
                    try:
                        driver.quit()
                    except Exception:
                        pass

                    driver = init_driver()
                    if not driver:
                        break

                    # Полная переинициализация
                    try:
                        driver.get(UPBIT_NOTICE_URL)
                        wait = WebDriverWait(driver, 15)
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
                        time.sleep(0.3)
                        
                        # Получаем актуальный max_id
                        reloaded_ids = get_all_notice_ids(driver)
                        if reloaded_ids:
                            all_ids = reloaded_ids
                            page_max_id = max(all_ids)
                            if page_max_id > current_max_id:
                                logging.info("🆕 Переинициализация: обнаружены новые ID!")
                                logging.info(f"📊 Было max_id: {current_max_id}")
                                logging.info(f"📊 Стало max_id: {page_max_id}")
                                new_ids = [nid for nid in all_ids if nid > current_max_id]
                                new_ids.sort()
                                logging.info(f"🔔 Новых новостей: {len(new_ids)} → ID: {new_ids}")
                                detection_start = datetime.now()
                                notify_about_new_ids(driver, new_ids, detection_start=detection_start, pause_between=0.5)
                                current_max_id = page_max_id
                                save_max_id(current_max_id)
                                logging.info("👀 Продолжаем мониторинг...")
                            else:
                                current_max_id = max(current_max_id, page_max_id)
                        
                        if not setup_mutation_observer(driver):
                            logging.error("❌ Не удалось установить MutationObserver после переинициализации")
                            break
                        check_count = 0
                        logging.info("✅ Браузер переинициализирован")
                    except Exception as reinit_exc:
                        logging.error(f"❌ Не удалось переинициализировать: {reinit_exc}")
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
