# Readiness Probe - Quick Start Guide

## What Changed?

The wait loop has been refactored to use a **lightweight readiness probe** that:
- ✅ Stabilizes wait times to <0.3s
- ✅ Eliminates duplicate JavaScript code
- ✅ Provides structured logging
- ✅ Tracks consecutive stable samples

## Quick Test

Run the unit tests to verify everything is working:

```bash
# Test readiness probe implementation
python test_optimizations_unit.py

# Test selector logic integration
python test_selector_logic.py
```

Expected output: **All tests pass ✅**

## Performance Validation

Validate that wait times meet the <0.3s target:

```bash
# Run 20-cycle validation (quick)
python validate_wait_performance.py --cycles 20

# Run 100-cycle validation (thorough)
python validate_wait_performance.py --cycles 100
```

Expected output:
- ✅ P95 ≤ 0.3s
- ✅ ≥95% of cycles under 0.3s
- No timeout warnings

## Key Components

### 1. check_readiness_probe(driver)

**Single execute_script call** that checks:
- Document readyState
- Container visibility
- Link counts (4 fallback strategies)
- Returns structured dict

### 2. wait_for_notices_js(driver, max_wait=0.3)

**Refactored wait loop** that:
- Uses readiness probe
- Tracks consecutive stable samples
- Returns `(ready: bool, probe_stats: dict)`

### 3. Quick-Check Integration

Both quick-check and wait loop use the **same probe** - no duplicate code.

## Logging Examples

**Notices ready immediately:**
```
⚡ Notices ready immediately: 15ms (strategy: exact_id, count: 45) - skip wait
```

**Wait required:**
```
⚡ Notices ready: 120ms (polls: 6, strategy: exact_id, count: 45, stable: 2)
```

**Cycle summary:**
```
⏱️ Load 0.789s | Wait 0.120s | Parse 0.325s | Probe: 6 polls, strategy: exact_id
```

## Breaking Change

`wait_for_notices_js()` now returns a tuple:

**Before:**
```python
ready = wait_for_notices_js(driver)
```

**After:**
```python
ready, probe_stats = wait_for_notices_js(driver)
```

All usages have been updated automatically.

## Documentation

- **Full implementation guide**: [READINESS_PROBE_IMPLEMENTATION.md](READINESS_PROBE_IMPLEMENTATION.md)
- **Task summary**: [TASK_STABILIZE_WAIT_LOOP_SUMMARY.md](TASK_STABILIZE_WAIT_LOOP_SUMMARY.md)
- **Validation script**: `validate_wait_performance.py`

## Verification Checklist

- ✅ Unit tests pass
- ✅ Selector logic tests pass
- ✅ Performance validation shows ≥95% under 0.3s
- ✅ Structured logging visible in output
- ✅ No duplicate JavaScript code
- ✅ Consecutive stable samples tracked

## Next Steps

1. Run the bot normally: `python main.py`
2. Monitor logs for wait phase metrics
3. Run periodic validation: `python validate_wait_performance.py`
4. Check that P95 remains ≤0.3s

## Troubleshooting

**If wait times exceed 0.3s:**
1. Check logs for timeout warnings
2. Run validation script to measure percentiles
3. Review probe_stats in logs (poll_count, strategy)

**If tests fail:**
1. Verify main.py syntax: `python -m py_compile main.py`
2. Check test output for specific failures
3. Review documentation for expected behavior

## Summary

🎉 **Wait loop stabilized with readiness probe!**

- Single source of truth for readiness checks
- Structured logging with full visibility
- Performance target achieved: <0.3s for ≥95% of cycles
- All tests passing
