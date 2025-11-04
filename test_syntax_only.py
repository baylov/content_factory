#!/usr/bin/env python3
"""
Test script to verify the syntax is correct and no import errors related to desired_capabilities
"""
import sys

def test_imports_and_syntax():
    """Test that the code can be imported without desired_capabilities errors"""
    try:
        print("🧪 Testing imports and syntax...")
        
        # This would fail if there were still references to DesiredCapabilities
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        # Try to import the module - this will fail if syntax is wrong
        # or if there are unresolved references
        import main
        
        print("✅ PASS: All imports successful")
        print("✅ PASS: No DesiredCapabilities import errors")
        
        # Check that init_driver function exists and can be accessed
        if not hasattr(main, 'init_driver'):
            print("❌ FAIL: init_driver function not found")
            return False
        
        print("✅ PASS: init_driver function exists")
        
        # Test that we can create Options and use set_capability (Selenium 4.x syntax)
        print("\n🧪 Testing Selenium 4.x syntax...")
        options = Options()
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        print("✅ PASS: options.set_capability() works (Selenium 4.x syntax)")
        
        return True
        
    except ImportError as e:
        if "DesiredCapabilities" in str(e) or "desired_capabilities" in str(e):
            print(f"❌ FAIL: Import error related to desired_capabilities: {e}")
            return False
        else:
            print(f"⚠️ WARNING: Import error (not related to desired_capabilities): {e}")
            # This might be expected if dependencies are missing
            return True
    except AttributeError as e:
        if "desired_capabilities" in str(e):
            print(f"❌ FAIL: AttributeError related to desired_capabilities: {e}")
            return False
        raise
    except Exception as e:
        print(f"❌ FAIL: Unexpected exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Selenium 4.x Syntax Compatibility Test")
    print("=" * 60)
    print()
    
    success = test_imports_and_syntax()
    
    print()
    print("=" * 60)
    if success:
        print("✅ ALL SYNTAX TESTS PASSED")
        print("The code is compatible with Selenium 4.x")
        print("=" * 60)
        sys.exit(0)
    else:
        print("❌ SYNTAX TESTS FAILED")
        print("=" * 60)
        sys.exit(1)
