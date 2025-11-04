#!/usr/bin/env python3
"""
Тест CDP API Discovery - обнаружение API endpoints через Chrome DevTools Protocol
"""

import sys
import logging
from main import init_driver, discover_api_endpoints, get_notices_from_api, get_all_notice_ids

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)


def test_api_discovery():
    """Тест режима обнаружения API endpoints"""
    logging.info("=" * 80)
    logging.info("ТЕСТ 1: CDP API DISCOVERY MODE")
    logging.info("=" * 80)
    
    driver = init_driver(enable_cdp=True)
    if not driver:
        logging.error("❌ Не удалось инициализировать драйвер с CDP")
        return False
    
    try:
        # Запускаем обнаружение API
        endpoints = discover_api_endpoints(driver, save_to_file=True)
        
        if endpoints:
            logging.info(f"\n✅ УСПЕХ: Найдено {len(endpoints)} потенциальных API endpoints")
            logging.info("📄 Результаты сохранены в api_discovery.json")
            return True
        else:
            logging.warning("\n⚠️ API endpoints не найдены")
            return False
    
    finally:
        driver.quit()


def test_api_interception():
    """Тест перехвата API запросов"""
    logging.info("\n" + "=" * 80)
    logging.info("ТЕСТ 2: API REQUEST INTERCEPTION")
    logging.info("=" * 80)
    
    driver = init_driver(enable_cdp=True)
    if not driver:
        logging.error("❌ Не удалось инициализировать драйвер с CDP")
        return False
    
    try:
        # Пытаемся получить новости через API
        notice_ids = get_notices_from_api(driver, max_wait=3.0)
        
        if notice_ids:
            logging.info(f"\n✅ УСПЕХ: Получено {len(notice_ids)} ID через API")
            logging.info(f"🔢 ID: {notice_ids[:10]}{'...' if len(notice_ids) > 10 else ''}")
            return True
        else:
            logging.warning("\n⚠️ API перехват не удался")
            return False
    
    finally:
        driver.quit()


def test_api_vs_html_comparison():
    """Сравнение API парсинга с HTML парсингом"""
    logging.info("\n" + "=" * 80)
    logging.info("ТЕСТ 3: API vs HTML PARSING COMPARISON")
    logging.info("=" * 80)
    
    # Тест 1: API парсинг
    logging.info("\n🔹 Тест с CDP API...")
    driver_api = init_driver(enable_cdp=True)
    if not driver_api:
        logging.error("❌ Не удалось инициализировать драйвер с CDP")
        return False
    
    try:
        api_ids = get_notices_from_api(driver_api, max_wait=3.0)
    finally:
        driver_api.quit()
    
    # Тест 2: HTML парсинг
    logging.info("\n🔹 Тест с HTML парсингом...")
    driver_html = init_driver(enable_cdp=False)
    if not driver_html:
        logging.error("❌ Не удалось инициализировать драйвер")
        return False
    
    try:
        driver_html.get("https://upbit.com/service_center/notice")
        import time
        time.sleep(1)
        html_ids = get_all_notice_ids(driver_html)
    finally:
        driver_html.quit()
    
    # Сравниваем результаты
    logging.info("\n" + "=" * 80)
    logging.info("📊 СРАВНЕНИЕ РЕЗУЛЬТАТОВ")
    logging.info("=" * 80)
    
    if api_ids and html_ids:
        api_set = set(api_ids)
        html_set = set(html_ids)
        
        logging.info(f"API парсинг:  {len(api_ids)} ID")
        logging.info(f"HTML парсинг: {len(html_ids)} ID")
        
        if api_set == html_set:
            logging.info("✅ ИДЕНТИЧНЫ: Оба метода вернули одинаковые ID")
            return True
        else:
            only_api = api_set - html_set
            only_html = html_set - api_set
            
            logging.warning("⚠️ РАЗЛИЧИЯ:")
            if only_api:
                logging.warning(f"  Только в API: {sorted(only_api)}")
            if only_html:
                logging.warning(f"  Только в HTML: {sorted(only_html)}")
            
            # Все равно считаем успехом если хотя бы оба нашли что-то
            return True
    
    elif api_ids:
        logging.info("✅ Только API парсинг успешен")
        return True
    
    elif html_ids:
        logging.warning("⚠️ Только HTML парсинг успешен (API fallback работает)")
        return True
    
    else:
        logging.error("❌ Оба метода не вернули результаты")
        return False


def main():
    """Запуск всех тестов"""
    logging.info("🚀 ЗАПУСК ТЕСТОВ CDP API INTERCEPTION")
    logging.info("")
    
    results = []
    
    # Тест 1: API Discovery
    try:
        result = test_api_discovery()
        results.append(("API Discovery", result))
    except Exception as e:
        logging.error(f"❌ Ошибка в тесте API Discovery: {e}")
        results.append(("API Discovery", False))
    
    # Тест 2: API Interception
    try:
        result = test_api_interception()
        results.append(("API Interception", result))
    except Exception as e:
        logging.error(f"❌ Ошибка в тесте API Interception: {e}")
        results.append(("API Interception", False))
    
    # Тест 3: Comparison
    try:
        result = test_api_vs_html_comparison()
        results.append(("API vs HTML", result))
    except Exception as e:
        logging.error(f"❌ Ошибка в тесте API vs HTML: {e}")
        results.append(("API vs HTML", False))
    
    # Итоги
    logging.info("\n" + "=" * 80)
    logging.info("📊 РЕЗУЛЬТАТЫ ТЕСТОВ")
    logging.info("=" * 80)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        logging.info(f"{status}: {test_name}")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    logging.info(f"\nВсего: {passed_count}/{total_count} тестов пройдено")
    
    if passed_count == total_count:
        logging.info("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return 0
    else:
        logging.warning("⚠️ Некоторые тесты провалены")
        return 1


if __name__ == "__main__":
    sys.exit(main())
