"""Analytics Agent — MariaDB 기반 논문 통계/집계/리스트 조회.

Milvus(벡터검색)가 아닌 MariaDB(SQL)를 사용하여:
- 기간별 논문 편수 집계 (월별/연도별/분기별)
- 조건별 논문 목록 조회 (키워드, 저자, 기간)
- 통계 데이터 기반 LLM 분석/요약

사용 시나리오:
- "2021년~올해까지 월별 논문 편수를 보여줘"
- "2024년 1~2월 OLED 관련 논문 리스트"
- "저자별 논문 편수 Top 10"
- "연도별 Micro LED 논문 추이"
"""
from __future__ import annotations

import logging

from langgraph.graph import StateGraph, END

from app.agents.state import AgentState
from app.agents.common import inject_date_context, build_sources, llm_json_call
from app.core import llm, database

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Co-Scientist analytics assistant for display technology researchers.
You analyze paper statistics and aggregation data from the database.

When presenting data:
- Use markdown tables for structured data
- Include totals and averages where appropriate
- Highlight notable trends or outliers
- If asked for a graph/chart, present data in a clear table format with bar indicators (▓)

Answer in the same language as the user's question."""

LIST_SYSTEM_PROMPT = """You are a Co-Scientist assistant that presents paper search results.

Response format:
1. First line: State the total count clearly (e.g. "2024년 10월에 발표된 논문은 총 4편입니다.")
2. Then list each paper as a bullet point with: title, author, date, keywords

Example:
2024년 10월에 발표된 논문은 총 3편입니다.

- **Title A** — Author1, Author2 (2024-10-01) [keyword1, keyword2]
- **Title B** — Author3 (2024-10-01) [keyword3]
- **Title C** — Author4, Author5 (2024-10-01) [keyword4, keyword5]

Answer in the same language as the user's question."""


CLASSIFY_SYSTEM_PROMPT = """You are a query analyzer for a paper database system.
Analyze the user's query and extract structured parameters for database search.
Return ONLY valid JSON with these fields:

{
  "type": "list" or "aggregate",
  "keyword": "search keyword or null",
  "group_by": "month" or "year" or "quarter",
  "author": "author name or null"
}

## Rules:
- type: "list" if user wants paper titles/details/목록/제목/보여줘. "aggregate" if user wants only counts/statistics/추이/그래프 without titles.
- keyword: Extract ONLY the technical/topic keyword for filtering papers (e.g. "OLED", "Micro LED", "holographic"). Set null if no specific topic filter — do NOT include words like "논문", "편수", "제목", "목록".
- group_by: "month" (default), "year" if 연도별/yearly, "quarter" if 분기별.
- author: Extract author name if mentioned, otherwise null.

## Examples:
"2024년 10월 논문 편수와 제목 보여줘" → {"type": "list", "keyword": null, "group_by": "month", "author": null}
"OLED 관련 논문 목록" → {"type": "list", "keyword": "OLED", "group_by": "month", "author": null}
"연도별 Micro LED 논문 편수 추이" → {"type": "aggregate", "keyword": "Micro LED", "group_by": "year", "author": null}
"최근 6개월 논문 몇 편?" → {"type": "aggregate", "keyword": null, "group_by": "month", "author": null}
"그 논문들 제목도 보여줘" → {"type": "list", "keyword": null, "group_by": "month", "author": null}
"holographic grating 관련 논문 찾아줘" → {"type": "list", "keyword": "holographic grating", "group_by": "month", "author": null}"""


async def classify_analytics_type(state: AgentState) -> AgentState:
    """LLM을 사용하여 질문의 analytics 유형, 키워드, group_by를 추출한다."""
    query = state.get("query", "")
    metadata = state.get("metadata") or {}

    try:
        result = await llm_json_call(
            system_prompt=CLASSIFY_SYSTEM_PROMPT,
            user_prompt=query,
            trace_name="analytics_classify",
            user_id=state.get("user_id"),
            temperature=0.1,
            state=state,
        )

        analytics_type = result.get("type", "list")
        if analytics_type not in ("list", "aggregate"):
            analytics_type = "list"
        metadata["analytics_type"] = analytics_type

        keyword = result.get("keyword")
        if keyword and keyword.lower() not in ("null", "none", ""):
            metadata["analytics_keyword"] = keyword

        group_by = result.get("group_by", "month")
        if group_by not in ("month", "year", "quarter"):
            group_by = "month"
        metadata["group_by"] = group_by

        author = result.get("author")
        if author and author.lower() not in ("null", "none", ""):
            metadata["analytics_author"] = author

    except Exception as e:
        logger.warning("[Analytics] LLM classify failed: %s, using defaults", e)
        metadata["analytics_type"] = "list"
        metadata["group_by"] = "month"

    state["metadata"] = metadata
    logger.info("[Analytics] type=%s, group_by=%s, keyword=%s",
                metadata.get("analytics_type"), metadata.get("group_by"),
                metadata.get("analytics_keyword"))
    return state


async def fetch_data(state: AgentState) -> AgentState:
    """MariaDB에서 집계 또는 목록 데이터를 가져온다."""
    filters = state.get("filters") or {}
    metadata = state.get("metadata") or {}
    analytics_type = metadata.get("analytics_type", "list")
    keyword = metadata.get("analytics_keyword")

    coverdate_from = filters.get("coverdate_from")
    coverdate_to = filters.get("coverdate_to")
    author = filters.get("author") or metadata.get("analytics_author")

    # 키워드 유효성 검증: keyword로 검색해서 0건이면 keyword 제거 후 재시도
    # (0.6B 모델이 hallucinate하여 잘못된 키워드를 추출하는 경우 방어)
    if keyword:
        test_data = await database.list_papers(
            coverdate_from=coverdate_from, coverdate_to=coverdate_to,
            keyword=keyword, author=author, limit=1,
        )
        if not test_data:
            logger.warning("[Analytics] keyword '%s' returned 0 results, retrying without keyword", keyword)
            keyword = None
            metadata.pop("analytics_keyword", None)

    if analytics_type == "aggregate":
        group_by = metadata.get("group_by", "month")
        data = await database.aggregate_papers(
            coverdate_from=coverdate_from,
            coverdate_to=coverdate_to,
            keyword=keyword,
            author=author,
            group_by=group_by,
        )
        state["search_results"] = data

        # 집계 결과를 텍스트 컨텍스트로 변환
        if data:
            total = sum(r["count"] for r in data)
            lines = [f"## 집계 결과 (group_by={group_by}, 총 {total}편)\n"]
            lines.append("| 기간 | 논문 수 | 비율 |")
            lines.append("|------|---------|------|")
            for row in data:
                pct = (row["count"] / total * 100) if total > 0 else 0
                bar = "▓" * max(1, int(pct / 5))
                lines.append(f"| {row['period']} | {row['count']} | {bar} {pct:.1f}% |")
            lines.append(f"\n**총 {total}편**")
            state["context"] = "\n".join(lines)
        else:
            state["context"] = "해당 조건의 논문이 없습니다."

    else:  # list
        data = await database.list_papers(
            coverdate_from=coverdate_from,
            coverdate_to=coverdate_to,
            keyword=keyword,
            author=author,
            limit=100,
        )
        state["search_results"] = data

        if data:
            lines = [f"## 논문 목록 (총 {len(data)}편)\n"]
            lines.append("| No | 날짜 | 제목 | 저자 | 키워드 |")
            lines.append("|----|------|------|------|--------|")
            for i, row in enumerate(data, 1):
                cd = str(row.get("coverdate", ""))
                date_str = f"{cd[:4]}-{cd[4:6]}-{cd[6:8]}" if len(cd) == 8 else cd
                title = (row.get("title") or "")[:60]
                author_str = (row.get("author") or "")[:30]
                kw = (row.get("paper_keyword") or "")[:40]
                lines.append(f"| {i} | {date_str} | {title} | {author_str} | {kw} |")
            state["context"] = "\n".join(lines)
        else:
            state["context"] = "해당 조건의 논문이 없습니다."

    logger.info("[Analytics] fetched %d results", len(state.get("search_results", [])))
    return state


async def generate_response(state: AgentState) -> AgentState:
    """집계/목록 데이터를 기반으로 LLM이 분석 요약을 생성한다."""
    query = state.get("query", "")
    context = state.get("context", "")
    metadata = state.get("metadata") or {}
    analytics_type = metadata.get("analytics_type", "list")
    user_id = state.get("user_id")

    if context == "해당 조건의 논문이 없습니다.":
        state["answer"] = "해당 조건에 맞는 논문을 찾지 못했습니다. 검색 조건을 조정해 보세요."
        state["sources"] = []
        return state

    sys_prompt = SYSTEM_PROMPT if analytics_type == "aggregate" else LIST_SYSTEM_PROMPT

    prompt = f"""### 데이터
{context}

### 사용자 질문
{query}

### 지시사항
- 위 데이터를 기반으로 사용자 질문에 답변하세요.
- 데이터에 포함된 수치를 정확히 인용하세요.
- 추이/변화가 있다면 해석을 덧붙이세요."""

    messages = [
        {"role": "system", "content": inject_date_context(sys_prompt, state)},
        {"role": "user", "content": prompt},
    ]

    answer = await llm.chat_completion(
        messages=messages, temperature=0.3,
        trace_name="analytics_generate", user_id=user_id,
    )

    state["answer"] = answer
    # 논문 목록인 경우 sources 생성
    results = state.get("search_results", [])
    if analytics_type == "list" and results:
        state["sources"] = [
            {
                "paper_id": str(r.get("doi") or r.get("filename", "")),
                "title": r.get("title", ""),
                "doi": r.get("doi"),
                "chunk_id": 0,
                "chunk_text": "",
                "score": 0.0,
            }
            for r in results[:20]
        ]
    else:
        state["sources"] = []

    logger.info("[Analytics] generate done: answer_len=%d", len(answer))
    return state


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("classify", classify_analytics_type)
    graph.add_node("fetch", fetch_data)
    graph.add_node("generate", generate_response)
    graph.set_entry_point("classify")
    graph.add_edge("classify", "fetch")
    graph.add_edge("fetch", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


agent = build_graph()
