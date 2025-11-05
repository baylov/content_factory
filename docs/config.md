# Configuration Guide

This guide covers all configuration options for the Upbit Notice Bot.

## Environment Variables

### Required Configuration

```bash
# Telegram Bot Token (required)
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Telegram Chat ID (required)
TELEGRAM_CHAT_ID=123456789
```

### Mode Configuration

```bash
# Default mode when no CLI flags specified
UPBIT_MODE=api                    # Options: api, html

# Disable auto-fallback between modes
UPBIT_NO_AUTOFALLBACK=0            # 0=enabled (default), 1=disabled
```

### Auto-Fallback Thresholds

```bash
# Number of consecutive API failures before switching to HTML
UPBIT_API_ERROR_THRESHOLD=5       # Default: 5

# Number of consecutive successful health checks before returning to API
UPBIT_API_RECOVERY_OK=20          # Default: 20
```

### Timing Configuration (milliseconds)

```bash
# API polling interval range (min,max)
UPBIT_API_SLEEP_MS=100,300         # Default: 100,300

# HTML page refresh interval range (min,max)  
UPBIT_HTML_REFRESH_MS=800,1200    # Default: 800,1200

# Jitter range for both modes (min,max)
UPBIT_JITTER_MS=20,40              # Default: 20,40
```

## CLI Arguments

### Mode Selection

```bash
# Force API mode (overrides UPBIT_MODE)
python3 main.py --api

# Force HTML/Legacy mode (overrides UPBIT_MODE)
python3 main.py --html
python3 main.py --legacy          # Alias for --html

# Disable auto-fallback
python3 main.py --no-autofallback
```

### Priority Order

1. CLI flags (`--api`, `--html`, `--no-autofallback`)
2. Environment variables (`UPBIT_MODE`, `UPBIT_NO_AUTOFALLBACK`)
3. Default values (`api` mode, auto-fallback enabled)

## Configuration Examples

### Production Setup (Recommended)
```bash
# .env file
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
UPBIT_MODE=api                     # Default to API
UPBIT_API_ERROR_THRESHOLD=3        # More sensitive to API issues
UPBIT_API_RECOVERY_OK=10           # Faster recovery to API
UPBIT_API_SLEEP_MS=150,250         # Conservative polling
```

### Development Setup
```bash
# .env file
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
UPBIT_MODE=api                     # Start with API for testing
UPBIT_NO_AUTOFALLBACK=1            # Disable fallback for debugging
UPBIT_API_SLEEP_MS=50,100          # Faster polling for testing
```

### High-Reliability Setup
```bash
# .env file
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
UPBIT_MODE=api                     # Prefer API
UPBIT_API_ERROR_THRESHOLD=2        # Very sensitive to failures
UPBIT_API_RECOVERY_OK=30           # Require stable recovery
UPBIT_HTML_REFRESH_MS=600,1000     # Faster HTML fallback
```

### Testing HTML Mode
```bash
# .env file
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
UPBIT_MODE=html                    # Force HTML mode
UPBIT_NO_AUTOFALLBACK=1            # Stay in HTML mode
UPBIT_HTML_REFRESH_MS=500,800      # Faster for testing
```

## Timing Details

### API Mode Timing
- **Base Sleep**: 100-300ms (configurable via `UPBIT_API_SLEEP_MS`)
- **Jitter**: ±20-40ms (configurable via `UPBIT_JITTER_MS`)
- **Total Cycle**: Base + Jitter + Network Latency + Processing
- **Typical Range**: 30-150ms

### HTML Mode Timing
- **Base Refresh**: 800-1200ms (configurable via `UPBIT_HTML_REFRESH_MS`)
- **Jitter**: ±20-40ms (configurable via `UPBIT_JITTER_MS`)
- **Page Load**: 500-900ms typical
- **Parsing**: 20-50ms typical
- **Total Cycle**: Base + Jitter + Load + Parsing
- **Typical Range**: 1.0-1.8s

## Auto-Fallback Behavior

### Failure Detection
The bot tracks these API failure types:
- HTTP timeouts (default: 10s)
- HTTP 4xx/5xx errors
- Connection errors
- JSON parse failures
- Empty or invalid responses

### State Transitions

#### API → HTML Fallback
1. Monitor consecutive API failures
2. When threshold exceeded (`UPBIT_API_ERROR_THRESHOLD`)
3. Initialize Selenium WebDriver
4. Switch to HTML mode
5. Log transition with reason

#### HTML → API Recovery
1. Perform periodic API health checks
2. Track consecutive successful checks
3. When threshold reached (`UPBIT_API_RECOVERY_OK`)
4. Clean up Selenium resources
5. Switch back to API mode
6. Log transition with reason

### Resource Management
- **API Sessions**: Reused with connection pooling
- **Selenium Drivers**: Single instance, properly cleaned up
- **Memory**: Automatic cleanup on mode switches
- **State**: Continuous via `last_notice.txt`

## Advanced Configuration

### HTTP Client Settings
```python
# These are built-in, but can be modified in source if needed
DEFAULT_TIMEOUT = 10  # seconds
MAX_RETRIES = 3
BACKOFF_FACTOR = 0.3
```

### Selenium Settings
```python
# These are built-in Chrome options
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--window-size=1920,1080')
```

### Logging Configuration
```python
# Default logging setup (can be customized)
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5
```

## Security Considerations

### Token Protection
- Never commit `.env` files to version control
- Use environment-specific tokens for different deployments
- Rotate tokens regularly
- Monitor Telegram bot usage

### Network Security
- API uses HTTPS with certificate validation
- No external dependencies beyond official package repositories
- Selenium uses headless Chrome with security hardening

### File Permissions
```bash
# Secure configuration files
chmod 600 .env
chmod 644 last_notice.txt
chmod 755 logs/
```

## Testing Configuration

### Validate Configuration
```bash
# Test basic configuration
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
required = ['TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']
missing = [var for var in required if not os.getenv(var)]
print(f'Missing variables: {missing}' if missing else 'All required variables set')
"

# Test mode resolution
python3 -c "
from config import resolve_mode, parse_cli_args
args = parse_cli_args([])
mode = resolve_mode(args)
print(f'Default mode: {mode.mode}')
print(f'Resolution path: {mode.resolution_path}')
"
```

### Dry Run Testing
```bash
# Test without sending notifications
TELEGRAM_TOKEN=dummy TELEGRAM_CHAT_ID=dummy python3 main.py --api --dry-run

# Test specific mode
UPBIT_MODE=html python3 main.py --html --test-mode
```
