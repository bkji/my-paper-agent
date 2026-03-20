"""Agent Tools — 에이전트가 사용할 수 있는 도구 모음."""
from __future__ import annotations

from datetime import datetime


def get_current_datetime() -> dict:
    """서버의 현재 날짜/시간을 반환한다.

    Returns:
        dict with:
            - datetime: "2026-03-20 14:30:00"
            - date: "2026-03-20"
            - year: 2026
            - month: 3
            - day: 20
            - weekday: "목요일"
            - iso: "2026-03-20T14:30:00"
    """
    now = datetime.now()
    weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    return {
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "weekday": weekdays[now.weekday()],
        "iso": now.isoformat(),
    }


def get_current_date_context() -> str:
    """LLM 시스템 프롬프트에 삽입할 현재 날짜 컨텍스트 문자열을 반환한다."""
    info = get_current_datetime()
    return (
        f"현재 날짜: {info['date']} ({info['weekday']})\n"
        f"현재 시각: {info['datetime']}\n"
        f"기준 연도: {info['year']}년"
    )
