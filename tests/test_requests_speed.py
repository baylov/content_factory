#!/usr/bin/env python3
"""
Сравнение скорости: Selenium vs Requests
"""
import time
import requests
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

def test_requests_method():
    """Тест парсинга через requests"""
    
    logging.info("="*60)
    logging.info("🧪 ТЕСТ: requests + BeautifulSoup")
    logging.info("="*60)
    
    url = 'https://upbit.com/service_center/notice'
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    times = []
    
    for i in range(5):
        start = time.time()
        
        try:
            response = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Пробуем найти новости
            links = soup.select('a[href*="/service_center/notice?id="]')
            
            elapsed = time.time() - start
            times.append(elapsed)
            
            logging.info(f"Попытка {i+1}: {elapsed:.3f}s - Найдено ссылок: {len(links)}")
            
            if len(links) == 0:
                logging.warning("   ⚠️ Новости не найдены - возможно блокировка")
        
        except Exception as e:
            logging.error(f"Попытка {i+1}: Ошибка - {e}")
        
        time.sleep(1)
    
    if times:
        avg = sum(times) / len(times)
        logging.info(f"\n📊 Средняя скорость: {avg:.3f}s")
        
        if avg < 0.5:
            logging.info("✅ ОТЛИЧНО! Requests работает быстрее")
        elif avg < 1.0:
            logging.info("✅ ХОРОШО! Requests даёт ускорение")
        else:
            logging.info("⚠️ Не быстрее текущего метода")

if __name__ == '__main__':
    test_requests_method()
