"""Knowledge Connector Agent — 논문 저자 기반 전문가 매칭."""
from __future__ import annotations
import logging
from collections import Counter
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import llm_text_call, retrieve_by_query, format_context, build_sources

logger = logging.getLogger(__name__)

RECOMMEND_SYSTEM = """You are a Co-Scientist helping find experts and collaboration opportunities.
Based on publication data, recommend experts:
For each expert: Name, Affiliation (if known), Expertise Areas, Key Publications, Relevance Score, Why Connect.
Suggest collaboration strategies. Answer in the same language as the user's question."""

async def search_experts(state: AgentState) -> AgentState:
    results = await retrieve_by_query(state.get("query",""), user_id=state.get("user_id"),
                                       filters=state.get("filters"), top_k=30)
    # 저자별 논문 수 집계
    author_counter = Counter()
    for r in results:
        authors_str = r.get("author", "")
        if authors_str:
            for a in authors_str.split(","):
                a = a.strip()
                if a:
                    author_counter[a] += 1
    top_authors = author_counter.most_common(15)
    state["metadata"] = state.get("metadata", {})
    state["metadata"]["top_authors"] = top_authors
    state["search_results"] = results
    state["context"] = format_context(results[:15])
    return state

async def rank_and_recommend(state: AgentState) -> AgentState:
    top_authors = state.get("metadata",{}).get("top_authors",[])
    authors_info = "\n".join(f"- {name}: {count} publications" for name, count in top_authors)
    answer = await llm_text_call(system_prompt=RECOMMEND_SYSTEM,
        user_prompt=f"Topic: {state.get('query','')}\n\n### Top Authors\n{authors_info}\n\n### Papers\n\n{state.get('context','')}",
        user_id=state.get("user_id"), trace_name="knowledge_recommend", temperature=0.3, state=state)
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results",[]))
    return state

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("search_experts", search_experts)
    graph.add_node("rank_and_recommend", rank_and_recommend)
    graph.set_entry_point("search_experts")
    graph.add_edge("search_experts", "rank_and_recommend")
    graph.add_edge("rank_and_recommend", END)
    return graph.compile()

agent = build_graph()
