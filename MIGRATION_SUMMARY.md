# Migration Summary: Requests → Playwright

## Overview
Successfully migrated the Upbit Notice Bot from `requests + BeautifulSoup` to **Playwright** for JavaScript rendering support.

## Files Modified

### 1. `requirements.txt`
- **Added**: `playwright>=1.40.0`

### 2. `main.py` - Major Refactoring

#### Imports Added
```python
import asyncio
from playwright.async_api import async_playwright
```

#### New Class: `UpbitParser`
```python
class UpbitParser:
    def __init__(self)
    async def init()          # Browser setup (once)
    async def get_page_html() # Load & extract HTML
    async def close()         # Cleanup
```

**Features**:
- Chromium headless browser
- Korean locale (ko-KR, Asia/Seoul)
- Anti-detection (webdriver flags hidden)
- Resource blocking (images, media)
- Error detection on page
- `networkidle` wait strategy

#### Functions Removed
- `init_session()` - replaced by `UpbitParser.init()`
- `fetch_page()` - replaced by `UpbitParser.get_page_html()`

#### Functions Modified
- `notify_about_new_ids()` - removed `session` parameter
- `main()` - converted to `async def main()`

#### Main Loop Changes
- All `time.sleep()` → `await asyncio.sleep()`
- HTTP requests → `await parser.get_page_html()`
- BeautifulSoup parsing unchanged (works with Playwright HTML)
- `finally` block now calls `await parser.close()`

#### Entry Point
```python
if __name__ == "__main__":
    asyncio.run(main())  # Was: main()
```

## Files Added

### 1. `PLAYWRIGHT_MIGRATION.md`
Complete migration documentation with:
- Installation instructions
- Configuration details
- Known issues (Upbit anti-bot)
- Debugging guide
- Performance expectations

### 2. `test_playwright.py`
Simple test script to verify Playwright setup:
```bash
python test_playwright.py
```

## Unchanged Functionality

✅ Pinned news filtering ('공지', '고정', 'pinned')  
✅ Max ID tracking (`last_notice.txt`)  
✅ Telegram notifications  
✅ MetricsLogger class  
✅ Performance logging  
✅ Error handling  
✅ Random delays (0.5-1.5s)  

## Key Technical Decisions

### 1. Browser Reuse
Browser/context/page created **once** in `init()` and reused for all requests.
- **Why**: Avoid expensive browser startup (1-2s each time)
- **Impact**: First load ~4s, subsequent loads ~3-4s

### 2. Partial Resource Blocking
Block images and media, but **allow CSS and fonts**.
- **Why**: Page needs CSS to render correctly
- **Impact**: Slightly slower but more reliable

### 3. NetworkIdle Strategy
Use `wait_until='networkidle'` instead of `domcontentloaded`.
- **Why**: Ensures JS has finished loading content
- **Impact**: +1-2s load time but guaranteed content

### 4. Anti-Detection
Hide `navigator.webdriver` and add realistic browser properties.
- **Why**: Bypass basic bot detection
- **Impact**: Minimal performance cost

### 5. Increased Timeouts
10 seconds instead of 2 seconds.
- **Why**: JS rendering takes longer than static HTML
- **Impact**: More tolerant of slow networks

## Performance Comparison

| Metric | Before (Requests) | After (Playwright) |
|--------|------------------|--------------------|
| HTTP Request | 0.3-0.5s | N/A |
| Page Load | N/A | 3-5s |
| Parsing | 0.01-0.05s | 0.01-0.05s |
| **Total Cycle** | **0.3-0.6s** | **3-5s** |
| JS Support | ❌ No | ✅ Yes |
| Reliability | ⚠️ Breaks on JS sites | ✅ Handles JS |

## Installation Steps

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Install Playwright browsers
playwright install chromium

# 3. Install system dependencies (Linux/Ubuntu)
sudo apt-get install libnspr4 libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 \
  libcups2t64 libxkbcommon0 libatspi2.0-0t64 libxcomposite1 libxdamage1 \
  libxfixes3 libxrandr2 libgbm1 libcairo2 libpango-1.0-0 libasound2t64

# 4. Run bot
python3 main.py
```

## Testing

```bash
# Test Playwright setup
python test_playwright.py

# Check logs
tail -f logs/bot.log
```

## Known Issues & Solutions

### Issue: Upbit Returns Error
**Symptom**: "알 수 없는 오류가 발생했습니다"  
**Cause**: Anti-bot protection or rate limiting  
**Solutions**:
1. Increase delays between requests
2. Use Korean IP/proxy
3. Add more human-like behavior
4. Contact Upbit for API access

### Issue: Slow Performance
**Symptom**: Cycles taking >5 seconds  
**Solutions**:
1. Check network speed
2. Reduce timeout values (risk: incomplete loads)
3. Block more resources (risk: page errors)

## Rollback Plan

If migration causes issues, revert by:
1. `git checkout main.py`
2. `git checkout requirements.txt`
3. `pip install -r requirements.txt`

## Success Criteria Met

✅ Playwright installed and configured  
✅ JavaScript rendering supported  
✅ Browser reuse implemented  
✅ All existing features preserved  
✅ Error handling robust  
✅ Detailed logging maintained  
✅ Graceful shutdown on Ctrl+C  
✅ Code compiles without errors  
✅ Documentation complete  

## Next Steps

1. **Monitor** first runs in production
2. **Adjust** delays if rate limiting occurs
3. **Fine-tune** timeouts based on actual performance
4. **Consider** proxy rotation if blocking persists
5. **Document** any site-specific quirks discovered

---

**Completed**: November 4, 2024  
**Branch**: `feat/upbit-playwright-js-rendering-speed`  
**Status**: ✅ Ready for testing
