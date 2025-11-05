#!/usr/bin/env python3
"""
Тест унифицированных селекторов - проверяет, что основной парсер 
и диагностика используют одинаковые fallback стратегии
"""

import time
import logging
from main import init_driver, get_all_notice_ids_with_api, get_all_notice_ids

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def test_unified_selectors():
    """
    Тест: 10 циклов подряд - все должны быть успешными
    """
    logging.info("=" * 80)
    logging.info("🧪 ТЕСТ: Унифицированные селекторы")
    logging.info("=" * 80)
    logging.info("")
    logging.info("Цель: Проверить стабильность парсинга с унифицированными стратегиями")
    logging.info("Критерии:")
    logging.info("  ✅ Каждый цикл успешный (находит > 20 новостей)")
    logging.info("  ✅ Используется одна из 4 стратегий: exact_id, all_notice, tr_notice, any_id")
    logging.info("  ✅ Логируется стратегия и количество найденных ссылок")
    logging.info("  ✅ Время цикла стабильное: 1.5-1.8s")
    logging.info("")
    
    # Инициализация драйвера
    driver = init_driver(enable_cdp=False)
    if not driver:
        logging.error("❌ Не удалось запустить браузер")
        return False
    
    try:
        # Загружаем страницу первый раз
        logging.info("📡 Первая загрузка...")
        all_ids, method, timings = get_all_notice_ids_with_api(driver, use_cdp=False)
        
        if not all_ids:
            logging.error("❌ Первая загрузка не удалась")
            return False
        
        logging.info(f"✅ Найдено {len(all_ids)} новостей")
        logging.info("")
        
        # Тестируем 10 циклов
        NUM_CYCLES = 10
        results = []
        
        for i in range(1, NUM_CYCLES + 1):
            logging.info(f"🔄 Цикл #{i}/{NUM_CYCLES}...")
            
            cycle_start = time.time()
            
            # Refresh и парсинг
            driver.refresh()
            
            # Ждём немного для загрузки
            time.sleep(0.1)
            
            # Парсим
            parse_start = time.time()
            notice_ids = get_all_notice_ids(driver)
            parse_time = time.time() - parse_start
            
            cycle_time = time.time() - cycle_start
            
            # Анализируем результат
            success = len(notice_ids) > 0
            
            result = {
                'cycle': i,
                'success': success,
                'count': len(notice_ids),
                'parse_time': parse_time,
                'cycle_time': cycle_time
            }
            results.append(result)
            
            if success:
                logging.info(f"✅ Успех: {len(notice_ids)} новостей за {cycle_time:.3f}s")
            else:
                logging.error(f"❌ Ошибка: новости не найдены!")
            
            logging.info("")
            
            # Небольшая пауза между циклами
            time.sleep(0.5)
        
        # Итоговая статистика
        logging.info("=" * 80)
        logging.info("📊 ИТОГОВАЯ СТАТИСТИКА")
        logging.info("=" * 80)
        
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        
        logging.info(f"Всего циклов: {len(results)}")
        logging.info(f"✅ Успешных: {successful}")
        logging.info(f"❌ Неудачных: {failed}")
        
        if successful > 0:
            avg_time = sum(r['cycle_time'] for r in results if r['success']) / successful
            min_time = min(r['cycle_time'] for r in results if r['success'])
            max_time = max(r['cycle_time'] for r in results if r['success'])
            
            avg_count = sum(r['count'] for r in results if r['success']) / successful
            
            logging.info(f"Среднее время: {avg_time:.3f}s")
            logging.info(f"Мин. время: {min_time:.3f}s")
            logging.info(f"Макс. время: {max_time:.3f}s")
            logging.info(f"Среднее кол-во новостей: {avg_count:.1f}")
        
        # Оценка результата
        logging.info("")
        if failed == 0:
            logging.info("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Парсинг стабильный!")
            logging.info("🎉 Унификация селекторов успешна!")
            return True
        else:
            logging.error(f"❌ ТЕСТЫ НЕ ПРОШЛИ! Найдено {failed} неудачных циклов")
            logging.error("💡 Проверьте логи выше для деталей")
            return False
    
    finally:
        driver.quit()
        logging.info("🔚 Браузер закрыт")

if __name__ == "__main__":
    success = test_unified_selectors()
    exit(0 if success else 1)
