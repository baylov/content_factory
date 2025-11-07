#!/usr/bin/env python3
"""
Demonstration script for aggressive polling mode.

This script shows how the system behaves with different polling configurations.
"""

import os
import sys
import time
from unittest.mock import patch

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    AGGRESSIVE_MODE_ENV,
    AGGRESSIVE_SLEEP_MS,
    AGGRESSIVE_429_THRESHOLD_LOW,
    AGGRESSIVE_429_THRESHOLD_HIGH,
    is_aggressive_mode_enabled,
    get_sleep_ranges
)

from main import RateLimitDetector, HybridTelemetry


def demonstrate_normal_mode():
    """Demonstrate normal polling mode."""
    print("📊 NORMAL MODE DEMONSTRATION")
    print("=" * 50)
    
    api_sleep_range, _, jitter_range, _, _, _ = get_sleep_ranges()
    print(f"• Sleep range: {api_sleep_range[0]}-{api_sleep_range[1]}ms + {jitter_range[0]}-{jitter_range[1]}ms jitter")
    print("• Typical cycle time: 1000-1340ms")
    print("• Detection latency: 3-7 seconds (average)")
    print("• Risk of rate-limiting: Low")
    print()
    
    # Simulate 5 cycles
    for i in range(5):
        base_sleep = 1000 + (i * 50)  # Simulate varying base sleep
        jitter = 30  # Fixed jitter for demo
        total_sleep = base_sleep + jitter
        print(f"  Cycle {i+1}: {total_sleep}ms sleep (base: {base_sleep}ms + jitter: {jitter}ms)")
        time.sleep(0.1)  # Small delay for demo


def demonstrate_aggressive_mode():
    """Demonstrate aggressive polling mode."""
    print("🚀 AGGRESSIVE MODE DEMONSTRATION")
    print("=" * 50)
    
    with patch.dict(os.environ, {AGGRESSIVE_MODE_ENV: "true"}):
        if is_aggressive_mode_enabled():
            print(f"• Aggressive mode: ENABLED")
            print(f"• Fixed sleep: {AGGRESSIVE_SLEEP_MS}ms (no jitter)")
            print("• Typical cycle time: 200-300ms")
            print("• Detection latency: <1 second (average)")
            print("• Risk of rate-limiting: HIGH")
            print()
            
            detector = RateLimitDetector()
            detector._current_mode = "aggressive"
            telemetry = HybridTelemetry(summary_interval=60)
            
            print("  Simulating 10 cycles in aggressive mode...")
            
            for i in range(10):
                cycle_start = time.time()
                
                # Simulate API call (mostly successful)
                if i < 7:  # First 7 cycles successful
                    success = True
                    status_code = 200
                    error_message = None
                else:  # Last 3 cycles get 429s
                    success = False
                    status_code = 429
                    error_message = "429 Too Many Requests"
                
                # Record the API call
                mode_changed, old_mode, new_mode, reason = detector.record_api_call(
                    success=success,
                    status_code=status_code,
                    error_message=error_message
                )
                
                # Determine sleep time
                api_sleep_range, _, _, _, _, _ = get_sleep_ranges()
                sleep_time_ms = detector.get_sleep_time_ms(api_sleep_range)
                
                # Record cycle
                cycle_duration = time.time() - cycle_start
                telemetry.record_cycle(
                    cycle_duration=cycle_duration,
                    mode="api",
                    api_latency=0.1,
                    error_occurred=not success,
                    sleep_time_ms=sleep_time_ms,
                    rate_limit_mode=detector._current_mode
                )
                
                # Log the cycle
                status = "✅ OK" if success else "❌ 429"
                mode_info = f"mode={detector._current_mode.upper()}"
                sleep_info = f"sleep={sleep_time_ms}ms"
                
                print(f"    Cycle {i+1:2}: {status} | {mode_info} | {sleep_info}")
                
                if mode_changed:
                    print(f"      🔄 MODE CHANGE: {old_mode.upper()} → {new_mode.upper()}")
                    print(f"      Reason: {reason}")
                
                time.sleep(0.05)  # Small delay for demo
            
            # Show final stats
            stats = detector.get_stats()
            print()
            print("  📊 Final Statistics:")
            print(f"    • Total API calls: {stats['total_api_calls']}")
            print(f"    • Success rate: {stats['success_rate']:.1f}%")
            print(f"    • 429 errors (60s): {stats['recent_429s_60s']}")
            print(f"    • Current mode: {stats['current_mode'].upper()}")
            print(f"    • HTML fallback suggested: {stats['suggest_html_fallback']}")
            
            print()
            print("  📈 Telemetry Summary:")
            print(f"    • Aggressive cycles: {telemetry.aggressive_cycles}")
            print(f"    • Normal cycles: {telemetry.normal_cycles}")
            print(f"    • Throttled cycles: {telemetry.throttled_cycles}")
            if telemetry.cycle_sleep_times:
                avg_sleep = sum(telemetry.cycle_sleep_times) / len(telemetry.cycle_sleep_times)
                print(f"    • Average sleep: {avg_sleep:.0f}ms")


def demonstrate_auto_backoff():
    """Demonstrate auto-backoff mechanism."""
    print("🔄 AUTO-BACKOFF DEMONSTRATION")
    print("=" * 50)
    
    detector = RateLimitDetector()
    detector._current_mode = "aggressive"
    
    print(f"Starting in AGGRESSIVE mode ({AGGRESSIVE_SLEEP_MS}ms sleep)")
    print(f"Thresholds: {AGGRESSIVE_429_THRESHOLD_LOW} 429s → normal mode, {AGGRESSIVE_429_THRESHOLD_HIGH} 429s → throttled mode")
    print()
    
    # Simulate increasing 429 errors
    scenarios = [
        (5, "Normal operation"),
        (AGGRESSIVE_429_THRESHOLD_LOW - 1, "Approaching threshold"),
        (AGGRESSIVE_429_THRESHOLD_LOW, f"Crossed low threshold → normal mode"),
        (AGGRESSIVE_429_THRESHOLD_HIGH - 1, "Approaching high threshold"),
        (AGGRESSIVE_429_THRESHOLD_HIGH, f"Crossed high threshold → throttled mode"),
        (AGGRESSIVE_429_THRESHOLD_HIGH + 5, "Deep in throttled mode"),
    ]
    
    api_sleep_range, _, _, _, _, _ = get_sleep_ranges()
    
    for error_count, description in scenarios:
        print(f"  {description}:")
        
        # Simulate the 429 errors
        for i in range(error_count):
            detector.record_api_call(success=False, status_code=429, error_message="429 Too Many Requests")
        
        # Get current state
        stats = detector.get_stats()
        sleep_time = detector.get_sleep_time_ms(api_sleep_range)
        
        print(f"    • 429 errors (60s): {stats['recent_429s_60s']}")
        print(f"    • Current mode: {stats['current_mode'].upper()}")
        print(f"    • Sleep time: {sleep_time}ms")
        print(f"    • Suggest HTML fallback: {stats['suggest_html_fallback']}")
        
        # Reset for next scenario (except last)
        if error_count < AGGRESSIVE_429_THRESHOLD_HIGH + 5:
            detector._current_mode = "aggressive"
            detector._429_timestamps.clear()
        
        print()


def demonstrate_recovery():
    """Demonstrate recovery mechanism."""
    print("🔧 RECOVERY DEMONSTRATION")
    print("=" * 50)
    
    detector = RateLimitDetector()
    detector._current_mode = "throttled"
    
    print(f"Starting in THROTTLED mode")
    print(f"Recovery condition: No 429s for {AGGRESSIVE_RECOVERY_CLEAR_SECONDS}s and no consecutive errors")
    print()
    
    # Simulate successful API calls over time
    print("  Simulating recovery with successful API calls...")
    
    for i in range(10):
        # Simulate time passing
        import time as time_module
        time_module.sleep(0.1)  # Small delay
        
        # Record successful API call
        detector.record_api_call(success=True, status_code=200)
        
        stats = detector.get_stats()
        print(f"    Call {i+1}: mode={stats['current_mode'].upper()}, consecutive_errors={stats['consecutive_errors']}")
        
        # Check if recovered
        if stats['current_mode'] == 'aggressive':
            print(f"    ✅ RECOVERED! Back to aggressive mode after {i+1} successful calls")
            break
    
    print()


def main():
    """Run all demonstrations."""
    print("🎯 UPBIT NOTICE BOT - AGGRESSIVE POLLING DEMO")
    print("=" * 60)
    print()
    
    print("This demonstration shows the key features of aggressive polling:")
    print("• 200ms polling for sub-second detection")
    print("• Automatic backoff when rate-limited")
    print("• Smart recovery when API is healthy")
    print("• Comprehensive metrics and telemetry")
    print()
    
    input("Press Enter to start normal mode demo...")
    demonstrate_normal_mode()
    
    input("\nPress Enter to start aggressive mode demo...")
    demonstrate_aggressive_mode()
    
    input("\nPress Enter to start auto-backoff demo...")
    demonstrate_auto_backoff()
    
    input("\nPress Enter to start recovery demo...")
    demonstrate_recovery()
    
    print("🎉 DEMONSTRATION COMPLETE!")
    print()
    print("📖 To use aggressive mode in production:")
    print(f"   export {AGGRESSIVE_MODE_ENV}=true")
    print("   python main.py")
    print()
    print("⚠️  WARNING: Aggressive mode carries high risk of rate-limiting!")
    print("   Monitor closely for 429 errors in the first 24-48 hours")
    print("   Have HTML mode ready as fallback: python main.py --html")


if __name__ == "__main__":
    main()