"""
Тесты для проверки intent detection и availability handling.
Запуск: python -m pytest backend/test_intent_detection.py -v
или: python backend/test_intent_detection.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.ai import detect_intent, parse_availability_constraints, is_task_request


def test_detect_intent_availability():
    """Тесты для определения availability intent"""
    test_cases = [
        ("найди свободное окно", "availability"),
        ("когда я свободен", "availability"),
        ("есть ли свободное время сегодня", "availability"),
        ("назови все свободные окна", "availability"),
        ("когда я могу", "availability"),
        ("могу ли я", "availability"),
        ("есть ли у меня время", "availability"),
        ("когда я свободен завтра утром", "availability"),
        ("найди ближайшее свободное окно на 30 минут сегодня", "availability"),
        ("Есть ли у меня свободное время сегодня после 18:00?", "availability"),
    ]
    
    for text, expected in test_cases:
        result = detect_intent(text)
        assert result == expected, f"Ожидалось {expected}, получено {result} для '{text}'"
    print("[OK] Все тесты availability intent прошли")


def test_detect_intent_create_event():
    """Тесты для определения create_event intent"""
    test_cases = [
        ("создай встречу с Петей завтра в 15:00", "create_event"),
        ("добавь задачу на завтра", "create_event"),
        ("запланируй совещание на понедельник", "create_event"),
        ("напомни купить молоко", "create_event"),
        ("встреча с командой 20.12 в 14:00", "create_event"),
        ("созвон завтра в 10:00", "create_event"),
    ]
    
    for text, expected in test_cases:
        result = detect_intent(text)
        assert result == expected, f"Ожидалось {expected}, получено {result} для '{text}'"
    print("[OK] Все тесты create_event intent прошли")


def test_detect_intent_chat():
    """Тесты для определения chat intent"""
    test_cases = [
        ("привет", "chat"),
        ("как дела", "chat"),
        ("спасибо", "chat"),
        ("что ты умеешь", "chat"),
    ]
    
    for text, expected in test_cases:
        result = detect_intent(text)
        assert result == expected, f"Ожидалось {expected}, получено {result} для '{text}'"
    print("[OK] Все тесты chat intent прошли")


def test_parse_availability_constraints():
    """Тесты для парсинга ограничений availability"""
    from datetime import date, time as dtime
    
    # Тест длительности
    constraints = parse_availability_constraints("найди свободное окно на 30 минут")
    assert constraints['duration_minutes'] == 30, f"Ожидалось 30, получено {constraints['duration_minutes']}"
    
    constraints = parse_availability_constraints("на час")
    assert constraints['duration_minutes'] == 60, f"Ожидалось 60, получено {constraints['duration_minutes']}"
    
    # Тест даты
    constraints = parse_availability_constraints("когда я свободен завтра")
    assert constraints['date'] is not None, "Дата должна быть определена"
    
    # Тест временного окна
    constraints = parse_availability_constraints("когда я свободен завтра утром")
    assert constraints['time_window'] == (dtime(9, 0), dtime(12, 0)), "Утро должно быть 09:00-12:00"
    
    # Тест "после"
    constraints = parse_availability_constraints("есть ли свободное время после 18:00")
    assert constraints['after_time'] == dtime(18, 0), "after_time должен быть 18:00"
    
    print("[OK] Все тесты parse_availability_constraints прошли")


def test_is_task_request_fixed():
    """Тест что is_task_request больше не использует предлоги в/во/к"""
    # Эти запросы НЕ должны быть create_event (они availability)
    test_cases = [
        "когда я свободен",
        "найди свободное окно",
        "есть ли свободное время",
    ]
    
    for text in test_cases:
        # is_task_request теперь использует detect_intent, который правильно определяет availability
        result = is_task_request(text)
        assert result == False, f"'{text}' не должен быть create_event (это availability)"
    
    print("[OK] is_task_request исправлен (не использует предлоги)")


if __name__ == "__main__":
    print("Запуск тестов intent detection...\n")
    try:
        test_detect_intent_availability()
        test_detect_intent_create_event()
        test_detect_intent_chat()
        test_parse_availability_constraints()
        test_is_task_request_fixed()
        print("\n[OK] Все тесты прошли успешно!")
    except AssertionError as e:
        print(f"\n[FAIL] Тест провален: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Ошибка при выполнении тестов: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

