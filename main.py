import os
import time
import logging
from datetime import datetime
import re
import random
import json
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


def init_driver(enable_cdp=False):
    """
    Инициализирует Selenium WebDriver с агрессивными настройками для максимальной скорости.
    Цель: загрузка страницы за 0.3-0.5 секунды вместо 2+ секунд.
    
    Args:
        enable_cdp: Если True, включает Chrome DevTools Protocol для перехвата сетевых запросов
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
        
        # CDP logging - включаем только если необходимо (Selenium 4.x синтаксис)
        if enable_cdp:
            chrome_options.add_argument('--enable-logging')
            chrome_options.add_argument('--v=1')
            # Selenium 4.x: используем set_capability вместо desired_capabilities
            chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        else:
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
        
        # Selenium 4.x: только service и options (desired_capabilities убран!)
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
        
        # Включаем CDP Network tracking если требуется
        if enable_cdp:
            try:
                driver.execute_cdp_cmd('Network.enable', {})
                logging.info("✅ Selenium WebDriver с STEALTH + CDP режимом инициализирован")
                logging.info("  ✓ Chrome DevTools Protocol enabled для перехвата API")
            except Exception as cdp_error:
                logging.warning(f"⚠️ CDP не удалось активировать: {cdp_error}")
                logging.info("  → Fallback на HTML парсинг")
        else:
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


def wait_for_notices_js(driver, max_wait=0.3):
    """
    Ждет появления новостей, проверяя каждые 20ms.
    Использует те же fallback стратегии, что и get_all_notice_ids().
    Возвращает True если новости появились, False если timeout.
    """
    start = time.time()
    check_interval = 0.02  # 20ms
    
    while time.time() - start < max_wait:
        try:
            # Используем те же стратегии, что и в get_all_notice_ids
            count = driver.execute_script("""
                // Стратегия 1: Точный селектор с ?id=
                let count = document.querySelectorAll('a[href*="/service_center/notice?id="]').length;
                
                // Стратегия 2: Любые ссылки с notice
                if (count === 0) {
                    count = document.querySelectorAll('a[href*="/service_center/notice"]').length;
                }
                
                // Стратегия 3: Ссылки в таблице
                if (count === 0) {
                    count = document.querySelectorAll('tr a[href*="notice"]').length;
                }
                
                // Стратегия 4: Любые ссылки с id=
                if (count === 0) {
                    count = document.querySelectorAll('a[href*="id="]').length;
                }
                
                return count;
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
    
    Fallback стратегии совпадают с диагностикой:
    1. exact_id - точный селектор с ?id=
    2. all_notice - любые ссылки с /service_center/notice
    3. tr_notice - ссылки в таблице
    4. any_id - любые ссылки с параметром id=
    """
    start_time = time.time()
    
    try:
        # JavaScript код с несколькими стратегиями поиска (как в диагностике!)
        result = driver.execute_script("""
            // Стратегия 1: Точный селектор с id параметром (самый надёжный)
            let links = document.querySelectorAll('a[href*="/service_center/notice?id="]');
            let strategy = 'exact_id';
            
            // Стратегия 2: Любые ссылки с notice (как в диагностике!)
            if (links.length === 0) {
                links = document.querySelectorAll('a[href*="/service_center/notice"]');
                strategy = 'all_notice';
            }
            
            // Стратегия 3: Ссылки в таблице с notice
            if (links.length === 0) {
                links = document.querySelectorAll('tr a[href*="notice"]');
                strategy = 'tr_notice';
            }
            
            // Стратегия 4: Любые ссылки с id= параметром
            if (links.length === 0) {
                links = document.querySelectorAll('a[href*="id="]');
                strategy = 'any_id';
            }
            
            console.log('Strategy used:', strategy, 'Total links found:', links.length);
            
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
        
        # Детальное логирование (показываем стратегию и количество ссылок)
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


def discover_api_endpoints(driver, save_to_file=True):
    """
    Режим обнаружения API endpoints - анализирует сетевые запросы
    и находит JSON API которые использует Upbit для загрузки новостей
    
    Args:
        driver: Selenium WebDriver с включенным CDP
        save_to_file: Сохранять ли результаты в api_discovery.json
    
    Returns:
        list: Список найденных API endpoints
    """
    logging.info("🔍 ━━━ РЕЖИМ ОБНАРУЖЕНИЯ API ━━━")
    logging.info("Загружаем страницу и анализируем сетевые запросы...")
    
    try:
        # Загружаем страницу
        driver.get(UPBIT_NOTICE_URL)
        time.sleep(3)  # Даём всем запросам завершиться
        
        # Получаем все логи производительности
        logs = driver.get_log('performance')
        logging.info(f"📊 Всего сетевых событий: {len(logs)}")
        
        # Анализируем запросы
        api_candidates = []
        json_responses = []
        
        for log in logs:
            try:
                message = json.loads(log['message'])
                msg_data = message.get('message', {})
                method = msg_data.get('method', '')
                
                # Ищем ответы на запросы
                if method == 'Network.responseReceived':
                    params = msg_data.get('params', {})
                    response = params.get('response', {})
                    url = response.get('url', '')
                    mime_type = response.get('mimeType', '')
                    status = response.get('status', 0)
                    
                    # Фильтруем JSON ответы
                    if 'json' in mime_type.lower() or 'application' in mime_type.lower():
                        json_responses.append({
                            'url': url,
                            'status': status,
                            'mimeType': mime_type,
                            'requestId': params.get('requestId', '')
                        })
                        
                        # Проверяем на наличие ключевых слов
                        url_lower = url.lower()
                        if any(keyword in url_lower for keyword in ['notice', 'announcement', 'news', 'board', 'list']):
                            api_candidates.append({
                                'url': url,
                                'status': status,
                                'mimeType': mime_type,
                                'requestId': params.get('requestId', ''),
                                'priority': 'HIGH'
                            })
                            logging.info(f"🎯 Найден потенциальный API: {url}")
            
            except (json.JSONDecodeError, KeyError) as e:
                # Пропускаем невалидные логи
                continue
        
        logging.info(f"\n📋 JSON ответы найдены: {len(json_responses)}")
        
        if api_candidates:
            logging.info(f"\n🎯 Потенциальные API endpoints: {len(api_candidates)}")
            for idx, candidate in enumerate(api_candidates, 1):
                logging.info(f"  {idx}. {candidate['url']}")
                logging.info(f"     Status: {candidate['status']}, Type: {candidate['mimeType']}")
        else:
            logging.warning("\n⚠️ Прямые API endpoints с ключевыми словами не найдены")
            logging.info("📋 Все JSON ответы:")
            for idx, resp in enumerate(json_responses[:10], 1):  # Показываем первые 10
                logging.info(f"  {idx}. {resp['url']}")
                logging.info(f"     Status: {resp['status']}, Type: {resp['mimeType']}")
        
        # Сохраняем результаты
        if save_to_file:
            discovery_data = {
                'timestamp': datetime.now().isoformat(),
                'total_network_events': len(logs),
                'json_responses': json_responses,
                'api_candidates': api_candidates
            }
            
            with open('api_discovery.json', 'w', encoding='utf-8') as f:
                json.dump(discovery_data, f, indent=2, ensure_ascii=False)
            
            logging.info("\n💾 Результаты сохранены в api_discovery.json")
        
        return api_candidates if api_candidates else json_responses
    
    except Exception as e:
        logging.error(f"❌ Ошибка обнаружения API: {e}")
        return []


def extract_ids_from_json(data):
    """
    Извлекает ID новостей из JSON ответа API
    Поддерживает различные структуры данных
    
    Args:
        data: JSON данные (dict или list)
    
    Returns:
        list: Список ID новостей (незакрепленных)
    """
    notice_ids = []
    
    try:
        # Вариант 1: data.data.list[] (наиболее вероятный для Upbit)
        if isinstance(data, dict) and 'data' in data:
            if isinstance(data['data'], dict) and 'list' in data['data']:
                items = data['data']['list']
                for item in items:
                    # Проверяем закреплённость
                    is_pinned = item.get('fixed', False) or item.get('pinned', False) or item.get('is_pinned', False)
                    if not is_pinned:
                        notice_id = item.get('id') or item.get('notice_id') or item.get('noticeId')
                        if notice_id:
                            notice_ids.append(int(notice_id))
                
                if notice_ids:
                    logging.info(f"✅ Структура: data.data.list[] - найдено {len(notice_ids)} ID")
                    return notice_ids
        
        # Вариант 2: data.notices[]
        if isinstance(data, dict) and 'notices' in data:
            items = data['notices']
            for item in items:
                is_pinned = item.get('fixed', False) or item.get('pinned', False)
                if not is_pinned:
                    notice_id = item.get('id') or item.get('notice_id')
                    if notice_id:
                        notice_ids.append(int(notice_id))
            
            if notice_ids:
                logging.info(f"✅ Структура: data.notices[] - найдено {len(notice_ids)} ID")
                return notice_ids
        
        # Вариант 3: data.data[] (прямой массив)
        if isinstance(data, dict) and 'data' in data and isinstance(data['data'], list):
            for item in data['data']:
                is_pinned = item.get('fixed', False) or item.get('pinned', False)
                if not is_pinned:
                    notice_id = item.get('id') or item.get('notice_id')
                    if notice_id:
                        notice_ids.append(int(notice_id))
            
            if notice_ids:
                logging.info(f"✅ Структура: data.data[] - найдено {len(notice_ids)} ID")
                return notice_ids
        
        # Вариант 4: data.list[]
        if isinstance(data, dict) and 'list' in data:
            for item in data['list']:
                is_pinned = item.get('fixed', False) or item.get('pinned', False)
                if not is_pinned:
                    notice_id = item.get('id') or item.get('notice_id')
                    if notice_id:
                        notice_ids.append(int(notice_id))
            
            if notice_ids:
                logging.info(f"✅ Структура: data.list[] - найдено {len(notice_ids)} ID")
                return notice_ids
        
        # Вариант 5: Прямой массив
        if isinstance(data, list):
            for item in data:
                is_pinned = item.get('fixed', False) or item.get('pinned', False)
                if not is_pinned:
                    notice_id = item.get('id') or item.get('notice_id')
                    if notice_id:
                        notice_ids.append(int(notice_id))
            
            if notice_ids:
                logging.info(f"✅ Структура: прямой массив - найдено {len(notice_ids)} ID")
                return notice_ids
        
        # Если ничего не нашли - показываем структуру для отладки
        logging.warning(f"⚠️ Неизвестная структура JSON")
        if isinstance(data, dict):
            logging.warning(f"   Доступные ключи: {list(data.keys())}")
            # Показываем первый уровень вложенности
            for key, value in list(data.items())[:3]:
                if isinstance(value, dict):
                    logging.warning(f"   {key}: dict с ключами {list(value.keys())[:5]}")
                elif isinstance(value, list):
                    logging.warning(f"   {key}: list длины {len(value)}")
                else:
                    logging.warning(f"   {key}: {type(value).__name__}")
        
    except Exception as e:
        logging.error(f"❌ Ошибка извлечения ID из JSON: {e}")
    
    return notice_ids


def load_known_endpoints():
    """
    Загружает известные API endpoints из api_discovery.json
    
    Returns:
        list: Список URL endpoints (может быть пустым)
    """
    endpoints = []
    try:
        if not os.path.exists('api_discovery.json'):
            return endpoints
        
        with open('api_discovery.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get('url'):
                    endpoints.append(item['url'])
        elif isinstance(data, dict):
            if data.get('api_candidates'):
                endpoints.extend(item['url'] for item in data['api_candidates'] if isinstance(item, dict) and item.get('url'))
            elif data.get('json_responses'):
                endpoints.extend(item['url'] for item in data['json_responses'] if isinstance(item, dict) and item.get('url'))
        
        # Удаляем пустые и дубли
        endpoints = [url for url in endpoints if url]
        endpoints = list(dict.fromkeys(endpoints))
        
        if endpoints:
            logging.info(f"📋 Загружено {len(endpoints)} известных API endpoints")
        else:
            logging.info("📋 Известные API endpoints не обнаружены в файле")
        
        return endpoints
    
    except Exception as e:
        logging.warning(f"⚠️ Ошибка загрузки api_discovery.json: {e}")
        return endpoints


def get_notices_from_api(driver, known_endpoints=None, max_wait=2.0, return_details=False):
    """
    Получает новости через перехват API запросов используя CDP
    
    Args:
        driver: Selenium WebDriver с включенным CDP
        known_endpoints: Список известных API endpoints (опционально)
        max_wait: Максимальное время ожидания API запроса (сек)
        return_details: Возвращать ли дополнительные метрики (dict)
    
    Returns:
        list | tuple: Список ID новостей или (list, details) если return_details=True
    """
    start_time = time.time()
    known_endpoints = known_endpoints or []
    
    try:
        # Загружаем страницу
        page_load_start = time.time()
        driver.get(UPBIT_NOTICE_URL)
        page_load_time = time.time() - page_load_start
        
        logging.info(f"  ⏱️ Загрузка страницы (API): {page_load_time:.3f}s")
        if known_endpoints:
            logging.info(f"  📋 Используем {len(known_endpoints)} известных endpoints для фильтрации")
        
        # Ждём появления API запросов
        wait_start = time.time()
        notices_data = None
        api_url_found = None
        
        while time.time() - wait_start < max_wait:
            try:
                logs = driver.get_log('performance')
                
                for log in logs:
                    try:
                        message = json.loads(log['message'])
                        msg_data = message.get('message', {})
                        method = msg_data.get('method', '')
                        
                        if method == 'Network.responseReceived':
                            params = msg_data.get('params', {})
                            response = params.get('response', {})
                            url = response.get('url', '')
                            mime_type = response.get('mimeType', '')
                            request_id = params.get('requestId', '')
                            
                            # Проверяем, это ли наш API endpoint
                            url_lower = url.lower()
                            is_json = 'json' in mime_type.lower() or 'application' in mime_type.lower()
                            is_notice_api = any(keyword in url_lower for keyword in ['notice', 'announcement', 'board', 'list'])
                            
                            # Если есть известные endpoints - проверяем их
                            if known_endpoints:
                                is_notice_api = is_notice_api or any(endpoint in url for endpoint in known_endpoints)
                            
                            if is_json and is_notice_api:
                                # Нашли API запрос! Получаем тело ответа
                                try:
                                    body_response = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                                    body_text = body_response.get('body', '')
                                    
                                    if body_text:
                                        # Парсим JSON
                                        notices_data = json.loads(body_text)
                                        api_url_found = url
                                        logging.info(f"✅ API запрос перехвачен: {url[:120]}...")
                                        break
                                
                                except Exception:
                                    # Тело ответа может быть недоступно - пропускаем
                                    continue
                    
                    except (json.JSONDecodeError, KeyError):
                        continue
                
                if notices_data:
                    break
                
                time.sleep(0.05)  # Проверяем каждые 50ms
            
            except Exception as poll_error:
                logging.debug(f"Ошибка при опросе логов: {poll_error}")
                time.sleep(0.05)
        
        wait_time = time.time() - wait_start
        
        if notices_data:
            # Парсим JSON и извлекаем ID
            parse_start = time.time()
            notice_ids = extract_ids_from_json(notices_data)
            parse_time = time.time() - parse_start
            
            total_time = time.time() - start_time
            
            if notice_ids:
                logging.info(f"  ⏱️ API запрос: {wait_time:.3f}s")
                logging.info(f"  ⏱️ Парсинг JSON: {parse_time:.3f}s")
                logging.info(f"✅ Найдено {len(notice_ids)} новостей (strategy: API)")
                logging.info(f"🔢 ID: {notice_ids[:5]}{'...' if len(notice_ids) > 5 else ''}")
                logging.info(f"⚡ API MODE: Load {page_load_time:.3f}s + API {wait_time:.3f}s + Parse {parse_time:.3f}s = {total_time:.3f}s")
                
                details = {
                    "endpoint": api_url_found,
                    "page_load_time": page_load_time,
                    "wait_time": wait_time,
                    "parse_time": parse_time,
                    "total_time": total_time,
                }
                
                return (notice_ids, details) if return_details else notice_ids
            else:
                logging.warning("⚠️ API перехвачен, но ID не извлечены (неизвестная структура)")
                logging.warning("   → Fallback на HTML парсинг")
                return (None, None) if return_details else None
        else:
            elapsed = time.time() - start_time
            logging.warning(f"⚠️ API endpoint не найден за {elapsed:.3f}s")
            logging.warning("   → Fallback на HTML парсинг")
            return (None, None) if return_details else None
    
    except Exception as e:
        elapsed = time.time() - start_time
        logging.error(f"❌ Ошибка перехвата API ({elapsed:.3f}s): {e}")
        logging.warning("   → Fallback на HTML парсинг")
        return (None, None) if return_details else None


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


def get_all_notice_ids_with_api(driver, known_endpoints=None, use_cdp=True):
    """
    Получает список ID новостей, пытаясь сначала использовать API, затем HTML fallback
    
    Args:
        driver: Selenium WebDriver
        known_endpoints: Список известных API endpoints
        use_cdp: Использовать ли CDP API (если False - только HTML)
    
    Returns:
        tuple: (notice_ids: list, method: str, timings: dict)
    """
    start_time = time.time()
    
    # Пытаемся API если CDP включен
    if use_cdp:
        try:
            api_result, api_details = get_notices_from_api(
                driver,
                known_endpoints=known_endpoints,
                max_wait=2.0,
                return_details=True
            )
            if api_result:
                total_time = api_details.get("total_time", time.time() - start_time)
                return api_result, "API", {"total": total_time, "api": api_details}
            else:
                logging.warning("⚠️ API не вернул результаты, выполняем HTML fallback")
        except Exception as e:
            logging.warning(f"⚠️ Ошибка API: {e}, выполняем HTML fallback")
    else:
        logging.info("ℹ️ CDP отключен, используем HTML парсинг")
    
    # HTML fallback с измерением времени
    try:
        page_load_start = time.time()
        driver.get(UPBIT_NOTICE_URL)
        page_load_time = time.time() - page_load_start
        logging.info(f"  ⏱️ Загрузка страницы (HTML): {page_load_time:.3f}s")
    except Exception as load_error:
        logging.error(f"❌ Ошибка загрузки страницы для HTML fallback: {load_error}")
        return [], "FAILED", {"total": time.time() - start_time}
    
    # БЫСТРАЯ ПРОВЕРКА: новости уже есть? (используем те же fallback стратегии)
    wait_start = time.time()
    quick_check_start = time.time()
    try:
        count = driver.execute_script("""
            // Стратегия 1: Точный селектор с ?id=
            let count = document.querySelectorAll('a[href*="/service_center/notice?id="]').length;
            
            // Стратегия 2: Любые ссылки с notice
            if (count === 0) {
                count = document.querySelectorAll('a[href*="/service_center/notice"]').length;
            }
            
            // Стратегия 3: Ссылки в таблице
            if (count === 0) {
                count = document.querySelectorAll('tr a[href*="notice"]').length;
            }
            
            // Стратегия 4: Любые ссылки с id=
            if (count === 0) {
                count = document.querySelectorAll('a[href*="id="]').length;
            }
            
            return count;
        """)
        quick_check_time = (time.time() - quick_check_start) * 1000
        
        if count > 0:
            # Новости УЖЕ ЕСТЬ! Не ждём дополнительно
            wait_time = time.time() - wait_start
            logging.info(f"⚡ Новости в HTML сразу после refresh ({quick_check_time:.0f}ms) - пропускаем ожидание")
        else:
            # Ждём появления
            logging.info(f"⏳ Новости не найдены сразу ({quick_check_time:.0f}ms) - ждём...")
            notices_appeared = wait_for_notices_js(driver, max_wait=0.3)
            wait_time = time.time() - wait_start
            
            if not notices_appeared:
                logging.warning(f"  ⚠️ Новости не появились за 0.3s")
    except Exception as check_error:
        # Если быстрая проверка не сработала, используем обычное ожидание
        logging.debug(f"Быстрая проверка не удалась: {check_error}, используем обычное ожидание")
        notices_appeared = wait_for_notices_js(driver, max_wait=0.3)
        wait_time = time.time() - wait_start
    
    logging.info(f"  ⏱️ Ожидание новостей (HTML): {wait_time:.3f}s")
    
    parse_start = time.time()
    notice_ids = get_all_notice_ids(driver)
    parse_time = time.time() - parse_start
    
    total_time = time.time() - start_time
    html_details = {
        "page_load": page_load_time,
        "wait": wait_time,
        "parse": parse_time,
    }
    
    if notice_ids:
        logging.info(f"✅ HTML MODE: Получено {len(notice_ids)} ID за {total_time:.3f}s")
    
    return notice_ids, "HTML", {"total": total_time, "html": html_details}


def main():
    logging.info("🚀 Upbit Notice Bot запущен")
    logging.info("")
    
    # CDP API отключён - используем только HTML парсинг
    known_endpoints = []
    use_cdp = False  # CDP API временно отключён
    
    logging.info("📡 Режим: ОПТИМИЗИРОВАННЫЙ HTML ПАРСИНГ")
    logging.info("  ✓ CDP API отключён (временно)")
    logging.info("  ✓ Прямой HTML парсинг")
    logging.info("  🎯 ЦЕЛЕВАЯ СКОРОСТЬ: < 1.5 секунды")
    logging.info("")
    logging.info("🔄 Интервал проверки: 1-2 секунды")
    logging.info("")
    logging.info("⚡ ОПТИМИЗАЦИИ:")
    logging.info("  ✓ Selenium headless Chrome с STEALTH")
    logging.info("  ✓ Отключены изображения, CSS, media")
    logging.info("  ✓ page_load_strategy='eager'")
    logging.info("  ✓ Быстрая проверка сразу после refresh")
    logging.info("  ✓ Умное ожидание (polling 20ms, max 0.3s)")
    logging.info("  ✓ Быстрый HTML парсинг")
    logging.info("  ✓ Автодиагностика при ошибках")
    logging.info("  ✓ Детальные метрики на каждом этапе")
    logging.info("")
    
    # Инициализация драйвера без CDP (только HTML парсинг)
    driver = init_driver(enable_cdp=use_cdp)
    if not driver:
        logging.error("❌ Не удалось запустить браузер")
        return
    
    # CDP discovery отключён (use_cdp=False)
    # Код оставлен для будущего использования
    if use_cdp and not known_endpoints:
        logging.info("🔍 Запускаем автоматическое обнаружение API endpoints...")
        try:
            discover_api_endpoints(driver, save_to_file=True)
            known_endpoints = load_known_endpoints()
            if known_endpoints:
                logging.info(f"📡 Обнаружено и загружено {len(known_endpoints)} endpoints")
            else:
                logging.warning("⚠️ API endpoints не обнаружены, используем HTML fallback")
        except Exception as discovery_error:
            logging.warning(f"⚠️ Ошибка обнаружения API: {discovery_error}")
    
    # Переменная для отслеживания 429 ошибок
    rate_limit_backoff = 0  # Дополнительная задержка при 429
    last_429_time = None
    
    try:
        # Первая загрузка с подробным логированием времени
        logging.info("📡 Подключаемся к Upbit...")
        
        cycle_start = time.time()
        
        # Используем HTML парсинг (CDP отключён)
        all_ids, method, timings = get_all_notice_ids_with_api(driver, known_endpoints=known_endpoints, use_cdp=use_cdp)
        
        # Итоговое время всего цикла
        total_cycle_time = time.time() - cycle_start
        
        logging.info(f"⏱️ ━━━ ИТОГО ЦИКЛ: {total_cycle_time:.3f}s ━━━")
        logging.info(f"   Strategy: {method}")
        
        # Оценка общей производительности (HTML режим)
        if total_cycle_time < 1.0:
            logging.info("✅ ⚡ ОТЛИЧНО: Полный цикл < 1 сек!")
        elif total_cycle_time < 1.5:
            logging.info("✅ ХОРОШО: Полный цикл < 1.5 сек")
        elif total_cycle_time < 2.0:
            logging.info("✅ ПРИЕМЛЕМО: Полный цикл < 2 сек")
        else:
            logging.warning(f"⚠️ МЕДЛЕННО: Полный цикл {total_cycle_time:.3f} сек")
        
        # Показываем детальные метрики HTML парсинга
        if method == "HTML" and isinstance(timings, dict):
            html_info = timings.get("html", {})
            if html_info:
                logging.info(
                    "     ⏱️ Load {0:.3f}s | Wait {1:.3f}s | Parse {2:.3f}s".format(
                        html_info.get("page_load", 0.0),
                        html_info.get("wait", 0.0),
                        html_info.get("parse", 0.0)
                    )
                )
        
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
                    
                    all_ids, method, timings = get_all_notice_ids_with_api(driver, known_endpoints=known_endpoints, use_cdp=use_cdp)
                    total_cycle_time = time.time() - cycle_start
                    
                    logging.info(f"  ⏱️ ━━━ ИТОГО ЦИКЛ: {total_cycle_time:.3f}s ━━━")
                    logging.info(f"     Strategy: {method}")
                    
                    # HTML режим - показываем детальные метрики
                    if method == "HTML":
                        html_info = timings.get("html", {}) if isinstance(timings, dict) else {}
                        logging.info(
                            "     ⏱️ Load {0:.3f}s | Wait {1:.3f}s | Parse {2:.3f}s".format(
                                html_info.get("page_load", 0.0),
                                html_info.get("wait", 0.0),
                                html_info.get("parse", 0.0)
                            )
                        )
                        # Оценка производительности
                        if total_cycle_time < 1.0:
                            logging.info("  ⚡ ОТЛИЧНО: < 1 сек!")
                        elif total_cycle_time < 1.5:
                            logging.info("  ✅ ХОРОШО: < 1.5 сек")
                        elif total_cycle_time < 2.0:
                            logging.info("  ✅ ПРИЕМЛЕМО: < 2 сек")
                        else:
                            logging.warning(f"  ⚠️ МЕДЛЕННО: {total_cycle_time:.3f} сек")
                    else:
                        logging.error(f"  ❌ {method} MODE: Получено за {total_cycle_time:.3f}s")
                    
                    # Сбрасываем backoff если цикл успешен
                    if rate_limit_backoff > 0:
                        logging.info("✅ Цикл успешен, сбрасываем backoff")
                        rate_limit_backoff = 0
                        last_429_time = None
                    
                except TimeoutException:
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
                    
                    driver = init_driver(enable_cdp=use_cdp)
                    if not driver:
                        logging.error("❌ Не удалось переинициализировать браузер, останавливаемся")
                        break
                    
                    # Получаем актуальный max_id с новым драйвером
                    reloaded_ids, method, timings = get_all_notice_ids_with_api(driver, known_endpoints=known_endpoints, use_cdp=use_cdp)
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
