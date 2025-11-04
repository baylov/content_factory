#!/usr/bin/env python3
"""
Скрипт для тестирования производительности загрузки страницы Upbit
Измеряет время загрузки с новыми оптимизациями
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

UPBIT_NOTICE_URL = "https://upbit.com/service_center/notice"

def test_optimized_load():
    """Тест с новыми оптимизациями"""
    print("=" * 60)
    print("ТЕСТ ОПТИМИЗИРОВАННОЙ ЗАГРУЗКИ")
    print("=" * 60)
    
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    
    # Агрессивная блокировка ресурсов
    chrome_options.add_argument('--blink-settings=imagesEnabled=false')
    chrome_options.add_argument('--disable-remote-fonts')
    chrome_options.add_argument('--disable-background-networking')
    chrome_options.add_argument('--disable-default-apps')
    chrome_options.add_argument('--disable-sync')
    chrome_options.add_argument('--disable-translate')
    chrome_options.add_argument('--mute-audio')
    
    prefs = {
        'profile.managed_default_content_settings.images': 2,
        'profile.managed_default_content_settings.stylesheets': 2,
        'profile.default_content_setting_values': {
            'images': 2,
            'plugins': 2,
            'popups': 2,
            'media_stream': 2,
            'stylesheets': 2,
        }
    }
    chrome_options.add_experimental_option('prefs', prefs)
    chrome_options.page_load_strategy = 'eager'  # КРИТИЧЕСКИ ВАЖНО
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(3)
    driver.implicitly_wait(0)
    
    try:
        # Тест 1: Первая загрузка
        print("\n📡 Тест #1: Первая загрузка страницы")
        start = time.time()
        driver.get(UPBIT_NOTICE_URL)
        load_time = time.time() - start
        
        wait_start = time.time()
        wait = WebDriverWait(driver, 5)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/service_center/notice?id="]')))
        wait_time = time.time() - wait_start
        
        total_time = time.time() - start
        
        print(f"  ⏱️ driver.get(): {load_time:.3f}s")
        print(f"  ⏱️ Wait for list: {wait_time:.3f}s")
        print(f"  ⏱️ ИТОГО: {total_time:.3f}s")
        
        if total_time < 0.5:
            print("  ✅ ОТЛИЧНО: < 0.5 сек!")
        elif total_time < 1.0:
            print("  ✅ ХОРОШО: < 1 сек")
        elif total_time < 2.0:
            print("  ⚠️ ПРИЕМЛЕМО: 1-2 сек")
        else:
            print(f"  ❌ МЕДЛЕННО: {total_time:.3f} сек")
        
        # Проверяем что список загрузился
        js_code = """
        const links = document.querySelectorAll('a[href*="/service_center/notice?id="]');
        return links.length;
        """
        links_count = driver.execute_script(js_code)
        print(f"  📊 Найдено ссылок: {links_count}")
        
        # Тест 2-4: Refresh
        refresh_times = []
        for i in range(3):
            print(f"\n🔄 Тест #{i+2}: Refresh #{i+1}")
            time.sleep(0.5)  # Небольшая пауза между тестами
            
            start = time.time()
            driver.refresh()
            refresh_time = time.time() - start
            
            wait_start = time.time()
            wait = WebDriverWait(driver, 3)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/service_center/notice?id="]')))
            wait_time = time.time() - wait_start
            
            total_time = time.time() - start
            refresh_times.append(total_time)
            
            print(f"  ⏱️ driver.refresh(): {refresh_time:.3f}s")
            print(f"  ⏱️ Wait for list: {wait_time:.3f}s")
            print(f"  ⏱️ ИТОГО: {total_time:.3f}s")
            
            if total_time < 0.5:
                print("  ✅ ОТЛИЧНО: < 0.5 сек!")
            elif total_time < 1.0:
                print("  ✅ ХОРОШО: < 1 сек")
            elif total_time < 2.0:
                print("  ⚠️ ПРИЕМЛЕМО: 1-2 сек")
            else:
                print(f"  ❌ МЕДЛЕННО: {total_time:.3f} сек")
        
        # Статистика
        print("\n" + "=" * 60)
        print("📊 СТАТИСТИКА")
        print("=" * 60)
        avg_refresh = sum(refresh_times) / len(refresh_times)
        min_refresh = min(refresh_times)
        max_refresh = max(refresh_times)
        
        print(f"Средний refresh: {avg_refresh:.3f}s")
        print(f"Минимальный: {min_refresh:.3f}s")
        print(f"Максимальный: {max_refresh:.3f}s")
        
        print("\n✅ ИТОГО:")
        if avg_refresh < 0.5:
            print(f"  🎯 ЦЕЛЬ ДОСТИГНУТА! Средняя скорость {avg_refresh:.3f}s < 0.5s")
        elif avg_refresh < 0.8:
            print(f"  ✅ ХОРОШИЙ РЕЗУЛЬТАТ! Средняя скорость {avg_refresh:.3f}s < 0.8s")
        elif avg_refresh < 2.0:
            print(f"  ⚠️ УЛУЧШЕНИЕ ЕСТЬ, но средняя {avg_refresh:.3f}s еще можно оптимизировать")
        else:
            print(f"  ❌ Средняя скорость {avg_refresh:.3f}s все еще медленная")
        
    finally:
        driver.quit()
        print("\n" + "=" * 60)

if __name__ == "__main__":
    test_optimized_load()
