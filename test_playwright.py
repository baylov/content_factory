#!/usr/bin/env python3
"""
Simple test to verify Playwright setup works correctly
"""

import asyncio
import sys
import re
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
            
            # Try to find news IDs with CORRECTED selector
            links = soup.select('a[href*="/service_center/notice?id="]')
            print(f"✓ Found {len(links)} news links")
            
            if len(links) == 0:
                # Fallback
                print("   Primary selector failed, trying regex fallback...")
                links = soup.find_all('a', href=re.compile(r'/service_center/notice\?id=\d+'))
                print(f"✓ Fallback regex found {len(links)} news links")
            
            if len(links) == 0:
                print("\n4. Analyzing page structure...")
                
                # Ищем все ссылки на странице
                all_links = soup.find_all('a', href=True)
                print(f"   Total links on page: {len(all_links)}")
                
                # Показываем первые 10 ссылок
                print("\n   First 10 links:")
                for i, link in enumerate(all_links[:10], 1):
                    href = link['href']
                    text = link.get_text(strip=True)[:40]
                    print(f"   {i}. {text} -> {href}")
                
                # Ищем упоминания "notice" или "공지"
                notice_related = [l for l in all_links if 'notice' in l['href'].lower() or '공지' in l.get_text()]
                print(f"\n   Links with 'notice' or '공지': {len(notice_related)}")
                
                if notice_related:
                    print("\n   First 5 notice-related links:")
                    for i, link in enumerate(notice_related[:5], 1):
                        href = link['href']
                        text = link.get_text(strip=True)[:40]
                        print(f"   {i}. {text} -> {href}")
                
                # Показываем структуру таблицы
                tables = soup.find_all('table')
                print(f"\n   Tables found: {len(tables)}")
                
                divs_with_list = soup.find_all('div', class_=re.compile('list|notice|board', re.I))
                print(f"   Divs with list/notice/board class: {len(divs_with_list)}")
                
                if divs_with_list:
                    print("\n   First 3 divs with list/notice/board class:")
                    for i, div in enumerate(divs_with_list[:3], 1):
                        class_attr = div.get('class', [])
                        data_attrs = {k: v for k, v in div.attrs.items() if k.startswith('data-')}
                        links_in_div = div.find_all('a', href=True)
                        print(f"   {i}. Classes: {class_attr}, data-attrs: {data_attrs}, links inside: {len(links_in_div)}")
                
                print("\n❌ TEST FAILED - No news links found with current selector")
                print("HTML saved to upbit_page_debug.html for manual analysis")
                return False
            
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
