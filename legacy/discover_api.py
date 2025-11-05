#!/usr/bin/env python3
"""
Скрипт для обнаружения API endpoints Upbit
Запускает режим discovery и сохраняет результаты в api_discovery.json
"""

import sys
import logging
from main import init_driver, discover_api_endpoints

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/api_discovery.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)


def main():
    """Запуск режима обнаружения API"""
    logging.info("=" * 80)
    logging.info("🔍 UPBIT API DISCOVERY MODE")
    logging.info("=" * 80)
    logging.info("")
    logging.info("Этот скрипт анализирует сетевые запросы Upbit")
    logging.info("и находит API endpoints для загрузки новостей.")
    logging.info("")
    
    # Инициализируем драйвер с CDP
    driver = init_driver(enable_cdp=True)
    if not driver:
        logging.error("❌ Не удалось инициализировать браузер с CDP")
        return 1
    
    try:
        # Запускаем обнаружение
        endpoints = discover_api_endpoints(driver, save_to_file=True)
        
        if endpoints:
            logging.info("")
            logging.info("=" * 80)
            logging.info("✅ ОБНАРУЖЕНИЕ ЗАВЕРШЕНО")
            logging.info("=" * 80)
            logging.info(f"Найдено {len(endpoints)} потенциальных API endpoints")
            logging.info("📄 Результаты сохранены в api_discovery.json")
            logging.info("")
            logging.info("💡 СЛЕДУЮЩИЙ ШАГ:")
            logging.info("   Проверьте api_discovery.json и используйте найденные endpoints")
            logging.info("   для настройки перехвата API в основном боте.")
            logging.info("")
            return 0
        else:
            logging.warning("")
            logging.warning("=" * 80)
            logging.warning("⚠️ API ENDPOINTS НЕ НАЙДЕНЫ")
            logging.warning("=" * 80)
            logging.warning("Возможные причины:")
            logging.warning("  1. Upbit не использует публичные API для загрузки новостей")
            logging.warning("  2. API запросы выполняются после загрузки страницы")
            logging.warning("  3. Структура сайта изменилась")
            logging.warning("")
            logging.warning("💡 РЕШЕНИЕ:")
            logging.warning("   Бот автоматически использует HTML парсинг как fallback")
            logging.warning("")
            return 0
    
    except Exception as e:
        logging.error(f"❌ Ошибка при обнаружении API: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return 1
    
    finally:
        driver.quit()
        logging.info("🔒 Браузер закрыт")


if __name__ == "__main__":
    sys.exit(main())
