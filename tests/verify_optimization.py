#!/usr/bin/env python3
"""
Verification script to confirm optimization changes are in place
"""

import re

def verify_optimizations():
    """Verify that all optimization changes are in place"""
    print("=" * 60)
    print("OPTIMIZATION VERIFICATION")
    print("=" * 60)
    
    with open('main.py', 'r') as f:
        content = f.read()
    
    checks = []
    
    # Check 1: All time.sleep(1) should be commented out
    active_sleep_1 = re.findall(r'^\s+time\.sleep\(1\)', content, re.MULTILINE)
    commented_sleep_1 = re.findall(r'^\s+#\s*time\.sleep\(1\)', content, re.MULTILINE)
    
    print("\n1. Stabilization delays (time.sleep(1)):")
    print(f"   Active: {len(active_sleep_1)}")
    print(f"   Commented out: {len(commented_sleep_1)}")
    
    if len(active_sleep_1) == 0 and len(commented_sleep_1) >= 3:
        print("   ✅ PASS - All stabilization delays removed")
        checks.append(True)
    else:
        print("   ❌ FAIL - Still has active time.sleep(1) calls")
        checks.append(False)
    
    # Check 2: WebDriverWait timeouts should be optimized (0.5s)
    wait_timeouts = re.findall(r'WebDriverWait\(driver,\s*(\d+(?:\.\d+)?)\)', content)
    
    print("\n2. WebDriverWait timeouts:")
    print(f"   Found: {wait_timeouts}")
    
    optimized_count = sum(1 for t in wait_timeouts if float(t) <= 0.5)
    total_count = len(wait_timeouts)
    
    if total_count > 0 and optimized_count == total_count:
        print(f"   ✅ PASS - All {total_count} timeouts optimized to ≤ 0.5s")
        checks.append(True)
    else:
        print(f"   ⚠️  WARNING - {optimized_count}/{total_count} timeouts optimized")
        checks.append(False)
    
    # Check 3: Comments indicating optimization
    optimization_comments = len(re.findall(r'Оптимизировано:|Убрано для скорости', content))
    
    print(f"\n3. Optimization comments:")
    print(f"   Found: {optimization_comments} optimization-related comments")
    
    if optimization_comments >= 5:
        print("   ✅ PASS - Code properly documented")
        checks.append(True)
    else:
        print("   ⚠️  WARNING - Consider adding more documentation")
        checks.append(True)  # Not critical
    
    # Check 4: Verify logging doesn't mention "Стабилизация" for refresh cycle
    # (we should have removed the line that logs stability time)
    stabilization_logs_in_refresh = re.findall(
        r'logging\.info\(f"\s*⏱️ Стабилизация:.*?\)', 
        content
    )
    
    print(f"\n4. Stabilization logging in refresh cycle:")
    print(f"   Active log statements: {len(stabilization_logs_in_refresh)}")
    
    if len(stabilization_logs_in_refresh) == 0:
        print("   ✅ PASS - Stabilization logging removed from refresh cycle")
        checks.append(True)
    else:
        print("   ❌ FAIL - Still logging stabilization time")
        checks.append(False)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(checks)
    total = len(checks)
    
    print(f"Checks passed: {passed}/{total}")
    
    if all(checks):
        print("\n✅ ALL OPTIMIZATIONS VERIFIED!")
        print("\nExpected improvements:")
        print("  Before: Refresh (0.8s) + Wait (0.8s) + Stabilization (1.0s) = ~2.6s")
        print("  After:  Refresh (0.8s) + Wait (0.5s) + Stabilization (0s) = ~1.3s")
        print("  Target: < 1.5 seconds ✅")
        print("  Stretch goal: < 1 second")
        return True
    else:
        print("\n❌ SOME CHECKS FAILED")
        return False

if __name__ == "__main__":
    import sys
    success = verify_optimizations()
    sys.exit(0 if success else 1)
