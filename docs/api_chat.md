# /api/chat API 명세서

> Co-Scientist Agent 채팅 엔드포인트 — 클라이언트 개발자용

## 기본 정보

| 항목 | 값 |
|------|-----|
| URL | `POST /api/chat` |
| Content-Type | `application/json` |
| 인증 | 없음 (내부 서비스용) |
| 서버 포트 | 20035 (기본값) |

---

## 요청 (Request)

### ChatRequest 스키마

```json
{
  "query": "string (필수)",
  "agent_type": "string | null (선택)",
  "user_id": "string | null (선택)",
  "filters": "object | null (선택)",
  "conversation_history": "string | null (선택)"
}
```

### 필드 상세

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `query` | `string` | **필수** | 사용자의 현재 질문 |
| `agent_type` | `string \| null` | 선택 | 에이전트 강제 지정. 생략 시 AI가 자동 분류 |
| `user_id` | `string \| null` | 선택 | 사용자 식별자 (트레이싱용) |
| `filters` | `object \| null` | 선택 | 날짜/조건 필터 직접 지정 |
| `conversation_history` | `string \| null` | 선택 | 이전 대화 히스토리 (멀티턴용) |

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

## 응답 (Response)

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

## 멀티턴 대화 구현 가이드

### 핵심 원칙

> **서버는 stateless입니다.** 대화 상태를 서버가 저장하지 않습니다.
> 클라이언트가 이전 대화를 `conversation_history` 필드에 문자열로 조립하여 매 요청마다 전송해야 합니다.

### conversation_history 포맷

```
사용자: {1턴 질문}
어시스턴트: {1턴 답변}
사용자: {2턴 질문}
어시스턴트: {2턴 답변}
```

- 각 턴은 `사용자: ` 또는 `어시스턴트: ` 접두사로 시작
- 현재 질문은 포함하지 않음 (`query`에 별도 전달)
- 최대 **5턴(10개 항목)** 권장 — 너무 길면 LLM 컨텍스트 낭비
- 어시스턴트 답변이 길 경우 **앞 400자 + 뒤 400자로 압축** 권장 (중간 생략)

### 압축 예시

어시스턴트 답변이 800자를 초과하면:

```
어시스턴트: OLED 수명 관련 최신 연구를 정리하면 다음과 같습니다. 1) Kim et al. (2024)은 새로운 호스트 재료를 사용하여...(처음 400자)
...(중략)...
따라서 OLED 수명 개선의 핵심은 호스트-도펀트 상호작용 최적화에 있습니다. [출처: Kim2024, Lee2023, Park2024](마지막 400자)
```

---

## 사용 예시

### 예시 1: 단일 질문 (멀티턴 없음)

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

### 예시 3: 멀티턴 대화 — 2턴째

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
  "conversation_history": "사용자: OLED 수명 관련 최신 논문 알려줘\n어시스턴트: OLED 수명 관련 최신 논문을 정리하면 다음과 같습니다.\n\n1. **Enhanced OLED Lifetime via Novel Host Materials** (Kim et al., 2024)\n   - 새로운 호스트 재료로 수명 30% 향상...\n\n2. **Degradation Mechanism in Blue OLED** (Lee et al., 2024)\n   - 블루 OLED 열화 메커니즘 분석..."
}
```

> 서버는 `conversation_history`에서 "Enhanced OLED Lifetime via Novel Host Materials"라는 논문 제목을 자동 추출하여, "첫 번째 논문"이 어떤 논문인지 이해합니다.

---

### 예시 4: 멀티턴 대화 — 3턴째 (날짜 컨텍스트 유지)

**1턴:** "최근 6개월 OLED 논문 보여줘"
**2턴:** "그 중에서 수명 관련 논문만 필터해줘"
**3턴:** "몇 편이야?"

**3턴 요청:**
```json
{
  "query": "몇 편이야?",
  "user_id": "researcher-001",
  "conversation_history": "사용자: 최근 6개월 OLED 논문 보여줘\n어시스턴트: 2025년 10월부터 2026년 3월까지의 OLED 논문 15편을 찾았습니다...(중략)...\n사용자: 그 중에서 수명 관련 논문만 필터해줘\n어시스턴트: 수명 관련 논문 5편을 필터했습니다. 1) Kim2024... 2) Lee2024..."
}
```

> 서버는 히스토리에서 "최근 6개월"이라는 날짜 표현을 추출하여, 3턴의 "몇 편이야?"에도 동일한 기간 필터를 적용합니다.

---

### 예시 5: 날짜 필터 직접 지정

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

2. **요청 시 문자열로 변환**
   - 배열을 `"사용자: ...\n어시스턴트: ..."` 포맷의 문자열로 조립
   - 현재 질문은 `conversation_history`에 포함하지 않음

3. **어시스턴트 답변 압축**
   - 800자 초과 시: 앞 400자 + `\n...(중략)...\n` + 뒤 400자
   - 논문 제목과 결론이 앞뒤에 위치하므로 이 방식이 효과적

4. **최대 턴 수 제한**
   - 최근 5턴(사용자 5개 + 어시스턴트 5개 = 10항목)만 유지
   - 오래된 턴은 앞에서부터 제거

5. **새 대화 시작**
   - `conversation_history`를 `null` 또는 생략하면 새 대화로 처리

### Python 클라이언트 예시

```python
import requests

API_URL = "http://localhost:20035/api/chat"

class ChatClient:
    def __init__(self, user_id: str = "client-001"):
        self.user_id = user_id
        self.history: list[dict] = []  # [{role, content}]

    def chat(self, query: str, agent_type: str | None = None) -> dict:
        # 히스토리 → 문자열 변환
        conversation_history = None
        if self.history:
            lines = []
            for turn in self.history[-10:]:  # 최근 5턴
                label = "사용자" if turn["role"] == "user" else "어시스턴트"
                content = turn["content"]
                if turn["role"] == "assistant" and len(content) > 800:
                    content = content[:400] + "\n...(중략)...\n" + content[-400:]
                lines.append(f"{label}: {content}")
            conversation_history = "\n".join(lines)

        # 요청
        payload = {
            "query": query,
            "user_id": self.user_id,
        }
        if agent_type:
            payload["agent_type"] = agent_type
        if conversation_history:
            payload["conversation_history"] = conversation_history

        resp = requests.post(API_URL, json=payload)
        result = resp.json()

        # 히스토리 업데이트
        self.history.append({"role": "user", "content": query})
        self.history.append({"role": "assistant", "content": result["answer"]})

        return result

    def reset(self):
        """새 대화 시작."""
        self.history.clear()


# 사용 예시
client = ChatClient(user_id="researcher-001")

# 1턴
r1 = client.chat("OLED 수명 관련 최신 논문 알려줘")
print(r1["answer"])

# 2턴 (멀티턴 — 히스토리 자동 포함)
r2 = client.chat("첫 번째 논문 좀 더 자세히 분석해줘")
print(r2["answer"])

# 3턴
r3 = client.chat("이 논문의 실험 방법은?")
print(r3["answer"])

# 새 대화
client.reset()
r4 = client.chat("2024년 논문 통계 보여줘", agent_type="analytics")
```

### JavaScript (fetch) 클라이언트 예시

```javascript
const API_URL = "http://localhost:20035/api/chat";

class ChatClient {
  constructor(userId = "client-001") {
    this.userId = userId;
    this.history = []; // [{role, content}]
  }

  async chat(query, agentType = null) {
    // 히스토리 → 문자열 변환
    let conversationHistory = null;
    if (this.history.length > 0) {
      const recentTurns = this.history.slice(-10); // 최근 5턴
      const lines = recentTurns.map((turn) => {
        const label = turn.role === "user" ? "사용자" : "어시스턴트";
        let content = turn.content;
        if (turn.role === "assistant" && content.length > 800) {
          content =
            content.slice(0, 400) + "\n...(중략)...\n" + content.slice(-400);
        }
        return `${label}: ${content}`;
      });
      conversationHistory = lines.join("\n");
    }

    // 요청
    const payload = {
      query,
      user_id: this.userId,
    };
    if (agentType) payload.agent_type = agentType;
    if (conversationHistory)
      payload.conversation_history = conversationHistory;

    const resp = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await resp.json();

    // 히스토리 업데이트
    this.history.push({ role: "user", content: query });
    this.history.push({ role: "assistant", content: result.answer });

    return result;
  }

  reset() {
    this.history = [];
  }
}

// 사용 예시
const client = new ChatClient("researcher-001");

const r1 = await client.chat("OLED 수명 관련 최신 논문 알려줘");
console.log(r1.answer);

const r2 = await client.chat("첫 번째 논문 좀 더 자세히 분석해줘");
console.log(r2.answer);
```

---

## /api/chat vs /v1/chat/completions 비교

| 항목 | `/api/chat` | `/v1/chat/completions` |
|------|-------------|----------------------|
| 프로토콜 | 자체 포맷 | OpenAI-compatible |
| 인증 | 없음 | Bearer token |
| 멀티턴 | 클라이언트가 `conversation_history` 문자열 전달 | 클라이언트가 `messages` 배열 전달, 서버가 자동 조립 |
| 스트리밍 | 미지원 | `stream: true` 지원 |
| 에이전트 지정 | `agent_type` 필드 | 미지원 (항상 자동 분류) |
| 날짜 필터 직접 지정 | `filters` 필드 | 미지원 |
| 주요 사용처 | 커스텀 클라이언트, CLI, 내부 서비스 | Open WebUI, ChatGPT 호환 UI |

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

---

## 서버 내부 처리 흐름

```
클라이언트 요청
  ↓
POST /api/chat (ChatRequest)
  ↓
state 구성:
  - query ← request.query
  - metadata.conversation_history ← request.conversation_history
  - metadata.agent_type ← request.agent_type
  ↓
Supervisor 파이프라인 (LangGraph):
  ① extract_dates — 날짜 파싱 (query + conversation_history 모두 검사)
  ② extract_conditions — 키워드/저자/DOI 추출 (LLM)
  ③ classify_intent — 에이전트 분류 (conversation_history 포함하여 판단)
  ④ route_to_agent — 에이전트 실행
  ⑤ add_citation — 출처 추가
  ↓
ChatResponse {answer, sources, trace_id}
```
