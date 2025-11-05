#!/usr/bin/env python3
"""
Тест исправления JS парсера для соответствия диагностике

Критерии приёмки:
1. ✅ JavaScript парсер находит новости с первой попытки
2. ✅ Strategy: exact_id (основной селектор)
3. ✅ Найдено 22-23 новости
4. ✅ Время цикла < 2 секунды
5. ✅ Нет запуска диагностики при нормальной работе
6. ✅ Тест: 10 циклов подряд - все успешные
7. ✅ В логах видны примеры найденных новостей
"""

import sys
import time
import logging
from main import init_driver, get_all_notice_ids_with_api, UPBIT_NOTICE_URL

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

def test_single_cycle(driver, cycle_num):
    """Тестирует один цикл парсинга"""
    logging.info(f"\n{'='*60}")
    logging.info(f"ЦИКЛ {cycle_num}")
    logging.info(f"{'='*60}")
    
    start = time.time()
    
    try:
        notice_ids, method, timings = get_all_notice_ids_with_api(driver, use_cdp=False)
        elapsed = time.time() - start
        
        if not notice_ids:
            logging.error(f"❌ ЦИКЛ {cycle_num}: Новости не найдены!")
            return False
        
        # Проверяем критерии
        total_time = timings.get('total', elapsed)
        
        logging.info(f"\n📊 РЕЗУЛЬТАТЫ ЦИКЛА {cycle_num}:")
        logging.info(f"  ✅ Найдено новостей: {len(notice_ids)}")
        logging.info(f"  ✅ Метод: {method}")
        logging.info(f"  ✅ Время цикла: {total_time:.3f}s")
        
        # Критерии приёмки
        success = True
        
        if len(notice_ids) < 20:
            logging.warning(f"  ⚠️ Найдено мало новостей: {len(notice_ids)} < 20")
            success = False
        else:
            logging.info(f"  ✅ Количество новостей OK: {len(notice_ids)} >= 20")
        
        if total_time >= 2.0:
            logging.warning(f"  ⚠️ Медленно: {total_time:.3f}s >= 2.0s")
            success = False
        else:
            logging.info(f"  ✅ Скорость OK: {total_time:.3f}s < 2.0s")
        
        return success
        
    except Exception as e:
        logging.error(f"❌ ЦИКЛ {cycle_num}: Ошибка - {e}")
        import traceback
        traceback.print_exc()
        return False

def test_multiple_cycles(driver, num_cycles=10):
    """Тестирует несколько циклов подряд"""
    logging.info(f"\n🧪 Запуск теста: {num_cycles} циклов подряд")
    
    results = []
    successful = 0
    failed = 0
    
    for i in range(1, num_cycles + 1):
        success = test_single_cycle(driver, i)
        results.append(success)
        
        if success:
            successful += 1
        else:
            failed += 1
        
        # Небольшая пауза между циклами
        if i < num_cycles:
            time.sleep(1.0)
    
    # Итоговая статистика
    logging.info(f"\n{'='*60}")
    logging.info("📊 ИТОГОВАЯ СТАТИСТИКА")
    logging.info(f"{'='*60}")
    logging.info(f"✅ Успешных циклов: {successful}/{num_cycles}")
    logging.info(f"❌ Неудачных циклов: {failed}/{num_cycles}")
    
    if failed == 0:
        logging.info("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return True
    else:
        logging.error(f"❌ ТЕСТЫ НЕ ПРОЙДЕНЫ: {failed} неудач")
        return False

def main():
    logging.info("🚀 Тест исправления JS парсера")
    logging.info("="*60)
    
    # Инициализация драйвера
    logging.info("🌐 Инициализация драйвера...")
    driver = init_driver(enable_cdp=False)
    
    if not driver:
        logging.error("❌ Не удалось инициализировать драйвер")
        return 1
    
    try:
        # Первая загрузка страницы
        logging.info(f"📄 Загрузка {UPBIT_NOTICE_URL}")
        driver.get(UPBIT_NOTICE_URL)
        time.sleep(2)
        
        # Запускаем тесты
        success = test_multiple_cycles(driver, num_cycles=10)
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        logging.info("\n⚠️ Тест прерван пользователем")
        return 1
    except Exception as e:
        logging.error(f"❌ Ошибка теста: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        logging.info("\n🔚 Закрытие драйвера...")
        driver.quit()

if __name__ == "__main__":
    sys.exit(main())
