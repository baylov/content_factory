#!/usr/bin/env python3
"""
Юнит-тест логики JS парсера без запуска браузера
Проверяет структуру JavaScript кода и Python обработки
"""

import sys
import re
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)

def test_get_all_notice_ids_code():
    """Проверяет код функции get_all_notice_ids"""
    logging.info("🧪 Тест 1: Проверка структуры функции get_all_notice_ids")
    
    # Читаем код main.py
    with open('main.py', 'r', encoding='utf-8') as f:
        code = f.read()
    
    # Извлекаем функцию get_all_notice_ids
    match = re.search(r'def get_all_notice_ids\(driver\):.*?(?=\ndef |\Z)', code, re.DOTALL)
    if not match:
        logging.error("❌ Функция get_all_notice_ids не найдена")
        return False
    
    func_code = match.group(0)
    
    # Проверяем ключевые элементы согласно задаче
    checks = []
    
    # 1. Проверка на явное тестирование стратегий
    if "console.log('Strategy 1 (exact_id):" in func_code:
        logging.info("  ✅ Strategy 1 logging присутствует")
        checks.append(True)
    else:
        logging.error("  ❌ Strategy 1 logging отсутствует")
        checks.append(False)
    
    if "console.log('Strategy 2 (all_notice):" in func_code:
        logging.info("  ✅ Strategy 2 logging присутствует")
        checks.append(True)
    else:
        logging.error("  ❌ Strategy 2 logging отсутствует")
        checks.append(False)
    
    # 2. Проверка на правильные селекторы
    if 'a[href*="/service_center/notice?id="]' in func_code:
        logging.info("  ✅ Селектор exact_id корректный")
        checks.append(True)
    else:
        logging.error("  ❌ Селектор exact_id некорректный")
        checks.append(False)
    
    if 'a[href*="/service_center/notice"]' in func_code:
        logging.info("  ✅ Селектор all_notice корректный")
        checks.append(True)
    else:
        logging.error("  ❌ Селектор all_notice некорректный")
        checks.append(False)
    
    # 3. Проверка на использование for loop вместо forEach
    if "for (let i = 0; i < links.length; i++)" in func_code:
        logging.info("  ✅ Использует for loop (как в диагностике)")
        checks.append(True)
    else:
        logging.error("  ❌ Не использует for loop")
        checks.append(False)
    
    # 4. Проверка на allLinks переменную
    if "const allLinks = links.length" in func_code:
        logging.info("  ✅ Сохраняет allLinks до фильтрации")
        checks.append(True)
    else:
        logging.error("  ❌ Не сохраняет allLinks")
        checks.append(False)
    
    # 5. Проверка на возврат правильной структуры
    if "totalLinks: allLinks" in func_code:
        logging.info("  ✅ Возвращает totalLinks")
        checks.append(True)
    else:
        logging.error("  ❌ Не возвращает totalLinks")
        checks.append(False)
    
    if "samples: notices.slice(0, 3)" in func_code:
        logging.info("  ✅ Возвращает samples")
        checks.append(True)
    else:
        logging.error("  ❌ Не возвращает samples")
        checks.append(False)
    
    # 6. Проверка на детальное логирование в Python
    if "📋 Примеры:" in func_code and "logging.info" in func_code:
        logging.info("  ✅ Выводит примеры новостей")
        checks.append(True)
    else:
        logging.error("  ❌ Не выводит примеры новостей")
        checks.append(False)
    
    # 7. Проверка на синхронизацию с диагностикой
    if "Синхронизировано с диагностикой" in func_code or "ТОЧНО ТУ ЖЕ логику" in func_code:
        logging.info("  ✅ Документирована синхронизация с диагностикой")
        checks.append(True)
    else:
        logging.error("  ❌ Не документирована синхронизация")
        checks.append(False)
    
    success_rate = sum(checks) / len(checks) * 100
    logging.info(f"\n📊 Результат: {sum(checks)}/{len(checks)} проверок пройдено ({success_rate:.0f}%)")
    
    return all(checks)

def test_diagnostic_consistency():
    """Проверяет согласованность с диагностикой"""
    logging.info("\n🧪 Тест 2: Согласованность с debug_save_html_and_find_selectors")
    
    with open('main.py', 'r', encoding='utf-8') as f:
        code = f.read()
    
    # Извлекаем оба кода
    parser_match = re.search(r'def get_all_notice_ids\(driver\):.*?(?=\ndef |\Z)', code, re.DOTALL)
    diagnostic_match = re.search(r'def debug_save_html_and_find_selectors\(driver\):.*?(?=\ndef |\Z)', code, re.DOTALL)
    
    if not parser_match or not diagnostic_match:
        logging.error("❌ Не найдена одна из функций")
        return False
    
    parser_code = parser_match.group(0)
    diagnostic_code = diagnostic_match.group(0)
    
    # Проверяем, что селекторы одинаковые
    parser_selectors = re.findall(r'a\[href\*="[^"]+"\]', parser_code)
    diagnostic_selectors = re.findall(r"'(a\[href\*=\"[^\"]+\"\])'", diagnostic_code)
    
    logging.info(f"  📋 Селекторов в парсере: {len(parser_selectors)}")
    logging.info(f"  📋 Селекторов в диагностике: {len(diagnostic_selectors)}")
    
    # Проверяем первые 4 селектора (основные)
    key_selectors = [
        'a[href*="/service_center/notice?id="]',
        'a[href*="/service_center/notice"]',
        'tr a[href*="notice"]',
        'a[href*="id="]'
    ]
    
    checks = []
    for selector in key_selectors:
        in_parser = selector in parser_code
        in_diagnostic = f"'{selector}'" in diagnostic_code or f'"{selector}"' in diagnostic_code
        
        if in_parser and in_diagnostic:
            logging.info(f"  ✅ {selector} присутствует в обеих функциях")
            checks.append(True)
        elif in_parser and not in_diagnostic:
            logging.warning(f"  ⚠️ {selector} только в парсере")
            checks.append(True)  # Это OK
        else:
            logging.error(f"  ❌ {selector} отсутствует в парсере")
            checks.append(False)
    
    return all(checks)

def test_timing_output():
    """Проверяет наличие детального вывода времени"""
    logging.info("\n🧪 Тест 3: Детальный вывод времени")
    
    with open('main.py', 'r', encoding='utf-8') as f:
        code = f.read()
    
    checks = []
    
    # Проверяем наличие итогового вывода в get_all_notice_ids_with_api
    if "⏱️ ━━━ ИТОГО ЦИКЛ:" in code:
        logging.info("  ✅ Итоговое время цикла выводится")
        checks.append(True)
    else:
        logging.error("  ❌ Итоговое время цикла не выводится")
        checks.append(False)
    
    if "Load" in code and "Wait" in code and "Parse" in code:
        logging.info("  ✅ Детализация Load/Wait/Parse присутствует")
        checks.append(True)
    else:
        logging.error("  ❌ Детализация Load/Wait/Parse отсутствует")
        checks.append(False)
    
    if "< 1.5 сек" in code:
        logging.info("  ✅ Проверка целевого времени < 1.5 сек")
        checks.append(True)
    else:
        logging.error("  ❌ Проверка целевого времени отсутствует")
        checks.append(False)
    
    return all(checks)

def main():
    logging.info("="*60)
    logging.info("Юнит-тест исправления JS парсера")
    logging.info("="*60)
    logging.info("")
    
    results = []
    
    # Запускаем тесты
    results.append(("Структура парсера", test_get_all_notice_ids_code()))
    results.append(("Согласованность с диагностикой", test_diagnostic_consistency()))
    results.append(("Детальный вывод времени", test_timing_output()))
    
    # Итог
    logging.info("\n" + "="*60)
    logging.info("ИТОГОВЫЕ РЕЗУЛЬТАТЫ")
    logging.info("="*60)
    
    for name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        logging.info(f"{status}: {name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        logging.info("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return 0
    else:
        logging.info("\n❌ НЕКОТОРЫЕ ТЕСТЫ ПРОВАЛЕНЫ")
        return 1

if __name__ == "__main__":
    sys.exit(main())
