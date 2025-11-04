# 📖 Пошаговая инструкция: Поиск WebSocket/API на Upbit

## 🎯 Цель

Найти более быстрый способ получения новостей Upbit через WebSocket или API вместо HTML парсинга.

**Текущая скорость**: 1.5 секунды  
**Целевая скорость**: < 0.5 секунды

---

## 🛠️ Необходимые инструменты

- Google Chrome (или Chromium)
- Доступ к интернету

---

## 📋 Часть 1: Поиск WebSocket

### Шаг 1: Открыть Chrome DevTools

1. Откройте Chrome
2. Перейдите на страницу: https://upbit.com/service_center/notice
3. Нажмите **F12** (или правой кнопкой → Inspect)

### Шаг 2: Настройка Network tab

1. Откройте вкладку **Network** в DevTools
2. В фильтре выберите **WS** (WebSocket)
3. Убедитесь что **Preserve log** включен (галочка)

### Шаг 3: Обновить страницу

1. Нажмите **F5** для обновления страницы
2. Наблюдайте за Network tab

### Шаг 4: Анализ WebSocket соединений

**Если видите WebSocket соединение**:

```
✅ НАЙДЕН WEBSOCKET!

URL будет выглядеть примерно так:
- wss://upbit.com/websocket
- wss://api.upbit.com/ws
- wss://stream.upbit.com/...
```

**Что делать дальше**:

1. Кликните на WebSocket соединение
2. Перейдите на вкладку **Messages**
3. Посмотрите формат сообщений
4. Проверьте, передаются ли там новости

**Пример сообщения**:
```json
{
  "type": "notice",
  "id": "12345",
  "title": "Новая новость",
  "created_at": "2024-01-01T12:00:00Z"
}
```

5. **СКОПИРУЙТЕ**:
   - URL WebSocket
   - Примеры 2-3 сообщений
   - Формат данных

**Если НЕ видите WebSocket**:
```
❌ WebSocket не найден
→ Переходим к поиску API
```

---

## 📋 Часть 2: Поиск API Endpoints

### Шаг 1: Настройка фильтра

1. В Network tab измените фильтр на **Fetch/XHR**
2. Убедитесь что **Preserve log** включен
3. Очистите логи (кнопка 🚫)

### Шаг 2: Обновить страницу

1. Нажмите **F5**
2. Наблюдайте за запросами

### Шаг 3: Поиск нужного API

Ищите запросы содержащие:
- `notice`
- `announcement`
- `board`
- `list`
- `feed`

**Пример того что искать**:
```
✅ ХОРОШИЕ ПРИМЕРЫ:
- https://api.upbit.com/v1/notices
- https://upbit.com/api/service_center/notices
- https://api-manager.upbit.com/api/v1/board/list

❌ НЕ ТО:
- https://upbit.com/static/css/...
- https://upbit.com/images/...
```

### Шаг 4: Проверка Response

1. Кликните на найденный запрос
2. Перейдите на вкладку **Response**
3. Проверьте что это JSON с новостями

**Пример правильного Response**:
```json
{
  "success": true,
  "data": {
    "notices": [
      {
        "id": "12345",
        "title": "Новость 1",
        "created_at": "2024-01-01T12:00:00Z"
      },
      {
        "id": "12346",
        "title": "Новость 2",
        "created_at": "2024-01-01T12:30:00Z"
      }
    ]
  }
}
```

### Шаг 5: Проверка Headers

1. Перейдите на вкладку **Headers**
2. Проверьте **Request Headers**
3. Посмотрите нужны ли специальные заголовки

**Что проверить**:
```
✅ Важно записать:
- URL запроса
- Method (GET/POST)
- Query параметры (?page=1&limit=20)
- Нужна ли авторизация (Authorization header)
- Cookies
```

4. **СКОПИРУЙТЕ**:
   - Полный URL
   - Request Headers
   - Пример Response

---

## 📋 Часть 3: Проверка RSS Feed

### Попробовать открыть URLs

Откройте в новой вкладке каждый URL:

1. https://upbit.com/service_center/notice/rss
2. https://upbit.com/rss/notice
3. https://upbit.com/feed/notices
4. https://upbit.com/api/notices/rss

**Если видите XML**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Upbit Notices</title>
    <item>
      <title>Новость 1</title>
      <link>https://upbit.com/service_center/notice?id=12345</link>
      <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
```

✅ **RSS НАЙДЕН!** - Скопируйте URL

---

## 📋 Часть 4: Проверка прямых API URLs

### Попробовать открыть

Откройте каждый URL в браузере:

1. https://api.upbit.com/v1/notices
2. https://upbit.com/api/v1/notices
3. https://api-manager.upbit.com/api/v1/notices
4. https://api.upbit.com/v1/announcements

**Если видите JSON с новостями**:

✅ **API НАЙДЕН!** - Скопируйте URL и пример Response

---

## 📝 Запись результатов

### Создайте файл `research_findings.txt`

```
=== РЕЗУЛЬТАТЫ ИССЛЕДОВАНИЯ ===

Дата: __________
Исследователь: __________

--- WebSocket ---
Найден: ДА / НЕТ
URL: __________
Пример сообщения:


--- API Endpoint ---
Найден: ДА / НЕТ
URL: __________
Method: GET / POST
Headers:


Response пример:


--- RSS Feed ---
Найден: ДА / НЕТ
URL: __________

--- Заметки ---

```

---

## 🎯 Что делать с результатами

### Если найден WebSocket ✅

**Приоритет: ВЫСОКИЙ**

Создайте новую задачу:
```
Название: Implement WebSocket for instant updates
Описание: Найден WebSocket: [URL]
Ожидаемое ускорение: 15x (1.5s → 0.1s)
```

### Если найден API ✅

**Приоритет: ВЫСОКИЙ**

Создайте новую задачу:
```
Название: Migrate to direct API requests
Описание: Найден API: [URL]
Ожидаемое ускорение: 3-5x (1.5s → 0.3-0.5s)
```

### Если найден RSS ✅

**Приоритет: СРЕДНИЙ**

Создайте новую задачу:
```
Название: Migrate to RSS parsing
Описание: Найден RSS: [URL]
Ожидаемое ускорение: 2-3x (1.5s → 0.5-0.7s)
```

### Если ничего не найдено ❌

**Вывод**: Текущий метод (Selenium) уже оптимален

**Возможные действия**:
1. Связаться с поддержкой Upbit для получения API
2. Продолжить использовать текущий метод (< 1.5s уже хорошо)
3. Рассмотреть альтернативные источники данных

---

## 💡 Советы

### Как не пропустить API

1. **Прокрутите страницу** - некоторые API вызовы срабатывают при скролле
2. **Кликните на новость** - может быть отдельный API для деталей
3. **Подождите 10-15 секунд** - могут быть периодические обновления
4. **Попробуйте другие страницы**:
   - https://upbit.com/service_center/announcement
   - https://upbit.com/service_center/inquiry
5. **Посмотрите исходный код страницы** (Ctrl+U):
   - Ищите "api", "websocket", "ws://", "wss://"

### Проверка работоспособности API

Если нашли API URL, проверьте его через:

```bash
# Linux/Mac
curl "https://api.upbit.com/v1/notices"

# Windows PowerShell
Invoke-WebRequest "https://api.upbit.com/v1/notices"
```

Или через Python:
```python
import requests
response = requests.get("https://api.upbit.com/v1/notices")
print(response.json())
```

---

## ❓ FAQ

**Q: Я не вижу WebSocket в списке**  
A: Это нормально, не все сайты используют WebSocket. Переходите к поиску API.

**Q: Я вижу много API запросов, какой выбрать?**  
A: Ищите тот, который возвращает список новостей с ID. Обычно в URL есть "notice" или "list".

**Q: API возвращает ошибку 401/403**  
A: Скопируйте все Headers из браузера, может требоваться авторизация или cookies.

**Q: Можно ли автоматизировать поиск?**  
A: Да, скрипт `discover_websocket.py` делает это, но требует Chrome установку.

---

## 📞 Поддержка

Если возникли вопросы или нашли что-то интересное:

1. Создайте issue в репозитории
2. Приложите скриншот Network tab
3. Скопируйте пример Request/Response

---

*Удачи в исследовании! 🚀*
