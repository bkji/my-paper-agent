"""Literature Survey Agent — 주제별 문헌 리뷰를 자동 생성한다."""
from __future__ import annotations

import logging

from langgraph.graph import StateGraph, END

from app.agents.state import AgentState
from app.agents.common import (
    llm_json_call, llm_text_call, multi_query_retrieve, format_context, build_sources,
)

logger = logging.getLogger(__name__)

PLAN_SYSTEM = """You are a research survey planner. Given a research topic, generate a survey outline.
Return JSON with this structure:
{
  "sections": [
    {"title": "section title", "search_queries": ["query1", "query2"]}
  ]
}
Generate 4-6 sections covering: background, key techniques, recent advances, challenges, future directions.
Each section should have 2-3 search queries optimized for semantic search over academic papers."""

SYNTHESIZE_SYSTEM = """You are a Co-Scientist writing a comprehensive literature survey for display technology researchers.
Based on the retrieved paper excerpts organized by section, write a well-structured literature review.
Requirements:
- Write section by section following the provided outline.
- Cite papers using [Author, Year] format with DOI when available.
- Identify consensus, contradictions, and research gaps across papers.
- End with a summary of key findings and suggested future research directions.
- Answer in the same language as the user's question."""


async def plan_survey(state: AgentState) -> AgentState:
    query = state.get("query", "")
    user_id = state.get("user_id")
    logger.info("[LitSurvey] plan_survey: query='%s'", query[:100])

    plan = await llm_json_call(
        system_prompt=PLAN_SYSTEM,
        user_prompt=f"Research topic: {query}",
        user_id=user_id, trace_name="lit_survey_plan",
    )
    sections = plan.get("sections", [
        {"title": "Background", "search_queries": [query]},
        {"title": "Key Techniques", "search_queries": [query]},
        {"title": "Recent Advances", "search_queries": [query]},
        {"title": "Challenges and Future Directions", "search_queries": [query]},
    ])
    state["metadata"] = state.get("metadata", {})
    state["metadata"]["sections"] = sections
    return state


async def multi_retrieve(state: AgentState) -> AgentState:
    sections = state.get("metadata", {}).get("sections", [])
    user_id = state.get("user_id")
    filters = state.get("filters")

    all_results = []
    section_contexts = []
    for section in sections:
        queries = section.get("search_queries", [])
        results = await multi_query_retrieve(queries=queries, user_id=user_id, filters=filters, top_k_per_query=3)
        all_results.extend(results)
        ctx = format_context(results) if results else "(No relevant papers found)"
        section_contexts.append(f"## {section['title']}\n\n{ctx}")

    state["search_results"] = all_results
    state["context"] = "\n\n".join(section_contexts)
    return state


async def synthesize(state: AgentState) -> AgentState:
    query = state.get("query", "")
    context = state.get("context", "")
    user_id = state.get("user_id")

    answer = await llm_text_call(
        system_prompt=SYNTHESIZE_SYSTEM,
        user_prompt=f"Topic: {query}\n\n### Retrieved Papers by Section\n\n{context}",
        user_id=user_id, trace_name="lit_survey_synthesize", temperature=0.4,
    )
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results", []))
    return state


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("plan_survey", plan_survey)
    graph.add_node("multi_retrieve", multi_retrieve)
    graph.add_node("synthesize", synthesize)
    graph.set_entry_point("plan_survey")
    graph.add_edge("plan_survey", "multi_retrieve")
    graph.add_edge("multi_retrieve", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


agent = build_graph()
