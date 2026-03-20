"""Cross-domain Connector Agent — 타 분야 접근법을 디스플레이에 적용 제안한다."""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import llm_json_call, llm_text_call, multi_query_retrieve, format_context, build_sources

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM = """You are a problem abstraction specialist. Given a display technology problem,
abstract it into a general problem. Return JSON:
{"original_problem":"...","abstract_problem":"...","target_domains":["biomedical","semiconductor","energy"],
"cross_search_queries":[{"domain":"name","queries":["q1","q2"]}]}"""

MAP_SYSTEM = """You are a Co-Scientist specializing in cross-domain innovation for display technology.
Given a display problem and analogous solutions from other fields, analyze adaptations.
For each: Source Field & Paper, Original Solution, Display Adaptation, Feasibility, Expected Impact, Risk Factors.
Rank by feasibility × impact. Answer in the same language as the user's question."""


async def extract_problem(state: AgentState) -> AgentState:
    result = await llm_json_call(system_prompt=EXTRACT_SYSTEM,
                                  user_prompt=f"Display technology problem: {state.get('query','')}",
                                  user_id=state.get("user_id"), trace_name="cross_domain_extract", state=state)
    state["metadata"] = state.get("metadata", {})
    state["metadata"]["abstract_problem"] = result.get("abstract_problem", state.get("query",""))
    state["metadata"]["cross_search_queries"] = result.get("cross_search_queries", [])
    return state


async def search_analogies(state: AgentState) -> AgentState:
    cross_queries = state.get("metadata", {}).get("cross_search_queries", [])
    all_results, domain_contexts = [], []
    for group in cross_queries:
        results = await multi_query_retrieve(queries=group.get("queries",[]), user_id=state.get("user_id"),
                                              filters=state.get("filters"), top_k_per_query=3)
        all_results.extend(results)
        ctx = format_context(results) if results else "(No papers found)"
        domain_contexts.append(f"## Domain: {group.get('domain','')}\n\n{ctx}")
    display_results = await multi_query_retrieve(queries=[state.get("query","")], user_id=state.get("user_id"),
                                                  filters=state.get("filters"), top_k_per_query=3)
    all_results.extend(display_results)
    domain_contexts.insert(0, f"## Domain: Display (original)\n\n{format_context(display_results)}")
    state["search_results"] = all_results
    state["context"] = "\n\n".join(domain_contexts)
    return state


async def map_to_display(state: AgentState) -> AgentState:
    answer = await llm_text_call(
        system_prompt=MAP_SYSTEM,
        user_prompt=f"Original problem: {state.get('query','')}\nAbstracted: {state.get('metadata',{}).get('abstract_problem','')}\n\n### Papers\n\n{state.get('context','')}",
        user_id=state.get("user_id"), trace_name="cross_domain_map", temperature=0.5,
    state=state,
)
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results", []))
    return state


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("extract_problem", extract_problem)
    graph.add_node("search_analogies", search_analogies)
    graph.add_node("map_to_display", map_to_display)
    graph.set_entry_point("extract_problem")
    graph.add_edge("extract_problem", "search_analogies")
    graph.add_edge("search_analogies", "map_to_display")
    graph.add_edge("map_to_display", END)
    return graph.compile()

agent = build_graph()
