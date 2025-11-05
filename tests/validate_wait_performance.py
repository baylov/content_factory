#!/usr/bin/env python3
"""
Validation script to measure wait phase performance.

Runs multiple refresh cycles and validates that wait phase completes
within <0.3s for ≥95% of cycles.

Usage:
    python validate_wait_performance.py [--cycles N]

Options:
    --cycles N    Number of cycles to test (default: 20)
"""

import sys
import argparse
import time
import logging
from main import init_driver, get_all_notice_ids_with_api

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


def validate_wait_performance(cycles=20):
    """
    Validates wait phase performance over multiple cycles.
    
    Args:
        cycles: Number of refresh cycles to test
    
    Returns:
        bool: True if ≥95% of cycles meet the <0.3s target
    """
    print("=" * 80)
    print(f"WAIT PHASE PERFORMANCE VALIDATION ({cycles} cycles)")
    print("=" * 80)
    print()
    
    # Initialize driver
    print("Initializing WebDriver...")
    driver = init_driver(enable_cdp=False)
    if not driver:
        print("❌ Failed to initialize driver")
        return False
    
    print("✅ Driver initialized")
    print()
    
    wait_times = []
    probe_stats_list = []
    
    try:
        for i in range(cycles):
            print(f"Cycle {i+1}/{cycles}...", end=" ", flush=True)
            
            try:
                # Execute refresh cycle
                notice_ids, method, timings = get_all_notice_ids_with_api(
                    driver, 
                    known_endpoints=[], 
                    use_cdp=False
                )
                
                # Extract wait time and probe stats
                html_details = timings.get('html', {})
                wait_time = html_details.get('wait', 0.0)
                probe_stats = html_details.get('probe_stats', {})
                
                wait_times.append(wait_time)
                probe_stats_list.append(probe_stats)
                
                # Show result
                if wait_time <= 0.3:
                    print(f"✅ {wait_time:.3f}s", end="")
                else:
                    print(f"⚠️ {wait_time:.3f}s", end="")
                
                if probe_stats:
                    print(f" (polls: {probe_stats.get('poll_count', 0)}, "
                          f"strategy: {probe_stats.get('strategy', 'unknown')})")
                else:
                    print()
                
            except Exception as e:
                print(f"❌ Error: {e}")
                wait_times.append(None)
                probe_stats_list.append(None)
        
        print()
        print("=" * 80)
        print("RESULTS")
        print("=" * 80)
        
        # Filter out None values
        valid_wait_times = [t for t in wait_times if t is not None]
        
        if not valid_wait_times:
            print("❌ No valid measurements collected")
            return False
        
        # Calculate statistics
        valid_wait_times.sort()
        
        min_wait = valid_wait_times[0]
        max_wait = valid_wait_times[-1]
        avg_wait = sum(valid_wait_times) / len(valid_wait_times)
        median_wait = valid_wait_times[len(valid_wait_times) // 2]
        
        # Calculate percentiles
        p95_index = int(len(valid_wait_times) * 0.95)
        p95_wait = valid_wait_times[min(p95_index, len(valid_wait_times) - 1)]
        
        p99_index = int(len(valid_wait_times) * 0.99)
        p99_wait = valid_wait_times[min(p99_index, len(valid_wait_times) - 1)]
        
        # Count how many meet target
        under_target = sum(1 for t in valid_wait_times if t <= 0.3)
        percent_under_target = (under_target / len(valid_wait_times)) * 100
        
        print(f"Valid measurements: {len(valid_wait_times)}/{cycles}")
        print()
        print(f"Wait time statistics:")
        print(f"  Min:    {min_wait:.3f}s")
        print(f"  Max:    {max_wait:.3f}s")
        print(f"  Avg:    {avg_wait:.3f}s")
        print(f"  Median: {median_wait:.3f}s")
        print(f"  P95:    {p95_wait:.3f}s")
        print(f"  P99:    {p99_wait:.3f}s")
        print()
        
        # Target validation
        print(f"Target: <0.3s for ≥95% of cycles")
        print(f"Result: {under_target}/{len(valid_wait_times)} ({percent_under_target:.1f}%) under 0.3s")
        print()
        
        if percent_under_target >= 95.0 and p95_wait <= 0.3:
            print("✅ TARGET MET: ≥95% of cycles completed within 0.3s")
            success = True
        else:
            print("⚠️ TARGET NOT MET")
            if percent_under_target < 95.0:
                print(f"   - Only {percent_under_target:.1f}% under 0.3s (need ≥95%)")
            if p95_wait > 0.3:
                print(f"   - P95 is {p95_wait:.3f}s (need ≤0.3s)")
            success = False
        
        print()
        
        # Probe stats summary
        print("Probe statistics:")
        valid_stats = [s for s in probe_stats_list if s is not None]
        
        if valid_stats:
            strategies = {}
            total_polls = 0
            quick_checks = 0
            
            for stats in valid_stats:
                strategy = stats.get('strategy', 'unknown')
                strategies[strategy] = strategies.get(strategy, 0) + 1
                total_polls += stats.get('poll_count', 0)
                if stats.get('quick_check'):
                    quick_checks += 1
            
            avg_polls = total_polls / len(valid_stats)
            
            print(f"  Avg polls per cycle: {avg_polls:.1f}")
            print(f"  Quick checks (no wait): {quick_checks}/{len(valid_stats)} "
                  f"({quick_checks/len(valid_stats)*100:.1f}%)")
            print(f"  Strategy distribution:")
            for strategy, count in sorted(strategies.items(), key=lambda x: x[1], reverse=True):
                print(f"    - {strategy}: {count}/{len(valid_stats)} "
                      f"({count/len(valid_stats)*100:.1f}%)")
        
        print()
        print("=" * 80)
        
        return success
        
    finally:
        print("Closing driver...")
        driver.quit()
        print("✅ Driver closed")


def main():
    parser = argparse.ArgumentParser(description="Validate wait phase performance")
    parser.add_argument('--cycles', type=int, default=20, 
                        help='Number of cycles to test (default: 20)')
    args = parser.parse_args()
    
    if args.cycles < 1:
        print("Error: cycles must be at least 1")
        return 1
    
    success = validate_wait_performance(cycles=args.cycles)
    
    if success:
        print()
        print("🎉 VALIDATION PASSED")
        return 0
    else:
        print()
        print("❌ VALIDATION FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
