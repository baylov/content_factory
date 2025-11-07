#!/usr/bin/env python3
"""
Test script for aggressive polling mode.

This script validates:
1. Aggressive mode configuration
2. Rate-limit detector functionality
3. Auto-backoff mechanisms
4. Metrics and telemetry
5. Sleep time calculations

Usage:
    python test_aggressive_mode.py
"""

import os
import sys
import time
from unittest.mock import Mock, patch

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    AGGRESSIVE_MODE_ENV,
    AGGRESSIVE_SLEEP_MS,
    AGGRESSIVE_429_THRESHOLD_LOW,
    AGGRESSIVE_429_THRESHOLD_HIGH,
    AGGRESSIVE_429_WINDOW_SECONDS,
    AGGRESSIVE_RECOVERY_CLEAR_SECONDS,
    AGGRESSIVE_CONSECUTIVE_ERROR_THRESHOLD,
    is_aggressive_mode_enabled,
    get_sleep_ranges
)

from main import RateLimitDetector, HybridTelemetry


def test_aggressive_mode_config():
    """Test aggressive mode configuration."""
    print("🧪 Testing aggressive mode configuration...")
    
    # Test default (disabled)
    with patch.dict(os.environ, {}, clear=True):
        assert not is_aggressive_mode_enabled(), "Aggressive mode should be disabled by default"
        print("   ✅ Default: aggressive mode disabled")
    
    # Test enabled
    with patch.dict(os.environ, {AGGRESSIVE_MODE_ENV: "true"}):
        assert is_aggressive_mode_enabled(), "Aggressive mode should be enabled when env var is true"
        print("   ✅ Enabled: aggressive mode active with env var")
    
    # Test various values
    for value in ["1", "yes", "on", "TRUE"]:
        with patch.dict(os.environ, {AGGRESSIVE_MODE_ENV: value}):
            assert is_aggressive_mode_enabled(), f"Aggressive mode should be enabled for '{value}'"
    
    for value in ["0", "false", "no", "off", ""]:
        with patch.dict(os.environ, {AGGRESSIVE_MODE_ENV: value}):
            assert not is_aggressive_mode_enabled(), f"Aggressive mode should be disabled for '{value}'"
    
    print("   ✅ All configuration values work correctly")


def test_rate_limit_detector():
    """Test rate limit detector functionality."""
    print("\n🧪 Testing rate limit detector...")
    
    detector = RateLimitDetector()
    
    # Test initial state
    stats = detector.get_stats()
    assert stats["current_mode"] == "normal", "Initial mode should be normal"
    assert stats["total_api_calls"] == 0, "Initial API calls should be 0"
    assert stats["recent_429s_60s"] == 0, "Initial 429s should be 0"
    print("   ✅ Initial state correct")
    
    # Test successful API calls
    for i in range(5):
        detector.record_api_call(success=True, status_code=200)
    
    stats = detector.get_stats()
    assert stats["total_api_calls"] == 5, "Should track 5 API calls"
    assert stats["successful_calls"] == 5, "Should track 5 successful calls"
    assert stats["success_rate"] == 100.0, "Success rate should be 100%"
    assert stats["recent_429s_60s"] == 0, "No 429s yet"
    print("   ✅ Successful calls tracked correctly")
    
    # Test 429 errors
    for i in range(3):
        detector.record_api_call(success=False, status_code=429, error_message="429 Too Many Requests")
    
    stats = detector.get_stats()
    assert stats["total_api_calls"] == 8, "Should track 8 total API calls"
    assert stats["total_429_errors"] == 3, "Should track 3 429 errors"
    assert stats["recent_429s_60s"] == 3, "Should track 3 recent 429s"
    assert stats["consecutive_errors"] == 3, "Should track 3 consecutive errors"
    print("   ✅ 429 errors tracked correctly")
    
    # Test mode changes
    # Simulate many 429s to trigger throttled mode
    for i in range(AGGRESSIVE_429_THRESHOLD_HIGH):
        detector.record_api_call(success=False, status_code=429)
    
    stats = detector.get_stats()
    assert stats["current_mode"] == "throttled", f"Should be throttled at {AGGRESSIVE_429_THRESHOLD_HIGH} 429s"
    print(f"   ✅ Mode changed to throttled at {AGGRESSIVE_429_THRESHOLD_HIGH} 429s")
    
    # Test recovery
    detector.reset()
    stats = detector.get_stats()
    assert stats["current_mode"] == "normal", "Should reset to normal mode"
    assert stats["total_api_calls"] == 0, "Should reset API call count"
    print("   ✅ Reset works correctly")


def test_sleep_time_calculations():
    """Test sleep time calculations for different modes."""
    print("\n🧪 Testing sleep time calculations...")
    
    detector = RateLimitDetector()
    api_sleep_range = (100, 300)  # Default range
    
    # Test normal mode
    detector._current_mode = "normal"
    sleep_time = detector.get_sleep_time_ms(api_sleep_range)
    assert api_sleep_range[0] <= sleep_time <= api_sleep_range[1], "Normal mode should use range"
    print(f"   ✅ Normal mode: sleep_time={sleep_time}ms (within {api_sleep_range}ms)")
    
    # Test aggressive mode
    detector._current_mode = "aggressive"
    sleep_time = detector.get_sleep_time_ms(api_sleep_range)
    assert sleep_time == AGGRESSIVE_SLEEP_MS, f"Aggressive mode should use {AGGRESSIVE_SLEEP_MS}ms"
    print(f"   ✅ Aggressive mode: sleep_time={sleep_time}ms (fixed {AGGRESSIVE_SLEEP_MS}ms)")
    
    # Test throttled mode
    detector._current_mode = "throttled"
    sleep_time = detector.get_sleep_time_ms(api_sleep_range)
    assert sleep_time >= api_sleep_range[1], "Throttled mode should use higher end of range or more"
    print(f"   ✅ Throttled mode: sleep_time={sleep_time}ms (>= {api_sleep_range[1]}ms)")


def test_telemetry():
    """Test enhanced telemetry functionality."""
    print("\n🧪 Testing enhanced telemetry...")
    
    telemetry = HybridTelemetry(summary_interval=1)  # 1 second for testing
    
    # Test recording cycles
    telemetry.record_cycle(
        cycle_duration=0.25,
        mode="api",
        api_latency=0.1,
        error_occurred=False,
        sleep_time_ms=200,
        rate_limit_mode="aggressive",
        detection_lag=150
    )
    
    telemetry.record_cycle(
        cycle_duration=0.3,
        mode="api",
        api_latency=0.15,
        error_occurred=False,
        sleep_time_ms=500,
        rate_limit_mode="normal",
        detection_lag=200
    )
    
    assert telemetry.cycle_count == 2, "Should record 2 cycles"
    assert telemetry.aggressive_cycles == 1, "Should record 1 aggressive cycle"
    assert telemetry.normal_cycles == 1, "Should record 1 normal cycle"
    assert len(telemetry.cycle_sleep_times) == 2, "Should record 2 sleep times"
    assert len(telemetry.detection_lags) == 2, "Should record 2 detection lags"
    print("   ✅ Cycle recording works correctly")
    
    # Test reset
    telemetry.reset()
    assert telemetry.cycle_count == 0, "Should reset cycle count"
    assert telemetry.aggressive_cycles == 0, "Should reset aggressive cycles"
    assert len(telemetry.cycle_sleep_times) == 0, "Should reset sleep times"
    print("   ✅ Reset works correctly")


def test_integration():
    """Test integration between components."""
    print("\n🧪 Testing integration...")
    
    # Set aggressive mode
    with patch.dict(os.environ, {AGGRESSIVE_MODE_ENV: "true"}):
        assert is_aggressive_mode_enabled(), "Aggressive mode should be enabled"
        
        detector = RateLimitDetector()
        telemetry = HybridTelemetry(summary_interval=60)
        
        # Simulate aggressive mode operation
        detector._current_mode = "aggressive"
        
        # Record some successful calls
        for i in range(5):
            detector.record_api_call(success=True, status_code=200)
            telemetry.record_cycle(
                cycle_duration=0.2 + i * 0.01,
                mode="api",
                api_latency=0.1,
                error_occurred=False,
                sleep_time_ms=AGGRESSIVE_SLEEP_MS,
                rate_limit_mode="aggressive"
            )
        
        # Verify everything is working
        stats = detector.get_stats()
        assert stats["current_mode"] == "aggressive", "Should stay in aggressive mode"
        assert stats["success_rate"] == 100.0, "Should have 100% success rate"
        assert telemetry.aggressive_cycles == 5, "Should record 5 aggressive cycles"
        
        print("   ✅ Integration test passed")
        print(f"   📊 Stats: {stats['total_api_calls']} calls, {stats['success_rate']:.1f}% success rate")
        print(f"   📊 Telemetry: {telemetry.aggressive_cycles} aggressive cycles")


def test_edge_cases():
    """Test edge cases and error conditions."""
    print("\n🧪 Testing edge cases...")
    
    detector = RateLimitDetector()
    
    # Test with None parameters
    detector.record_api_call(success=True, status_code=None, error_message=None)
    stats = detector.get_stats()
    assert stats["total_api_calls"] == 1, "Should handle None parameters"
    print("   ✅ Handles None parameters")
    
    # Test HTML fallback suggestion
    assert not detector.should_suggest_html_fallback(), "Should not suggest fallback initially"
    
    # Simulate persistent 429s
    for i in range(AGGRESSIVE_429_THRESHOLD_HIGH + 5):
        detector.record_api_call(success=False, status_code=429)
    
    assert detector.should_suggest_html_fallback(), "Should suggest fallback after persistent 429s"
    print("   ✅ HTML fallback suggestion works")
    
    # Test consecutive errors threshold
    detector.reset()
    for i in range(AGGRESSIVE_CONSECUTIVE_ERROR_THRESHOLD * 2 + 10):
        detector.record_api_call(success=False, error_message="Connection error")
    
    assert detector.should_suggest_html_fallback(), "Should suggest fallback after many consecutive errors"
    print("   ✅ Consecutive error threshold works")


def main():
    """Run all tests."""
    print("🚀 Starting aggressive polling mode tests...\n")
    
    try:
        test_aggressive_mode_config()
        test_rate_limit_detector()
        test_sleep_time_calculations()
        test_telemetry()
        test_integration()
        test_edge_cases()
        
        print("\n✅ All tests passed!")
        print("\n📋 Summary:")
        print("   • Aggressive mode configuration: ✅")
        print("   • Rate-limit detection: ✅")
        print("   • Auto-backoff mechanisms: ✅")
        print("   • Enhanced telemetry: ✅")
        print("   • Sleep time calculations: ✅")
        print("   • Integration: ✅")
        print("   • Edge cases: ✅")
        
        print("\n🎯 Ready for production deployment!")
        print("\n📖 Usage:")
        print(f"   export {AGGRESSIVE_MODE_ENV}=true")
        print("   python main.py")
        print(f"\n   Or: {AGGRESSIVE_MODE_ENV}=true python main.py")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())