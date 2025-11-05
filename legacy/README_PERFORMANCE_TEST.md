# Performance Test Guide

## Overview
This document explains how to test the performance improvements made to the Upbit Notice Bot.

## Test Script
`test_performance.py` - Measures actual page load times with the new optimizations

## Running the Test

### Prerequisites
- Python 3.x
- Chrome/Chromium browser installed
- Required packages installed: `pip install -r requirements.txt`

### Execute Test
```bash
python3 test_performance.py
```

## What the Test Does

1. **Initializes optimized Chrome driver** with all performance flags
2. **Performs 4 load tests:**
   - 1 initial page load
   - 3 page refreshes
3. **Measures timing for each stage:**
   - driver.get() / driver.refresh() time
   - WebDriverWait for news list
   - Total time per operation
4. **Calculates statistics:**
   - Average refresh time
   - Min/max refresh times
   - Performance assessment

## Expected Results

### Target Performance
- **Initial load**: < 1 second
- **Refresh**: < 0.5 seconds (target) or < 0.8 seconds (acceptable)
- **Average**: ~0.5-0.7 seconds

### Success Criteria
- ✅ **ОТЛИЧНО**: < 0.5 sec
- ✅ **ХОРОШО**: < 1 sec
- ⚠️ **ПРИЕМЛЕМО**: 1-2 sec
- ❌ **МЕДЛЕННО**: > 2 sec

## Sample Output

```
============================================================
ТЕСТ ОПТИМИЗИРОВАННОЙ ЗАГРУЗКИ
============================================================

📡 Тест #1: Первая загрузка страницы
  ⏱️ driver.get(): 0.421s
  ⏱️ Wait for list: 0.053s
  ⏱️ ИТОГО: 0.474s
  ✅ ОТЛИЧНО: < 0.5 сек!
  📊 Найдено ссылок: 50

🔄 Тест #2: Refresh #1
  ⏱️ driver.refresh(): 0.387s
  ⏱️ Wait for list: 0.045s
  ⏱️ ИТОГО: 0.432s
  ✅ ОТЛИЧНО: < 0.5 сек!

...

============================================================
📊 СТАТИСТИКА
============================================================
Средний refresh: 0.456s
Минимальный: 0.412s
Максимальный: 0.523s

✅ ИТОГО:
  🎯 ЦЕЛЬ ДОСТИГНУТА! Средняя скорость 0.456s < 0.5s
```

## Troubleshooting

### ChromeDriver Issues
If you get a ChromeDriver error:
1. Ensure Chrome/Chromium is installed
2. Update webdriver-manager: `pip install --upgrade webdriver-manager`
3. Check Chrome version compatibility

### Timeout Errors
If pages timeout:
1. Check your internet connection
2. Try increasing timeout in test script (line with `WebDriverWait(driver, 5)`)
3. Verify Upbit website is accessible

### Slow Performance
If results are slower than expected:
1. Check network latency: `ping upbit.com`
2. Ensure no other heavy processes running
3. Try running test multiple times (first run may be slower)

## Comparing Before/After

### Before Optimizations
- Page load: 2-2.7 seconds
- Refresh: 2+ seconds
- Full cycle: 2.2-3 seconds

### After Optimizations (Expected)
- Page load: 0.3-0.8 seconds
- Refresh: 0.3-0.8 seconds
- Full cycle: 0.5-1.2 seconds

### Improvement
- **~3.5x faster** ⚡
- More consistent performance
- Detailed timing visibility

## Integration Testing

After running performance test, verify the actual bot:

```bash
# 1. Set up .env file
cp .env.example .env
# Edit .env with your Telegram credentials

# 2. Run the bot
python3 main.py

# 3. Watch the logs for timing metrics:
# Look for lines with ⏱️ emoji
```

## Monitoring in Production

Check `logs/bot.log` for performance metrics:
```
⏱️ Время загрузки страницы: 0.421s
⏱️ Время ожидания списка новостей: 0.053s
⏱️ ИТОГО время загрузки: 0.474s
✅ ОТЛИЧНО: Загрузка < 0.5 сек!
```

And during refresh cycles:
```
🔄 Refresh #1 в 14:23:45...
  ⏱️ Refresh страницы: 0.421s
  ⏱️ Ожидание списка: 0.053s
  ⏱️ Стабилизация: 0.101s
  ⏱️ ИТОГО refresh: 0.575s
  ✅ ХОРОШО: Refresh < 1 сек
  ⏱️ Парсинг ID: 0.012s
```

## Notes

- First load is often slightly slower than subsequent refreshes
- Network conditions affect timing
- Target of 0.3-0.5s may vary based on geographic location
- Metrics are logged for every refresh for continuous monitoring
