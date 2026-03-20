"""Report Drafter Agent — 연구 결과 기반 보고서/발표 초안 작성."""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import llm_text_call, retrieve_by_query, format_context, build_sources

logger = logging.getLogger(__name__)

DRAFT_SYSTEM = """You are a Co-Scientist report writer for display R&D.
Based on retrieved papers, draft a professional report or presentation.
Detect format from query (report/presentation/summary) and structure accordingly.
Include figure/table placeholders where appropriate.
Use formal, technical writing style. Answer in the same language as the user's question."""

async def gather_inputs(state: AgentState) -> AgentState:
    results = await retrieve_by_query(state.get("query",""), user_id=state.get("user_id"),
                                       filters=state.get("filters"), top_k=10)
    state["search_results"] = results
    state["context"] = format_context(results)
    return state

async def draft_report(state: AgentState) -> AgentState:
    answer = await llm_text_call(system_prompt=DRAFT_SYSTEM,
        user_prompt=f"Request: {state.get('query','')}\n\n### Reference Papers\n\n{state.get('context','')}",
        user_id=state.get("user_id"), trace_name="report_draft", temperature=0.3)
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results",[]))
    return state

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("gather_inputs", gather_inputs)
    graph.add_node("draft_report", draft_report)
    graph.set_entry_point("gather_inputs")
    graph.add_edge("gather_inputs", "draft_report")
    graph.add_edge("draft_report", END)
    return graph.compile()

agent = build_graph()
