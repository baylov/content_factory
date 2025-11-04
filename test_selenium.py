#!/usr/bin/env python3
"""
Simple test to verify Selenium setup works correctly
"""

import sys
import re
from main import init_driver, get_all_notice_ids, get_notice_by_id

def test_selenium():
    print("=" * 60)
    print("SELENIUM SETUP TEST")
    print("=" * 60)
    
    driver = None
    
    try:
        # Initialize browser
        print("\n1. Initializing Selenium browser...")
        driver = init_driver()
        
        if not driver:
            print("❌ TEST FAILED - Could not initialize browser")
            return False
        
        print("✓ Browser initialized successfully")
        
        # Load page
        print("\n2. Loading Upbit notice page...")
        driver.get("https://upbit.com/service_center/notice")
        print("✓ Page loaded successfully")
        
        # Wait for content
        print("\n3. Waiting for page content...")
        import time
        time.sleep(1)
        print("✓ Page content ready")
        
        # Get notice IDs
        print("\n4. Fetching notice IDs...")
        notice_ids = get_all_notice_ids(driver)
        
        if not notice_ids:
            print("❌ TEST FAILED - No notice IDs found")
            
            # Debug information
            print("\n   Debug: Checking page source...")
            page_source = driver.page_source
            print(f"   Page source length: {len(page_source)} characters")
            
            # Check for notice links
            if 'service_center/notice' in page_source:
                print("   ✓ Found 'service_center/notice' in page source")
            else:
                print("   ❌ 'service_center/notice' not found in page source")
            
            return False
        
        print(f"✓ Found {len(notice_ids)} notice IDs")
        print(f"   Sample IDs: {notice_ids[:5]}")
        
        # Get details for first notice
        print("\n5. Fetching details for first notice...")
        first_id = notice_ids[0]
        notice = get_notice_by_id(driver, first_id)
        
        if not notice:
            print(f"❌ Could not fetch details for notice ID {first_id}")
            return False
        
        print(f"✓ Successfully fetched notice details:")
        print(f"   ID: {notice['id']}")
        print(f"   Title: {notice['title'][:50]}...")
        print(f"   Link: {notice['link']}")
        
        print("\n" + "=" * 60)
        print("✅ TEST PASSED - Selenium setup working correctly!")
        print("=" * 60)
        return True
            
    except Exception as e:
        print(f"\n❌ TEST FAILED - Error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Cleanup
        if driver:
            print("\n6. Closing browser...")
            driver.quit()
            print("✓ Browser closed")

if __name__ == "__main__":
    success = test_selenium()
    sys.exit(0 if success else 1)
