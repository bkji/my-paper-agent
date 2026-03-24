"""한국어 날짜 표현 파서 — 자연어 쿼리에서 날짜 필터를 추출한다.

지원 패턴:
- D1 절대(특정): "2024년 11월", "2024년 3월"
- D2 절대(범위): "2023년 3분기", "2024년 상반기", "2022~2024년", "2023년"
- D3 상대: "최근 6개월", "작년", "올해", "지난달", "올해 초", "작년 여름"
- D4 비교: "2022년 대비 2024년", "2020년과 2023년 비교"
"""
from __future__ import annotations

import calendar
import re
import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)


def _normalize_short_year(query: str) -> str:
    """2자리 연도를 4자리로 변환한다.

    규칙: 50 미만 → 2000년대 (25년 → 2025년), 50 이상 → 1900년대 (99년 → 1999년)
    "25년" → "2025년", "99년" → "1999년", "03년" → "2003년"
    단, "2024년" 같은 4자리 연도는 건드리지 않는다.
    """
    def _replace(m):
        y = int(m.group(1))
        full_year = (2000 + y) if y < 50 else (1900 + y)
        return f"{full_year}년"

    # 4자리 연도 뒤의 "년"은 건드리지 않고, 2자리 연도+"년"만 매칭
    # (?<!\d) — 앞에 숫자가 없어야 함 (4자리 연도의 뒷부분을 잡지 않기 위해)
    return re.sub(r'(?<!\d)(\d{2})년', _replace, query)


def extract_date_filters(query: str, reference_date: datetime | None = None) -> dict | None:
    """쿼리에서 날짜 표현을 추출하여 coverdate_from/to 필터를 반환한다.

    Returns:
        dict with 'coverdate_from', 'coverdate_to' (YYYYMMDD int) or None
    """
    ref = reference_date or datetime.now()

    # 전처리: 2자리 연도 → 4자리 변환 ("25년" → "2025년")
    query = _normalize_short_year(query)

    # D4: 비교 패턴 (두 연도가 "대비", "비교", "vs", "변화"로 연결)
    m = re.search(r'(\d{4})년?\s*(?:대비|과|와|vs\.?)\s*(\d{4})년', query)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        if y1 > y2:
            y1, y2 = y2, y1
        return {"coverdate_from": y1 * 10000 + 101, "coverdate_to": y2 * 10000 + 1231}

    m = re.search(r'(\d{4})\s*[~\-–]\s*(\d{4})년?\s*(?:변화|추이|비교)', query)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        return {"coverdate_from": y1 * 10000 + 101, "coverdate_to": y2 * 10000 + 1231}

    # D1-range: 같은 연도 월 범위 "2024년 10월 ~ 12월", "2024년 3월~8월"
    m = re.search(r'(\d{4})년\s*(\d{1,2})월\s*[~\-–]\s*(\d{1,2})월', query)
    if m:
        year, m1, m2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= m1 <= 12 and 1 <= m2 <= 12:
            if m1 > m2:
                m1, m2 = m2, m1
            last_day = calendar.monthrange(year, m2)[1]
            return {
                "coverdate_from": year * 10000 + m1 * 100 + 1,
                "coverdate_to": year * 10000 + m2 * 100 + last_day,
            }

    # D1-cross: 다른 연도 월 범위 "2024년 10월 ~ 2025년 3월"
    m = re.search(r'(\d{4})년\s*(\d{1,2})월\s*[~\-–]\s*(\d{4})년\s*(\d{1,2})월', query)
    if m:
        y1, m1, y2, m2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        if 1 <= m1 <= 12 and 1 <= m2 <= 12:
            last_day = calendar.monthrange(y2, m2)[1]
            return {
                "coverdate_from": y1 * 10000 + m1 * 100 + 1,
                "coverdate_to": y2 * 10000 + m2 * 100 + last_day,
            }

    # D1: 절대 연월 "2024년 11월"
    m = re.search(r'(\d{4})년\s*(\d{1,2})월', query)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            last_day = calendar.monthrange(year, month)[1]
            return {
                "coverdate_from": year * 10000 + month * 100 + 1,
                "coverdate_to": year * 10000 + month * 100 + last_day,
            }

    # D2: 분기 "2023년 3분기"
    m = re.search(r'(\d{4})년\s*(\d)\s*분기', query)
    if m:
        year, q = int(m.group(1)), int(m.group(2))
        if 1 <= q <= 4:
            ms = (q - 1) * 3 + 1
            me = q * 3
            last_day = calendar.monthrange(year, me)[1]
            return {"coverdate_from": year * 10000 + ms * 100 + 1, "coverdate_to": year * 10000 + me * 100 + last_day}

    # D2: 상반기/하반기 "2024년 상반기"
    m = re.search(r'(\d{4})년\s*(상반기|하반기)', query)
    if m:
        year = int(m.group(1))
        if m.group(2) == "상반기":
            return {"coverdate_from": year * 10000 + 101, "coverdate_to": year * 10000 + 630}
        else:
            return {"coverdate_from": year * 10000 + 701, "coverdate_to": year * 10000 + 1231}

    # D2: 연도 범위 "2022~2024년", "2003년~2005년"
    m = re.search(r'(\d{4})년?\s*[~\-–]\s*(\d{4})년?', query)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        if y1 > y2:
            y1, y2 = y2, y1
        return {"coverdate_from": y1 * 10000 + 101, "coverdate_to": y2 * 10000 + 1231}

    # D3: 최근 N개월 "최근 6개월"
    m = re.search(r'최근\s*(\d+)\s*개월', query)
    if m:
        n = int(m.group(1))
        dt_from = ref - relativedelta(months=n)
        return {"coverdate_from": int(dt_from.strftime("%Y%m%d")), "coverdate_to": int(ref.strftime("%Y%m%d"))}

    # D3: 최근 N년 "최근 3년"
    m = re.search(r'최근\s*(\d+)\s*년', query)
    if m:
        n = int(m.group(1))
        dt_from = ref - relativedelta(years=n)
        return {"coverdate_from": int(dt_from.strftime("%Y%m%d")), "coverdate_to": int(ref.strftime("%Y%m%d"))}

    # D3: 올해 초
    if re.search(r'올해\s*초', query):
        return {"coverdate_from": ref.year * 10000 + 101, "coverdate_to": ref.year * 10000 + 331}

    # D3: 지난 + 계절 "지난 여름", "지난 겨울"
    m = re.search(r'지난\s*(봄|여름|가을|겨울)', query)
    if m:
        season = m.group(1)
        # "지난 여름": 현재 월 기준으로 가장 최근 지난 해당 계절
        season_months = {"봄": 3, "여름": 6, "가을": 9, "겨울": 12}
        season_start = season_months[season]
        # 현재 달이 해당 계절 이후면 올해, 아니면 작년
        if ref.month > season_start + 2:
            y = ref.year
        else:
            y = ref.year - 1
        season_map = {
            "봄": (301, 531), "여름": (601, 831),
            "가을": (901, 1130), "겨울": (1201, 10228),
        }
        s, e = season_map[season]
        if season == "겨울":
            return {"coverdate_from": y * 10000 + 1201, "coverdate_to": (y + 1) * 10000 + 228}
        return {"coverdate_from": y * 10000 + s, "coverdate_to": y * 10000 + e}

    # D3: 작년 + 계절
    m = re.search(r'작년\s*(봄|여름|가을|겨울)', query)
    if m:
        y = ref.year - 1
        season = m.group(1)
        season_map = {
            "봄": (301, 531), "여름": (601, 831),
            "가을": (901, 1130), "겨울": (1201, 10228),  # 겨울은 다음해 2월까지
        }
        s, e = season_map[season]
        if season == "겨울":
            return {"coverdate_from": y * 10000 + 1201, "coverdate_to": (y + 1) * 10000 + 228}
        return {"coverdate_from": y * 10000 + s, "coverdate_to": y * 10000 + e}

    # D3: 작년/지난해
    if re.search(r'작년|지난해|전년', query):
        y = ref.year - 1
        return {"coverdate_from": y * 10000 + 101, "coverdate_to": y * 10000 + 1231}

    # D3: 올해/금년
    if re.search(r'올해|금년', query):
        return {"coverdate_from": ref.year * 10000 + 101, "coverdate_to": int(ref.strftime("%Y%m%d"))}

    # D3: 지난달/전월
    if re.search(r'지난달|전월', query):
        dt = ref - relativedelta(months=1)
        last_day = calendar.monthrange(dt.year, dt.month)[1]
        return {
            "coverdate_from": dt.year * 10000 + dt.month * 100 + 1,
            "coverdate_to": dt.year * 10000 + dt.month * 100 + last_day,
        }

    # D2: 단독 연도 "2024년", "1999년" (다른 패턴에 매칭 안 된 경우)
    m = re.search(r'(\d{4})년', query)
    if m:
        year = int(m.group(1))
        if 1900 <= year <= 2099:
            return {"coverdate_from": year * 10000 + 101, "coverdate_to": year * 10000 + 1231}

    return None
