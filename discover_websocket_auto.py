#!/usr/bin/env python3
"""
Исследование WebSocket и Network запросов на странице Upbit (автоматическая версия)
"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

def discover_realtime_endpoints():
    """Находит WebSocket и API endpoints для real-time обновлений"""
    
    chrome_options = Options()
    # Headless режим для автоматического выполнения
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    # Включаем логирование Performance
    chrome_options.set_capability('goog:loggingPrefs', {
        'performance': 'ALL',
        'browser': 'ALL'
    })
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Stealth
    stealth(driver,
        languages=["ko-KR", "ko"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    
    logging.info("="*60)
    logging.info("🔍 ИССЛЕДОВАНИЕ UPBIT REAL-TIME ENDPOINTS")
    logging.info("="*60)
    
    try:
        # Загружаем страницу
        logging.info("\n📡 Загружаем страницу новостей...")
        driver.get('https://upbit.com/service_center/notice')
        
        # Ждём полной загрузки
        logging.info("⏳ Ожидание загрузки (5 секунд)...")
        time.sleep(5)
        
        logging.info("\n🔍 Анализируем сетевые запросы...\n")
        
        # Получаем все Performance logs
        logs = driver.get_log('performance')
        
        websockets = []
        api_endpoints = []
        potential_notice_apis = []
        
        for log in logs:
            try:
                message = json.loads(log['message'])
                method = message.get('message', {}).get('method', '')
                
                # === 1. ПОИСК WEBSOCKET ===
                if method == 'Network.webSocketCreated':
                    params = message['message']['params']
                    ws_url = params.get('url', '')
                    websockets.append(ws_url)
                    logging.info(f"🔌 WebSocket найден: {ws_url}")
                
                # === 2. ПОИСК API ENDPOINTS С JSON ===
                elif method == 'Network.responseReceived':
                    response = message['message']['params']['response']
                    url = response.get('url', '')
                    mime_type = response.get('mimeType', '')
                    status = response.get('status', 0)
                    
                    # Ищем JSON API
                    if ('json' in mime_type or 'application' in mime_type) and status == 200:
                        # Ищем endpoints связанные с notices/announcements
                        if any(keyword in url.lower() for keyword in 
                               ['notice', 'announcement', 'board', 'news', 'feed', 'list']):
                            potential_notice_apis.append({
                                'url': url,
                                'mime': mime_type,
                                'status': status
                            })
                            logging.info(f"📋 Потенциальный API: {url}")
                            logging.info(f"   Type: {mime_type}, Status: {status}")
                        
                        # Все JSON endpoints (для полноты картины)
                        if url not in [x['url'] for x in api_endpoints]:
                            api_endpoints.append({
                                'url': url,
                                'mime': mime_type
                            })
                
            except Exception as e:
                continue
        
        # === ИТОГИ ===
        logging.info("\n" + "="*60)
        logging.info("📊 РЕЗУЛЬТАТЫ ИССЛЕДОВАНИЯ")
        logging.info("="*60)
        
        logging.info(f"\n🔌 WebSocket endpoints: {len(websockets)}")
        if websockets:
            for ws in websockets:
                logging.info(f"   • {ws}")
        else:
            logging.warning("   ⚠️ WebSocket не найден")
        
        logging.info(f"\n📋 API endpoints для новостей: {len(potential_notice_apis)}")
        if potential_notice_apis:
            for api in potential_notice_apis:
                logging.info(f"   • {api['url']}")
                logging.info(f"     Type: {api['mime']}, Status: {api['status']}")
        else:
            logging.warning("   ⚠️ Специфичные API для новостей не найдены")
        
        logging.info(f"\n🌐 Всего JSON endpoints: {len(api_endpoints)}")
        if api_endpoints:
            logging.info("Примеры JSON endpoints:")
            for api in api_endpoints[:5]:  # Показываем первые 5
                logging.info(f"   • {api['url']}")
                logging.info(f"     Type: {api['mime']}")
        
        # === СОХРАНЯЕМ РЕЗУЛЬТАТЫ ===
        results = {
            'websockets': websockets,
            'notice_apis': potential_notice_apis,
            'all_json_apis': api_endpoints
        }
        
        with open('upbit_realtime_discovery.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logging.info("\n💾 Результаты сохранены в upbit_realtime_discovery.json")
        
        # === ДОПОЛНИТЕЛЬНЫЕ ПРОВЕРКИ ===
        logging.info("\n" + "="*60)
        logging.info("🔬 ДОПОЛНИТЕЛЬНЫЕ ПРОВЕРКИ")
        logging.info("="*60)
        
        # Проверка на RSS
        logging.info("\n📡 Проверка RSS feed...")
        rss_urls = [
            'https://upbit.com/service_center/notice/rss',
            'https://upbit.com/rss/notice',
            'https://upbit.com/feed/notices',
            'https://upbit.com/api/notices/rss'
        ]
        
        rss_found = False
        for rss_url in rss_urls:
            try:
                driver.get(rss_url)
                time.sleep(1)
                if 'xml' in driver.page_source.lower() or 'rss' in driver.page_source.lower():
                    logging.info(f"   ✅ RSS найден: {rss_url}")
                    rss_found = True
                    break
            except:
                pass
        
        if not rss_found:
            logging.info("   ⚠️ RSS feed не найден")
        
        # Проверка прямого API
        logging.info("\n📡 Проверка прямого API...")
        api_urls = [
            'https://api.upbit.com/v1/notices',
            'https://api-manager.upbit.com/api/v1/notices',
            'https://upbit.com/api/v1/notices',
            'https://api.upbit.com/v1/announcements'
        ]
        
        api_found = False
        for api_url in api_urls:
            try:
                driver.get(api_url)
                time.sleep(1)
                content = driver.page_source
                if '{' in content and 'notice' in content.lower():
                    logging.info(f"   ✅ API endpoint найден: {api_url}")
                    logging.info(f"      Содержимое: {content[:200]}...")
                    api_found = True
            except:
                pass
        
        if not api_found:
            logging.info("   ⚠️ Прямые API endpoints не найдены")
        
        # === РЕКОМЕНДАЦИИ ===
        logging.info("\n" + "="*60)
        logging.info("💡 РЕКОМЕНДАЦИИ")
        logging.info("="*60)
        
        if websockets:
            logging.info("\n✅ НАЙДЕН WEBSOCKET!")
            logging.info("Рекомендация: Подключиться к WebSocket для мгновенных обновлений")
            logging.info("Ожидаемая скорость: < 0.1 секунды")
        
        if potential_notice_apis:
            logging.info("\n✅ НАЙДЕНЫ API ENDPOINTS!")
            logging.info("Рекомендация: Использовать прямые API запросы вместо HTML парсинга")
            logging.info("Ожидаемая скорость: 0.2-0.5 секунды")
        
        if not websockets and not potential_notice_apis:
            logging.info("\n⚠️ WebSocket и API endpoints не найдены")
            logging.info("Рекомендации:")
            logging.info("1. Текущий Selenium подход уже оптимален (< 1.5s)")
            logging.info("2. Requests не работает из-за JavaScript рендеринга")
            logging.info("3. Рассмотреть оптимизацию текущего парсинга:")
            logging.info("   - Уменьшить время ожидания")
            logging.info("   - Использовать более эффективные селекторы")
            logging.info("   - Минимизировать загрузку ресурсов")
        
        logging.info("\n" + "="*60)
        
    finally:
        driver.quit()
        logging.info("\n✅ Исследование завершено")

if __name__ == '__main__':
    discover_realtime_endpoints()
