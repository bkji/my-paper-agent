"""qa_dataset 추가 질문 1,000건 생성 → MariaDB INSERT.

유형:
- analytics (신규): 집계/통계/목록/그래프 질문
- 기존 13개 agent: 다양한 사용자 역할, 날짜 유형, 복잡도 커버
"""
import os
import sys
import random
import json
import pymysql
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

conn = pymysql.connect(
    host=os.getenv("MARIADB_HOST"),
    port=int(os.getenv("MARIADB_PORT")),
    user=os.getenv("MARIADB_USER"),
    password=os.getenv("MARIADB_PASSWORD"),
    database=os.getenv("MARIADB_DATABASE"),
    charset="utf8mb4",
)
cursor = conn.cursor()

# ─── 기본 데이터 ─────────────────────────────────────────────

USER_ROLES = {
    "R1": "R&D 연구자",
    "R2": "공정 엔지니어",
    "R3": "재료 엔지니어",
    "R4": "품질/신뢰성 엔지니어",
    "R5": "설비 엔지니어",
    "R6": "소프트웨어 개발자",
    "R7": "경영/전략 기획",
    "R8": "특허/IP 담당자",
}

DOMAINS = {
    "OLED": ["발광효율", "수명", "번인", "마이크로 캐비티", "캐비티 구조", "투명 OLED", "플렉서블 OLED",
             "정공수송층(HTL)", "전자수송층(ETL)", "TADF 소재", "인광 재료", "형광 재료", "탑에미션"],
    "MicroLED": ["전사 기술", "GaN LED", "에피택시 성장", "레이저 리프트오프(LLO)", "검사 및 리페어",
                 "칩 본딩", "컬러 변환", "양자점 패터닝", "AR/VR 디스플레이", "대면적 전사"],
    "LCD": ["백라이트 효율", "고속 응답", "IPS/VA 모드", "편광판", "로컬디밍", "HDR 구현",
            "광학 필름", "대면적 디스플레이", "산화물 TFT", "QDEF"],
    "TFT": ["LTPS", "IGZO", "산화물 반도체", "플렉서블 TFT", "a-Si TFT", "게이트 드라이버",
            "TFT 이동도", "박막 트랜지스터", "보상 회로"],
    "QD": ["양자점 합성", "페로브스카이트 양자점", "QD-OLED", "QD-LED", "색순도", "안정성",
           "카드뮴 프리", "InP 양자점", "코어쉘 구조"],
    "공정": ["습식 식각", "건식 식각", "잉크젯 프린팅", "슬롯다이 코팅", "PECVD", "ALD",
            "세정 공정", "포토리소그래피", "습식 코팅", "열증착"],
    "봉지": ["TFE(Thin Film Encapsulation)", "봉지 필름", "수분투과율(WVTR)", "봉지 신뢰성",
            "ALD 봉지", "유기/무기 다층", "에지 실링", "댐 앤 필"],
    "장비": ["증착기", "노광장비", "식각장비", "라미네이션 장비", "인라인 시스템", "클러스터 장비",
            "검사장비", "레이저 가공장비", "E-beam 증착", "진공 챔버"],
}

COMPANIES = ["Samsung", "BOE", "LG Display", "TCL CSOT", "Sharp", "JDI", "AUO", "Innolux",
             "Visionox", "Tianma", "Canon Tokki", "Applied Materials", "Kateeva",
             "Universal Display", "Coherent", "Sumitomo Chemical", "Idemitsu Kosan", "Merck"]

UNIVERSITIES = ["KAIST", "서울대", "성균관대", "ETRI", "포항공대", "연세대", "고려대",
                "MIT", "Stanford", "Tsinghua", "NTU Singapore"]

DATE_D1 = []  # 절대 연월
for y in range(2020, 2027):
    for m in range(1, 13):
        DATE_D1.append(f"{y}년 {m}월")

DATE_D2_YEAR = [f"{y}년" for y in range(2020, 2027)]
DATE_D2_HALF = [f"{y}년 {h}" for y in range(2020, 2027) for h in ["상반기", "하반기"]]
DATE_D2_QUARTER = [f"{y}년 {q}분기" for y in range(2020, 2027) for q in range(1, 5)]
DATE_D2_RANGE = [f"{y1}~{y2}년" for y1 in range(2020, 2025) for y2 in range(y1+1, 2027)]

DATE_D3 = ["최근 3개월", "최근 6개월", "최근 9개월", "최근 1년", "최근 2년", "최근 3년",
           "최근 5년", "최근 12개월", "올해", "올해 초", "금년", "작년", "지난해",
           "작년 여름", "작년 겨울", "지난달"]

DATE_D4_COMPARE = [f"{y1}년과 {y2}년 비교" for y1 in range(2020, 2025) for y2 in range(y1+1, 2027) if y2 - y1 <= 3]
DATE_D4_VS = [f"{y1}년 대비 {y2}년" for y1 in range(2020, 2025) for y2 in range(y1+1, 2027) if y2 - y1 <= 3]
DATE_D4_CHANGE = [f"{y1}~{y2}년 변화" for y1 in range(2020, 2025) for y2 in range(y1+1, 2027) if y2 - y1 <= 4]

ref_date = 20260320

# ─── 날짜 파싱 결과 계산 ─────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.date_parser import extract_date_filters


def parse_date(expr):
    r = extract_date_filters(expr, reference_date=datetime(2026, 3, 20))
    if r:
        return r.get("coverdate_from"), r.get("coverdate_to")
    return None, None


# ─── 질문 생성 템플릿 ─────────────────────────────────────────

def gen_analytics_questions():
    """analytics 에이전트용 질문 생성 (~400건)"""
    questions = []

    # 월별/연도별 통계 (~100건)
    for _ in range(50):
        d = random.choice(DATE_D2_YEAR + DATE_D2_HALF)
        domain = random.choice(list(DOMAINS.keys()))
        kw = random.choice(DOMAINS[domain])
        templates = [
            f"{d} {kw} 관련 논문 월별 편수를 보여줘",
            f"{d} {domain} 분야 논문 통계를 알려줘",
            f"{d} {kw} 논문 건수 추이를 그래프로 나타내줘",
        ]
        q = random.choice(templates)
        pf, pt = parse_date(d)
        questions.append(("analytics", "C2", q, kw, domain, d, pf, pt))

    for _ in range(50):
        d = random.choice(DATE_D3)
        domain = random.choice(list(DOMAINS.keys()))
        kw = random.choice(DOMAINS[domain])
        templates = [
            f"{d} {kw} 논문이 몇 편 있어?",
            f"{d} {domain} 분야 논문 월별 편수를 알려줘",
            f"{d} {kw} 관련 연구 통계를 보여줘",
        ]
        q = random.choice(templates)
        pf, pt = parse_date(d)
        questions.append(("analytics", "C2", q, kw, domain, d, pf, pt))

    # 논문 목록 조회 (~100건)
    for _ in range(50):
        d = random.choice(DATE_D1[:48])  # 2020~2023년
        domain = random.choice(list(DOMAINS.keys()))
        kw = random.choice(DOMAINS[domain])
        templates = [
            f"{d}에 발표된 {kw} 관련 논문 목록을 보여줘",
            f"{d} {domain} 논문 리스트를 알려줘",
        ]
        q = random.choice(templates)
        pf, pt = parse_date(d)
        questions.append(("analytics", "C1", q, kw, domain, d, pf, pt))

    for _ in range(50):
        d = random.choice(DATE_D3)
        domain = random.choice(list(DOMAINS.keys()))
        kw = random.choice(DOMAINS[domain])
        comp = random.choice(COMPANIES + UNIVERSITIES)
        templates = [
            f"{d} {comp}의 {kw} 논문 목록",
            f"{d} {kw} 관련 논문 제목과 저자를 보여줘",
            f"{d} {domain} 분야에서 어떤 논문이 발표되었는지 알려줘",
        ]
        q = random.choice(templates)
        pf, pt = parse_date(d)
        questions.append(("analytics", "C2", q, kw, domain, d, pf, pt))

    # 비교 집계 (~50건)
    for _ in range(50):
        d = random.choice(DATE_D4_CHANGE + DATE_D4_COMPARE)
        domain = random.choice(list(DOMAINS.keys()))
        kw = random.choice(DOMAINS[domain])
        templates = [
            f"{d} {kw} 논문 편수 변화를 보여줘",
            f"{d} {domain} 분야 논문 건수 추이를 연도별로 비교해줘",
        ]
        q = random.choice(templates)
        pf, pt = parse_date(d)
        questions.append(("analytics", "C3", q, kw, domain, d, pf, pt))

    # 날짜 없는 전체 통계 (~50건)
    for _ in range(50):
        domain = random.choice(list(DOMAINS.keys()))
        kw = random.choice(DOMAINS[domain])
        templates = [
            f"{kw} 관련 전체 논문 편수를 연도별로 보여줘",
            f"{domain} 분야 논문 월별 발표 추이",
            f"{kw} 관련 저자별 논문 수 Top 10을 알려줘",
            f"전체 논문 월별 통계를 그래프로 보여줘",
        ]
        q = random.choice(templates)
        questions.append(("analytics", "C2", q, kw, domain, None, None, None))

    return questions


def gen_agent_questions():
    """기존 에이전트용 다양한 질문 생성 (~600건)"""
    questions = []
    agent_templates = {
        "paper_qa": [
            "{kw} 관련 최신 연구 결과를 알려줘",
            "{comp}이(가) 발표한 {kw} 논문의 핵심 내용은?",
            "{kw}와 {kw2}의 차이점을 논문 기반으로 설명해줘",
            "{d} {kw} 관련 논문에서 사용된 방법론은?",
            "{kw} 분야에서 가장 많이 인용되는 연구는?",
        ],
        "literature_survey": [
            "{kw} 관련 문헌 리뷰를 작성해줘",
            "{d} {domain} 분야 연구 동향을 종합적으로 정리해줘",
            "{kw} 기술의 발전 과정을 문헌 기반으로 요약해줘",
        ],
        "trend_analyzer": [
            "{d} {kw} 기술 트렌드를 분석해줘",
            "{domain} 분야에서 향후 3년 기술 예측을 해줘",
            "{d} {kw} 연구 방향이 어떻게 변했는지 분석해줘",
        ],
        "idea_generator": [
            "{kw} 분야에서 새로운 연구 아이디어를 제안해줘",
            "{kw}와 {kw2}를 융합한 연구 주제를 추천해줘",
        ],
        "experiment_planner": [
            "{kw} 성능 향상을 위한 실험 설계를 해줘",
            "{kw} 관련 최적 조건을 찾기 위한 실험 방법을 제안해줘",
        ],
        "material_advisor": [
            "{kw}에 적합한 재료를 비교 분석해줘",
            "{kw} 성능 향상을 위한 최적 재료/공정을 추천해줘",
        ],
        "competitive_intel": [
            "{comp}의 {kw} 기술 동향을 분석해줘",
            "{kw} 분야 주요 경쟁사들의 기술 수준을 비교해줘",
        ],
        "patent_landscaper": [
            "{kw} 관련 특허 동향을 분석해줘",
            "{domain} 분야 특허 공백 영역을 식별해줘",
        ],
        "report_drafter": [
            "{d} {kw} 기술 현황 보고서 초안을 작성해줘",
            "{kw} 관련 연구 성과를 정리한 발표 자료를 만들어줘",
        ],
        "cross_domain": [
            "반도체 분야의 {kw2} 기술을 {kw}에 적용할 수 있을까?",
            "바이오 분야 접근법 중 {kw} 문제 해결에 도움될 게 있어?",
        ],
        "peer_review": [
            "{kw} 관련 연구 논문의 가상 리뷰를 해줘",
            "{domain} 분야 최신 연구의 강점과 약점을 분석해줘",
        ],
        "knowledge_connector": [
            "{kw} 분야 전문가를 추천해줘",
            "{domain} 관련 연구를 가장 많이 한 저자는 누구야?",
        ],
    }

    for agent_type, templates in agent_templates.items():
        count = 50 if agent_type in ("paper_qa", "trend_analyzer", "literature_survey") else 30
        for _ in range(count):
            domain = random.choice(list(DOMAINS.keys()))
            kws = DOMAINS[domain]
            kw = random.choice(kws)
            kw2 = random.choice([k for k in kws if k != kw]) if len(kws) > 1 else kw
            comp = random.choice(COMPANIES + UNIVERSITIES)

            # 날짜 유형 선택
            date_type = random.choice(["D0", "D0", "D1", "D2", "D3", "D4"])
            d = None
            pf, pt = None, None
            if date_type == "D1":
                d = random.choice(DATE_D1[:60])
            elif date_type == "D2":
                d = random.choice(DATE_D2_YEAR + DATE_D2_HALF + DATE_D2_QUARTER)
            elif date_type == "D3":
                d = random.choice(DATE_D3)
            elif date_type == "D4":
                d = random.choice(DATE_D4_COMPARE + DATE_D4_VS + DATE_D4_CHANGE)
                date_type = "D4"
            else:
                date_type = "D0"

            if d:
                pf, pt = parse_date(d)

            template = random.choice(templates)
            q = template.format(kw=kw, kw2=kw2, comp=comp, d=d or "", domain=domain)
            q = q.replace("  ", " ").strip()

            complexity = "C1" if date_type == "D0" else ("C2" if date_type in ("D1", "D2") else "C3")
            questions.append((agent_type, complexity, q, kw, domain, d, pf, pt))

    return questions


# ─── 생성 및 INSERT ─────────────────────────────────────────

print("질문 생성 중...")
random.seed(42)

analytics_qs = gen_analytics_questions()
agent_qs = gen_agent_questions()
all_qs = analytics_qs + agent_qs
random.shuffle(all_qs)

# 1000건으로 제한
all_qs = all_qs[:1000]

print(f"총 {len(all_qs)}건 생성됨")

# agent_type 분포
from collections import Counter
type_dist = Counter(q[0] for q in all_qs)
print("에이전트별 분포:")
for k, v in sorted(type_dist.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}건")

date_dist = Counter()
for q in all_qs:
    dt = "D0" if q[5] is None else ("D1" if "월" in str(q[5]) and "분기" not in str(q[5]) and "반기" not in str(q[5]) and "~" not in str(q[5])
                                     else ("D4" if "비교" in str(q[5]) or "대비" in str(q[5]) or "변화" in str(q[5])
                                           else ("D3" if any(x in str(q[5]) for x in ["최근", "올해", "작년", "금년", "지난"]) else "D2")))
    date_dist[dt] += 1
print("날짜 유형별 분포:")
for k, v in sorted(date_dist.items()):
    print(f"  {k}: {v}건")

# INSERT
role_keys = list(USER_ROLES.keys())
insert_sql = """
INSERT INTO qa_dataset
    (user_role, user_role_name, agent_type, complexity, date_type, query_text,
     expected_answer, answer_format, date_expression, parsed_from, parsed_to,
     reference_date, expected_filters, expected_keywords, domain_category, sub_domain,
     difficulty_score, is_validated)
VALUES
    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

count = 0
for agent_type, complexity, query_text, kw, domain, date_expr, pf, pt in all_qs:
    role_key = random.choice(role_keys)
    role_name = USER_ROLES[role_key]

    # date_type 판별
    if date_expr is None:
        date_type = "D0"
    elif any(x in str(date_expr) for x in ["비교", "대비", "변화"]):
        date_type = "D4"
    elif any(x in str(date_expr) for x in ["최근", "올해", "작년", "금년", "지난"]):
        date_type = "D3"
    elif "월" in str(date_expr) and "분기" not in str(date_expr) and "반기" not in str(date_expr) and "~" not in str(date_expr):
        date_type = "D1"
    else:
        date_type = "D2"

    # expected_answer 간략
    if agent_type == "analytics":
        expected_answer = "MariaDB SQL 집계/목록 결과 기반 응답"
    else:
        expected_answer = f"{agent_type} 에이전트가 RAG 기반으로 응답"

    # expected_filters
    filters = {}
    if pf:
        filters["coverdate_from"] = pf
    if pt:
        filters["coverdate_to"] = pt

    difficulty = {"C1": 1, "C2": 2, "C3": 3}.get(complexity, 2)

    cursor.execute(insert_sql, (
        role_key, role_name, agent_type, complexity, date_type, query_text,
        expected_answer, "text", date_expr, pf, pt,
        ref_date, json.dumps(filters, ensure_ascii=False) if filters else None,
        kw, domain, kw,
        difficulty, 0
    ))
    count += 1

conn.commit()
print(f"\n{count}건 INSERT 완료")

# 최종 확인
cursor.execute("SELECT COUNT(*) FROM qa_dataset")
total = cursor.fetchone()[0]
print(f"qa_dataset 총 건수: {total}건")

cursor.close()
conn.close()
