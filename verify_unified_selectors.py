#!/usr/bin/env python3
"""
Верификация изменений для унификации селекторов (v2.3)
"""

import sys
import re
from pathlib import Path


def check_main_py():
    """Проверяет изменения в main.py"""
    print("=" * 80)
    print("🔍 ПРОВЕРКА: main.py")
    print("=" * 80)
    print()
    
    with open('main.py', 'r', encoding='utf-8') as f:
        code = f.read()
    
    checks = []
    
    # 1. Проверка: old strategy name removed
    check = {
        'name': "Удалена старая стратегия 'notice_links'",
        'test': "strategy = 'notice_links'" not in code,
        'error': "Найдена старая стратегия 'notice_links' - должна быть переименована"
    }
    checks.append(check)
    
    # 2. Проверка: new strategy name present
    check = {
        'name': "Добавлена новая стратегия 'all_notice'",
        'test': "strategy = 'all_notice'" in code,
        'error': "Новая стратегия 'all_notice' не найдена"
    }
    checks.append(check)
    
    # 3. Проверка: all 4 strategies in get_all_notice_ids
    strategies = ['exact_id', 'all_notice', 'tr_notice', 'any_id']
    for strategy in strategies:
        check = {
            'name': f"Стратегия '{strategy}' в get_all_notice_ids()",
            'test': f"strategy = '{strategy}'" in code,
            'error': f"Стратегия '{strategy}' не найдена"
        }
        checks.append(check)
    
    # 4. Проверка: enhanced logging
    check = {
        'name': "Улучшенное логирование (strategy + total links)",
        'test': "total links" in code and "result['totalLinks']" in code,
        'error': "Улучшенное логирование не найдено"
    }
    checks.append(check)
    
    # 5. Проверка: wait_for_notices_js uses all strategies
    wait_pattern = r'def wait_for_notices_js\([^)]*\):.*?(?=\ndef )'
    wait_match = re.search(wait_pattern, code, re.DOTALL)
    
    if wait_match:
        wait_code = wait_match.group(0)
        selectors = [
            'a[href*="/service_center/notice?id="]',
            'a[href*="/service_center/notice"]',
            'tr a[href*="notice"]',
            'a[href*="id="]'
        ]
        for selector in selectors:
            check = {
                'name': f"wait_for_notices_js() использует '{selector}'",
                'test': selector in wait_code,
                'error': f"Селектор '{selector}' не найден в wait_for_notices_js()"
            }
            checks.append(check)
    
    # 6. Проверка: quick check uses all strategies
    quick_pattern = r'# БЫСТРАЯ ПРОВЕРКА.*?driver\.execute_script\("""(.*?)"""'
    quick_match = re.search(quick_pattern, code, re.DOTALL)
    
    if quick_match:
        quick_code = quick_match.group(1)
        for selector in selectors:
            check = {
                'name': f"Quick check использует '{selector}'",
                'test': selector in quick_code,
                'error': f"Селектор '{selector}' не найден в quick check"
            }
            checks.append(check)
    
    # Выполняем проверки
    passed = 0
    failed = 0
    
    for check in checks:
        if check['test']:
            print(f"✅ {check['name']}")
            passed += 1
        else:
            print(f"❌ {check['name']}")
            print(f"   Error: {check['error']}")
            failed += 1
    
    print()
    print(f"Результат: {passed} пройдено, {failed} не пройдено")
    print()
    
    return failed == 0


def check_readme():
    """Проверяет обновления в README.md"""
    print("=" * 80)
    print("🔍 ПРОВЕРКА: README.md")
    print("=" * 80)
    print()
    
    with open('README.md', 'r', encoding='utf-8') as f:
        readme = f.read()
    
    checks = []
    
    # 1. Версия обновлена до v2.3
    check = {
        'name': "Версия обновлена до v2.3",
        'test': 'v2.3' in readme,
        'error': "Версия v2.3 не найдена"
    }
    checks.append(check)
    
    # 2. Упоминание унифицированных стратегий
    check = {
        'name': "Упоминание унифицированных стратегий",
        'test': 'унифициров' in readme.lower() or 'unified' in readme.lower(),
        'error': "Унифицированные стратегии не упомянуты"
    }
    checks.append(check)
    
    # 3. Ссылка на новую документацию
    check = {
        'name': "Ссылка на UNIFIED_SELECTORS_README.md",
        'test': 'UNIFIED_SELECTORS_README' in readme,
        'error': "Ссылка на новую документацию не найдена"
    }
    checks.append(check)
    
    # 4. all_notice вместо notice_links
    check = {
        'name': "Стратегия 'all_notice' упомянута",
        'test': 'all_notice' in readme,
        'error': "Стратегия 'all_notice' не найдена"
    }
    checks.append(check)
    
    # 5. Обновленные настройки (20ms, 0.3s)
    check = {
        'name': "Обновленные настройки (20ms polling)",
        'test': '20ms' in readme,
        'error': "20ms polling не найден"
    }
    checks.append(check)
    
    check = {
        'name': "Обновленные настройки (0.3s max wait)",
        'test': '0.3' in readme,
        'error': "0.3s max wait не найден"
    }
    checks.append(check)
    
    # Выполняем проверки
    passed = 0
    failed = 0
    
    for check in checks:
        if check['test']:
            print(f"✅ {check['name']}")
            passed += 1
        else:
            print(f"❌ {check['name']}")
            print(f"   Error: {check['error']}")
            failed += 1
    
    print()
    print(f"Результат: {passed} пройдено, {failed} не пройдено")
    print()
    
    return failed == 0


def check_new_files():
    """Проверяет наличие новых файлов"""
    print("=" * 80)
    print("🔍 ПРОВЕРКА: Новые файлы")
    print("=" * 80)
    print()
    
    required_files = [
        'test_selector_logic.py',
        'test_unified_selectors.py',
        'UNIFIED_SELECTORS_README.md',
        'TASK_UNIFIED_SELECTORS.md'
    ]
    
    passed = 0
    failed = 0
    
    for filename in required_files:
        if Path(filename).exists():
            print(f"✅ {filename} существует")
            passed += 1
        else:
            print(f"❌ {filename} НЕ найден")
            failed += 1
    
    print()
    print(f"Результат: {passed} пройдено, {failed} не пройдено")
    print()
    
    return failed == 0


def check_syntax():
    """Проверяет синтаксис Python файлов"""
    print("=" * 80)
    print("🔍 ПРОВЕРКА: Синтаксис Python")
    print("=" * 80)
    print()
    
    import py_compile
    
    files = [
        'main.py',
        'test_selector_logic.py',
        'test_unified_selectors.py',
        'verify_unified_selectors.py'
    ]
    
    passed = 0
    failed = 0
    
    for filename in files:
        try:
            py_compile.compile(filename, doraise=True)
            print(f"✅ {filename} - синтаксис OK")
            passed += 1
        except py_compile.PyCompileError as e:
            print(f"❌ {filename} - синтаксическая ошибка")
            print(f"   {e}")
            failed += 1
    
    print()
    print(f"Результат: {passed} пройдено, {failed} не пройдено")
    print()
    
    return failed == 0


def main():
    """Запускает все проверки"""
    print()
    print("🧪 ВЕРИФИКАЦИЯ УНИФИКАЦИИ СЕЛЕКТОРОВ (v2.3)")
    print()
    
    results = []
    
    # Проверяем main.py
    results.append(('main.py', check_main_py()))
    
    # Проверяем README.md
    results.append(('README.md', check_readme()))
    
    # Проверяем новые файлы
    results.append(('Новые файлы', check_new_files()))
    
    # Проверяем синтаксис
    results.append(('Синтаксис', check_syntax()))
    
    # Итоговый результат
    print("=" * 80)
    print("📊 ИТОГОВЫЙ РЕЗУЛЬТАТ")
    print("=" * 80)
    print()
    
    all_passed = all(result[1] for result in results)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {name}")
    
    print()
    
    if all_passed:
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
        print()
        print("Изменения v2.3:")
        print("  ✓ Стратегия 'notice_links' переименована в 'all_notice'")
        print("  ✓ Все функции используют унифицированные стратегии")
        print("  ✓ Улучшенное логирование (strategy + total links)")
        print("  ✓ Документация обновлена")
        print("  ✓ Тесты добавлены")
        print()
        print("🎉 Готово к использованию!")
        return 0
    else:
        print("❌ НЕКОТОРЫЕ ПРОВЕРКИ НЕ ПРОШЛИ")
        print()
        print("Пожалуйста, исправьте ошибки выше.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
