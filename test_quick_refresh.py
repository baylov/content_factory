#!/usr/bin/env python3
"""
Тест быстрого refresh с новыми оптимизациями:
- max_wait снижен до 0.3s
- polling interval снижен до 20ms
- быстрая проверка сразу после refresh
"""

import time
import sys
from main import init_driver, get_all_notice_ids_with_api, UPBIT_NOTICE_URL

def test_quick_refresh_cycle():
    """
    Тестирует полный цикл с новыми оптимизациями
    Цель: < 1.5 секунды
    """
    print("=" * 70)
    print("ТЕСТ БЫСТРОГО REFRESH С НОВЫМИ ОПТИМИЗАЦИЯМИ")
    print("=" * 70)
    print()
    print("🎯 ЦЕЛЬ: Цикл < 1.5 секунды")
    print("📊 Измеряем: Load + Wait + Parse")
    print()
    
    # Инициализация драйвера (без CDP)
    print("🔧 Инициализация драйвера...")
    driver = init_driver(enable_cdp=False)
    
    if not driver:
        print("❌ Не удалось инициализировать драйвер")
        return False
    
    try:
        # Выполняем несколько циклов для статистики
        cycle_times = []
        load_times = []
        wait_times = []
        parse_times = []
        
        num_cycles = 5
        
        for i in range(num_cycles):
            print(f"\n{'=' * 70}")
            print(f"ЦИКЛ #{i+1}/{num_cycles}")
            print(f"{'=' * 70}")
            
            cycle_start = time.time()
            
            # Получаем новости через оптимизированную функцию
            notice_ids, method, timings = get_all_notice_ids_with_api(
                driver, 
                known_endpoints=[], 
                use_cdp=False
            )
            
            cycle_time = time.time() - cycle_start
            cycle_times.append(cycle_time)
            
            # Извлекаем детальные метрики
            if method == "HTML" and isinstance(timings, dict):
                html_info = timings.get("html", {})
                load_time = html_info.get("page_load", 0)
                wait_time = html_info.get("wait", 0)
                parse_time = html_info.get("parse", 0)
                
                load_times.append(load_time)
                wait_times.append(wait_time)
                parse_times.append(parse_time)
                
                print(f"\n📊 Детальные метрики:")
                print(f"  ⏱️ Load:  {load_time:.3f}s")
                print(f"  ⏱️ Wait:  {wait_time:.3f}s {'🎯' if wait_time < 0.3 else ''}")
                print(f"  ⏱️ Parse: {parse_time:.3f}s")
                print(f"  {'─' * 40}")
                print(f"  ⏱️ ИТОГО: {cycle_time:.3f}s")
                
                # Оценка
                if cycle_time < 1.0:
                    print(f"  ✅ ⚡ ОТЛИЧНО: < 1.0 сек!")
                elif cycle_time < 1.3:
                    print(f"  ✅ ХОРОШО: < 1.3 сек")
                elif cycle_time < 1.5:
                    print(f"  ✅ ПРИЕМЛЕМО: < 1.5 сек")
                else:
                    print(f"  ⚠️ МЕДЛЕННО: > 1.5 сек")
            
            print(f"\n🔢 Найдено новостей: {len(notice_ids)}")
            
            # Пауза между циклами
            if i < num_cycles - 1:
                time.sleep(0.5)
        
        # Статистика
        print(f"\n\n{'=' * 70}")
        print("📊 ИТОГОВАЯ СТАТИСТИКА")
        print(f"{'=' * 70}")
        
        avg_cycle = sum(cycle_times) / len(cycle_times)
        min_cycle = min(cycle_times)
        max_cycle = max(cycle_times)
        
        avg_load = sum(load_times) / len(load_times)
        avg_wait = sum(wait_times) / len(wait_times)
        avg_parse = sum(parse_times) / len(parse_times)
        
        print(f"\n⏱️ Общее время цикла:")
        print(f"  Среднее: {avg_cycle:.3f}s")
        print(f"  Мин:     {min_cycle:.3f}s")
        print(f"  Макс:    {max_cycle:.3f}s")
        
        print(f"\n⏱️ Детализация (среднее):")
        print(f"  Load:  {avg_load:.3f}s")
        print(f"  Wait:  {avg_wait:.3f}s {'🎯 ОПТИМИЗИРОВАНО!' if avg_wait < 0.3 else ''}")
        print(f"  Parse: {avg_parse:.3f}s")
        
        # Проверка целей
        print(f"\n{'=' * 70}")
        print("🎯 ПРОВЕРКА ЦЕЛЕЙ")
        print(f"{'=' * 70}")
        
        goals_met = []
        
        # Цель 1: Wait time < 0.3s
        if avg_wait < 0.3:
            print(f"✅ Wait time: {avg_wait:.3f}s < 0.3s")
            goals_met.append(True)
        else:
            print(f"❌ Wait time: {avg_wait:.3f}s >= 0.3s")
            goals_met.append(False)
        
        # Цель 2: Total cycle < 1.5s
        if avg_cycle < 1.5:
            print(f"✅ Total cycle: {avg_cycle:.3f}s < 1.5s")
            goals_met.append(True)
        else:
            print(f"❌ Total cycle: {avg_cycle:.3f}s >= 1.5s")
            goals_met.append(False)
        
        # Цель 3: Notices found
        if len(notice_ids) > 0:
            print(f"✅ Notices found: {len(notice_ids)} > 0")
            goals_met.append(True)
        else:
            print(f"❌ Notices found: 0")
            goals_met.append(False)
        
        print(f"\n{'=' * 70}")
        if all(goals_met):
            print("🎉 ВСЕ ЦЕЛИ ДОСТИГНУТЫ!")
            print(f"   • Wait time оптимизирован: {avg_wait:.3f}s < 0.3s")
            print(f"   • Цикл ускорен: {avg_cycle:.3f}s < 1.5s")
            print(f"   • Новости обнаружены корректно")
            return True
        else:
            print("⚠️ НЕ ВСЕ ЦЕЛИ ДОСТИГНУТЫ")
            return False
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        driver.quit()
        print(f"\n{'=' * 70}")


if __name__ == "__main__":
    success = test_quick_refresh_cycle()
    sys.exit(0 if success else 1)
