#!/usr/bin/env python3
"""
Быстрый тест JS парсера
"""

import sys
import time
import logging
from main import init_driver, get_all_notice_ids, UPBIT_NOTICE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

def main():
    logging.info("🚀 Быстрый тест JS парсера")
    
    # Инициализация драйвера
    logging.info("🌐 Инициализация драйвера...")
    driver = init_driver(enable_cdp=False)
    
    if not driver:
        logging.error("❌ Не удалось инициализировать драйвер")
        return 1
    
    try:
        # Загрузка страницы
        logging.info(f"📄 Загрузка {UPBIT_NOTICE_URL}")
        driver.get(UPBIT_NOTICE_URL)
        time.sleep(2)  # Даем странице полностью загрузиться
        
        # Парсинг
        logging.info("\n📊 Запуск парсера...")
        notice_ids = get_all_notice_ids(driver)
        
        if notice_ids:
            logging.info(f"\n✅ УСПЕХ: Найдено {len(notice_ids)} новостей")
            return 0
        else:
            logging.error("\n❌ ПРОВАЛ: Новости не найдены")
            return 1
        
    except Exception as e:
        logging.error(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        driver.quit()

if __name__ == "__main__":
    sys.exit(main())
