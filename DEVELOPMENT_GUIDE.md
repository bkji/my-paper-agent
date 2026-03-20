# Co-Scientist Agent 개발 가이드

초보자도 따라할 수 있도록 프로젝트 전체 구조와 개발 과정을 정리한 문서입니다.

---

## 1. 프로젝트 개요

논문 데이터를 **MariaDB**(관계형 DB)와 **Milvus**(벡터 DB)에 적재하고, 이를 기반으로 **14개 전문 에이전트**가 사용자의 질문에 답하는 Co-Scientist 시스템입니다.

**핵심 특징:**
- 한국어 자연어 날짜 표현 자동 파싱 ("작년 여름", "최근 6개월" 등)
- Milvus 벡터 검색(의미 기반) + MariaDB SQL 집계(통계/목록) 자동 선택
- 폐쇄망 서버 이전 대비 — `.env`만 변경하면 LM Studio ↔ vLLM/TEI 전환 가능
- Open WebUI 연동 지원 (`/v1/chat/completions`)

---

## 2. 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    사용자 질문 입력                           │
│  예: "작년 여름에 발표된 Micro LED 관련 논문 목록 보여줘"       │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌───────────────────────────────────────────────────────────────┐
│  Supervisor Agent (app/agents/supervisor.py)                  │
│                                                               │
│  1단계: extract_dates                                         │
│    - 서버 시간 조회 (app/core/tools.py)                        │
│    - 날짜 파싱 (app/core/date_parser.py)                      │
│    - "작년 여름" → coverdate_from=20250601, to=20250831       │
│                                                               │
│  2단계: classify_intent                                       │
│    - LLM으로 질문 의도 분류 → 14개 에이전트 중 선택             │
│                                                               │
│  3단계: route_to_agent                                        │
│    - 선택된 에이전트 동적 로드 및 실행                          │
└───────────────────────┬───────────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────┐
│  선택된 에이전트 실행                                      │
│                                                          │
│  [의미 검색이 필요한 경우] → Milvus 벡터 검색              │
│    - 질문 임베딩 → hybrid search (dense + BM25 sparse)    │
│    - coverdate 필터 자동 적용                              │
│                                                          │
│  [통계/집계가 필요한 경우] → MariaDB SQL 집계              │
│    - GROUP BY 월별/연도별/분기별                           │
│    - chunk_id=1만 카운트 (논문 단위 정확한 편수)            │
│                                                          │
│  → LLM이 검색 결과 기반으로 답변 생성                      │
│  → 시스템 프롬프트에 현재 서버 날짜 자동 주입               │
└──────────────────────────────────────────────────────────┘
```

---

## 3. 디렉토리 구조

```
claude_code/
├── .env                          # 모든 접속정보 (Git 미포함)
├── .env.example                  # 폐쇄망 이전용 템플릿
├── requirements.txt              # Python 패키지 목록
│
├── app/                          # 메인 애플리케이션
│   ├── config.py                 # 환경변수 로드 (Settings 클래스)
│   ├── main.py                   # FastAPI 앱 진입점
│   │
│   ├── core/                     # 외부 시스템 클라이언트
│   │   ├── llm.py                # LLM API (OpenAI-compatible)
│   │   ├── embeddings.py         # 임베딩 API (OpenAI-compatible)
│   │   ├── vectorstore.py        # Milvus 벡터 DB 클라이언트
│   │   ├── database.py           # MariaDB 클라이언트 (SQLAlchemy)
│   │   ├── date_parser.py        # 한국어 날짜 파서 (D1~D4)
│   │   ├── tools.py              # 서버 시간 도구
│   │   └── langfuse_client.py    # Langfuse 트레이싱
│   │
│   ├── agents/                   # 14개 전문 에이전트
│   │   ├── supervisor.py         # 의도분류 + 라우팅
│   │   ├── common.py             # 공통 헬퍼 (검색, LLM 호출)
│   │   ├── state.py              # AgentState 정의
│   │   ├── phase1/               # 문헌 분석
│   │   │   ├── paper_qa.py       #   논문 검색 & 질의응답
│   │   │   ├── literature_survey.py  # 문헌 리뷰 자동 생성
│   │   │   ├── paper_deep_dive.py    # 특정 논문 심층 분석
│   │   │   └── analytics.py     #   통계/집계/목록 (MariaDB SQL)
│   │   ├── phase2/               # 아이디어 & 트렌드
│   │   │   ├── idea_generator.py #   연구 아이디어 제안
│   │   │   ├── cross_domain.py   #   타 분야 적용 제안
│   │   │   └── trend_analyzer.py #   기술 트렌드 분석
│   │   ├── phase3/               # 실용 R&D
│   │   │   ├── experiment_planner.py # 실험 설계
│   │   │   ├── material_advisor.py   # 재료/공정 비교
│   │   │   ├── patent_landscaper.py  # 특허 동향
│   │   │   └── competitive_intel.py  # 경쟁사 분석
│   │   └── phase4/               # 지식 종합
│   │       ├── report_drafter.py #   보고서 초안 작성
│   │       ├── peer_review.py    #   가상 논문 리뷰
│   │       └── knowledge_connector.py # 전문가 매칭
│   │
│   ├── api/routes/               # API 엔드포인트
│   │   ├── chat.py               # POST /api/chat
│   │   ├── agents.py             # GET /api/agents
│   │   ├── documents.py          # POST /api/documents/ingest
│   │   └── openai_compat.py      # POST /v1/chat/completions
│   │
│   ├── models/                   # 데이터 모델
│   │   ├── db_models.py          # SQLAlchemy ORM
│   │   └── schemas.py            # Pydantic 스키마
│   │
│   └── services/                 # 비즈니스 로직
│       ├── chunker.py            # 텍스트 청킹
│       └── ingest.py             # 문서 수집 파이프라인
│
├── scripts/                      # 유틸리티 스크립트
│   ├── cli.py                    # 터미널 CLI (대화형/단일 쿼리)
│   ├── generate_qa_dataset.py    # QA 데이터셋 생성
│   └── evaluate_agents.py        # 에이전트 자동 평가
│
├── data/sample_paper.csv         # 논문 원본 데이터 (10건)
├── load_csv_to_mariadb.py        # CSV → MariaDB 적재
└── load_mariadb_to_milvus.py     # MariaDB → Milvus 적재 (임베딩)
```

---

## 4. 환경 설정

### 4-1. Python 환경

```bash
# 프로젝트 전용 WinPython
D:/WPy64-312101_paper/python/python.exe -m pip install -r requirements.txt
```

### 4-2. .env 파일 설정

`.env.example`을 `.env`로 복사 후 값을 변경합니다.

```env
# --- MariaDB ---
MARIADB_HOST=localhost
MARIADB_PORT=3306
MARIADB_USER=root
MARIADB_PASSWORD=your-password
MARIADB_DATABASE=paper

# --- Milvus ---
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_DATABASE=m_paper
MILVUS_COLLECTION=m_sid_v_09_01

# --- LLM (OpenAI-compatible API) ---
# 로컬: LM Studio → http://localhost:20020/v1
# 폐쇄망: vLLM → http://localhost:8000/v1
LLM_BASE_URL=http://localhost:20020/v1
LLM_API_KEY=lm-studio
LLM_MODEL=qwen3-0.6b

# --- Embedding (OpenAI-compatible API) ---
# 로컬: LM Studio → http://localhost:20020/v1
# 폐쇄망: TEI → http://localhost:8080/v1
EMBEDDING_BASE_URL=http://localhost:20020/v1
EMBEDDING_API_KEY=lm-studio
EMBEDDING_MODEL=text-embedding-bge-m3
EMBEDDING_DIM=1024

# --- Langfuse ---
LANGFUSE_SECRET_KEY=your-secret-key
LANGFUSE_PUBLIC_KEY=your-public-key
LANGFUSE_HOST=http://localhost:20025

# --- RAG ---
CHUNK_SIZE=512
CHUNK_OVERLAP=50
TOP_K=5
```

**폐쇄망 전환 시:** `.env`의 `LLM_BASE_URL`, `EMBEDDING_BASE_URL`만 변경하면 됩니다. 코드 수정 불필요.

### 4-3. 필수 서비스 실행 순서

1. **MariaDB** — `paper` 데이터베이스, `sid_v_09_01` 테이블
2. **Milvus** — `m_paper` 데이터베이스, `m_sid_v_09_01` 컬렉션
3. **LM Studio** (또는 vLLM/TEI) — LLM + 임베딩 서버
4. **Langfuse** (선택) — 트레이싱/관찰

---

## 5. 데이터 파이프라인

### 5-1. CSV → MariaDB

```bash
D:/WPy64-312101_paper/python/python.exe load_csv_to_mariadb.py
```

`data/sample_paper.csv` (17개 컬럼, 10건) → MariaDB `paper.sid_v_09_01`

### 5-2. MariaDB → Milvus (임베딩 포함)

```bash
# LM Studio 서버 실행 필수 (http://localhost:20020)
D:/WPy64-312101_paper/python/python.exe load_mariadb_to_milvus.py
```

MariaDB 전체 데이터 → bge-m3 임베딩(1024 dim) → Milvus 적재

### 5-3. QA 데이터셋 생성

```bash
D:/WPy64-312101_paper/python/python.exe scripts/generate_qa_dataset.py
```

MariaDB `qa_dataset` 테이블에 1,000건 추가 (총 2,080건).

---

## 6. 서버 실행

### 6-1. FastAPI 서버

```bash
D:/WPy64-312101_paper/python/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

- Swagger UI: `http://localhost:8080/docs`
- API: `POST /api/chat`, `GET /api/agents`, `POST /v1/chat/completions`

### 6-2. CLI (터미널)

```bash
# 단일 쿼리
D:/WPy64-312101_paper/python/python.exe scripts/cli.py -q "OLED 효율 관련 최신 논문 찾아줘"

# 에이전트 지정
D:/WPy64-312101_paper/python/python.exe scripts/cli.py -a analytics -q "2024년 월별 논문 편수"

# 대화형 모드
D:/WPy64-312101_paper/python/python.exe scripts/cli.py
```

---

## 7. 14개 에이전트 설명

| 단계 | 에이전트 | 데이터 소스 | 설명 |
|------|---------|------------|------|
| Phase 1 | `paper_qa` | Milvus | 논문 검색 & 질의응답 |
| Phase 1 | `literature_survey` | Milvus | 주제별 문헌 리뷰 자동 생성 |
| Phase 1 | `paper_deep_dive` | Milvus | 특정 논문 심층 분석 |
| Phase 1 | `analytics` | **MariaDB** | 통계/집계/목록 (편수, 추이, 리스트) |
| Phase 2 | `idea_generator` | Milvus | 연구 아이디어 제안 |
| Phase 2 | `cross_domain` | Milvus | 타 분야 기술 적용 제안 |
| Phase 2 | `trend_analyzer` | Milvus | 기술 트렌드 분석 |
| Phase 3 | `experiment_planner` | Milvus | 실험 설계 제안 |
| Phase 3 | `material_advisor` | Milvus | 재료/공정 비교 분석 |
| Phase 3 | `patent_landscaper` | Milvus | 특허 동향 분석 |
| Phase 3 | `competitive_intel` | Milvus | 경쟁사 동향 모니터링 |
| Phase 4 | `report_drafter` | Milvus | 보고서/발표 초안 작성 |
| Phase 4 | `peer_review` | Milvus | 논문/보고서 가상 리뷰 |
| Phase 4 | `knowledge_connector` | Milvus | 전문가 매칭 |

**데이터 소스 자동 선택 기준:**
- 의미 기반 검색 (유사 논문 찾기) → **Milvus** (벡터 + BM25 하이브리드)
- 통계/집계 (편수, 목록, 그래프) → **MariaDB** (SQL GROUP BY/COUNT)

---

## 8. 날짜 파싱 시스템

사용자의 자연어 날짜 표현을 자동으로 `coverdate_from/to` 필터로 변환합니다.

| 유형 | 예시 | 변환 결과 |
|------|------|-----------|
| D1 (절대 연월) | "2024년 11월" | 20241101 ~ 20241130 |
| D2 (절대 범위) | "2023년 3분기", "2022~2024년" | 20230701~20230930, 20220101~20241231 |
| D3 (상대) | "작년 여름", "최근 6개월" | 서버 시간 기준 자동 계산 |
| D4 (비교) | "2020년과 2024년 비교" | 20200101 ~ 20241231 |

**서버 시간 tool (`app/core/tools.py`):**
- `get_current_datetime()` — 서버 현재 시간 반환
- 모든 LLM 프롬프트에 현재 날짜 자동 주입 → LLM도 시간 인식 가능

---

## 9. 평가 방법

```bash
D:/WPy64-312101_paper/python/python.exe scripts/evaluate_agents.py
```

4가지 항목을 자동으로 평가합니다:

| 항목 | 방법 | 최근 결과 |
|------|------|-----------|
| 날짜 파싱 | date_parser vs DB 기대값 (전수) | **100%** (1,155건) |
| 필터 적용 | 파서 출력 vs expected_filters | **100%** (85건) |
| Intent 분류 | LLM 출력 vs expected agent_type (100건 샘플) | 50% (qwen3-0.6b 한계) |
| E2E 파이프라인 | supervisor 전체 실행 (10건 샘플) | 70% |

**참고:** Intent 분류 50%는 qwen3-0.6b(0.6B 파라미터) 모델 한계이며, 폐쇄망의 qwen3-235B로 전환 시 대폭 개선됩니다.

---

## 10. Milvus vs MariaDB 사용 구분

| 상황 | 사용 DB | 이유 |
|------|--------|------|
| "OLED 효율 관련 논문 찾아줘" | Milvus | 의미 기반 유사도 검색 |
| "2024년 월별 논문 편수" | MariaDB | SQL GROUP BY 집계 |
| "작년 여름 Micro LED 논문 목록" | MariaDB | 조건별 목록 조회 |
| "LTPS 관련 문헌 리뷰" | Milvus | 다중 쿼리 + LLM 종합 |
| "Samsung의 OLED 기술 동향" | Milvus | 키워드+저자 필터 검색 |

**Milvus 주의사항:** 논문은 chunk로 분할 적재되므로, 동일 논문이 여러 행으로 존재합니다. 논문 편수를 세려면 `chunk_id=1`인 것만 카운트하거나, MariaDB에서 집계해야 합니다.

---

## 11. 폐쇄망 서버 이전 체크리스트

1. `.env.example` → `.env` 복사
2. `LLM_BASE_URL` → vLLM 서버 주소 (`http://...:8000/v1`)
3. `EMBEDDING_BASE_URL` → TEI 서버 주소 (`http://...:8080/v1`)
4. `LLM_MODEL` → `qwen3-235B-A22B-Instruct-2507`
5. `EMBEDDING_MODEL` → `bge-m3`
6. MariaDB, Milvus 접속정보 변경
7. Langfuse 접속정보 변경
8. `pip install -r requirements.txt` 실행
9. 데이터 적재 (`load_csv_to_mariadb.py` → `load_mariadb_to_milvus.py`)
10. FastAPI 서버 시작

**코드 수정은 불필요합니다.** `.env`만 변경하면 됩니다.
