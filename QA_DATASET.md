# Co-Scientist Q&A Dataset Documentation

## 1. 개요

### 목적
Co-Scientist Agent 시스템의 다양한 사용자 유형별 예상 질문과 답변 구조를 체계적으로 정의하여:
- Agent 기능 요구사항 명확화
- 날짜 인식(Date Parsing) 기능 개발의 테스트 데이터 확보
- 사용자 시나리오 기반 품질 검증 기준 마련

### 규모
- **총 1,080건** Q&A 데이터
- **389건** 날짜 파싱 테스트 케이스
- MariaDB `paper.qa_dataset`, `paper.date_parse_testcases` 테이블에 저장

---

## 2. 카테고리 분류 체계

### 2.1 사용자 역할 (R1~R8)

| 코드 | 역할 | 건수 | 주요 사용 Agent |
|------|------|------|----------------|
| R1 | R&D 연구자 (Display) | 200 | paper_qa, literature_survey, idea_generator, trend_analyzer |
| R2 | 소프트웨어 개발자 | 100 | paper_qa, trend_analyzer, cross_domain |
| R3 | 설비 엔지니어 | 120 | paper_qa, material_advisor, experiment_planner |
| R4 | 재료 엔지니어 | 160 | material_advisor, literature_survey, idea_generator |
| R5 | 공정 엔지니어 | 140 | experiment_planner, material_advisor, paper_qa |
| R6 | 특허/IP 담당자 | 100 | patent_landscaper, competitive_intel, paper_qa |
| R7 | 경영/전략 기획 | 120 | competitive_intel, trend_analyzer, report_drafter |
| R8 | 품질/신뢰성 엔지니어 | 140 | experiment_planner, material_advisor, peer_review |

### 2.2 Agent 유형 (13개)

| Phase | Agent | 설명 | 건수 |
|-------|-------|------|------|
| Phase 1 | paper_qa | 논문 검색 및 질의응답 | 191 |
| Phase 1 | literature_survey | 문헌 리뷰 자동 생성 | 127 |
| Phase 1 | paper_deep_dive | 특정 논문 심층 분석 | 29 |
| Phase 2 | idea_generator | 연구 아이디어 제안 | 56 |
| Phase 2 | cross_domain | 타 분야 기술 적용 제안 | 74 |
| Phase 2 | trend_analyzer | 기술 트렌드 분석 | 135 |
| Phase 3 | experiment_planner | 실험 설계 제안 | 102 |
| Phase 3 | patent_landscaper | 특허 동향 분석 | 87 |
| Phase 3 | competitive_intel | 경쟁사 동향 분석 | 40 |
| Phase 3 | material_advisor | 재료/공정 비교 분석 | 103 |
| Phase 4 | report_drafter | 보고서 초안 작성 | 68 |
| Phase 4 | peer_review | 논문 가상 리뷰 | 28 |
| Phase 4 | knowledge_connector | 전문가 매칭 | 40 |

### 2.3 난이도 (C1~C3)

| 코드 | 수준 | 설명 | 건수 |
|------|------|------|------|
| C1 | Simple | 단일 의도, 직접 답변 (100~300자) | 74 |
| C2 | Medium | 복수 필터, 2~3편 종합 (300~1000자) | 786 |
| C3 | Complex | 다단계 추론, 비교 분석 (1000자+) | 220 |

### 2.4 날짜 유형 (D0~D4)

| 코드 | 유형 | 설명 | 건수 | 비율 |
|------|------|------|------|------|
| D0 | 없음 | 날짜 표현 없음 | 691 | 64% |
| D1 | 절대(특정) | "2024년 11월" | 93 | 9% |
| D2 | 절대(범위) | "2023년 3분기", "2022~2024년" | 88 | 8% |
| D3 | 상대 | "최근 6개월", "작년", "올해 초" | 163 | 15% |
| D4 | 비교 | "2022년 대비 2024년 변화" | 45 | 4% |

---

## 3. 분포 통계

### 3.1 역할 × Agent 매트릭스 (상위)

각 역할은 해당 역할에 자연스러운 2~7개 Agent에 분배됨.

예시:
- R1(R&D 연구자): paper_qa, literature_survey, paper_deep_dive, idea_generator, cross_domain, trend_analyzer, report_drafter
- R3(설비 엔지니어): paper_qa, material_advisor, experiment_planner, trend_analyzer, patent_landscaper
- R6(특허/IP): patent_landscaper, competitive_intel, paper_qa, trend_analyzer, knowledge_connector

### 3.2 날짜 유형별 파싱 테스트 케이스

date_parse_testcases 테이블에 389건:
- D1 (절대 특정): ~93건
- D2 (절대 범위): ~88건
- D3 (상대): ~163건
- D4 (비교): ~45건

각 테스트 케이스는 `input_expression`, `reference_date`, `expected_from`, `expected_to`를 포함.

---

## 4. 역할별 Q&A 예시

### 4.1 R1: R&D 연구자

**Simple (C1) / 날짜 없음 (D0)**
> Q: "OLED 발광효율 관련 논문 찾아줘"
> A: 'OLED 발광효율' 키워드로 검색한 논문 목록 제공

**Medium (C2) / 상대 날짜 (D3)**
> Q: "최근 6개월간 Micro LED 전사 기술 관련 Samsung 논문 정리해줘"
> A: 상대 기간(최근 6개월) + 저자 필터(Samsung) 적용 논문 요약

**Complex (C3) / 비교 (D4)**
> Q: "2022년 대비 2024년 Blue OLED 발광재 연구 방법론이 어떻게 진화했는지 비교 분석해줘"
> A: 두 시점의 주요 방법론 비교 + 패러다임 변화 분석

### 4.2 R3: 설비 엔지니어

**Medium (C2) / 절대 날짜 (D1)**
> Q: "2024년 8월에 발표된 증착기 관련 실험 방법을 참고해서 우리 실험에 맞게 설계해줘"
> A: 특정 기간 논문의 방법론 참조 실험 설계

**Medium (C2) / 상대 날짜 (D3)**
> Q: "최근 1년간 AOI 검사장비 분야 특허 출원 동향 분석해줘"
> A: 기간 내 특허 동향 + 신규 출원 트렌드

### 4.3 R4: 재료 엔지니어

**Medium (C2) / 날짜 없음 (D0)**
> Q: "QD 색변환용 양자점 후보 재료를 비교 분석해줘"
> A: 후보 재료 비교 테이블 + 추천 순위

**Complex (C3) / 비교 (D4)**
> Q: "2020년 대비 2024년 봉지 필름 성능이 어떻게 발전했는지 분석하고 차세대 재료를 추천해줘"
> A: 재료 성능 진화 + 차세대 추천

### 4.4 R6: 특허/IP 담당자

**Medium (C2) / 절대 범위 (D2)**
> Q: "2023년 상반기 Micro LED 전사기술 분야 특허 출원 추이 분석해줘"
> A: 기간 내 특허 트렌드

**Complex (C3) / 비교 (D4)**
> Q: "2021년 대비 2024년 OLED 봉지 분야 특허 landscape가 어떻게 변했는지 분석하고 IP 전략 제안해줘"
> A: 특허 맵 변화 + FTO 분석 + 전략 제안

### 4.5 R7: 경영/전략 기획

**Medium (C2) / 상대 날짜 (D3)**
> Q: "최근 3년간 BOE의 Micro LED 관련 연구 활동을 모니터링해줘"
> A: 기간 내 경쟁사 활동 브리핑

**Complex (C3) / 비교 (D4)**
> Q: "2020년과 2024년 비교 QD-OLED 분야에서 주요 플레이어들의 전략 변화를 분석하고 우리의 대응 방향을 제안해줘"
> A: 경쟁 환경 변화 + 위협/기회 + 액션 플랜

---

## 5. 날짜 표현 레퍼런스

### 5.1 절대 날짜 (D1) — 특정 연월

| 패턴 | 예시 | 파싱 결과 |
|------|------|----------|
| `{YYYY}년 {M}월` | "2024년 11월" | from=20241101, to=20241130 |
| `{YYYY}년 {MM}월` | "2024년 03월" | from=20240301, to=20240331 |

### 5.2 절대 범위 (D2) — 기간

| 패턴 | 예시 | 파싱 결과 |
|------|------|----------|
| `{YYYY}년 {Q}분기` | "2023년 3분기" | from=20230701, to=20230930 |
| `{YYYY}년 상반기` | "2024년 상반기" | from=20240101, to=20240630 |
| `{YYYY}년 하반기` | "2024년 하반기" | from=20240701, to=20241231 |
| `{YYYY}~{YYYY}년` | "2022~2024년" | from=20220101, to=20241231 |
| `{YYYY}년` (단독) | "2023년" | from=20230101, to=20231231 |

### 5.3 상대 날짜 (D3) — 기준일 필요

기준일: 2026-03-20 기준

| 패턴 | 예시 | 파싱 결과 |
|------|------|----------|
| `최근 {N}개월` | "최근 6개월" | from=20250920, to=20260320 |
| `최근 {N}년` | "최근 3년" | from=20230320, to=20260320 |
| `작년 / 지난해` | "작년" | from=20250101, to=20251231 |
| `올해 / 금년` | "올해" | from=20260101, to=20260320 |
| `지난달 / 전월` | "지난달" | from=20260201, to=20260228 |
| `올해 초` | "올해 초" | from=20260101, to=20260331 |
| `작년 여름` | "작년 여름" | from=20250601, to=20250831 |
| `작년 겨울` | "작년 겨울" | from=20251201, to=20260228 |

### 5.4 비교 날짜 (D4)

| 패턴 | 예시 | 파싱 결과 |
|------|------|----------|
| `{Y1}년 대비 {Y2}년` | "2022년 대비 2024년" | from=20220101, to=20241231 |
| `{Y1}년과 {Y2}년 비교` | "2020년과 2023년 비교" | from=20200101, to=20231231 |
| `{Y1}~{Y2}년 변화` | "2021~2025년 변화" | from=20210101, to=20251231 |

> **Note**: D4 비교 쿼리는 두 시점을 별도 검색하여 비교해야 하므로, Agent에서 두 번의 검색이 필요할 수 있음.

---

## 6. MariaDB 스키마

### 6.1 qa_dataset 테이블

```sql
-- 전체 데이터 조회
SELECT * FROM qa_dataset LIMIT 10;

-- 역할별 분포
SELECT user_role, user_role_name, COUNT(*) as cnt
FROM qa_dataset GROUP BY user_role, user_role_name ORDER BY user_role;

-- Agent별 분포
SELECT agent_type, COUNT(*) as cnt
FROM qa_dataset GROUP BY agent_type ORDER BY cnt DESC;

-- 날짜 유형별 분포
SELECT date_type, COUNT(*) as cnt
FROM qa_dataset GROUP BY date_type ORDER BY date_type;

-- 특정 역할 + Agent 조합 조회
SELECT query_text, expected_answer, date_type, date_expression
FROM qa_dataset
WHERE user_role = 'R1' AND agent_type = 'paper_qa'
ORDER BY complexity, date_type;

-- 날짜 표현이 있는 쿼리만 조회
SELECT query_text, date_expression, parsed_from, parsed_to, date_type
FROM qa_dataset
WHERE date_type != 'D0'
ORDER BY date_type, parsed_from;
```

### 6.2 date_parse_testcases 테이블

```sql
-- 날짜 파싱 테스트 케이스 전체
SELECT t.input_expression, t.date_type, t.reference_date,
       t.expected_from, t.expected_to, q.query_text
FROM date_parse_testcases t
JOIN qa_dataset q ON t.qa_id = q.qa_id
ORDER BY t.date_type, t.expected_from;

-- 유형별 테스트 케이스 수
SELECT date_type, COUNT(*) FROM date_parse_testcases GROUP BY date_type;
```

### 6.3 expected_filters JSON 형식

```json
{
  "coverdate_from": 20240101,
  "coverdate_to": 20241231,
  "author": "Samsung",
  "keywords": "OLED blue emitter"
}
```

---

## 7. 향후 Agent 개선 방향

### 7.1 날짜 파서 (Date Parser) 통합 — 최우선

**문제점**: 현재 Agent는 "2024년 11월 논문 알려줘"에서 날짜를 추출하지 못함.

**해결**: `supervisor.py`의 `classify_intent()` → `route_to_agent()` 사이에 `extract_date_filters()` 함수 삽입

```python
# 기존 흐름
classify_intent → route_to_agent

# 개선 흐름
classify_intent → extract_date_filters → route_to_agent
```

**통합 지점**:
- `D:\work\vscode\0313_paper_01\app\agents\supervisor.py` — 새 노드 추가
- `D:\work\vscode\0313_paper_01\app\agents\common.py` — `_build_filter_expr()` 변경 불필요 (이미 coverdate_from/to 지원)

### 7.2 D4 비교 쿼리 지원

trend_analyzer, competitive_intel에서 두 시점 별도 검색 후 비교 로직 추가 필요.

### 7.3 자연어 필터 확장

날짜 외에도:
- "Samsung 논문" → `author` 필터
- "Micro LED 관련" → `keywords` 필터
- 이런 자연어 필터 추출을 LLM 기반으로 통합 가능

---

## 부록: 도메인 어휘

### 기술 분야
OLED, Micro LED, QD (양자점), LCD, TFT, 봉지, 공정, 장비

### 주요 키워드 (예시)
발광효율, 수명 개선, Blue 발광재, TADF 소재, 전사 기술, Mass Transfer, 레이저 리프트오프, 양자점 합성, QD-OLED, 미니 LED 백라이트, LTPO TFT, IGZO, 수분투과율(WVTR), TFE, 잉크젯 프린팅, ALD 박막

### 주요 기관/기업
Samsung, LG Display, BOE, TCL CSOT, Applied Materials, Canon Tokki, Universal Display, Merck, 서울대, KAIST, 포항공대
