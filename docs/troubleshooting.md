# Troubleshooting Guide

This guide helps diagnose and resolve common issues with the Upbit Notice Bot.

## Quick Diagnosis

### Health Check Script
```bash
#!/bin/bash
# quick-health-check.sh

echo "=== Upbit Notice Bot Health Check ==="
echo "Time: $(date)"

# Check if running
if pgrep -f "python3 main.py" > /dev/null; then
    echo "✅ Bot process is running"
else
    echo "❌ Bot process is NOT running"
    exit 1
fi

# Check last log entry
if [ -f "logs/bot.log" ]; then
    echo "📋 Last log entry:"
    tail -1 logs/bot.log
else
    echo "❌ No log file found"
fi

# Check last notice time
if [ -f "last_notice.txt" ]; then
    last_id=$(cat last_notice.txt)
    echo "📄 Last notice ID: $last_id"
else
    echo "❌ No state file found"
fi

# Test API connectivity
echo "🌐 Testing API connectivity..."
if curl -s --max-time 5 "https://api-manager.upbit.com/v1/notices?page=1&per_page=1" > /dev/null; then
    echo "✅ API is reachable"
else
    echo "❌ API is NOT reachable"
fi

echo "=== Health Check Complete ==="
```

## Common Issues

### 1. Bot Not Starting

#### Symptoms
- Process exits immediately
- No log files created
- Systemd service fails

#### Diagnosis
```bash
# Check Python environment
python3 --version
pip3 list | grep -E "(requests|selenium|beautifulsoup)"

# Check configuration
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('TELEGRAM_TOKEN:', 'SET' if os.getenv('TELEGRAM_TOKEN') else 'MISSING')
print('TELEGRAM_CHAT_ID:', 'SET' if os.getenv('TELEGRAM_CHAT_ID') else 'MISSING')
"

# Test import
python3 -c "
try:
    import main
    print('✅ Main module imports successfully')
except Exception as e:
    print(f'❌ Import error: {e}')
"
```

#### Solutions
```bash
# Fix environment
pip3 install -r requirements.txt
cp .env.example .env
# Edit .env with correct values

# Fix permissions
chmod +x main.py
chmod 755 logs/

# Fix systemd (if using)
sudo systemctl daemon-reload
sudo systemctl restart upbit-notice-bot
```

### 2. No Telegram Notifications

#### Symptoms
- Bot runs but no notifications arrive
- Logs show "New notice detected" but no "Telegram sent"
- Telegram bot shows "can't send message"

#### Diagnosis
```bash
# Test Telegram API
python3 -c "
import requests
import os
from dotenv import load_dotenv
load_dotenv()

token = os.getenv('TELEGRAM_TOKEN')
chat_id = os.getenv('TELEGRAM_CHAT_ID')

try:
    url = f'https://api.telegram.org/bot{token}/getMe'
    r = requests.get(url, timeout=5)
    print('Bot info:', r.json())
    
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    data = {'chat_id': chat_id, 'text': 'Test message from bot'}
    r = requests.post(url, json=data, timeout=5)
    print('Send result:', r.json())
except Exception as e:
    print(f'Telegram error: {e}')
"
```

#### Solutions
```bash
# Verify bot token
# 1. Talk to @BotFather on Telegram
# 2. Get new token if needed
# 3. Update .env file

# Verify chat ID
# 1. Send message to your bot first
# 2. Use: https://api.telegram.org/bot<TOKEN>/getUpdates
# 3. Extract chat_id from response

# Check bot privacy settings
# 1. Go to @BotFather → /mybots → [Your Bot] → Bot Settings
# 2. Turn OFF "Group Privacy" if sending to groups
```

### 3. API Mode Failures

#### Symptoms
- Frequent API → HTML transitions
- High failure rates in logs
- Slow response times

#### Diagnosis
```bash
# Test API directly
curl -v "https://api-manager.upbit.com/v1/notices?page=1&per_page=5" | jq .

# Check network connectivity
ping api-manager.upbit.com
traceroute api-manager.upbit.com

# Monitor API performance
python3 -c "
import time
import requests
for i in range(5):
    start = time.time()
    try:
        r = requests.get('https://api-manager.upbit.com/v1/notices?page=1&per_page=1', timeout=5)
        elapsed = time.time() - start
        print(f'Request {i+1}: {r.status_code}, {elapsed:.3f}s')
    except Exception as e:
        elapsed = time.time() - start
        print(f'Request {i+1}: ERROR - {e} ({elapsed:.3f}s)')
    time.sleep(1)
"
```

#### Solutions
```bash
# Adjust thresholds
export UPBIT_API_ERROR_THRESHOLD=10  # More tolerant
export UPBIT_API_SLEEP_MS=200,400    # Slower polling

# Force API mode (temporary)
python3 main.py --api --no-autofallback

# Check for rate limiting
# Monitor logs for "429" status codes
```

### 4. HTML Mode Issues

#### Symptoms
- Selenium crashes
- Chrome driver issues
- Memory leaks

#### Diagnosis
```bash
# Test Chrome driver
python3 -c "
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

try:
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
    driver.get('https://www.google.com')
    print(f'Chrome test: SUCCESS - Title: {driver.title}')
    driver.quit()
except Exception as e:
    print(f'Chrome test: FAILED - {e}')
"

# Check Chrome installation
google-chrome --version
chromedriver --version
```

#### Solutions
```bash
# Update Chrome and driver
sudo apt update
sudo apt install -y google-chrome-stable
pip install --upgrade webdriver-manager

# Fix display issues (for headless)
export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &

# Add memory limits
python3 main.py --html --max-memory 300
```

### 5. Performance Issues

#### Symptoms
- High CPU usage
- Memory leaks
- Slow response times

#### Diagnosis
```bash
# Monitor resources
top -p $(pgrep -f "python3 main.py")
ps aux | grep "python3 main.py"
cat /proc/$(pgrep -f "python3 main.py")/status | grep -E "(VmRSS|VmSize|Threads)"

# Check log patterns
grep "Cycle.*s" logs/bot.log | tail -20
grep -E "(ERROR|WARN)" logs/bot.log | tail -10

# Profile performance
python3 -c "
import time
import cProfile
import pstats

def profile_bot():
    from main import main
    main()

cProfile.run('profile_bot()', 'profile_output')
stats = pstats.Stats('profile_output')
stats.sort_stats('cumulative').print_stats(10)
"
```

#### Solutions
```bash
# Optimize timing
export UPBIT_API_SLEEP_MS=200,300    # Reduce API calls
export UPBIT_HTML_REFRESH_MS=1000,1500  # Slower HTML refresh

# Force API mode (more efficient)
python3 main.py --api --no-autofallback

# Restart service periodically
# Add to crontab: 0 */6 * * * systemctl restart upbit-notice-bot
```

## Debug Mode

### Enable Debug Logging
```bash
# Set debug environment
export UPBIT_DEBUG=1
export UPBIT_VERBOSE=1

# Run with debug output
python3 main.py --api --debug

# Or modify logging level in main.py
logging.getLogger().setLevel(logging.DEBUG)
```

### Debug Scripts

#### API Debug
```bash
#!/bin/bash
# debug-api.sh

echo "=== API Debug ==="
echo "Testing API endpoint..."

for page in {1..3}; do
    echo "Page $page:"
    curl -s "https://api-manager.upbit.com/v1/notices?page=$page&per_page=5" | \
        jq '.data[0] | {id, title, published_at}'
    echo "---"
done
```

#### HTML Debug
```bash
#!/bin/bash
# debug-html.sh

echo "=== HTML Debug ==="

python3 -c "
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth
import time

options = Options()
options.add_argument('--headless')
driver = webdriver.Chrome(options=options)
stealth(driver,
    languages=['en-US', 'en'],
    vendor='Google Inc.',
    platform='Win32',
    webgl_vendor='Intel Inc.',
    renderer='Intel Iris OpenGL Engine',
    fix_hairline=True)

try:
    print('Loading page...')
    driver.get('https://upbit.com/service_center/notice')
    time.sleep(2)
    
    print('Page title:', driver.title)
    print('Current URL:', driver.current_url)
    
    # Check for notices
    notices = driver.find_elements('css selector', 'a[href*=\"/service_center/notice?id=\"]')
    print(f'Found {len(notices)} notice links')
    
    if notices:
        print('First notice:', notices[0].text)
    
    # Save HTML for inspection
    with open('debug_page.html', 'w') as f:
        f.write(driver.page_source)
    print('Page saved to debug_page.html')
    
except Exception as e:
    print(f'Error: {e}')
finally:
    driver.quit()
"
```

## Recovery Procedures

### Full Reset
```bash
#!/bin/bash
# reset-bot.sh

echo "=== Resetting Upbit Notice Bot ==="

# Stop service
sudo systemctl stop upbit-notice-bot

# Backup current state
cp last_notice.txt last_notice.txt.backup.$(date +%Y%m%d_%H%M%S)

# Clear logs (optional)
# > logs/bot.log
# > logs/performance_metrics.log

# Reset state (caution: may cause duplicates)
echo "0" > last_notice.txt

# Restart service
sudo systemctl start upbit-notice-bot

echo "=== Reset Complete ==="
```

### Emergency Fallback
```bash
# Force HTML mode if API is completely down
export UPBIT_MODE=html
export UPBIT_NO_AUTOFALLBACK=1
python3 main.py --html --no-autofallback
```

## Getting Help

### Collect Diagnostic Information
```bash
#!/bin/bash
# collect-diagnostics.sh

DIAG_DIR="diagnostics_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$DIAG_DIR"

echo "Collecting diagnostics..."

# System info
uname -a > "$DIAG_DIR/system.txt"
python3 --version > "$DIAG_DIR/python.txt"
pip3 list > "$DIAG_DIR/packages.txt"

# Configuration
cp .env "$DIAG_DIR/env.txt"  # Remove sensitive data before sharing

# Logs
tail -100 logs/bot.log > "$DIAG_DIR/bot.log"
tail -50 logs/performance_metrics.log > "$DIAG_DIR/performance.log"

# State
cp last_notice.txt "$DIAG_DIR/last_notice.txt"

# Process info
ps aux | grep python > "$DIAG_DIR/processes.txt"

echo "Diagnostics saved to: $DIAG_DIR"
echo "Please review and remove sensitive data before sharing."
```

### Log Analysis
```bash
# Analyze common patterns
echo "=== Recent Errors ==="
grep -E "(ERROR|Exception|Failed)" logs/bot.log | tail -10

echo "=== Mode Transitions ==="
grep "TRANSITION" logs/bot.log | tail -10

echo "=== Performance Summary ==="
grep "Cycle.*s" logs/bot.log | tail -20 | awk '{print $NF}' | sort -n

echo "=== API Failures ==="
grep "API.*ERROR" logs/bot.log | tail -10
```
