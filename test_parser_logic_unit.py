#!/usr/bin/env python3
"""
Unit test - проверка логики парсера без браузера
Тестирует что Python код правильно обрабатывает данные от JavaScript
"""

import re
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def parse_links_python(links):
    """
    Имитирует Python часть парсера из get_all_notice_ids()
    """
    notice_ids = []
    samples = []
    
    for link in links:
        href = link.get('href', '')
        text = link.get('text', '')
        
        # Извлекаем ID через regex в Python
        match = re.search(r'id=(\d+)', href)
        if not match:
            continue
        
        notice_id = int(match.group(1))
        
        # === ПРОВЕРКА НА ЗАКРЕПЛЕННОСТЬ (в Python!) ===
        is_pinned = False
        
        # Метод 1: Текст содержит маркер
        if '공지' in text:
            is_pinned = True
        
        # Метод 2: Текст слишком короткий (навигация)
        if len(text) < 5:
            is_pinned = True
        
        # Добавляем только незакрепленные
        if not is_pinned:
            notice_ids.append(notice_id)
            
            # Сохраняем примеры
            if len(samples) < 3:
                samples.append({
                    'id': notice_id,
                    'title': text[:50]
                })
    
    return notice_ids, samples


def test_parse_logic():
    """
    Тестирует логику парсинга с разными типами данных
    """
    logging.info("=" * 80)
    logging.info("🧪 UNIT TEST: Логика парсинга (без браузера)")
    logging.info("=" * 80)
    logging.info("")
    
    # === ТЕСТ 1: Нормальные новости ===
    logging.info("ТЕСТ 1: Нормальные новости")
    links = [
        {'href': '/service_center/notice?id=5710', 'text': 'Новость про Bitcoin и ETH'},
        {'href': '/service_center/notice?id=5709', 'text': 'Обновление сервиса Upbit'},
        {'href': '/service_center/notice?id=5708', 'text': 'Технические работы сегодня'},
    ]
    
    ids, samples = parse_links_python(links)
    
    assert len(ids) == 3, f"Expected 3 ids, got {len(ids)}"
    assert ids == [5710, 5709, 5708], f"Expected [5710, 5709, 5708], got {ids}"
    logging.info(f"✅ Найдено {len(ids)} новостей: {ids}")
    logging.info("")
    
    # === ТЕСТ 2: Закрепленные новости (маркер 공지) ===
    logging.info("ТЕСТ 2: Закрепленные новости с маркером 공지")
    links = [
        {'href': '/service_center/notice?id=5710', 'text': 'Новость про Bitcoin'},
        {'href': '/service_center/notice?id=5709', 'text': '공지 Важное объявление'},  # Закреплено
        {'href': '/service_center/notice?id=5708', 'text': 'Обычная новость'},
    ]
    
    ids, samples = parse_links_python(links)
    
    assert len(ids) == 2, f"Expected 2 ids (filtered pinned), got {len(ids)}"
    assert ids == [5710, 5708], f"Expected [5710, 5708], got {ids}"
    assert 5709 not in ids, "Pinned notice (공지) should be filtered out"
    logging.info(f"✅ Найдено {len(ids)} новостей (отфильтровано 1 закрепленное): {ids}")
    logging.info("")
    
    # === ТЕСТ 3: Короткие ссылки (навигация) ===
    logging.info("ТЕСТ 3: Короткие ссылки (навигация)")
    links = [
        {'href': '/service_center/notice?id=5710', 'text': 'Длинный текст новости'},
        {'href': '/service_center/notice?id=5709', 'text': '다음'},  # Короткий - навигация
        {'href': '/service_center/notice?id=5708', 'text': 'Еще одна новость'},
    ]
    
    ids, samples = parse_links_python(links)
    
    assert len(ids) == 2, f"Expected 2 ids (filtered short), got {len(ids)}"
    assert ids == [5710, 5708], f"Expected [5710, 5708], got {ids}"
    assert 5709 not in ids, "Short text should be filtered out"
    logging.info(f"✅ Найдено {len(ids)} новостей (отфильтровано 1 короткий): {ids}")
    logging.info("")
    
    # === ТЕСТ 4: Смешанные ссылки ===
    logging.info("ТЕСТ 4: Смешанные ссылки (обычные + закрепленные + короткие)")
    links = [
        {'href': '/service_center/notice?id=5710', 'text': 'Bitcoin новость длинная'},
        {'href': '/service_center/notice?id=5709', 'text': '공지 Закреплено'},  # Закреплено
        {'href': '/service_center/notice?id=5708', 'text': 'ETH обновление'},
        {'href': '/service_center/notice?id=5707', 'text': '다음'},  # Короткий
        {'href': '/service_center/notice?id=5706', 'text': 'Обычная новость про XRP'},
        {'href': '/service_center/notice?id=5705', 'text': '공지 Еще закрепленное'},  # Закреплено
    ]
    
    ids, samples = parse_links_python(links)
    
    assert len(ids) == 3, f"Expected 3 ids, got {len(ids)}"
    assert ids == [5710, 5708, 5706], f"Expected [5710, 5708, 5706], got {ids}"
    assert 5709 not in ids, "공지 should be filtered"
    assert 5707 not in ids, "Short text should be filtered"
    assert 5705 not in ids, "공지 should be filtered"
    logging.info(f"✅ Найдено {len(ids)} новостей (отфильтровано 3): {ids}")
    logging.info("")
    
    # === ТЕСТ 5: Нет валидных ID ===
    logging.info("ТЕСТ 5: Ссылки без валидных ID")
    links = [
        {'href': '/service_center/notice', 'text': 'Ссылка без ID'},
        {'href': '/service_center', 'text': 'Главная'},
        {'href': '#', 'text': 'Якорь'},
    ]
    
    ids, samples = parse_links_python(links)
    
    assert len(ids) == 0, f"Expected 0 ids, got {len(ids)}"
    logging.info(f"✅ Найдено {len(ids)} новостей (все без ID): {ids}")
    logging.info("")
    
    # === ТЕСТ 6: Samples ===
    logging.info("ТЕСТ 6: Проверка samples (первые 3)")
    links = [
        {'href': '/service_center/notice?id=5710', 'text': 'Первая новость'},
        {'href': '/service_center/notice?id=5709', 'text': 'Вторая новость'},
        {'href': '/service_center/notice?id=5708', 'text': 'Третья новость'},
        {'href': '/service_center/notice?id=5707', 'text': 'Четвертая новость'},
    ]
    
    ids, samples = parse_links_python(links)
    
    assert len(samples) == 3, f"Expected 3 samples, got {len(samples)}"
    assert samples[0]['id'] == 5710, "First sample ID should be 5710"
    assert samples[1]['id'] == 5709, "Second sample ID should be 5709"
    assert samples[2]['id'] == 5708, "Third sample ID should be 5708"
    logging.info(f"✅ Samples: {samples}")
    logging.info("")
    
    # === ВСЕ ТЕСТЫ ПРОЙДЕНЫ ===
    logging.info("=" * 80)
    logging.info("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    logging.info("=" * 80)
    logging.info("✅ Логика парсинга в Python работает корректно")
    logging.info("✅ Фильтрация закрепленных новостей работает")
    logging.info("✅ Фильтрация коротких текстов работает")
    logging.info("✅ Извлечение ID через regex работает")
    logging.info("✅ Samples формируются правильно")
    return True


if __name__ == "__main__":
    import sys
    success = test_parse_logic()
    sys.exit(0 if success else 1)
