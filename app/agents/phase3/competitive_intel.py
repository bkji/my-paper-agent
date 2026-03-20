"""Competitive Intelligence Agent — 경쟁사 동향 모니터링 및 브리핑."""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import llm_text_call, multi_query_retrieve, format_context, build_sources

logger = logging.getLogger(__name__)

COMPETITORS = ["Samsung", "BOE", "LG Display", "TCL CSOT", "Sharp", "JDI", "AUO", "Innolux",
               "Applied Materials", "Canon Tokki", "Universal Display", "Merck"]

BRIEFING_SYSTEM = """You are a Co-Scientist competitive intelligence analyst for display R&D.
Generate a competitive briefing:
1.Executive Summary, 2.Competitor Activity, 3.Technology Comparison,
4.Threat/Opportunity Assessment, 5.Collaboration Potential, 6.Recommended Actions.
Cite papers [Author, Year]. Answer in the same language as the user's question."""

async def search_competitor_news(state: AgentState) -> AgentState:
    query = state.get("query","")
    queries = [f"{c} {query}" for c in COMPETITORS[:5]] + [query]
    results = await multi_query_retrieve(queries=queries, user_id=state.get("user_id"),
                                          filters=state.get("filters"), top_k_per_query=3)
    state["search_results"] = results
    state["context"] = format_context(results)
    return state

async def generate_briefing(state: AgentState) -> AgentState:
    answer = await llm_text_call(system_prompt=BRIEFING_SYSTEM,
        user_prompt=f"Query: {state.get('query','')}\n\n### Competitor Papers\n\n{state.get('context','')}",
        user_id=state.get("user_id"), trace_name="competitive_briefing", temperature=0.3)
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results",[]))
    return state

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("search_competitor_news", search_competitor_news)
    graph.add_node("generate_briefing", generate_briefing)
    graph.set_entry_point("search_competitor_news")
    graph.add_edge("search_competitor_news", "generate_briefing")
    graph.add_edge("generate_briefing", END)
    return graph.compile()

agent = build_graph()
