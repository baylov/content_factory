#!/usr/bin/env python3
"""
Тест скорости API endpoint

Проверяет:
1. Доступность API endpoint
2. Скорость ответа
3. Структуру данных
4. Количество новостей
"""

import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_session():
    """Создает session с retry механизмом"""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    return session


def test_api_endpoint():
    """Тестирует API endpoint"""
    print("🧪 Тест Upbit API Endpoint")
    print("=" * 60)
    print()
    
    url = "https://api-manager.upbit.com/api/v1/announcements"
    params = {
        "os": "web",
        "page": 1,
        "per_page": 20,
        "category": "all"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    
    session = create_session()
    
    print(f"📡 URL: {url}")
    print(f"📦 Params: {params}")
    print()
    
    # Выполняем 5 тестовых запросов
    times = []
    
    for i in range(5):
        print(f"Запрос #{i+1}... ", end="", flush=True)
        
        start_time = time.time()
        
        try:
            response = session.get(url, params=params, headers=headers, timeout=5)
            response.raise_for_status()
            
            elapsed = time.time() - start_time
            times.append(elapsed)
            
            data = response.json()
            
            if data.get("success"):
                notices = data["data"]["notices"]
                total_count = data["data"]["total_count"]
                
                print(f"✅ {elapsed*1000:.0f}ms ({len(notices)} новостей)")
                
                if i == 0:
                    # Показываем детали первого запроса
                    print()
                    print("📊 Структура данных:")
                    print(f"  • success: {data.get('success')}")
                    print(f"  • total_count: {total_count}")
                    print(f"  • total_pages: {data['data']['total_pages']}")
                    print(f"  • notices: {len(notices)} элементов")
                    print()
                    
                    if notices:
                        notice = notices[0]
                        print("📰 Пример новости (первая):")
                        print(f"  • id: {notice.get('id')}")
                        print(f"  • title: {notice.get('title')[:50]}...")
                        print(f"  • category: {notice.get('category')}")
                        print(f"  • listed_at: {notice.get('listed_at')}")
                        print(f"  • first_listed_at: {notice.get('first_listed_at')}")
                        print(f"  • need_new_badge: {notice.get('need_new_badge')}")
                        print(f"  • need_update_badge: {notice.get('need_update_badge')}")
                        print()
            else:
                print(f"❌ success=false")
                
        except requests.Timeout:
            print(f"⏱️ Timeout")
        except requests.ConnectionError as e:
            print(f"🔌 Connection error: {e}")
        except requests.HTTPError as e:
            print(f"❌ HTTP {e.response.status_code}")
        except Exception as e:
            print(f"❌ Error: {e}")
        
        # Пауза между запросами
        if i < 4:
            time.sleep(1)
    
    print()
    print("=" * 60)
    print("📊 СТАТИСТИКА")
    print("=" * 60)
    
    if times:
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        print(f"Всего запросов: {len(times)}")
        print(f"Средняя скорость: {avg_time*1000:.0f}ms")
        print(f"Минимум: {min_time*1000:.0f}ms")
        print(f"Максимум: {max_time*1000:.0f}ms")
        print()
        
        # Оценка
        if avg_time < 0.3:
            print("⚡ ОТЛИЧНО: < 300ms")
        elif avg_time < 0.5:
            print("✅ ХОРОШО: < 500ms")
        elif avg_time < 1.0:
            print("✅ ПРИЕМЛЕМО: < 1000ms")
        else:
            print(f"⚠️ МЕДЛЕННО: {avg_time*1000:.0f}ms")
        
        print()
        print("✅ API endpoint работает корректно!")
    else:
        print("❌ Все запросы завершились с ошибкой")


if __name__ == "__main__":
    test_api_endpoint()
