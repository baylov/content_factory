# Operations Guide

This guide covers operational aspects of running the Upbit Notice Bot in production.

## Monitoring and Logs

### Log Files

The bot generates several log files in the `logs/` directory:

- `bot.log` - Main operational logs with timestamps
- `performance_metrics.log` - Detailed performance metrics

### Log Interpretation

#### API Mode Logs
```
[2024-01-15 10:30:15] [API] Cycle #123: 0.045s ⚡ 5 notices (max_id: 12345)
[2024-01-15 10:30:15] [API] New notice detected: ID=12346, delay=0.032s
[2024-01-15 10:30:15] [API] Telegram notification sent successfully
```

#### HTML Mode Logs (Fallback)
```
[2024-01-15 10:30:15] [HTML] Cycle #124: 1.234s 5 notices (max_id: 12346)
[2024-01-15 10:30:15] [HTML] Page loaded in 0.823s, parsing in 0.045s
```

#### Mode Transition Logs
```
[2024-01-15 10:30:15] [TRANSITION] API → HTML: 5 consecutive API failures detected
[2024-01-15 10:31:15] [TRANSITION] HTML → API: 20 consecutive successful health checks
```

### Performance Metrics

Every 60 seconds, the bot outputs summary metrics:

```
[2024-01-15 10:31:00] [SUMMARY] API Mode - Cycles: 600, Avg: 0.067s, P95: 0.123s
[2024-01-15 10:31:00] [SUMMARY] HTML Mode - Cycles: 0, Avg: N/A, P95: N/A
[2024-01-15 10:31:00] [SUMMARY] Transitions: 0, Failures: 0, Recovery: 100%
```

## State Management

### last_notice.txt

This file tracks the last processed notice ID to prevent duplicates:

```bash
# Check current state
cat last_notice.txt
12345

# Reset if needed (caution: may cause duplicate notifications)
echo "0" > last_notice.txt
```

### State Continuity

The bot maintains state continuity across mode switches:
- API and HTML modes use the same `last_notice.txt`
- Mode transitions preserve the last known ID
- No duplicate notifications during transitions

## Performance Expectations

### API Mode (Default)
- **Cycle Time**: 30-150ms typical
- **CPU Usage**: 1-3%
- **Memory Usage**: 10-20MB
- **Network**: Minimal HTTP requests every 100-300ms

### HTML Mode (Fallback)
- **Cycle Time**: 1.0-1.8s typical
- **CPU Usage**: 15-25%
- **Memory Usage**: 200-300MB
- **Network**: Full page loads every 800-1200ms

## Rate Limiting

### API Rate Limits
- Default polling: 100-300ms with 20-40ms jitter
- Built-in exponential backoff for failures
- Automatic fallback on persistent failures

### HTML Rate Limits
- Page refresh: 800-1200ms with jitter
- Human-like delays to avoid detection
- Chrome headless with stealth mode

## Troubleshooting Operations

### Common Issues

#### Bot Stops Responding
```bash
# Check logs
tail -f logs/bot.log

# Check process
ps aux | grep python

# Restart if needed
systemctl restart upbit-notice-bot
```

#### No Notifications
```bash
# Check last notice ID
cat last_notice.txt

# Check Telegram connectivity
python3 -c "import requests; print(requests.get('https://api.telegram.org/bot<TOKEN>/getMe').json())"

# Check API connectivity
curl -s "https://api-manager.upbit.com/v1/notices?page=1&per_page=1" | jq .
```

#### High Memory Usage
```bash
# Check if stuck in HTML mode
grep "HTML Mode" logs/bot.log | tail -10

# Force API mode
UPBIT_MODE=api python3 main.py --api --no-autofallback
```

### Health Checks

#### Manual Health Check
```bash
# API health
python3 -c "
import requests
try:
    r = requests.get('https://api-manager.upbit.com/v1/notices?page=1&per_page=1', timeout=5)
    print(f'API Status: {r.status_code}, Response time: {r.elapsed.total_seconds():.3f}s')
except Exception as e:
    print(f'API Error: {e}')
"

# HTML health
python3 -c "
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
driver = webdriver.Chrome(options=options)
try:
    driver.get('https://upbit.com/service_center/notice')
    print(f'HTML Status: Loaded, Title: {driver.title}')
except Exception as e:
    print(f'HTML Error: {e}')
finally:
    driver.quit()
"
```

## Backup and Recovery

### Essential Files to Backup
- `.env` - Configuration and secrets
- `last_notice.txt` - State tracking
- `logs/` - Historical logs (optional)

### Recovery Procedures

#### Fresh Server Setup
```bash
# Restore configuration
cp .env.backup .env

# Restore state
cp last_notice.txt.backup last_notice.txt

# Start service
systemctl start upbit-notice-bot
```

#### After Major Outage
```bash
# Check for missed notices during downtime
python3 -c "
import requests
from datetime import datetime, timedelta

# Get last known ID
with open('last_notice.txt') as f:
    last_id = int(f.read().strip())

# Check for newer notices
r = requests.get('https://api-manager.upbit.com/v1/notices?page=1&per_page=50')
notices = r.json().get('data', [])

new_notices = [n for n in notices if n['id'] > last_id]
print(f'Missed notices: {len(new_notices)}')
for notice in new_notices[:5]:  # Show first 5
    print(f'ID: {notice[\"id\"]}, Title: {notice[\"title\"][:50]}...')
"
```

## Maintenance

### Regular Tasks
- Monitor log file sizes (rotate if needed)
- Check Telegram bot token validity
- Verify notification delivery
- Update dependencies monthly

### Log Rotation
```bash
# Add to logrotate
cat > /etc/logrotate.d/upbit-notice-bot << EOF
/home/user/upbit-notice-bot/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 user user
}
EOF
```

### Updates
```bash
# Update dependencies
pip install -r requirements.txt --upgrade

# Restart service
systemctl restart upbit-notice-bot

# Verify operation
tail -f logs/bot.log
```
