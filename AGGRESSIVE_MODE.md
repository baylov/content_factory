# Aggressive Polling Mode

The Upbit Notice Bot now supports **aggressive polling mode** for ultra-low latency detection of new notices.

## Overview

Aggressive mode reduces API polling from the default 1000-2000ms range down to **200ms fixed polling**, achieving sub-second detection latency compared to the typical 3-7 second delay.

⚠️ **WARNING**: This is a high-risk feature that may trigger rate-limiting (429 errors) or temporary IP blocks from Upbit.

## Features

### 🚀 Ultra-Fast Polling
- **200ms fixed polling** (no jitter for consistency)
- **Detection latency**: <1 second average (vs 3-7 seconds normal)
- **Cycle time**: 200-300ms typical (including API latency)

### 🛡️ Intelligent Rate-Limit Detection
- **Rolling window tracking** of 429 errors (60-second window)
- **Automatic backoff** based on error frequency:
  - **10+ 429s in 60s** → 500ms polling (normal mode)
  - **20+ 429s in 60s** → 1000ms polling (throttled mode)
- **Recovery detection**: Resume 200ms after 5 minutes of no 429s

### 📊 Comprehensive Metrics & Telemetry
- **Per-cycle metrics**: cycle_ms, api_status, 429_count_60s, mode
- **10-second summaries**: Real-time rate-limit window state
- **Enhanced logging**: Total attempts, success %, 429 errors, timeouts
- **Detection latency tracking**: Actual time between new notice discoveries

### 🔄 Smart Fallback Safeguards
- **50+ consecutive errors** → Auto-downgrade to 500ms polling
- **10+ minutes of persistent 429s** → Suggest HTML mode switch
- **Never auto-switches to HTML** (operator decision required)

## Usage

### Enable Aggressive Mode

```bash
# Method 1: Environment variable
export UPBIT_AGGRESSIVE_MODE=true
python main.py

# Method 2: One-liner
UPBIT_AGGRESSIVE_MODE=true python main.py

# Method 3: .env file
echo "UPBIT_AGGRESSIVE_MODE=true" >> .env
python main.py
```

### Disable Aggressive Mode

```bash
# Default (disabled)
unset UPBIT_AGGRESSIVE_MODE
python main.py

# Or explicitly disable
export UPBIT_AGGRESSIVE_MODE=false
python main.py
```

### Force HTML Fallback

If rate-limiting becomes problematic:

```bash
python main.py --html
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|-----------|----------|-------------|
| `UPBIT_AGGRESSIVE_MODE` | `false` | Enable 200ms polling |
| `UPBIT_API_ERROR_THRESHOLD` | `5` | API failures before HTML fallback |
| `UPBIT_API_RECOVERY_OK` | `20` | Successes before API recovery |
| `UPBIT_NO_AUTOFALLBACK` | `false` | Disable auto-fallback |

### Aggressive Mode Thresholds

| Threshold | Value | Action |
|-----------|--------|--------|
| Low 429 threshold | `10` in 60s | Switch to normal mode (500ms) |
| High 429 threshold | `20` in 60s | Switch to throttled mode (1000ms) |
| Recovery clear time | `300s` (5 min) | Resume aggressive mode |
| Consecutive error limit | `50` | Auto-backoff to 500ms |
| Persistent 429 limit | `600s` (10 min) | Suggest HTML fallback |

## Monitoring

### Real-time Logs

Aggressive mode provides enhanced logging:

```
🔄 Cycle #1 | ts_kst=14:23:45.123 | mode=API | rl_mode=AGGRESSIVE | status=ok | cycle=0.245s | api=0.089s | sleep=200ms | notices=0 | max_id=12345 | last_known=12345 | new_ids=- | 429s_60s=0
```

### 10-Second Summaries

```
📊 10s rate-limit window: mode=AGGRESSIVE, api_calls=50, success_rate=100.0%, 429s_60s=0, consecutive_errors=0, 429_rate=0.0/min
   💤 Recent avg sleep: 200ms
   ⚡ Recent detection lag: 180ms
```

### 60-Second Summaries

```
📈 60s summary: mode=API, cycles=300, avg_cycle=0.235s, p95_cycle=0.280s, error_rate=0.00%, api_cycles=300(0.235s), html_cycles=0(n/a), api_latency=0.089s, failures=0, transitions=0, rl_mode=AGGRESSIVE, 429s_60s=0, success_rate=100.0%, modes=aggr:300|norm:0|throt:0
   📊 ID tracking: last_known=12345, max=12345, gap=0
   💤 Sleep times: avg=200ms, min=200ms, max=200ms
   ⚡ Detection latency: avg=185ms, min=120ms, max=280ms
```

## Rate-Limit Modes

### 🟢 AGGRESSIVE Mode
- **Sleep**: Fixed 200ms
- **Jitter**: 0-10ms (minimal for consistency)
- **Use case**: Normal operation, no rate-limiting detected

### 🟡 NORMAL Mode  
- **Sleep**: 500ms (or configured API range)
- **Jitter**: Standard 20-40ms
- **Use case**: Moderate rate-limiting detected

### 🔴 THROTTLED Mode
- **Sleep**: 1000ms+ (high end of range + extra)
- **Jitter**: Standard 20-40ms  
- **Use case**: Heavy rate-limiting detected

## Testing

### Run Tests

```bash
# Test aggressive mode functionality
source venv/bin/activate
python test_aggressive_mode.py
```

### Interactive Demo

```bash
# See how aggressive mode works
python demo_aggressive_mode.py
```

## Production Deployment

### Pre-Launch Checklist

- [ ] Monitor baseline API behavior for 1 hour in normal mode
- [ ] Enable aggressive mode during low-traffic period
- [ ] Monitor closely for first 24-48 hours
- [ ] Have HTML fallback command ready: `python main.py --html`
- [ ] Set up alerts for high 429 error rates

### Monitoring Commands

```bash
# Watch for 429 errors in real-time
tail -f logs/bot.log | grep "429"

# Monitor rate-limit mode changes
tail -f logs/bot.log | grep "RATE-LIMIT MODE CHANGE"

# Check detection latency
grep "detection lag" logs/bot.log | tail -10
```

### Success Criteria

- ✅ **Polling interval**: 200ms achieved
- ✅ **Cycle time**: 200-300ms typical  
- ✅ **Detection latency**: <1s average
- ✅ **Auto-backoff**: Triggers at 10/20 429s
- ✅ **Recovery**: Resumes 200ms after 5min clear
- ✅ **No IP bans**: After 48 hours of operation

### Troubleshooting

#### High 429 Errors
```bash
# Check current rate-limit status
grep "429s_60s" logs/bot.log | tail -5

# If >10 429s in 60s, consider:
export UPBIT_AGGRESSIVE_MODE=false
python main.py
```

#### Persistent Rate-Limiting
```bash
# If throttled mode persists >10min:
python main.py --html
```

#### Detection Latency Still High
- Check API latency: `grep "api=" logs/bot.log`
- Verify aggressive mode enabled: `grep "AGGRESSIVE MODE" logs/bot.log`
- Check for consecutive errors: `grep "consecutive_errors" logs/bot.log`

## Performance Impact

### Resource Usage
- **CPU**: Minimal increase (more frequent API calls)
- **Memory**: No significant change
- **Network**: 5-10x more API requests per hour
- **Rate-limit risk**: HIGH (monitor closely)

### Expected Improvements
- **Detection latency**: 70-90% reduction (3-7s → <1s)
- **Notification speed**: Near-instant after publication
- **User experience**: Significantly faster notice delivery

## Risks & Mitigations

| Risk | Impact | Mitigation |
|-------|---------|------------|
| Rate-limiting (429) | Service degradation | Auto-backoff to 500ms/1000ms |
| IP blocking | Service outage | Monitor 429 patterns, HTML fallback |
| Increased API costs | Higher resource usage | Monitor usage, set limits |
| Upbit policy changes | Feature breakage | Graceful fallback to normal mode |

## Support

For issues with aggressive mode:

1. Check logs for 429 error patterns
2. Verify `UPBIT_AGGRESSIVE_MODE=true` is set
3. Run test suite: `python test_aggressive_mode.py`
4. Try normal mode: `unset UPBIT_AGGRESSIVE_MODE`
5. Use HTML fallback: `python main.py --html`

---

**⚠️ Remember**: Aggressive mode is powerful but carries risks. Monitor closely and be prepared to fallback to normal operation if rate-limiting occurs.