#!/usr/bin/env python3
"""
Test script - проверка стабильности парсера на 100 циклов
Цель: 100% успешных циклов без единого падения
"""

import sys
import time
import logging
from main import init_driver, get_all_notice_ids, UPBIT_NOTICE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def test_stability(cycles=100):
    """
    Тестирует стабильность парсера на N циклов
    """
    logging.info("=" * 80)
    logging.info(f"🧪 ТЕСТ СТАБИЛЬНОСТИ: {cycles} ЦИКЛОВ")
    logging.info("=" * 80)
    logging.info("")
    
    driver = init_driver(enable_cdp=False)
    if not driver:
        logging.error("❌ Не удалось инициализировать браузер")
        return False
    
    # Загружаем страницу один раз
    logging.info("📡 Загружаем страницу...")
    driver.get(UPBIT_NOTICE_URL)
    time.sleep(2)
    
    stats = {
        'success': 0,
        'failed': 0,
        'times': [],
        'strategies': {},
        'counts': []
    }
    
    try:
        for cycle in range(1, cycles + 1):
            logging.info("")
            logging.info(f"━━━ Цикл #{cycle}/{cycles} ━━━")
            
            start = time.time()
            
            # Refresh страницы
            driver.refresh()
            time.sleep(0.1)  # Короткая пауза после refresh
            
            # Парсим новости
            notice_ids = get_all_notice_ids(driver)
            
            elapsed = time.time() - start
            
            # Проверяем результат
            if notice_ids and len(notice_ids) > 0:
                stats['success'] += 1
                stats['times'].append(elapsed)
                stats['counts'].append(len(notice_ids))
                
                logging.info(f"✅ Цикл #{cycle}: Успешно - {len(notice_ids)} новостей за {elapsed:.3f}s")
            else:
                stats['failed'] += 1
                logging.error(f"❌ Цикл #{cycle}: ПРОВАЛ - новости не найдены!")
            
            # Короткая пауза между циклами
            time.sleep(1)
    
    except KeyboardInterrupt:
        logging.info("")
        logging.info("⚠️ Тест прерван пользователем")
    
    finally:
        driver.quit()
    
    # === СТАТИСТИКА ===
    logging.info("")
    logging.info("=" * 80)
    logging.info("📊 СТАТИСТИКА")
    logging.info("=" * 80)
    logging.info(f"✅ Успешных циклов: {stats['success']}")
    logging.info(f"❌ Провалов: {stats['failed']}")
    
    if stats['success'] > 0:
        success_rate = (stats['success'] / (stats['success'] + stats['failed'])) * 100
        logging.info(f"📈 Успешность: {success_rate:.1f}%")
        
        avg_time = sum(stats['times']) / len(stats['times'])
        min_time = min(stats['times'])
        max_time = max(stats['times'])
        
        logging.info(f"⏱️ Время парсинга:")
        logging.info(f"   • Среднее: {avg_time:.3f}s")
        logging.info(f"   • Минимум: {min_time:.3f}s")
        logging.info(f"   • Максимум: {max_time:.3f}s")
        
        if stats['counts']:
            avg_count = sum(stats['counts']) / len(stats['counts'])
            min_count = min(stats['counts'])
            max_count = max(stats['counts'])
            
            logging.info(f"🔢 Количество новостей:")
            logging.info(f"   • Среднее: {avg_count:.1f}")
            logging.info(f"   • Минимум: {min_count}")
            logging.info(f"   • Максимум: {max_count}")
    
    logging.info("=" * 80)
    
    # Проверка критериев приёмки
    if stats['failed'] == 0 and stats['success'] == cycles:
        logging.info("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        logging.info(f"✅ {cycles} циклов подряд - ВСЕ успешные")
        return True
    else:
        logging.error("❌ ТЕСТЫ НЕ ПРОЙДЕНЫ!")
        logging.error(f"   Провалов: {stats['failed']}")
        return False


if __name__ == "__main__":
    # По умолчанию 100 циклов, можно указать другое количество
    num_cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    
    success = test_stability(num_cycles)
    sys.exit(0 if success else 1)
