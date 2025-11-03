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
    Оптимизирован для быстрой загрузки с минимизацией ресурсов.
    """
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--disable-dev-tools')
        chrome_options.add_argument('--disable-extensions')
        
        # Оптимизация скорости загрузки
        chrome_options.add_argument('--blink-settings=imagesEnabled=false')  # Отключить изображения
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        
        # Дополнительные настройки для производительности
        prefs = {
            'profile.default_content_setting_values': {
                'images': 2,  # Блокировать изображения
                'plugins': 2,  # Блокировать плагины
                'popups': 2,  # Блокировать всплывающие окна
            },
            'profile.managed_default_content_settings': {
                'images': 2
            }
        }
        chrome_options.add_experimental_option('prefs', prefs)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.set_page_load_timeout(15)  # Уменьшен timeout для более быстрых циклов
        driver.implicitly_wait(5)  # Уменьшен implicit wait

        logging.info("✅ Браузер Chrome запущен в оптимизированном режиме (быстрая загрузка)")
        return driver

    except Exception as e:
        logging.error(f"❌ Ошибка инициализации браузера: {e}")
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
        const match = href.match(/id=(\\d+)/);
        
        if (match && parseInt(match[1]) === {notice_id}) {{
            const titleSpan = link.querySelector('span.css-qju2q6');
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
    logging.info("📡 Режим: FAST REFRESH POLLING (без MutationObserver)")
    logging.info("🔄 Интервал refresh: 1-2 секунды (случайный)")
    logging.info("🔢 Логика: Отслеживание по максимальному ID")
    
    driver = init_driver()
    if not driver:
        logging.error("❌ Не удалось запустить браузер")
        return
    
    # Переменная для отслеживания 429 ошибок
    rate_limit_backoff = 0  # Дополнительная задержка при 429
    last_429_time = None
    
    try:
        # Первая загрузка
        logging.info("📡 Подключаемся к Upbit...")
        driver.get(UPBIT_NOTICE_URL)
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
        
        # Небольшая пауза для полной загрузки
        time.sleep(get_random_delay())
        
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
                    # Выполняем refresh страницы
                    driver.refresh()
                    
                    # Ждем загрузки списка новостей
                    wait = WebDriverWait(driver, 10)
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
                    
                    # Небольшая пауза для стабильности
                    time.sleep(0.3)
                    
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
                
                # Получаем время после загрузки
                detection_time = datetime.now()
                load_time = (detection_time - refresh_start_time).total_seconds()
                
                if load_time > 2.0:
                    logging.warning(f"⚠️ Медленная загрузка: {load_time:.2f}с")
                
                # Получаем все ID
                all_ids = get_all_notice_ids(driver)
                
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
                    
                    # Перезагружаем страницу
                    driver.get(UPBIT_NOTICE_URL)
                    wait = WebDriverWait(driver, 15)
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tr a[href*="/service_center/notice"]')))
                    time.sleep(get_random_delay())
                    
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
