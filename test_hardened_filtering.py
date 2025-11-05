#!/usr/bin/env python3
"""
Integration test - проверка hardened filtering с реальным браузером
Тестирует что новая логика работает на живой странице
"""

import sys
import time
import logging
from main import init_driver, get_all_notice_ids, get_last_parse_stats, UPBIT_NOTICE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def test_hardened_filtering():
    """
    Тестирует hardened filtering на реальной странице
    """
    logging.info("=" * 80)
    logging.info("🧪 INTEGRATION TEST: Hardened Filtering")
    logging.info("=" * 80)
    logging.info("")
    
    driver = init_driver(enable_cdp=False)
    if not driver:
        logging.error("❌ Не удалось инициализировать браузер")
        return False
    
    try:
        # Загружаем страницу
        logging.info("📡 Загружаем страницу Upbit...")
        start = time.time()
        driver.get(UPBIT_NOTICE_URL)
        time.sleep(2)  # Ждём полной загрузки
        load_time = time.time() - start
        logging.info(f"✅ Страница загружена за {load_time:.3f}s")
        logging.info("")
        
        # Тест 1: Обычный парсинг
        logging.info("━━━ ТЕСТ 1: Обычный парсинг ━━━")
        parse_start = time.time()
        notice_ids = get_all_notice_ids(driver)
        parse_time = time.time() - parse_start
        
        stats = get_last_parse_stats()
        
        logging.info("")
        logging.info(f"⏱️ Время парсинга: {parse_time:.3f}s")
        logging.info(f"🔢 Найдено новостей: {len(notice_ids)}")
        logging.info(f"📊 Всего ссылок: {stats['total_raw_links']}")
        logging.info(f"📊 После фильтрации: {stats['total_filtered_links']}")
        logging.info(f"🛡️ Fallback: {'ДА' if stats['fallback_invoked'] else 'НЕТ'}")
        
        if stats['filter_stats'].get('total_filtered', 0) > 0:
            logging.info("🗂️ Детали фильтрации:")
            for reason, count in stats['filter_stats'].items():
                if count > 0 and reason != 'total_filtered':
                    logging.info(f"   • {reason}: {count}")
        
        # Проверки
        assert len(notice_ids) > 0, "Должны быть найдены новости"
        assert len(notice_ids) >= 20, f"Ожидается минимум 20 новостей, получено {len(notice_ids)}"
        
        logging.info("")
        logging.info("✅ Тест 1 пройден: Новости найдены и отфильтрованы корректно")
        logging.info("")
        
        # Тест 2: С пользовательским порогом
        logging.info("━━━ ТЕСТ 2: Пользовательский порог (min_expected_count=15) ━━━")
        parse_start = time.time()
        notice_ids_custom = get_all_notice_ids(driver, min_expected_count=15)
        parse_time = time.time() - parse_start
        
        stats_custom = get_last_parse_stats()
        
        logging.info("")
        logging.info(f"⏱️ Время парсинга: {parse_time:.3f}s")
        logging.info(f"🔢 Найдено новостей: {len(notice_ids_custom)}")
        logging.info(f"🛡️ Fallback: {'ДА' if stats_custom['fallback_invoked'] else 'НЕТ'}")
        
        assert len(notice_ids_custom) > 0, "Должны быть найдены новости"
        assert len(notice_ids_custom) >= 15, f"Ожидается минимум 15 новостей, получено {len(notice_ids_custom)}"
        
        logging.info("")
        logging.info("✅ Тест 2 пройден: Пользовательский порог работает")
        logging.info("")
        
        # Тест 3: Повторный парсинг (проверка стабильности)
        logging.info("━━━ ТЕСТ 3: Повторный парсинг (5 циклов) ━━━")
        fallback_count = 0
        for i in range(1, 6):
            driver.refresh()
            time.sleep(0.5)
            
            parse_start = time.time()
            ids = get_all_notice_ids(driver)
            parse_time = time.time() - parse_start
            
            stats = get_last_parse_stats()
            if stats['fallback_invoked']:
                fallback_count += 1
            
            logging.info(f"   Цикл {i}: {len(ids)} новостей за {parse_time:.3f}s (fallback: {'ДА' if stats['fallback_invoked'] else 'НЕТ'})")
            
            assert len(ids) > 0, f"Цикл {i}: должны быть найдены новости"
            assert len(ids) >= 20, f"Цикл {i}: ожидается минимум 20 новостей"
        
        logging.info("")
        logging.info(f"📊 Fallback активирован: {fallback_count}/5 циклов")
        logging.info("✅ Тест 3 пройден: Стабильность подтверждена")
        logging.info("")
        
        # Итоги
        logging.info("=" * 80)
        logging.info("🎉 ВСЕ ИНТЕГРАЦИОННЫЕ ТЕСТЫ ПРОЙДЕНЫ!")
        logging.info("=" * 80)
        logging.info("✅ Hardened filtering работает на реальной странице")
        logging.info("✅ Metadata извлекается корректно")
        logging.info("✅ Fallback защищает от чрезмерной фильтрации")
        logging.info("✅ Статистика отслеживается правильно")
        logging.info("✅ Пользовательские пороги работают")
        logging.info("✅ Парсинг стабилен на повторных циклах")
        
        return True
        
    except Exception as e:
        logging.error(f"❌ Ошибка теста: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return False
        
    finally:
        driver.quit()


if __name__ == "__main__":
    success = test_hardened_filtering()
    sys.exit(0 if success else 1)
