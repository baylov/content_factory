import os
import time
import logging
from datetime import datetime
import re
import random
import asyncio
from logging.handlers import RotatingFileHandler

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.async_api import async_playwright

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


class UpbitParser:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
    async def init(self):
        """Инициализация браузера один раз при старте"""
        logging.info("🔧 Инициализация Playwright браузера...")
        
        self.playwright = await async_playwright().start()
        
        # Запуск браузера с оптимизациями
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--disable-setuid-sandbox',
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        
        # Создание контекста с более реалистичным user agent
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='ko-KR',
            timezone_id='Asia/Seoul',
            extra_http_headers={
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            }
        )
        
        # Создание страницы
        self.page = await self.context.new_page()
        
        # Скрываем признаки автоматизации
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.navigator.chrome = {
                runtime: {}
            };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['ko-KR', 'ko', 'en-US', 'en']
            });
        """)
        
        # Блокировка ненужных ресурсов для скорости (только images, media)
        # Оставляем CSS и fonts чтобы страница загружалась корректно
        await self.page.route("**/*", lambda route: route.abort() 
            if route.request.resource_type in ["image", "media"]
            else route.continue_())
        
        # Увеличенные таймауты для первой загрузки
        self.page.set_default_timeout(10000)
        self.page.set_default_navigation_timeout(10000)
        
        logging.info("✅ Playwright браузер инициализирован")
        logging.info("  ✓ Headless режим: включен")
        logging.info("  ✓ Блокировка ресурсов: images, media (CSS/fonts разрешены)")
        logging.info("  ✓ Таймауты: 10 секунд")
        logging.info("  ✓ Локаль: ko-KR (Asia/Seoul)")
        
    async def get_page_html(self):
        """Получение HTML страницы через Playwright с замером времени"""
        start_time = time.time()
        
        try:
            # Переход на страницу (используем ту же page, не создаём новую!)
            await self.page.goto(
                UPBIT_NOTICE_URL,
                wait_until='networkidle',
                timeout=10000
            )
            
            # Проверяем визуальные индикаторы ошибок
            error_indicators = await self.page.query_selector_all('.error, .alert-error')
            if error_indicators:
                logging.warning("⚠️ На странице обнаружены индикаторы ошибки")
            
            # Дополнительное ожидание для полной загрузки JS-контента
            await self.page.wait_for_timeout(1000)
            
            load_time = time.time() - start_time
            logging.info(f"⏱️ Время загрузки страницы: {load_time:.3f}s")
            
            if load_time > 3:
                logging.error(f"❌ МЕДЛЕННО: Загрузка {load_time:.3f} сек")
            elif load_time < 1:
                logging.info(f"⚡ БЫСТРО: Загрузка {load_time:.3f} сек")
            
            # Проверка текста страницы на ошибки
            error_text = await self.page.evaluate('''() => {
                return document.body.innerText;
            }''')
            
            if '알 수 없는 오류' in error_text or '오류가 발생' in error_text:
                logging.error("❌ Страница показывает ошибку в тексте")
            
            # Извлечение HTML
            html = await self.page.content()
            
            # === Сохранение HTML для отладки ===
            debug_file = 'upbit_page_debug.html'
            try:
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(html)
                logging.info(f"💾 DEBUG: HTML сохранён в {debug_file}")
            except Exception as e:
                logging.warning(f"⚠️ Не удалось сохранить debug HTML: {e}")
            # === КОНЕЦ ДОБАВЛЕНИЯ ===
            
            return html, load_time
            
        except Exception as e:
            load_time = time.time() - start_time
            logging.error(f"❌ Ошибка загрузки страницы: {e}")
            return None, load_time
        
    async def close(self):
        """Корректное закрытие браузера"""
        logging.info("🔄 Закрытие Playwright браузера...")
        
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
            
        logging.info("✅ Браузер закрыт")


def get_all_notice_ids(soup):
    """
    Получает все ID новостей со страницы (включая закрепленные).
    Парсит HTML через BeautifulSoup.
    Возвращает список ID: [5710, 5709, 5701, 5696, ...]
    """
    try:
        # ИСПРАВЛЕННЫЙ СЕЛЕКТОР: Точный селектор с параметром id
        links = soup.select('a[href*="/service_center/notice?id="]')
        
        # Fallback: если первый селектор не сработал
        if not links:
            logging.warning("[get_all_notice_ids] Основной селектор не сработал, пробуем regex")
            links = soup.find_all('a', href=re.compile(r'/service_center/notice\?id=\d+'))
        
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
            
            # DEBUG: детальная информация
            all_links = soup.find_all('a', href=True)
            logging.info(f"[DEBUG] Всего ссылок на странице: {len(all_links)}")
            
            if all_links:
                # Показываем первые 5 ссылок
                sample = []
                for l in all_links[:5]:
                    text = l.get_text(strip=True)[:30]
                    href = l['href'][:50]
                    sample.append(f"{text} -> {href}")
                logging.info(f"[DEBUG] Примеры ссылок:")
                for s in sample:
                    logging.info(f"[DEBUG]   {s}")
            
            # Ищем специфичные для Upbit элементы
            notice_divs = soup.find_all('div', class_=re.compile('notice|board|list', re.I))
            logging.info(f"[DEBUG] Divs с классами notice/board/list: {len(notice_divs)}")
            
            # Проверяем на сообщения об ошибках
            error_texts = soup.find_all(string=re.compile('오류|error|차단|block', re.I))
            if error_texts:
                logging.error(f"[DEBUG] Обнаружены сообщения об ошибках на странице:")
                for err in error_texts[:3]:
                    logging.error(f"[DEBUG]   {err.strip()[:100]}")
            
            return []
            
    except Exception as e:
        logging.error(f"[get_all_notice_ids] Ошибка: {e}")
        import traceback
        logging.error(f"[DEBUG] Traceback: {traceback.format_exc()}")
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
            link = row.select_one('a[href*="/service_center/notice?id="]')
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
        links = soup.select('a[href*="/service_center/notice?id="]')
        
        for link in links:
            href = link.get('href', '')
            match = re.search(r'id=(\d+)', href)
            
            if match and int(match.group(1)) == notice_id:
                # Извлекаем заголовок
                # Сначала пробуем найти span с заголовком
                title_span = link.select_one('span.css-qju2q6, span.css-twx20f, span[class*="title"]')
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


def notify_about_new_ids(soup, new_ids, *, detection_start=None, pause_between=0.5):
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


async def main():
    logging.info("🚀 Upbit Notice Bot запущен")
    logging.info("📡 Режим: PLAYWRIGHT + ASYNC (JavaScript support)")
    logging.info("🔄 Интервал проверки: 0.5-1.5 секунды (случайный)")
    logging.info("🔢 Логика: Отслеживание по максимальному ID")
    logging.info("")
    logging.info("⚡ ОПТИМИЗАЦИИ СКОРОСТИ:")
    logging.info("  ✓ Playwright headless режим")
    logging.info("  ✓ Переиспользование browser context")
    logging.info("  ✓ Блокировка изображений, media")
    logging.info("  ✓ Таймауты: 10 секунд")
    logging.info("  ✓ wait_until='networkidle'")
    logging.info("  ✓ Антидетект: скрыты признаки автоматизации")
    logging.info("  🎯 ЦЕЛЕВАЯ СКОРОСТЬ: 2-5 сек на цикл (с JS-рендерингом)")
    logging.info("")
    
    parser = UpbitParser()
    await parser.init()
    
    # Переменная для отслеживания 429 ошибок
    rate_limit_backoff = 0  # Дополнительная задержка при 429
    last_429_time = None
    consecutive_errors = 0  # Счетчик последовательных ошибок
    
    try:
        # Первая загрузка с подробным логированием времени
        logging.info("📡 Подключаемся к Upbit...")
        
        html, load_time = await parser.get_page_html()
        
        if not html:
            logging.error("❌ Не удалось загрузить страницу при первом запросе")
            await parser.close()
            return
        
        if load_time < 0.5:
            logging.info("⚡ ОТЛИЧНО: Загрузка < 0.5 сек!")
        elif load_time < 1.0:
            logging.info("✅ ХОРОШО: Загрузка < 1.0 сек")
        elif load_time < 1.5:
            logging.warning("⚠️ ПРИЕМЛЕМО: Загрузка < 1.5 сек")
        else:
            logging.error(f"❌ МЕДЛЕННО: Загрузка {load_time:.3f} сек")
        
        soup = BeautifulSoup(html, 'html.parser')
        
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
            notify_about_new_ids(soup, new_ids, pause_between=0.5)
            
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
                await asyncio.sleep(total_delay)
                
                # Время начала цикла
                cycle_start_time = datetime.now()
                cycle_start = time.time()
                refresh_count += 1
                
                logging.info(f"🔄 Проверка #{refresh_count} в {cycle_start_time.strftime('%H:%M:%S')}...")
                
                # === ЗАГРУЗКА СТРАНИЦЫ ===
                load_start = time.time()
                html, load_time = await parser.get_page_html()
                
                logging.info(f"  ⏱️ Загрузка страницы: {load_time:.3f}s")
                
                # Обработка ошибок загрузки
                if not html:
                    consecutive_errors += 1
                    
                    logging.warning(f"⚠️ Не удалось загрузить страницу (попытка #{refresh_count}), продолжаем...")
                    
                    # Если слишком много последовательных ошибок - увеличиваем интервал
                    if consecutive_errors > 5:
                        rate_limit_backoff = random.uniform(5, 10)
                        logging.warning(f"⚠️ Много последовательных ошибок, увеличиваем интервал на {rate_limit_backoff:.1f}с")
                    
                    continue
                
                # Успешный запрос - сбрасываем счетчики
                consecutive_errors = 0
                if rate_limit_backoff > 0:
                    logging.info("✅ Загрузка успешна, сбрасываем backoff")
                    rate_limit_backoff = 0
                    last_429_time = None
                
                soup = BeautifulSoup(html, 'html.parser')
                
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
                    notify_about_new_ids(soup, new_ids, detection_start=cycle_start_time, pause_between=0.5)
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
                
            except asyncio.TimeoutError:
                logging.warning("⚠️ Timeout при запросе, продолжаем...")
                await asyncio.sleep(2)
            
            except Exception as exc:
                logging.error(f"❌ Неожиданная ошибка в цикле: {type(exc).__name__}: {exc}")
                await asyncio.sleep(5)
                
    except KeyboardInterrupt:
        logging.info("⏹️ Остановка (Ctrl+C)")
    finally:
        await parser.close()
        logging.info("✅ Сессия завершена")


if __name__ == "__main__":
    asyncio.run(main())
