"""
Co-Scientist Agent용 Q&A 데이터셋 1,080건 생성 및 MariaDB 적재 스크립트

분류 체계:
- 사용자 역할 (R1~R8): 8개 유형
- Agent 유형 (13개): paper_qa ~ knowledge_connector
- 난이도 (C1~C3): Simple / Medium / Complex
- 날짜 유형 (D0~D4): 없음 / 절대 / 절대범위 / 상대 / 비교
"""

import os
import sys
import json
import random
import calendar
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import mariadb
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("MARIADB_HOST", "localhost"),
    "port": int(os.getenv("MARIADB_PORT", "3306")),
    "user": os.getenv("MARIADB_USER"),
    "password": os.getenv("MARIADB_PASSWORD"),
}
DATABASE = os.getenv("MARIADB_DATABASE", "paper")

# 기준일
REF_DATE = datetime(2026, 3, 20)
REF_DATE_INT = 20260320

# ============================================================
# 도메인 어휘 사전
# ============================================================

ROLES = {
    "R1": "R&D 연구자",
    "R2": "소프트웨어 개발자",
    "R3": "설비 엔지니어",
    "R4": "재료 엔지니어",
    "R5": "공정 엔지니어",
    "R6": "특허/IP 담당자",
    "R7": "경영/전략 기획",
    "R8": "품질/신뢰성 엔지니어",
}

# 역할별 주요 agent 매핑
ROLE_AGENTS = {
    "R1": ["paper_qa", "literature_survey", "paper_deep_dive", "idea_generator", "cross_domain", "trend_analyzer", "report_drafter"],
    "R2": ["paper_qa", "trend_analyzer", "cross_domain", "literature_survey", "report_drafter"],
    "R3": ["paper_qa", "material_advisor", "experiment_planner", "trend_analyzer", "patent_landscaper"],
    "R4": ["material_advisor", "paper_qa", "literature_survey", "idea_generator", "experiment_planner", "cross_domain"],
    "R5": ["experiment_planner", "material_advisor", "paper_qa", "literature_survey", "trend_analyzer", "patent_landscaper"],
    "R6": ["patent_landscaper", "competitive_intel", "paper_qa", "trend_analyzer", "knowledge_connector"],
    "R7": ["competitive_intel", "trend_analyzer", "report_drafter", "paper_qa", "knowledge_connector", "patent_landscaper"],
    "R8": ["experiment_planner", "material_advisor", "paper_qa", "literature_survey", "peer_review"],
}

# 역할별 목표 건수
ROLE_TARGETS = {
    "R1": 200, "R2": 100, "R3": 120, "R4": 160,
    "R5": 140, "R6": 100, "R7": 120, "R8": 140,
}

# 도메인 카테고리
DOMAINS = {
    "OLED": [
        "발광효율", "수명 개선", "Blue 발광재", "인광 재료", "TADF 소재",
        "호스트 재료", "전자수송층(ETL)", "정공수송층(HTL)", "캐비티 구조",
        "탑에미션", "플렉서블 OLED", "투명 OLED", "마이크로 캐비티",
        "광추출 효율", "색 안정성", "번인(burn-in)", "패널 구동",
    ],
    "MicroLED": [
        "전사 기술", "Mass Transfer", "레이저 리프트오프(LLO)", "칩 사이즈 축소",
        "풀컬러 구현", "색변환층", "본딩 기술", "수율 향상",
        "검사 및 리페어", "구동 회로", "에피택시 성장", "GaN LED",
        "InGaN 양자우물", "마이크로 디스플레이", "AR/VR 응용",
    ],
    "QD": [
        "양자점 합성", "QD 색변환", "QD-OLED", "QD-LED",
        "Cd-free 양자점", "InP 양자점", "페로브스카이트 양자점",
        "양자점 안정성", "양자점 패터닝", "양자점 잉크젯",
        "광변환 효율", "색순도", "QD 봉지",
    ],
    "LCD": [
        "백라이트 효율", "미니 LED 백라이트", "로컬디밍", "편광판",
        "액정 배향", "고속 응답", "광시야각", "HDR 구현",
        "IPS/VA 모드", "산화물 TFT", "대면적 디스플레이",
    ],
    "TFT": [
        "LTPO TFT", "IGZO", "산화물 반도체", "a-Si TFT",
        "LTPS", "TFT 이동도", "게이트 절연막", "채널 스케일링",
        "구동 회로 설계", "보상 회로", "플렉서블 TFT",
    ],
    "봉지": [
        "수분투과율(WVTR)", "TFE(Thin Film Encapsulation)", "ALD 박막",
        "유기/무기 다층 봉지", "댐 앤 필", "봉지 필름",
        "에지 실링", "플렉서블 봉지", "봉지 신뢰성",
    ],
    "공정": [
        "유기증착", "잉크젯 프린팅", "스퍼터링", "PECVD",
        "건식 식각", "습식 식각", "포토리소그래피", "나노임프린트",
        "레이저 어닐링", "세정 공정", "진공 공정",
    ],
    "장비": [
        "증착기", "식각장비", "세정장비", "AOI 검사장비",
        "레이저 가공장비", "노광장비", "코팅장비", "라미네이션 장비",
        "진공 챔버", "클러스터 장비", "인라인 시스템",
    ],
}

SUBJECTS_FLAT = []
for cat, items in DOMAINS.items():
    for item in items:
        SUBJECTS_FLAT.append((cat, item))

TECHNOLOGIES = [
    "잉크젯 프린팅", "레이저 리프트오프", "ALD 박막 증착", "유기 증착",
    "나노임프린트", "롤투롤 공정", "스퍼터링", "PECVD",
    "포토리소그래피", "E-beam 증착", "열증착", "화학기상증착",
    "습식 코팅", "스핀코팅", "슬롯다이 코팅",
]

MATERIALS = [
    "유기 발광재", "양자점", "봉지 필름", "편광판 소재", "LTPO",
    "IGZO 타깃", "ITO 전극", "은 나노와이어", "그래핀",
    "Al2O3 배리어", "SiNx 절연막", "폴리이미드 기판",
    "에폭시 봉지재", "UV 경화 수지", "열경화 수지",
]

AUTHORS = [
    "Samsung", "LG Display", "BOE", "TCL CSOT", "Sharp",
    "서울대", "KAIST", "포항공대", "성균관대", "한양대",
    "Applied Materials", "Canon Tokki", "ULVAC", "Veeco",
    "Kateeva", "Coherent", "Universal Display", "Merck",
    "Sumitomo Chemical", "Idemitsu Kosan", "Dupont",
]

EQUIPMENT = [
    "증착기", "식각장비", "세정장비", "AOI 검사장비", "레이저 가공장비",
    "노광장비", "코팅장비", "라미네이션 장비", "본딩 장비", "전사 장비",
]

PERFORMANCE_METRICS = [
    "발광효율", "수명", "색순도", "응답속도", "WVTR",
    "이동도", "균일성", "수율", "전력소모", "해상도",
    "밝기", "대비비", "색재현율", "시야각", "두께",
]

# ============================================================
# 날짜 표현 생성 및 파싱
# ============================================================

def resolve_date_range(date_type, ref=REF_DATE):
    """날짜 유형에 따라 (expression, from_int, to_int) 반환"""
    if date_type == "D0":
        return None, None, None

    if date_type == "D1":
        # 절대 날짜: 특정 연월
        year = random.randint(2020, 2026)
        month = random.randint(1, 12)
        if year == 2026 and month > 3:
            month = random.randint(1, 3)
        last_day = calendar.monthrange(year, month)[1]
        expressions = [
            f"{year}년 {month}월",
            f"{year}년 {month:02d}월",
        ]
        return random.choice(expressions), year * 10000 + month * 100 + 1, year * 10000 + month * 100 + last_day

    if date_type == "D2":
        # 절대 범위: 분기, 상하반기, 연도 범위
        variant = random.choice(["quarter", "half", "year_range", "year"])
        if variant == "quarter":
            year = random.randint(2020, 2025)
            q = random.randint(1, 4)
            month_start = (q - 1) * 3 + 1
            month_end = q * 3
            last_day = calendar.monthrange(year, month_end)[1]
            return f"{year}년 {q}분기", year * 10000 + month_start * 100 + 1, year * 10000 + month_end * 100 + last_day
        elif variant == "half":
            year = random.randint(2020, 2025)
            half = random.choice(["상반기", "하반기"])
            if half == "상반기":
                return f"{year}년 상반기", year * 10000 + 101, year * 10000 + 630
            else:
                return f"{year}년 하반기", year * 10000 + 701, year * 10000 + 1231
        elif variant == "year_range":
            y1 = random.randint(2020, 2023)
            y2 = y1 + random.randint(1, 3)
            return f"{y1}~{y2}년", y1 * 10000 + 101, y2 * 10000 + 1231
        else:
            year = random.randint(2020, 2025)
            return f"{year}년", year * 10000 + 101, year * 10000 + 1231

    if date_type == "D3":
        # 상대 날짜
        variant = random.choice([
            "recent_months", "recent_years", "last_year", "this_year",
            "last_month", "year_beginning", "last_summer", "last_winter",
        ])
        if variant == "recent_months":
            n = random.choice([3, 6, 9, 12])
            dt_from = ref - relativedelta(months=n)
            return f"최근 {n}개월", int(dt_from.strftime("%Y%m%d")), REF_DATE_INT
        elif variant == "recent_years":
            n = random.choice([1, 2, 3, 5])
            dt_from = ref - relativedelta(years=n)
            return f"최근 {n}년", int(dt_from.strftime("%Y%m%d")), REF_DATE_INT
        elif variant == "last_year":
            y = ref.year - 1
            expr = random.choice(["작년", "지난해", f"{y}년"])
            return expr, y * 10000 + 101, y * 10000 + 1231
        elif variant == "this_year":
            expr = random.choice(["올해", "금년"])
            return expr, ref.year * 10000 + 101, REF_DATE_INT
        elif variant == "last_month":
            dt = ref - relativedelta(months=1)
            last_day = calendar.monthrange(dt.year, dt.month)[1]
            return "지난달", int(dt.strftime("%Y%m01")), dt.year * 10000 + dt.month * 100 + last_day
        elif variant == "year_beginning":
            return "올해 초", ref.year * 10000 + 101, ref.year * 10000 + 331
        elif variant == "last_summer":
            y = ref.year - 1
            return "작년 여름", y * 10000 + 601, y * 10000 + 831
        elif variant == "last_winter":
            y = ref.year - 1
            return "작년 겨울", y * 10000 + 1201, ref.year * 10000 + 228

    if date_type == "D4":
        # 비교
        y1 = random.randint(2020, 2022)
        y2 = y1 + random.randint(2, 4)
        if y2 > 2025:
            y2 = 2025
        exprs = [
            f"{y1}년 대비 {y2}년",
            f"{y1}년과 {y2}년 비교",
            f"{y1}~{y2}년 변화",
        ]
        return random.choice(exprs), y1 * 10000 + 101, y2 * 10000 + 1231

    return None, None, None


# ============================================================
# 템플릿 라이브러리
# ============================================================

def get_random_subject():
    cat, item = random.choice(SUBJECTS_FLAT)
    return cat, item

def get_random_tech():
    return random.choice(TECHNOLOGIES)

def get_random_material():
    return random.choice(MATERIALS)

def get_random_author():
    return random.choice(AUTHORS)

def get_random_equip():
    return random.choice(EQUIPMENT)

def get_random_metric():
    return random.choice(PERFORMANCE_METRICS)


# agent별 템플릿: (query_template, expected_answer_template, answer_format, difficulty)
# {s} = subject, {d} = date_expression, {t} = technology, {m} = material, {a} = author, {e} = equipment, {p} = metric

TEMPLATES = {
    "paper_qa": {
        "C1": {
            "D0": [
                ("{s} 관련 논문 찾아줘", "'{s}' 키워드로 검색한 논문 목록 (제목, 저자, DOI, 날짜) 제공", "text", 1),
                ("{s}에 대해 알려줘", "'{s}'에 대한 개요와 관련 논문에서 추출한 핵심 내용 요약", "text", 1),
                ("{s} 최신 연구 뭐 있어?", "'{s}' 관련 최신 논문 리스트와 각 논문의 핵심 기여 1줄 요약", "text", 1),
                ("{s} 논문 검색해줘", "'{s}' 검색 결과 논문 목록을 relevance score 순으로 제공", "text", 1),
            ],
            "D1": [
                ("{d}에 발표된 {s} 논문 알려줘", "'{s}' 키워드 + 날짜 필터({d}) 적용한 논문 목록", "text", 2),
                ("{d} {s} 관련 논문 리스트 보여줘", "해당 기간 내 '{s}' 논문 목록 (날짜순 정렬)", "text", 2),
            ],
            "D2": [
                ("{d} 사이에 나온 {s} 논문이 있나?", "기간({d}) 내 '{s}' 논문 유무 및 목록", "text", 2),
                ("{d} 동안 발표된 {s} 연구 정리해줘", "기간 내 논문을 시간순으로 정리한 요약", "text", 2),
            ],
            "D3": [
                ("{d} {s} 관련 논문 있어?", "상대 기간({d}) 내 '{s}' 논문 검색 결과", "text", 2),
                ("{d}간 {s} 연구 동향 간단히 알려줘", "해당 기간 논문 기반 간략 동향 요약", "text", 2),
            ],
            "D4": [
                ("{d} {s} 연구 성과 차이가 있어?", "두 시점 논문을 비교하여 주요 변화점 제시", "text", 3),
            ],
        },
        "C2": {
            "D0": [
                ("{s}에서 {p} 향상 방법에 대한 논문 정리해줘", "'{s}' + '{p}' 복합 검색 후 방법론별 분류 요약", "text", 2),
                ("{a}이 발표한 {s} 관련 논문 요약해줘", "저자 필터 + 키워드 검색 후 논문별 핵심 기여 요약", "text", 2),
                ("{s}와 {t} 관련 연구 비교해줘", "두 주제 교차 검색 후 공통점/차이점 분석", "text", 3),
            ],
            "D1": [
                ("{d}에 {a}이 발표한 {s} 논문 내용 알려줘", "날짜 + 저자 + 키워드 복합 필터 적용 결과", "text", 3),
            ],
            "D3": [
                ("{d} {a}이 {s}에 대해 뭘 발표했어?", "상대 기간 + 저자 필터 적용 논문 요약", "text", 3),
                ("{d}간 {s} 분야에서 {p}가 개선된 논문 알려줘", "기간 + 성능지표 복합 검색 결과", "text", 3),
            ],
        },
        "C3": {
            "D0": [
                ("{s}에서 {p} 개선을 위해 어떤 접근법들이 사용되었고 각각의 장단점은?", "다수 논문에서 접근법 추출 → 비교 테이블 + 장단점 분석", "structured", 4),
            ],
            "D3": [
                ("{d}간 {s} 분야에서 {p} 성능 개선 추이와 주요 breakthrough를 분석해줘", "시계열 분석 + 주요 전환점 논문 식별 + 성능 변화 정리", "structured", 5),
            ],
            "D4": [
                ("{d} {s} 분야의 연구 방법론이 어떻게 진화했는지 비교 분석해줘", "두 시점의 주요 방법론 비교 + 패러다임 변화 분석", "structured", 5),
            ],
        },
    },
    "literature_survey": {
        "C2": {
            "D0": [
                ("{s}에 대한 문헌 리뷰 작성해줘", "4~6개 섹션으로 구성된 체계적 문헌 리뷰 (배경, 방법론, 결과, 한계, 미래방향)", "report", 3),
                ("{s} 기술의 현재 수준과 과제를 정리해줘", "현재 기술 수준 + 미해결 과제 + 향후 방향 구조화된 리뷰", "report", 3),
            ],
            "D1": [
                ("{d}에 발표된 {s} 관련 문헌을 리뷰해줘", "특정 월 논문 기반 리뷰", "report", 3),
            ],
            "D2": [
                ("{d} {s} 연구를 체계적으로 리뷰해줘", "기간 내 문헌 리뷰", "report", 3),
            ],
            "D3": [
                ("{d}간 {s} 연구를 종합적으로 리뷰해줘", "기간 내 논문 기반 체계적 리뷰", "report", 3),
            ],
        },
        "C3": {
            "D0": [
                ("{s}와 {t} 기술의 접점에 대한 종합 리뷰를 작성해줘", "두 분야 교차 리뷰 + 시너지/갈등 분석 + 통합 전망", "report", 5),
            ],
            "D3": [
                ("{d}간 {s} 분야의 연구 트렌드를 중심으로 포괄적 리뷰를 작성해줘", "시간축 중심 리뷰 + 연구 그룹별 기여도 + 기술 로드맵", "report", 5),
            ],
            "D4": [
                ("{d} {s} 연구의 방향이 어떻게 변했는지 비교 리뷰해줘", "두 시점 비교 중심 리뷰 + 패러다임 전환 분석", "report", 5),
            ],
        },
    },
    "paper_deep_dive": {
        "C2": {
            "D0": [
                ("{s}에 대한 {a}의 최신 논문을 심층 분석해줘", "8개 차원 분석: 기여도, 방법론, 결과, 강점, 한계, 선행연구 관계, 미래방향, 실용적 시사점", "structured", 3),
                ("DOI: {doi} 논문 자세히 분석해줘", "DOI로 특정 논문 조회 후 8개 차원 심층 분석", "structured", 3),
            ],
            "D1": [
                ("{d}에 나온 {a}의 {s} 논문 심층 분석해줘", "날짜 필터 + 저자 필터로 논문 조회 후 심층 분석", "structured", 3),
            ],
            "D3": [
                ("{d}간 {a}이 발표한 {s} 논문 중 가장 인용 많은 것 분석해줘", "기간 + 저자 필터 적용 후 상위 논문 심층 분석", "structured", 4),
            ],
        },
        "C3": {
            "D0": [
                ("{s} 관련 {a}의 연구를 방법론 관점에서 비판적으로 분석해줘", "방법론 타당성 + 재현성 + 통계적 유의성 비판 분석", "structured", 5),
            ],
        },
    },
    "idea_generator": {
        "C2": {
            "D0": [
                ("{s}에서 {p}를 개선할 수 있는 새로운 연구 아이디어 제안해줘", "3~5개 아이디어 (신규성/실현가능성/근거 포함)", "structured", 3),
                ("{s}에 {t}를 적용한 새로운 접근법 아이디어 있어?", "기술 융합 관점의 아이디어 제안 + 실현 방안", "structured", 3),
            ],
            "D1": [
                ("{d}에 발표된 {s} 논문 기반으로 후속 연구 아이디어 제안해줘", "특정 기간 논문에서 영감 받은 아이디어", "structured", 3),
            ],
            "D2": [
                ("{d} {s} 연구 결과를 바탕으로 새로운 아이디어 제안해줘", "기간 내 연구 기반 아이디어", "structured", 3),
            ],
            "D3": [
                ("{d}간 {s} 연구 트렌드를 보고 다음 연구 방향을 제안해줘", "최신 트렌드 기반 미래 연구 아이디어", "structured", 4),
            ],
        },
        "C3": {
            "D0": [
                ("{s}와 {m} 기술을 융합하여 {p}를 획기적으로 개선할 아이디어를 제안해줘", "다분야 융합 아이디어 + 실험 로드맵 + 리스크 분석", "structured", 5),
            ],
            "D4": [
                ("{d} {s} 연구 발전 과정을 분석하고 아직 시도되지 않은 접근법을 제안해줘", "시간적 gap 분석 기반 신규 아이디어", "structured", 5),
            ],
        },
    },
    "cross_domain": {
        "C2": {
            "D0": [
                ("반도체 분야의 {t} 기술을 {s}에 적용할 수 있을까?", "타 분야 기술 이전 가능성 평가 + 적용 방안", "structured", 3),
                ("바이오 분야에서 사용하는 접근법 중 {s} 문제 해결에 도움될 게 있어?", "바이오→디스플레이 크로스도메인 솔루션 제안", "structured", 3),
                ("에너지 분야의 {m}을 {s}에 응용할 수 있을까?", "에너지→디스플레이 재료 전이 가능성 평가", "structured", 3),
            ],
            "D1": [
                ("{d}에 발표된 타 분야 논문 중 {s}에 적용 가능한 기술 찾아줘", "날짜 필터 + 크로스도메인 탐색", "structured", 3),
            ],
            "D3": [
                ("{d}간 반도체 분야에서 나온 기술 중 {s}에 적용 가능한 것 분석해줘", "기간 내 크로스도메인 기회 탐색", "structured", 4),
            ],
        },
        "C3": {
            "D0": [
                ("{s}의 {p} 문제를 해결하기 위해 반도체/에너지/바이오 등 타 분야 접근법을 종합적으로 분석하고 적용 전략을 제안해줘", "다중 분야 솔루션 탐색 + feasibility×impact 순위 + 구현 로드맵", "structured", 5),
            ],
            "D4": [
                ("{d} 타 분야에서 {s}로의 기술 이전 사례가 어떻게 변화했는지 분석해줘", "크로스도메인 기술 이전 역사 분석", "structured", 5),
            ],
        },
    },
    "trend_analyzer": {
        "C2": {
            "D1": [
                ("{d}에 {s} 분야에서 어떤 연구가 활발했어?", "특정 월 연구 활동 트렌드 요약", "report", 3),
            ],
            "D2": [
                ("{d} {s} 분야 연구 동향 요약해줘", "기간 내 트렌드 분석 리포트", "report", 3),
            ],
            "D3": [
                ("{d}간 {s} 기술의 연구 동향 분석해줘", "8개 섹션 트렌드 리포트 (개요, 부상기술, 쇠퇴기술, 주요그룹, 지역트렌드, 키워드변화, 예측, 추천)", "report", 3),
                ("{d}간 {s} 분야 주요 연구 그룹과 트렌드 알려줘", "주요 연구 그룹별 활동 + 기술 방향 변화", "report", 3),
            ],
        },
        "C3": {
            "D4": [
                ("{d} {s} 분야에서 연구 focus가 어떻게 바뀌었는지 분석하고 향후 3년 예측해줘", "두 시점 비교 + 전환점 분석 + 미래 예측", "report", 5),
                ("{d} {s} 기술의 성능 지표 변화와 기술 성숙도를 분석해줘", "기간별 성능 추이 + S-curve 분석 + 기술 로드맵", "report", 5),
            ],
            "D3": [
                ("{d}간 디스플레이 산업 전반의 기술 트렌드와 {s}의 위치를 분석해줘", "거시 트렌드 내 특정 기술 포지셔닝 분석", "report", 5),
            ],
        },
    },
    "experiment_planner": {
        "C2": {
            "D0": [
                ("{s}에서 {p} 향상을 위한 실험 설계를 제안해줘", "가설 → 변수 → 실험 설계(DOE) → 분석 방법 제안", "structured", 3),
                ("{m}의 {p}를 평가하기 위한 실험 프로토콜 작성해줘", "재료 평가 실험 계획: 시료 준비 → 측정 → 분석", "structured", 3),
            ],
            "D1": [
                ("{d}에 발표된 {s} 실험 방법을 참고해서 우리 실험에 맞게 설계해줘", "특정 기간 논문의 방법론 참조 실험 설계", "structured", 3),
            ],
            "D2": [
                ("{d} {s} 관련 실험 방법론 중 가장 효과적인 것을 참고해서 실험 계획 세워줘", "기간 내 최선 방법론 기반 설계", "structured", 4),
            ],
            "D3": [
                ("{d}간 발표된 {s} 실험 방법론을 참고하여 실험 계획 세워줘", "최신 방법론 기반 실험 설계", "structured", 4),
            ],
        },
        "C3": {
            "D0": [
                ("{s}에서 {p}에 영향을 주는 다중 인자를 고려한 최적화 실험을 설계해줘", "다인자 DOE + 통계 분석 + contingency plan", "structured", 5),
            ],
            "D4": [
                ("{d} {s} 실험 방법론이 어떻게 발전했는지 분석하고 최신 최적 설계를 제안해줘", "방법론 진화 분석 + 최적 실험 설계", "structured", 5),
            ],
        },
    },
    "patent_landscaper": {
        "C2": {
            "D0": [
                ("{s} 관련 특허 동향 분석해줘", "특허 개요, 주요 출원인, 기술 클러스터, 공백 영역, 출원 추이", "report", 3),
                ("{a}의 {s} 관련 특허 포트폴리오 분석해줘", "특정 기업 특허 포트폴리오 분석", "report", 3),
            ],
            "D1": [
                ("{d}에 출원된 {s} 관련 특허 동향 알려줘", "특정 월 특허 출원 분석", "report", 3),
            ],
            "D2": [
                ("{d} {s} 분야 특허 출원 추이 분석해줘", "기간 내 특허 트렌드", "report", 3),
            ],
            "D3": [
                ("{d}간 {s} 분야 특허 출원 동향 분석해줘", "기간 내 특허 동향 + 신규 출원 트렌드", "report", 3),
            ],
        },
        "C3": {
            "D4": [
                ("{d} {s} 분야 특허 landscape가 어떻게 변했는지 분석하고 IP 전략 제안해줘", "특허 맵 변화 + FTO 분석 + 전략 제안", "report", 5),
            ],
            "D3": [
                ("{d}간 {a}의 {s} 특허 전략 변화를 분석하고 공백 영역 식별해줘", "기간 내 특허 전략 진화 + 기회 분석", "report", 5),
            ],
        },
    },
    "competitive_intel": {
        "C2": {
            "D0": [
                ("{a}의 {s} 기술 동향 분석해줘", "경쟁사 기술 활동 + 논문/특허 기반 전략 분석", "report", 3),
                ("{s} 분야에서 주요 경쟁사들의 기술 수준 비교해줘", "경쟁사별 기술 비교 매트릭스", "table", 3),
            ],
            "D1": [
                ("{d}에 {a}이 {s} 관련 어떤 활동을 했어?", "특정 월 경쟁사 활동 브리핑", "report", 3),
            ],
            "D2": [
                ("{d} {a}의 {s} 연구 활동 분석해줘", "기간 내 경쟁사 활동 요약", "report", 3),
            ],
            "D3": [
                ("{d}간 {a}의 {s} 관련 연구 활동을 모니터링해줘", "기간 내 경쟁사 활동 브리핑", "report", 3),
            ],
        },
        "C3": {
            "D4": [
                ("{d} {s} 분야에서 주요 플레이어들의 전략 변화를 분석하고 우리의 대응 방향을 제안해줘", "경쟁 환경 변화 + 위협/기회 + 액션 플랜", "report", 5),
            ],
            "D3": [
                ("{d}간 {s} 분야 경쟁 구도 변화와 각 사 전략을 분석해줘", "기간 내 경쟁 구도 + 전략 분석", "report", 5),
            ],
        },
    },
    "material_advisor": {
        "C2": {
            "D0": [
                ("{s}용 {m} 후보 재료를 비교 분석해줘", "후보 재료 비교 테이블 + 추천 순위", "table", 3),
                ("{p} 향상을 위한 {m} 대체재를 추천해줘", "기존 대비 대체재 성능 비교 + 추천", "table", 3),
                ("{s}에 사용되는 {m}의 장단점 분석해줘", "재료 물성 + 공정 적합성 + 비용 분석", "structured", 3),
            ],
            "D1": [
                ("{d}에 보고된 {s}용 신규 {m} 정보 알려줘", "특정 월 신규 재료 논문 검색", "table", 3),
            ],
            "D2": [
                ("{d} {s}에 새로 적용된 {m} 후보들 비교해줘", "기간 내 신규 재료 비교 분석", "table", 3),
            ],
            "D3": [
                ("{d}간 발표된 논문 기준으로 {s}용 최적 {m}을 추천해줘", "최신 논문 기반 재료 추천", "table", 4),
            ],
        },
        "C3": {
            "D0": [
                ("{s}에서 {p}와 비용을 동시에 만족하는 최적 재료 조합을 제안해줘", "다목적 최적화 관점 재료 조합 + 트레이드오프 분석", "structured", 5),
            ],
            "D4": [
                ("{d} {s}용 {m} 성능이 어떻게 발전했는지 분석하고 차세대 재료를 추천해줘", "재료 성능 진화 + 차세대 추천", "structured", 5),
            ],
        },
    },
    "report_drafter": {
        "C2": {
            "D0": [
                ("{s}에 대한 기술 보고서 초안 작성해줘", "보고서 구조 (배경, 기술 현황, 분석, 결론, 참고문헌)", "report", 3),
                ("{s} 관련 발표 자료 초안 만들어줘", "프레젠테이션 구조 (슬라이드별 내용 + 그림 위치)", "report", 3),
            ],
            "D1": [
                ("{d} {s} 연구 결과를 요약한 보고서 작성해줘", "특정 월 성과 보고서", "report", 3),
            ],
            "D2": [
                ("{d} {s} 기술 동향 보고서를 작성해줘", "기간 내 기술 동향 보고서", "report", 3),
            ],
            "D3": [
                ("{d}간 {s} 연구 성과를 정리한 보고서 초안 작성해줘", "기간별 성과 정리 보고서", "report", 4),
            ],
            "D4": [
                ("{d} {s} 기술의 발전 과정을 정리한 보고서 초안 작성해줘", "시간 비교 기반 기술 발전 보고서", "report", 4),
            ],
        },
    },
    "peer_review": {
        "C2": {
            "D0": [
                ("{s}에 대한 내 논문 초록을 리뷰해줘: {abstract}", "3명 가상 리뷰어 (기술/도메인/실무) 의견 + 메타리뷰", "structured", 3),
            ],
        },
        "C3": {
            "D0": [
                ("{s} 주제의 내 논문 전체를 비판적으로 리뷰하고 개선점을 제안해줘", "심층 리뷰: 방법론 검증 + 결과 해석 + 관련 문헌 대비 포지셔닝", "structured", 5),
            ],
        },
    },
    "knowledge_connector": {
        "C1": {
            "D0": [
                ("{s} 분야 전문가 누가 있어?", "논문 저자 기반 전문가 리스트 (발표 건수 순)", "text", 1),
                ("{s} 관련 활발하게 연구하는 그룹 알려줘", "활동량 기반 연구 그룹 순위", "text", 1),
            ],
            "D1": [
                ("{d}에 {s} 논문 발표한 연구자 알려줘", "특정 월 활동 저자 리스트", "text", 2),
            ],
            "D2": [
                ("{d} {s} 분야 활발한 연구자 누구야?", "기간 내 활발한 저자", "text", 2),
            ],
            "D3": [
                ("{d}간 {s} 분야에서 가장 활발한 연구자는?", "기간 내 저자 활동량 분석", "text", 2),
            ],
        },
        "C2": {
            "D0": [
                ("{s}와 {t} 양쪽에 전문성이 있는 연구자를 찾아줘", "교차 분야 전문가 매칭", "text", 3),
            ],
            "D4": [
                ("{d} {s} 분야 주요 연구자 구성이 어떻게 바뀌었는지 분석해줘", "연구자 네트워크 변화 분석", "text", 4),
            ],
        },
    },
}

# ============================================================
# Q&A 생성 엔진
# ============================================================

def fill_template(template_str, subject, domain_cat, date_expr, tech, material, author, equip, metric):
    """템플릿의 슬롯을 채운다."""
    result = template_str
    result = result.replace("{s}", subject)
    result = result.replace("{d}", date_expr or "")
    result = result.replace("{t}", tech)
    result = result.replace("{m}", material)
    result = result.replace("{a}", author)
    result = result.replace("{e}", equip)
    result = result.replace("{p}", metric)
    # peer_review용 abstract placeholder
    if "{abstract}" in result:
        result = result.replace("{abstract}", f"본 연구에서는 {subject}에 대한 새로운 접근법을 제시하고 {metric} 개선 효과를 검증하였다.")
    if "{doi}" in result:
        result = result.replace("{doi}", f"10.xxxx/{subject[:10].replace(' ', '')}.2024")
    return result.strip()


def generate_all_qa():
    """1,080건 Q&A 데이터를 생성한다."""
    all_qa = []
    qa_texts_seen = set()

    for role_code, target_count in ROLE_TARGETS.items():
        role_name = ROLES[role_code]
        agents_for_role = ROLE_AGENTS[role_code]
        generated = 0

        # 각 agent에 할당할 건수 분배
        agent_counts = {}
        base_per_agent = target_count // len(agents_for_role)
        remainder = target_count % len(agents_for_role)
        for i, agent in enumerate(agents_for_role):
            agent_counts[agent] = base_per_agent + (1 if i < remainder else 0)

        for agent_type, count in agent_counts.items():
            if agent_type not in TEMPLATES:
                # 이 agent에 템플릿이 없으면 paper_qa 템플릿 사용
                agent_templates = TEMPLATES.get("paper_qa", {})
            else:
                agent_templates = TEMPLATES[agent_type]

            # complexity × date_type 분배
            complexity_dist = {"C1": 0.35, "C2": 0.40, "C3": 0.25}
            date_dist = {"D0": 0.40, "D1": 0.15, "D2": 0.15, "D3": 0.20, "D4": 0.10}

            items_generated = 0
            max_attempts = count * 10

            attempts = 0
            while items_generated < count and attempts < max_attempts:
                attempts += 1

                # 난이도 선택
                complexity = random.choices(list(complexity_dist.keys()), weights=list(complexity_dist.values()))[0]
                date_type = random.choices(list(date_dist.keys()), weights=list(date_dist.values()))[0]

                # 해당 조합의 템플릿 찾기
                templates = agent_templates.get(complexity, {}).get(date_type, [])
                if not templates:
                    # fallback: 같은 complexity의 D0 템플릿
                    templates = agent_templates.get(complexity, {}).get("D0", [])
                    if templates:
                        date_type = "D0"
                    else:
                        # 더 낮은 complexity fallback
                        for c in ["C2", "C1"]:
                            templates = agent_templates.get(c, {}).get("D0", [])
                            if templates:
                                complexity = c
                                date_type = "D0"
                                break

                if not templates:
                    continue

                tpl_query, tpl_answer, answer_format, difficulty = random.choice(templates)

                # 슬롯 채우기
                domain_cat, subject = get_random_subject()
                tech = get_random_tech()
                material = get_random_material()
                author = get_random_author()
                equip = get_random_equip()
                metric = get_random_metric()

                # 날짜 생성
                date_expr, parsed_from, parsed_to = resolve_date_range(date_type)

                query = fill_template(tpl_query, subject, domain_cat, date_expr, tech, material, author, equip, metric)
                expected = fill_template(tpl_answer, subject, domain_cat, date_expr, tech, material, author, equip, metric)

                # 중복 방지
                if query in qa_texts_seen:
                    continue
                qa_texts_seen.add(query)

                # 필터 구성
                filters = {}
                if parsed_from:
                    filters["coverdate_from"] = parsed_from
                if parsed_to:
                    filters["coverdate_to"] = parsed_to
                if "{a}" in tpl_query or author in query:
                    if author in query:
                        filters["author"] = author

                # 키워드
                keywords = subject
                if tech in query:
                    keywords += f", {tech}"
                if material in query:
                    keywords += f", {material}"

                qa_item = {
                    "user_role": role_code,
                    "user_role_name": role_name,
                    "agent_type": agent_type,
                    "complexity": complexity,
                    "date_type": date_type,
                    "query_text": query,
                    "expected_answer": expected,
                    "answer_format": answer_format,
                    "date_expression": date_expr,
                    "parsed_from": parsed_from,
                    "parsed_to": parsed_to,
                    "reference_date": REF_DATE_INT if date_type in ("D3", "D4") else None,
                    "expected_filters": json.dumps(filters, ensure_ascii=False) if filters else None,
                    "expected_keywords": keywords,
                    "domain_category": domain_cat,
                    "sub_domain": subject,
                    "difficulty_score": difficulty,
                }
                all_qa.append(qa_item)
                items_generated += 1
                generated += 1

        print(f"[{role_code}] {role_name}: {generated}건 생성 (목표: {target_count})")

    print(f"\n총 {len(all_qa)}건 생성 완료")
    return all_qa


# ============================================================
# MariaDB 적재
# ============================================================

def insert_qa_data(qa_list):
    conn = mariadb.connect(**DB_CONFIG, database=DATABASE)
    cursor = conn.cursor()

    # 기존 데이터 삭제
    cursor.execute("DELETE FROM `date_parse_testcases`")
    cursor.execute("DELETE FROM `qa_dataset`")

    sql = """INSERT INTO `qa_dataset` (
        user_role, user_role_name, agent_type, complexity, date_type,
        query_text, expected_answer, answer_format,
        date_expression, parsed_from, parsed_to, reference_date,
        expected_filters, expected_keywords,
        domain_category, sub_domain, difficulty_score
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    for item in qa_list:
        cursor.execute(sql, (
            item["user_role"], item["user_role_name"], item["agent_type"],
            item["complexity"], item["date_type"],
            item["query_text"], item["expected_answer"], item["answer_format"],
            item["date_expression"], item["parsed_from"], item["parsed_to"],
            item["reference_date"], item["expected_filters"], item["expected_keywords"],
            item["domain_category"], item["sub_domain"], item["difficulty_score"],
        ))

    conn.commit()
    print(f"MariaDB에 {len(qa_list)}건 INSERT 완료")

    # date_parse_testcases 생성 (D1~D4 항목만)
    cursor.execute("SELECT qa_id, date_type, date_expression, parsed_from, parsed_to, reference_date FROM qa_dataset WHERE date_type != 'D0'")
    date_rows = cursor.fetchall()

    tc_sql = """INSERT INTO `date_parse_testcases`
        (qa_id, input_expression, date_type, reference_date, expected_from, expected_to)
        VALUES (?, ?, ?, ?, ?, ?)"""

    tc_count = 0
    for qa_id, dt, expr, p_from, p_to, ref_d in date_rows:
        if expr and p_from and p_to:
            ref = ref_d if ref_d else REF_DATE_INT
            cursor.execute(tc_sql, (qa_id, expr, dt, ref, p_from, p_to))
            tc_count += 1

    conn.commit()
    print(f"date_parse_testcases에 {tc_count}건 INSERT 완료")

    # 분포 검증
    print("\n=== 분포 검증 ===")
    cursor.execute("SELECT user_role, user_role_name, COUNT(*) FROM qa_dataset GROUP BY user_role, user_role_name ORDER BY user_role")
    for row in cursor.fetchall():
        print(f"  {row[0]} {row[1]}: {row[2]}건")

    cursor.execute("SELECT agent_type, COUNT(*) FROM qa_dataset GROUP BY agent_type ORDER BY COUNT(*) DESC")
    print("\n  Agent별:")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]}건")

    cursor.execute("SELECT date_type, COUNT(*) FROM qa_dataset GROUP BY date_type ORDER BY date_type")
    print("\n  날짜유형별:")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]}건")

    cursor.execute("SELECT complexity, COUNT(*) FROM qa_dataset GROUP BY complexity ORDER BY complexity")
    print("\n  난이도별:")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]}건")

    cursor.close()
    conn.close()


def main():
    random.seed(42)  # 재현성
    qa_list = generate_all_qa()
    insert_qa_data(qa_list)


if __name__ == "__main__":
    main()
