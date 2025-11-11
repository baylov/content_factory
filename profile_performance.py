#!/usr/bin/env python3
"""
Performance analysis script for HTML parsing.
Measures the timing of each phase: Load, Wait, Parse
"""

import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

# Import from main
import sys
sys.path.append('/home/engine/project')

from main import init_driver, get_all_notice_ids_with_api, UPBIT_NOTICE_URL

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def profile_html_parsing(num_cycles=5):
    """
    Profile HTML parsing performance over multiple cycles.
    """
    print("🔍 PERFORMANCE ANALYSIS: HTML Parsing")
    print("=" * 50)
    
    # Initialize driver
    driver = init_driver(enable_cdp=False)
    if not driver:
        print("❌ Failed to initialize driver")
        return
    
    try:
        total_times = []
        load_times = []
        wait_times = []
        parse_times = []
        
        for i in range(num_cycles):
            print(f"\n🔄 Cycle {i+1}/{num_cycles}")
            print("-" * 30)
            
            cycle_start = time.time()
            
            # Load phase
            load_start = time.time()
            driver.get(UPBIT_NOTICE_URL)
            load_time = time.time() - load_start
            load_times.append(load_time)
            print(f"⏱️  Load: {load_time:.3f}s")
            
            # Wait phase (simulate the wait_for_notices_js)
            wait_start = time.time()
            
            # Quick readiness check
            try:
                probe_result = driver.execute_script("""
                    const result = {
                        ready: false,
                        readyState: document.readyState,
                        count: 0,
                        strategy: null,
                        containerVisible: false
                    };
                    
                    if (document.readyState === 'loading') {
                        return result;
                    }
                    
                    const containers = document.querySelectorAll('table, .notice-list, [class*="notice"], tbody');
                    result.containerVisible = containers.length > 0;
                    
                    let links = document.querySelectorAll('a[href*="/service_center/notice?id="]');
                    if (links.length > 0) {
                        result.count = links.length;
                        result.strategy = 'exact_id';
                        result.ready = true;
                        return result;
                    }
                    
                    links = document.querySelectorAll('a[href*="/service_center/notice"]');
                    if (links.length > 0) {
                        result.count = links.length;
                        result.strategy = 'all_notice';
                        result.ready = true;
                        return result;
                    }
                    
                    return result;
                """)
                
                if not probe_result['ready']:
                    # Poll for readiness
                    max_wait = 0.15
                    check_interval = 0.015
                    poll_count = 0
                    
                    while time.time() - wait_start < max_wait:
                        poll_count += 1
                        try:
                            links = driver.execute_script("""
                                return document.querySelectorAll('a[href*="/service_center/notice?id="]').length;
                            """)
                            if links > 0:
                                break
                        except:
                            pass
                        time.sleep(check_interval)
                    
                    print(f"   📊 Polled {poll_count} times for readiness")
                
            except Exception as e:
                print(f"   ⚠️ Wait phase error: {e}")
            
            wait_time = time.time() - wait_start
            wait_times.append(wait_time)
            print(f"⏱️  Wait: {wait_time:.3f}s")
            
            # Parse phase
            parse_start = time.time()
            
            try:
                notice_ids = driver.execute_script("""
                    const links = document.querySelectorAll('a[href*="/service_center/notice?id="]');
                    const ids = [];
                    for (let link of links) {
                        const href = link.getAttribute('href');
                        const match = href.match(/id=(\\d+)/);
                        if (match) {
                            ids.push(parseInt(match[1]));
                        }
                    }
                    return ids;
                """)
                print(f"📋 Found {len(notice_ids)} notice IDs: {notice_ids[:5]}{'...' if len(notice_ids) > 5 else ''}")
                
            except Exception as e:
                print(f"❌ Parse error: {e}")
                notice_ids = []
            
            parse_time = time.time() - parse_start
            parse_times.append(parse_time)
            print(f"⏱️  Parse: {parse_time:.3f}s")
            
            # Total cycle time
            total_time = time.time() - cycle_start
            total_times.append(total_time)
            print(f"⏱️  TOTAL: {total_time:.3f}s")
            
            # Wait between cycles (simulating current 50-100ms)
            time.sleep(0.075)  # 75ms average
        
        # Analysis
        print("\n" + "=" * 50)
        print("📊 PERFORMANCE SUMMARY")
        print("=" * 50)
        
        if total_times:
            avg_total = sum(total_times) / len(total_times)
            avg_load = sum(load_times) / len(load_times)
            avg_wait = sum(wait_times) / len(wait_times)
            avg_parse = sum(parse_times) / len(parse_times)
            
            print(f"Average Total Time: {avg_total:.3f}s")
            print(f"  - Load:  {avg_load:.3f}s ({avg_load/avg_total*100:.1f}%)")
            print(f"  - Wait:  {avg_wait:.3f}s ({avg_wait/avg_total*100:.1f}%)")
            print(f"  - Parse: {avg_parse:.3f}s ({avg_parse/avg_total*100:.1f}%)")
            
            print(f"\nMin/Max Times:")
            print(f"  Total: {min(total_times):.3f}s - {max(total_times):.3f}s")
            print(f"  Load:  {min(load_times):.3f}s - {max(load_times):.3f}s")
            print(f"  Wait:  {min(wait_times):.3f}s - {max(wait_times):.3f}s")
            print(f"  Parse: {min(parse_times):.3f}s - {max(parse_times):.3f}s")
            
            # Recommendations
            print(f"\n💡 OPTIMIZATION RECOMMENDATIONS:")
            if avg_load > 1.5:
                print(f"  🔥 Load phase is the bottleneck ({avg_load:.3f}s)")
                print(f"     → Consider page_load_strategy optimization")
                print(f"     → More aggressive resource blocking")
            elif avg_wait > 0.2:
                print(f"  ⏰ Wait phase can be optimized ({avg_wait:.3f}s)")
                print(f"     → Reduce max_wait timeout")
                print(f"     → Optimize polling interval")
            elif avg_parse > 0.1:
                print(f"  📄 Parse phase can be improved ({avg_parse:.3f}s)")
                print(f"     → Optimize JavaScript selectors")
            else:
                print(f"  ✅ Performance looks good!")
                print(f"     → Target: <2.0s total, current: {avg_total:.3f}s")
    
    finally:
        driver.quit()
        print("\n✅ Driver closed")

if __name__ == "__main__":
    profile_html_parsing(num_cycles=3)