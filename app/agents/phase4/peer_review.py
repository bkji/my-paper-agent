"""Peer Review Simulator Agent — 논문/보고서에 대한 가상 리뷰."""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import llm_text_call, retrieve_by_query, format_context, build_sources

logger = logging.getLogger(__name__)

REVIEW_SYSTEM = """You are simulating 3 expert peer reviewers for a display technology paper:
1. **Technical Reviewer**: Focus on methodology rigor, statistical validity
2. **Domain Expert**: Focus on novelty, significance in display field
3. **Practitioner**: Focus on practical applicability in manufacturing

For each reviewer provide: Summary, Strengths, Weaknesses, Questions for Authors, Rating (1-10).
Then provide a Meta-Review synthesizing all three perspectives with prioritized revision suggestions.
Answer in the same language as the user's question."""

async def parse_manuscript(state: AgentState) -> AgentState:
    results = await retrieve_by_query(state.get("query",""), user_id=state.get("user_id"),
                                       filters=state.get("filters"), top_k=10)
    state["search_results"] = results
    state["context"] = format_context(results)
    return state

async def review(state: AgentState) -> AgentState:
    answer = await llm_text_call(system_prompt=REVIEW_SYSTEM,
        user_prompt=f"Manuscript topic: {state.get('query','')}\n\n### Related Work\n\n{state.get('context','')}",
        user_id=state.get("user_id"), trace_name="peer_review", temperature=0.4, state=state)
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results",[]))
    return state

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("parse_manuscript", parse_manuscript)
    graph.add_node("review", review)
    graph.set_entry_point("parse_manuscript")
    graph.add_edge("parse_manuscript", "review")
    graph.add_edge("review", END)
    return graph.compile()

agent = build_graph()
