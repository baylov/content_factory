#!/usr/bin/env python3
"""
Stability test for optimized HTML parsing.
Tests 100+ cycles to ensure reliability.
"""

import time
import logging
import sys
sys.path.append('/home/engine/project')

from main import init_driver, get_all_notice_ids_with_api, UPBIT_NOTICE_URL

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def stability_test(num_cycles=100):
    """
    Run stability test with multiple cycles.
    """
    print(f"🧪 STABILITY TEST: {num_cycles} cycles")
    print("=" * 50)
    
    driver = init_driver(enable_cdp=False)
    if not driver:
        print("❌ Failed to initialize driver")
        return
    
    try:
        success_count = 0
        failure_count = 0
        total_times = []
        notice_counts = []
        
        for i in range(num_cycles):
            cycle_start = time.time()
            
            try:
                # Test the optimized function
                notice_ids, method, timings = get_all_notice_ids_with_api(driver, known_endpoints=None, use_cdp=False)
                
                cycle_time = time.time() - cycle_start
                total_times.append(cycle_time)
                notice_counts.append(len(notice_ids))
                
                if notice_ids and len(notice_ids) > 0:
                    success_count += 1
                    if i % 20 == 0:  # Log every 20 cycles
                        print(f"✅ Cycle {i+1:3d}: {cycle_time:.3f}s, {len(notice_ids)} IDs")
                else:
                    failure_count += 1
                    print(f"❌ Cycle {i+1:3d}: {cycle_time:.3f}s, NO IDs!")
                
            except Exception as e:
                failure_count += 1
                print(f"💥 Cycle {i+1:3d}: EXCEPTION - {e}")
            
            # Small delay between cycles
            time.sleep(0.05)
        
        # Analysis
        print("\n" + "=" * 50)
        print("📊 STABILITY TEST RESULTS")
        print("=" * 50)
        
        if total_times:
            avg_time = sum(total_times) / len(total_times)
            min_time = min(total_times)
            max_time = max(total_times)
            p95_time = sorted(total_times)[int(len(total_times) * 0.95)]
            
            print(f"Performance:")
            print(f"  Average: {avg_time:.3f}s")
            print(f"  Min/Max: {min_time:.3f}s - {max_time:.3f}s")
            print(f"  P95: {p95_time:.3f}s")
            
            # Performance categories
            if avg_time < 1.0:
                grade = "⚡ EXCELLENT"
            elif avg_time < 1.5:
                grade = "✅ GOOD"
            elif avg_time < 2.0:
                grade = "🟡 ACCEPTABLE"
            elif avg_time < 2.5:
                grade = "🟠 SLOW"
            else:
                grade = "❌ TOO SLOW"
            
            print(f"  Grade: {grade}")
        
        print(f"\nReliability:")
        print(f"  Success: {success_count}/{num_cycles} ({success_count/num_cycles*100:.1f}%)")
        print(f"  Failures: {failure_count}/{num_cycles} ({failure_count/num_cycles*100:.1f}%)")
        
        if notice_counts:
            avg_notices = sum(notice_counts) / len(notice_counts)
            print(f"\nNotice Detection:")
            print(f"  Average IDs per cycle: {avg_notices:.1f}")
            print(f"  Min/Max: {min(notice_counts)} - {max(notice_counts)}")
            
            # Check for consistency
            consistent_detections = sum(1 for count in notice_counts if count > 0)
            print(f"  Consistency: {consistent_detections}/{num_cycles} ({consistent_detections/num_cycles*100:.1f}%)")
        
        # Final assessment
        print(f"\n🎯 ASSESSMENT:")
        if success_count >= num_cycles * 0.95 and avg_time < 2.0:
            print("✅ PASSED: Reliable and fast enough for production")
        elif success_count >= num_cycles * 0.90:
            print("🟡 MARGINAL: Mostly reliable, may need minor tweaks")
        else:
            print("❌ FAILED: Too many failures or too slow")
        
        return {
            'avg_time': avg_time if total_times else 0,
            'success_rate': success_count / num_cycles,
            'consistent_detections': consistent_detections / num_cycles if notice_counts else 0
        }
    
    finally:
        driver.quit()
        print("\n✅ Driver closed")

if __name__ == "__main__":
    stability_test(num_cycles=50)  # Start with 50 cycles for quick test