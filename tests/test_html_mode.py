#!/usr/bin/env python3
"""
Тест для проверки работы HTML режима (CDP отключён)
Проверяет, что бот использует только HTML парсинг и достигает целевой скорости 1.5-2 сек
"""

import time
import logging
from main import init_driver, get_all_notice_ids_with_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def test_html_mode():
    """Тест HTML режима"""
    logging.info("=" * 60)
    logging.info("ТЕСТ: HTML РЕЖИМ (CDP ОТКЛЮЧЁН)")
    logging.info("=" * 60)
    
    # Инициализация драйвера без CDP
    logging.info("\n1. Инициализация драйвера (enable_cdp=False)...")
    driver = init_driver(enable_cdp=False)
    
    if not driver:
        logging.error("❌ Не удалось инициализировать драйвер")
        return False
    
    logging.info("✅ Драйвер инициализирован (без CDP)")
    
    try:
        # Загружаем страницу и парсим новости
        logging.info("\n2. Загрузка новостей (HTML режим)...")
        start_time = time.time()
        
        all_ids, method, timings = get_all_notice_ids_with_api(
            driver,
            known_endpoints=[],
            use_cdp=False
        )
        
        total_time = time.time() - start_time
        
        # Проверяем результаты
        logging.info("\n" + "=" * 60)
        logging.info("РЕЗУЛЬТАТЫ ТЕСТА")
        logging.info("=" * 60)
        
        if not all_ids:
            logging.error("❌ Не удалось получить ID новостей")
            return False
        
        logging.info(f"✅ Получено {len(all_ids)} новостей")
        logging.info(f"🔢 ID: {all_ids[:5]}{'...' if len(all_ids) > 5 else ''}")
        logging.info(f"📊 Strategy: {method}")
        
        if method != "HTML":
            logging.error(f"❌ Ожидался HTML режим, получен: {method}")
            return False
        
        logging.info(f"✅ Strategy: HTML (как и ожидалось)")
        
        # Проверяем производительность
        logging.info(f"\n⏱️ ВРЕМЯ ЦИКЛА: {total_time:.3f}s")
        
        if isinstance(timings, dict) and "html" in timings:
            html_info = timings["html"]
            logging.info(
                "   Load: {0:.3f}s | Wait: {1:.3f}s | Parse: {2:.3f}s".format(
                    html_info.get("page_load", 0.0),
                    html_info.get("wait", 0.0),
                    html_info.get("parse", 0.0)
                )
            )
        
        # Оценка производительности
        if total_time < 1.0:
            logging.info("⚡ ОТЛИЧНО: < 1 сек!")
            status = "EXCELLENT"
        elif total_time < 1.5:
            logging.info("✅ ХОРОШО: < 1.5 сек")
            status = "GOOD"
        elif total_time < 2.0:
            logging.info("✅ ПРИЕМЛЕМО: < 2 сек (целевая скорость)")
            status = "ACCEPTABLE"
        else:
            logging.warning(f"⚠️ МЕДЛЕННО: {total_time:.3f} сек (целевая: < 2 сек)")
            status = "SLOW"
        
        # Итоговая оценка
        logging.info("\n" + "=" * 60)
        logging.info("ИТОГОВАЯ ОЦЕНКА")
        logging.info("=" * 60)
        
        if status in ["EXCELLENT", "GOOD", "ACCEPTABLE"]:
            logging.info("✅ ТЕСТ ПРОЙДЕН")
            logging.info(f"   - Режим: HTML (CDP отключён)")
            logging.info(f"   - Скорость: {status}")
            logging.info(f"   - Время: {total_time:.3f}s")
            logging.info(f"   - Новости: {len(all_ids)} шт")
            return True
        else:
            logging.error("❌ ТЕСТ НЕ ПРОЙДЕН")
            logging.error(f"   - Время цикла: {total_time:.3f}s > 2.0s")
            return False
        
    except Exception as e:
        logging.error(f"❌ Ошибка теста: {e}", exc_info=True)
        return False
    
    finally:
        try:
            driver.quit()
            logging.info("\n✅ Драйвер закрыт")
        except:
            pass


if __name__ == "__main__":
    success = test_html_mode()
    exit(0 if success else 1)
