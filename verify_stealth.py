#!/usr/bin/env python3
"""
Verification script to check all stealth implementation requirements
"""
import re

def check_requirements_txt():
    """Check that selenium-stealth is in requirements.txt"""
    with open('requirements.txt', 'r') as f:
        content = f.read()
    
    if 'selenium-stealth>=1.0.6' in content:
        print("✅ selenium-stealth>=1.0.6 in requirements.txt")
        return True
    else:
        print("❌ selenium-stealth not found in requirements.txt")
        return False

def check_stealth_import():
    """Check that stealth is imported in main.py"""
    with open('main.py', 'r') as f:
        content = f.read()
    
    if 'from selenium_stealth import stealth' in content:
        print("✅ selenium_stealth imported in main.py")
        return True
    else:
        print("❌ selenium_stealth not imported")
        return False

def check_stealth_applied():
    """Check that stealth is applied to driver"""
    with open('main.py', 'r') as f:
        content = f.read()
    
    checks = [
        ('stealth(driver,', '✅ stealth() called on driver'),
        ('languages=["ko-KR", "ko", "en-US", "en"]', '✅ Korean and English languages set'),
        ('vendor="Google Inc."', '✅ vendor set to Google Inc.'),
        ('platform="Win32"', '✅ platform set to Win32'),
        ('webgl_vendor="Intel Inc."', '✅ webgl_vendor set'),
        ('renderer="Intel Iris OpenGL Engine"', '✅ renderer set'),
        ('fix_hairline=True', '✅ fix_hairline enabled'),
    ]
    
    all_ok = True
    for pattern, message in checks:
        if pattern in content:
            print(message)
        else:
            print(f"❌ Missing: {pattern}")
            all_ok = False
    
    return all_ok

def check_timeout():
    """Check that timeout is increased to 10 seconds"""
    with open('main.py', 'r') as f:
        content = f.read()
    
    if 'set_page_load_timeout(10)' in content:
        print("✅ Page load timeout increased to 10 seconds")
        return True
    else:
        print("❌ Timeout not set to 10 seconds")
        return False

def check_sleep_pauses():
    """Check that sleep pauses are increased to 1 second"""
    with open('main.py', 'r') as f:
        lines = f.readlines()
    
    sleep_1_count = 0
    for line in lines:
        if 'time.sleep(1)' in line:
            sleep_1_count += 1
    
    if sleep_1_count >= 3:
        print(f"✅ Found {sleep_1_count} instances of time.sleep(1)")
        return True
    else:
        print(f"❌ Expected at least 3 instances of time.sleep(1), found {sleep_1_count}")
        return False

def check_headless_mode():
    """Check that new headless mode is used"""
    with open('main.py', 'r') as f:
        content = f.read()
    
    if '--headless=new' in content:
        print("✅ Using new headless mode (--headless=new)")
        return True
    else:
        print("❌ Not using --headless=new")
        return False

def check_automation_detection():
    """Check that automation detection is disabled"""
    with open('main.py', 'r') as f:
        content = f.read()
    
    checks = [
        ('excludeSwitches", ["enable-automation"]', '✅ excludeSwitches enable-automation'),
        ('useAutomationExtension\', False', '✅ useAutomationExtension disabled'),
    ]
    
    all_ok = True
    for pattern, message in checks:
        if pattern in content:
            print(message)
        else:
            print(f"❌ Missing: {pattern}")
            all_ok = False
    
    return all_ok

def check_logging():
    """Check that stealth logging is updated"""
    with open('main.py', 'r') as f:
        content = f.read()
    
    checks = [
        ('STEALTH режимом инициализирован', '✅ Stealth mode logging message'),
        ('Скрыты признаки автоматизации', '✅ Logging mentions automation hiding'),
        ('WebGL/Canvas fingerprint защита', '✅ Logging mentions fingerprint protection'),
    ]
    
    all_ok = True
    for pattern, message in checks:
        if pattern in content:
            print(message)
        else:
            print(f"❌ Missing logging: {pattern}")
            all_ok = False
    
    return all_ok

if __name__ == "__main__":
    print("🔍 Verifying stealth implementation...")
    print()
    
    results = []
    
    print("1. Requirements:")
    results.append(check_requirements_txt())
    print()
    
    print("2. Import:")
    results.append(check_stealth_import())
    print()
    
    print("3. Stealth Configuration:")
    results.append(check_stealth_applied())
    print()
    
    print("4. Timeout:")
    results.append(check_timeout())
    print()
    
    print("5. Sleep Pauses:")
    results.append(check_sleep_pauses())
    print()
    
    print("6. Headless Mode:")
    results.append(check_headless_mode())
    print()
    
    print("7. Automation Detection:")
    results.append(check_automation_detection())
    print()
    
    print("8. Logging:")
    results.append(check_logging())
    print()
    
    if all(results):
        print("=" * 50)
        print("🎉 ALL CHECKS PASSED!")
        print("=" * 50)
        print()
        print("✅ Acceptance Criteria:")
        print("  1. ✅ selenium-stealth installed")
        print("  2. ✅ Stealth applied to WebDriver")
        print("  3. ✅ Timeout increased to 10 seconds")
        print("  4. ✅ Pause after loading increased to 1 second")
        print("  5. ✅ New headless mode enabled")
        print("  6. ✅ Automation detection disabled")
        print("  7. ✅ Proper logging messages")
    else:
        print("=" * 50)
        print("❌ SOME CHECKS FAILED")
        print("=" * 50)
