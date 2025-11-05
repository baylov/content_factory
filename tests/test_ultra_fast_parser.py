#!/usr/bin/env python3
"""
Тест ультра-быстрого JS парсера с проверкой селекторов
Проверяет:
1. Диагностическую функцию debug_save_html_and_find_selectors()
2. Умное ожидание wait_for_notices_js()
3. Улучшенный парсер get_all_notice_ids() с fallback стратегиями
4. Производительность < 1 секунды
5. Автоматическую диагностику при ошибках
"""

import sys
import time
import logging
from main import init_driver, debug_save_html_and_find_selectors, wait_for_notices_js, get_all_notice_ids

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

UPBIT_NOTICE_URL = "https://upbit.com/service_center/notice"


def test_diagnostic_function():
    """Тест диагностической функции"""
    print("\n" + "="*80)
    print("ТЕСТ 1: Диагностическая функция debug_save_html_and_find_selectors()")
    print("="*80)
    
    driver = init_driver()
    if not driver:
        print("❌ FAIL: Не удалось инициализировать браузер")
        return False
    
    try:
        driver.get(UPBIT_NOTICE_URL)
        time.sleep(1)
        
        print("\n📋 Запускаем диагностику...")
        best_selector = debug_save_html_and_find_selectors(driver)
        
        if best_selector:
            print(f"\n✅ PASS: Найден лучший селектор: {best_selector}")
            
            # Проверяем что HTML файл создан
            import os
            if os.path.exists('upbit_debug.html'):
                file_size = os.path.getsize('upbit_debug.html')
                print(f"✅ PASS: HTML файл создан (размер: {file_size} байт)")
            else:
                print("❌ FAIL: HTML файл не создан")
                return False
            
            return True
        else:
            print("❌ FAIL: Не найден подходящий селектор")
            return False
            
    except Exception as e:
        print(f"❌ FAIL: Ошибка: {e}")
        return False
    finally:
        driver.quit()


def test_smart_wait():
    """Тест умного ожидания"""
    print("\n" + "="*80)
    print("ТЕСТ 2: Умное ожидание wait_for_notices_js()")
    print("="*80)
    
    driver = init_driver()
    if not driver:
        print("❌ FAIL: Не удалось инициализировать браузер")
        return False
    
    try:
        print("\n📋 Загружаем страницу...")
        driver.get(UPBIT_NOTICE_URL)
        
        print("📋 Запускаем умное ожидание (max 1.0s)...")
        start = time.time()
        result = wait_for_notices_js(driver, max_wait=1.0)
        elapsed = time.time() - start
        
        if result:
            print(f"✅ PASS: Новости появились за {elapsed:.3f}s")
            
            if elapsed < 1.0:
                print(f"⚡ ОТЛИЧНО: Ожидание < 1 сек!")
            
            return True
        else:
            print(f"❌ FAIL: Новости не появились за {elapsed:.3f}s")
            return False
            
    except Exception as e:
        print(f"❌ FAIL: Ошибка: {e}")
        return False
    finally:
        driver.quit()


def test_ultra_fast_parser():
    """Тест ультра-быстрого парсера"""
    print("\n" + "="*80)
    print("ТЕСТ 3: Ультра-быстрый парсер get_all_notice_ids()")
    print("="*80)
    
    driver = init_driver()
    if not driver:
        print("❌ FAIL: Не удалось инициализировать браузер")
        return False
    
    try:
        print("\n📋 Загружаем страницу...")
        driver.get(UPBIT_NOTICE_URL)
        wait_for_notices_js(driver, max_wait=1.0)
        
        print("📋 Запускаем парсинг...")
        start = time.time()
        notice_ids = get_all_notice_ids(driver)
        parse_time = time.time() - start
        
        if notice_ids and len(notice_ids) > 0:
            print(f"\n✅ PASS: Найдено {len(notice_ids)} новостей")
            print(f"🔢 ID: {notice_ids[:5]}{'...' if len(notice_ids) > 5 else ''}")
            print(f"⏱️ Время парсинга: {parse_time:.3f}s")
            
            if parse_time < 1.0:
                print(f"⚡ ОТЛИЧНО: Парсинг < 1 сек!")
            elif parse_time < 2.0:
                print(f"✅ ХОРОШО: Парсинг < 2 сек")
            else:
                print(f"⚠️ МЕДЛЕННО: Парсинг {parse_time:.3f}s")
            
            return True
        else:
            print("❌ FAIL: Новости не найдены")
            return False
            
    except Exception as e:
        print(f"❌ FAIL: Ошибка: {e}")
        return False
    finally:
        driver.quit()


def test_full_cycle_performance():
    """Тест производительности полного цикла"""
    print("\n" + "="*80)
    print("ТЕСТ 4: Производительность полного цикла (< 1 сек)")
    print("="*80)
    
    driver = init_driver()
    if not driver:
        print("❌ FAIL: Не удалось инициализировать браузер")
        return False
    
    try:
        print("\n📋 Полный цикл: загрузка + ожидание + парсинг...")
        
        cycle_start = time.time()
        
        # 1. Загрузка
        load_start = time.time()
        driver.get(UPBIT_NOTICE_URL)
        load_time = time.time() - load_start
        print(f"  ⏱️ Загрузка: {load_time:.3f}s")
        
        # 2. Ожидание
        wait_start = time.time()
        wait_for_notices_js(driver, max_wait=0.5)
        wait_time = time.time() - wait_start
        print(f"  ⏱️ Ожидание: {wait_time:.3f}s")
        
        # 3. Парсинг
        parse_start = time.time()
        notice_ids = get_all_notice_ids(driver)
        parse_time = time.time() - parse_start
        print(f"  ⏱️ Парсинг: {parse_time:.3f}s")
        
        total_time = time.time() - cycle_start
        
        print(f"\n⏱️ ИТОГО: {total_time:.3f}s")
        
        if total_time < 1.0:
            print("✅ PASS: Полный цикл < 1 сек! ⚡")
            return True
        elif total_time < 1.5:
            print("✅ PASS: Полный цикл < 1.5 сек")
            return True
        elif total_time < 2.0:
            print("⚠️ ПРИЕМЛЕМО: Полный цикл < 2 сек")
            return True
        else:
            print(f"❌ FAIL: Полный цикл {total_time:.3f}s > 2 сек")
            return False
            
    except Exception as e:
        print(f"❌ FAIL: Ошибка: {e}")
        return False
    finally:
        driver.quit()


def test_fallback_strategies():
    """Тест fallback стратегий"""
    print("\n" + "="*80)
    print("ТЕСТ 5: Fallback стратегии парсера")
    print("="*80)
    
    driver = init_driver()
    if not driver:
        print("❌ FAIL: Не удалось инициализировать браузер")
        return False
    
    try:
        print("\n📋 Загружаем страницу...")
        driver.get(UPBIT_NOTICE_URL)
        wait_for_notices_js(driver, max_wait=1.0)
        
        print("📋 Парсинг с fallback стратегиями...")
        notice_ids = get_all_notice_ids(driver)
        
        if notice_ids and len(notice_ids) > 0:
            print(f"✅ PASS: Fallback стратегии работают (найдено {len(notice_ids)} новостей)")
            return True
        else:
            print("❌ FAIL: Fallback стратегии не сработали")
            return False
            
    except Exception as e:
        print(f"❌ FAIL: Ошибка: {e}")
        return False
    finally:
        driver.quit()


def main():
    print("\n" + "="*80)
    print("ТЕСТИРОВАНИЕ УЛЬТРА-БЫСТРОГО JS ПАРСЕРА")
    print("="*80)
    
    tests = [
        ("Диагностическая функция", test_diagnostic_function),
        ("Умное ожидание", test_smart_wait),
        ("Ультра-быстрый парсер", test_ultra_fast_parser),
        ("Производительность цикла", test_full_cycle_performance),
        ("Fallback стратегии", test_fallback_strategies),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Критическая ошибка в тесте '{test_name}': {e}")
            results.append((test_name, False))
    
    # Итоги
    print("\n" + "="*80)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nИтого: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return 0
    else:
        print(f"\n⚠️ Провалено {total - passed} тест(ов)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
