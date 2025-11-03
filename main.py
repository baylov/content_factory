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


def init_session():
    """
    Инициализирует requests Session с оптимальными настройками для максимальной скорости.
    Цель: HTTP запрос за 0.2-0.4 секунды.
    """
    session = requests.Session()
    
    # Настраиваем заголовки для имитации браузера
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0'
    })
    
    logging.info("✅ Requests Session инициализирована")
    logging.info("🚀 Используем requests + BeautifulSoup для ULTRA-FAST парсинга")
    logging.info("⚡ Целевая скорость HTTP запроса: 0.2-0.4 секунды")
    
    return session


def get_all_notice_ids(soup):
    """
    Получает все ID новостей со страницы (включая закрепленные).
    Парсит HTML через BeautifulSoup.
    Возвращает список ID: [5710, 5709, 5701, 5696, ...]
    """
    try:
        # Ищем все ссылки на новости в таблице
        links = soup.select('tr a[href*="/service_center/notice"]')
        
        ids = []
        for link in links:
            href = link.get('href', '')
            match = re.search(r'id=(\d+)', href)
            if match:
                notice_id = int(match.group(1))
                ids.append(notice_id)
        
        if ids:
            logging.info(f"[get_all_notice_ids] Найдено ID: {ids[:5]}... (всего {len(ids)})")
            return ids
        else:
            logging.warning("[get_all_notice_ids] ID не найдены")
            return []
    except Exception as e:
        logging.error(f"[get_all_notice_ids] Ошибка: {e}")
        return []


def is_pinned_notice(row_element):
    """
    Определяет, является ли новость закрепленной.
    Проверяет наличие маркеров в HTML (например, класс 'pinned', бейдж '고정' и т.д.)
    """
    try:
        # Проверяем различные маркеры закрепленных новостей
        row_html = str(row_element)
        
        # Типичные маркеры:
        # - класс 'pinned'
        # - бейдж с текстом '고정' (закреплено по-корейски)
        # - специальные CSS классы
        if 'pinned' in row_html.lower():
            return True
        if '고정' in row_html:
            return True
        
        # Проверяем наличие специальных иконок или бейджей
        badge = row_element.select_one('.badge, .pin-badge, [class*="pin"]')
        if badge and ('고정' in badge.get_text() or 'pinned' in badge.get_text().lower()):
            return True
        
        return False
    except Exception as e:
        logging.error(f"[is_pinned_notice] Ошибка: {e}")
        return False


def get_unpinned_notice_ids(soup):
    """
    Получает ID только незакрепленных новостей.
    Возвращает список ID, отфильтрованный от закрепленных.
    """
    try:
        # Ищем все строки таблицы с новостями
        rows = soup.select('tr')
        
        unpinned_ids = []
        
        for row in rows:
            # Проверяем, закреплена ли новость
            if is_pinned_notice(row):
                continue
            
            # Ищем ссылку на новость
            link = row.select_one('a[href*="/service_center/notice"]')
            if link:
                href = link.get('href', '')
                match = re.search(r'id=(\d+)', href)
                if match:
                    notice_id = int(match.group(1))
                    unpinned_ids.append(notice_id)
        
        if unpinned_ids:
            logging.info(f"[get_unpinned_notice_ids] Незакрепленных ID: {unpinned_ids[:5]}... (всего {len(unpinned_ids)})")
        else:
            logging.warning("[get_unpinned_notice_ids] Незакрепленных ID не найдено")
        
        return unpinned_ids
    except Exception as e:
        logging.error(f"[get_unpinned_notice_ids] Ошибка: {e}")
        return []


def get_notice_by_id(soup, notice_id):
    """
    Получает данные конкретной новости по её ID из HTML.
    Парсит через BeautifulSoup.
    """
    try:
        # Ищем все ссылки на новости
        links = soup.select('tr a[href*="/service_center/notice"]')
        
        for link in links:
            href = link.get('href', '')
            match = re.search(r'id=(\d+)', href)
            
            if match and int(match.group(1)) == notice_id:
                # Извлекаем заголовок
                # Сначала пробуем найти span с заголовком
                title_span = link.select_one('span.css-qju2q6, span[class*="title"]')
                if title_span:
                    title = title_span.get_text(strip=True)
                else:
                    title = link.get_text(strip=True)
                
                # Формируем полную ссылку
                full_link = f"https://upbit.com{href}" if href.startswith('/') else href
                
                return {
                    "id": notice_id,
                    "title": title,
                    "link": full_link
                }
        
        return None
    except Exception as e:
        logging.error(f"[get_notice_by_id] Ошибка для ID {notice_id}: {e}")
        return None


def fetch_page(session, url, timeout=2):
    """
    Выполняет HTTP запрос и возвращает BeautifulSoup объект.
    
    Args:
        session: requests.Session объект
        url: URL страницы
        timeout: таймаут запроса (по умолчанию 2 секунды)
    
    Returns:
        tuple: (soup, response_time, status_code) или (None, 0, status_code) при ошибке
    """
    try:
        start_time = time.time()
        response = session.get(url, timeout=timeout)
        response_time = time.time() - start_time
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            return soup, response_time, response.status_code
        else:
            logging.error(f"[fetch_page] HTTP {response.status_code}: {url}")
            return None, response_time, response.status_code
    
    except requests.exceptions.Timeout:
        logging.error(f"[fetch_page] Timeout: {url}")
        return None, timeout, None
    
    except requests.exceptions.ConnectionError as e:
        logging.error(f"[fetch_page] Connection error: {e}")
        return None, 0, None
    
    except Exception as e:
        logging.error(f"[fetch_page] Ошибка: {e}")
        return None, 0, None


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


def notify_about_new_ids(session, soup, new_ids, *, detection_start=None, pause_between=0.5):
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
        notice = get_notice_by_id(soup, notice_id)
        
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
    Возвращает случайный интервал между refresh (0.5-1.0 секунды для ultra-fast режима)
    """
    return random.uniform(0.5, 1.0)


def main():
    logging.info("🚀 Upbit Notice Bot запущен")
    logging.info("📡 Режим: ULTRA-FAST REQUESTS + BEAUTIFULSOUP")
    logging.info("🔄 Интервал проверки: 0.5-1.5 секунды (случайный)")
    logging.info("🔢 Логика: Отслеживание по максимальному ID")
    logging.info("")
    logging.info("⚡ ОПТИМИЗАЦИИ СКОРОСТИ:")
    logging.info("  ✓ requests вместо Selenium (без браузера!)")
    logging.info("  ✓ BeautifulSoup для парсинга HTML")
    logging.info("  ✓ Keep-alive соединение (переиспользование session)")
    logging.info("  ✓ Минимальный timeout (2 секунды)")
    logging.info("  ✓ Без загрузки JavaScript, изображений, CSS")
    logging.info("  🎯 ЦЕЛЕВАЯ СКОРОСТЬ: 0.3-0.5 сек на цикл")
    logging.info("")
    
    session = init_session()
    
    # Переменная для отслеживания 429 ошибок
    rate_limit_backoff = 0  # Дополнительная задержка при 429
    last_429_time = None
    consecutive_errors = 0  # Счетчик последовательных ошибок
    
    try:
        # Первая загрузка с подробным логированием времени
        logging.info("📡 Подключаемся к Upbit...")
        
        soup, response_time, status_code = fetch_page(session, UPBIT_NOTICE_URL, timeout=2)
        
        if not soup:
            logging.error("❌ Не удалось загрузить страницу при первом запросе")
            if status_code == 429:
                logging.error("❌ Получена 429 ошибка - слишком много запросов")
                logging.info("💡 Рекомендация: увеличьте интервал между запросами")
            return
        
        logging.info(f"⏱️ Время HTTP запроса: {response_time:.3f}s")
        
        if response_time < 0.4:
            logging.info("✅ ОТЛИЧНО: HTTP запрос < 0.4 сек!")
        elif response_time < 0.7:
            logging.info("✅ ХОРОШО: HTTP запрос < 0.7 сек")
        elif response_time < 1.0:
            logging.warning("⚠️ ПРИЕМЛЕМО: HTTP запрос < 1 сек")
        else:
            logging.error(f"❌ МЕДЛЕННО: HTTP запрос {response_time:.3f} сек")
        
        # Парсим список новостей
        parse_start = time.time()
        all_ids = get_all_notice_ids(soup)
        parse_time = time.time() - parse_start
        
        logging.info(f"⏱️ Время парсинга HTML: {parse_time:.3f}s")
        
        if not all_ids:
            logging.error("❌ Не удалось получить ID новостей")
            logging.info("💡 Возможно, структура страницы изменилась или требуется JavaScript")
            logging.info("💡 Попробуйте проверить HTML структуру страницы")
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
            
            notice = get_notice_by_id(soup, page_max_id)
            
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
            notify_about_new_ids(session, soup, new_ids, pause_between=0.5)
            
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
        
        # Цикл мониторинга с частым polling
        current_max_id = tracked_max_id
        refresh_count = 0
        
        logging.info("🔄 Начинаем polling с проверками каждые 0.5-1.5 секунды...")
        
        while True:
            try:
                # Вычисляем интервал для следующей проверки
                base_interval = get_refresh_interval()  # 0.5-1.0 секунды
                human_delay = get_random_delay()  # 0.5-1.5 секунды
                
                # Добавляем backoff если была 429 ошибка
                total_delay = base_interval + rate_limit_backoff
                
                logging.debug(f"💤 Ожидание {total_delay:.2f}с (base: {base_interval:.2f}s, backoff: {rate_limit_backoff:.2f}s)")
                time.sleep(total_delay)
                
                # Время начала цикла
                cycle_start_time = datetime.now()
                cycle_start = time.time()
                refresh_count += 1
                
                logging.info(f"🔄 Проверка #{refresh_count} в {cycle_start_time.strftime('%H:%M:%S')}...")
                
                # === HTTP ЗАПРОС ===
                http_start = time.time()
                soup, response_time, status_code = fetch_page(session, UPBIT_NOTICE_URL, timeout=2)
                http_time = time.time() - http_start
                
                logging.info(f"  ⏱️ HTTP запрос: {http_time:.3f}s")
                
                # Обработка ошибок HTTP
                if not soup:
                    consecutive_errors += 1
                    
                    if status_code == 429:
                        # 429 Too Many Requests - увеличиваем задержку
                        rate_limit_backoff = random.uniform(10, 30)
                        last_429_time = datetime.now()
                        logging.error(f"❌ Получена 429 ошибка! Увеличиваем задержку на {rate_limit_backoff:.1f}с")
                        continue
                    
                    elif status_code == 403:
                        # 403 Forbidden - возможна блокировка
                        rate_limit_backoff = random.uniform(5, 15)
                        logging.error(f"❌ Получена 403 ошибка! Увеличиваем задержку на {rate_limit_backoff:.1f}с")
                        continue
                    
                    else:
                        # Другие ошибки - просто логируем и продолжаем
                        logging.warning(f"⚠️ Не удалось загрузить страницу (попытка #{refresh_count}), продолжаем...")
                        
                        # Если слишком много последовательных ошибок - увеличиваем интервал
                        if consecutive_errors > 5:
                            rate_limit_backoff = random.uniform(5, 10)
                            logging.warning(f"⚠️ Много последовательных ошибок, увеличиваем интервал на {rate_limit_backoff:.1f}с")
                        
                        continue
                
                # Успешный запрос - сбрасываем счетчики
                consecutive_errors = 0
                if rate_limit_backoff > 0:
                    logging.info("✅ HTTP запрос успешен, сбрасываем backoff")
                    rate_limit_backoff = 0
                    last_429_time = None
                
                # === ПАРСИНГ HTML ===
                parse_start = time.time()
                all_ids = get_all_notice_ids(soup)
                parse_time = time.time() - parse_start
                
                logging.info(f"  ⏱️ Парсинг HTML: {parse_time:.3f}s")
                
                if not all_ids:
                    logging.warning("⚠️ Не удалось получить ID после запроса")
                    continue
                
                # === ПРОВЕРКА ID ===
                check_start = time.time()
                page_max_id = max(all_ids)
                check_time = time.time() - check_start
                
                logging.info(f"  ⏱️ Проверка ID: {check_time:.3f}s")
                
                # Проверяем есть ли новые новости
                if page_max_id > current_max_id:
                    logging.info(f"🆕 ОБНАРУЖЕНЫ НОВЫЕ НОВОСТИ!")
                    logging.info(f"📊 Было max_id: {current_max_id}")
                    logging.info(f"📊 Стало max_id: {page_max_id}")
                    
                    # Находим все новые ID
                    new_ids = [nid for nid in all_ids if nid > current_max_id]
                    new_ids.sort()
                    
                    logging.info(f"🔔 Новых новостей: {len(new_ids)} → ID: {new_ids}")
                    
                    # === ОТПРАВКА В TELEGRAM ===
                    telegram_start = time.time()
                    notify_about_new_ids(session, soup, new_ids, detection_start=cycle_start_time, pause_between=0.5)
                    telegram_time = time.time() - telegram_start
                    
                    logging.info(f"  ⏱️ Отправка в Telegram: {telegram_time:.3f}s")
                    
                    # Обновляем текущий max_id
                    current_max_id = page_max_id
                    save_max_id(current_max_id)
                    
                    # Общее время цикла
                    total_cycle_time = time.time() - cycle_start
                    logging.info(f"  ⏱️ ИТОГО цикл: {total_cycle_time:.3f}s")
                    
                    if total_cycle_time < 0.5:
                        logging.info("  ✅ ОТЛИЧНО: Цикл < 0.5 сек!")
                    elif total_cycle_time < 1.0:
                        logging.info("  ✅ ХОРОШО: Цикл < 1 сек")
                    elif total_cycle_time < 2.0:
                        logging.warning("  ⚠️ ПРИЕМЛЕМО: Цикл 1-2 сек")
                    else:
                        logging.error(f"  ❌ МЕДЛЕННО: Цикл {total_cycle_time:.3f} сек")
                    
                    logging.info("👀 Продолжаем мониторинг...")
                else:
                    # Общее время цикла (без отправки в Telegram)
                    total_cycle_time = time.time() - cycle_start
                    logging.info(f"  ⏱️ ИТОГО цикл: {total_cycle_time:.3f}s")
                    
                    if total_cycle_time < 0.5:
                        logging.info("  ✅ ОТЛИЧНО: Цикл < 0.5 сек!")
                    elif total_cycle_time < 1.0:
                        logging.info("  ✅ ХОРОШО: Цикл < 1 сек")
                    
                    logging.debug(f"✓ Проверка #{refresh_count}: новостей нет (max_id: {page_max_id})")
                
            except requests.exceptions.Timeout:
                logging.warning("⚠️ Timeout при запросе, продолжаем...")
                time.sleep(2)
            
            except requests.exceptions.ConnectionError as e:
                logging.error(f"❌ Connection error: {e}")
                logging.warning("⚠️ Ждем 5 секунд перед повторной попыткой...")
                time.sleep(5)
            
            except Exception as exc:
                logging.error(f"❌ Неожиданная ошибка: {type(exc).__name__}: {exc}")
                time.sleep(5)
                
    except KeyboardInterrupt:
        logging.info("⏹️ Остановка (Ctrl+C)")
    finally:
        logging.info("✅ Сессия завершена")


if __name__ == "__main__":
    main()
