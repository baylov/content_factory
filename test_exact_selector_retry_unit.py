#!/usr/bin/env python3
"""
Unit tests for exact_id selector retry logic with stubbed drivers.
Tests various scenarios including late-rendering, instant success, and fallback triggers.
"""

import sys
import time
from unittest.mock import Mock, MagicMock


def create_mock_driver_instant_success():
    """
    Mock driver where exact_id selector succeeds immediately.
    """
    driver = Mock()
    
    def execute_script(script, *args):
        if 'exactIdLinks' in script:
            # Simulate exact_id finding links immediately
            return {
                'exact_id_count': 25,
                'all_notice_count': 30,
                'readyState': 'complete',
                'containerVisible': True
            }
        elif 'broader_content_exists' in script:
            return {
                'broader_content_exists': True,
                'exact_id_count': 25,
                'all_notice_count': 30,
                'tr_notice_count': 28,
                'any_id_count': 26,
                'readyState': 'complete',
                'containerVisible': True
            }
        return []
    
    driver.execute_script = Mock(side_effect=execute_script)
    return driver


def create_mock_driver_late_rendering():
    """
    Mock driver where exact_id selector fails first 3 attempts, then succeeds.
    Simulates late-rendering scenario.
    """
    driver = Mock()
    attempt_count = {'value': 0}
    
    def execute_script(script, *args):
        if 'exactIdLinks' in script:
            attempt_count['value'] += 1
            
            if attempt_count['value'] < 3:
                # First 2 attempts: exact_id returns 0, but broader selectors see content
                return {
                    'exact_id_count': 0,
                    'all_notice_count': 30,
                    'readyState': 'interactive',
                    'containerVisible': True
                }
            else:
                # 3rd attempt onwards: exact_id succeeds
                return {
                    'exact_id_count': 25,
                    'all_notice_count': 30,
                    'readyState': 'complete',
                    'containerVisible': True
                }
        elif 'broader_content_exists' in script:
            return {
                'broader_content_exists': True,
                'exact_id_count': 25,
                'all_notice_count': 30,
                'tr_notice_count': 28,
                'any_id_count': 26,
                'readyState': 'complete',
                'containerVisible': True
            }
        return []
    
    driver.execute_script = Mock(side_effect=execute_script)
    return driver


def create_mock_driver_total_failure():
    """
    Mock driver where exact_id selector always returns 0 and no broader content exists.
    """
    driver = Mock()
    
    def execute_script(script, *args):
        if 'exactIdLinks' in script:
            return {
                'exact_id_count': 0,
                'all_notice_count': 0,
                'readyState': 'complete',
                'containerVisible': False
            }
        elif 'broader_content_exists' in script:
            return {
                'broader_content_exists': False,
                'exact_id_count': 0,
                'all_notice_count': 0,
                'tr_notice_count': 0,
                'any_id_count': 0,
                'readyState': 'complete',
                'containerVisible': False
            }
        return []
    
    driver.execute_script = Mock(side_effect=execute_script)
    return driver


def create_mock_driver_broader_content_only():
    """
    Mock driver where exact_id fails but broader selectors see content.
    Tests fallback trigger logic.
    """
    driver = Mock()
    
    def execute_script(script, *args):
        if 'exactIdLinks' in script:
            return {
                'exact_id_count': 0,
                'all_notice_count': 30,
                'readyState': 'complete',
                'containerVisible': True
            }
        elif 'broader_content_exists' in script:
            return {
                'broader_content_exists': True,
                'exact_id_count': 0,
                'all_notice_count': 30,
                'tr_notice_count': 28,
                'any_id_count': 26,
                'readyState': 'complete',
                'containerVisible': True
            }
        return []
    
    driver.execute_script = Mock(side_effect=execute_script)
    return driver


def test_instant_success():
    """
    Test: Exact_id selector succeeds on first attempt.
    Expected: success=True, attempts=1, time < 5ms
    """
    print("=" * 70)
    print("TEST 1: Instant success (exact_id works on first attempt)")
    print("=" * 70)
    
    # Import after Mock setup
    from main import retry_exact_id_selector
    
    driver = create_mock_driver_instant_success()
    
    result = retry_exact_id_selector(driver, max_retries=5, retry_interval=0.04, max_total_time=0.2)
    
    print(f"Result: {result}")
    
    # Assertions
    assert result['success'] == True, "Should succeed"
    assert result['count'] == 25, "Should find 25 links"
    assert result['attempts'] == 1, "Should succeed on first attempt"
    assert result['elapsed_time'] < 0.005, f"Should be instant (< 5ms), got {result['elapsed_time']*1000:.0f}ms"
    
    print("✅ PASS: Instant success works correctly")
    return True


def test_late_rendering():
    """
    Test: Exact_id selector fails first 2 attempts, succeeds on 3rd.
    Expected: success=True, attempts=3, time ≈ 80-100ms (2 retries * 40ms)
    """
    print("\n" + "=" * 70)
    print("TEST 2: Late rendering (exact_id succeeds after retries)")
    print("=" * 70)
    
    from main import retry_exact_id_selector
    
    driver = create_mock_driver_late_rendering()
    
    result = retry_exact_id_selector(driver, max_retries=5, retry_interval=0.04, max_total_time=0.2)
    
    print(f"Result: {result}")
    
    # Assertions
    assert result['success'] == True, "Should succeed after retries"
    assert result['count'] == 25, "Should find 25 links"
    assert result['attempts'] == 3, f"Should succeed on 3rd attempt, got {result['attempts']}"
    assert 0.070 < result['elapsed_time'] < 0.150, \
        f"Should take ~80-100ms (2 retries * 40ms), got {result['elapsed_time']*1000:.0f}ms"
    
    print("✅ PASS: Late rendering retry works correctly")
    return True


def test_total_failure():
    """
    Test: Exact_id selector always fails, no broader content.
    Expected: success=False, attempts=5, time ≈ 160-200ms (4 retries * 40ms)
    """
    print("\n" + "=" * 70)
    print("TEST 3: Total failure (no content detected)")
    print("=" * 70)
    
    from main import retry_exact_id_selector
    
    driver = create_mock_driver_total_failure()
    
    result = retry_exact_id_selector(driver, max_retries=5, retry_interval=0.04, max_total_time=0.2)
    
    print(f"Result: {result}")
    
    # Assertions
    assert result['success'] == False, "Should fail"
    assert result['count'] == 0, "Should find 0 links"
    assert result['attempts'] <= 5, f"Should make at most 5 attempts, got {result['attempts']}"
    assert result['elapsed_time'] < 0.25, \
        f"Should respect max_total_time=0.2s (with buffer), got {result['elapsed_time']*1000:.0f}ms"
    
    # Check DOM state
    dom_state = result['dom_state']
    assert dom_state['broader_content_exists'] == False, "Should detect no broader content"
    
    print("✅ PASS: Total failure detection works correctly")
    return True


def test_broader_content_fallback():
    """
    Test: Exact_id fails but broader selectors see content.
    Expected: success=False, broader_content_exists=True (triggers fallback)
    """
    print("\n" + "=" * 70)
    print("TEST 4: Broader content exists (should trigger fallback)")
    print("=" * 70)
    
    from main import retry_exact_id_selector
    
    driver = create_mock_driver_broader_content_only()
    
    result = retry_exact_id_selector(driver, max_retries=5, retry_interval=0.04, max_total_time=0.2)
    
    print(f"Result: {result}")
    
    # Assertions
    assert result['success'] == False, "Should fail exact_id"
    assert result['count'] == 0, "Should find 0 links with exact_id"
    
    # Check DOM state for fallback trigger
    dom_state = result['dom_state']
    assert dom_state['broader_content_exists'] == True, "Should detect broader content"
    assert dom_state['all_notice_count'] > 0, "Should see all_notice links"
    
    print("✅ PASS: Broader content detection works correctly")
    return True


def test_time_constraints():
    """
    Test: Verify retry loop respects time constraints.
    Expected: Never exceeds max_total_time by more than one interval
    """
    print("\n" + "=" * 70)
    print("TEST 5: Time constraints (max_total_time respected)")
    print("=" * 70)
    
    from main import retry_exact_id_selector
    
    driver = create_mock_driver_total_failure()
    
    # Test with shorter max_total_time
    result = retry_exact_id_selector(driver, max_retries=10, retry_interval=0.05, max_total_time=0.1)
    
    print(f"Result: {result}")
    print(f"Time taken: {result['elapsed_time']*1000:.0f}ms (max allowed: 100ms)")
    
    # Should stop early due to time constraint, not exhaust all 10 retries
    assert result['elapsed_time'] < 0.15, \
        f"Should respect max_total_time (100ms + 50ms buffer), got {result['elapsed_time']*1000:.0f}ms"
    assert result['attempts'] < 10, \
        f"Should stop before max_retries due to time constraint, got {result['attempts']} attempts"
    
    print("✅ PASS: Time constraints work correctly")
    return True


def test_check_dom_state_function():
    """
    Test: Verify check_dom_state_for_fallback function works correctly.
    """
    print("\n" + "=" * 70)
    print("TEST 6: check_dom_state_for_fallback function")
    print("=" * 70)
    
    from main import check_dom_state_for_fallback
    
    driver = create_mock_driver_broader_content_only()
    
    dom_state = check_dom_state_for_fallback(driver)
    
    print(f"DOM State: {dom_state}")
    
    # Assertions
    assert dom_state['broader_content_exists'] == True, "Should detect broader content"
    assert dom_state['exact_id_count'] == 0, "exact_id should be 0"
    assert dom_state['all_notice_count'] == 30, "all_notice should be 30"
    assert dom_state['readyState'] == 'complete', "readyState should be complete"
    assert dom_state['containerVisible'] == True, "container should be visible"
    
    print("✅ PASS: check_dom_state_for_fallback works correctly")
    return True


def main():
    """
    Run all unit tests.
    """
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " UNIT TESTS: EXACT_ID SELECTOR RETRY LOGIC ".center(68) + "║")
    print("╚" + "=" * 68 + "╝")
    print()
    
    tests = [
        ("Instant success", test_instant_success),
        ("Late rendering", test_late_rendering),
        ("Total failure", test_total_failure),
        ("Broader content fallback", test_broader_content_fallback),
        ("Time constraints", test_time_constraints),
        ("DOM state function", test_check_dom_state_function),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except AssertionError as e:
            print(f"\n❌ FAIL: {e}")
            results.append((name, False))
        except Exception as e:
            print(f"\n❌ ERROR in test '{name}': {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print("\n" + "=" * 70)
    print(f"Passed: {passed}/{total} tests")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        print("\n✅ Acceptance criteria:")
        print("  1. ✅ Retry logic correctly handles instant success")
        print("  2. ✅ Retry logic recovers from late-rendering (3+ attempts)")
        print("  3. ✅ Retry logic detects total failure")
        print("  4. ✅ Retry logic triggers fallback when broader content exists")
        print("  5. ✅ Retry loop respects time constraints (<200ms)")
        print("  6. ✅ DOM state checking works for fallback decisions")
        return True
    else:
        print(f"❌ SOME TESTS FAILED: {total - passed} out of {total}")
        return False


if __name__ == "__main__":
    success = main()
    print()
    sys.exit(0 if success else 1)
