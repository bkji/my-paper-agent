# Co-Scientist Agent 클라이언트 개발 가이드

## 멀티턴 대화 방식

서버는 **stateless** — 세션/상태를 저장하지 않습니다.
**클라이언트가 매번 이전 대화를 messages에 담아서 보내야 합니다.**

---

## 1. `/v1/chat/completions` (OpenAI 호환 API)

Open WebUI 등 OpenAI 호환 클라이언트에서 사용하는 엔드포인트.
**`query` 필드 없이 `messages`만으로 동작** — 서버가 마지막 user 메시지에서 질문을 자동 추출합니다.

### 1턴째
```json
{
  "model": "co-scientist-bk03",
  "messages": [
    {"role": "user", "content": "OLED 최신 논문 알려줘"}
  ],
  "stream": true,
  "stream_options": {"include_usage": true}
}
```

### 2턴째 — 이전 대화를 클라이언트가 다시 보냄
```json
{
  "model": "co-scientist-bk03",
  "messages": [
    {"role": "user", "content": "OLED 최신 논문 알려줘"},
    {"role": "assistant", "content": "OLED 관련 논문은... [1] Kim et al..."},
    {"role": "user", "content": "1번째 논문을 자세히 분석해줘"}
  ],
  "stream": true,
  "stream_options": {"include_usage": true}
}
```

### 3턴째
```json
{
  "model": "co-scientist-bk03",
  "messages": [
    {"role": "user", "content": "OLED 최신 논문 알려줘"},
    {"role": "assistant", "content": "OLED 관련 논문은... [1] Kim et al..."},
    {"role": "user", "content": "1번째 논문을 자세히 분석해줘"},
    {"role": "assistant", "content": "이 논문의 핵심은..."},
    {"role": "user", "content": "참조 문헌 3번은 어떤 내용이야?"}
  ],
  "stream": true,
  "stream_options": {"include_usage": true}
}
```

> - Open WebUI를 사용하면 이 과정이 **자동으로** 처리됩니다.
> - `stream_options: {"include_usage": true}` — 스트리밍 마지막 chunk에 토큰 사용량(usage)이 포함됩니다. 생략하면 usage를 받을 수 없습니다.

---

## 2. `/api/chat` (자체 API)

직접 개발하는 클라이언트에서 사용하는 엔드포인트.
**`query`(현재 질문)가 필수**이며, `messages`에 이전 대화 히스토리를 전달합니다.
스트리밍 시 usage는 `done` 이벤트에 항상 포함되므로 별도 옵션이 필요 없습니다.

### 1턴째
```json
{
  "query": "OLED 최신 논문 알려줘",
  "stream": true
}
```

### 2턴째
```json
{
  "query": "1번째 논문을 자세히 분석해줘",
  "messages": [
    {"role": "user", "content": "OLED 최신 논문 알려줘"},
    {"role": "assistant", "content": "OLED 관련 논문은... [1] Kim et al..."}
  ]
}
```

### 3턴째
```json
{
  "query": "참조 문헌 3번은 어떤 내용이야?",
  "messages": [
    {"role": "user", "content": "OLED 최신 논문 알려줘"},
    {"role": "assistant", "content": "OLED 관련 논문은... [1] Kim et al..."},
    {"role": "user", "content": "1번째 논문을 자세히 분석해줘"},
    {"role": "assistant", "content": "이 논문의 핵심은..."}
  ]
}
```

> `query`는 현재 질문, `messages`는 이전 대화 히스토리입니다.

### 두 API 비교

| 항목 | `/v1/chat/completions` | `/api/chat` |
|------|----------------------|------------|
| 형식 | OpenAI 호환 | 자체 형식 |
| 질문 전달 | `messages` 마지막 user 메시지 (자동 추출) | **`query` 필드 필수** |
| 대화 히스토리 | `messages`에 전체 대화 포함 | `messages`에 이전 대화 (현재 질문 제외) |
| 스트리밍 usage | `stream_options: {"include_usage": true}` **필요** | `done` 이벤트에 **항상 포함** |
| 용도 | Open WebUI 등 외부 클라이언트 | 직접 개발하는 클라이언트 |

---

## 3. 서버 내부 처리

클라이언트가 보낸 messages를 서버가 자동으로 최적화합니다:

```
클라이언트가 보낸 messages (전체 대화)
  ↓
서버 내부 처리 (supervisor.build_history):
  1. 마지막 user 메시지 제외 (query로 별도 처리)
  2. 최근 5턴(user+assistant 10항목)만 유지
  3. assistant 응답이 800자 초과 시 → 앞 400자 + "...(중략)..." + 뒤 400자로 압축
  4. 참조 문헌 섹션은 보존 ("참조 문헌 N번" 멀티턴 참조용)
  5. 저작권 고지는 자동 제거
  ↓
LLM 시스템 프롬프트에 [이전 대화]로 주입
```

### 요약

| 항목 | 값 |
|------|-----|
| 최대 유지 턴 수 | 5턴 (user+assistant 10항목) |
| assistant 응답 압축 임계값 | 800자 초과 시 |
| 압축 방식 | 앞 400자 + ...(중략)... + 뒤 400자 |
| 참조 문헌 | 압축하지 않고 보존 |
| 저작권 고지 | 자동 제거 |

---

## 4. 클라이언트 구현 핵심

```
클라이언트 책임                          서버 책임
─────────────                          ─────────
messages에 이전 대화 포함하여 전송  →   최근 5턴만 유지
assistant 응답을 그대로 저장       →   긴 응답 앞뒤 400자 압축
                                       참조 문헌 보존
                                       LLM 프롬프트에 주입
```

### 클라이언트가 해야 할 것
1. assistant 응답을 **그대로 저장** (압축/가공하지 않음)
2. 다음 요청 시 이전 대화를 **messages 배열에 전부 포함**
3. 서버가 알아서 최근 5턴 자르고 긴 응답 압축함 → 클라이언트는 신경 쓸 필요 없음

### 클라이언트가 하지 않아도 되는 것
- 대화 히스토리 압축/요약 (서버가 함)
- 참조 문헌 별도 관리 (서버가 보존함)
- 턴 수 제한 관리 (서버가 5턴으로 자름)

---

## 5. 멀티턴에서 지원되는 참조 표현

서버가 이전 대화 맥락을 활용하여 아래 표현을 자동 해석합니다:

| 표현 | 해석 |
|------|------|
| "이 논문", "위 논문", "해당 논문" | 직전 응답의 첫 번째 논문 |
| "1번째 논문", "3번째 논문" | 직전 응답의 N번째 검색 결과 |
| "참조 문헌 3번" | 직전 응답 참조 문헌의 3번 항목 |

---

## 6. 토큰 사용량 (usage)

모든 API 응답에 `usage` 필드가 **항상** 포함됩니다 (null이 아닌 0이라도 반환).

### usage에 포함되는 값

| 필드 | 설명 |
|------|------|
| `prompt_tokens` | 최종 답변 생성 LLM 호출의 입력 토큰 수 |
| `completion_tokens` | 최종 답변 생성 LLM 호출의 출력 토큰 수 |
| `total_tokens` | prompt_tokens + completion_tokens |

### stream on/off 토큰 수 일관성

스트리밍(`stream: true`)과 비스트리밍(`stream: false`) 모두 **동일한 prompt_tokens**를 반환합니다.

- 서버가 LLM에 `stream_options: {"include_usage": true}`를 전달하여 실제 토큰 수를 수신
- LLM 서버가 usage를 제공하지 않거나 `0`을 반환하는 경우에만 글자수 기반 추정(`글자수 // 4`)으로 대체
- `completion_tokens`는 LLM 생성의 자연스러운 변동으로 요청마다 약간 다를 수 있음

### 주의사항

- **최종 답변 생성 호출만** 카운트됨 (내부 의도 분류, 조건 추출 등은 미포함)
- 내부 LLM 호출의 상세 토큰 사용량은 **Langfuse**에서 trace 단위로 확인 가능
- LLM 호출 없이 응답하는 경우 (예: "데이터 없음") → `{0, 0, 0}` 반환
- 스트리밍에서도 동일하게 usage 반환:
  - `/api/chat`, `/api/chat_v2`: `event: done`의 `usage` 필드
  - `/v1/chat/completions`: `stream_options.include_usage=true` 시 마지막 chunk

### 응답 예시

```json
{
  "answer": "...",
  "sources": [...],
  "trace_id": "abc-123",
  "usage": {
    "prompt_tokens": 1500,
    "completion_tokens": 500,
    "total_tokens": 2000
  }
}
```

---

## 7. URL 경로 (Trailing Slash)

모든 API 엔드포인트는 **trailing slash(`/`) 유무와 관계없이 동일하게 동작**합니다.
307 리다이렉트 없이 바로 200 응답합니다.

| 경로 (둘 다 동일) | 설명 |
|---|---|
| `/api/chat` 또는 `/api/chat/` | 자체 Chat API |
| `/api/chat_v2` 또는 `/api/chat_v2/` | Chat API v2 (SSE 개선) |
| `/v1/chat/completions` 또는 `/v1/chat/completions/` | OpenAI 호환 API |
| `/v1/models` 또는 `/v1/models/` | 모델 목록 |

---

## 8. 인증

| 환경 | 설정 |
|------|------|
| 인증 활성화 | `.env`에 `OPENAI_COMPAT_API_KEY=your-key` 설정 |
| 인증 비활성화 | `.env`에 `OPENAI_COMPAT_API_KEY=` (빈값) |

인증 활성화 시 모든 API에 Bearer 토큰 필요:
```
Authorization: Bearer your-key
```

---

## 9. 스트리밍 응답

### `/v1/chat/completions` (OpenAI 형식)
```
data: {"choices":[{"delta":{"role":"assistant","content":""},...}],"usage":null}
data: {"choices":[{"delta":{"content":"OLED"},...}],"usage":null}
data: {"choices":[{"delta":{"content":" 관련"},...}],"usage":null}
...
data: {"choices":[{"delta":{},"finish_reason":"stop",...}],"usage":null}
data: {"choices":[],"usage":{"prompt_tokens":578,"completion_tokens":450,"total_tokens":1028}}
data: [DONE]
```

> `stream_options: {"include_usage": true}`를 요청에 포함하면 마지막 chunk에 usage가 포함됩니다.

### `/api/chat` (자체 형식)
```
event: status
data: {"message":"논문 검색 및 질문 분석 중..."}

event: token
data: {"content":"OLED"}

event: token
data: {"content":" 관련"}

...

event: sources
data: {"sources":[{"title":"...","doi":"...","score":0.85}]}

event: done
data: {"stream_id":"abc123","usage":{"prompt_tokens":578,"completion_tokens":450,"total_tokens":1028}}
```

> `done` 이벤트에 항상 `usage`가 포함됩니다. `/api/chat_v2`도 동일하며 추가로 `elapsed_ms` 필드를 포함합니다.

---

## 10. 테스트 스크립트

`scripts/` 디렉토리에 API 동작 확인용 bat 파일이 있습니다.

| 스크립트 | 용도 |
|---|---|
| `scripts/curl_test.bat` | 인증 포함 (Bearer 토큰 사용) |
| `scripts/curl_test_no_api.bat` | 인증 없이 테스트 (`.env`에서 `OPENAI_COMPAT_API_KEY=` 빈값 설정 시) |

### 테스트 항목 (4개)

| # | 엔드포인트 | 모드 | 확인 포인트 |
|---|---|---|---|
| [1] | `/api/chat` | 비스트리밍 | JSON 응답 + usage |
| [2] | `/api/chat` | 스트리밍 | SSE 이벤트 + done.usage |
| [3] | `/v1/chat/completions` | 비스트리밍 | OpenAI 형식 응답 + usage |
| [4] | `/v1/chat/completions` | 스트리밍 + usage | OpenAI SSE chunk + 마지막 usage chunk |

### 사용 방법

```bash
# 인증 있는 환경
scripts\curl_test.bat

# 인증 없는 환경
scripts\curl_test_no_api.bat
```
