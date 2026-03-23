"""Paper Deep Dive Agent — 특정 논문 1편을 심층 분석한다.

논문 원문 조회 우선순위:
1. DOI 지정 → MariaDB DOI 검색
2. 제목 키워드 → MariaDB 제목 검색 (원문 전체)
3. Fallback → Milvus 벡터 검색 (chunk 단위)
"""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import retrieve_by_query, format_context, build_sources, llm_text_call, llm_json_call
from app.core import database

logger = logging.getLogger(__name__)

ANALYZE_SYSTEM = """You are a Co-Scientist performing a deep analysis of a research paper for display technology researchers.
Provide a thorough, structured analysis covering:
1. **Core Contribution**: What is the main novelty and significance?
2. **Methodology**: Detailed description of the approach, materials, and experimental setup.
3. **Key Results**: Main findings with specific numbers/metrics.
4. **Strengths**: What makes this paper valuable?
5. **Limitations**: What are the weaknesses or missing aspects?
6. **Relation to Prior Work**: How does it compare to existing approaches?
7. **Future Research Directions**: What follow-up work could be done?
8. **Practical Implications**: How could this be applied in display manufacturing/R&D?
Answer in the same language as the user's question."""

TITLE_EXTRACT_PROMPT = """Extract the paper title keyword from the user's query.
Return ONLY JSON: {"title_keyword": "<keyword or null>"}

Examples:
"Subjective assessment of visual fidelity 논문을 요약해줘" → {"title_keyword": "Subjective assessment of visual fidelity"}
"holographic grating 논문 분석해줘" → {"title_keyword": "holographic grating"}
"이 논문에 대해 자세히 알려줘" → {"title_keyword": null}
"DOI 10.1002/jsid.2117 논문 분석" → {"title_keyword": null}"""


async def fetch_paper(state: AgentState) -> AgentState:
    query = state.get("query", "")
    user_id = state.get("user_id")
    filters = state.get("filters")

    # 1. DOI가 명시된 경우 → MariaDB DOI 검색 (원문 포함)
    if filters and filters.get("doi"):
        paper = await database.get_paper_fulltext_by_doi(filters["doi"])
        if paper:
            state["context"] = _format_fulltext(paper)
            state["search_results"] = [paper]
            logger.info("[DeepDive] found paper by DOI: '%s'", paper["title"][:60])
            return state

    # 2. 쿼리에서 논문 제목 추출 → MariaDB 제목 검색 (원문 전체)
    try:
        title_result = await llm_json_call(
            system_prompt=TITLE_EXTRACT_PROMPT,
            user_prompt=query,
            trace_name="deep_dive_extract_title",
            user_id=user_id,
            temperature=0.1,
            state=state,
        )
        title_keyword = title_result.get("title_keyword")
        if title_keyword and title_keyword.lower() not in ("null", "none", ""):
            paper = await database.get_paper_fulltext_by_title(title_keyword)
            if paper:
                state["context"] = _format_fulltext(paper)
                state["search_results"] = [paper]
                logger.info("[DeepDive] found paper by title: '%s' (text_len=%d)",
                            paper["title"][:60], len(paper.get("paper_text") or ""))
                return state
    except Exception as e:
        logger.warning("[DeepDive] title extraction failed: %s", e)

    # 3. Fallback → Milvus 벡터 검색 (chunk 단위)
    results = await retrieve_by_query(query, user_id=user_id, filters=filters, top_k=20)
    state["context"] = format_context(results) if results else ""
    state["search_results"] = results
    return state


def _format_fulltext(paper: dict) -> str:
    """논문 원문을 LLM context 형식으로 포맷한다."""
    return (
        f"Title: {paper.get('title', '')}\n"
        f"Author: {paper.get('author', '')}\n"
        f"DOI: {paper.get('doi', '')}\n"
        f"Date: {paper.get('coverdate', '')}\n"
        f"Keywords: {paper.get('paper_keyword', '')}\n\n"
        f"Full Text:\n{paper.get('paper_text', '')}"
    )


async def analyze(state: AgentState) -> AgentState:
    query = state.get("query", "")
    context = state.get("context", "")
    user_id = state.get("user_id")

    if not context:
        state["answer"] = "해당 논문을 찾지 못했습니다. 정확한 제목이나 DOI를 입력해 주세요."
        state["sources"] = []
        return state

    # 컨텍스트가 너무 길면 잘라냄 (LLM context window 보호)
    max_context_chars = 12000
    if len(context) > max_context_chars:
        context = context[:max_context_chars] + "\n\n... (truncated)"

    answer = await llm_text_call(
        system_prompt=ANALYZE_SYSTEM,
        user_prompt=f"User request: {query}\n\n### Paper Content\n\n{context}",
        user_id=user_id, trace_name="deep_dive_analyze", temperature=0.3,
    state=state,
)
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results", []))
    return state


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("fetch_paper", fetch_paper)
    graph.add_node("analyze", analyze)
    graph.set_entry_point("fetch_paper")
    graph.add_edge("fetch_paper", "analyze")
    graph.add_edge("analyze", END)
    return graph.compile()

agent = build_graph()
