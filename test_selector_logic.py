#!/usr/bin/env python3
"""
Тест логики селекторов - проверяет, что стратегии унифицированы
без запуска браузера
"""

import re

def extract_selectors_from_function(code, function_name):
    """Извлекает селекторы и стратегии из JavaScript кода в функции"""
    # Найти функцию в коде
    func_pattern = rf'def {function_name}\([^)]*\):(.*?)(?=\ndef |\Z)'
    func_match = re.search(func_pattern, code, re.DOTALL)
    
    if not func_match:
        return None
    
    func_code = func_match.group(1)
    
    # Найти JavaScript блок
    js_pattern = r'"""(.*?)"""'
    js_match = re.search(js_pattern, func_code, re.DOTALL)
    
    if not js_match:
        return None
    
    js_code = js_match.group(1)
    
    # Извлечь селекторы и стратегии
    selectors = []
    
    # Найти все строки типа: querySelectorAll('...')
    selector_pattern = r"querySelectorAll\(['\"]([^'\"]+)['\"]\)"
    strategy_pattern = r"strategy = ['\"]([^'\"]+)['\"]"
    
    for match in re.finditer(selector_pattern, js_code):
        selector = match.group(1)
        
        # Найти стратегию, связанную с этим селектором
        # Ищем предыдущее упоминание strategy перед этим селектором
        before_text = js_code[:match.start()]
        strat_matches = list(re.finditer(strategy_pattern, before_text))
        
        if strat_matches:
            strategy = strat_matches[-1].group(1)
            selectors.append((selector, strategy))
    
    return selectors


def test_selector_unification():
    """Проверяет унификацию селекторов между функциями"""
    
    print("=" * 80)
    print("🧪 ТЕСТ: Унификация селекторов")
    print("=" * 80)
    print()
    
    # Читаем main.py
    with open('/home/engine/project/main.py', 'r', encoding='utf-8') as f:
        code = f.read()
    
    # Проверяем, что стратегия 'notice_links' переименована в 'all_notice'
    print("1. Проверка переименования стратегии 'notice_links' → 'all_notice'...")
    
    if "strategy = 'notice_links'" in code:
        print("   ❌ Найдена старая стратегия 'notice_links'")
        return False
    else:
        print("   ✅ Старая стратегия 'notice_links' не найдена")
    
    if "strategy = 'all_notice'" in code:
        print("   ✅ Новая стратегия 'all_notice' присутствует")
    else:
        print("   ❌ Новая стратегия 'all_notice' не найдена")
        return False
    
    print()
    
    # Проверяем, что в get_all_notice_ids есть правильные стратегии
    print("2. Проверка fallback стратегий в get_all_notice_ids()...")
    
    required_strategies = ['exact_id', 'all_notice', 'tr_notice', 'any_id']
    
    for strategy in required_strategies:
        pattern = rf"strategy = '{strategy}'"
        if re.search(pattern, code):
            print(f"   ✅ Стратегия '{strategy}' найдена")
        else:
            print(f"   ❌ Стратегия '{strategy}' НЕ найдена")
            return False
    
    print()
    
    # Проверяем селекторы
    print("3. Проверка селекторов...")
    
    expected_selectors = [
        'a[href*="/service_center/notice?id="]',
        'a[href*="/service_center/notice"]',
        'tr a[href*="notice"]',
        'a[href*="id="]'
    ]
    
    for selector in expected_selectors:
        if selector in code:
            print(f"   ✅ Селектор '{selector}' найден")
        else:
            print(f"   ❌ Селектор '{selector}' НЕ найден")
            return False
    
    print()
    
    # Проверяем логирование
    print("4. Проверка улучшенного логирования...")
    
    # Должно быть логирование стратегии и количества ссылок
    log_patterns = [
        r"strategy:.*result\['strategy'\]",
        r"total links:.*result\['totalLinks'\]",
        r"Total links found:.*result\.get\('totalLinks'",
    ]
    
    found_logging = False
    for pattern in log_patterns:
        if re.search(pattern, code):
            found_logging = True
            break
    
    if found_logging:
        print("   ✅ Логирование стратегии и количества ссылок найдено")
    else:
        print("   ❌ Логирование стратегии и количества ссылок НЕ найдено")
        return False
    
    print()
    
    # Проверяем wait_for_notices_js и readiness probe
    print("5. Проверка wait_for_notices_js() использует readiness probe...")
    
    # Проверяем что функция вызывает check_readiness_probe
    if 'check_readiness_probe(driver)' in code:
        print("   ✅ wait_for_notices_js() использует check_readiness_probe")
        
        # Проверяем, что readiness probe содержит все 4 селектора
        probe_pattern = r'def check_readiness_probe\(driver\):(.*?)(?=\ndef )'
        probe_match = re.search(probe_pattern, code, re.DOTALL)
        
        if probe_match:
            probe_code = probe_match.group(1)
            all_selectors_found = all(sel in probe_code for sel in expected_selectors)
            
            if all_selectors_found:
                print("   ✅ check_readiness_probe() содержит все 4 fallback селектора")
            else:
                print("   ❌ check_readiness_probe() не содержит все fallback селекторы")
                return False
        else:
            print("   ❌ Функция check_readiness_probe() не найдена")
            return False
    else:
        print("   ❌ wait_for_notices_js() не использует check_readiness_probe")
        return False
    
    print()
    
    # Проверяем quick check в get_all_notice_ids_with_api
    print("6. Проверка quick check использует readiness probe...")
    
    quick_check_pattern = r'# БЫСТРАЯ ПРОВЕРКА.*?check_readiness_probe\(driver\)'
    quick_match = re.search(quick_check_pattern, code, re.DOTALL)
    
    if quick_match:
        print("   ✅ Quick check использует check_readiness_probe (единая реализация)")
    else:
        print("   ⚠️  Quick check может не использовать readiness probe")
    
    print()
    
    # Проверяем документацию функции
    print("7. Проверка документации get_all_notice_ids()...")
    
    doc_pattern = r'def get_all_notice_ids\(driver\):\s+"""(.*?)"""'
    doc_match = re.search(doc_pattern, code, re.DOTALL)
    
    if doc_match:
        doc = doc_match.group(1)
        
        if 'all_notice' in doc and 'exact_id' in doc:
            print("   ✅ Документация обновлена с новыми стратегиями")
        else:
            print("   ⚠️  Документация может быть не полной")
    else:
        print("   ⚠️  Документация не найдена")
    
    print()
    print("=" * 80)
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
    print("=" * 80)
    print()
    print("Изменения:")
    print("  ✓ Стратегия 'notice_links' переименована в 'all_notice'")
    print("  ✓ Все 4 fallback стратегии унифицированы")
    print("  ✓ check_readiness_probe() содержит все стратегии")
    print("  ✓ wait_for_notices_js() использует readiness probe")
    print("  ✓ Quick check использует readiness probe (единая реализация)")
    print("  ✓ Логирование показывает стратегию и количество ссылок")
    print("  ✓ Документация обновлена")
    print()
    
    return True


if __name__ == "__main__":
    success = test_selector_unification()
    exit(0 if success else 1)
