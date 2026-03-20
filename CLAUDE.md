# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Co-scientist agent 개발 프로젝트. 초기 단계로 `./data/sample_paper.csv`의 논문 데이터를 MariaDB와 Milvus에 적재하는 작업을 수행한다. 이후 agent 개발은 DB를 기준으로 모든 작업을 수행함.

## Data Pipeline

### 원본 데이터
- `data/sample_paper.csv` — 논문 메타데이터 및 텍스트 (columns: mariadb_id, filename, doi, coverdate, title, paper_keyword, paper_text, volume, issue, totalpage, referencetotal, author, references, chunk_id, chunk_total_counts, bm25_keywords, parser_ver)

### MariaDB (관계형 저장소)
- 접속: `localhost:3306`, user `root`, password `Password19`
- Database: `paper`, Table: `sid_v_09_01`
- Character set: `utf8mb4` / `utf8mb4_unicode_ci`
- 스키마는 `MariaDB.md` 참조 — CSV 컬럼과 1:1 매핑

### Milvus (벡터 저장소)
- Database: `m_paper`, Collection: `m_sid_v_09_01`
- MariaDB 전체 필드 + 3개 신규 필드:
  - `embeddings` — paper_text를 bge-m3로 임베딩 (1024 dim, IVF_FLAT, IP, nlist=128)
  - `bm25_keywords_sparse` — bm25_keywords 기반 BM25 sparse vector (SPARSE_INVERTED_INDEX, BM25, DAAT_MAXSCORE)
  - `embedding_model_id` — 임베딩 모델명 기록
- 상세 설정은 `milvus.md` 참조

## Python 환경

이 프로젝트 전용 WinPython 사용:

```bash
# Python 실행
D:/WPy64-312101_paper/python/python.exe script.py

# 패키지 설치
D:/WPy64-312101_paper/python/python.exe -m pip install <패키지명>
```

- 현재 base 패키지만 설치됨. 필요한 라이브러리(pymilvus, mariadb, pandas 등)는 pip으로 자동 설치할 것.

## VM npm 패키지 사용 가이드

### 핵심 원칙

**VM에서 `npm install`은 절대 시도하지 않는다.** 프록시 allowlist에 의해 항상 실패한다. 다른 우회 설치 방법(curl, wget 등)도 시도하지 않는다.

### 1. 프리설치 패키지 (우선 사용)

아래 패키지들이 `/usr/local/lib/node_modules_global/lib/node_modules/`에 프리설치되어 있다.

- `docx` (v9.5.3) — Word 문서 생성 (ESM only)
- `pptxgenjs` — PowerPoint 생성
- `pdf-lib` — PDF 생성/편집
- `pdfjs-dist` — PDF 읽기/파싱
- `sharp` — 이미지 처리
- `marked` — Markdown → HTML
- `markdown-toc` — Markdown 목차 생성
- `graphviz` — 그래프 시각화
- `typescript` / `tsx` / `ts-node` — TypeScript
- `@anthropic-ai` — Anthropic SDK

#### 세션 시작 시 심볼릭 링크

```bash
mkdir -p node_modules && for pkg in /usr/local/lib/node_modules_global/lib/node_modules/*/; do ln -sf "$pkg" "node_modules/$(basename "$pkg")"; done
```

#### 사용 시 주의

- `docx`, `marked` 등 ESM 패키지는 `import`를 사용 (`require()` 불가)
- `.mjs` 파일이나 `--input-type=module` 플래그를 사용할 것

### 2. 프리설치에 없는 패키지가 필요할 때

**VM에서 직접 설치를 시도하지 않는다.** `npm install`, `curl`, `wget` 등 어떤 방법으로도 시도하지 않는다.

대신 유저에게 현재 선택된 폴더에서 직접 설치하도록 안내한다:

```bash
npm install <패키지명>
```

- 유저의 로컬 터미널에서, Cowork에 선택된 폴더 안에서 위 명령 실행
- 설치 완료되면 알려달라고 요청

#### VM에서 참조하는 방법

워크스페이스 마운트 경로는 세션마다 다르므로 하드코딩하지 않는다:

```bash
WS=$(find "$HOME/mnt" -maxdepth 1 -mindepth 1 -type d ! -name uploads | head -1)
```

## Github 정보
- Repository: https://github.com/bkji/my-paper-agent.git

## Code 생성 작업 규칙
- Python 패키지 설치는 자동으로 진행할 것. 버전 에러 발생시 적절한 패키지 버전 재설치 포함.
- Python code 실행도 자동으로 수행하여 에러 수정할 것.
- Git commit도 자동으로 수행하되, 주요 코드 변경점 발생시 수행하고, **commit message는 한글로 상세히 작성**할 것.
