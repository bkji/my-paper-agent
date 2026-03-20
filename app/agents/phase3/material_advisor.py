"""Material/Process Advisor Agent — 목표 기반 재료/공정 비교 분석."""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import llm_json_call, llm_text_call, multi_query_retrieve, format_context, build_sources

logger = logging.getLogger(__name__)

PARSE_SYSTEM = """You are a materials science specialist. Parse the user's material/process goal.
Return JSON: {"target":"...","metrics":["..."],"constraints":["..."],"search_queries":["q1","q2","q3"]}"""

COMPARE_SYSTEM = """You are a Co-Scientist material advisor for display R&D.
Compare candidate materials/processes and recommend the best option:
1.Comparison Table (properties, performance, cost, process compatibility),
2.Detailed Analysis of Top-3 Candidates, 3.Risk Assessment, 4.Final Recommendation.
Cite papers [Author, Year]. Answer in the same language as the user's question."""

async def parse_goal(state: AgentState) -> AgentState:
    result = await llm_json_call(system_prompt=PARSE_SYSTEM, user_prompt=state.get("query",""),
                                  user_id=state.get("user_id"), trace_name="material_parse")
    state["metadata"] = state.get("metadata", {})
    state["metadata"]["search_queries"] = result.get("search_queries", [state.get("query","")])
    return state

async def search_materials(state: AgentState) -> AgentState:
    queries = state.get("metadata",{}).get("search_queries",[])
    results = await multi_query_retrieve(queries=queries, user_id=state.get("user_id"),
                                          filters=state.get("filters"), top_k_per_query=5)
    state["search_results"] = results
    state["context"] = format_context(results)
    return state

async def compare_and_recommend(state: AgentState) -> AgentState:
    answer = await llm_text_call(system_prompt=COMPARE_SYSTEM,
        user_prompt=f"Goal: {state.get('query','')}\n\n### Related Papers\n\n{state.get('context','')}",
        user_id=state.get("user_id"), trace_name="material_compare", temperature=0.3)
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results",[]))
    return state

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("parse_goal", parse_goal)
    graph.add_node("search_materials", search_materials)
    graph.add_node("compare_and_recommend", compare_and_recommend)
    graph.set_entry_point("parse_goal")
    graph.add_edge("parse_goal", "search_materials")
    graph.add_edge("search_materials", "compare_and_recommend")
    graph.add_edge("compare_and_recommend", END)
    return graph.compile()

agent = build_graph()
