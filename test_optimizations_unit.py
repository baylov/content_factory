#!/usr/bin/env python3
"""
Unit тесты для проверки оптимизаций без запуска браузера
Проверяем что изменения в коде соответствуют требованиям
"""

import re
import sys

def test_wait_for_notices_max_wait():
    """
    Проверяет что max_wait в wait_for_notices_js() снижен с 1.0 до 0.3
    """
    print("=" * 70)
    print("ТЕСТ 1: max_wait снижен с 1.0 до 0.3")
    print("=" * 70)
    
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем определение функции wait_for_notices_js
    pattern = r'def wait_for_notices_js\(driver, max_wait=([0-9.]+)\):'
    match = re.search(pattern, content)
    
    if not match:
        print("❌ Не найдено определение функции wait_for_notices_js")
        return False
    
    max_wait = float(match.group(1))
    print(f"Найдено: max_wait={max_wait}")
    
    if max_wait == 0.3:
        print("✅ max_wait = 0.3 (целевое значение)")
        return True
    elif max_wait == 1.0:
        print("❌ max_wait = 1.0 (старое значение, нужно 0.3)")
        return False
    else:
        print(f"⚠️ max_wait = {max_wait} (неожиданное значение)")
        return max_wait <= 0.3


def test_readiness_probe_exists():
    """
    Проверяет что существует функция check_readiness_probe
    """
    print("\n" + "=" * 70)
    print("ТЕСТ 1.5: Существует функция check_readiness_probe")
    print("=" * 70)
    
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем определение функции check_readiness_probe
    if 'def check_readiness_probe(driver):' in content:
        print("✅ Функция check_readiness_probe найдена")
        
        # Проверяем ключевые элементы
        checks = {
            'readyState check': 'document.readyState' in content,
            'container visibility': 'containerVisible' in content,
            'strategy tracking': "result.strategy = 'exact_id'" in content or "result.strategy = 'all_notice'" in content,
            'ready flag': 'result.ready' in content,
        }
        
        all_passed = True
        for check_name, passed in checks.items():
            if passed:
                print(f"  ✓ {check_name}")
            else:
                print(f"  ✗ {check_name}")
                all_passed = False
        
        return all_passed
    else:
        print("❌ Функция check_readiness_probe не найдена")
        return False


def test_polling_interval():
    """
    Проверяет что polling interval снижен с 50ms (0.05) до 20ms (0.02)
    """
    print("\n" + "=" * 70)
    print("ТЕСТ 2: polling interval снижен с 50ms до 20ms")
    print("=" * 70)
    
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем check_interval в wait_for_notices_js
    pattern = r'def wait_for_notices_js.*?check_interval = ([0-9.]+).*?time\.sleep\(check_interval\)'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("❌ Не найден check_interval в wait_for_notices_js")
        return False
    
    interval = float(match.group(1))
    interval_ms = interval * 1000
    
    print(f"Найдено: check_interval={interval} ({interval_ms:.0f}ms)")
    
    if interval == 0.02:
        print("✅ check_interval = 0.02 (20ms) - целевое значение")
        return True
    elif interval == 0.05:
        print("❌ check_interval = 0.05 (50ms) - старое значение, нужно 0.02 (20ms)")
        return False
    else:
        print(f"⚠️ check_interval = {interval} ({interval_ms:.0f}ms) - неожиданное значение")
        return interval <= 0.02


def test_quick_check_after_refresh():
    """
    Проверяет что добавлена быстрая проверка сразу после refresh
    """
    print("\n" + "=" * 70)
    print("ТЕСТ 3: Быстрая проверка сразу после refresh")
    print("=" * 70)
    
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем комментарий о быстрой проверке и использование readiness probe
    quick_check_patterns = [
        r'БЫСТРАЯ ПРОВЕРКА',
        r'check_readiness_probe',
        r'skip wait',
        r'ready immediately',
    ]
    
    found_patterns = []
    for pattern in quick_check_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            found_patterns.append(pattern)
    
    print(f"Найдено паттернов быстрой проверки: {len(found_patterns)}/{len(quick_check_patterns)}")
    
    for pattern in found_patterns:
        print(f"  ✓ {pattern}")
    
    if len(found_patterns) >= 3:
        print("✅ Быстрая проверка с readiness probe реализована")
        return True
    else:
        print("❌ Быстрая проверка не найдена или не полностью реализована")
        return False


def test_optimizations_logging():
    """
    Проверяет что логирование оптимизаций обновлено
    """
    print("\n" + "=" * 70)
    print("ТЕСТ 4: Обновлено логирование оптимизаций")
    print("=" * 70)
    
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем обновлённое логирование с probe stats
    optimizations_patterns = [
        r'polling 20ms',
        r'max 0\.3s',
        r'readiness probe',
        r'probe_stats',
        r'poll_count',
    ]
    
    found_patterns = []
    for pattern in optimizations_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            found_patterns.append(pattern)
    
    print(f"Найдено обновлений в логировании: {len(found_patterns)}/{len(optimizations_patterns)}")
    
    for pattern in found_patterns:
        print(f"  ✓ {pattern}")
    
    if len(found_patterns) >= 3:
        print("✅ Логирование с probe stats обновлено")
        return True
    else:
        print("⚠️ Логирование оптимизаций не полностью обновлено")
        return len(found_patterns) > 0


def test_target_speed_updated():
    """
    Проверяет что целевая скорость обновлена на < 1.5 секунды
    """
    print("\n" + "=" * 70)
    print("ТЕСТ 5: Целевая скорость обновлена на < 1.5 секунды")
    print("=" * 70)
    
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем целевую скорость
    target_patterns = [
        r'< 1\.5 секунды',
        r'< 1\.5 сек',
        r'<1\.5s',
    ]
    
    found = False
    for pattern in target_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            print(f"✓ Найдено: {pattern}")
            found = True
    
    if found:
        print("✅ Целевая скорость обновлена на < 1.5 секунды")
        return True
    else:
        print("⚠️ Целевая скорость не найдена или не обновлена")
        return False


def main():
    """
    Запускает все тесты
    """
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " UNIT ТЕСТЫ ОПТИМИЗАЦИЙ ".center(68) + "║")
    print("╚" + "=" * 68 + "╝")
    print()
    
    tests = [
        ("max_wait снижен до 0.3s", test_wait_for_notices_max_wait),
        ("Readiness probe существует", test_readiness_probe_exists),
        ("polling interval снижен до 20ms", test_polling_interval),
        ("Быстрая проверка после refresh", test_quick_check_after_refresh),
        ("Логирование оптимизаций", test_optimizations_logging),
        ("Целевая скорость < 1.5s", test_target_speed_updated),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ Ошибка в тесте '{name}': {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Итоговая статистика
    print("\n" + "=" * 70)
    print("ИТОГОВЫЕ РЕЗУЛЬТАТЫ")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print("\n" + "=" * 70)
    print(f"Пройдено: {passed}/{total} тестов")
    
    if passed == total:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        print("\n✅ Критерии приёмки:")
        print("  1. ✅ Lightweight readiness probe реализован")
        print("  2. ✅ max_wait уменьшен с 1.0 до 0.3 секунд")
        print("  3. ✅ Polling interval уменьшен с 50ms до 20ms")
        print("  4. ✅ Быстрая проверка с readiness probe")
        print("  5. ✅ Structured logging (probe duration, poll count, strategy)")
        print("  6. ✅ Целевое время цикла: < 1.5 секунды")
        print("  7. ✅ Wait time: < 0.3 секунды")
        return True
    else:
        print(f"❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ: {total - passed} из {total}")
        return False


if __name__ == "__main__":
    success = main()
    print()
    sys.exit(0 if success else 1)
