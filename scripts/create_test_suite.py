"""폐쇄망 테스트용 agent_test_suite 테이블 생성 및 데이터 적재 (~1,000건).

14개 에이전트 × 5개 카테고리 × 다양한 도메인/날짜/난이도 조합.
중복 질문 없이 생성하며, 기존 qa_dataset(2,080건)과 별도로 운영.

검증 카테고리:
- intent_check: LLM이 올바른 에이전트로 분류하는지
- answer_quality: 답변 품질 (길이, 구조, 키워드 포함)
- date_filter: 날짜 필터가 올바르게 적용되는지
- multi_turn: 멀티턴 대화에서 문맥 유지
- edge_case: 엣지케이스 처리
"""
import os
import sys
import json
import random
import pymysql
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

random.seed(42)

conn = pymysql.connect(
    host=os.getenv("MARIADB_HOST"),
    port=int(os.getenv("MARIADB_PORT")),
    user=os.getenv("MARIADB_USER"),
    password=os.getenv("MARIADB_PASSWORD"),
    database=os.getenv("MARIADB_DATABASE"),
    charset="utf8mb4",
)
cursor = conn.cursor()

# ── 테이블 생성 ──────────────────────────────────────────────
cursor.execute("DROP TABLE IF EXISTS agent_test_suite")
cursor.execute("""
CREATE TABLE agent_test_suite (
    test_id         INT AUTO_INCREMENT PRIMARY KEY,
    agent_type      VARCHAR(30)   NOT NULL COMMENT '기대 에이전트 타입',
    test_category   VARCHAR(30)   NOT NULL COMMENT 'intent_check|answer_quality|date_filter|multi_turn|edge_case',
    difficulty      VARCHAR(10)   DEFAULT 'C1' COMMENT 'C1/C2/C3',
    query_text      TEXT          NOT NULL COMMENT '테스트 질문',
    conversation_history JSON     DEFAULT NULL COMMENT '멀티턴 이전 대화 (messages 배열)',
    expected_keywords TEXT        DEFAULT NULL COMMENT '답변에 포함되어야 할 키워드 (콤마 구분)',
    expected_format VARCHAR(30)   DEFAULT 'text' COMMENT 'text|table|structured|report',
    check_criteria  JSON          DEFAULT NULL COMMENT '검증 기준 {min_len, must_contain 등}',
    description     VARCHAR(200)  DEFAULT NULL COMMENT '테스트 설명',
    is_active       TINYINT       DEFAULT 1,
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_agent (agent_type),
    INDEX idx_category (test_category),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""")
print("agent_test_suite 테이블 생성 완료")


# ═══════════════════════════════════════════════════════════════
# 도메인 데이터
# ═══════════════════════════════════════════════════════════════

TOPICS = {
    "OLED": [
        "OLED 발광 효율", "OLED 수명", "번인 현상", "마이크로 캐비티", "투명 OLED",
        "플렉서블 OLED", "정공수송층(HTL)", "전자수송층(ETL)", "TADF 소재", "인광 재료",
        "형광 재료", "탑에미션 구조", "WOLED", "탠덤 OLED", "잉크젯 OLED",
        "OLED 봉지", "OLED 구동 회로", "OLED 색재현", "OLED 전력소모",
    ],
    "MicroLED": [
        "Micro LED 전사 기술", "GaN LED", "에피택시 성장", "레이저 리프트오프",
        "Micro LED 검사", "Micro LED 리페어", "칩 본딩", "컬러 변환층",
        "양자점 패터닝", "대면적 전사", "Micro LED 수율", "Micro LED 균일도",
        "Micro LED 구동 회로", "Micro LED 열관리", "Red Micro LED",
    ],
    "LCD": [
        "백라이트 효율", "고속 응답", "IPS 모드", "VA 모드", "편광판",
        "로컬디밍", "HDR 구현", "광학 필름", "Mini LED 백라이트",
        "산화물 TFT LCD", "QDEF 필름", "LCD 시야각", "LCD 명암비",
    ],
    "QD": [
        "양자점 합성", "페로브스카이트 양자점", "QD-OLED", "QD-LED",
        "양자점 색순도", "양자점 안정성", "카드뮴 프리 양자점", "InP 양자점",
        "코어쉘 구조", "양자점 패터닝", "QD 컬러필터", "QD 발광 효율",
    ],
    "TFT": [
        "LTPS TFT", "IGZO TFT", "산화물 반도체", "플렉서블 TFT", "a-Si TFT",
        "게이트 드라이버", "TFT 이동도", "보상 회로", "TFT 균일도",
        "저온 공정 TFT", "TFT 안정성", "oxide TFT",
    ],
    "공정": [
        "습식 식각", "건식 식각", "잉크젯 프린팅", "슬롯다이 코팅", "PECVD",
        "ALD 공정", "포토리소그래피", "열증착", "스퍼터링", "플라즈마 처리",
        "레이저 어닐링", "나노임프린트",
    ],
    "봉지": [
        "TFE 봉지", "봉지 필름", "수분투과율(WVTR)", "ALD 봉지",
        "유기/무기 다층 봉지", "에지 실링", "댐 앤 필", "봉지 신뢰성",
    ],
    "홀로그래픽": [
        "holographic grating", "holographic display", "CGH(Computer Generated Hologram)",
        "SLM(Spatial Light Modulator)", "3D 홀로그래픽 디스플레이",
    ],
    "AR/VR": [
        "AR 디스플레이", "VR 디스플레이", "foveated rendering", "near-eye display",
        "see-through display", "광도파관", "마이크로디스플레이",
    ],
}

COMPANIES = [
    "Samsung Display", "LG Display", "BOE", "TCL CSOT", "Sharp", "JDI",
    "AUO", "Innolux", "Visionox", "Tianma", "Canon Tokki", "Applied Materials",
    "Kateeva", "Universal Display", "Coherent", "Sumitomo Chemical", "Merck",
    "Idemitsu Kosan", "Dupont", "Corning",
]

DATES_D1 = [f"{y}년 {m}월" for y in range(2022, 2026) for m in range(1, 13)]
DATES_D2_HALF = [f"{y}년 {h}" for y in range(2022, 2026) for h in ["상반기", "하반기"]]
DATES_D2_Q = [f"{y}년 {q}분기" for y in range(2022, 2026) for q in range(1, 5)]
DATES_D2_YEAR = [f"{y}년" for y in range(2020, 2026)]
DATES_D2_RANGE = [f"{y1}~{y2}년" for y1 in range(2020, 2025) for y2 in range(y1+1, 2027) if y2 - y1 <= 3]
DATES_D3 = [
    "최근 3개월", "최근 6개월", "최근 9개월", "최근 1년", "최근 2년", "최근 3년",
    "최근 12개월", "올해", "올해 초", "작년", "지난해", "지난달",
]
DATES_D4 = [f"{y1}년 대비 {y2}년" for y1 in range(2021, 2025) for y2 in range(y1+1, 2026)]


def pick_topic():
    domain = random.choice(list(TOPICS.keys()))
    topic = random.choice(TOPICS[domain])
    return domain, topic


def pick_date(dtype=None):
    if dtype == "D1":
        return random.choice(DATES_D1)
    elif dtype == "D2":
        return random.choice(DATES_D2_HALF + DATES_D2_Q + DATES_D2_YEAR + DATES_D2_RANGE)
    elif dtype == "D3":
        return random.choice(DATES_D3)
    elif dtype == "D4":
        return random.choice(DATES_D4)
    else:
        return random.choice(DATES_D1 + DATES_D2_HALF + DATES_D3)


# ═══════════════════════════════════════════════════════════════
# 질문 생성기
# ═══════════════════════════════════════════════════════════════

ALL_TESTS = []
SEEN_QUERIES = set()  # 중복 방지


def add(agent, category, query, difficulty="C1", keywords=None, fmt="text",
        criteria=None, desc=None, history=None):
    # 중복 체크
    q_norm = query.strip()
    if q_norm in SEEN_QUERIES:
        return False
    SEEN_QUERIES.add(q_norm)
    ALL_TESTS.append({
        "agent_type": agent,
        "test_category": category,
        "difficulty": difficulty,
        "query_text": q_norm,
        "conversation_history": json.dumps(history, ensure_ascii=False) if history else None,
        "expected_keywords": keywords,
        "expected_format": fmt,
        "check_criteria": json.dumps(criteria, ensure_ascii=False) if criteria else None,
        "description": desc,
    })
    return True


# ═══════════════════════════════════════════════════════════════
# 1. analytics (~120건)
# ═══════════════════════════════════════════════════════════════

# intent_check: 편수/목록/추이 등 다양한 표현
analytics_count_templates = [
    "{date} 논문 편수 알려줘",
    "{date} 발표된 논문 몇 편이야?",
    "{date} 논문이 총 몇 건이야?",
    "{topic} 관련 논문 편수",
    "{date} {topic} 논문 몇 편?",
    "전체 논문 수는?",
    "{topic} 논문이 몇 편인지 알려줘",
    "{date} 게재된 논문 건수",
]

analytics_list_templates = [
    "{date} 논문 목록 보여줘",
    "{date} 발표된 논문 제목을 보여줘",
    "{topic} 관련 논문 리스트",
    "{date} {topic} 논문 목록",
    "{topic} 논문 찾아줘",
    "{date} 논문 제목 알려줘",
    "volume {vol} issue {iss} 논문 목록",
    "{topic} 관련 논문 있어?",
]

analytics_trend_templates = [
    "연도별 논문 편수 추이를 보여줘",
    "월별 논문 발표 추이",
    "{topic} 논문 연도별 추이",
    "분기별 논문 편수 경향",
    "{date} {topic} 월별 추이",
    "논문 발표 동향 그래프",
    "{topic} 논문 수 변화 추이",
    "연도별 {topic} 논문 경향 분석",
]

analytics_agg_templates = [
    "저자별 논문 편수 상위 10명",
    "도메인별 논문 비율 알려줘",
    "{date} 주요 키워드별 논문 분포",
    "월별 평균 논문 편수는?",
    "{topic} 분야 논문 비중이 어느 정도야?",
]

# intent_check
for tmpl in analytics_count_templates:
    for _ in range(3):
        _, topic = pick_topic()
        date = pick_date()
        q = tmpl.format(date=date, topic=topic)
        add("analytics", "intent_check", q, keywords="편", desc="편수 질문")

for tmpl in analytics_list_templates:
    for _ in range(2):
        _, topic = pick_topic()
        date = pick_date()
        vol = random.randint(60, 65)
        iss = random.randint(1, 4)
        q = tmpl.format(date=date, topic=topic, vol=vol, iss=iss)
        add("analytics", "intent_check", q, keywords="제목", fmt="table", desc="목록 질문")

for tmpl in analytics_trend_templates:
    _, topic = pick_topic()
    date = pick_date("D2")
    q = tmpl.format(date=date, topic=topic)
    add("analytics", "intent_check", q, keywords="추이", desc="추이 질문")

for tmpl in analytics_agg_templates:
    _, topic = pick_topic()
    date = pick_date("D2")
    q = tmpl.format(date=date, topic=topic)
    add("analytics", "intent_check", q, keywords="편", difficulty="C2", desc="복합 집계")

# date_filter
for dtype in ["D1", "D2", "D3", "D4"]:
    for _ in range(4):
        date = pick_date(dtype)
        _, topic = pick_topic()
        templates = [
            f"{date} 논문 편수는?",
            f"{date} {topic} 논문 목록",
            f"{date} 논문 추이 보여줘",
            f"{date} 발표된 논문 제목 알려줘",
        ]
        q = random.choice(templates)
        add("analytics", "date_filter", q, keywords="편,제목", desc=f"날짜 {dtype} 필터")

# answer_quality
for _ in range(8):
    _, topic = pick_topic()
    date = pick_date()
    templates = [
        f"{date} {topic} 논문 편수와 제목을 보여줘",
        f"{topic} 관련 논문 목록과 편수를 정리해줘",
        f"{date} 논문 중 {topic} 관련 것만 골라서 보여줘",
    ]
    q = random.choice(templates)
    add("analytics", "answer_quality", q, keywords="편,제목", fmt="table", difficulty="C2",
        desc="편수+목록 복합 답변")

# edge_case
add("analytics", "edge_case", "2010년 논문 있어?", desc="데이터 없는 연도")
add("analytics", "edge_case", "2030년 논문 편수", desc="미래 날짜")
add("analytics", "edge_case", "zzxqw 관련 논문 있어?", desc="무의미 키워드")
add("analytics", "edge_case", "논문", desc="너무 짧은 질문")
add("analytics", "edge_case", "전체 논문 편수와 저자 목록과 키워드 분포와 연도별 추이를 한번에 보여줘",
    difficulty="C3", desc="과다 요청")


# ═══════════════════════════════════════════════════════════════
# 2. paper_qa (~120건)
# ═══════════════════════════════════════════════════════════════

pqa_tech_templates = [
    "{topic}에 대해 알려줘",
    "{topic}의 원리를 설명해줘",
    "{topic} 방법에 대해 설명해줘",
    "{topic}의 최신 기술은?",
    "{topic}을 개선하는 방법은?",
    "{topic}의 장단점을 설명해줘",
    "{topic} 기술의 핵심 과제는?",
    "{topic}이란 무엇인가?",
    "{topic}의 작동 원리는?",
    "{topic}에서 중요한 파라미터는?",
]

pqa_specific_templates = [
    "{topic}의 성능을 높이기 위한 접근법은?",
    "{topic} 분야에서 가장 많이 사용되는 방법은?",
    "{topic} 기술의 한계와 해결 방안은?",
    "{topic} 연구에서 주로 사용되는 측정 방법은?",
    "{topic}의 응용 분야는?",
    "{topic}에 영향을 미치는 주요 요인은?",
]

pqa_paper_title_templates = [
    "{title} 논문을 요약해줘",
    "{title} 논문의 핵심 기여는?",
    "{title} 논문에서 사용된 방법론은?",
]

PAPER_TITLES = [
    "Subjective assessment of visual fidelity",
    "High-speed and contactless inspection of defective micro-LEDs",
    "Wide-viewing-angle dual-view integral imaging display",
    "Holographic grating-based optical element",
    "Foveated rendering for near-eye display",
    "Flexible OLED display with thin-film encapsulation",
    "Quantum dot color conversion for micro-LED",
    "Oxide TFT backplane for AMOLED",
    "High-efficiency tandem OLED architecture",
    "Mini LED backlight with local dimming",
]

# intent_check
for tmpl in pqa_tech_templates:
    for _ in range(3):
        _, topic = pick_topic()
        q = tmpl.format(topic=topic)
        add("paper_qa", "intent_check", q, keywords=topic.split()[0], desc="기술 질문")

for tmpl in pqa_specific_templates:
    for _ in range(2):
        _, topic = pick_topic()
        q = tmpl.format(topic=topic)
        add("paper_qa", "intent_check", q, keywords=topic.split()[0], desc="심화 기술 질문")

# answer_quality - 논문 제목 기반
for title in PAPER_TITLES:
    for tmpl in pqa_paper_title_templates:
        q = tmpl.format(title=title)
        add("paper_qa", "answer_quality", q, keywords="요약,기여,방법", difficulty="C2",
            desc="논문 제목 기반 질문")

# answer_quality - 비교/분석
pqa_compare = [
    "{t1}와 {t2}의 차이점은?",
    "{t1} 대비 {t2}의 장점은?",
    "{t1}과 {t2} 중 어떤 것이 더 효율적인가?",
]
for tmpl in pqa_compare:
    for _ in range(3):
        d1, t1 = pick_topic()
        d2, t2 = pick_topic()
        if t1 != t2:
            q = tmpl.format(t1=t1, t2=t2)
            add("paper_qa", "answer_quality", q, difficulty="C2", desc="기술 비교 질문")

# date_filter
for _ in range(8):
    date = pick_date()
    _, topic = pick_topic()
    templates = [
        f"{date} {topic} 연구 내용을 알려줘",
        f"{date} 발표된 {topic} 관련 논문 내용은?",
        f"{date} {topic} 기술 논문에서 다룬 방법은?",
    ]
    q = random.choice(templates)
    add("paper_qa", "date_filter", q, keywords=topic.split()[0], desc="날짜+기술 질문")

# multi_turn
multi_turn_contexts = [
    {"topic": "Micro LED 결함 검출", "prev_answer": "Micro LED 결함 검출에는 PL 검사, EL 검사, 광학 현미경 기반 자동 검사 등이 있습니다..."},
    {"topic": "OLED 발광 효율", "prev_answer": "OLED 발광 효율을 높이기 위해서는 재료 최적화, 구조 설계, 광추출 기술 등이 사용됩니다..."},
    {"topic": "양자점 합성", "prev_answer": "양자점 합성에는 열분해법, 핫인젝션법 등이 주로 사용되며..."},
    {"topic": "TFT 이동도", "prev_answer": "TFT 이동도를 높이기 위해서는 채널 재료 선택, 어닐링 조건, 게이트 절연막 등이 중요합니다..."},
    {"topic": "플렉서블 디스플레이", "prev_answer": "플렉서블 디스플레이는 PI 기판, TFE 봉지, 유연한 터치센서 등의 기술이 필요합니다..."},
]

mt_followups = [
    "이 논문의 실험 방법을 더 자세히 설명해줘",
    "좀 더 구체적으로 알려줘",
    "관련 논문이 더 있어?",
    "이 기술의 한계점은?",
    "실제 적용 사례가 있어?",
    "1번째 논문을 자세히 설명해줘",
    "2번째 논문의 핵심 내용은?",
    "참조 문헌 1번 자세히 알려줘",
    "다른 접근 방법은 없어?",
    "이 방법의 장단점을 비교해줘",
]

for ctx in multi_turn_contexts:
    for followup in random.sample(mt_followups, 4):
        history = [
            {"role": "user", "content": f"{ctx['topic']}에 대해 알려줘"},
            {"role": "assistant", "content": ctx["prev_answer"]},
        ]
        add("paper_qa", "multi_turn", followup, history=history,
            desc=f"멀티턴: {ctx['topic']} → 후속질문")

# edge_case
add("paper_qa", "edge_case", "존재하지 않는 XYZ123 기술에 대해 알려줘", desc="검색 결과 없음")
add("paper_qa", "edge_case", "?", desc="단일 문자 질문")
add("paper_qa", "edge_case", "OLED", desc="단어만 입력")
add("paper_qa", "edge_case", "모든 디스플레이 기술의 원리를 다 설명해줘", difficulty="C3", desc="과도하게 넓은 질문")
add("paper_qa", "edge_case", "이전에 물어본 것 다시 알려줘", desc="멀티턴 없이 이전 참조")


# ═══════════════════════════════════════════════════════════════
# 3. literature_survey (~80건)
# ═══════════════════════════════════════════════════════════════

ls_templates = [
    "{topic} 연구 동향을 종합적으로 정리해줘",
    "{topic}에 대한 문헌 리뷰를 작성해줘",
    "{topic} 분야 서베이를 해줘",
    "{topic} 관련 최신 연구를 정리해줘",
    "{topic} 기술 현황과 향후 과제를 정리해줘",
    "{topic} 연구의 최근 진행 상황을 종합해줘",
    "{domain} 분야 전반적인 연구 동향을 리뷰해줘",
    "{topic} 관련 주요 논문들을 종합 정리해줘",
]

for tmpl in ls_templates:
    for domain, topics in TOPICS.items():
        for topic in random.sample(topics, min(2, len(topics))):
            q = tmpl.format(topic=topic, domain=domain)
            add("literature_survey", "intent_check", q, keywords="동향,연구",
                fmt="structured", desc=f"{domain} 서베이")

# date_filter
for _ in range(8):
    date = pick_date()
    _, topic = pick_topic()
    q = f"{date} {topic} 연구 동향을 정리해줘"
    add("literature_survey", "date_filter", q, keywords="동향", desc="날짜+서베이")

# answer_quality
ls_quality = [
    "{topic} 분야의 연구 흐름을 배경, 기술, 성과, 과제, 전망으로 나눠서 정리해줘",
    "{topic} 관련 최근 5년 연구를 체계적으로 리뷰해줘",
    "{t1}와 {t2} 연구 동향을 비교 정리해줘",
]
for _ in range(8):
    _, t1 = pick_topic()
    _, t2 = pick_topic()
    tmpl = random.choice(ls_quality)
    q = tmpl.format(topic=t1, t1=t1, t2=t2)
    add("literature_survey", "answer_quality", q, keywords="동향,연구",
        difficulty="C2", fmt="structured", desc="구조화 서베이")

# edge_case
add("literature_survey", "edge_case", "모든 디스플레이 기술의 연구 동향을 한번에 정리해줘",
    difficulty="C3", desc="과도하게 넓은 범위")


# ═══════════════════════════════════════════════════════════════
# 4. paper_deep_dive (~60건)
# ═══════════════════════════════════════════════════════════════

# DOI 기반
SAMPLE_DOIS = [
    "10.1002/jsid.1284", "10.1002/jsid.1200", "10.1002/jsid.1150",
    "10.1002/jsid.1300", "10.1002/jsid.1250", "10.1002/jsid.1100",
    "10.1002/jsid.1350", "10.1002/jsid.1400", "10.1002/jsid.1050",
    "10.1002/jsid.1175",
]

dd_doi_templates = [
    "DOI {doi} 논문을 심층 분석해줘",
    "{doi} 논문의 방법론과 한계를 분석해줘",
    "{doi} 이 논문 분석해줘",
    "{doi} 논문의 핵심 기여와 실험 결과를 정리해줘",
    "DOI {doi} 논문의 강점과 약점은?",
]

for doi in SAMPLE_DOIS:
    for tmpl in random.sample(dd_doi_templates, 3):
        q = tmpl.format(doi=doi)
        add("paper_deep_dive", "intent_check", q, keywords="분석", desc="DOI 심층분석")

# 제목 기반
dd_title_templates = [
    "{title} 논문을 심층 분석해줘",
    "{title} 논문의 핵심 기여와 한계를 분석해줘",
    "{title} 논문의 실험 방법론을 상세 분석해줘",
]
for title in PAPER_TITLES:
    for tmpl in random.sample(dd_title_templates, 2):
        q = tmpl.format(title=title)
        add("paper_deep_dive", "intent_check", q, keywords="분석,기여", desc="제목 기반 심층분석")

# answer_quality
for doi in random.sample(SAMPLE_DOIS, 5):
    q = f"DOI {doi} 논문의 방법론, 강점, 한계, 기여, 향후 방향을 상세히 분석해줘"
    add("paper_deep_dive", "answer_quality", q, keywords="방법론,강점,한계",
        difficulty="C2", fmt="structured", desc="8-point 분석")

# edge_case
add("paper_deep_dive", "edge_case", "DOI 10.9999/fake.0001 논문을 분석해줘", desc="가짜 DOI")
add("paper_deep_dive", "edge_case", "없는논문제목XYZ123 논문 심층 분석해줘", desc="없는 제목")


# ═══════════════════════════════════════════════════════════════
# 5. idea_generator (~70건)
# ═══════════════════════════════════════════════════════════════

ig_templates = [
    "{t1}와 {t2}를 결합한 새로운 연구 아이디어를 제안해줘",
    "{topic} 기반 혁신적 연구 주제를 브레인스토밍해줘",
    "{topic} 분야에서 새로운 연구 방향을 제안해줘",
    "{t1}의 문제를 {t2} 기술로 해결하는 아이디어는?",
    "{topic}을 활용한 차세대 기술 아이디어를 제안해줘",
    "{domain} 분야 미해결 과제를 해결할 연구 아이디어는?",
    "{t1}과 {t2} 융합 연구 아이디어 3가지를 제안해줘",
]

for tmpl in ig_templates:
    for _ in range(8):
        d1, t1 = pick_topic()
        d2, t2 = pick_topic()
        q = tmpl.format(topic=t1, t1=t1, t2=t2, domain=d1)
        add("idea_generator", "intent_check", q, keywords="아이디어", desc="아이디어 제안")

# answer_quality
ig_quality = [
    "{t1}과 {t2} 융합으로 가능한 아이디어 5가지를 신규성, 실현가능성과 함께 제안해줘",
    "{topic} 분야 미해결 문제에 대한 혁신적 접근법을 구체적으로 제안해줘",
    "{topic}에서 기존 접근법의 한계를 극복할 아이디어를 제안하고 실현 전략을 포함해줘",
]
for tmpl in ig_quality:
    for _ in range(4):
        d1, t1 = pick_topic()
        _, t2 = pick_topic()
        q = tmpl.format(topic=t1, t1=t1, t2=t2)
        add("idea_generator", "answer_quality", q, keywords="아이디어,실현",
            difficulty="C2", fmt="structured", desc="구조화 아이디어")

# edge_case
add("idea_generator", "edge_case", "아무 아이디어나 제안해줘", desc="모호한 요청")
add("idea_generator", "edge_case", "우주 탐사와 디스플레이를 결합한 아이디어",
    difficulty="C3", desc="극도로 다른 분야 결합")


# ═══════════════════════════════════════════════════════════════
# 6. cross_domain (~60건)
# ═══════════════════════════════════════════════════════════════

OTHER_DOMAINS = [
    "의료 영상", "반도체 공정", "자동차 센서", "바이오 센서", "태양전지",
    "에너지 저장", "로봇 비전", "인공지능", "나노기술", "3D 프린팅",
    "광통신", "웨어러블", "스마트 섬유", "음향 기술", "배터리",
]

cd_templates = [
    "{other} 기술을 디스플레이 분야에 적용할 수 있는 방법은?",
    "{other} 기술을 {topic}에 활용하는 방안을 제안해줘",
    "{other} 분야의 접근법을 {topic} 문제 해결에 적용하면?",
    "{other}에서 사용되는 {method}를 디스플레이에 적용할 방법은?",
    "다른 분야에서 {topic} 문제를 어떻게 해결하고 있는지 알려줘",
]

METHODS = ["머신러닝", "딥러닝", "강화학습", "시뮬레이션", "최적화 알고리즘",
           "통계적 공정관리", "유전 알고리즘", "전산유체역학"]

for tmpl in cd_templates:
    for other in OTHER_DOMAINS:
        _, topic = pick_topic()
        method = random.choice(METHODS)
        q = tmpl.format(other=other, topic=topic, method=method)
        add("cross_domain", "intent_check", q, keywords=f"{other},디스플레이",
            desc=f"타분야({other}) 적용")

# answer_quality
for _ in range(8):
    other = random.choice(OTHER_DOMAINS)
    _, topic = pick_topic()
    q = f"{other} 분야의 기술을 {topic}에 적용할 구체적 방안과 기대효과, 리스크를 분석해줘"
    add("cross_domain", "answer_quality", q, keywords="적용,기대효과,리스크",
        difficulty="C2", fmt="structured", desc="구체적 적용 분석")

# edge_case
add("cross_domain", "edge_case", "요리 기술을 디스플레이에 적용할 방법은?",
    desc="관련성 낮은 분야")


# ═══════════════════════════════════════════════════════════════
# 7. trend_analyzer (~70건)
# ═══════════════════════════════════════════════════════════════

ta_templates = [
    "{topic} 기술의 발전 트렌드를 분석해줘",
    "{topic} 분야 기술 트렌드 변화를 정리해줘",
    "{domain} 기술 발전 타임라인을 정리해줘",
    "{topic}의 최근 기술 경향은?",
    "{topic} 분야에서 떠오르는 기술은?",
    "{topic} 기술 진화 과정을 분석해줘",
]

for tmpl in ta_templates:
    for domain, topics in TOPICS.items():
        for topic in random.sample(topics, min(2, len(topics))):
            q = tmpl.format(topic=topic, domain=domain)
            add("trend_analyzer", "intent_check", q, keywords="트렌드,기술", desc=f"{domain} 트렌드")

# date_filter
for _ in range(8):
    date = pick_date("D2")
    _, topic = pick_topic()
    q = f"{date} {topic} 기술 트렌드 변화를 분석해줘"
    add("trend_analyzer", "date_filter", q, keywords="트렌드", desc="날짜+트렌드")

# answer_quality
ta_quality = [
    "{t1} vs {t2} 기술 트렌드를 비교 분석해줘",
    "{topic} 기술의 과거, 현재, 미래 트렌드를 분석해줘",
    "{domain} 분야 기술 카테고리별 트렌드와 향후 2~3년 전망을 분석해줘",
]
for tmpl in ta_quality:
    for _ in range(3):
        d1, t1 = pick_topic()
        _, t2 = pick_topic()
        q = tmpl.format(topic=t1, t1=t1, t2=t2, domain=d1)
        add("trend_analyzer", "answer_quality", q, keywords="트렌드,전망",
            difficulty="C2", fmt="structured", desc="심층 트렌드 분석")


# ═══════════════════════════════════════════════════════════════
# 8. experiment_planner (~60건)
# ═══════════════════════════════════════════════════════════════

ep_templates = [
    "{topic} 개선을 위한 실험 설계를 제안해줘",
    "{topic} 최적화 실험 방법론을 설계해줘",
    "{topic} 관련 DOE 실험을 설계해줘",
    "{topic} 성능 평가를 위한 실험 계획을 세워줘",
    "{topic} 연구를 위한 실험 프로토콜을 제안해줘",
    "{topic} 문제 해결을 위한 체계적 실험 방법은?",
]

for tmpl in ep_templates:
    for _ in range(8):
        _, topic = pick_topic()
        q = tmpl.format(topic=topic)
        add("experiment_planner", "intent_check", q, keywords="실험,설계",
            desc="실험 설계 요청")

# answer_quality
ep_quality = [
    "{topic} 최적화를 위한 풀팩토리얼 실험 설계를 변수, 수준, 측정방법 포함하여 제안해줘",
    "{topic} 성능 개선 실험의 독립변수, 종속변수, 통제변수를 정의하고 프로토콜을 설계해줘",
]
for tmpl in ep_quality:
    for _ in range(5):
        _, topic = pick_topic()
        q = tmpl.format(topic=topic)
        add("experiment_planner", "answer_quality", q, keywords="변수,실험,프로토콜",
            difficulty="C2", fmt="structured", desc="구조화된 실험 설계")

# edge_case
add("experiment_planner", "edge_case", "아무 실험이나 설계해줘", desc="모호한 요청")


# ═══════════════════════════════════════════════════════════════
# 9. material_advisor (~60건)
# ═══════════════════════════════════════════════════════════════

ma_templates = [
    "{topic}용 소재를 비교 분석해줘",
    "{topic}에 적합한 재료를 추천해줘",
    "{topic} 소재 후보를 비교하고 최적 소재를 추천해줘",
    "{topic}에 사용되는 재료의 장단점을 비교해줘",
    "{topic} 공정에 적합한 소재 선택 기준은?",
    "{topic}용 대체 소재를 제안해줘",
]

for tmpl in ma_templates:
    for _ in range(8):
        _, topic = pick_topic()
        q = tmpl.format(topic=topic)
        add("material_advisor", "intent_check", q, keywords="소재,비교",
            desc="재료 비교/추천")

# answer_quality
ma_quality = [
    "{topic} 소재 후보를 성능, 비용, 공정적합성, 안정성 기준으로 비교표를 만들어줘",
    "{topic}에 사용되는 재료 3가지를 비교하고 최종 추천과 근거를 제시해줘",
]
for tmpl in ma_quality:
    for _ in range(5):
        _, topic = pick_topic()
        q = tmpl.format(topic=topic)
        add("material_advisor", "answer_quality", q, keywords="비교,추천",
            difficulty="C2", fmt="table", desc="비교표+추천")

# edge_case
add("material_advisor", "edge_case", "가장 싼 디스플레이 소재 알려줘", desc="모호한 비용 질문")


# ═══════════════════════════════════════════════════════════════
# 10. patent_landscaper (~50건)
# ═══════════════════════════════════════════════════════════════

pl_templates = [
    "{topic} 관련 특허 동향을 분석해줘",
    "{topic} 특허 현황과 공백 영역을 분석해줘",
    "{topic} 분야 특허 랜드스케이프를 분석해줘",
    "{topic} 관련 IP 전략을 제안해줘",
    "{topic} 특허 출원 트렌드를 분석해줘",
]

for tmpl in pl_templates:
    for _ in range(8):
        _, topic = pick_topic()
        q = tmpl.format(topic=topic)
        add("patent_landscaper", "intent_check", q, keywords="특허",
            desc="특허 분석 요청")

# answer_quality
for _ in range(6):
    _, topic = pick_topic()
    q = f"{topic} 분야 특허 현황, 주요 출원인, 기술 클러스터, 공백 영역, IP 전략을 종합 분석해줘"
    add("patent_landscaper", "answer_quality", q, keywords="특허,공백,전략",
        difficulty="C2", fmt="structured", desc="종합 특허 분석")


# ═══════════════════════════════════════════════════════════════
# 11. competitive_intel (~60건)
# ═══════════════════════════════════════════════════════════════

ci_templates = [
    "{c1}과 {c2}의 디스플레이 기술 경쟁 현황을 분석해줘",
    "{c1}의 {topic} 전략을 분석해줘",
    "{topic} 시장에서 주요 기업별 기술 현황을 비교해줘",
    "{c1}, {c2}, {c3}의 기술 우위를 비교 분석해줘",
    "{c1}의 최근 기술 동향을 분석해줘",
]

for tmpl in ci_templates:
    for _ in range(10):
        cs = random.sample(COMPANIES, 3)
        _, topic = pick_topic()
        q = tmpl.format(c1=cs[0], c2=cs[1], c3=cs[2], topic=topic)
        add("competitive_intel", "intent_check", q, keywords=cs[0],
            desc="경쟁사 분석")

# answer_quality
for _ in range(6):
    cs = random.sample(COMPANIES, 2)
    _, topic = pick_topic()
    q = f"{cs[0]}와 {cs[1]}의 {topic} 기술 경쟁 현황을 위협, 기회, 협력 가능성과 함께 분석해줘"
    add("competitive_intel", "answer_quality", q, keywords="위협,기회",
        difficulty="C2", fmt="structured", desc="SWOT 분석")


# ═══════════════════════════════════════════════════════════════
# 12. report_drafter (~50건)
# ═══════════════════════════════════════════════════════════════

rd_templates = [
    "{topic} 기술 동향 보고서 초안을 작성해줘",
    "{topic}에 대한 경영진 발표 자료를 작성해줘",
    "{topic} 기술 현황 요약 보고서를 작성해줘",
    "{domain} 분야 연구 성과 보고서 초안을 작성해줘",
    "{topic} 관련 기술 동향 브리핑 자료를 작성해줘",
]

for tmpl in rd_templates:
    for _ in range(8):
        d, topic = pick_topic()
        q = tmpl.format(topic=topic, domain=d)
        add("report_drafter", "intent_check", q, keywords="보고서",
            fmt="report", desc="보고서 작성 요청")

# answer_quality
for _ in range(6):
    _, topic = pick_topic()
    q = f"{topic} 기술 현황, 주요 성과, 과제, 향후 전략을 포함한 경영진 보고서를 작성해줘"
    add("report_drafter", "answer_quality", q, keywords="보고서,전략",
        difficulty="C2", fmt="report", desc="경영진 보고서 품질")


# ═══════════════════════════════════════════════════════════════
# 13. peer_review (~50건)
# ═══════════════════════════════════════════════════════════════

pr_templates = [
    "{title} 논문을 리뷰해줘",
    "{topic} 관련 논문에 대한 전문가 리뷰를 해줘",
    "{topic} 연구에 대한 비판적 리뷰를 작성해줘",
    "{topic} 논문의 강점과 약점을 평가해줘",
    "{topic} 연구에 대한 피드백을 해줘",
]

for tmpl in pr_templates:
    for _ in range(7):
        _, topic = pick_topic()
        title = random.choice(PAPER_TITLES)
        q = tmpl.format(topic=topic, title=title)
        add("peer_review", "intent_check", q, keywords="리뷰",
            desc="피어리뷰 요청")

# answer_quality
for title in random.sample(PAPER_TITLES, 5):
    q = f"{title} 논문에 대해 기술적 전문가, 도메인 전문가, 실무자 3인의 리뷰를 작성해줘"
    add("peer_review", "answer_quality", q, keywords="리뷰,강점,약점",
        difficulty="C2", fmt="structured", desc="3인 리뷰어 구조")

for _ in range(5):
    _, topic = pick_topic()
    q = f"{topic} 최신 연구에 대한 비판적 리뷰를 점수(1~10)와 개선 제안 포함하여 작성해줘"
    add("peer_review", "answer_quality", q, keywords="리뷰,점수,개선",
        difficulty="C3", fmt="structured", desc="정량적 리뷰")


# ═══════════════════════════════════════════════════════════════
# 14. knowledge_connector (~50건)
# ═══════════════════════════════════════════════════════════════

kc_templates = [
    "{topic} 분야 전문가를 추천해줘",
    "{topic} 분야에서 협력할 수 있는 연구팀을 추천해줘",
    "{topic} 저자 네트워크를 분석해줘",
    "{topic} 분야 핵심 연구자는 누구야?",
    "{topic} 관련 전문가를 매칭해줘",
    "{topic} 연구 그룹 간 협력 관계를 분석해줘",
]

for tmpl in kc_templates:
    for _ in range(6):
        _, topic = pick_topic()
        q = tmpl.format(topic=topic)
        add("knowledge_connector", "intent_check", q, keywords="전문가,추천",
            desc="전문가 매칭")

# answer_quality
for _ in range(6):
    _, topic = pick_topic()
    q = f"{topic} 분야 상위 5명 전문가를 논문 수, 소속, 전문 분야, 협력 전략과 함께 추천해줘"
    add("knowledge_connector", "answer_quality", q, keywords="전문가,소속,협력",
        difficulty="C2", fmt="structured", desc="전문가 상세 추천")


# ═══════════════════════════════════════════════════════════════
# 15. 경계 테스트 — 분류 혼동 질문 (~50건)
# ═══════════════════════════════════════════════════════════════

# paper_qa vs literature_survey 경계
boundary_pqa_ls = [
    ("paper_qa", "OLED 소재 효율에 대해 알려줘", "짧은 기술 질문"),
    ("literature_survey", "OLED 소재 연구의 최근 동향을 종합적으로 정리해줘", "종합 정리"),
    ("paper_qa", "양자점의 코어쉘 구조란?", "개념 질문"),
    ("literature_survey", "양자점 디스플레이 기술 서베이를 작성해줘", "서베이 요청"),
    ("paper_qa", "IGZO TFT의 특성은?", "특성 질문"),
    ("literature_survey", "산화물 TFT 연구 전반을 리뷰해줘", "전반 리뷰"),
]

# analytics vs paper_qa 경계
boundary_ana_pqa = [
    ("analytics", "OLED 관련 논문 목록을 보여줘", "목록 요청"),
    ("paper_qa", "OLED 관련 논문에서 어떤 기술을 다루는지 알려줘", "기술 내용 질문"),
    ("analytics", "Micro LED 논문이 몇 편이야?", "편수 질문"),
    ("paper_qa", "Micro LED 논문에서 어떤 방법을 쓰는지 알려줘", "방법론 질문"),
    ("analytics", "2024년 논문 제목 보여줘", "제목 목록"),
    ("paper_qa", "2024년 논문에서 주로 다루는 주제는?", "주제 분석"),
]

# trend_analyzer vs literature_survey 경계
boundary_ta_ls = [
    ("trend_analyzer", "Micro LED 기술 트렌드를 분석해줘", "트렌드 분석"),
    ("literature_survey", "Micro LED 기술 연구 현황을 정리해줘", "연구 현황 정리"),
    ("trend_analyzer", "OLED 기술 발전 타임라인을 정리해줘", "타임라인"),
    ("literature_survey", "OLED 기술 관련 문헌을 종합 리뷰해줘", "문헌 리뷰"),
]

# paper_deep_dive vs paper_qa 경계
boundary_dd_pqa = [
    ("paper_deep_dive", "10.1002/jsid.1284 논문 분석해줘", "DOI → deep_dive"),
    ("paper_qa", "Micro LED 검사 관련 논문 내용 알려줘", "일반 기술 질문"),
    ("paper_deep_dive", "Holographic grating-based optical element 논문 심층 분석해줘", "제목 → deep_dive"),
    ("paper_qa", "holographic grating 기술에 대해 알려줘", "기술 일반 질문"),
]

# competitive_intel vs trend_analyzer 경계
boundary_ci_ta = [
    ("competitive_intel", "Samsung Display와 BOE의 기술 경쟁 현황", "회사+경쟁"),
    ("trend_analyzer", "대형 디스플레이 기술 발전 트렌드", "기술 트렌드"),
    ("competitive_intel", "LG Display의 OLED TV 전략 분석", "회사 전략"),
    ("trend_analyzer", "OLED TV 기술 진화 트렌드를 분석해줘", "기술 진화"),
]

# peer_review vs paper_qa 경계
boundary_pr_pqa = [
    ("peer_review", "이 논문의 방법론에 문제점이 있는지 리뷰해줘", "리뷰/문제점"),
    ("paper_qa", "이 논문의 방법론을 설명해줘", "방법론 설명"),
    ("peer_review", "OLED 효율 연구에 대한 전문가 피드백을 해줘", "피드백 요청"),
    ("paper_qa", "OLED 효율 연구 결과를 알려줘", "연구 결과 질문"),
]

# material_advisor vs paper_qa 경계
boundary_ma_pqa = [
    ("material_advisor", "InP vs CdSe 양자점 소재를 비교해줘", "소재 비교"),
    ("paper_qa", "InP 양자점의 발광 원리는?", "원리 질문"),
    ("material_advisor", "OLED HTL 소재 후보를 비교 추천해줘", "소재 추천"),
    ("paper_qa", "HTL 소재가 OLED 효율에 미치는 영향은?", "영향 질문"),
]

# experiment_planner vs paper_qa 경계
boundary_ep_pqa = [
    ("experiment_planner", "Micro LED 전사 수율 향상 실험을 설계해줘", "실험 설계"),
    ("paper_qa", "Micro LED 전사 수율을 높이는 방법은?", "방법 질문"),
    ("experiment_planner", "OLED 봉지 신뢰성 평가 실험 계획을 세워줘", "실험 계획"),
    ("paper_qa", "OLED 봉지 신뢰성 평가 방법은?", "평가 방법 질문"),
]

# knowledge_connector vs paper_qa 경계
boundary_kc_pqa = [
    ("knowledge_connector", "foveated rendering 전문가 네트워크를 분석해줘", "전문가 네트워크"),
    ("paper_qa", "foveated rendering의 원리를 알려줘", "기술 질문"),
    ("knowledge_connector", "Micro LED 연구 핵심 저자를 추천해줘", "저자 추천"),
    ("paper_qa", "Micro LED 연구에서 어떤 결과가 나왔어?", "연구 결과"),
]

all_boundaries = (
    boundary_pqa_ls + boundary_ana_pqa + boundary_ta_ls + boundary_dd_pqa +
    boundary_ci_ta + boundary_pr_pqa + boundary_ma_pqa + boundary_ep_pqa +
    boundary_kc_pqa
)

for agent, query, desc in all_boundaries:
    add(agent, "intent_check", query, desc=f"경계: {desc}")


# ═══════════════════════════════════════════════════════════════
# INSERT
# ═══════════════════════════════════════════════════════════════

insert_sql = """
INSERT INTO agent_test_suite
(agent_type, test_category, difficulty, query_text, conversation_history,
 expected_keywords, expected_format, check_criteria, description)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

for t in ALL_TESTS:
    cursor.execute(insert_sql, (
        t["agent_type"], t["test_category"], t["difficulty"],
        t["query_text"], t["conversation_history"],
        t["expected_keywords"], t["expected_format"],
        t["check_criteria"], t["description"],
    ))

conn.commit()
print(f"\n테스트 데이터 {len(ALL_TESTS)}건 삽입 완료")

# 에이전트별 요약
cursor.execute("""
    SELECT agent_type, COUNT(*) cnt
    FROM agent_test_suite
    GROUP BY agent_type
    ORDER BY cnt DESC
""")
print(f"\n{'에이전트':<25s} {'건수':>5s}")
print("-" * 32)
for row in cursor.fetchall():
    print(f"{row[0]:<25s} {row[1]:>5d}")

# 카테고리별 요약
cursor.execute("""
    SELECT test_category, COUNT(*) cnt
    FROM agent_test_suite
    GROUP BY test_category
    ORDER BY cnt DESC
""")
print(f"\n{'카테고리':<20s} {'건수':>5s}")
print("-" * 27)
for row in cursor.fetchall():
    print(f"{row[0]:<20s} {row[1]:>5d}")

cursor.execute("SELECT COUNT(*) FROM agent_test_suite")
total = cursor.fetchone()[0]
print(f"\n총 {total}건")

cursor.close()
conn.close()
