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
  "conversation_history": "string | null (선택)",
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
| `conversation_history` | `string \| null` | 선택 | `null` | 이전 대화 히스토리 (멀티턴용) |
| `stream` | `boolean` | 선택 | `false` | `true`: SSE 스트리밍, `false`: JSON 일괄 응답 |

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

event: token
data: {"content": "1. **Enhanced OLED Lifetime"}

event: token
data: {"content": " via Novel Host Materials**"}

event: token
data: {"content": "\n\n---\n📚 **참조 논문**\n- Enhanced OLED Lifetime... (DOI: 10.1002/jsid.1234)\n\n⚠️ 저작권 고지: ..."}

event: sources
data: {"sources": [{"paper_id": "SID2024-001", "title": "Enhanced OLED Lifetime via Novel Host Materials", "doi": "10.1002/jsid.1234", "chunk_id": 0, "chunk_text": "We demonstrate...", "score": 0.92}]}

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

### 스트리밍 모드에서의 멀티턴

스트리밍 모드(`stream: true`)에서도 `conversation_history`는 동일하게 사용됩니다.
단, 스트리밍 응답에서 전체 답변을 조립한 후 히스토리에 추가해야 합니다.

```
1. token 이벤트들의 content를 이어붙여 전체 답변 완성
2. done 이벤트 수신 후, 전체 답변을 히스토리에 추가
3. 다음 요청 시 conversation_history에 포함
```

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

**응답 (SSE):**
```
event: status
data: {"message": "논문 검색 및 질문 분석 중..."}

event: status
data: {"message": "답변 생성 중..."}

event: token
data: {"content": "OLED 수명 관련 최신 논문을"}

event: token
data: {"content": " 정리하면 다음과 같습니다."}

...

event: sources
data: {"sources": [{"paper_id": "SID2024-001", "title": "Enhanced OLED Lifetime via Novel Host Materials", "doi": "10.1002/jsid.1234", "chunk_id": 0, "chunk_text": "...", "score": 0.92}]}

event: done
data: {"stream_id": "a1b2c3d4e5f6"}
```

---

### 예시 4: 멀티턴 대화 — 2턴째

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

### 예시 5: 멀티턴 + 스트리밍

**요청:**
```json
{
  "query": "이 논문의 실험 방법은?",
  "stream": true,
  "user_id": "researcher-001",
  "conversation_history": "사용자: OLED 수명 관련 최신 논문 알려줘\n어시스턴트: 1. Enhanced OLED Lifetime via Novel Host Materials (Kim et al., 2024)...\n사용자: 첫 번째 논문 좀 더 자세히 분석해줘\n어시스턴트: Enhanced OLED Lifetime via Novel Host Materials 논문의 핵심 내용은..."
}
```

> 스트리밍과 멀티턴은 동시에 사용할 수 있습니다. 이전 대화를 `conversation_history`에 넣고 `stream: true`로 요청하면 됩니다.

---

### 예시 6: 멀티턴 대화 — 3턴째 (날짜 컨텍스트 유지)

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

### Python 클라이언트 예시 — JSON 모드

```python
import requests

API_URL = "http://localhost:20035/api/chat"

class ChatClient:
    def __init__(self, user_id: str = "client-001"):
        self.user_id = user_id
        self.history: list[dict] = []  # [{role, content}]

    def chat(self, query: str, agent_type: str | None = None) -> dict:
        # 히스토리 → 문자열 변환
        conversation_history = self._build_history()

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

    def _build_history(self) -> str | None:
        if not self.history:
            return None
        lines = []
        for turn in self.history[-10:]:  # 최근 5턴
            label = "사용자" if turn["role"] == "user" else "어시스턴트"
            content = turn["content"]
            if turn["role"] == "assistant" and len(content) > 800:
                content = content[:400] + "\n...(중략)...\n" + content[-400:]
            lines.append(f"{label}: {content}")
        return "\n".join(lines)

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

### Python 클라이언트 예시 — 스트리밍 모드

```python
import json
import requests

API_URL = "http://localhost:20035/api/chat"


def chat_stream(query: str, conversation_history: str | None = None):
    """SSE 스트리밍으로 답변을 토큰 단위로 수신한다."""
    payload = {
        "query": query,
        "stream": True,
    }
    if conversation_history:
        payload["conversation_history"] = conversation_history

    full_answer = ""
    sources = []

    # stream=True로 응답을 줄 단위로 읽음
    with requests.post(API_URL, json=payload, stream=True) as resp:
        resp.raise_for_status()

        event_type = None
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue

            # SSE 파싱: "event: xxx" 또는 "data: {...}"
            if line.startswith("event: "):
                event_type = line[7:]
                continue

            if line.startswith("data: "):
                data = json.loads(line[6:])

                if event_type == "status":
                    print(f"[상태] {data['message']}")

                elif event_type == "token":
                    # 토큰을 즉시 출력 (줄바꿈 없이 이어붙임)
                    print(data["content"], end="", flush=True)
                    full_answer += data["content"]

                elif event_type == "sources":
                    sources = data["sources"]

                elif event_type == "error":
                    print(f"\n[오류] {data['message']}")

                elif event_type == "done":
                    print()  # 마지막 줄바꿈
                    break

    return {"answer": full_answer, "sources": sources}


# ── 사용 예시 ──

# 1턴: 스트리밍으로 답변 수신
print("=== 1턴 ===")
r1 = chat_stream("OLED 수명 관련 최신 논문 알려줘")

# 2턴: 히스토리 포함 스트리밍
print("\n=== 2턴 ===")
history = f"사용자: OLED 수명 관련 최신 논문 알려줘\n어시스턴트: {r1['answer']}"
r2 = chat_stream("첫 번째 논문 자세히 분석해줘", conversation_history=history)
```

### Python 클라이언트 예시 — 스트리밍 + 멀티턴 통합 클래스

```python
import json
import requests

API_URL = "http://localhost:20035/api/chat"


class StreamingChatClient:
    """스트리밍과 멀티턴을 모두 지원하는 클라이언트."""

    def __init__(self, user_id: str = "client-001"):
        self.user_id = user_id
        self.history: list[dict] = []

    def chat(self, query: str, stream: bool = True, agent_type: str | None = None):
        """질문을 보내고 답변을 받는다.

        Args:
            query: 사용자 질문
            stream: True면 토큰 단위 스트리밍, False면 일괄 응답
            agent_type: 에이전트 강제 지정 (생략 시 자동 분류)

        Returns:
            dict: {"answer": str, "sources": list}
        """
        payload = {
            "query": query,
            "user_id": self.user_id,
            "stream": stream,
        }
        if agent_type:
            payload["agent_type"] = agent_type

        history_str = self._build_history()
        if history_str:
            payload["conversation_history"] = history_str

        if stream:
            result = self._stream_request(payload)
        else:
            resp = requests.post(API_URL, json=payload)
            result = resp.json()

        # 히스토리 업데이트
        self.history.append({"role": "user", "content": query})
        self.history.append({"role": "assistant", "content": result["answer"]})

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

    def _build_history(self) -> str | None:
        if not self.history:
            return None
        lines = []
        for turn in self.history[-10:]:
            label = "사용자" if turn["role"] == "user" else "어시스턴트"
            content = turn["content"]
            if turn["role"] == "assistant" and len(content) > 800:
                content = content[:400] + "\n...(중략)...\n" + content[-400:]
            lines.append(f"{label}: {content}")
        return "\n".join(lines)

    def reset(self):
        self.history.clear()


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
    this.history = []; // [{role, content}]
  }

  async chat(query, agentType = null) {
    const payload = {
      query,
      user_id: this.userId,
    };
    if (agentType) payload.agent_type = agentType;

    const historyStr = this._buildHistory();
    if (historyStr) payload.conversation_history = historyStr;

    const resp = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await resp.json();

    this.history.push({ role: "user", content: query });
    this.history.push({ role: "assistant", content: result.answer });

    return result;
  }

  _buildHistory() {
    if (this.history.length === 0) return null;
    const recent = this.history.slice(-10);
    const lines = recent.map((turn) => {
      const label = turn.role === "user" ? "사용자" : "어시스턴트";
      let content = turn.content;
      if (turn.role === "assistant" && content.length > 800) {
        content =
          content.slice(0, 400) + "\n...(중략)...\n" + content.slice(-400);
      }
      return `${label}: ${content}`;
    });
    return lines.join("\n");
  }

  reset() {
    this.history = [];
  }
}
```

### JavaScript (fetch) 클라이언트 예시 — 스트리밍 모드

```javascript
const API_URL = "http://localhost:20035/api/chat";

async function chatStream(query, conversationHistory = null) {
  const payload = { query, stream: true };
  if (conversationHistory) {
    payload.conversation_history = conversationHistory;
  }

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
            // 화면에 토큰 즉시 표시 (예: DOM에 추가)
            process.stdout.write(data.content); // Node.js
            // document.getElementById('answer').textContent += data.content;  // 브라우저
            fullAnswer += data.content;
            break;
          case "sources":
            sources = data.sources;
            break;
          case "error":
            console.error(`[오류] ${data.message}`);
            break;
          case "done":
            console.log("\n[완료]");
            return { answer: fullAnswer, sources };
        }
      }
    }
  }
  return { answer: fullAnswer, sources };
}

// 사용 예시
const r1 = await chatStream("OLED 수명 관련 최신 논문 알려줘");
const r2 = await chatStream(
  "첫 번째 논문 자세히 분석해줘",
  `사용자: OLED 수명 관련 최신 논문 알려줘\n어시스턴트: ${r1.answer}`
);
```

### JavaScript — 브라우저 EventSource 사용 (GET 불가, fetch 권장)

> 주의: 브라우저의 `EventSource` API는 GET 요청만 지원하므로 `/api/chat`(POST)에는 사용할 수 없습니다.
> 위의 `fetch` + `ReadableStream` 방식을 사용하세요.

---

## /api/chat vs /v1/chat/completions 비교

| 항목 | `/api/chat` | `/v1/chat/completions` |
|------|-------------|----------------------|
| 프로토콜 | 자체 포맷 | OpenAI-compatible |
| 인증 | 없음 | Bearer token |
| 멀티턴 | 클라이언트가 `conversation_history` 문자열 전달 | 클라이언트가 `messages` 배열 전달, 서버가 자동 조립 |
| 스트리밍 | `stream: true` → SSE (named events) | `stream: true` → SSE (OpenAI 포맷) |
| SSE 포맷 | `event: token\ndata: {"content": "..."}` | `data: {"choices": [{"delta": {"content": "..."}}]}` |
| 에이전트 지정 | `agent_type` 필드 | 미지원 (항상 자동 분류) |
| 날짜 필터 직접 지정 | `filters` 필드 | 미지원 |
| 주요 사용처 | 커스텀 클라이언트, CLI, 내부 서비스 | Open WebUI, ChatGPT 호환 UI |

### 스트리밍 방식의 차이

| | `/api/chat` (SSE named events) | `/v1/chat/completions` (OpenAI SSE) |
|---|---|---|
| 상태 알림 | `event: status` 이벤트로 진행 상태 표시 | 없음 (검색 중 무응답) |
| 토큰 전달 | `event: token` + `{"content": "..."}` | `data: {"choices":[{"delta":{"content":"..."}}]}` |
| 소스 전달 | `event: sources` + 구조화된 JSON | 답변 텍스트에 포함 |
| 완료 신호 | `event: done` | `data: [DONE]` |
| 에러 처리 | `event: error` 이벤트 | 스트림 중단 |

**`/api/chat` 스트리밍의 장점:**
- `status` 이벤트로 사용자에게 "검색 중..." 같은 진행 상태를 표시할 수 있음
- `sources` 이벤트로 논문 목록을 구조화된 데이터로 별도 수신 (파싱 불필요)
- `error` 이벤트로 에러를 깔끔하게 처리

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

스트리밍 모드에서 에러가 발생하면 `error` 이벤트로 전달되고, 이후 `done` 이벤트로 스트림이 종료됩니다.

```
event: status
data: {"message": "논문 검색 및 질문 분석 중..."}

event: error
data: {"message": "처리 중 오류 발생: Connection refused"}

event: done
data: {"stream_id": "a1b2c3d4e5f6"}
```

---

## 서버 내부 처리 흐름

### JSON 모드 (`stream: false`)

```
클라이언트 요청
  ↓
POST /api/chat (ChatRequest, stream=false)
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
  ④ route_to_agent — 에이전트 실행 → LLM 답변 생성
  ⑤ add_citation — 출처 추가
  ↓
ChatResponse {answer, sources, trace_id}
```

### 스트리밍 모드 (`stream: true`)

```
클라이언트 요청
  ↓
POST /api/chat (ChatRequest, stream=true)
  ↓
state 구성 + _stream_mode = True
  ↓
[SSE: status] "논문 검색 및 질문 분석 중..."
  ↓
Supervisor 파이프라인 (LangGraph):
  ① extract_dates — 날짜 파싱
  ② extract_conditions — 키워드 추출
  ③ classify_intent — 에이전트 분류
  ④ route_to_agent — 에이전트 실행 (LLM 최종 호출은 스킵, messages만 준비)
  ⑤ add_citation — 출처 준비
  ↓
[SSE: status] "답변 생성 중..."
  ↓
LLM 실시간 스트리밍 (토큰 단위):
  [SSE: token] "OLED"
  [SSE: token] " 수명"
  [SSE: token] " 관련..."
  ... (토큰마다 즉시 전송)
  ↓
[SSE: token] "\n\n---\n📚 참조 논문..." (출처 텍스트)
[SSE: sources] [{paper_id, title, ...}]  (구조화된 소스)
[SSE: done] {stream_id: "..."}
```

> **핵심 차이**: JSON 모드는 ④에서 LLM 답변까지 모두 완성한 후 반환하지만,
> 스트리밍 모드는 ④에서 LLM 호출을 스킵하고 messages만 준비한 뒤,
> 별도 스트리밍 단계에서 토큰 단위로 전송합니다.
