"""Paper Deep Dive Agent — 특정 논문 1편을 심층 분석한다."""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import retrieve_by_query, format_context, build_sources, llm_text_call
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


async def fetch_paper(state: AgentState) -> AgentState:
    query = state.get("query", "")
    user_id = state.get("user_id")
    filters = state.get("filters")

    if filters and filters.get("doi"):
        papers = await database.get_papers_by_doi(filters["doi"], user_id=user_id)
        if papers:
            paper = papers[0]
            state["context"] = (
                f"Title: {paper['title']}\nAuthor: {paper['author']}\n"
                f"DOI: {paper['doi']}\nDate: {paper['coverdate']}\n\n"
                f"Full Text:\n{paper['paper_text']}"
            )
            state["search_results"] = [paper]
            return state

    results = await retrieve_by_query(query, user_id=user_id, filters=filters, top_k=20)
    state["context"] = format_context(results) if results else ""
    state["search_results"] = results
    return state


async def analyze(state: AgentState) -> AgentState:
    query = state.get("query", "")
    context = state.get("context", "")
    user_id = state.get("user_id")

    if not context:
        state["answer"] = "해당 논문을 찾지 못했습니다. 정확한 제목이나 DOI를 입력해 주세요."
        state["sources"] = []
        return state

    answer = await llm_text_call(
        system_prompt=ANALYZE_SYSTEM,
        user_prompt=f"User request: {query}\n\n### Paper Content\n\n{context}",
        user_id=user_id, trace_name="deep_dive_analyze", temperature=0.3,
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
