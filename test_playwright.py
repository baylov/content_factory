#!/usr/bin/env python3
"""
Simple test to verify Playwright setup works correctly
"""

import asyncio
import sys
from main import UpbitParser
from bs4 import BeautifulSoup

async def test_playwright():
    print("=" * 60)
    print("PLAYWRIGHT SETUP TEST")
    print("=" * 60)
    
    parser = UpbitParser()
    
    try:
        # Initialize browser
        print("\n1. Initializing Playwright browser...")
        await parser.init()
        print("✓ Browser initialized successfully")
        
        # Load page
        print("\n2. Loading Upbit notice page...")
        html, load_time = await parser.get_page_html()
        
        if html:
            print(f"✓ Page loaded successfully in {load_time:.3f}s")
            
            # Parse HTML
            print("\n3. Parsing HTML with BeautifulSoup...")
            soup = BeautifulSoup(html, 'html.parser')
            
            # Try to find news IDs
            links = soup.select('tr a[href*="/service_center/notice"]')
            print(f"✓ Found {len(links)} news links")
            
            if len(links) > 0:
                print("\n4. Sample news links:")
                for i, link in enumerate(links[:3], 1):
                    href = link.get('href', '')
                    title = link.get_text(strip=True)[:50]
                    print(f"   {i}. {title}... ({href})")
                
                print("\n" + "=" * 60)
                print("✅ TEST PASSED - Playwright setup working correctly!")
                print("=" * 60)
                return True
            else:
                print("\n❌ TEST FAILED - No news links found")
                return False
        else:
            print("❌ TEST FAILED - Could not load page")
            return False
            
    except Exception as e:
        print(f"\n❌ TEST FAILED - Error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Cleanup
        print("\n5. Closing browser...")
        await parser.close()
        print("✓ Browser closed")

if __name__ == "__main__":
    success = asyncio.run(test_playwright())
    sys.exit(0 if success else 1)
