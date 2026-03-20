"""Trend Analyzer Agent — 논문 기반 기술 트렌드를 분석한다."""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import llm_text_call, retrieve_by_query, format_context, build_sources

logger = logging.getLogger(__name__)

ANALYZE_SYSTEM = """You are a Co-Scientist specializing in technology trend analysis for display R&D.
Based on papers retrieved from different time periods, analyze trends.
Provide: 1.Executive Summary, 2.Rising Technologies, 3.Declining/Mature Technologies,
4.Key Research Groups, 5.Geographic Trends, 6.Keyword Evolution,
7.Prediction (next 2-3 years), 8.Strategic Recommendations.
Cite papers [Author, Year]. Answer in the same language as the user's question."""


async def collect_temporal_data(state: AgentState) -> AgentState:
    results = await retrieve_by_query(query=state.get("query",""), user_id=state.get("user_id"),
                                       filters=state.get("filters"), top_k=30)
    results.sort(key=lambda x: x.get("coverdate", ""), reverse=True)
    state["search_results"] = results
    state["context"] = format_context(results)
    return state


async def analyze_trends(state: AgentState) -> AgentState:
    if not state.get("search_results"):
        state["answer"] = "해당 주제에 대한 논문 데이터가 부족합니다."
        state["sources"] = []
        return state
    answer = await llm_text_call(
        system_prompt=ANALYZE_SYSTEM,
        user_prompt=f"Technology area: {state.get('query','')}\n\n### Papers (newest first)\n\n{state.get('context','')}",
        user_id=state.get("user_id"), trace_name="trend_analyze", temperature=0.4,
    state=state,
)
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results", []))
    return state


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("collect_temporal_data", collect_temporal_data)
    graph.add_node("analyze_trends", analyze_trends)
    graph.set_entry_point("collect_temporal_data")
    graph.add_edge("collect_temporal_data", "analyze_trends")
    graph.add_edge("analyze_trends", END)
    return graph.compile()

agent = build_graph()
