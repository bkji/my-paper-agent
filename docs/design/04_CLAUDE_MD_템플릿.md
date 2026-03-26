# CLAUDE.md 템플릿

> 이 파일을 프로젝트 루트에 `CLAUDE.md`로 복사하여 사용합니다.
> `{변수}`로 표시된 부분을 프로젝트에 맞게 수정하세요.

---

```markdown
# CLAUDE.md

Claude Code가 이 프로젝트에서 작업할 때 참조하는 지침서입니다.

## 프로젝트 개요

{프로젝트명} — {한 줄 설명}

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
│   ├── agents/                   # {N}개 에이전트 (LangGraph StateGraph)
│   │   ├── supervisor.py         # extract_dates → classify_intent → route
│   │   ├── common.py             # 검색/LLM 호출 공통 헬퍼
│   │   ├── state.py              # AgentState TypedDict
│   │   ├── phase1/               # {에이전트 목록}
│   │   ├── phase2/               # {에이전트 목록}
│   │   ├── phase3/               # {에이전트 목록}
│   │   └── phase4/               # {에이전트 목록}
│   ├── api/
│   │   ├── deps.py               # 공통 의존성 (Bearer 토큰 인증)
│   │   └── routes/               # chat, agents, documents, openai_compat
│   ├── models/                   # db_models (SQLAlchemy), schemas (Pydantic)
│   └── services/                 # chunker, ingest
├── scripts/                      # CLI, QA 생성, 평가 스크립트
├── data/{데이터파일}              # 원본 데이터
├── load_csv_to_mariadb.py        # CSV → MariaDB
├── load_mariadb_to_milvus.py     # MariaDB → Milvus (임베딩)
├── .env                          # 접속정보 (Git 미포함)
├── .env.example                  # 환경변수 템플릿
├── requirements.txt              # Python 패키지
└── CLAUDE.md                     # 이 파일
```

## 환경변수 (.env)

**모든 접속정보는 `.env`에서 관리. 코드에 절대 하드코딩하지 않는다.**

```env
# LLM (OpenAI-compatible API)
LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

# Embedding (OpenAI-compatible API)
EMBEDDING_BASE_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIM

# MariaDB
MARIADB_HOST, MARIADB_PORT, MARIADB_USER, MARIADB_PASSWORD, MARIADB_DATABASE

# Milvus
MILVUS_HOST, MILVUS_PORT, MILVUS_DATABASE, MILVUS_COLLECTION

# Langfuse
LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_HOST

# OpenAI-compatible API (빈값이면 인증 비활성화)
OPENAI_COMPAT_API_KEY=

# 서버 설정
SERVER_HOST=0.0.0.0
SERVER_PORT={포트}

# RAG
CHUNK_SIZE, CHUNK_OVERLAP, TOP_K
```

## DB 구성

### MariaDB (`{DB명}` DB)
- `{테이블명}` — 원본 데이터 (컬럼 설명)
- `qa_dataset` — QA 테스트셋

### Milvus (`{DB명}` DB)
- `{컬렉션명}` — 벡터 컬렉션 (dense: IVF_FLAT/IP, sparse: BM25)
- **주의:** 데이터가 chunk 단위로 적재됨. 건수 = `chunk_id=1`만 카운트

### Milvus vs MariaDB 사용 구분
- **의미 검색** (유사 문서, RAG) → Milvus
- **통계/집계** (건수, 추이, 목록) → MariaDB SQL

## Python 환경

```bash
{Python 경로 및 실행 방법}
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
{N}개 에이전트 중 하나:
  - Milvus 검색 ({N-1}개)
  - MariaDB 집계 (analytics)
  ↓
LLM 답변 생성 (시스템 프롬프트에 현재 날짜 자동 주입)
  ↓
응답: {answer, sources, trace_id}
```

## 날짜 파싱 시스템 (`app/core/date_parser.py`)

- D1: "2024년 11월" → 절대 날짜
- D2: "2023년 3분기", "2022~2024년" → 범위 변환
- D3: "작년 여름", "최근 6개월" → 서버 시간 기준 상대 계산
- D4: "2020년과 2024년 비교" → 전체 범위

## 서버 시간 도구 (`app/core/tools.py`)

- `get_current_datetime()` — 서버 현재 시간 dict 반환
- `get_current_date_context()` — LLM 프롬프트용 날짜 문자열
- `inject_date_context()` — 모든 LLM 호출에 자동 주입

## 실행 명령

```bash
# 데이터 적재
{python} load_csv_to_mariadb.py
{python} load_mariadb_to_milvus.py

# FastAPI 서버
{python} -m uvicorn app.main:app --host 0.0.0.0 --port {포트}

# CLI
{python} scripts/cli.py -q "질문"

# 평가
{python} scripts/evaluate_agents.py
```

## Code 생성 작업 규칙

1. **패키지 설치, Python 실행, git commit, shell 실행 — 모두 묻지 않고 자동 수행.** 확인 프롬프트 금지. 에러 시만 보고.
2. **Git commit**은 주요 코드 변경점마다 자동 수행. **commit message는 한글로 상세히 작성.**
3. **접속정보**는 `.env`에서 관리. 코드에 하드코딩 절대 금지.
4. **중간중간 메모리에 작업 상태 저장** — 터미널이 꺼져도 이어서 작업 가능하도록.
5. **사용자에게 표시하는 내용은 한글**로 작성. code 등 반드시 필요한 것만 영어.
6. **폐쇄망 이전 대비** — LLM/Embedding은 OpenAI-compatible API로 통일. `.env`만 변경하면 전환 가능.
7. **Milvus chunk 주의** — 건수 집계는 MariaDB에서 `chunk_id=1`만 카운트.

## Github
- Repository: {레포지토리 URL}
```

---

## 사용법

1. 위 템플릿을 프로젝트 루트에 `CLAUDE.md`로 저장
2. `{변수}` 부분을 프로젝트에 맞게 수정
3. 설계 문서(`01_시스템_설계서.md`, `02_상세기능_설계서.md`)와 함께 참조
4. Claude Code에 이 CLAUDE.md와 설계 문서를 기반으로 구현 요청

## CLAUDE.md 작성 핵심 원칙

| 원칙 | 설명 |
|------|------|
| **구조 먼저** | 디렉토리 구조를 명확히 → Claude가 파일 위치를 알고 작업 |
| **환경변수 강조** | .env 사용 규칙을 반복 강조 → 하드코딩 방지 |
| **DB 구분 명시** | Milvus vs MariaDB 용도 구분 → 잘못된 DB 사용 방지 |
| **실행 명령** | 실제 명령어 포함 → Claude가 직접 실행/검증 가능 |
| **작업 규칙** | 자동화 수준 명시 → 불필요한 확인 프롬프트 제거 |
| **chunk 주의사항** | chunk 중복 문제를 명시 → 집계 오류 방지 |
