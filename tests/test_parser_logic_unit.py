#!/usr/bin/env python3
"""
Unit test - проверка логики парсера без браузера
Тестирует что Python код правильно обрабатывает данные от JavaScript
Включает тесты для расширенной фильтрации и fallback механизма
"""

import re
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def parse_links_python_enhanced(links, min_expected_count=20):
    """
    Имитирует новую Python часть парсера из get_all_notice_ids() с расширенной фильтрацией
    """
    all_notices = []
    filter_stats = {
        'pinned_badge': 0,
        'pinned_class': 0,
        'pinned_marker': 0,
        'short_navigation': 0,
        'no_id': 0,
        'total_filtered': 0
    }
    
    for link in links:
        href = link.get('href', '')
        text = link.get('text', '')
        parent_classes = link.get('parentClasses', '').lower()
        badge_text = link.get('badgeText', '')
        data_attrs = link.get('dataAttrs', {})
        
        # Извлекаем ID через regex в Python
        match = re.search(r'id=(\d+)', href)
        if not match:
            filter_stats['no_id'] += 1
            continue
        
        notice_id = int(match.group(1))
        
        # Сохраняем все данные для возможного fallback
        notice_data = {
            'id': notice_id,
            'text': text,
            'href': href,
            'parent_classes': parent_classes,
            'badge_text': badge_text,
            'data_attrs': data_attrs,
            'is_pinned': False,
            'filter_reason': None
        }
        
        # === ПРОВЕРКА НА ЗАКРЕПЛЕННОСТЬ (только с явными маркерами!) ===
        
        # Метод 1: Badge содержит маркер закрепления
        if badge_text and ('공지' in badge_text or 'pin' in badge_text.lower() or 'fixed' in badge_text.lower()):
            notice_data['is_pinned'] = True
            notice_data['filter_reason'] = 'pinned_badge'
            filter_stats['pinned_badge'] += 1
        
        # Метод 2: Класс родительского элемента содержит маркер
        elif 'pinned' in parent_classes or 'fixed' in parent_classes or 'sticky' in parent_classes:
            notice_data['is_pinned'] = True
            notice_data['filter_reason'] = 'pinned_class'
            filter_stats['pinned_class'] += 1
        
        # Метод 3: Data-атрибуты указывают на закрепление
        elif data_attrs.get('pinned') == 'true' or data_attrs.get('fixed') == 'true' or data_attrs.get('type') == 'pinned':
            notice_data['is_pinned'] = True
            notice_data['filter_reason'] = 'pinned_class'
            filter_stats['pinned_class'] += 1
        
        # Метод 4: Текст НАЧИНАЕТСЯ с маркера (не просто содержит где-то)
        elif text.startswith('공지') or text.startswith('[공지]') or text.startswith('[중요]'):
            notice_data['is_pinned'] = True
            notice_data['filter_reason'] = 'pinned_marker'
            filter_stats['pinned_marker'] += 1
        
        # Метод 5: Текст слишком короткий (явная навигация)
        elif len(text) < 3 or (len(text) < 5 and text.isdigit()):
            notice_data['is_pinned'] = True
            notice_data['filter_reason'] = 'short_navigation'
            filter_stats['short_navigation'] += 1
        
        all_notices.append(notice_data)
    
    # Подсчитываем отфильтрованные
    filtered_notices = [n for n in all_notices if not n['is_pinned']]
    filter_stats['total_filtered'] = len(all_notices) - len(filtered_notices)
    
    # === ЗАЩИТНЫЙ FALLBACK ===
    fallback_invoked = False
    
    if len(filtered_notices) < min_expected_count and len(all_notices) >= min_expected_count:
        fallback_invoked = True
        
        # Стратегия fallback: возвращаем те, что отфильтрованы по менее строгим причинам
        relaxed_notices = [
            n for n in all_notices 
            if not n['is_pinned'] or n['filter_reason'] in ['short_navigation', 'pinned_marker']
        ]
        
        # Если все еще мало - берем только verified pinned (badge + class)
        if len(relaxed_notices) < min_expected_count:
            relaxed_notices = [
                n for n in all_notices
                if not n['is_pinned'] or n['filter_reason'] not in ['pinned_badge', 'pinned_class']
            ]
        
        # Последний fallback - берем все
        if len(relaxed_notices) < min_expected_count:
            relaxed_notices = all_notices
        
        filtered_notices = relaxed_notices
    
    notice_ids = [n['id'] for n in filtered_notices]
    samples = [{'id': n['id'], 'title': n['text'][:50]} for n in filtered_notices[:3]]
    
    return notice_ids, samples, filter_stats, fallback_invoked


def test_parse_logic():
    """
    Тестирует логику парсинга с разными типами данных
    """
    logging.info("=" * 80)
    logging.info("🧪 UNIT TEST: Расширенная логика парсинга с fallback")
    logging.info("=" * 80)
    logging.info("")
    
    # === ТЕСТ 1: Нормальные новости ===
    logging.info("ТЕСТ 1: Нормальные новости")
    links = [
        {'href': '/service_center/notice?id=5710', 'text': 'Новость про Bitcoin и ETH', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5709', 'text': 'Обновление сервиса Upbit', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5708', 'text': 'Технические работы сегодня', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
    ]
    
    ids, samples, stats, fallback = parse_links_python_enhanced(links, min_expected_count=20)
    
    assert len(ids) == 3, f"Expected 3 ids, got {len(ids)}"
    assert ids == [5710, 5709, 5708], f"Expected [5710, 5709, 5708], got {ids}"
    assert stats['total_filtered'] == 0, "No filtering should occur"
    assert not fallback, "No fallback should be invoked"
    logging.info(f"✅ Найдено {len(ids)} новостей: {ids}")
    logging.info(f"   Filter stats: {stats}, Fallback: {fallback}")
    logging.info("")
    
    # === ТЕСТ 2: Pinned через badge ===
    logging.info("ТЕСТ 2: Закрепленные новости через badge")
    links = [
        {'href': '/service_center/notice?id=5710', 'text': 'Новость про Bitcoin', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5709', 'text': 'Важное объявление', 'parentClasses': '', 'badgeText': '공지', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5708', 'text': 'Обычная новость', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
    ]
    
    ids, samples, stats, fallback = parse_links_python_enhanced(links, min_expected_count=20)
    
    assert len(ids) == 2, f"Expected 2 ids (filtered pinned), got {len(ids)}"
    assert ids == [5710, 5708], f"Expected [5710, 5708], got {ids}"
    assert 5709 not in ids, "Pinned via badge should be filtered out"
    assert stats['pinned_badge'] == 1, "Should have 1 pinned badge"
    logging.info(f"✅ Найдено {len(ids)} новостей (отфильтровано 1 badge): {ids}")
    logging.info(f"   Filter stats: {stats}")
    logging.info("")
    
    # === ТЕСТ 3: Pinned через класс ===
    logging.info("ТЕСТ 3: Закрепленные новости через parent class")
    links = [
        {'href': '/service_center/notice?id=5710', 'text': 'Длинный текст новости', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5709', 'text': 'Закрепленная новость', 'parentClasses': 'row pinned', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5708', 'text': 'Еще одна новость', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
    ]
    
    ids, samples, stats, fallback = parse_links_python_enhanced(links, min_expected_count=20)
    
    assert len(ids) == 2, f"Expected 2 ids (filtered pinned class), got {len(ids)}"
    assert ids == [5710, 5708], f"Expected [5710, 5708], got {ids}"
    assert 5709 not in ids, "Pinned via class should be filtered out"
    assert stats['pinned_class'] == 1, "Should have 1 pinned class"
    logging.info(f"✅ Найдено {len(ids)} новостей (отфильтровано 1 class): {ids}")
    logging.info(f"   Filter stats: {stats}")
    logging.info("")
    
    # === ТЕСТ 4: Pinned через маркер в начале текста ===
    logging.info("ТЕСТ 4: Закрепленные новости через маркер в начале")
    links = [
        {'href': '/service_center/notice?id=5710', 'text': 'Bitcoin новость длинная', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5709', 'text': '공지 Закреплено', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5708', 'text': 'Текст с 공지 в середине', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
    ]
    
    ids, samples, stats, fallback = parse_links_python_enhanced(links, min_expected_count=20)
    
    assert len(ids) == 2, f"Expected 2 ids, got {len(ids)}"
    assert ids == [5710, 5708], f"Expected [5710, 5708], got {ids}"
    assert 5709 not in ids, "Should filter when marker at start"
    assert 5708 in ids, "Should NOT filter when marker in middle"
    assert stats['pinned_marker'] == 1, "Should have 1 pinned marker"
    logging.info(f"✅ Найдено {len(ids)} новостей (маркер только в начале): {ids}")
    logging.info(f"   Filter stats: {stats}")
    logging.info("")
    
    # === ТЕСТ 5: Короткие навигационные ссылки ===
    logging.info("ТЕСТ 5: Короткие навигационные ссылки")
    links = [
        {'href': '/service_center/notice?id=5710', 'text': 'Обычная новость', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5709', 'text': '다음', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5708', 'text': '1', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5707', 'text': '이전', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
    ]
    
    ids, samples, stats, fallback = parse_links_python_enhanced(links, min_expected_count=20)
    
    assert len(ids) == 1, f"Expected 1 id, got {len(ids)}"
    assert ids == [5710], f"Expected [5710], got {ids}"
    assert stats['short_navigation'] == 3, "Should have 3 short navigation items"
    logging.info(f"✅ Найдено {len(ids)} новостей (отфильтровано 3 навигационных): {ids}")
    logging.info(f"   Filter stats: {stats}")
    logging.info("")
    
    # === ТЕСТ 6: Смешанные ссылки с разными маркерами ===
    logging.info("ТЕСТ 6: Смешанные ссылки с разными типами pinning")
    links = [
        {'href': '/service_center/notice?id=5710', 'text': 'Bitcoin новость', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5709', 'text': 'Важное', 'parentClasses': '', 'badgeText': '공지', 'dataAttrs': {}},  # Badge
        {'href': '/service_center/notice?id=5708', 'text': 'ETH обновление', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5707', 'text': 'Закрепленная', 'parentClasses': 'sticky-row', 'badgeText': '', 'dataAttrs': {}},  # Class
        {'href': '/service_center/notice?id=5706', 'text': 'XRP новость', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},
        {'href': '/service_center/notice?id=5705', 'text': '[공지] Важное', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},  # Marker
        {'href': '/service_center/notice?id=5704', 'text': '다음', 'parentClasses': '', 'badgeText': '', 'dataAttrs': {}},  # Short
    ]
    
    ids, samples, stats, fallback = parse_links_python_enhanced(links, min_expected_count=20)
    
    assert len(ids) == 3, f"Expected 3 ids, got {len(ids)}"
    assert ids == [5710, 5708, 5706], f"Expected [5710, 5708, 5706], got {ids}"
    assert stats['pinned_badge'] == 1, "Should have 1 pinned badge"
    assert stats['pinned_class'] == 1, "Should have 1 pinned class"
    assert stats['pinned_marker'] == 1, "Should have 1 pinned marker"
    assert stats['short_navigation'] == 1, "Should have 1 short navigation"
    assert stats['total_filtered'] == 4, "Should filter 4 total"
    logging.info(f"✅ Найдено {len(ids)} новостей (отфильтровано 4): {ids}")
    logging.info(f"   Filter stats: {stats}")
    logging.info("")
    
    # === ТЕСТ 7: Fallback механизм - чрезмерная фильтрация ===
    logging.info("ТЕСТ 7: FALLBACK - чрезмерная фильтрация (25 links → 15 после фильтрации)")
    links = []
    # Создаем 15 нормальных новостей
    for i in range(5800, 5815):
        links.append({
            'href': f'/service_center/notice?id={i}',
            'text': f'Обычная новость {i}',
            'parentClasses': '',
            'badgeText': '',
            'dataAttrs': {}
        })
    # Добавляем 10 с pinned marker (будут отфильтрованы)
    for i in range(5815, 5825):
        links.append({
            'href': f'/service_center/notice?id={i}',
            'text': f'공지 Закрепленная {i}',
            'parentClasses': '',
            'badgeText': '',
            'dataAttrs': {}
        })
    
    ids, samples, stats, fallback = parse_links_python_enhanced(links, min_expected_count=20)
    
    assert len(links) == 25, f"Should have 25 total links"
    assert fallback == True, "Fallback SHOULD be invoked"
    assert len(ids) >= 20, f"After fallback should have ≥20 notices, got {len(ids)}"
    assert stats['pinned_marker'] == 10, "Should have 10 pinned markers"
    logging.info(f"✅ Fallback сработал! Было 25 → после фильтрации 15 → после fallback {len(ids)}")
    logging.info(f"   Filter stats: {stats}, Fallback: {fallback}")
    logging.info("")
    
    # === ТЕСТ 8: Fallback механизм - НЕ срабатывает когда достаточно ===
    logging.info("ТЕСТ 8: Fallback НЕ срабатывает при достаточном количестве")
    links = []
    # Создаем 25 нормальных новостей
    for i in range(5800, 5825):
        links.append({
            'href': f'/service_center/notice?id={i}',
            'text': f'Обычная новость {i}',
            'parentClasses': '',
            'badgeText': '',
            'dataAttrs': {}
        })
    # Добавляем 5 pinned через badge (будут отфильтрованы)
    for i in range(5825, 5830):
        links.append({
            'href': f'/service_center/notice?id={i}',
            'text': f'Важная новость {i}',
            'parentClasses': '',
            'badgeText': '공지',
            'dataAttrs': {}
        })
    
    ids, samples, stats, fallback = parse_links_python_enhanced(links, min_expected_count=20)
    
    assert len(links) == 30, f"Should have 30 total links"
    assert fallback == False, "Fallback should NOT be invoked"
    assert len(ids) == 25, f"Should have 25 notices (5 filtered), got {len(ids)}"
    assert stats['pinned_badge'] == 5, "Should have 5 pinned badges"
    logging.info(f"✅ Fallback не сработал (достаточно результатов): {len(ids)} новостей")
    logging.info(f"   Filter stats: {stats}, Fallback: {fallback}")
    logging.info("")
    
    # === ТЕСТ 9: Многоуровневый fallback ===
    logging.info("ТЕСТ 9: Многоуровневый fallback (badge → marker → все)")
    links = []
    # 10 нормальных
    for i in range(5800, 5810):
        links.append({
            'href': f'/service_center/notice?id={i}',
            'text': f'Обычная новость {i}',
            'parentClasses': '',
            'badgeText': '',
            'dataAttrs': {}
        })
    # 5 с badge (строгая фильтрация)
    for i in range(5810, 5815):
        links.append({
            'href': f'/service_center/notice?id={i}',
            'text': f'Badge новость {i}',
            'parentClasses': '',
            'badgeText': 'pinned',
            'dataAttrs': {}
        })
    # 5 с class (строгая фильтрация)
    for i in range(5815, 5820):
        links.append({
            'href': f'/service_center/notice?id={i}',
            'text': f'Class новость {i}',
            'parentClasses': 'fixed-row',
            'badgeText': '',
            'dataAttrs': {}
        })
    # 5 с marker (мягкая фильтрация - вернутся при fallback)
    for i in range(5820, 5825):
        links.append({
            'href': f'/service_center/notice?id={i}',
            'text': f'공지 Marker новость {i}',
            'parentClasses': '',
            'badgeText': '',
            'dataAttrs': {}
        })
    
    ids, samples, stats, fallback = parse_links_python_enhanced(links, min_expected_count=20)
    
    assert len(links) == 25, f"Should have 25 total links"
    assert fallback == True, "Fallback should be invoked"
    # После первого уровня fallback: 10 нормальных + 5 marker = 15 (все еще < 20)
    # После второго уровня: 10 нормальных + 5 marker + 5 badge + 5 class = 25
    assert len(ids) >= 20, f"Should have ≥20 after multi-level fallback, got {len(ids)}"
    logging.info(f"✅ Многоуровневый fallback: 10 обычных → релаксация → {len(ids)} итого")
    logging.info(f"   Filter stats: {stats}, Fallback: {fallback}")
    logging.info("")
    
    # === ВСЕ ТЕСТЫ ПРОЙДЕНЫ ===
    logging.info("=" * 80)
    logging.info("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    logging.info("=" * 80)
    logging.info("✅ Расширенная фильтрация работает корректно")
    logging.info("✅ Badge/Class/Marker/Navigation фильтрация работает")
    logging.info("✅ Fallback механизм срабатывает корректно")
    logging.info("✅ Многоуровневый fallback работает")
    logging.info("✅ Статистика фильтрации отслеживается")
    return True


if __name__ == "__main__":
    import sys
    success = test_parse_logic()
    sys.exit(0 if success else 1)
