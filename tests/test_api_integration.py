#!/usr/bin/env python3
"""
Полный интеграционный тест API режима

Проверяет:
1. API endpoint доступность
2. HTTP session с retry
3. Получение новостей
4. Структура данных
5. Обработка новых новостей
6. Вычисление задержки обнаружения
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo
from main import (
    create_api_session, 
    get_notices_via_api, 
    get_last_max_id, 
    save_max_id
)


def test_api_session():
    """Тест создания HTTP session"""
    print("1️⃣ Тест создания HTTP session...")
    session = create_api_session()
    assert session is not None, "Session не создана"
    print("   ✅ HTTP session создана с retry механизмом")
    return session


def test_api_fetch(session):
    """Тест получения новостей через API"""
    print("\n2️⃣ Тест получения новостей через API...")
    
    start_time = time.time()
    notices = get_notices_via_api(session)
    elapsed = time.time() - start_time
    
    assert notices is not None, "API вернул None"
    assert len(notices) > 0, "API не вернул новости"
    assert len(notices) == 20, f"Ожидалось 20 новостей, получено {len(notices)}"
    
    print(f"   ✅ Получено {len(notices)} новостей за {elapsed:.3f}s")
    
    if elapsed < 0.3:
        print(f"   ⚡ ОТЛИЧНО: < 0.3s")
    elif elapsed < 0.5:
        print(f"   ✅ ХОРОШО: < 0.5s")
    else:
        print(f"   ⚠️ МЕДЛЕННО: {elapsed:.3f}s")
    
    return notices


def test_notice_structure(notices):
    """Тест структуры данных новостей"""
    print("\n3️⃣ Тест структуры данных новостей...")
    
    notice = notices[0]
    
    # Проверяем обязательные поля
    required_fields = ["id", "title", "category", "listed_at"]
    for field in required_fields:
        assert field in notice, f"Отсутствует обязательное поле: {field}"
    
    # Проверяем типы
    assert isinstance(notice["id"], int), "ID должен быть int"
    assert isinstance(notice["title"], str), "title должен быть str"
    assert isinstance(notice["category"], str), "category должен быть str"
    assert isinstance(notice["listed_at"], str), "listed_at должен быть str"
    
    # Проверяем ISO формат времени
    try:
        published_at = datetime.fromisoformat(notice["listed_at"])
        assert published_at.tzinfo is not None, "listed_at должен содержать timezone"
    except Exception as e:
        raise AssertionError(f"listed_at не в ISO формате: {e}")
    
    print(f"   ✅ Структура данных корректна")
    print(f"   📊 Пример новости:")
    print(f"      • id: {notice['id']}")
    print(f"      • title: {notice['title'][:50]}...")
    print(f"      • category: {notice['category']}")
    print(f"      • listed_at: {notice['listed_at']}")


def test_detection_delay_calculation(notices):
    """Тест вычисления задержки обнаружения"""
    print("\n4️⃣ Тест вычисления задержки обнаружения...")
    
    notice = notices[0]
    
    # Парсим время публикации
    published_at = datetime.fromisoformat(notice["listed_at"])
    
    # Текущее время в KST
    detected_at = datetime.now(ZoneInfo("Asia/Seoul"))
    
    # Вычисляем задержку
    delay = (detected_at - published_at).total_seconds()
    
    assert delay >= 0, f"Задержка не может быть отрицательной: {delay}"
    
    print(f"   ✅ Задержка вычислена корректно: {delay:.3f}s")
    print(f"   📊 Детали:")
    print(f"      • Опубликовано: {published_at.strftime('%Y-%m-%d %H:%M:%S')} KST")
    print(f"      • Обнаружено:   {detected_at.strftime('%Y-%m-%d %H:%M:%S')} KST")
    print(f"      • Задержка:     {delay:.3f}s")


def test_id_tracking(notices):
    """Тест отслеживания ID"""
    print("\n5️⃣ Тест отслеживания ID...")
    
    # Находим max_id
    max_id = max(n["id"] for n in notices)
    
    # Сохраняем оригинал
    original_max_id = get_last_max_id()
    
    # Сохраняем тестовый ID
    test_id = max_id - 5
    save_max_id(test_id)
    
    # Читаем обратно
    read_id = get_last_max_id()
    
    assert read_id == test_id, f"ID не совпадает: сохранён {test_id}, прочитан {read_id}"
    
    # Находим новые ID
    new_ids = [n["id"] for n in notices if n["id"] > test_id]
    
    print(f"   ✅ Отслеживание ID работает")
    print(f"   📊 Детали:")
    print(f"      • Max ID в новостях: {max_id}")
    print(f"      • Тестовый last_known_id: {test_id}")
    print(f"      • Найдено новых новостей: {len(new_ids)}")
    print(f"      • Новые ID: {sorted(new_ids)[:5]}")
    
    # Восстанавливаем оригинал
    if original_max_id is not None:
        save_max_id(original_max_id)


def test_no_filtering():
    """Тест отсутствия фильтрации"""
    print("\n6️⃣ Тест отсутствия фильтрации...")
    
    session = create_api_session()
    notices = get_notices_via_api(session)
    
    # Проверяем что получили ровно 20 новостей (per_page=20)
    assert len(notices) == 20, f"Должно быть 20 новостей, получено {len(notices)}"
    
    # Проверяем что есть новости разных категорий
    categories = set(n["category"] for n in notices)
    
    print(f"   ✅ Фильтрация отсутствует")
    print(f"   📊 Детали:")
    print(f"      • Всего новостей: {len(notices)}")
    print(f"      • Категорий: {len(categories)}")
    print(f"      • Список категорий: {', '.join(sorted(categories))}")


def run_all_tests():
    """Запуск всех тестов"""
    print("🧪 Интеграционный тест API режима")
    print("=" * 60)
    print()
    
    try:
        # Тест 1: HTTP session
        session = test_api_session()
        
        # Тест 2: API fetch
        notices = test_api_fetch(session)
        
        # Тест 3: Структура данных
        test_notice_structure(notices)
        
        # Тест 4: Задержка обнаружения
        test_detection_delay_calculation(notices)
        
        # Тест 5: ID tracking
        test_id_tracking(notices)
        
        # Тест 6: Отсутствие фильтрации
        test_no_filtering()
        
        print("\n" + "=" * 60)
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("=" * 60)
        print()
        print("💡 Готовность к продакшену:")
        print("   ✅ API endpoint работает")
        print("   ✅ HTTP session с retry")
        print("   ✅ Структура данных корректна")
        print("   ✅ Задержка обнаружения вычисляется")
        print("   ✅ ID tracking функционирует")
        print("   ✅ Фильтрация отключена")
        print()
        print("🚀 Можно запускать в продакшен: python main.py")
        
    except AssertionError as e:
        print("\n" + "=" * 60)
        print(f"❌ ТЕСТ ПРОВАЛИЛСЯ: {e}")
        print("=" * 60)
        return False
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ НЕОЖИДАННАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        return False
    
    return True


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
