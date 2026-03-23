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
from app.agents.common import inject_date_context, build_sources
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

LIST_SYSTEM_PROMPT = """You are a Co-Scientist assistant that organizes paper lists.
Present the paper list in a clean markdown table with columns: No, Date, Title, Author, Keywords.
Add a brief summary at the end.
Answer in the same language as the user's question."""


async def classify_analytics_type(state: AgentState) -> AgentState:
    """질문을 분석하여 집계(aggregate) vs 목록(list) vs 통계분석(analysis) 유형을 판단한다."""
    query = state.get("query", "")
    filters = state.get("filters") or {}

    # 키워드 기반 빠른 판단
    q_lower = query.lower()
    agg_keywords = ["편수", "건수", "몇 편", "몇 건", "count", "통계", "추이", "그래프", "graph",
                    "월별", "연도별", "분기별", "연간", "증감", "변화량"]
    list_keywords = ["목록", "리스트", "list", "보여줘", "찾아줘", "어떤 논문", "논문 제목"]

    is_agg = any(kw in q_lower for kw in agg_keywords)
    is_list = any(kw in q_lower for kw in list_keywords) and not is_agg

    metadata = state.get("metadata") or {}

    if is_agg:
        metadata["analytics_type"] = "aggregate"
        # group_by 판단
        if "월별" in query or "monthly" in q_lower:
            metadata["group_by"] = "month"
        elif "분기별" in query or "quarter" in q_lower:
            metadata["group_by"] = "quarter"
        elif "연도별" in query or "연간" in query or "yearly" in q_lower:
            metadata["group_by"] = "year"
        else:
            metadata["group_by"] = "month"  # 기본값
    else:
        metadata["analytics_type"] = "list"

    # 키워드 추출 (날짜/집계 표현 + 조사/어미 + 비검색어 제거 후 핵심 키워드만 남김)
    import re
    cleaned = re.sub(
        r'\d{4}년?\s*\d{0,2}월?|\d{4}\s*[~\-]\s*\d{4}년?|최근\s*\d+\s*(개월|년)|'
        r'올해|작년|금년|지난해|지난달|상반기|하반기|\d분기|'
        r'월별|연도별|분기별|연간|편수|건수|통계|추이|그래프|graph|'
        r'목록|리스트|list|논문|관련|관한|대한|전체|전부|모든|'
        r'제목|저자|키워드|날짜|기간|분야|'
        r'보여줘|알려줘|찾아줘|분석해줘|나타내줘|있는지|있어\?|해줘|좀|주세요|줘|'
        r'을|를|이|가|은|는|에|의|로|으로|에서|까지|부터|별|간|와|과|도|만|좀|및|어떤',
        '', query
    ).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # 2글자 이상의 의미있는 키워드만 사용
    if cleaned and len(cleaned) >= 2 and not cleaned.isspace():
        metadata["analytics_keyword"] = cleaned

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
    author = filters.get("author")

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
