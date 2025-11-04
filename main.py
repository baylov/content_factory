import os
import time
import logging
from datetime import datetime
import re
import random
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
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

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
    Инициализирует Selenium WebDriver с агрессивными настройками для максимальной скорости.
    Цель: загрузка страницы за 0.3-0.5 секунды вместо 2+ секунд.
    """
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')  # Новый headless режим
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--disable-dev-tools')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        
        # Агрессивная оптимизация скорости - блокировка всех ненужных ресурсов
        chrome_options.add_argument('--blink-settings=imagesEnabled=false')
        chrome_options.add_argument('--disable-remote-fonts')
        chrome_options.add_argument('--disable-background-networking')
        chrome_options.add_argument('--disable-default-apps')
        chrome_options.add_argument('--disable-sync')
        chrome_options.add_argument('--disable-translate')
        chrome_options.add_argument('--hide-scrollbars')
        chrome_options.add_argument('--mute-audio')
        chrome_options.add_argument('--disable-breakpad')
        chrome_options.add_argument('--disable-crash-reporter')
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_argument('--log-level=3')
        
        # Блокировка всех медиа и ненужных ресурсов через prefs
        prefs = {
            'profile.managed_default_content_settings.images': 2,
            'profile.managed_default_content_settings.stylesheets': 2,  # Блокировать CSS
            'profile.default_content_setting_values': {
                'images': 2,          # Блокировать изображения
                'plugins': 2,         # Блокировать плагины
                'popups': 2,          # Блокировать всплывающие окна
                'media_stream': 2,    # Блокировать медиа-стримы
                'stylesheets': 2,     # Блокировать стили (может повлиять на структуру!)
            }
        }
        chrome_options.add_experimental_option('prefs', prefs)
        
        # КРИТИЧЕСКИ ВАЖНО: используем 'eager' вместо 'normal'
        # 'eager' не ждет загрузки всех ресурсов, только DOM
        chrome_options.page_load_strategy = 'eager'
        
        # Отключить обнаружение автоматизации
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Применяем STEALTH для обхода детекции автоматизации
        stealth(driver,
            languages=["ko-KR", "ko", "en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )

        # Увеличиваем timeout до 10 секунд для обхода блокировки
        driver.set_page_load_timeout(10)
        
        # Убираем implicit wait - будем использовать explicit wait только для списка новостей
        driver.implicitly_wait(0)

        logging.info("✅ Selenium WebDriver с STEALTH режимом инициализирован")
        logging.info("  ✓ Скрыты признаки автоматизации")
        logging.info("  ✓ Реалистичный User-Agent")
        logging.info("  ✓ WebGL/Canvas fingerprint защита")
        return driver

    except Exception as e:
        logging.error(f"❌ Ошибка инициализации браузера: {e}")
        return None


def debug_save_html_and_find_selectors(driver):
    """
    Сохраняет HTML страницы и тестирует разные селекторы для диагностики проблем
    """
    try:
        logging.info("🔍 ДИАГНОСТИКА: Начинаем анализ страницы...")
        
        # Сохраняем HTML
        html = driver.page_source
        debug_file = 'upbit_debug.html'
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(html)
        logging.info(f"💾 HTML сохранен в {debug_file}")
        
        # Тестируем разные селекторы через JavaScript
        selectors_to_test = [
            'a[href*="/service_center/notice?id="]',
            'a[href*="/service_center/notice"]',
            'tr a[href*="notice"]',
            '.notice-list a',
            '[class*="notice"] a',
            'table a[href*="id="]',
            'a[href*="id="]',
            'tr a',
        ]
        
        logging.info("🔍 Тестируем селекторы:")
        best_selector = None
        best_count = 0
        
        for selector in selectors_to_test:
            try:
                result = driver.execute_script(f"""
                    const links = document.querySelectorAll('{selector}');
                    const samples = [];
                    for (let i = 0; i < Math.min(3, links.length); i++) {{
                        samples.push({{
                            href: links[i].getAttribute('href') || '',
                            text: links[i].textContent.trim().substring(0, 50)
                        }});
                    }}
                    return {{
                        count: links.length,
                        samples: samples
                    }};
                """)
                
                count = result['count']
                samples = result['samples']
                
                logging.info(f"  🔍 Селектор '{selector}': найдено {count} элементов")
                
                if count > best_count:
                    best_count = count
                    best_selector = selector
                
                if count > 0 and samples:
                    for s in samples[:3]:
                        text = s['text'][:50]
                        href = s['href'][:60] if s['href'] else 'NO HREF'
                        logging.info(f"     📄 {text} -> {href}")
            except Exception as e:
                logging.error(f"  ❌ Ошибка тестирования селектора '{selector}': {e}")
        
        if best_selector:
            logging.info(f"✅ ЛУЧШИЙ СЕЛЕКТОР: '{best_selector}' ({best_count} элементов)")
            logging.info(f"💡 РЕКОМЕНДАЦИЯ: Используйте селектор '{best_selector}'")
        else:
            logging.error("❌ НЕ НАЙДЕНО подходящих селекторов!")
            logging.error("💡 Проверьте upbit_debug.html вручную")
        
        return best_selector
        
    except Exception as e:
        logging.error(f"❌ Ошибка диагностики: {e}")
        return None


def wait_for_notices_js(driver, max_wait=1.0):
    """
    Ждет появления новостей, проверяя каждые 50ms
    Возвращает True если новости появились, False если timeout
    """
    start = time.time()
    check_interval = 0.05  # 50ms
    
    while time.time() - start < max_wait:
        try:
            count = driver.execute_script("""
                return document.querySelectorAll('a[href*="/service_center/notice"]').length;
            """)
            
            if count > 0:
                elapsed = time.time() - start
                logging.info(f"⚡ Новости появились за {elapsed:.3f}s")
                return True
        except:
            pass
        
        time.sleep(check_interval)
    
    elapsed = time.time() - start
    logging.warning(f"⚠️ Новости не появились за {elapsed:.3f}s")
    return False


def get_all_notice_ids(driver):
    """
    Извлекает ID новостей через JavaScript с умными fallback стратегиями.
    
    Приоритет 1: НАЙТИ новости (правильный селектор)
    Приоритет 2: Сделать быстро (< 1 сек)
    
    Возвращает список ID незакрепленных новостей: [5710, 5709, 5701, ...]
    При ошибке автоматически запускает диагностику.
    """
    start_time = time.time()
    
    try:
        # JavaScript код с несколькими стратегиями поиска
        result = driver.execute_script("""
            // Стратегия 1: Точный селектор с id параметром
            let links = document.querySelectorAll('a[href*="/service_center/notice?id="]');
            let strategy = 'exact_id';
            
            // Стратегия 2: Если не нашли - любые ссылки с notice
            if (links.length === 0) {
                links = document.querySelectorAll('a[href*="/service_center/notice"]');
                strategy = 'notice_links';
            }
            
            // Стратегия 3: Если все еще не нашли - ссылки в tr с notice
            if (links.length === 0) {
                links = document.querySelectorAll('tr a[href*="notice"]');
                strategy = 'tr_notice';
            }
            
            // Стратегия 4: Если все еще не нашли - любые ссылки с id= параметром
            if (links.length === 0) {
                links = document.querySelectorAll('a[href*="id="]');
                strategy = 'any_id';
            }
            
            console.log('Strategy used:', strategy, 'Links found:', links.length);
            
            const notices = [];
            
            links.forEach(link => {
                const href = link.getAttribute('href');
                if (!href) return;
                
                // Извлекаем ID из href
                const match = href.match(/id=(\\d+)/);
                if (!match) return;
                
                const id = parseInt(match[1]);
                const title = link.textContent.trim();
                
                // Проверяем закрепленность несколькими способами
                let isPinned = false;
                
                // Способ 1: Проверка текста на маркер 공지 (공지 = "объявление/уведомление" на корейском)
                const row = link.closest('tr') || link.closest('div') || link.parentElement;
                if (row) {
                    const rowText = row.textContent;
                    isPinned = rowText.includes('공지');
                }
                
                // Способ 2: Проверка на иконку pin
                if (!isPinned && row) {
                    const pinIcon = row.querySelector('[class*="pin"]') || 
                                   row.querySelector('[class*="fixed"]') ||
                                   row.querySelector('svg[class*="pin"]');
                    isPinned = pinIcon !== null;
                }
                
                // Способ 3: Проверка класса row
                if (!isPinned && row) {
                    const rowClass = row.className || '';
                    isPinned = rowClass.includes('pinned') || 
                              rowClass.includes('fixed') ||
                              rowClass.includes('notice');
                }
                
                // Добавляем только незакрепленные
                if (!isPinned) {
                    notices.push({
                        id: id,
                        title: title,
                        href: href
                    });
                }
            });
            
            // Возвращаем результат
            return {
                success: notices.length > 0,
                count: notices.length,
                totalLinks: links.length,
                notices: notices,
                strategy: strategy
            };
        """)
        
        parse_time = time.time() - start_time
        
        # Проверяем результат
        if not result['success'] or result['count'] == 0:
            logging.error(f"❌ Новости не найдены!")
            logging.error(f"   Strategy: {result.get('strategy', 'unknown')}")
            logging.error(f"   Total links found: {result.get('totalLinks', 0)}")
            logging.error("💡 Запускаем диагностику...")
            
            # Автоматически запускаем диагностику
            debug_save_html_and_find_selectors(driver)
            return []
        
        # Извлекаем только ID
        notice_ids = [n['id'] for n in result['notices']]
        
        # Детальное логирование
        logging.info(f"✅ Найдено {result['count']} новостей (strategy: {result['strategy']}, total links: {result['totalLinks']})")
        logging.info(f"🔢 ID: {notice_ids[:5]}{'...' if len(notice_ids) > 5 else ''}")
        logging.info(f"⏱️ Время парсинга: {parse_time:.3f}s")
        
        # Оценка скорости
        if parse_time > 1.0:
            logging.warning(f"⚠️ Медленно: {parse_time:.3f}s > 1.0s")
        elif parse_time > 0.5:
            logging.info(f"✅ Хорошо: {parse_time:.3f}s < 1.0s")
        else:
            logging.info(f"⚡ Отлично: {parse_time:.3f}s < 0.5s!")
        
        return notice_ids
        
    except Exception as e:
        parse_time = time.time() - start_time
        logging.error(f"❌ Ошибка парсинга (время: {parse_time:.3f}s): {e}")
        logging.error("💡 Запускаем диагностику...")
        
        # Автоматически запускаем диагностику при ошибке
        try:
            debug_save_html_and_find_selectors(driver)
        except Exception as debug_error:
            logging.error(f"❌ Ошибка диагностики: {debug_error}")
        
        return []


def get_notice_by_id(driver, notice_id):
    """
    Получает данные конкретной новости по её ID
    """
    js_code = f"""
    const links = document.querySelectorAll('tr a[href*="/service_center/notice"]');
    
    for (let link of links) {{
        const href = link.getAttribute('href');
        const match = href.match(/id=(\\d+)/);
        
        if (match && parseInt(match[1]) === {notice_id}) {{
            const titleSpan = link.querySelector('span.css-qju2q6, span.css-twx20f, span[class*="title"]');
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
    message = f"""🔔 <b>Новая новость Upbit</b>

<b>{title}</b>

🔗 {link}"""
    
    # Добавляем футер с метриками (согласно требованию)
    if detection_time:
        bot_latency = (send_time - detection_time).total_seconds()
        
        # Форматируем времена
        detection_str = detection_time.strftime('%H:%M:%S')
        send_str = send_time.strftime('%H:%M:%S')
        
        # Футер с метриками
        message += f"""

⏱ Обнаружено: {detection_str}
📤 Отправлено: {send_str}
⚡️ Задержка: {bot_latency:.1f} сек"""
    
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


def get_random_delay():
    """
    Возвращает случайную задержку между 0.5 и 1.5 секундами для имитации человека
    """
    return random.uniform(0.5, 1.5)


def get_refresh_interval():
    """
    Возвращает случайный интервал между refresh (1-2 секунды)
    """
    return random.uniform(1.0, 2.0)


def main():
    logging.info("🚀 Upbit Notice Bot запущен")
    logging.info("📡 Режим: ULTRA-FAST JS PARSER + SMART SELECTOR CHECK")
    logging.info("🔄 Интервал проверки: 1-2 секунды")
    logging.info("")
    logging.info("⚡ ОПТИМИЗАЦИИ:")
    logging.info("  ✓ Selenium headless Chrome с STEALTH")
    logging.info("  ✓ Отключены изображения, CSS, media")
    logging.info("  ✓ page_load_strategy='eager'")
    logging.info("  ✓ Умное ожидание (polling 50ms)")
    logging.info("  ✓ JavaScript парсинг с fallback стратегиями")
    logging.info("  ✓ Автодиагностика при ошибках")
    logging.info("  ✓ Детальные метрики на каждом этапе")
    logging.info("  🎯 ЦЕЛЕВАЯ СКОРОСТЬ: < 1 сек на цикл")
    logging.info("")
    
    driver = init_driver()
    if not driver:
        logging.error("❌ Не удалось запустить браузер")
        return
    
    # Переменная для отслеживания 429 ошибок
    rate_limit_backoff = 0  # Дополнительная задержка при 429
    last_429_time = None
    
    try:
        # Первая загрузка с подробным логированием времени
        logging.info("📡 Подключаемся к Upbit...")
        
        cycle_start = time.time()
        
        # 1. Загрузка страницы
        page_load_start = time.time()
        driver.get(UPBIT_NOTICE_URL)
        page_load_time = time.time() - page_load_start
        logging.info(f"  ⏱️ Загрузка страницы: {page_load_time:.3f}s")
        
        # 2. Умное ожидание появления новостей (polling с проверкой каждые 50ms)
        wait_start = time.time()
        notices_appeared = wait_for_notices_js(driver, max_wait=0.5)
        wait_time = time.time() - wait_start
        
        # Fallback: если новости не появились за 0.5s, даём ещё 0.5s
        if not notices_appeared:
            logging.warning("⚠️ Новости не появились за 0.5s, даём ещё 0.5s...")
            time.sleep(0.5)
            wait_time = time.time() - wait_start
        
        logging.info(f"  ⏱️ Ожидание новостей: {wait_time:.3f}s")
        
        # 3. Парсинг ID (время учтено внутри get_all_notice_ids)
        parse_start = time.time()
        all_ids = get_all_notice_ids(driver)
        parse_time = time.time() - parse_start
        
        # Итоговое время всего цикла
        total_cycle_time = time.time() - cycle_start
        
        logging.info(f"⏱️ ━━━ ИТОГО ЦИКЛ: {total_cycle_time:.3f}s ━━━")
        logging.info(f"   Загрузка: {page_load_time:.3f}s | Ожидание: {wait_time:.3f}s | Парсинг: {parse_time:.3f}s")
        
        # Оценка общей производительности
        if total_cycle_time < 1.0:
            logging.info("✅ ⚡ ОТЛИЧНО: Полный цикл < 1 сек!")
        elif total_cycle_time < 1.5:
            logging.info("✅ ХОРОШО: Полный цикл < 1.5 сек")
        elif total_cycle_time < 2.0:
            logging.warning("⚠️ ПРИЕМЛЕМО: Полный цикл 1.5-2 сек")
        else:
            logging.error(f"❌ МЕДЛЕННО: Полный цикл {total_cycle_time:.3f} сек")
        
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
            notify_about_new_ids(driver, new_ids, pause_between=0.5)
            
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
        
        # Цикл мониторинга с частым refresh
        current_max_id = tracked_max_id
        refresh_count = 0
        
        logging.info("🔄 Начинаем polling с refresh каждые 1-2 секунды...")
        
        while True:
            try:
                # Вычисляем интервал для следующего refresh
                base_interval = get_refresh_interval()  # 1-2 секунды
                human_delay = get_random_delay()  # 0.5-1.5 секунды
                
                # Добавляем backoff если была 429 ошибка
                total_delay = base_interval + human_delay + rate_limit_backoff
                
                logging.debug(f"💤 Ожидание {total_delay:.2f}с (base: {base_interval:.2f}s, random: {human_delay:.2f}s, backoff: {rate_limit_backoff:.2f}s)")
                time.sleep(total_delay)
                
                # Время начала refresh
                refresh_start_time = datetime.now()
                refresh_count += 1
                
                logging.info(f"🔄 Refresh #{refresh_count} в {refresh_start_time.strftime('%H:%M:%S')}...")
                
                try:
                    # Время начала всего цикла refresh
                    cycle_start = time.time()
                    
                    # 1. Выполняем refresh страницы
                    refresh_load_start = time.time()
                    driver.refresh()
                    refresh_load_time = time.time() - refresh_load_start
                    logging.info(f"  ⏱️ Refresh страницы: {refresh_load_time:.3f}s")
                    
                    # 2. Умное ожидание появления новостей (polling)
                    wait_start = time.time()
                    notices_appeared = wait_for_notices_js(driver, max_wait=0.5)
                    wait_time = time.time() - wait_start
                    
                    # Fallback: если новости не появились за 0.5s, даём ещё 0.5s
                    if not notices_appeared:
                        logging.warning("  ⚠️ Новости не появились за 0.5s, даём ещё 0.5s...")
                        time.sleep(0.5)
                        wait_time = time.time() - wait_start
                    
                    logging.info(f"  ⏱️ Ожидание новостей: {wait_time:.3f}s")
                    
                    # 3. Парсинг ID (время учтено внутри get_all_notice_ids)
                    parse_start = time.time()
                    all_ids = get_all_notice_ids(driver)
                    parse_time = time.time() - parse_start
                    
                    # Итоговое время всего цикла
                    total_cycle_time = time.time() - cycle_start
                    
                    logging.info(f"  ⏱️ ━━━ ИТОГО ЦИКЛ: {total_cycle_time:.3f}s ━━━")
                    logging.info(f"     Refresh: {refresh_load_time:.3f}s | Ожидание: {wait_time:.3f}s | Парсинг: {parse_time:.3f}s")
                    
                    # Оценка производительности
                    if total_cycle_time < 1.0:
                        logging.info("  ✅ ⚡ ОТЛИЧНО: Цикл < 1 сек!")
                    elif total_cycle_time < 1.5:
                        logging.info("  ✅ ХОРОШО: Цикл < 1.5 сек")
                    elif total_cycle_time < 2.0:
                        logging.warning("  ⚠️ ПРИЕМЛЕМО: Цикл 1.5-2 сек")
                    else:
                        logging.error(f"  ❌ МЕДЛЕННО: Цикл {total_cycle_time:.3f} сек")
                    
                    # Сбрасываем backoff если refresh успешен
                    if rate_limit_backoff > 0:
                        logging.info("✅ Refresh успешен, сбрасываем backoff")
                        rate_limit_backoff = 0
                        last_429_time = None
                    
                except TimeoutException:
                    # Проверяем статус код - возможно 429
                    try:
                        status_code = driver.execute_script("return document.readyState")
                        if status_code != "complete":
                            logging.warning("⚠️ Страница не загрузилась полностью")
                            # Увеличиваем backoff на 10-30 секунд
                            rate_limit_backoff = random.uniform(10, 30)
                            last_429_time = datetime.now()
                            logging.warning(f"⚠️ Возможна блокировка 429, увеличиваем задержку на {rate_limit_backoff:.1f}с")
                            continue
                    except:
                        pass
                    
                    logging.warning("⚠️ Timeout при загрузке, пропускаем цикл")
                    continue
                
                # Получаем время после загрузки - момент обнаружения новостей
                detection_time = datetime.now()
                
                if not all_ids:
                    logging.warning("⚠️ Не удалось получить ID после refresh")
                    continue
                
                # Находим максимальный ID
                page_max_id = max(all_ids)
                
                # Проверяем есть ли новые новости
                if page_max_id > current_max_id:
                    logging.info(f"🆕 ОБНАРУЖЕНЫ НОВЫЕ НОВОСТИ!")
                    logging.info(f"📊 Было max_id: {current_max_id}")
                    logging.info(f"📊 Стало max_id: {page_max_id}")
                    
                    # Находим все новые ID
                    new_ids = [nid for nid in all_ids if nid > current_max_id]
                    new_ids.sort()
                    
                    logging.info(f"🔔 Новых новостей: {len(new_ids)} → ID: {new_ids}")
                    
                    # Отправляем уведомления
                    notify_about_new_ids(driver, new_ids, detection_start=detection_time, pause_between=0.5)
                    
                    # Обновляем текущий max_id
                    current_max_id = page_max_id
                    save_max_id(current_max_id)
                    
                    logging.info("👀 Продолжаем мониторинг...")
                else:
                    logging.debug(f"✓ Проверка #{refresh_count}: новостей нет (max_id: {page_max_id})")
                
            except WebDriverException as e:
                error_msg = str(e).lower()
                
                # Проверяем на 429 ошибку
                if '429' in error_msg or 'rate limit' in error_msg or 'too many requests' in error_msg:
                    rate_limit_backoff = random.uniform(10, 30)
                    last_429_time = datetime.now()
                    logging.error(f"❌ Обнаружена 429 ошибка! Увеличиваем задержку на {rate_limit_backoff:.1f}с")
                    continue
                
                # Проверяем на session error
                if 'session' in error_msg or 'disconnected' in error_msg:
                    logging.error(f"❌ Ошибка сессии браузера: {e}")
                    logging.warning("⚠️ Переинициализация браузера...")
                    
                    try:
                        driver.quit()
                    except:
                        pass
                    
                    driver = init_driver()
                    if not driver:
                        logging.error("❌ Не удалось переинициализировать браузер, останавливаемся")
                        break
                    
                    # Перезагружаем страницу с умным ожиданием
                    driver.get(UPBIT_NOTICE_URL)
                    wait_for_notices_js(driver, max_wait=1.0)
                    
                    # Получаем актуальный max_id
                    reloaded_ids = get_all_notice_ids(driver)
                    if reloaded_ids:
                        all_ids = reloaded_ids
                        page_max_id = max(all_ids)
                        if page_max_id > current_max_id:
                            logging.info("🆕 После переинициализации: обнаружены новые ID!")
                            new_ids = [nid for nid in all_ids if nid > current_max_id]
                            new_ids.sort()
                            detection_start = datetime.now()
                            notify_about_new_ids(driver, new_ids, detection_start=detection_start, pause_between=0.5)
                            current_max_id = page_max_id
                            save_max_id(current_max_id)
                        else:
                            current_max_id = max(current_max_id, page_max_id)
                    
                    logging.info("✅ Браузер переинициализирован, продолжаем мониторинг...")
                    continue
                
                # Другие ошибки
                logging.error(f"❌ WebDriver ошибка: {e}")
                time.sleep(5)
                
            except Exception as exc:
                logging.error(f"❌ Неожиданная ошибка: {type(exc).__name__}: {exc}")
                time.sleep(5)
                
    except KeyboardInterrupt:
        logging.info("⏹️ Остановка (Ctrl+C)")
    finally:
        if driver:
            driver.quit()
            logging.info("✅ Браузер закрыт")


if __name__ == "__main__":
    main()
