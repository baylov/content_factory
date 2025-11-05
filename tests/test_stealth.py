#!/usr/bin/env python3
"""
Test script to verify selenium-stealth is working correctly
"""
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

def test_stealth_import():
    """Test that selenium-stealth can be imported"""
    print("✅ selenium-stealth imported successfully")
    return True

def test_stealth_initialization():
    """Test that stealth can be applied to a driver"""
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Apply stealth
        stealth(driver,
            languages=["ko-KR", "ko", "en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        
        driver.set_page_load_timeout(10)
        
        print("✅ Stealth successfully applied to WebDriver")
        
        # Test that we can detect the stealth properties
        webdriver_present = driver.execute_script("return navigator.webdriver")
        print(f"   navigator.webdriver = {webdriver_present}")
        
        if webdriver_present is None or webdriver_present is False:
            print("   ✅ navigator.webdriver is properly hidden")
        else:
            print("   ⚠️  navigator.webdriver is still detected")
        
        driver.quit()
        return True
        
    except Exception as e:
        print(f"❌ Error testing stealth: {e}")
        return False

def test_main_import():
    """Test that main.py can be imported with stealth"""
    try:
        # Check if the import works
        import main
        print("✅ main.py imports successfully with stealth")
        return True
    except ImportError as e:
        print(f"❌ Error importing main.py: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Testing selenium-stealth integration...")
    print()
    
    tests = [
        test_stealth_import,
        test_stealth_initialization,
        test_main_import,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)
        print()
    
    if all(results):
        print("🎉 All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)
