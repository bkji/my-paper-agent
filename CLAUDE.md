# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Co-scientist agent 개발 프로젝트. 논문 데이터를 MariaDB(관계형)와 Milvus(벡터)에 적재하고, 이를 기반으로 agent를 개발한다.

## 프로젝트 구조

```
├── data/sample_paper.csv          # 논문 원본 데이터 (17개 컬럼, 10건)
├── load_csv_to_mariadb.py         # CSV → MariaDB 적재 스크립트
├── load_mariadb_to_milvus.py      # MariaDB → Milvus 적재 스크립트 (임베딩 포함)
├── .env                           # 접속정보 (Git 미포함)
├── MariaDB.md                     # MariaDB 테이블 스키마 정의
├── milvus.md                      # Milvus 컬렉션 설정 정의
├── GUIDE.md                       # 초보자용 전체 파이프라인 가이드
└── CLAUDE.md                      # 이 파일
```

## Data Pipeline

```
sample_paper.csv → [load_csv_to_mariadb.py] → MariaDB paper.sid_v_09_01
                                                        │
                                                        ▼
                   [load_mariadb_to_milvus.py] → Milvus m_paper.m_sid_v_09_01
                        + LM Studio 임베딩 API (bge-m3, 1024 dim)
```

### 실행 명령

```bash
# 1. CSV → MariaDB
D:/WPy64-312101_paper/python/python.exe load_csv_to_mariadb.py

# 2. MariaDB → Milvus (LM Studio 서버 시작 필수)
D:/WPy64-312101_paper/python/python.exe load_mariadb_to_milvus.py
```

## DB 구성

### MariaDB
- Database: `paper`, Table: `sid_v_09_01`
- Character set: `utf8mb4` / `utf8mb4_unicode_ci`
- CSV 컬럼과 1:1 매핑, 인덱스: filename, doi, coverdate, paper_keyword, paper_text
- 상세 스키마: `MariaDB.md` 참조

### Milvus
- Database: `m_paper`, Collection: `m_sid_v_09_01`
- PK: `id` (INT64, auto_id) — `mariadb_id`는 일반 필드
- MariaDB 전체 필드 + 신규 3개 필드:
  - `embeddings` — FLOAT_VECTOR (1024 dim, IVF_FLAT, IP, nlist=128)
  - `bm25_keywords_sparse` — SPARSE_FLOAT_VECTOR (BM25 function 자동 생성)
  - `embedding_model_id` — 사용된 임베딩 모델명
- 스칼라 인덱스(INVERTED): coverdate, paper_keyword, title, volume, issue, author
- 상세 설정: `milvus.md` 참조

### LM Studio (임베딩 서버)
- URL: `http://localhost:20020`
- 임베딩 모델: `text-embedding-bge-m3` (1024 dim)
- LLM 모델: `qwen3-0.6b` (사용 가능)

## 환경변수 (.env)

모든 접속정보는 `.env` 파일에서 관리하며, Python 코드에 하드코딩하지 않는다.

```env
MARIADB_HOST, MARIADB_PORT, MARIADB_USER, MARIADB_PASSWORD, MARIADB_DATABASE
MILVUS_HOST, MILVUS_PORT, MILVUS_DATABASE, MILVUS_COLLECTION
LMSTUDIO_URL, EMBEDDING_MODEL
```

## Python 환경

프로젝트 전용 WinPython: `D:\WPy64-312101_paper`

```bash
D:/WPy64-312101_paper/python/python.exe -m pip install <패키지명>
```

설치된 주요 패키지: `mariadb`, `pandas`, `python-dotenv`, `pymilvus[model]`

## VM npm 패키지 사용 가이드

### 핵심 원칙

**VM에서 `npm install`은 절대 시도하지 않는다.** 프록시 allowlist에 의해 항상 실패한다. 다른 우회 설치 방법(curl, wget 등)도 시도하지 않는다.

### 프리설치 패키지 (우선 사용)

`/usr/local/lib/node_modules_global/lib/node_modules/`에 프리설치:
`docx`, `pptxgenjs`, `pdf-lib`, `pdfjs-dist`, `sharp`, `marked`, `markdown-toc`, `graphviz`, `typescript`/`tsx`/`ts-node`, `@anthropic-ai`

```bash
mkdir -p node_modules && for pkg in /usr/local/lib/node_modules_global/lib/node_modules/*/; do ln -sf "$pkg" "node_modules/$(basename "$pkg")"; done
```

- ESM 패키지(`docx`, `marked` 등)는 `import` 사용 (`.mjs` 또는 `--input-type=module`)
- 프리설치에 없는 패키지는 유저에게 로컬 터미널에서 `npm install` 하도록 안내

## Github
- Repository: https://github.com/bkji/my-paper-agent.git

## Code 생성 작업 규칙
- Python 패키지 설치는 자동으로 진행할 것. 버전 에러 발생시 적절한 패키지 버전 재설치 포함.
- Python code 실행도 자동으로 수행하여 에러 수정할 것.
- Git commit도 자동으로 수행하되, 주요 코드 변경점 발생시 수행하고, **commit message는 한글로 상세히 작성**할 것.
- 접속정보(DB, API 등)는 `.env`에서 관리하고 코드에 하드코딩하지 않는다.
