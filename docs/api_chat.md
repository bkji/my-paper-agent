# /api/chat API 명세서

> Co-Scientist Agent 채팅 엔드포인트 — 클라이언트 개발자용

---

## 빠른 시작: 3턴 멀티턴 대화 예시

가장 자주 쓰는 패턴입니다. **매 턴마다 이전 대화를 `messages` 배열에 누적하여 전송**합니다.

### 1턴 — 첫 질문

```json
{
  "query": "OLED 논문 최신 3편 알려줘",
  "messages": [
    {"role": "user", "content": "OLED 논문 최신 3편 알려줘"}
  ]
}
```

**응답:**
```json
{
  "answer": "1) Kim2024, 2) Lee2024, 3) Park2024",
  "sources": [...],
  "trace_id": "trace-001"
}
```

### 2턴 — 후속 질문

이전 응답(`assistant`)과 새 질문(`user`)을 `messages`에 추가합니다.

```json
{
  "query": "두 번째 논문 요약해줘",
  "messages": [
    {"role": "user", "content": "OLED 논문 최신 3편 알려줘"},
    {"role": "assistant", "content": "1) Kim2024, 2) Lee2024, 3) Park2024"},
    {"role": "user", "content": "두 번째 논문 요약해줘"}
  ]
}
```

**응답:**
```json
{
  "answer": "Lee2024는 블루 OLED 열화 분석 논문입니다",
  "sources": [...],
  "trace_id": "trace-002"
}
```

### 3턴 — 추가 질문

같은 패턴으로 계속 누적합니다.

```json
{
  "query": "저자가 누구야?",
  "messages": [
    {"role": "user", "content": "OLED 논문 최신 3편 알려줘"},
    {"role": "assistant", "content": "1) Kim2024, 2) Lee2024, 3) Park2024"},
    {"role": "user", "content": "두 번째 논문 요약해줘"},
    {"role": "assistant", "content": "Lee2024는 블루 OLED 열화 분석 논문입니다"},
    {"role": "user", "content": "저자가 누구야?"}
  ]
}
```

> 서버가 히스토리에서 "Lee2024"를 자동 추적하여 해당 논문의 저자 정보를 응답합니다.

### 패턴 요약

```
messages = []

# 1턴
messages.append({"role": "user", "content": 질문1})
→ 요청: {query: 질문1, messages: messages}
→ 응답 수신
messages.append({"role": "assistant", "content": 응답1})

# 2턴
messages.append({"role": "user", "content": 질문2})
→ 요청: {query: 질문2, messages: messages}
→ 응답 수신
messages.append({"role": "assistant", "content": 응답2})

# N턴: 같은 패턴 반복
```

- `query`는 항상 마지막 user 메시지와 동일
- 이전 답변은 원본 그대로 넣으면 됨 (서버가 자동 압축)
- 새 대화 시작 → `messages`를 빈 배열로 초기화

---

## 1. 기본 정보

| 항목 | 값 |
|------|-----|
| URL | `POST /api/chat` |
| Content-Type | `application/json` |
| 인증 | Bearer token (`.env`의 `OPENAI_COMPAT_API_KEY` — 미설정 시 인증 없음) |
| 서버 포트 | 20035 (기본값) |
| 응답 모드 | JSON 일괄 응답 (기본) / SSE 스트리밍 (`stream: true`) |

### 인증

`.env`에 `OPENAI_COMPAT_API_KEY`가 설정되어 있으면 **Bearer 토큰 인증**이 필요합니다.
미설정이면 인증 없이 접근 가능합니다. `/v1/chat/completions`와 **동일한 키**를 사용합니다.

```bash
# 인증 키가 설정된 경우
curl -X POST http://localhost:20035/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer co-sci" \
  -d '{"query": "OLED 논문 알려줘"}'
```

인증 실패 시 응답 (HTTP 401):
```json
{"detail": "Invalid or missing API key"}
```

---

## 2. 요청 (Request)

### 최소 요청 (필수 파라미터만)

**`query`만 필수**이며, 나머지는 모두 선택입니다.

```bash
curl -X POST http://localhost:20035/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "OLED 논문 알려줘"}'
```

### 필수/선택 요약

| 필드 | 필수 여부 | 기본값 | 한 줄 설명 |
|------|-----------|--------|-----------|
| `query` | **필수** | - | 사용자의 현재 질문 |
| `messages` | 선택 | `null` | 멀티턴 대화 히스토리 |
| `stream` | 선택 | `false` | SSE 스트리밍 여부 |
| `agent_type` | 선택 | `null` | 에이전트 강제 지정 |
| `user_id` | 선택 | `null` | 트레이싱용 사용자 ID |
| `filters` | 선택 | `null` | 날짜 필터 직접 지정 |
| `conversation_history` | 선택 | `null` | 하위 호환용 (messages 우선) |
| **헤더** `Authorization` | **조건부** | - | `.env`에 API 키 설정 시 필수 |

### ChatRequest 스키마

```json
{
  "query":                "string         (필수)",
  "messages":             "[{role, content}] | null  (선택 — 멀티턴용)",
  "stream":               "boolean        (선택, 기본값: false)",
  "agent_type":           "string | null  (선택 — 에이전트 강제 지정)",
  "user_id":              "string | null  (선택 — 트레이싱용)",
  "filters":              "object | null  (선택 — 날짜 필터 직접 지정)",
  "conversation_history": "string | null  (선택 — 하위 호환용, messages 우선)"
}
```

### 필드 상세

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `query` | `string` | **필수** | - | 사용자의 현재 질문 |
| `messages` | `list[{role, content}]` | 선택 | `null` | 이전 대화 히스토리 (멀티턴용, **권장**) |
| `stream` | `boolean` | 선택 | `false` | `true`: SSE 실시간 스트리밍, `false`: JSON 일괄 응답 |
| `agent_type` | `string` | 선택 | `null` | 에이전트 강제 지정. 생략 시 AI가 자동 분류 |
| `user_id` | `string` | 선택 | `null` | 사용자 식별자 (Langfuse 트레이싱용) |
| `filters` | `object` | 선택 | `null` | 날짜/조건 필터 직접 지정 |
| `conversation_history` | `string` | 선택 | `null` | 하위 호환용. `messages`가 있으면 무시됨 |

### messages 필드 규칙

| 규칙 | 설명 |
|------|------|
| 포맷 | `[{"role": "user\|assistant", "content": "..."}]` |
| 마지막 항목 | 현재 질문 (`query`와 동일한 내용) |
| 압축 | 서버가 자동 수행 (assistant 답변 800자 초과 시 앞400+뒤400) |
| 턴 제한 | 최근 5턴(10항목)만 사용 (초과 시 오래된 턴 자동 제거) |
| 새 대화 | `messages` 생략 또는 빈 배열 |

### agent_type 허용 값 (14개)

| Phase | agent_type | 설명 |
|-------|-----------|------|
| 1 | `paper_qa` | 논문 검색/Q&A |
| 1 | `literature_survey` | 문헌 리뷰 |
| 1 | `paper_deep_dive` | 논문 심층 분석 |
| 1 | `analytics` | 통계/집계 |
| 2 | `idea_generator` | 연구 아이디어 제안 |
| 2 | `cross_domain` | 타 분야 적용 |
| 2 | `trend_analyzer` | 트렌드 분석 |
| 3 | `experiment_planner` | 실험 설계 |
| 3 | `material_advisor` | 재료/공정 비교 |
| 3 | `patent_landscaper` | 특허 분석 |
| 3 | `competitive_intel` | 경쟁사 분석 |
| 4 | `report_drafter` | 보고서 초안 |
| 4 | `peer_review` | 가상 리뷰 |
| 4 | `knowledge_connector` | 전문가 매칭 |

### filters 필드 구조

```json
{
  "date_start": 20240101,
  "date_end": 20241231
}
```

> `filters`를 직접 지정하면 서버의 날짜 파싱 단계를 건너뜁니다.

---

## 3. 응답 — JSON 모드 (`stream: false`)

`stream`이 `false`(기본값)이면 처리 완료 후 JSON 하나를 반환합니다.

### ChatResponse 스키마

```json
{
  "answer": "string",
  "sources": [SourceDocument] | null,
  "trace_id": "string | null"
}
```

### SourceDocument 스키마

```json
{
  "paper_id": "string",
  "title": "string",
  "doi": "string | null",
  "chunk_id": 0,
  "chunk_text": "string",
  "score": 0.0
}
```

### 필드 상세

| 필드 | 타입 | 설명 |
|------|------|------|
| `answer` | `string` | AI가 생성한 답변 (한국어, Markdown 포함 가능) |
| `sources` | `list[SourceDocument] \| null` | 참조한 논문 목록 |
| `sources[].paper_id` | `string` | 논문 고유 ID |
| `sources[].title` | `string` | 논문 제목 |
| `sources[].doi` | `string \| null` | DOI |
| `sources[].chunk_id` | `int` | 청크 번호 (0부터 시작) |
| `sources[].chunk_text` | `string` | 검색된 청크 텍스트 |
| `sources[].score` | `float` | 유사도 점수 (0~1, 높을수록 관련성 높음) |
| `trace_id` | `string \| null` | Langfuse 트레이싱 ID (디버깅용) |

---

## 4. 응답 — SSE 스트리밍 (`stream: true`)

`stream`이 `true`이면 `text/event-stream` 형식으로 **토큰 단위 실시간 전송**합니다.

### 스트리밍 동작 과정

```
클라이언트 요청 (stream: true)
  ↓
[event: status]  "논문 검색 및 질문 분석 중..."     ← 검색/분류 시작 (수 초 소요)
  ↓
[event: status]  "답변 생성 중..."                  ← LLM 답변 생성 시작
  ↓
[event: token]   "OLED"                            ← 토큰 단위 실시간 전송
[event: token]   " 수명"
[event: token]   " 관련..."
  ↓
[event: token]   "\n\n---\n📚 참조 논문..."          ← 출처 정보
  ↓
[event: sources]  [{paper_id, title, ...}, ...]    ← 구조화된 논문 목록
  ↓
[event: done]    {stream_id: "abc123"}             ← 스트리밍 완료
```

### SSE 이벤트 종류

| event | data 형식 | 설명 | 수신 횟수 |
|-------|-----------|------|----------|
| `status` | `{"message": "..."}` | 처리 단계 안내 | 1~2회 |
| `token` | `{"content": "..."}` | LLM 토큰 1개 | 수십~수백 회 |
| `sources` | `{"sources": [...]}` | 참조 논문 목록 | 0~1회 |
| `error` | `{"message": "..."}` | 에러 발생 시 | 0~1회 |
| `done` | `{"stream_id": "..."}` | 스트리밍 완료 신호 | 항상 1회 (마지막) |

### SSE 원시 데이터 예시

```
event: status
data: {"message": "논문 검색 및 질문 분석 중..."}

event: status
data: {"message": "답변 생성 중..."}

event: token
data: {"content": "OLED 수명 관련"}

event: token
data: {"content": " 최신 연구를 정리하면"}

event: token
data: {"content": " 다음과 같습니다.\n\n"}

event: sources
data: {"sources": [{"paper_id": "SID2024-001", "title": "Enhanced OLED Lifetime via Novel Host Materials", "doi": "10.1002/jsid.1234", "chunk_id": 0, "chunk_text": "...", "score": 0.92}]}

event: done
data: {"stream_id": "a1b2c3d4e5f6"}
```

### 전체 답변 조립

`token` 이벤트의 `content`를 순서대로 이어붙이면 전체 답변이 됩니다.

```
전체 답변 = token[0].content + token[1].content + token[2].content + ...
```

---

## 5. 사용 예시

### 예시 1: 단일 질문 (가장 간단한 호출)

```bash
curl -X POST http://localhost:20035/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "OLED 수명 관련 최신 논문 알려줘"}'
```

```json
{
  "answer": "OLED 수명 관련 최신 논문을 정리하면...",
  "sources": [{"paper_id": "SID2024-001", "title": "Enhanced OLED Lifetime...", "doi": "10.1002/jsid.1234", "chunk_id": 0, "chunk_text": "We demonstrate...", "score": 0.92}],
  "trace_id": "abc123-def456"
}
```

### 예시 2: 에이전트 직접 지정

```bash
curl -X POST http://localhost:20035/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "2024년 OLED 논문 몇 편이야?", "agent_type": "analytics"}'
```

### 예시 3: 스트리밍 모드

```bash
curl -N -X POST http://localhost:20035/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "OLED 수명 관련 최신 논문 알려줘", "stream": true}'
```

> `-N`: curl 출력 버퍼링 비활성화 (SSE 실시간 확인용)

### 예시 4: 멀티턴 3턴 대화 (단계별 전체 흐름)

**1턴 요청:**
```json
{
  "query": "OLED 논문 최신 3편 알려줘",
  "messages": [
    {"role": "user", "content": "OLED 논문 최신 3편 알려줘"}
  ]
}
```

**1턴 응답:** `"1) Kim2024, 2) Lee2024, 3) Park2024"`

**2턴 요청:**
```json
{
  "query": "두 번째 논문 요약해줘",
  "messages": [
    {"role": "user", "content": "OLED 논문 최신 3편 알려줘"},
    {"role": "assistant", "content": "1) Kim2024, 2) Lee2024, 3) Park2024"},
    {"role": "user", "content": "두 번째 논문 요약해줘"}
  ]
}
```

**2턴 응답:** `"Lee2024는 블루 OLED 열화 분석 논문입니다"`

**3턴 요청:**
```json
{
  "query": "저자가 누구야?",
  "messages": [
    {"role": "user", "content": "OLED 논문 최신 3편 알려줘"},
    {"role": "assistant", "content": "1) Kim2024, 2) Lee2024, 3) Park2024"},
    {"role": "user", "content": "두 번째 논문 요약해줘"},
    {"role": "assistant", "content": "Lee2024는 블루 OLED 열화 분석 논문입니다"},
    {"role": "user", "content": "저자가 누구야?"}
  ]
}
```

> 서버가 히스토리에서 "Lee2024"를 자동 추적하여 해당 논문의 저자 정보를 응답합니다.

### 예시 5: 멀티턴 + 스트리밍

```json
{
  "query": "이 논문의 실험 방법은?",
  "stream": true,
  "messages": [
    {"role": "user", "content": "OLED 논문 최신 3편 알려줘"},
    {"role": "assistant", "content": "1) Kim2024, 2) Lee2024, 3) Park2024"},
    {"role": "user", "content": "두 번째 논문 요약해줘"},
    {"role": "assistant", "content": "Lee2024는 블루 OLED 열화 분석 논문입니다"},
    {"role": "user", "content": "이 논문의 실험 방법은?"}
  ]
}
```

### 예시 6: 멀티턴 — 날짜 컨텍스트 자동 유지

```json
{
  "query": "몇 편이야?",
  "messages": [
    {"role": "user", "content": "최근 6개월 OLED 논문 보여줘"},
    {"role": "assistant", "content": "2025년 10월~2026년 3월 OLED 논문 15편입니다..."},
    {"role": "user", "content": "수명 관련 논문만 필터해줘"},
    {"role": "assistant", "content": "수명 관련 5편: 1) Kim2024 2) Lee2024..."},
    {"role": "user", "content": "몇 편이야?"}
  ]
}
```

> 3턴의 "몇 편이야?"에도 "최근 6개월" 기간 필터가 자동 적용됩니다.

### 예시 7: 날짜 필터 직접 지정

```json
{
  "query": "디스플레이 논문 목록",
  "filters": {"date_start": 20240101, "date_end": 20241231}
}
```

### 예시 8: 에이전트 지정 + 멀티턴 + 스트리밍 (모든 옵션 조합)

```json
{
  "query": "통계 다시 보여줘",
  "agent_type": "analytics",
  "stream": true,
  "user_id": "researcher-001",
  "messages": [
    {"role": "user", "content": "2024년 OLED 논문 몇 편이야?"},
    {"role": "assistant", "content": "2024년 OLED 논문은 총 42편입니다."},
    {"role": "user", "content": "통계 다시 보여줘"}
  ]
}
```

---

## 6. CLI 멀티턴 테스트

`scripts/cli.py`의 인터랙티브 모드에서 멀티턴 대화를 테스트할 수 있습니다.

### 실행

```bash
D:/WPy64-312101_paper/python/python.exe scripts/cli.py
```

### 명령어

| 명령 | 설명 |
|------|------|
| (텍스트 입력) | 질문 전송 (이전 대화 자동 포함) |
| `/new` | 새 대화 시작 (히스토리만 초기화) |
| `/history` | 현재 대화 히스토리 보기 |
| `/agents` | 에이전트 목록 보기 |
| `/use <agent>` | 에이전트 강제 지정 |
| `/filter <json>` | 날짜 필터 설정 |
| `/clear` | 에이전트 + 필터 + 히스토리 모두 초기화 |
| `/help` | 명령어 도움말 |
| `/quit` | 종료 |

### 멀티턴 테스트 예시

```
Co-Scientist Interactive CLI (type /help for commands)
============================================================

[턴 1] >>> OLED 논문 최신 3편 알려줘

============================================================
Agent: paper_qa
============================================================
1) Kim2024, 2) Lee2024, 3) Park2024

[턴 2] >>> 두 번째 논문 요약해줘

============================================================
Agent: paper_deep_dive
============================================================
Lee2024는 블루 OLED 열화 메커니즘을 분석한 논문입니다...

[턴 3] >>> 저자가 누구야?

============================================================
Agent: paper_qa
============================================================
Lee et al. (2024)의 저자 목록은...

[턴 4] >>> /new
새 대화를 시작합니다.

[턴 1] >>> 최근 6개월 디스플레이 트렌드는?
...
```

> 질문을 입력하면 이전 대화가 자동으로 `messages`에 누적되어 서버에 전달됩니다.
> `/new`로 새 대화를 시작하면 히스토리가 초기화됩니다.
> `/history`로 현재까지의 대화 내용을 확인할 수 있습니다.

---

## 7. 클라이언트 구현 코드

### Python — JSON 모드

```python
import requests

API_URL = "http://localhost:20035/api/chat"

class ChatClient:
    def __init__(self, user_id: str = "client-001"):
        self.user_id = user_id
        self.messages: list[dict] = []

    def chat(self, query: str, agent_type: str | None = None) -> dict:
        self.messages.append({"role": "user", "content": query})

        payload = {
            "query": query,
            "user_id": self.user_id,
            "messages": self.messages,
        }
        if agent_type:
            payload["agent_type"] = agent_type

        resp = requests.post(API_URL, json=payload)
        result = resp.json()

        self.messages.append({"role": "assistant", "content": result["answer"]})
        return result

    def reset(self):
        """새 대화 시작."""
        self.messages.clear()


# ── 사용 예시 ──
client = ChatClient(user_id="researcher-001")

r1 = client.chat("OLED 논문 최신 3편 알려줘")
print(r1["answer"])
# → "1) Kim2024, 2) Lee2024, 3) Park2024"

r2 = client.chat("두 번째 논문 요약해줘")
print(r2["answer"])
# → "Lee2024는 블루 OLED 열화 분석 논문입니다"

r3 = client.chat("저자가 누구야?")
print(r3["answer"])
# → "Lee et al. (2024)..."

client.reset()  # 새 대화
```

### Python — 스트리밍 모드

```python
import json
import requests

API_URL = "http://localhost:20035/api/chat"


class StreamingChatClient:
    """스트리밍과 멀티턴을 모두 지원하는 클라이언트."""

    def __init__(self, user_id: str = "client-001"):
        self.user_id = user_id
        self.messages: list[dict] = []

    def chat(self, query: str, stream: bool = True, agent_type: str | None = None):
        self.messages.append({"role": "user", "content": query})

        payload = {
            "query": query,
            "user_id": self.user_id,
            "stream": stream,
            "messages": self.messages,
        }
        if agent_type:
            payload["agent_type"] = agent_type

        if stream:
            result = self._stream_request(payload)
        else:
            resp = requests.post(API_URL, json=payload)
            result = resp.json()

        self.messages.append({"role": "assistant", "content": result["answer"]})
        return result

    def _stream_request(self, payload: dict) -> dict:
        full_answer = ""
        sources = []

        with requests.post(API_URL, json=payload, stream=True) as resp:
            resp.raise_for_status()
            event_type = None

            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("event: "):
                    event_type = line[7:]
                    continue
                if line.startswith("data: "):
                    data = json.loads(line[6:])

                    if event_type == "status":
                        print(f"\n[{data['message']}]")
                    elif event_type == "token":
                        print(data["content"], end="", flush=True)
                        full_answer += data["content"]
                    elif event_type == "sources":
                        sources = data["sources"]
                    elif event_type == "error":
                        print(f"\n[오류] {data['message']}")
                    elif event_type == "done":
                        print()
                        break

        return {"answer": full_answer, "sources": sources}

    def reset(self):
        self.messages.clear()


# ── 사용 예시 ──
client = StreamingChatClient(user_id="researcher-001")

r1 = client.chat("OLED 논문 최신 3편 알려줘")         # 스트리밍
r2 = client.chat("두 번째 논문 요약해줘")              # 스트리밍
r3 = client.chat("저자가 누구야?", stream=False)       # JSON 모드 전환
```

### JavaScript — JSON 모드

```javascript
const API_URL = "http://localhost:20035/api/chat";

class ChatClient {
  constructor(userId = "client-001") {
    this.userId = userId;
    this.messages = [];
  }

  async chat(query, agentType = null) {
    this.messages.push({ role: "user", content: query });

    const payload = {
      query,
      user_id: this.userId,
      messages: this.messages,
    };
    if (agentType) payload.agent_type = agentType;

    const resp = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await resp.json();

    this.messages.push({ role: "assistant", content: result.answer });
    return result;
  }

  reset() {
    this.messages = [];
  }
}

// 사용 예시
const client = new ChatClient("researcher-001");
const r1 = await client.chat("OLED 논문 최신 3편 알려줘");
const r2 = await client.chat("두 번째 논문 요약해줘");
const r3 = await client.chat("저자가 누구야?");
```

### JavaScript — 스트리밍 모드

```javascript
const API_URL = "http://localhost:20035/api/chat";

async function chatStream(query, messages = []) {
  const payload = { query, stream: true, messages };

  const resp = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();

  let fullAnswer = "";
  let sources = [];
  let eventType = null;
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7);
        continue;
      }
      if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice(6));

        switch (eventType) {
          case "status":
            console.log(`[상태] ${data.message}`);
            break;
          case "token":
            document.getElementById("answer").textContent += data.content;
            fullAnswer += data.content;
            break;
          case "sources":
            sources = data.sources;
            break;
          case "error":
            console.error(`[오류] ${data.message}`);
            break;
          case "done":
            return { answer: fullAnswer, sources };
        }
      }
    }
  }
  return { answer: fullAnswer, sources };
}

// 사용 예시
const msgs = [];

msgs.push({ role: "user", content: "OLED 논문 최신 3편 알려줘" });
const r1 = await chatStream("OLED 논문 최신 3편 알려줘", msgs);
msgs.push({ role: "assistant", content: r1.answer });

msgs.push({ role: "user", content: "두 번째 논문 요약해줘" });
const r2 = await chatStream("두 번째 논문 요약해줘", msgs);
msgs.push({ role: "assistant", content: r2.answer });
```

> 브라우저의 `EventSource` API는 GET만 지원하므로, `fetch` + `ReadableStream`을 사용합니다.

---

## 8. /api/chat vs /v1/chat/completions 비교

| 항목 | `/api/chat` | `/v1/chat/completions` |
|------|-------------|----------------------|
| 프로토콜 | 자체 포맷 | OpenAI-compatible |
| 인증 | Bearer token (동일 키) | Bearer token (동일 키) |
| 멀티턴 | `messages` 배열 | `messages` 배열 |
| **멀티턴 내부 처리** | **동일 (supervisor.build_history)** | **동일 (supervisor.build_history)** |
| 스트리밍 | SSE named events (`event: token`) | OpenAI SSE (`data: {choices:[...]}`) |
| 에이전트 지정 | `agent_type` 필드 | 미지원 (자동 분류) |
| 필터 지정 | `filters` 필드 | 미지원 |
| 진행 상태 알림 | `event: status` | 없음 |
| 주요 사용처 | 커스텀 클라이언트, CLI | Open WebUI, ChatGPT 호환 UI |

### 두 엔드포인트의 공통점

- **멀티턴 처리가 완전히 동일**: `build_history` 노드에서 동일한 로직(압축, 포맷팅, 턴 제한)
- **에이전트 동작이 동일**: 동일한 supervisor 파이프라인, 14개 에이전트, 날짜 파싱/의도 분류
- **차이는 입출력 포맷뿐**: `/api/chat`은 자체 JSON, `/v1/chat/completions`는 OpenAI 포맷

---

## 9. 에러 응답

### 422 Validation Error

```json
{
  "detail": [{"loc": ["body", "query"], "msg": "field required", "type": "value_error.missing"}]
}
```

### 500 Internal Server Error

```json
{"detail": "Internal server error"}
```

### 스트리밍 중 에러

```
event: error
data: {"message": "처리 중 오류 발생: Connection refused"}

event: done
data: {"stream_id": "a1b2c3d4e5f6"}
```

> 에러 이벤트 후 반드시 `done` 이벤트가 전송됩니다. 클라이언트는 `done`으로 스트림 종료를 판단하세요.

---

## 10. 서버 내부 처리 흐름

```
POST /api/chat                    POST /v1/chat/completions
  │ messages 배열                    │ messages 배열
  │ + query, filters,               │ (OpenAI 포맷)
  │   agent_type                    │
  └──────────┬───────────────────────┘
             ↓
  ┌─ Supervisor 파이프라인 (LangGraph) ─────────────────────┐
  │                                                         │
  │  ⓪ build_history                                       │
  │     messages 배열 → conversation_history 문자열 변환     │
  │     (압축, 최근 5턴 제한 — 두 엔드포인트 동일 로직)      │
  │                                                         │
  │  ① extract_dates                                        │
  │     날짜 파싱 (query + conversation_history 모두 검사)   │
  │                                                         │
  │  ② extract_conditions                                   │
  │     키워드/저자/DOI 추출 (LLM)                           │
  │                                                         │
  │  ③ classify_intent                                      │
  │     에이전트 분류 (conversation_history 포함)             │
  │                                                         │
  │  ④ route_to_agent                                       │
  │     14개 에이전트 중 하나 실행                            │
  │                                                         │
  │  ⑤ append_citation                                      │
  │     출처 + 저작권 고지 추가                               │
  └─────────────────────────────────────────────────────────┘
             ↓
  ┌─────────┴─────────┐
  │ /api/chat         │ /v1/chat/completions
  │ ChatResponse JSON │ OpenAI 포맷 JSON
  │ 또는 SSE stream   │ 또는 OpenAI SSE stream
  └───────────────────┘
```
