"""Experiment Planner Agent — 문헌 기반 실험 설계를 제안한다."""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import llm_json_call, llm_text_call, multi_query_retrieve, format_context, build_sources

logger = logging.getLogger(__name__)

PARSE_SYSTEM = """You are an experiment design specialist. Parse the user's hypothesis/goal.
Return JSON: {"hypothesis":"...","independent_vars":["..."],"dependent_vars":["..."],"constraints":["..."],
"search_queries":["q1","q2","q3"]}"""

DESIGN_SYSTEM = """You are a Co-Scientist experiment planner for display R&D.
Based on related papers, design a comprehensive experiment:
1.Variables (independent/dependent/controlled), 2.Design Type (factorial/DOE/etc),
3.Materials & Equipment, 4.Step-by-step Protocol, 5.Statistical Analysis Plan,
6.Risk Mitigation. Answer in the same language as the user's question."""


async def parse_hypothesis(state: AgentState) -> AgentState:
    result = await llm_json_call(system_prompt=PARSE_SYSTEM, user_prompt=state.get("query",""),
                                  user_id=state.get("user_id"), trace_name="exp_parse", state=state)
    state["metadata"] = state.get("metadata", {})
    state["metadata"]["hypothesis"] = result.get("hypothesis", state.get("query",""))
    state["metadata"]["search_queries"] = result.get("search_queries", [state.get("query","")])
    return state

async def search_methods(state: AgentState) -> AgentState:
    queries = state.get("metadata",{}).get("search_queries",[])
    results = await multi_query_retrieve(queries=queries, user_id=state.get("user_id"),
                                          filters=state.get("filters"), top_k_per_query=5)
    state["search_results"] = results
    state["context"] = format_context(results)
    return state

async def design_experiment(state: AgentState) -> AgentState:
    answer = await llm_text_call(
        system_prompt=DESIGN_SYSTEM,
        user_prompt=f"Hypothesis: {state.get('metadata',{}).get('hypothesis','')}\n\n### Related Papers\n\n{state.get('context','')}",
        user_id=state.get("user_id"), trace_name="exp_design", temperature=0.3,
    state=state,
)
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results",[]))
    return state

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("parse_hypothesis", parse_hypothesis)
    graph.add_node("search_methods", search_methods)
    graph.add_node("design_experiment", design_experiment)
    graph.set_entry_point("parse_hypothesis")
    graph.add_edge("parse_hypothesis", "search_methods")
    graph.add_edge("search_methods", "design_experiment")
    graph.add_edge("design_experiment", END)
    return graph.compile()

agent = build_graph()
