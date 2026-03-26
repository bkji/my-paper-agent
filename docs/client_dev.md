# Co-Scientist Agent 클라이언트 개발 가이드

## 멀티턴 대화 방식

서버는 **stateless** — 세션/상태를 저장하지 않습니다.
**클라이언트가 매번 이전 대화를 messages에 담아서 보내야 합니다.**

---

## 1. `/v1/chat/completions` (OpenAI 호환 API)

Open WebUI 등 OpenAI 호환 클라이언트에서 사용하는 엔드포인트.

### 1턴째
```json
{
  "model": "co-scientist-bk03",
  "messages": [
    {"role": "user", "content": "OLED 최신 논문 알려줘"}
  ],
  "stream": true
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
  "stream": true
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
  "stream": true
}
```

> Open WebUI를 사용하면 이 과정이 **자동으로** 처리됩니다.

---

## 2. `/api/chat` (자체 API)

직접 개발하는 클라이언트에서 사용하는 엔드포인트.

### 1턴째
```json
{
  "query": "OLED 최신 논문 알려줘"
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

## 6. 인증

| 환경 | 설정 |
|------|------|
| 인증 활성화 | `.env`에 `OPENAI_COMPAT_API_KEY=your-key` 설정 |
| 인증 비활성화 | `.env`에 `OPENAI_COMPAT_API_KEY=` (빈값) |

인증 활성화 시 모든 API에 Bearer 토큰 필요:
```
Authorization: Bearer your-key
```

---

## 7. 스트리밍 응답

### `/v1/chat/completions` (OpenAI 형식)
```
data: {"choices":[{"delta":{"role":"assistant","content":""},...}]}
data: {"choices":[{"delta":{"content":"OLED"},...}]}
data: {"choices":[{"delta":{"content":" 관련"},...}]}
...
data: {"choices":[{"delta":{},"finish_reason":"stop",...}]}
data: [DONE]
```

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
data: {"stream_id":"abc123","usage":{"prompt_tokens":1500,...}}
```
