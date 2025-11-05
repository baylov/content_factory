#!/usr/bin/env python3
"""
Test script - проверка стабильности парсера на 100 циклов
Цель: 100% успешных циклов без единого падения
"""

import sys
import time
import logging
from main import init_driver, get_all_notice_ids, get_last_parse_stats, UPBIT_NOTICE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def test_stability(cycles=100):
    """
    Тестирует стабильность парсера на N циклов с отслеживанием fallback
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
        'counts': [],
        'fallback_invocations': 0,
        'cycles_with_fallback': [],
        'strategy_1_hits': 0,
        'strategy_1_misses': 0,
        'exact_id_retry_attempts': [],
        'exact_id_retry_times': []
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
            
            # Получаем статистику парсинга
            parse_stats = get_last_parse_stats()
            
            # Проверяем результат
            if notice_ids and len(notice_ids) > 0:
                stats['success'] += 1
                stats['times'].append(elapsed)
                stats['counts'].append(len(notice_ids))
                
                # Отслеживаем Strategy 1 success rate
                strategy_stats = parse_stats.get('strategy_stats', {})
                if strategy_stats.get('exact_id_success', False):
                    stats['strategy_1_hits'] += 1
                else:
                    stats['strategy_1_misses'] += 1
                
                # Отслеживаем retry attempts и timing
                if 'exact_id_attempts' in strategy_stats:
                    stats['exact_id_retry_attempts'].append(strategy_stats['exact_id_attempts'])
                if 'exact_id_retry_time' in strategy_stats:
                    stats['exact_id_retry_times'].append(strategy_stats['exact_id_retry_time'])
                
                # Отслеживаем fallback
                if parse_stats.get('fallback_invoked', False):
                    stats['fallback_invocations'] += 1
                    stats['cycles_with_fallback'].append(cycle)
                    logging.warning(f"🛡️ Цикл #{cycle}: Fallback был активирован!")
                
                # Логируем Strategy 1 статус
                strategy_used = strategy_stats.get('strategy_used', 'unknown')
                if strategy_used == 'exact_id':
                    logging.info(
                        f"✅ Цикл #{cycle}: Успешно - {len(notice_ids)} новостей за {elapsed:.3f}s "
                        f"(Strategy 1 ✓, {strategy_stats.get('exact_id_attempts', 1)} attempt(s))"
                    )
                else:
                    logging.info(
                        f"✅ Цикл #{cycle}: Успешно - {len(notice_ids)} новостей за {elapsed:.3f}s "
                        f"(Strategy {strategy_used}, fallback reason: {strategy_stats.get('fallback_reason', 'unknown')})"
                    )
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
        
        # Статистика Strategy 1 hit rate
        total_strategy_attempts = stats['strategy_1_hits'] + stats['strategy_1_misses']
        if total_strategy_attempts > 0:
            strategy_1_rate = (stats['strategy_1_hits'] / total_strategy_attempts) * 100
            logging.info(f"🎯 Strategy 1 (exact_id) success rate:")
            logging.info(f"   • Hits: {stats['strategy_1_hits']}")
            logging.info(f"   • Misses: {stats['strategy_1_misses']}")
            logging.info(f"   • Success rate: {strategy_1_rate:.1f}%")
            
            if strategy_1_rate >= 90:
                logging.info(f"   ✅ SUCCESS: ≥90% target achieved!")
            else:
                logging.warning(f"   ⚠️ BELOW TARGET: <90% (target: ≥90%)")
        
        # Статистика retry attempts
        if stats['exact_id_retry_attempts']:
            avg_attempts = sum(stats['exact_id_retry_attempts']) / len(stats['exact_id_retry_attempts'])
            max_attempts = max(stats['exact_id_retry_attempts'])
            min_attempts = min(stats['exact_id_retry_attempts'])
            
            logging.info(f"🔄 Retry statistics:")
            logging.info(f"   • Avg attempts: {avg_attempts:.2f}")
            logging.info(f"   • Min attempts: {min_attempts}")
            logging.info(f"   • Max attempts: {max_attempts}")
        
        # Статистика retry timing
        if stats['exact_id_retry_times']:
            avg_retry_time = sum(stats['exact_id_retry_times']) / len(stats['exact_id_retry_times'])
            max_retry_time = max(stats['exact_id_retry_times'])
            
            logging.info(f"⏱️ Retry timing:")
            logging.info(f"   • Avg retry time: {avg_retry_time*1000:.0f}ms")
            logging.info(f"   • Max retry time: {max_retry_time*1000:.0f}ms")
            
            if max_retry_time < 0.2:
                logging.info(f"   ✅ All retries under 200ms threshold")
            else:
                logging.warning(f"   ⚠️ Some retries exceeded 200ms threshold")
        
        # Статистика fallback
        if stats['fallback_invocations'] > 0:
            logging.info(f"🛡️ Fallback активаций:")
            logging.info(f"   • Всего: {stats['fallback_invocations']} раз")
            logging.info(f"   • Циклы: {stats['cycles_with_fallback'][:10]}{'...' if len(stats['cycles_with_fallback']) > 10 else ''}")
            fallback_rate = (stats['fallback_invocations'] / stats['success']) * 100
            logging.info(f"   • Частота: {fallback_rate:.1f}% успешных циклов")
        else:
            logging.info(f"🛡️ Fallback активаций: 0 (отличная фильтрация!)")
    
    logging.info("=" * 80)
    
    # Проверка критериев приёмки
    if stats['failed'] == 0 and stats['success'] == cycles:
        logging.info("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        logging.info(f"✅ {cycles} циклов подряд - ВСЕ успешные")
        if stats['fallback_invocations'] == 0:
            logging.info(f"✅ Нет чрезмерной фильтрации - fallback не потребовался")
        else:
            logging.info(f"ℹ️ Fallback сработал {stats['fallback_invocations']} раз(а), но все циклы успешны")
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
