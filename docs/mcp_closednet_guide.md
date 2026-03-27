# 폐쇄망 MCP 서버 배포 가이드

Co-Scientist MCP 서버를 폐쇄망(Air-gapped Network)에 배포할 때 필요한 설정 및 준비사항입니다.

> **코드 변경은 없습니다.** 이미 폐쇄망 대비로 설계되어 `.env`와 인프라 준비만 하면 됩니다.

---

## 1. 인프라 체크리스트

| 구성요소 | 필요 여부 | 용도 | 비고 |
|---------|----------|------|------|
| vLLM | **필수** | LLM 추론 | OpenAI-compatible API (`/v1/chat/completions`) |
| TEI | **필수** | 임베딩 생성 | bge-m3 모델 서빙 (`/v1/embeddings`) |
| MariaDB | **필수** | 논문 원본 + 통계/집계 | `paper` DB |
| Milvus | **필수** | 벡터 검색 (dense + sparse) | `m_paper` DB |
| Langfuse | 선택 | 트레이싱/관측성 | 없으면 키 빈값으로 비활성화 |

## 2. `.env` 파일 설정

`.env.example`을 `.env`로 복사한 후 폐쇄망 서버 주소로 변경합니다.

```env
# --- LLM (폐쇄망 vLLM 서버) ---
LLM_BASE_URL=http://<vLLM서버IP>:<PORT>/v1
LLM_API_KEY=your-api-key
LLM_MODEL=qwen3-235B-A22B-Instruct-2507

# --- Embedding (폐쇄망 TEI 서버) ---
EMBEDDING_BASE_URL=http://<TEI서버IP>:<PORT>/v1
EMBEDDING_API_KEY=your-api-key
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024

# --- MariaDB ---
MARIADB_HOST=<DB서버IP>
MARIADB_PORT=3306
MARIADB_USER=root
MARIADB_PASSWORD=<실제 비밀번호>
MARIADB_DATABASE=paper

# --- Milvus ---
MILVUS_HOST=<Milvus서버IP>
MILVUS_PORT=19530
MILVUS_DATABASE=m_paper
MILVUS_COLLECTION=m_sid_v_09_01

# --- Langfuse (없으면 빈값으로 비활성화) ---
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_HOST=

# --- 인증 (폐쇄망에서는 빈값 권장) ---
OPENAI_COMPAT_API_KEY=

# --- 서버 설정 ---
SERVER_HOST=0.0.0.0
SERVER_PORT=20031

# --- RAG ---
CHUNK_SIZE=512
CHUNK_OVERLAP=50
TOP_K=5
```

## 3. Python 패키지 오프라인 설치

폐쇄망은 pip 접속이 불가하므로 외부망에서 휠 파일을 미리 다운로드합니다.

```bash
# [외부망] 휠 다운로드
pip download -r requirements.txt -d ./wheels/

# [폐쇄망] 오프라인 설치
pip install --no-index --find-links=./wheels/ -r requirements.txt
```

### 핵심 패키지 목록

| 패키지 | 용도 |
|--------|------|
| `mcp>=1.0.0` | MCP 프로토콜 서버 |
| `fastapi`, `uvicorn` | REST API 서버 |
| `langgraph` | 에이전트 오케스트레이션 |
| `pymilvus` | Milvus 벡터 DB 클라이언트 |
| `sqlalchemy`, `pymysql` | MariaDB 클라이언트 |
| `httpx` | LLM/Embedding API 호출 |
| `langfuse` | 트레이싱 (선택) |

## 4. MCP 설정 파일 경로 수정

폐쇄망 서버의 Python 및 프로젝트 경로에 맞게 수정합니다.

### VS Code (`.vscode/mcp.json`)

```json
{
  "servers": {
    "co-scientist": {
      "command": "/path/to/python",
      "args": ["/path/to/tool/mcp_server.py"],
      "env": {
        "PYTHONPATH": "/path/to/tool"
      }
    }
  }
}
```

### Claude Desktop (`claude_desktop_config.json`)

경로: `~/.config/Claude/claude_desktop_config.json` (Linux) 또는 `%APPDATA%\Claude\claude_desktop_config.json` (Windows)

```json
{
  "mcpServers": {
    "co-scientist": {
      "command": "/path/to/python",
      "args": ["/path/to/tool/mcp_server.py"],
      "env": {
        "PYTHONPATH": "/path/to/tool"
      }
    }
  }
}
```

### Cursor

Cursor 설정 → MCP Servers에 동일한 형식으로 추가합니다.

## 5. 데이터 적재 (최초 1회)

폐쇄망 DB에 데이터가 없다면 아래 순서로 적재합니다.

```bash
# 1단계: CSV → MariaDB
python load_csv_to_mariadb.py

# 2단계: MariaDB → Milvus (임베딩 생성 포함)
python load_mariadb_to_milvus.py
```

> **주의:** 2단계는 TEI 서버가 먼저 가동 중이어야 합니다 (임베딩 생성 필요).

## 6. MCP 서버 실행

### stdio 모드 (Claude Desktop, VS Code 등에서 자동 실행)

MCP 설정 파일에 등록하면 클라이언트가 자동으로 프로세스를 시작합니다.
수동 테스트 시:

```bash
python mcp_server.py
```

### SSE 모드 (원격 접속용)

```bash
# 기본 포트 (20032)
python mcp_server.py --transport sse --port 20032

# 또는 run_mcp.bat / run_mcp.sh 사용
run_mcp.bat sse
run_mcp.sh sse
```

클라이언트에서 `http://<서버IP>:20032/sse`로 연결합니다.

### streamable-http 모드 (최신 MCP 프로토콜)

```bash
python mcp_server.py --transport streamable-http --port 20032
```

엔드포인트: `http://<서버IP>:20032/mcp`

## 7. 제공되는 MCP 도구

| 도구 | 설명 | 필수 파라미터 |
|------|------|-------------|
| `ask_co_scientist` | 14개 에이전트 중 자동 선택하여 답변 | `query` |
| `list_agents` | 사용 가능한 에이전트 목록 반환 | 없음 |
| `search_papers` | 논문 검색/통계 (analytics 에이전트) | `query` |

## 8. 동작 확인

MCP 서버가 정상 동작하는지 확인하려면:

1. **인프라 확인** — MariaDB, Milvus, vLLM, TEI 서버 접속 가능 여부
2. **MCP 서버 시작** — stderr 로그에 `Starting MCP server` 출력 확인
3. **도구 호출 테스트** — MCP 클라이언트에서 `list_agents` 호출하여 14개 에이전트 목록 반환 확인
4. **질의 테스트** — `ask_co_scientist`로 간단한 질문 전송하여 응답 확인

```
예시 질문: "최근 3년간 Micro LED 관련 논문 트렌드를 알려줘"
```

## 9. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `Connection refused` (LLM) | vLLM 서버 미가동 | vLLM 서버 시작 확인, `LLM_BASE_URL` 점검 |
| `Connection refused` (Embedding) | TEI 서버 미가동 | TEI 서버 시작 확인, `EMBEDDING_BASE_URL` 점검 |
| `Collection not found` | Milvus 데이터 미적재 | `load_mariadb_to_milvus.py` 실행 |
| `Access denied` (MariaDB) | DB 인증 실패 | `.env`의 `MARIADB_PASSWORD` 확인 |
| `ModuleNotFoundError` | 패키지 미설치 | 오프라인 휠 설치 확인 |
| MCP 연결 안됨 | 경로 오류 | MCP 설정의 `command`, `args`, `PYTHONPATH` 경로 확인 |
