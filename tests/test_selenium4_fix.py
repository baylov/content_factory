#!/usr/bin/env python3
"""
Test script to verify Selenium 4.x compatibility fix
"""
import sys
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def test_init_driver():
    """Test that init_driver works without desired_capabilities error"""
    try:
        from main import init_driver
        
        # Test 1: init_driver with CDP enabled (the problematic case)
        print("🧪 Test 1: Initializing driver with CDP enabled...")
        driver = init_driver(enable_cdp=True)
        
        if driver is None:
            print("❌ FAIL: Driver initialization returned None")
            return False
        
        print("✅ PASS: Driver initialized successfully with CDP")
        
        # Test 2: Check that driver is a WebDriver instance
        from selenium import webdriver
        if not isinstance(driver, webdriver.Chrome):
            print("❌ FAIL: Driver is not a Chrome WebDriver instance")
            driver.quit()
            return False
        
        print("✅ PASS: Driver is a valid Chrome WebDriver instance")
        
        # Clean up
        driver.quit()
        print("✅ Driver closed successfully")
        
        # Test 3: init_driver without CDP (should also work)
        print("\n🧪 Test 2: Initializing driver without CDP...")
        driver2 = init_driver(enable_cdp=False)
        
        if driver2 is None:
            print("❌ FAIL: Driver initialization returned None (without CDP)")
            return False
        
        print("✅ PASS: Driver initialized successfully without CDP")
        driver2.quit()
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Selenium 4.x Compatibility Test")
    print("=" * 60)
    print()
    
    success = test_init_driver()
    
    print()
    print("=" * 60)
    if success:
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        sys.exit(0)
    else:
        print("❌ TESTS FAILED")
        print("=" * 60)
        sys.exit(1)
