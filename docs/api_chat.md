# /api/chat API 명세서

> Co-Scientist Agent 채팅 엔드포인트 — 클라이언트 개발자용

## 기본 정보

| 항목 | 값 |
|------|-----|
| URL | `POST /api/chat` |
| Content-Type | `application/json` |
| 인증 | 없음 (내부 서비스용) |
| 서버 포트 | 20035 (기본값) |
| 응답 모드 | JSON 일괄 응답 (기본) / SSE 스트리밍 (`stream: true`) |

---

## 요청 (Request)

### ChatRequest 스키마

```json
{
  "query": "string (필수)",
  "agent_type": "string | null (선택)",
  "user_id": "string | null (선택)",
  "filters": "object | null (선택)",
  "messages": [{"role": "user|assistant", "content": "string"}] | null (선택)",
  "stream": "boolean (선택, 기본값: false)"
}
```

### 필드 상세

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `query` | `string` | **필수** | - | 사용자의 현재 질문 |
| `agent_type` | `string \| null` | 선택 | `null` | 에이전트 강제 지정. 생략 시 AI가 자동 분류 |
| `user_id` | `string \| null` | 선택 | `null` | 사용자 식별자 (트레이싱용) |
| `filters` | `object \| null` | 선택 | `null` | 날짜/조건 필터 직접 지정 |
| `messages` | `list[ChatMessage] \| null` | 선택 | `null` | **이전 대화 히스토리 (멀티턴용, 권장 방식)** |
| `stream` | `boolean` | 선택 | `false` | `true`: SSE 스트리밍, `false`: JSON 일괄 응답 |

### messages (멀티턴 대화 — 권장 방식)

`messages`는 이전 대화를 `{role, content}` 배열로 전달합니다. `/v1/chat/completions`(OpenAI 포맷)와 동일한 구조이므로, 두 엔드포인트를 동일한 방식으로 사용할 수 있습니다.

```json
{
  "query": "첫 번째 논문 자세히 분석해줘",
  "messages": [
    {"role": "user", "content": "OLED 수명 관련 최신 논문 알려줘"},
    {"role": "assistant", "content": "OLED 수명 관련 최신 논문을 정리하면..."},
    {"role": "user", "content": "첫 번째 논문 자세히 분석해줘"}
  ]
}
```

**중요 규칙:**
- `messages`의 마지막 항목은 현재 질문(`query`와 동일)이어야 합니다
- 서버가 내부에서 마지막 user 메시지를 제외하고, 나머지를 히스토리로 변환합니다
- 어시스턴트 답변이 800자를 초과하면 **서버가 자동으로 앞 400자 + 뒤 400자로 압축**합니다
- 최대 **5턴(10개 항목)** 까지 처리합니다 (초과 시 오래된 턴 자동 제거)
- **클라이언트는 원본 대화를 그대로 보내면 됩니다** — 압축/포맷팅은 서버가 처리

> 💡 이 방식은 `/v1/chat/completions`와 내부 처리가 **완전히 동일**합니다.
> 두 엔드포인트 모두 supervisor의 `build_history` 노드에서 동일한 로직으로 히스토리를 변환합니다.

### conversation_history (하위 호환용)

기존에 `conversation_history` 문자열을 직접 전달하던 클라이언트를 위해 하위 호환을 유지합니다.
**`messages`가 있으면 `conversation_history`는 무시됩니다.**

```json
{
  "query": "첫 번째 논문 자세히 분석해줘",
  "conversation_history": "사용자: OLED 수명 관련 최신 논문 알려줘\n어시스턴트: OLED 수명 관련..."
}
```

> ⚠️ 새 클라이언트는 `messages` 방식을 사용하세요. `conversation_history`는 향후 제거될 수 있습니다.

### agent_type 허용 값 (14개)

| Phase | agent_type 값 | 설명 |
|-------|---------------|------|
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

---

## 응답 — 모드 1: JSON 일괄 응답 (`stream: false`)

`stream`이 `false`(기본값)이면 처리가 완료된 후 JSON 객체 하나를 반환합니다.

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
| `sources` | `list[SourceDocument] \| null` | 참조한 논문 목록 (검색 기반 에이전트일 때) |
| `sources[].paper_id` | `string` | 논문 고유 ID |
| `sources[].title` | `string` | 논문 제목 |
| `sources[].doi` | `string \| null` | DOI |
| `sources[].chunk_id` | `int` | 청크 번호 (0부터 시작) |
| `sources[].chunk_text` | `string` | 검색된 청크 텍스트 |
| `sources[].score` | `float` | 유사도 점수 (0~1, 높을수록 관련성 높음) |
| `trace_id` | `string \| null` | Langfuse 트레이싱 ID (디버깅용) |

---

## 응답 — 모드 2: SSE 스트리밍 (`stream: true`)

`stream`이 `true`이면 `text/event-stream` (Server-Sent Events) 형식으로 응답합니다.
답변이 완성될 때까지 기다리지 않고, **토큰이 생성되는 즉시** 클라이언트에 전달됩니다.

### 스트리밍 동작 과정

```
클라이언트 요청 (stream: true)
  ↓
[event: status]  "논문 검색 및 질문 분석 중..."     ← 검색/분류 시작
  ↓
  ... (서버에서 논문 검색 + 의도 분류 진행, 수 초 소요) ...
  ↓
[event: status]  "답변 생성 중..."                  ← LLM 답변 생성 시작
  ↓
[event: token]   "OLED"                            ← 토큰 1개
[event: token]   " 수명"                           ← 토큰 1개
[event: token]   " 관련"                           ← 토큰 1개
[event: token]   "..."                             ← ... (계속)
  ↓
[event: token]   "\n\n---\n📚 참조 논문..."          ← 출처 정보
  ↓
[event: sources]  [{paper_id, title, ...}, ...]    ← 논문 목록 (구조화된 데이터)
  ↓
[event: done]    {stream_id: "abc123"}             ← 스트리밍 완료
```

### SSE 이벤트 종류

| event 타입 | data 형식 | 설명 | 수신 횟수 |
|-----------|-----------|------|----------|
| `status` | `{"message": "..."}` | 현재 처리 단계 안내 | 1~2회 |
| `token` | `{"content": "..."}` | LLM이 생성한 토큰 1개 | 다수 (수십~수백 회) |
| `sources` | `{"sources": [...]}` | 참조 논문 목록 (SourceDocument 배열) | 0~1회 |
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

### 클라이언트에서 전체 답변 조립하기

스트리밍 모드에서 **전체 답변 텍스트**를 얻으려면, `token` 이벤트의 `content`를 순서대로 이어붙이면 됩니다.

```
전체 답변 = token[0].content + token[1].content + token[2].content + ...
```

---

## 멀티턴 대화 구현 가이드

### 핵심 원칙

> **서버는 stateless입니다.** 대화 상태를 서버가 저장하지 않습니다.
> 클라이언트가 이전 대화를 `messages` 배열로 매 요청마다 전송해야 합니다.
> 히스토리 압축과 포맷팅은 **서버 내부(supervisor)**에서 자동 처리됩니다.

### 내부 처리 흐름

```
클라이언트: messages 배열 전송
  ↓
supervisor.build_history 노드:
  1. 마지막 user 메시지 제외 (query에 별도 전달)
  2. 최근 5턴(10항목)만 유지
  3. assistant 답변 800자 초과 시 앞400자 + 뒤400자로 압축
  4. "사용자: ...\n어시스턴트: ..." 포맷으로 변환
  ↓
supervisor.extract_dates:
  - conversation_history에서도 날짜 표현 추출
  ↓
supervisor.classify_intent:
  - conversation_history를 포함하여 의도 분류
  ↓
각 에이전트:
  - conversation_history에서 논문 제목 자동 추적
```

> 이 흐름은 `/api/chat`과 `/v1/chat/completions` 모두 **동일**합니다.

---

## 사용 예시

### 예시 1: 단일 질문 (JSON 모드)

**요청:**
```bash
curl -X POST http://localhost:20035/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "OLED 수명 관련 최신 논문 알려줘"
  }'
```

**응답:**
```json
{
  "answer": "OLED 수명 관련 최신 논문을 정리하면 다음과 같습니다...",
  "sources": [
    {
      "paper_id": "SID2024-001",
      "title": "Enhanced OLED Lifetime via Novel Host Materials",
      "doi": "10.1002/jsid.1234",
      "chunk_id": 0,
      "chunk_text": "We demonstrate a novel host material...",
      "score": 0.92
    }
  ],
  "trace_id": "abc123-def456"
}
```

---

### 예시 2: 에이전트 직접 지정

**요청:**
```bash
curl -X POST http://localhost:20035/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "2024년 OLED 논문 몇 편이야?",
    "agent_type": "analytics"
  }'
```

---

### 예시 3: 스트리밍 모드

**요청:**
```bash
curl -N -X POST http://localhost:20035/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "OLED 수명 관련 최신 논문 알려줘",
    "stream": true
  }'
```

> `-N` 플래그: curl의 출력 버퍼링을 비활성화하여 SSE 이벤트를 실시간으로 확인

---

### 예시 4: 멀티턴 대화 — 2턴째 (messages 방식)

시나리오: 1턴에서 OLED 논문을 검색하고, 2턴에서 후속 질문

**1턴 요청:**
```json
{
  "query": "OLED 수명 관련 최신 논문 알려줘",
  "user_id": "researcher-001"
}
```

**1턴 응답:**
```json
{
  "answer": "OLED 수명 관련 최신 논문을 정리하면 다음과 같습니다.\n\n1. **Enhanced OLED Lifetime via Novel Host Materials** (Kim et al., 2024)\n   - 새로운 호스트 재료로 수명 30% 향상...\n\n2. **Degradation Mechanism in Blue OLED** (Lee et al., 2024)\n   - 블루 OLED 열화 메커니즘 분석...",
  "sources": [...],
  "trace_id": "trace-001"
}
```

**2턴 요청 (멀티턴):**
```json
{
  "query": "첫 번째 논문 좀 더 자세히 분석해줘",
  "user_id": "researcher-001",
  "messages": [
    {"role": "user", "content": "OLED 수명 관련 최신 논문 알려줘"},
    {"role": "assistant", "content": "OLED 수명 관련 최신 논문을 정리하면 다음과 같습니다.\n\n1. **Enhanced OLED Lifetime via Novel Host Materials** (Kim et al., 2024)\n   - 새로운 호스트 재료로 수명 30% 향상...\n\n2. **Degradation Mechanism in Blue OLED** (Lee et al., 2024)\n   - 블루 OLED 열화 메커니즘 분석..."},
    {"role": "user", "content": "첫 번째 논문 좀 더 자세히 분석해줘"}
  ]
}
```

> 클라이언트는 이전 응답 원본을 그대로 `messages`에 넣으면 됩니다.
> 서버가 자동으로 압축하고 히스토리를 구성합니다.

---

### 예시 5: 멀티턴 + 스트리밍

**요청:**
```json
{
  "query": "이 논문의 실험 방법은?",
  "stream": true,
  "user_id": "researcher-001",
  "messages": [
    {"role": "user", "content": "OLED 수명 관련 최신 논문 알려줘"},
    {"role": "assistant", "content": "1. Enhanced OLED Lifetime via Novel Host Materials (Kim et al., 2024)..."},
    {"role": "user", "content": "첫 번째 논문 좀 더 자세히 분석해줘"},
    {"role": "assistant", "content": "Enhanced OLED Lifetime via Novel Host Materials 논문의 핵심 내용은..."},
    {"role": "user", "content": "이 논문의 실험 방법은?"}
  ]
}
```

> 스트리밍과 멀티턴은 동시에 사용할 수 있습니다.

---

### 예시 6: 멀티턴 — 날짜 컨텍스트 유지

**1턴:** "최근 6개월 OLED 논문 보여줘"
**2턴:** "그 중에서 수명 관련 논문만 필터해줘"
**3턴:** "몇 편이야?"

**3턴 요청:**
```json
{
  "query": "몇 편이야?",
  "user_id": "researcher-001",
  "messages": [
    {"role": "user", "content": "최근 6개월 OLED 논문 보여줘"},
    {"role": "assistant", "content": "2025년 10월부터 2026년 3월까지의 OLED 논문 15편을 찾았습니다..."},
    {"role": "user", "content": "그 중에서 수명 관련 논문만 필터해줘"},
    {"role": "assistant", "content": "수명 관련 논문 5편을 필터했습니다. 1) Kim2024... 2) Lee2024..."},
    {"role": "user", "content": "몇 편이야?"}
  ]
}
```

> 서버는 히스토리에서 "최근 6개월"이라는 날짜 표현을 자동 추출하여, 3턴의 "몇 편이야?"에도 동일한 기간 필터를 적용합니다.

---

### 예시 7: 날짜 필터 직접 지정

**요청:**
```json
{
  "query": "디스플레이 논문 목록",
  "filters": {
    "date_start": 20240101,
    "date_end": 20241231
  }
}
```

> `filters`를 직접 지정하면 날짜 파싱 단계를 건너뜁니다.

---

## 클라이언트 구현 참고사항

### 멀티턴 구현 체크리스트

1. **대화 히스토리 배열 관리**
   - 클라이언트 측에서 `[{role, content}]` 형태로 대화를 저장

2. **요청 시 `messages` 배열에 그대로 전달**
   - 현재 질문도 마지막 항목으로 포함
   - 이전 답변은 원본 그대로 (서버가 알아서 압축함)

3. **새 대화 시작**
   - `messages`를 생략하면 새 대화로 처리

4. **스트리밍 모드에서의 히스토리**
   - `token` 이벤트들의 `content`를 이어붙여 전체 답변 완성
   - `done` 이벤트 수신 후, 전체 답변을 히스토리에 추가

### Python 클라이언트 예시 — JSON 모드

```python
import requests

API_URL = "http://localhost:20035/api/chat"

class ChatClient:
    def __init__(self, user_id: str = "client-001"):
        self.user_id = user_id
        self.messages: list[dict] = []

    def chat(self, query: str, agent_type: str | None = None) -> dict:
        # 현재 질문을 messages에 추가
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

        # 응답을 messages에 추가
        self.messages.append({"role": "assistant", "content": result["answer"]})

        return result

    def reset(self):
        """새 대화 시작."""
        self.messages.clear()


# 사용 예시
client = ChatClient(user_id="researcher-001")

# 1턴
r1 = client.chat("OLED 수명 관련 최신 논문 알려줘")
print(r1["answer"])

# 2턴 (멀티턴 — messages 자동 포함)
r2 = client.chat("첫 번째 논문 좀 더 자세히 분석해줘")
print(r2["answer"])

# 3턴
r3 = client.chat("이 논문의 실험 방법은?")
print(r3["answer"])

# 새 대화
client.reset()
r4 = client.chat("2024년 논문 통계 보여줘", agent_type="analytics")
```

### Python 클라이언트 예시 — 스트리밍 모드

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
        # 현재 질문을 messages에 추가
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

        # 응답을 messages에 추가
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

# 스트리밍 모드 (기본)
r1 = client.chat("OLED 수명 관련 최신 논문 알려줘")
r2 = client.chat("첫 번째 논문 자세히 분석해줘")

# JSON 모드로 전환
r3 = client.chat("몇 편이야?", stream=False)
print(r3["answer"])
```

### JavaScript (fetch) 클라이언트 예시 — JSON 모드

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
```

### JavaScript (fetch) 클라이언트 예시 — 스트리밍 모드

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
    buffer = lines.pop(); // 마지막 불완전한 줄은 버퍼에 유지

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
            // 화면에 토큰 즉시 표시
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
```

> 주의: 브라우저의 `EventSource` API는 GET 요청만 지원하므로, `fetch` + `ReadableStream` 방식을 사용해야 합니다.

---

## /api/chat vs /v1/chat/completions 비교

| 항목 | `/api/chat` | `/v1/chat/completions` |
|------|-------------|----------------------|
| 프로토콜 | 자체 포맷 | OpenAI-compatible |
| 인증 | 없음 | Bearer token |
| 멀티턴 | `messages` 배열 전달 | `messages` 배열 전달 |
| **멀티턴 내부 처리** | **동일 (supervisor.build_history)** | **동일 (supervisor.build_history)** |
| 스트리밍 | `stream: true` → SSE (named events) | `stream: true` → SSE (OpenAI 포맷) |
| SSE 포맷 | `event: token\ndata: {"content": "..."}` | `data: {"choices": [{"delta": {"content": "..."}}]}` |
| 에이전트 지정 | `agent_type` 필드 | 미지원 (항상 자동 분류) |
| 날짜 필터 직접 지정 | `filters` 필드 | 미지원 |
| 진행 상태 알림 | `event: status` 이벤트 | 없음 |
| 주요 사용처 | 커스텀 클라이언트, CLI, 내부 서비스 | Open WebUI, ChatGPT 호환 UI |

### 두 엔드포인트의 공통점

- **멀티턴 처리가 완전히 동일**: 두 엔드포인트 모두 `messages` 배열을 supervisor에 전달하고, `build_history` 노드에서 동일한 로직(압축, 포맷팅, 턴 제한)으로 `conversation_history` 문자열을 생성
- **에이전트 동작이 동일**: 동일한 supervisor 파이프라인, 동일한 14개 에이전트, 동일한 날짜 파싱/의도 분류 로직
- **차이는 입출력 포맷뿐**: `/api/chat`은 자체 JSON, `/v1/chat/completions`는 OpenAI 포맷

---

## 에러 응답

### 422 Validation Error (필수 필드 누락)

```json
{
  "detail": [
    {
      "loc": ["body", "query"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 500 Internal Server Error (서버 내부 오류)

```json
{
  "detail": "Internal server error"
}
```

### 스트리밍 중 에러

```
event: error
data: {"message": "처리 중 오류 발생: Connection refused"}

event: done
data: {"stream_id": "a1b2c3d4e5f6"}
```

---

## 서버 내부 처리 흐름

### 통합 파이프라인 (두 엔드포인트 공통)

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
