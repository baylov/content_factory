# Auto-Fallback Implementation

## Overview

The Upbit Notice Bot now supports automatic fallback between API and HTML modes with comprehensive observability and operator controls. This ensures maximum uptime and reliability when API endpoints experience issues.

## Features

### 1. Failure Detection
- **Rolling Window**: Tracks API failures within a configurable time window (default: 2 minutes)
- **Multiple Error Types**: Detects timeouts, HTTP errors (4xx, 5xx), connection errors, and JSON parse failures
- **Smart Thresholds**: Configurable failure and recovery thresholds

### 2. Auto-Fallback Behavior
- **API → HTML**: Automatically switches to HTML mode when API failure threshold is exceeded
- **HTML → API**: Returns to API mode after consecutive successful health checks
- **Resource Management**: Safely initializes/cleans up API sessions and Selenium drivers
- **Continuity**: Maintains `last_notice.txt` continuity across mode switches

### 3. Enhanced Telemetry
- **Per-Cycle Metrics**: Mode, cycle time, notice count, max_id, last_known_id
- **60-Second Summaries**: Average/P95 cycle times, failure rates, transition counts
- **Mode-Specific Stats**: Separate metrics for API and HTML performance
- **Transition Logging**: Detailed logs for all mode switches with reasons

### 4. Configuration Options

#### Environment Variables
```bash
# Basic mode selection
UPBIT_MODE=api                    # Default mode: api or html

# Failure detection
UPBIT_API_ERROR_THRESHOLD=5         # Failures before fallback (default: 5)
UPBIT_API_RECOVERY_OK=20           # Successes before recovery (default: 20)

# Timing configuration
UPBIT_API_SLEEP_MS=100,300         # API sleep range in ms (default: 100-300)
UPBIT_HTML_REFRESH_MS=800,1200     # HTML refresh range in ms (default: 800-1200)
UPBIT_JITTER_MS=20,40              # Jitter range in ms (default: 20-40)

# Control
UPBIT_NO_AUTOFALLBACK=1            # Disable auto-fallback (default: enabled)
```

#### CLI Flags
```bash
python main.py                      # API mode with auto-fallback (default)
python main.py --api                # Force API mode
python main.py --html               # Force HTML mode
python main.py --legacy             # Alias for --html
python main.py --no-autofallback    # Disable auto-fallback
```

## Usage Examples

### Default Behavior (API with Auto-Fallback)
```bash
# Start in API mode, auto-fallback to HTML on failures
python main.py

# Equivalent with explicit flag
python main.py --api
```

### Force HTML Mode
```bash
# Force legacy HTML mode, no auto-fallback
python main.py --html
```

### Disable Auto-Fallback
```bash
# Stay in API mode regardless of failures
python main.py --no-autofallback

# Or via environment
UPBIT_NO_AUTOFALLBACK=1 python main.py
```

### Custom Thresholds
```bash
# Trigger fallback after 3 failures, recover after 10 successes
UPBIT_API_ERROR_THRESHOLD=3 UPBIT_API_RECOVERY_OK=10 python main.py
```

### Custom Timing
```bash
# Faster API polling, slower HTML refresh
UPBIT_API_SLEEP_MS=50,150 UPBIT_HTML_REFRESH_MS=500,1000 python main.py
```

## Monitoring and Observability

### Log Output
Each cycle logs:
```
🔄 Cycle #123 | ts_kst=14:30:15.123 | mode=API | status=ok | cycle=0.245s | api=0.203s | html=n/a | notices=2 | max_id=5789 | last_known=5787 | new_ids=5788,5789
```

### 60-Second Summaries
```
📈 60s summary: mode=API, cycles=240, avg_cycle=0.251s, p95_cycle=0.312s, error_rate=0.00%, api_cycles=240(0.251s), html_cycles=0(n/a), api_latency=0.203s, failures=0, transitions=0
   📊 ID tracking: last_known=5789, max_id=5789, gap=0
```

### Mode Transitions
```
🔄 MODE SWITCH: API → HTML
   Reason: API failures: 5 in 120s
   Recent errors:
     • timeout at 14:28:30
     • connection_error at 14:28:45
     • http_500 at 14:29:00
     • timeout at 14:29:15
     • http_429 at 14:29:30
   Failure count: 5
   Transition #1
```

## Implementation Details

### FailureDetector Class
- Tracks failure timestamps in rolling window
- Configurable thresholds for fallback and recovery
- Detailed error history for diagnostics
- Reset capability on mode switches

### ModeManager Class
- Manages API session and HTML driver lifecycle
- Handles safe resource initialization/cleanup
- Tracks transition history and statistics
- Respects auto-fallback disable flag

### HybridTelemetry Class
- Enhanced metrics collection for hybrid mode
- Per-mode performance tracking
- Automatic summary reporting
- Integration with failure detector and mode manager

### Resource Management
- **API Session**: Created on-demand, closed on HTML switch
- **HTML Driver**: Lazy initialization, quit on API switch
- **Memory Protection**: Guards against double initialization
- **Error Handling**: Graceful degradation on resource failures

## Testing

### Unit Tests
```bash
# Run comprehensive tests
python test_autofallback_simple.py
```

### Demo Simulation
```bash
# See auto-fallback in action with simulated failures
python demo_simple.py
```

## Performance Considerations

### Resource Usage
- **API Mode**: HTTP session only (~10MB memory)
- **HTML Mode**: Selenium WebDriver (~50-100MB memory)
- **Transitions**: Brief resource overlap during switches
- **Cleanup**: Automatic resource cleanup on all transitions

### Latency Impact
- **API Mode**: 100-300ms + jitter (configurable)
- **HTML Mode**: 800-1200ms + jitter (configurable)
- **Switch Overhead**: ~1-2 seconds for resource initialization
- **Jitter**: Prevents thundering herd issues

## Troubleshooting

### Common Issues

#### Auto-Fallback Not Triggering
```bash
# Check if disabled
python main.py --no-autofallback  # Should stay in API mode even with failures

# Verify threshold
UPBIT_API_ERROR_THRESHOLD=3 python main.py  # Lower threshold for testing
```

#### Frequent Mode Switching
```bash
# Increase thresholds for stability
UPBIT_API_ERROR_THRESHOLD=10 UPBIT_API_RECOVERY_OK=30 python main.py
```

#### Resource Leaks
- Monitor memory usage during transitions
- Check logs for resource cleanup errors
- Ensure proper shutdown with Ctrl+C

### Debug Logging
```bash
# Enable debug logging for detailed diagnostics
python main.py --debug 2>&1 | tee debug.log
```

## Migration Guide

### From Previous Version
- No breaking changes - existing configurations work
- Default mode remains API
- Auto-fallback enabled by default
- All existing CLI flags preserved

### Recommended Settings
- **Production**: Default settings (5 failures, 20 recoveries)
- **Testing**: Lower thresholds (3 failures, 10 recoveries)
- **High-Latency**: Longer sleep ranges (300-500ms API)
- **Resource-Constrained**: Disable auto-fallback with `--no-autofallback`

## Future Enhancements

- Exponential backoff for repeated failures
- Health check endpoints before mode switches
- Metrics export to monitoring systems
- Automatic threshold adjustment based on patterns
- Multiple fallback endpoints/strategies