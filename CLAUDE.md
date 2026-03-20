# CLAUDE.md

Claude Code가 이 프로젝트에서 작업할 때 참조하는 지침서입니다.

## 프로젝트 개요

Co-Scientist Agent — 논문 데이터를 MariaDB(관계형)와 Milvus(벡터)에 적재하고, 14개 전문 에이전트가 사용자 질문에 답하는 R&D 지원 시스템.

## 프로젝트 구조

```
├── app/                          # FastAPI 메인 애플리케이션
│   ├── config.py                 # .env 환경변수 로드 (Settings)
│   ├── main.py                   # FastAPI 앱 + 라우터 등록
│   ├── core/                     # 외부 시스템 클라이언트
│   │   ├── llm.py                # LLM (OpenAI-compatible API)
│   │   ├── embeddings.py         # Embedding (OpenAI-compatible API)
│   │   ├── vectorstore.py        # Milvus 벡터 검색/관리
│   │   ├── database.py           # MariaDB (SQLAlchemy + raw SQL 집계)
│   │   ├── date_parser.py        # 한국어 날짜 파서 (D1~D4)
│   │   ├── tools.py              # 서버 시간 도구
│   │   └── langfuse_client.py    # Langfuse 트레이싱
│   ├── agents/                   # 14개 에이전트 (LangGraph StateGraph)
│   │   ├── supervisor.py         # extract_dates → classify_intent → route
│   │   ├── common.py             # 검색/LLM 호출 공통 헬퍼
│   │   ├── state.py              # AgentState TypedDict
│   │   ├── phase1/               # paper_qa, literature_survey, paper_deep_dive, analytics
│   │   ├── phase2/               # idea_generator, cross_domain, trend_analyzer
│   │   ├── phase3/               # experiment_planner, material_advisor, patent_landscaper, competitive_intel
│   │   └── phase4/               # report_drafter, peer_review, knowledge_connector
│   ├── api/routes/               # chat, agents, documents, openai_compat
│   ├── models/                   # db_models (SQLAlchemy), schemas (Pydantic)
│   └── services/                 # chunker, ingest
├── scripts/                      # CLI, QA 생성, 평가 스크립트
├── data/sample_paper.csv         # 논문 원본 데이터
├── load_csv_to_mariadb.py        # CSV → MariaDB
├── load_mariadb_to_milvus.py     # MariaDB → Milvus (임베딩)
├── .env                          # 접속정보 (Git 미포함)
├── .env.example                  # 폐쇄망 이전용 템플릿
├── requirements.txt              # Python 패키지
├── DEVELOPMENT_GUIDE.md          # 초보자용 개발 가이드
└── CLAUDE.md                     # 이 파일
```

## 환경변수 (.env)

**모든 접속정보는 `.env`에서 관리. 코드에 절대 하드코딩하지 않는다.**

```env
# LLM (로컬: LM Studio / 폐쇄망: vLLM)
LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

# Embedding (로컬: LM Studio / 폐쇄망: TEI)
EMBEDDING_BASE_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIM

# MariaDB
MARIADB_HOST, MARIADB_PORT, MARIADB_USER, MARIADB_PASSWORD, MARIADB_DATABASE

# Milvus
MILVUS_HOST, MILVUS_PORT, MILVUS_DATABASE, MILVUS_COLLECTION

# Langfuse
LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_HOST

# OpenAI-compatible API (Open WebUI 연동)
OPENAI_COMPAT_API_KEY=co-sci

# 서버 설정
SERVER_HOST=0.0.0.0
SERVER_PORT=20035

# RAG
CHUNK_SIZE, CHUNK_OVERLAP, TOP_K
```

## DB 구성

### MariaDB (`paper` DB)
- `sid_v_09_01` — 논문 원본 (17 컬럼, coverdate=INT64 YYYYMMDD)
- `qa_dataset` — QA 테스트셋 (2,080건, 14개 에이전트 유형)
- `date_parse_testcases` — 날짜 파싱 테스트 (389건, D1~D4)

### Milvus (`m_paper` DB)
- `m_sid_v_09_01` — 논문 벡터 (dense: IVF_FLAT/IP, sparse: BM25)
- **주의:** 논문이 chunk 단위로 적재됨. 논문 편수 = `chunk_id=1`만 카운트

### Milvus vs MariaDB 사용 구분
- **의미 검색** (유사 논문, RAG) → Milvus
- **통계/집계** (편수, 월별 추이, 목록) → MariaDB SQL

## Python 환경

```bash
# 프로젝트 전용 WinPython
D:/WPy64-312101_paper/python/python.exe -m pip install <패키지명>
D:/WPy64-312101_paper/python/python.exe <스크립트.py>
```

## 에이전트 아키텍처

```
사용자 질문
  ↓
Supervisor (3단계):
  1. extract_dates — 서버 시간 기준 날짜 파싱 → filters
  2. classify_intent — LLM 의도 분류 → agent_type 선택
  3. route_to_agent — 에이전트 실행
  ↓
14개 에이전트 중 하나:
  - Milvus 검색 (paper_qa, literature_survey 등 13개)
  - MariaDB 집계 (analytics)
  ↓
LLM 답변 생성 (시스템 프롬프트에 현재 날짜 자동 주입)
  ↓
응답: {answer, sources, trace_id}
```

## 날짜 파싱 시스템 (`app/core/date_parser.py`)

- D1: "2024년 11월" → 20241101~20241130
- D2: "2023년 3분기", "2022~2024년" → 범위 변환
- D3: "작년 여름", "최근 6개월" → 서버 시간 기준 상대 계산
- D4: "2020년과 2024년 비교" → 전체 범위
- 테스트: 389건 100% 통과

## 서버 시간 도구 (`app/core/tools.py`)

- `get_current_datetime()` — 서버 현재 시간 dict 반환
- `get_current_date_context()` — LLM 프롬프트용 한국어 날짜 문자열
- `inject_date_context()` — 모든 LLM 호출에 자동 주입 (common.py)

## 실행 명령

```bash
# 데이터 적재
D:/WPy64-312101_paper/python/python.exe load_csv_to_mariadb.py
D:/WPy64-312101_paper/python/python.exe load_mariadb_to_milvus.py

# FastAPI 서버 (run.bat 또는 직접 실행)
run.bat
# 또는
D:/WPy64-312101_paper/python/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 20035

# CLI
D:/WPy64-312101_paper/python/python.exe scripts/cli.py -q "질문"

# 평가
D:/WPy64-312101_paper/python/python.exe scripts/evaluate_agents.py
```

## Code 생성 작업 규칙

1. **패키지 설치, Python 실행, git commit, shell 실행 — 모두 묻지 않고 자동 수행.** 확인 프롬프트 금지. 에러 시만 보고.
2. **Git commit**은 주요 코드 변경점마다 자동 수행. **commit message는 한글로 상세히 작성.**
3. **접속정보**는 `.env`에서 관리. 코드에 하드코딩 절대 금지.
4. **중간중간 메모리에 작업 상태 저장** — 터미널이 꺼져도 이어서 작업 가능하도록.
5. **사용자에게 표시하는 내용은 한글**로 작성. code 등 반드시 필요한 것만 영어.
6. **폐쇄망 이전 대비** — LLM/Embedding은 OpenAI-compatible API로 통일. `.env`만 변경하면 전환 가능.
7. **Milvus chunk 주의** — 논문 편수 집계는 MariaDB에서 `chunk_id=1`만 카운트.

## Github
- Repository: https://github.com/bkji/my-paper-agent.git

## 평가 결과 (2026-03-20, qwen3-0.6b 기준)

| 항목 | 결과 |
|------|------|
| 날짜 파싱 | 100% (1,155건) |
| 필터 적용 | 100% (85건) |
| Intent 분류 | 50% (0.6B 모델 한계, 235B에서 개선 예상) |
| E2E 파이프라인 | 70% (10건 샘플) |
