"""폐쇄망 테스트용 agent_test_suite 테이블 생성 및 데이터 적재.

14개 에이전트 × 다양한 시나리오 = 체계적 검증 데이터셋.
기존 qa_dataset(2,080건)과 별도로, 에이전트별 핵심 기능 검증에 초점.

검증 관점:
- intent_check: LLM이 올바른 에이전트로 분류하는지
- answer_quality: 답변 품질 (길이, 구조, 키워드 포함)
- date_filter: 날짜 필터가 올바르게 적용되는지
- multi_turn: 멀티턴 대화에서 문맥 유지
- edge_case: 엣지케이스 처리
"""
import os
import sys
import json
import pymysql
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    check_criteria  JSON          DEFAULT NULL COMMENT '검증 기준 {min_len, must_contain, agent_type 등}',
    description     VARCHAR(200)  DEFAULT NULL COMMENT '테스트 설명',
    is_active       TINYINT       DEFAULT 1,
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_agent (agent_type),
    INDEX idx_category (test_category),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""")
print("agent_test_suite 테이블 생성 완료")

# ── 테스트 데이터 ────────────────────────────────────────────

TESTS = []


def add(agent, category, query, difficulty="C1", keywords=None, fmt="text",
        criteria=None, desc=None, history=None):
    TESTS.append({
        "agent_type": agent,
        "test_category": category,
        "difficulty": difficulty,
        "query_text": query,
        "conversation_history": json.dumps(history, ensure_ascii=False) if history else None,
        "expected_keywords": keywords,
        "expected_format": fmt,
        "check_criteria": json.dumps(criteria, ensure_ascii=False) if criteria else None,
        "description": desc,
    })


# ═══════════════════════════════════════════════════════════════
# PHASE 1: 기본 지식 검색
# ═══════════════════════════════════════════════════════════════

# ── analytics ──
add("analytics", "intent_check", "전체 논문 몇 편이야?",
    keywords="편", desc="전체 편수 질문 → analytics 분류")
add("analytics", "intent_check", "2024년 10월 발표된 논문 편수와 제목을 보여줘",
    keywords="편,제목", fmt="table", desc="편수+목록 질문")
add("analytics", "intent_check", "연도별 논문 편수 추이를 보여줘",
    keywords="추이,편", desc="추이 집계")
add("analytics", "intent_check", "월별 Micro LED 논문 현황 알려줘",
    keywords="Micro LED,월별", desc="키워드+월별 집계")
add("analytics", "intent_check", "volume 64 issue 1 논문 목록",
    keywords="volume,issue", fmt="table", desc="volume/issue 필터")
add("analytics", "date_filter", "2024년 하반기 논문 편수는?",
    keywords="편", criteria={"coverdate_from": 20240701, "coverdate_to": 20241231},
    desc="D2 날짜 필터 적용")
add("analytics", "date_filter", "최근 6개월 논문 편수 알려줘",
    keywords="편", desc="D3 상대 날짜 필터")
add("analytics", "date_filter", "2023년 대비 2024년 논문 편수 비교",
    keywords="편,비교", desc="D4 비교 날짜")
add("analytics", "answer_quality", "2024년 12월 논문 목록 보여줘",
    keywords="제목", fmt="table", difficulty="C2",
    desc="특정 월 논문 목록 상세 표시")
add("analytics", "answer_quality", "holographic 관련 논문 있어?",
    keywords="holographic", desc="키워드 검색")
add("analytics", "edge_case", "2010년 논문 있어?",
    desc="데이터 없는 연도 → 빈 결과 처리")
add("analytics", "edge_case", "작성자별 논문 편수 상위 10명",
    keywords="저자,편", difficulty="C3", desc="저자별 집계 (복잡)")

# ── paper_qa ──
add("paper_qa", "intent_check", "Micro LED 결함 검출 방법에 대해 알려줘",
    keywords="Micro LED,검출", desc="기술 질문 → paper_qa")
add("paper_qa", "intent_check", "foveated rendering이란 무엇인가?",
    keywords="foveated,rendering", desc="개념 질문")
add("paper_qa", "intent_check", "OLED 발광 효율을 높이는 방법은?",
    keywords="OLED,효율", desc="방법론 질문")
add("paper_qa", "answer_quality", "양자점 디스플레이의 장단점을 설명해줘",
    keywords="양자점,장점,단점", difficulty="C2", desc="장단점 비교 답변 구조")
add("paper_qa", "answer_quality", "TFT 소자에서 이동도가 중요한 이유는?",
    keywords="이동도,TFT", desc="원리 설명")
add("paper_qa", "answer_quality",
    "Subjective assessment of visual fidelity 논문을 요약해줘",
    keywords="요약", desc="특정 논문 제목 기반 검색")
add("paper_qa", "answer_quality",
    "High-speed and contactless inspection of defective micro-LEDs 논문의 핵심 기여는?",
    keywords="핵심,기여", desc="특정 논문 핵심 기여")
add("paper_qa", "date_filter", "최근 1년간 OLED 봉지 기술 연구 내용을 알려줘",
    keywords="봉지,OLED", desc="날짜 필터 + 기술 질문")
add("paper_qa", "edge_case", "존재하지 않는 XYZ123 기술에 대해 알려줘",
    desc="검색 결과 없을 때 graceful 처리")
add("paper_qa", "multi_turn", "이 논문의 실험 방법을 더 자세히 설명해줘",
    history=[
        {"role": "user", "content": "Micro LED 결함 검출 방법에 대해 알려줘"},
        {"role": "assistant", "content": "Micro LED 결함 검출에는 여러 방법이 있습니다..."}
    ],
    desc="멀티턴: 이전 질문 맥락 유지")
add("paper_qa", "multi_turn", "1번째 논문을 자세히 설명해줘",
    history=[
        {"role": "user", "content": "OLED 효율 연구 알려줘"},
        {"role": "assistant", "content": "관련 논문을 찾았습니다. 1) Paper A... 2) Paper B..."}
    ],
    desc="멀티턴: N번째 논문 참조")

# ── literature_survey ──
add("literature_survey", "intent_check", "디스플레이 기술의 최근 연구 동향을 정리해줘",
    keywords="동향,연구", desc="서베이 요청 → literature_survey")
add("literature_survey", "intent_check", "Micro LED 전사 기술 문헌 리뷰를 작성해줘",
    keywords="리뷰,전사", desc="문헌 리뷰 명시 요청")
add("literature_survey", "answer_quality", "OLED 소재 연구 동향을 종합적으로 정리해줘",
    keywords="소재,OLED", difficulty="C2", fmt="structured",
    desc="구조화된 리뷰 답변 품질")
add("literature_survey", "answer_quality", "플렉서블 디스플레이 기술 현황과 과제를 서베이해줘",
    keywords="플렉서블,과제", difficulty="C3", fmt="structured",
    desc="고복잡도 서베이")
add("literature_survey", "date_filter", "2024년 하반기 양자점 연구 동향 정리해줘",
    keywords="양자점", desc="날짜 필터 + 서베이")

# ── paper_deep_dive ──
add("paper_deep_dive", "intent_check",
    "DOI 10.1002/jsid.1284 논문을 심층 분석해줘",
    keywords="분석", desc="DOI 포함 → paper_deep_dive")
add("paper_deep_dive", "intent_check",
    "Wide-viewing-angle dual-view integral imaging display 논문을 심층 분석해줘",
    keywords="분석", desc="논문 제목 지정 심층 분석")
add("paper_deep_dive", "answer_quality",
    "10.1002/jsid.1284 논문의 방법론, 강점, 한계를 상세히 분석해줘",
    keywords="방법론,강점,한계", difficulty="C2", fmt="structured",
    desc="8-point 분석 품질 확인")
add("paper_deep_dive", "edge_case",
    "DOI 10.9999/fake.0001 논문을 분석해줘",
    desc="존재하지 않는 DOI 처리")

# ═══════════════════════════════════════════════════════════════
# PHASE 2: 아이디어 생성 & 트렌드
# ═══════════════════════════════════════════════════════════════

# ── idea_generator ──
add("idea_generator", "intent_check",
    "Micro LED와 holographic grating을 결합한 새로운 연구 아이디어를 제안해줘",
    keywords="아이디어", desc="아이디어 제안 → idea_generator")
add("idea_generator", "intent_check",
    "OLED와 양자점 융합 연구 주제를 브레인스토밍해줘",
    keywords="브레인스토밍", desc="브레인스토밍 키워드")
add("idea_generator", "answer_quality",
    "플렉서블 디스플레이와 웨어러블 기기의 융합 아이디어 3가지를 제안해줘",
    keywords="아이디어,플렉서블,웨어러블", difficulty="C2", fmt="structured",
    criteria={"min_ideas": 3}, desc="구조화된 아이디어 3개 이상")
add("idea_generator", "answer_quality",
    "TFT 공정 단순화를 위한 혁신적 연구 아이디어를 제안해줘",
    keywords="TFT,공정", difficulty="C3", desc="실현가능성 포함 아이디어")

# ── cross_domain ──
add("cross_domain", "intent_check",
    "의료 영상 기술을 디스플레이 분야에 적용할 수 있는 방법은?",
    keywords="의료,디스플레이", desc="타분야 적용 → cross_domain")
add("cross_domain", "intent_check",
    "반도체 공정 기술을 Micro LED 제조에 활용하는 방안",
    keywords="반도체,Micro LED", desc="타분야 기술 전이")
add("cross_domain", "answer_quality",
    "자동차 센서 기술을 디스플레이 검사에 적용할 방법을 제안해줘",
    keywords="자동차,센서,검사", difficulty="C2", desc="구체적 적용 방안")

# ── trend_analyzer ──
add("trend_analyzer", "intent_check",
    "Micro LED 기술의 발전 트렌드를 분석해줘",
    keywords="트렌드,Micro LED", desc="트렌드 분석 → trend_analyzer")
add("trend_analyzer", "intent_check",
    "디스플레이 기술 발전 타임라인을 정리해줘",
    keywords="타임라인", desc="타임라인 키워드")
add("trend_analyzer", "answer_quality",
    "OLED vs Micro LED 기술 트렌드를 비교 분석해줘",
    keywords="OLED,Micro LED,비교", difficulty="C2", fmt="structured",
    desc="기술 비교 트렌드 답변 품질")
add("trend_analyzer", "date_filter",
    "2023~2024년 QD 기술 트렌드 변화를 분석해줘",
    keywords="QD,트렌드", desc="날짜 범위 + 트렌드")

# ═══════════════════════════════════════════════════════════════
# PHASE 3: 실용 응용
# ═══════════════════════════════════════════════════════════════

# ── experiment_planner ──
add("experiment_planner", "intent_check",
    "OLED 발광층 효율 개선을 위한 실험 설계를 제안해줘",
    keywords="실험,OLED", desc="실험 설계 → experiment_planner")
add("experiment_planner", "answer_quality",
    "Micro LED 전사 수율 향상을 위한 DOE 실험 설계를 해줘",
    keywords="DOE,전사,수율", difficulty="C2", fmt="structured",
    desc="DOE 설계 구조 확인")
add("experiment_planner", "answer_quality",
    "양자점 합성 조건 최적화 실험 방법을 제안해줘",
    keywords="양자점,합성,최적화", difficulty="C3", desc="복잡한 실험 설계")

# ── material_advisor ──
add("material_advisor", "intent_check",
    "Micro LED용 발광 소재를 비교 분석해줘",
    keywords="소재,비교", desc="재료 비교 → material_advisor")
add("material_advisor", "answer_quality",
    "OLED 정공수송층(HTL) 소재 후보를 비교하고 추천해줘",
    keywords="HTL,정공수송층,추천", difficulty="C2", fmt="table",
    desc="소재 비교표 + 추천")
add("material_advisor", "answer_quality",
    "TFE 봉지 재료의 수분투과율, 비용, 공정성을 비교해줘",
    keywords="TFE,봉지,수분투과율", difficulty="C3", fmt="table",
    desc="다차원 비교 분석")

# ── patent_landscaper ──
add("patent_landscaper", "intent_check",
    "홀로그래픽 디스플레이 관련 특허 동향을 분석해줘",
    keywords="특허,홀로그래픽", desc="특허 분석 → patent_landscaper")
add("patent_landscaper", "answer_quality",
    "Micro LED 전사 기술 특허 현황과 공백 영역을 분석해줘",
    keywords="특허,전사,공백", difficulty="C2", fmt="structured",
    desc="특허 공백 식별")

# ── competitive_intel ──
add("competitive_intel", "intent_check",
    "삼성과 LG의 디스플레이 기술 경쟁 현황을 분석해줘",
    keywords="삼성,LG,경쟁", desc="경쟁사 분석 → competitive_intel")
add("competitive_intel", "answer_quality",
    "BOE와 TCL CSOT의 대형 디스플레이 전략을 비교해줘",
    keywords="BOE,TCL,전략", difficulty="C2", fmt="structured",
    desc="경쟁사 전략 비교")
add("competitive_intel", "answer_quality",
    "Micro LED 시장에서 주요 기업별 기술 우위를 분석해줘",
    keywords="Micro LED,기업,우위", difficulty="C3",
    desc="복합 경쟁 분석")

# ═══════════════════════════════════════════════════════════════
# PHASE 4: 커뮤니케이션 & 지식 합성
# ═══════════════════════════════════════════════════════════════

# ── report_drafter ──
add("report_drafter", "intent_check",
    "2024년 디스플레이 기술 동향 보고서 초안을 작성해줘",
    keywords="보고서,2024", desc="보고서 작성 → report_drafter")
add("report_drafter", "answer_quality",
    "Micro LED 기술 현황과 전망에 대한 경영진 발표 자료를 작성해줘",
    keywords="Micro LED,발표,전망", difficulty="C2", fmt="report",
    desc="발표 자료 형식")
add("report_drafter", "answer_quality",
    "OLED vs Micro LED 기술 비교 요약 보고서를 작성해줘",
    keywords="OLED,Micro LED,비교", difficulty="C3", fmt="report",
    desc="비교 보고서")

# ── peer_review ──
add("peer_review", "intent_check",
    "Wide-viewing-angle dual-view integral imaging display 논문을 리뷰해줘",
    keywords="리뷰", desc="피어 리뷰 → peer_review")
add("peer_review", "answer_quality",
    "Micro LED 검사 기술 논문에 대한 전문가 리뷰를 해줘",
    keywords="리뷰,강점,약점", difficulty="C2", fmt="structured",
    desc="3인 리뷰어 구조")
add("peer_review", "answer_quality",
    "OLED 발광 효율 관련 최신 연구에 대한 비판적 리뷰를 작성해줘",
    keywords="비판,리뷰,개선", difficulty="C3", fmt="structured",
    desc="비판적 리뷰 품질")

# ── knowledge_connector ──
add("knowledge_connector", "intent_check",
    "foveated rendering 분야 전문가를 추천해줘",
    keywords="전문가,추천", desc="전문가 매칭 → knowledge_connector")
add("knowledge_connector", "answer_quality",
    "Micro LED 전사 기술 분야에서 협력할 수 있는 연구팀을 추천해줘",
    keywords="연구팀,협력,추천", difficulty="C2", fmt="structured",
    desc="연구팀 추천 + 협력 전략")
add("knowledge_connector", "answer_quality",
    "OLED 소재 연구자 네트워크를 분석하고 핵심 전문가를 매칭해줘",
    keywords="전문가,네트워크,매칭", difficulty="C3",
    desc="저자 네트워크 분석")

# ═══════════════════════════════════════════════════════════════
# 크로스 에이전트 경계 테스트 (분류가 혼동되기 쉬운 질문)
# ═══════════════════════════════════════════════════════════════

add("paper_qa", "intent_check",
    "OLED 소재 효율에 대해 알려줘",
    desc="짧은 기술 질문 → paper_qa (literature_survey 아님)")
add("literature_survey", "intent_check",
    "OLED 소재 연구의 최근 동향을 종합적으로 정리해줘",
    desc="종합 정리 → literature_survey (paper_qa 아님)")
add("analytics", "intent_check",
    "OLED 관련 논문 목록을 보여줘",
    desc="목록 요청 → analytics (paper_qa 아님)")
add("trend_analyzer", "intent_check",
    "Micro LED 기술 동향 분석해줘",
    desc="트렌드 분석 → trend_analyzer (literature_survey 아님)")
add("paper_deep_dive", "intent_check",
    "10.1002/jsid.1200 이 논문 분석해줘",
    desc="DOI 포함 → paper_deep_dive (paper_qa 아님)")
add("peer_review", "intent_check",
    "이 논문의 방법론에 문제점이 있는지 리뷰해줘",
    desc="리뷰/문제점 → peer_review (paper_qa 아님)")
add("material_advisor", "intent_check",
    "QD-LED용 InP vs CdSe 양자점 소재를 비교해줘",
    desc="소재 비교 → material_advisor (paper_qa 아님)")
add("competitive_intel", "intent_check",
    "Samsung Display와 BOE의 최근 기술 동향 비교",
    desc="회사명+비교 → competitive_intel (trend_analyzer 아님)")
add("experiment_planner", "intent_check",
    "잉크젯 프린팅 조건 최적화 실험을 설계해줘",
    desc="실험 설계 → experiment_planner (paper_qa 아님)")
add("knowledge_connector", "intent_check",
    "홀로그래픽 디스플레이 분야 전문가 네트워크를 분석해줘",
    desc="전문가 네트워크 → knowledge_connector (peer_review 아님)")

# ═══════════════════════════════════════════════════════════════
# INSERT
# ═══════════════════════════════════════════════════════════════

insert_sql = """
INSERT INTO agent_test_suite
(agent_type, test_category, difficulty, query_text, conversation_history,
 expected_keywords, expected_format, check_criteria, description)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

for t in TESTS:
    cursor.execute(insert_sql, (
        t["agent_type"], t["test_category"], t["difficulty"],
        t["query_text"], t["conversation_history"],
        t["expected_keywords"], t["expected_format"],
        t["check_criteria"], t["description"],
    ))

conn.commit()
print(f"테스트 데이터 {len(TESTS)}건 삽입 완료")

# 요약 출력
cursor.execute("""
    SELECT agent_type, test_category, COUNT(*) cnt
    FROM agent_test_suite
    GROUP BY agent_type, test_category
    ORDER BY agent_type, test_category
""")
print(f"\n{'에이전트':<25s} {'카테고리':<18s} {'건수':>4s}")
print("-" * 50)
for row in cursor.fetchall():
    print(f"{row[0]:<25s} {row[1]:<18s} {row[2]:>4d}")

cursor.execute("SELECT COUNT(*) FROM agent_test_suite")
total = cursor.fetchone()[0]
print(f"\n총 {total}건")

cursor.close()
conn.close()
