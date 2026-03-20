"""Patent Landscaper Agent — 특허 동향 분석 및 공백 영역 식별."""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import llm_text_call, retrieve_by_query, format_context, build_sources

logger = logging.getLogger(__name__)

ANALYZE_SYSTEM = """You are a Co-Scientist patent analyst for display technology.
Analyze the patent/paper landscape covering:
1.Overview, 2.Key Players, 3.Technology Clusters, 4.White Space Opportunities,
5.Filing Trends, 6.Freedom-to-Operate Risks, 7.IP Strategy Recommendations.
Cite papers [Author, Year]. Answer in the same language as the user's question."""

async def search_patents(state: AgentState) -> AgentState:
    results = await retrieve_by_query(state.get("query",""), user_id=state.get("user_id"),
                                       filters=state.get("filters"), top_k=20)
    state["search_results"] = results
    state["context"] = format_context(results)
    return state

async def analyze_landscape(state: AgentState) -> AgentState:
    answer = await llm_text_call(system_prompt=ANALYZE_SYSTEM,
        user_prompt=f"Topic: {state.get('query','')}\n\n### Papers/Patents\n\n{state.get('context','')}",
        user_id=state.get("user_id"), trace_name="patent_analyze", temperature=0.3, state=state)
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results",[]))
    return state

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("search_patents", search_patents)
    graph.add_node("analyze_landscape", analyze_landscape)
    graph.set_entry_point("search_patents")
    graph.add_edge("search_patents", "analyze_landscape")
    graph.add_edge("analyze_landscape", END)
    return graph.compile()

agent = build_graph()
