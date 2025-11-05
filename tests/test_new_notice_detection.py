#!/usr/bin/env python3
"""
Тест обнаружения новых новостей

Симулирует обнаружение новой новости путём временного понижения max_id
"""

import os
import time
from main import create_api_session, get_notices_via_api, process_new_notices, get_last_max_id, save_max_id


def test_new_notice_detection():
    """Тестирует обнаружение новой новости"""
    print("🧪 Тест обнаружения новых новостей")
    print("=" * 60)
    print()
    
    # Создаем session
    session = create_api_session()
    print("✅ HTTP session создана")
    print()
    
    # Получаем текущие новости
    print("📡 Получаем текущие новости...")
    notices = get_notices_via_api(session)
    
    if not notices:
        print("❌ Не удалось получить новости")
        return
    
    print(f"✅ Получено {len(notices)} новостей")
    
    # Находим текущий max_id
    current_max_id = max(n["id"] for n in notices)
    print(f"📊 Текущий max_id: {current_max_id}")
    print()
    
    # Сохраняем оригинальный max_id если есть
    original_max_id = get_last_max_id()
    print(f"📊 Оригинальный max_id в файле: {original_max_id}")
    print()
    
    # Устанавливаем max_id ниже текущего на 2
    test_max_id = current_max_id - 2
    print(f"🔧 Устанавливаем тестовый max_id: {test_max_id}")
    print(f"   (на 2 ниже текущего, чтобы симулировать 2 новые новости)")
    save_max_id(test_max_id)
    print()
    
    # Ждём секунду
    time.sleep(1)
    
    # Теперь обрабатываем новости - должны обнаружить 2 новые
    print("🔍 Обрабатываем новости (должны обнаружить 2 новые)...")
    print()
    
    process_new_notices(notices, session)
    
    print()
    print("=" * 60)
    print("✅ Тест завершён")
    print()
    
    # Восстанавливаем оригинальный max_id
    if original_max_id is not None:
        save_max_id(original_max_id)
        print(f"🔧 Восстановлен оригинальный max_id: {original_max_id}")
    
    print()
    print("💡 Проверьте логи выше на наличие уведомлений о новых новостях")
    print("   Должны быть записи вида:")
    print("   🆕 НОВАЯ НОВОСТЬ #XXXX")
    print("   ⏱️ Задержка обнаружения: X.XXXs")


if __name__ == "__main__":
    test_new_notice_detection()
