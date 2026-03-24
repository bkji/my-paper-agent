# Co-Scientist Agent 사용자 가이드

Co-Scientist는 논문 데이터베이스를 기반으로 R&D 연구를 지원하는 AI 에이전트 시스템입니다.
14개 전문 에이전트가 질문 의도를 자동으로 파악하여 적절한 답변을 생성합니다.

---

## 목차

1. [접속 정보](#접속-정보)
2. [사용 가능한 질문 유형](#사용-가능한-질문-유형)
3. [에이전트별 상세 안내](#에이전트별-상세-안내)
4. [멀티턴 대화 (이어서 질문하기)](#멀티턴-대화-이어서-질문하기)
5. [논문 원문 참조 조건](#논문-원문-참조-조건)
6. [날짜 표현 지원](#날짜-표현-지원)
7. [제한사항 및 참고사항](#제한사항-및-참고사항)
8. [트러블슈팅](#트러블슈팅)

---

## 접속 정보

| 항목 | 값 |
|------|-----|
| Open WebUI 모델명 | `co-scientist-bk03` |
| API 엔드포인트 (OpenAI 호환) | `http://host.docker.internal:20035/v1` (Docker) |
| API 엔드포인트 (직접 호출) | `http://localhost:20035/api/chat` |
| API Key | `.env`의 `OPENAI_COMPAT_API_KEY` 값 |
| Swagger 문서 | `http://localhost:20035/docs` |
| API 상세 명세 | `docs/api_chat.md` |

> Docker 내 Open WebUI에서는 반드시 `host.docker.internal`을 사용하세요. `localhost`는 컨테이너 자신을 가리킵니다.

### /api/chat 빠른 호출

```bash
# 최소 요청 (query만 필수)
curl -X POST http://localhost:20035/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <인증키>" \
  -d '{"query": "OLED 논문 알려줘"}'
```

> `/api/chat`과 `/v1/chat/completions` 모두 동일한 API Key를 사용합니다.
> 키 미설정 시 인증 없이 접근 가능합니다. 상세 명세는 `docs/api_chat.md`를 참조하세요.

---

## 사용 가능한 질문 유형

### 한눈에 보기

| 질문 유형 | 에이전트 | 예시 |
|-----------|----------|------|
| 논문 내용 질문 | paper_qa | "Micro LED 결함 검출 방법에 대해 알려줘" |
| 특정 논문 요약 | paper_qa | "Subjective assessment of visual fidelity 논문을 요약해줘" |
| 논문 심층 분석 | paper_deep_dive | "Wide-viewing-angle dual-view 논문을 심층 분석해줘" |
| 문헌 리뷰 | literature_survey | "디스플레이 기술의 최근 연구 동향을 정리해줘" |
| 통계/편수/목록 | analytics | "2024년 10월 논문 편수와 제목을 보여줘" |
| 연구 아이디어 | idea_generator | "Micro LED와 holographic grating을 결합한 아이디어를 제안해줘" |
| 타 분야 접목 | cross_domain | "의료 영상 기술을 디스플레이에 적용할 수 있는 방법은?" |
| 기술 트렌드 | trend_analyzer | "Micro LED 기술의 발전 트렌드를 분석해줘" |
| 실험 설계 | experiment_planner | "OLED 발광층 효율 개선을 위한 실험 설계를 제안해줘" |
| 재료/소재 비교 | material_advisor | "Micro LED용 발광 소재를 비교 분석해줘" |
| 특허 동향 | patent_landscaper | "홀로그래픽 디스플레이 관련 특허 동향을 분석해줘" |
| 경쟁사 분석 | competitive_intel | "삼성과 LG의 디스플레이 기술 경쟁 현황을 분석해줘" |
| 보고서 초안 | report_drafter | "2024년 디스플레이 기술 동향 보고서 초안을 작성해줘" |
| 논문 리뷰 | peer_review | "이 논문의 강점과 약점을 리뷰해줘" |
| 전문가 추천 | knowledge_connector | "foveated rendering 분야 전문가를 추천해줘" |

---

## 에이전트별 상세 안내

### Phase 1: 기본 논문 검색 및 분석

#### 1. analytics — 통계/편수/목록/경향 분석
논문 편수, 목록, 추이, **경향 분석** 등을 처리합니다. MariaDB SQL로 정확한 수치를 제공합니다.

**이 에이전트로 분류되는 키워드:** "편수", "건수", "몇 편", "목록", "리스트", "제목", "통계", "추이", "경향", "동향", "그래프", "찾아줘", "volume", "issue"

**질문 예시:**
| 질문 | 응답 유형 |
|------|----------|
| "전체 논문 몇 편이야?" | 총 편수 집계 |
| "2024년 10월 발표된 논문 편수와 제목을 보여줘" | 편수 + 목록 (list) |
| "연도별 논문 편수 추이를 보여줘" | 월별/연도별 집계 (aggregate) |
| "2024년 12월 논문 목록 보여줘" | 논문 리스트 (list) |
| "holographic 관련 논문 있어?" | 키워드 필터링 목록 |
| "최근 6개월 논문 편수 알려줘" | 상대 날짜 + 집계 |
| "2024년 하반기 논문 목록" | 반기 + 목록 |
| "2024년 10월~12월 논문 경향 분석해줘" | **카테고리별 경향 분석** |
| "OLED 논문 경향 분석해줘" | **특정 주제 경향 분석** |
| "volume 32, issue 10인 논문 제목들 보여줘" | volume/issue 필터링 |
| "led관련 논문 찾아줘" | 키워드 검색 목록 |

**경향 분석 기능:**
- **목적어 없는 경우** ("논문 경향 분석해줘"): 아래 SID/Wiley 디스플레이 기술 카테고리 기준으로 분류하여 분석
- **목적어 있는 경우** ("OLED 경향 분석해줘"): 해당 주제 논문만 필터링하여 분석

**디스플레이 기술 카테고리 (SID/Wiley 분류 기준):**
1. Active-Matrix Devices and Displays
2. Applied Vision and Human Factors
3. Backlighting and Solid State Lighting Technologies
4. Display Electronics
5. Display Manufacturing Technologies
6. Display Measurements
7. Display Systems; Optical and Electronic
8. Electronic Paper and Flexible Displays
9. Liquid Crystal and other Non-emissive Displays
10. Organic Light Emitting Devices and Displays
11. Plasma and other Emissive Displays
12. Projection Displays and Systems

**데이터 소스:** MariaDB SQL (Milvus 미사용)
**특이사항:** 키워드 검색 시 0건이면 자동으로 키워드 없이 재시도합니다. 복합 키워드("Micro LED")는 변형("micro-LED", "microLED")도 함께 검색합니다.

---

#### 2. paper_qa — 논문 내용 질의응답
가장 범용적인 에이전트입니다. 기술 원리, 방법론, 개념 질문에 답합니다.

**질문 예시:**
| 질문 | 검색 방식 |
|------|----------|
| "Micro LED 결함 검출 방법에 대해 알려줘" | Milvus 벡터 검색 (chunk) |
| "foveated rendering이란 무엇인가?" | Milvus 벡터 검색 (chunk) |
| "OLED 발광 효율을 높이는 방법은?" | Milvus 벡터 검색 (chunk) |
| "Subjective assessment of visual fidelity 논문을 요약해줘" | **MariaDB 원문 전체** |
| "High-speed inspection of defective micro-LEDs 논문의 핵심 기여는?" | **MariaDB 원문 전체** |

**핵심:** 특정 논문 제목을 언급하면 원문 전체를 기반으로 답변하고, 일반 질문은 관련 chunk를 검색합니다.

---

#### 3. paper_deep_dive — 특정 논문 심층 분석
논문 1편을 지정하여 8개 항목(연구 목적, 방법론, 주요 결과, 기여, 한계점, 후속 연구 등)으로 심층 분석합니다.

**질문 예시:**
- "Wide-viewing-angle dual-view integral imaging display 논문을 심층 분석해줘"
- "DOI 10.1234/xxxx 논문을 분석해줘"

**데이터 소스 우선순위:** DOI → 논문 제목(MariaDB 원문) → Milvus fallback(top_k=20)
**참고:** 제목이나 DOI를 정확하게 입력할수록 원문 전체 기반 분석이 가능합니다.

---

#### 4. literature_survey — 문헌 리뷰 자동 생성
주제를 4~6개 섹션으로 자동 분해하고, 각 섹션별로 관련 논문을 검색하여 종합 리뷰를 생성합니다.

**질문 예시:**
- "디스플레이 기술의 최근 연구 동향을 정리해줘"
- "Micro LED 전사 기술에 대한 문헌 리뷰를 작성해줘"
- "OLED 열화 메커니즘 연구를 서베이해줘"

**데이터 소스:** Milvus 벡터 검색 (섹션별 다중 쿼리, 각 top_k=3)

---

### Phase 2: 창의적 분석

#### 5. idea_generator — 연구 아이디어 제안
여러 기술을 교차 분석하여 5개의 새로운 연구 아이디어를 제안합니다. (temperature=0.7로 창의성 강조)

**질문 예시:**
- "Micro LED와 holographic grating을 결합한 새로운 연구 아이디어를 제안해줘"
- "OLED와 양자점을 결합한 연구 주제를 브레인스토밍해줘"

---

#### 6. cross_domain — 타 분야 기술 접목
디스플레이 문제를 추상화하고, 타 분야의 접근법을 매핑하여 새로운 해결책을 제안합니다.

**질문 예시:**
- "의료 영상 기술을 디스플레이 분야에 적용할 수 있는 방법은?"
- "반도체 공정 기술을 Micro LED 제조에 활용하는 방법은?"

---

#### 7. trend_analyzer — 기술 트렌드 분석
논문 30편을 시간순으로 정렬 분석하여 기술 발전 트렌드(Rising/Declining Tech, Prediction 등)를 제공합니다.

**질문 예시:**
- "Micro LED 기술의 발전 트렌드를 분석해줘"
- "홀로그래픽 디스플레이 연구의 흐름을 분석해줘"

---

### Phase 3: 전문 분석

#### 8. experiment_planner — 실험 설계 제안
가설을 파싱하고 관련 논문의 실험 방법을 참고하여 상세 실험 설계(변수, 재료, 프로토콜, 통계 방법)를 제안합니다.

**질문 예시:**
- "OLED 발광층 효율 개선을 위한 실험 설계를 제안해줘"
- "Micro LED 전사 수율 향상을 위한 실험을 설계해줘"

---

#### 9. material_advisor — 재료/소재 비교 분석
관련 논문을 기반으로 재료/소재를 비교표로 정리하고 Top-3 추천 및 리스크 평가를 제공합니다.

**질문 예시:**
- "Micro LED용 발광 소재를 비교 분석해줘"
- "OLED 발광 호스트 재료를 추천해줘"

---

#### 10. patent_landscaper — 특허 동향 분석
논문 데이터를 기반으로 특허 관련 동향(Key Players, White Space, FTO Risks, IP Strategy)을 분석합니다.

**질문 예시:**
- "홀로그래픽 디스플레이 관련 특허 동향을 분석해줘"
- "Micro LED 전사 기술의 IP 현황은?"

> **참고:** 실제 특허 DB가 아닌 **논문 데이터 기반 추론**입니다.

---

#### 11. competitive_intel — 경쟁사 분석
12개 주요 디스플레이 기업의 연구 활동을 분석합니다.

**질문 예시:**
- "삼성과 LG의 디스플레이 기술 경쟁 현황을 분석해줘"
- "BOE의 최근 연구 동향은?"

**분석 대상 기업:** Samsung, BOE, LG Display, TCL CSOT, Sharp, JDI, AUO, Innolux, Applied Materials, Canon Tokki, Universal Display, Merck

---

### Phase 4: 문서 생성 및 리뷰

#### 12. report_drafter — 보고서/발표 초안 작성
쿼리 포맷(report/presentation/summary)을 자동 감지하여 구조화된 초안을 생성합니다.

**질문 예시:**
- "2024년 디스플레이 기술 동향 보고서 초안을 작성해줘"
- "Micro LED 기술 현황 발표 자료를 만들어줘"
- "OLED 기술 요약 문서를 작성해줘"

---

#### 13. peer_review — 가상 피어 리뷰
3명의 가상 리뷰어(Technical, Domain Expert, Practitioner)가 각각 Strengths/Weaknesses/Rating을 평가하고 Meta-Review를 제공합니다.

**질문 예시:**
- "Wide-viewing-angle dual-view 논문을 리뷰해줘"
- "이 논문의 강점과 약점을 분석해줘"

---

#### 14. knowledge_connector — 전문가/저자 추천
논문 저자 데이터를 집계(논문 수 기준 Top 15)하여 해당 분야 전문가를 추천하고 협업 전략을 제안합니다.

**질문 예시:**
- "foveated rendering 분야 전문가를 추천해줘"
- "Micro LED 연구를 가장 많이 한 저자는?"

---

## 멀티턴 대화 (이어서 질문하기)

Open WebUI에서 **이전 대화를 이어서** 질문할 수 있습니다.

### 지원되는 멀티턴 패턴

**예시 1 — 날짜 컨텍스트 유지:**
```
사용자: 2024년 10월 논문 편수 알려줘
에이전트: 4편입니다.
사용자: 그 논문들 제목도 보여줘     ← "2024년 10월"을 히스토리에서 자동 추출
```

**예시 2 — 심화 질문:**
```
사용자: 2024년 10월 논문 리스트 알려줘
에이전트: (4편 목록 출력)
사용자: 그 논문들 중 첫 번째 논문을 요약해줘     ← 이전 답변에서 제목 참조 → 원문 조회
```

**예시 3 — 주제 이어가기:**
```
사용자: Micro LED 결함 검출 방법에 대해 알려줘
에이전트: (답변)
사용자: 더 자세히 설명해줘     ← 이전 주제를 맥락으로 활용
```

### 멀티턴 조건 및 제한사항

| 항목 | 내용 |
|------|------|
| **최대 유지 턴 수** | 최근 6턴 (사용자+어시스턴트 합계) |
| **어시스턴트 응답 압축** | 이전 응답은 300자로 요약되어 전달 |
| **지원 인터페이스** | Open WebUI 등 OpenAI-compatible API (`/v1/chat/completions`) |
| **CLI 모드** | 단일 질문만 지원 (멀티턴 미지원) |

**예시 4 — 날짜 전환 (멀티턴에서 새 날짜 사용):**
```
사용자: 2024년 10월~12월 논문 경향 분석해줘
에이전트: (10월~12월 분석 결과)
사용자: 지난 여름에 발표된 논문 경향 분석해줘     ← 새 날짜 "지난 여름"을 정상 인식 (이전 10~12월 무시)
```

### 멀티턴이 잘 안 되는 경우

- **6턴 이상 지난 맥락:** 사라집니다 → 핵심 정보를 다시 언급해주세요
- **완전히 다른 주제로 전환:** 이전 맥락이 혼란을 줄 수 있습니다 → 새 채팅 권장
- **모호한 지시어:** "그거", "아까 것" → 가능하면 구체적 키워드로 바꿔주세요

---

## 논문 원문 참조 조건

### 원문 전체가 참조되는 경우 (MariaDB)

논문 **제목**이나 **DOI**를 명시적으로 언급하면 MariaDB에서 원본 논문 전체를 조회합니다.

| 에이전트 | 원문 참조 조건 | 우선순위 |
|----------|---------------|----------|
| **paper_qa** | 질문에 논문 제목 포함 | 제목 → MariaDB 원문, 없으면 Milvus |
| **paper_deep_dive** | DOI 또는 논문 제목 포함 | DOI → 제목 → MariaDB, 없으면 Milvus(top_k=20) |

**원문 참조 O (예시):**
- "Subjective assessment of visual fidelity 논문을 요약해줘"
- "High-speed and contactless inspection of defective micro-LEDs 논문의 핵심 기여는?"
- "DOI 10.1234/xxxx 논문을 분석해줘"

**원문 참조 X → 벡터 검색 chunk 사용 (예시):**
- "Micro LED 결함 검출 방법에 대해 알려줘" (특정 논문이 아닌 일반 질문)
- "OLED 효율 높이는 방법은?"

### 참고사항
- 제목은 **부분 일치**로 검색합니다 (전체 제목을 외울 필요 없음)
- 원문이 MariaDB에 없으면 자동으로 Milvus 벡터 검색으로 fallback
- 원문 컨텍스트는 **6,000자**로 제한 (매우 긴 논문은 일부 생략)

### 나머지 12개 에이전트
literature_survey, idea_generator, cross_domain, trend_analyzer, experiment_planner, material_advisor, patent_landscaper, competitive_intel, report_drafter, peer_review, knowledge_connector는 모두 **Milvus 벡터 검색(chunk 기반)**만 사용합니다. 원문 전체 참조는 paper_qa와 paper_deep_dive에서만 지원됩니다.

---

## 날짜 표현 지원

다양한 한국어 날짜 표현을 자동으로 인식합니다. 서버 현재 시간을 기준으로 상대 날짜를 계산합니다.

| 유형 | 예시 | 변환 결과 |
|------|------|-----------|
| 절대(연월) | "2024년 10월" | 20241001 ~ 20241031 |
| 절대(연도) | "2024년" | 20240101 ~ 20241231 |
| 범위 | "2022~2024년" | 20220101 ~ 20241231 |
| 분기 | "2024년 3분기" | 20240701 ~ 20240930 |
| 반기 | "2024년 하반기" | 20240701 ~ 20241231 |
| 상대 | "최근 6개월" | (서버 기준) 6개월 전 ~ 현재 |
| 상대 | "작년", "올해" | 해당 연도 전체 |
| 월 범위 | "2024년 10월~12월" | 20241001 ~ 20241231 |
| 월 범위 (연도 걸침) | "2024년 10월~2025년 3월" | 20241001 ~ 20250331 |
| 계절 | "작년 여름" | 해당 연도 7월 ~ 9월 |
| 계절 | "지난 여름" | 가장 최근 지난 여름 (서버 시간 기준) |
| 비교 | "2022년 대비 2024년" | 20220101 ~ 20241231 |

---

## 제한사항 및 참고사항

### 데이터 범위
- 시스템에 적재된 논문 데이터만 검색 가능합니다 (실시간 인터넷 검색 미지원)
- 현재 적재된 논문: **10편** (2024년 5월 1편, 10월 4편, 12월 4편, 2026년 2월 1편)
- 해당 기간 외의 질문에는 "논문이 없습니다"로 응답합니다
- 특허 분석(patent_landscaper)은 실제 특허 DB가 아닌 **논문 데이터 기반 추론**입니다

### LLM 모델 의존성
- 답변 품질은 사용 중인 LLM 모델에 따라 크게 달라집니다
- `qwen3-0.6b`: 기본 질문은 가능하나, intent 분류 정확도 ~50%
- `qwen3-4b-instruct-2507`: 대부분의 질문에 정확한 답변 가능 (권장)
- 폐쇄망 서버(235B): 높은 품질 기대

### 검색 팁
- **영문 키워드**가 한글 키워드보다 검색 정확도가 높습니다 (논문 데이터가 영문)
- 너무 넓은 주제("디스플레이 전체")보다는 **구체적인 키워드**가 좋은 결과를 줍니다
- analytics에서 키워드 검색 시 영문으로 입력하세요 (예: "holographic", "micro LED")
- 존재하지 않는 기술/논문을 질문하면 "찾을 수 없습니다" 응답이 나옵니다

### 응답 형식
| 에이전트 | 응답 형식 |
|----------|----------|
| analytics | 표(table) 형식으로 편수/목록 제공, 경향 분석 시 SID/Wiley 카테고리별 분류 |
| literature_survey | 섹션별로 구분된 문헌 리뷰 |
| report_drafter | 보고서/발표 구조 형식 |
| peer_review | 3인 리뷰어의 강점/약점/평점 + Meta-Review |
| knowledge_connector | 전문가 프로필 + 협업 전략 |
| 기타 | 자유 형식 텍스트 답변 + 참고 문헌 목록 |

---

## 저작권 및 참조 문헌 표시

모든 응답 끝에는 자동으로 **참조 문헌**과 **저작권 고지**가 추가됩니다.

**참조 문헌 형식:**
```
---
**참조 문헌:**
1. 제목: <논문 제목>, 저자: <저자명>, DOI: https://doi.org/10.xxxx/xxxx
2. 제목: <논문 제목>, 저자: <저자명>, DOI: https://doi.org/10.xxxx/xxxx
```

**저작권 고지:**
```
본 서비스는 삼성디스플레이 임직원의 내부 목적에 한해 제공됩니다.
외부 공개, 마케팅, 제3자 제공 또는 상업적 활용은 엄격히 금지됩니다.
Copyright © 1999-2026 John Wiley & Sons, Inc or related companies.
All rights reserved, including rights for text and data mining and
training of artificial intelligence technologies or similar technologies.
```

- RAG 검색 결과(sources)가 있는 경우: 참조 문헌 + 저작권 고지
- sources가 없는 경우 (예: 데이터 없음 응답): 저작권 고지만 표시

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| "해당 조건에 맞는 논문을 찾지 못했습니다" | 날짜/키워드 필터에 해당하는 데이터 없음 | 날짜 범위를 넓히거나 키워드를 변경 |
| 응답이 비어있음 | LLM 모델 언로드 또는 context 초과 | LM Studio에서 모델 로드 상태 확인 |
| Intent 분류 오류 (다른 에이전트로 라우팅) | 소형 모델의 분류 한계 | 질문을 더 명확하게 작성 (예: "편수"를 포함) |
| Open WebUI에서 연결 안 됨 | Docker 네트워크 이슈 | URL을 `host.docker.internal`로 변경 |
| 멀티턴에서 맥락이 사라짐 | 6턴 초과 또는 CLI 모드 사용 | 핵심 정보를 다시 언급하거나 Open WebUI 사용 |
| 참고 문헌 중복 표시 | 같은 논문의 여러 chunk 반환 | 자동 중복 제거됨 (title 기준) |
| JSON 파싱 에러 | 소형 LLM의 JSON 생성 실패 | 자동 fallback 처리됨, 재시도 시 정상 응답 |
