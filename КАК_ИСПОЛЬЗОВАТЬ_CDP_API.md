# Как использовать CDP API для ультра-быстрого парсинга

## 🚀 Быстрый старт

### Шаг 1: Обнаружение API endpoints

Первым делом нужно найти какие API использует Upbit:

```bash
python3 discover_api.py
```

**Результат:**
- Создастся файл `api_discovery.json` со списком найденных endpoints
- Логи сохранятся в `logs/api_discovery.log`

**Что искать в api_discovery.json:**
```json
{
  "api_candidates": [
    {
      "url": "https://api.upbit.com/v1/notices",  ← Это нужный endpoint!
      "status": 200,
      "mimeType": "application/json"
    }
  ]
}
```

### Шаг 2: Запуск тестов

Проверьте что всё работает:

```bash
python3 test_cdp_api.py
```

**Ожидаемый результат:**
```
✅ PASSED: API Discovery
✅ PASSED: API Interception
✅ PASSED: API vs HTML
Всего: 3/3 тестов пройдено
🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!
```

### Шаг 3: Использование в боте

Есть 3 варианта использования:

---

## Вариант 1: Автоматический (рекомендуется)

Бот сам попытается найти API и использует fallback на HTML если не получится.

**Изменения в main.py:**

Найдите строку:
```python
driver = init_driver()
```

Замените на:
```python
driver = init_driver(enable_cdp=True)
```

Найдите строку:
```python
all_ids = get_all_notice_ids(driver)
```

Замените на:
```python
all_ids = get_notices_from_api(driver) or get_all_notice_ids(driver)
```

**Что происходит:**
1. Попытка получить новости через API (< 1 сек)
2. Если не получилось → автоматический fallback на HTML (1.5-2 сек)

---

## Вариант 2: С известными endpoints (быстрее)

Если вы обнаружили стабильный API endpoint через `discover_api.py`, можно его указать явно.

**В начале main.py добавьте:**
```python
# API endpoints (найдены через discover_api.py)
KNOWN_API_ENDPOINTS = [
    'https://api.upbit.com/v1/notices',
    'https://upbit.com/api/v1/service_center/notices'
]
```

**Замените:**
```python
all_ids = get_notices_from_api(driver) or get_all_notice_ids(driver)
```

**На:**
```python
all_ids = get_notices_from_api(
    driver,
    known_endpoints=KNOWN_API_ENDPOINTS,
    max_wait=1.5  # Быстрее чем 2.0 по умолчанию
) or get_all_notice_ids(driver)
```

**Преимущества:**
- Быстрее находит нужный endpoint (не нужно искать среди всех)
- Меньше max_wait → ещё быстрее при сбое

---

## Вариант 3: Только HTML (без CDP)

Если CDP не работает или не нужен - оставьте как есть:

```python
driver = init_driver(enable_cdp=False)  # или просто init_driver()
all_ids = get_all_notice_ids(driver)
```

**Когда использовать:**
- Chrome/ChromeDriver не доступен
- CDP вызывает проблемы
- Скорость 1.5-2 сек устраивает

---

## 📊 Сравнение вариантов

| Вариант | Скорость (API) | Скорость (Fallback) | Надёжность | Сложность |
|---------|----------------|---------------------|------------|-----------|
| **1. Автоматический** | < 1 сек | 1.5-2 сек | ⭐⭐⭐⭐⭐ | Низкая |
| **2. С endpoints** | < 0.8 сек | 1.5-2 сек | ⭐⭐⭐⭐ | Средняя |
| **3. Только HTML** | - | 1.5-2 сек | ⭐⭐⭐⭐⭐ | Минимальная |

---

## 🎯 Рекомендация

**Для большинства случаев - Вариант 1 (Автоматический):**

```python
# В main.py

# 1. Инициализация с CDP
driver = init_driver(enable_cdp=True)

# 2. В первой загрузке
all_ids = get_notices_from_api(driver) or get_all_notice_ids(driver)

# 3. В цикле мониторинга
all_ids = get_notices_from_api(driver) or get_all_notice_ids(driver)
```

**Почему это лучше:**
- ✅ Работает автоматически (не нужно вручную искать endpoints)
- ✅ Быстро при успехе (< 1 сек)
- ✅ Надёжно при сбое (fallback на HTML)
- ✅ Минимум изменений в коде

---

## 📝 Примеры логов

### Успешный API перехват

```
⚡ API PARSING SUCCESS!
  📡 Endpoint: https://api.upbit.com/v1/notices...
  🔢 Найдено ID: 15 → [5710, 5709, 5708, 5707, 5706]...
  ⏱️ Время: Load 0.412s + Wait 0.156s + Parse 0.001s = 0.569s
  ✅ ⚡ ОТЛИЧНО: < 1 секунды!
```

### Fallback на HTML

```
⚠️ API endpoint не найден за 2.000s
   → Fallback на HTML парсинг
✅ Найдено 15 новостей (strategy: exact_id, total links: 35)
🔢 ID: [5710, 5709, 5708, 5707, 5706]...
⏱️ Время парсинга: 0.156s
```

---

## 🔧 Troubleshooting

### Проблема: API не находится

**Симптом:**
```
⚠️ API endpoint не найден за 2.000s
   → Fallback на HTML парсинг
```

**Решение:**
1. Это нормально! Upbit может не использовать публичные API
2. Fallback на HTML сработает автоматически
3. Или запустите `discover_api.py` для поиска endpoints

### Проблема: CDP не активируется

**Симптом:**
```
⚠️ CDP не удалось активировать: ...
  → Fallback на HTML парсинг
```

**Решение:**
1. Проверьте Chrome: `google-chrome --version`
2. Обновите Selenium: `pip install selenium>=4.0.0 --upgrade`
3. Или используйте Вариант 3 (только HTML)

### Проблема: JSON структура неизвестна

**Симптом:**
```
⚠️ Неизвестная структура JSON
   Доступные ключи: ['data', 'success', 'message']
```

**Решение:**
1. Скопируйте логи и JSON структуру
2. Добавьте новый вариант в `extract_ids_from_json()` в main.py
3. Или создайте issue с примером JSON

### Проблема: Медленно даже с CDP

**Симптом:**
```
⏱️ Время: Load 1.234s + Wait 0.856s + Parse 0.001s = 2.091s
⚠️ ПРИЕМЛЕМО: < 2 секунд
```

**Решение:**
1. Проверьте интернет-соединение
2. Upbit может быть перегружен
3. Используйте `known_endpoints` для ускорения
4. HTML fallback всё равно сработает

---

## 💡 Полезные советы

### 1. Периодически обновляйте api_discovery.json

Upbit может менять API endpoints. Раз в неделю запускайте:

```bash
python3 discover_api.py
```

### 2. Мониторьте метрики

Следите за логами - они покажут какой метод использовался:

- `⚡ API PARSING SUCCESS!` → использован CDP API (< 1 сек)
- `✅ Найдено X новостей (strategy: ...)` → использован HTML (1.5-2 сек)

### 3. Комбинируйте с существующими оптимизациями

CDP API работает вместе со всеми текущими оптимизациями:
- ✅ Stealth mode (обход блокировок)
- ✅ Page load strategy = 'eager'
- ✅ Блокировка изображений/CSS
- ✅ Smart waiting с polling 50ms

### 4. Тестируйте перед production

Всегда тестируйте изменения:

```bash
# Тест CDP
python3 test_cdp_api.py

# Тест основного бота
python3 main.py  # Ctrl+C после первого цикла
```

---

## 🎓 Как это работает

### CDP (Chrome DevTools Protocol)

1. Браузер отправляет все Network события в лог
2. Мы перехватываем эти события в реальном времени
3. Находим JSON API запросы с новостями
4. Получаем JSON напрямую (без парсинга HTML!)
5. Извлекаем ID новостей из JSON

### Fallback на HTML

Если CDP не сработал:
1. Используем старый проверенный метод
2. Загружаем страницу
3. Ждём появления элементов
4. Парсим HTML через JavaScript
5. Извлекаем ID из ссылок

**Результат:** Всегда работает! 🎉

---

## 📚 Дополнительно

- **Полная документация:** `CDP_API_README.md`
- **Детали реализации:** `CDP_IMPLEMENTATION_SUMMARY.md`
- **Тесты:** `test_cdp_api.py`
- **Discovery:** `discover_api.py`

---

## ✅ Checklist для внедрения

- [ ] Запустить `discover_api.py`
- [ ] Проверить `api_discovery.json`
- [ ] Запустить `test_cdp_api.py`
- [ ] Изменить `init_driver()` → `init_driver(enable_cdp=True)`
- [ ] Изменить `get_all_notice_ids()` → `get_notices_from_api() or get_all_notice_ids()`
- [ ] (Опционально) Добавить `KNOWN_API_ENDPOINTS`
- [ ] Протестировать основной бот
- [ ] Проверить метрики в логах
- [ ] Запустить в production

---

**Удачи с ультра-быстрым парсингом! ⚡**

Если возникнут вопросы - проверьте полную документацию в `CDP_API_README.md`
