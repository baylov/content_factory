# Exact Selector Retry Logic Documentation

## Overview

The exact_id selector (`a[href*="/service_center/notice?id="]`) is the most precise selector for finding Upbit notice links, but it may occasionally fail to find links during the initial page load due to late DOM rendering. This document describes the retry logic implemented to maximize Strategy 1 success rate (target: ≥90%).

## Problem Statement

**Issue**: The exact_id selector sometimes returns 0 links immediately after page load/refresh, even though:
- The page is technically "ready" (document.readyState = 'interactive' or 'complete')
- Broader selectors can already see content
- The exact_id links render shortly afterwards (within 50-150ms)

**Impact**: This causes unnecessary fallback to Strategy 2/3/4, reducing accuracy and making debugging harder.

## Solution: Focused Retry Loop

Before falling back to broader strategies, we now:

1. **Poll the exact_id selector** multiple times
2. **Short intervals**: 40ms between attempts
3. **Time-bounded**: Maximum 200ms total
4. **Smart fallback**: Only fallback when:
   - All retries exhausted (5 attempts)
   - AND broader selectors detect content
   - OR no content detected anywhere (page still loading)

## Implementation

### Key Functions

#### `retry_exact_id_selector(driver, max_retries=5, retry_interval=0.04, max_total_time=0.2)`

Retries the exact_id selector before falling back to broader strategies.

**Parameters**:
- `driver`: Selenium WebDriver instance
- `max_retries`: Maximum number of retry attempts (default: 5)
- `retry_interval`: Time between retries in seconds (default: 0.04 = 40ms)
- `max_total_time`: Maximum total time for all retries (default: 0.2s)

**Returns** (dict):
```python
{
    'success': bool,           # Whether exact_id selector found links
    'count': int,              # Number of links found
    'attempts': int,           # Number of attempts made
    'elapsed_time': float,     # Total time spent (seconds)
    'dom_state': dict          # DOM state at final attempt
}
```

#### `check_dom_state_for_fallback(driver)`

Checks broader selectors to determine if content exists but exact_id selector failed.

**Returns** (dict):
```python
{
    'broader_content_exists': bool,  # If any broader selector found links
    'exact_id_count': int,           # Count for exact_id selector
    'all_notice_count': int,         # Count for all_notice selector
    'tr_notice_count': int,          # Count for tr_notice selector
    'any_id_count': int,             # Count for any_id selector
    'readyState': str,               # document.readyState
    'containerVisible': bool         # Whether notice container is visible
}
```

## Instrumentation & Logging

### Global Stats Tracking

`_last_parse_stats['strategy_stats']` now includes:

```python
{
    'strategy_used': str,              # 'exact_id', 'all_notice', 'tr_notice', or 'any_id'
    'exact_id_attempts': int,          # Number of retry attempts made
    'exact_id_retry_time': float,      # Time spent in retry loop (seconds)
    'exact_id_success': bool,          # Whether Strategy 1 succeeded
    'fallback_reason': str or None,    # Reason for fallback (if failed)
    'dom_state_at_fallback': dict      # DOM state when fallback triggered
}
```

### Fallback Reasons

- `None` - Strategy 1 succeeded
- `'exact_id_failed_but_broader_content_exists'` - Broader selectors saw content, but exact_id didn't
- `'no_content_detected'` - No content detected anywhere (page still loading)

### Log Output Examples

**Success on first attempt**:
```
🔍 Strategy 1 (exact_id): Starting with retry loop...
📊 Strategy 1 instrumentation: attempts=1, time=2ms, success=True
✅ Strategy 1 (exact_id): 25 links (found after 1 attempt(s), 2ms)
```

**Success after retries**:
```
🔍 Strategy 1 (exact_id): Starting with retry loop...
📊 Strategy 1 instrumentation: attempts=3, time=87ms, success=True
✅ Strategy 1 (exact_id): 25 links (found after 3 attempt(s), 87ms)
```

**Fallback with context**:
```
🔍 Strategy 1 (exact_id): Starting with retry loop...
📊 Strategy 1 instrumentation: attempts=5, time=198ms, success=False
⚠️ Strategy 1 failed after 5 attempts (198ms) BUT broader selectors see content:
   • all_notice: 30 links
   • tr_notice: 28 links
   • any_id: 26 links
   • DOM: readyState=complete, container=True
🔍 Strategy 2 (all_notice): 30 links
```

## Performance Impact

### Timing Analysis

| Scenario | Attempts | Time | Impact on Cycle |
|----------|----------|------|-----------------|
| Instant success (90%+ expected) | 1 | 0-5ms | Negligible (~0.01s) |
| Late rendering (5-10% expected) | 2-4 | 40-150ms | Small (~0.1s) |
| Total failure (rare) | 5 | 160-200ms | Bounded (~0.2s) |

**Total cycle time**: Still meets <1.5s target even in worst case:
- Load: 0.7-0.9s
- Retry: 0.0-0.2s (worst case)
- Parse: 0.1-0.3s
- **Total: 0.8-1.4s** ✅

### Strategy 1 Hit Rate Target

**Target**: ≥90% of cycles should use Strategy 1 (exact_id)

**Measurement**: Run 100-cycle stability test:
```bash
python test_stability_100.py
```

**Expected output**:
```
🎯 Strategy 1 (exact_id) success rate:
   • Hits: 95
   • Misses: 5
   • Success rate: 95.0%
   ✅ SUCCESS: ≥90% target achieved!
```

## Testing

### Unit Tests

Run unit tests with stubbed drivers:
```bash
python test_exact_selector_retry_unit.py
```

**Test scenarios**:
1. **Instant success** - exact_id works on first attempt
2. **Late rendering** - exact_id succeeds after 2-3 retries
3. **Total failure** - No content detected (page still loading)
4. **Broader content fallback** - Broader selectors see content, exact_id doesn't
5. **Time constraints** - Retry loop respects max_total_time
6. **DOM state function** - check_dom_state_for_fallback works correctly

### Integration Tests

Run 100-cycle stability test:
```bash
python test_stability_100.py 100
```

**What it measures**:
- Strategy 1 hit rate (target: ≥90%)
- Average retry attempts
- Average retry time
- Max retry time (should be <200ms)
- Overall cycle time (should remain <1.5s)

### Validation

Quick 10-cycle validation:
```bash
python test_stability_100.py 10
```

Look for:
- All cycles successful (0 failures)
- Strategy 1 hit rate displayed
- Retry statistics logged
- Fallback reasons (if any)

## Troubleshooting

### Low Strategy 1 Hit Rate (<90%)

**Possible causes**:
1. Page rendering is consistently slow
2. Network latency is high
3. Upbit changed page structure

**Debug steps**:
1. Check logs for `fallback_reason`
2. Review DOM state at fallback
3. Increase `max_retries` or `max_total_time` if needed
4. Run diagnostic: `python main.py` (will save `upbit_debug.html`)

### Excessive Retry Time

If retry times consistently exceed 200ms:

1. **Check intervals**: Default is 40ms × 5 = 200ms max
2. **Network issues**: High latency might slow execute_script
3. **Consider adjustment**: Reduce `retry_interval` to 30ms

### False Positives (Strategy 1 says success but returns 0)

This should never happen due to the retry loop checking `exact_id_count > 0` before returning success.

If it does:
1. Check logs for exact_id_count value
2. Verify JavaScript selector is correct
3. Run unit tests to verify mock behavior

## Configuration

### Tuning Retry Parameters

In `get_all_notice_ids()`, adjust the retry call:

```python
retry_result = retry_exact_id_selector(
    driver, 
    max_retries=5,        # Increase for slower networks
    retry_interval=0.04,  # Decrease for faster polling
    max_total_time=0.2    # Increase if needed (but watch cycle time!)
)
```

**Recommendations**:
- **Fast networks**: max_retries=3, retry_interval=0.03 (90ms total)
- **Slow networks**: max_retries=7, retry_interval=0.05 (300ms total)
- **Default (balanced)**: max_retries=5, retry_interval=0.04 (200ms total)

### Disabling Retry (Not Recommended)

To disable retry and fallback immediately:

```python
# Change in get_all_notice_ids():
retry_result = {
    'success': False,
    'count': 0,
    'attempts': 0,
    'elapsed_time': 0.0,
    'dom_state': check_dom_state_for_fallback(driver)
}
```

## Success Metrics

### Key Performance Indicators (KPIs)

| Metric | Target | Current (v2.8) |
|--------|--------|----------------|
| Strategy 1 hit rate | ≥90% | TBD (measure with 100-cycle test) |
| Avg retry attempts | 1-2 | TBD |
| Avg retry time | <50ms | TBD |
| Max retry time | <200ms | 200ms (by design) |
| Cycle time (with retry) | <1.5s | TBD |
| False positives | 0% | 0% (expected) |

### Measuring Success

After deployment, run:

```bash
# Full stability test
python test_stability_100.py 100 > stability_report.log 2>&1

# Extract metrics
grep "Strategy 1 (exact_id) success rate:" stability_report.log
grep "Retry statistics:" -A 3 stability_report.log
grep "Retry timing:" -A 2 stability_report.log
```

## Version History

- **v2.8 (Current)** - Added exact_id retry logic with instrumentation
- **v2.7** - Hardened filtering with defensive fallback
- **v2.6** - Readiness probe implementation
- **v2.5** - Parser sync with diagnostic technique

## Future Improvements

Potential enhancements:

1. **Adaptive retry intervals** - Adjust based on past success patterns
2. **Machine learning** - Predict when exact_id will succeed based on page characteristics
3. **Preemptive fallback** - Skip exact_id retry if we know it will fail
4. **Telemetry** - Send metrics to monitoring service for trend analysis

## Related Documentation

- `HARDENED_FILTERING_README.md` - Filtering logic and fallback mechanism
- `READINESS_PROBE_IMPLEMENTATION.md` - Readiness probe architecture
- `ULTRA_FAST_PARSER_README.md` - Overall parsing strategy
- `test_exact_selector_retry_unit.py` - Unit test implementation
- `test_stability_100.py` - 100-cycle stability test

## Support

For issues or questions:
1. Check logs in `logs/bot.log`
2. Run diagnostic: `python main.py`
3. Review `upbit_debug.html` for DOM structure
4. Run unit tests: `python test_exact_selector_retry_unit.py`
5. Check strategy statistics: `get_last_parse_stats()['strategy_stats']`
