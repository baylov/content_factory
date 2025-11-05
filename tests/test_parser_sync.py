#!/usr/bin/env python3
"""
Quick test - проверка что парсер синхронизирован с диагностикой
Запускает 10 циклов для быстрой проверки
"""

import sys
import time
import logging
from main import init_driver, get_all_notice_ids, debug_save_html_and_find_selectors, UPBIT_NOTICE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def test_parser_sync():
    """
    Тестирует что парсер использует ту же логику что и диагностика
    """
    logging.info("=" * 80)
    logging.info("🧪 БЫСТРЫЙ ТЕСТ: Синхронизация парсера с диагностикой")
    logging.info("=" * 80)
    logging.info("")
    
    driver = init_driver(enable_cdp=False)
    if not driver:
        logging.error("❌ Не удалось инициализировать браузер")
        return False
    
    try:
        # Загружаем страницу
        logging.info("📡 Загружаем страницу...")
        driver.get(UPBIT_NOTICE_URL)
        time.sleep(2)
        
        success_count = 0
        fail_count = 0
        
        # Тестируем 10 циклов
        for cycle in range(1, 11):
            logging.info("")
            logging.info(f"━━━ Цикл #{cycle}/10 ━━━")
            
            # Refresh
            driver.refresh()
            time.sleep(0.1)
            
            # Парсинг
            start = time.time()
            notice_ids = get_all_notice_ids(driver)
            elapsed = time.time() - start
            
            # Проверка
            if notice_ids and len(notice_ids) > 0:
                success_count += 1
                logging.info(f"✅ Цикл #{cycle}: {len(notice_ids)} новостей за {elapsed:.3f}s")
            else:
                fail_count += 1
                logging.error(f"❌ Цикл #{cycle}: ПРОВАЛ")
                
                # Запускаем диагностику при провале
                logging.info("💡 Сравниваем с диагностикой...")
                debug_save_html_and_find_selectors(driver)
            
            # Пауза между циклами
            time.sleep(1)
        
        # Итоги
        logging.info("")
        logging.info("=" * 80)
        logging.info("📊 ИТОГИ")
        logging.info("=" * 80)
        logging.info(f"✅ Успешно: {success_count}/10")
        logging.info(f"❌ Провалов: {fail_count}/10")
        
        if fail_count == 0:
            logging.info("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
            return True
        else:
            logging.error(f"❌ Есть провалы: {fail_count}")
            return False
    
    finally:
        driver.quit()


if __name__ == "__main__":
    success = test_parser_sync()
    sys.exit(0 if success else 1)
