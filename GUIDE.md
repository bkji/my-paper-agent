# 논문 데이터 파이프라인 구축 가이드

CSV 논문 데이터를 MariaDB(관계형 DB)와 Milvus(벡터 DB)에 적재하는 전체 과정을 설명합니다.

---

## 1. 사전 준비

### 1.1 필요한 소프트웨어

| 소프트웨어 | 용도 | 기본 포트 |
|---|---|---|
| MariaDB | 관계형 데이터 저장 | 3306 |
| Milvus | 벡터 검색 엔진 | 19530 |
| LM Studio | 임베딩 모델 서빙 | 20020 |
| Python 3.12 | 스크립트 실행 | - |

### 1.2 Python 환경 설정

이 프로젝트는 전용 WinPython(`D:\WPy64-312101_paper`)을 사용합니다.

```bash
# 필요한 패키지 설치
D:/WPy64-312101_paper/python/python.exe -m pip install mariadb pandas python-dotenv "pymilvus[model]"
```

### 1.3 LM Studio 설정

1. LM Studio를 실행합니다.
2. 임베딩 모델 `bge-m3`를 다운로드하고 로드합니다.
3. **Server** 탭으로 이동합니다.
4. 포트를 `20020`으로 설정합니다.
5. **Start Server** 버튼을 클릭합니다.

서버가 정상 동작하는지 확인:
```bash
curl http://localhost:20020/v1/models
```
응답에 `text-embedding-bge-m3`가 포함되어 있으면 성공입니다.

### 1.4 환경변수 설정 (.env)

프로젝트 루트에 `.env` 파일을 생성합니다. 접속 정보는 코드에 직접 넣지 않고 이 파일에서 관리합니다.

```env
# MariaDB
MARIADB_HOST=localhost
MARIADB_PORT=3306
MARIADB_USER=root
MARIADB_PASSWORD=여기에_비밀번호_입력
MARIADB_DATABASE=paper

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_DATABASE=m_paper
MILVUS_COLLECTION=m_sid_v_09_01

# LM Studio 임베딩
LMSTUDIO_URL=http://localhost:20020
EMBEDDING_MODEL=text-embedding-bge-m3
```

> **주의:** `.env` 파일은 `.gitignore`에 포함되어 있어 Git에 커밋되지 않습니다. 각자 환경에 맞게 생성해야 합니다.

---

## 2. 데이터 원본

`data/sample_paper.csv` 파일에 논문 데이터가 들어 있습니다.

| 컬럼명 | 타입 | 설명 |
|---|---|---|
| mariadb_id | 정수 | 논문 고유 ID |
| filename | 문자열 | 파일명 |
| doi | 문자열 | DOI 링크 |
| coverdate | 정수 | 발행일 (YYYYMMDD) |
| title | 문자열 | 논문 제목 |
| paper_keyword | 문자열 | 논문 키워드 |
| paper_text | 문자열 | 논문 본문 텍스트 |
| volume | 정수 | 권 |
| issue | 정수 | 호 |
| totalpage | 정수 | 총 페이지 수 |
| referencetotal | 정수 | 참고문헌 수 |
| author | 문자열 | 저자 |
| references | 문자열 | 참고문헌 목록 |
| chunk_id | 정수 | 청크 번호 |
| chunk_total_counts | 정수 | 전체 청크 수 |
| bm25_keywords | 문자열 | BM25 검색용 키워드 |
| parser_ver | 문자열 | 파서 버전 |

---

## 3. Step 1 — CSV → MariaDB 적재

### 3.1 MariaDB 준비

MariaDB가 실행 중인지 확인합니다. 접속 정보는 `.env`에서 관리합니다.

### 3.2 스크립트 실행

```bash
D:/WPy64-312101_paper/python/python.exe load_csv_to_mariadb.py
```

### 3.3 수행 내용

이 스크립트는 다음을 자동으로 수행합니다:

1. `paper` 데이터베이스 생성 (없으면)
2. `sid_v_09_01` 테이블 생성 (기존 있으면 삭제 후 재생성)
3. CSV 데이터를 테이블에 INSERT
4. 건수 검증

### 3.4 생성되는 테이블 구조

```
paper.sid_v_09_01
├── mariadb_id       BIGINT
├── filename         VARCHAR(512)      ← 인덱스
├── doi              VARCHAR(256)      ← 인덱스
├── coverdate        BIGINT            ← 인덱스
├── title            TEXT
├── paper_keyword    TEXT              ← 인덱스 (prefix 255)
├── paper_text       TEXT              ← 인덱스 (prefix 255)
├── volume           SMALLINT
├── issue            SMALLINT
├── totalpage        SMALLINT
├── referencetotal   SMALLINT
├── author           TEXT
├── references       TEXT
├── chunk_id         SMALLINT
├── chunk_total_counts SMALLINT
├── bm25_keywords    TEXT
└── parser_ver       VARCHAR(20)
```

### 3.5 정상 실행 결과

```
CSV 로드: 10행
테이블 paper.sid_v_09_01 생성 완료
10건 INSERT 완료
검증: 테이블 내 총 10건
```

---

## 4. Step 2 — MariaDB → Milvus 적재

### 4.1 사전 확인

- Milvus가 `localhost:19530`에서 실행 중인지 확인
- LM Studio 서버가 `localhost:20020`에서 실행 중인지 확인 (**Start Server 필수!**)

### 4.2 스크립트 실행

```bash
D:/WPy64-312101_paper/python/python.exe load_mariadb_to_milvus.py
```

### 4.3 수행 내용

이 스크립트는 다음을 자동으로 수행합니다:

1. MariaDB에서 전체 데이터 조회
2. LM Studio API를 호출하여 `paper_text`를 벡터로 임베딩 (bge-m3, 1024차원)
3. Milvus에 `m_paper` 데이터베이스 생성
4. `m_sid_v_09_01` 컬렉션 생성 (기존 있으면 삭제 후 재생성)
5. 데이터 삽입 (BM25 sparse vector는 Milvus가 자동 생성)
6. 인덱스 생성
7. 건수 검증

### 4.4 생성되는 컬렉션 구조

```
m_paper.m_sid_v_09_01
│
│── id                    INT64 (PK, 자동 생성)
│
│── [MariaDB 원본 필드 전체]
│   ├── mariadb_id        INT64
│   ├── filename          VARCHAR(512)
│   ├── ...
│   └── parser_ver        VARCHAR(20)
│
│── [신규 필드 3개]
│   ├── embeddings              FLOAT_VECTOR (1024 dim) ← paper_text 임베딩
│   ├── bm25_keywords_sparse    SPARSE_FLOAT_VECTOR     ← bm25_keywords 기반 자동 생성
│   └── embedding_model_id      VARCHAR(128)            ← 사용된 임베딩 모델명
```

### 4.5 인덱스 목록

| 필드명 | 인덱스 타입 | 메트릭/설정 | 용도 |
|---|---|---|---|
| embeddings | IVF_FLAT | IP, nlist=128 | 의미 검색 (Semantic Search) |
| bm25_keywords_sparse | SPARSE_INVERTED_INDEX | BM25 | 키워드 검색 |
| coverdate | INVERTED | - | 날짜 필터링 |
| paper_keyword | INVERTED | - | 키워드 필터링 |
| title | INVERTED | - | 제목 필터링 |
| volume | INVERTED | - | 권 필터링 |
| issue | INVERTED | - | 호 필터링 |
| author | INVERTED | - | 저자 필터링 |

### 4.6 정상 실행 결과

```
MariaDB에서 10건 조회 완료
임베딩 생성 중...
  임베딩 8/10 완료
  임베딩 10/10 완료
Milvus 접속 완료 (localhost:19530)
Collection 'm_sid_v_09_01' 생성 완료
10건 INSERT 완료
embeddings 인덱스 생성 완료 (IVF_FLAT, IP, nlist=128)
bm25_keywords_sparse 인덱스 생성 완료 (SPARSE_INVERTED_INDEX, BM25)
coverdate 인덱스 생성 완료 (INVERTED)
paper_keyword 인덱스 생성 완료 (INVERTED)
title 인덱스 생성 완료 (INVERTED)
volume 인덱스 생성 완료 (INVERTED)
issue 인덱스 생성 완료 (INVERTED)
author 인덱스 생성 완료 (INVERTED)
검증: collection 내 총 10건
```

---

## 5. 전체 파이프라인 요약

```
sample_paper.csv
       │
       ▼
 ┌─────────────┐    load_csv_to_mariadb.py
 │   MariaDB   │◄────────────────────────
 │  paper.     │
 │  sid_v_09_01│
 └──────┬──────┘
        │
        ▼
 ┌─────────────┐    load_mariadb_to_milvus.py
 │   Milvus    │◄────────────────────────────
 │  m_paper.   │    + LM Studio 임베딩 API
 │  m_sid_v_   │      (bge-m3, 1024 dim)
 │  09_01      │
 └─────────────┘
```

### 실행 순서

```bash
# 1. MariaDB 적재
D:/WPy64-312101_paper/python/python.exe load_csv_to_mariadb.py

# 2. Milvus 적재 (LM Studio 서버 시작 필수)
D:/WPy64-312101_paper/python/python.exe load_mariadb_to_milvus.py
```

---

## 6. 트러블슈팅

### LM Studio 연결 실패
- LM Studio에서 **Server** 탭 → **Start Server** 버튼이 눌려 있는지 확인
- 포트가 `20020`으로 설정되어 있는지 확인

### MariaDB 연결 실패
- MariaDB 서비스가 실행 중인지 확인
- `.env` 파일의 접속 정보가 올바른지 확인

### Milvus 연결 실패
- Milvus 서비스가 실행 중인지 확인 (Docker 등)
- 포트 `19530`이 열려 있는지 확인

### 패키지 import 에러
- 필요한 패키지가 모두 설치되었는지 확인:
```bash
D:/WPy64-312101_paper/python/python.exe -m pip install mariadb pandas python-dotenv "pymilvus[model]"
```
