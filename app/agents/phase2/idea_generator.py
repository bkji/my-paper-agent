"""Idea Generator Agent — 논문 교차 분석 기반 연구 아이디어를 제안한다."""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import llm_json_call, llm_text_call, multi_query_retrieve, format_context, build_sources

logger = logging.getLogger(__name__)

DECOMPOSE_SYSTEM = """You are a research topic decomposer. Given a research topic, break it down into 3-5 sub-topics.
Return JSON: {"sub_topics": [{"name": "...", "search_queries": ["q1","q2"], "domain": "display/materials/optics/..."}], "constraints": ["..."]}"""

IDEATION_SYSTEM = """You are a Co-Scientist idea generator for display technology R&D.
Based on cross-referenced paper excerpts, generate 3-5 novel research ideas.
For each: Idea Title, Description, Novelty, Feasibility (High/Medium/Low), Supporting Evidence, Suggested First Steps.
Rank by potential impact. Answer in the same language as the user's question."""


async def decompose_topic(state: AgentState) -> AgentState:
    query = state.get("query", "")
    result = await llm_json_call(system_prompt=DECOMPOSE_SYSTEM, user_prompt=f"Research topic: {query}",
                                  user_id=state.get("user_id"), trace_name="idea_gen_decompose", state=state)
    state["metadata"] = state.get("metadata", {})
    state["metadata"]["sub_topics"] = result.get("sub_topics", [{"name": query, "search_queries": [query], "domain": "display"}])
    state["metadata"]["constraints"] = result.get("constraints", [])
    return state


async def cross_retrieve(state: AgentState) -> AgentState:
    sub_topics = state.get("metadata", {}).get("sub_topics", [])
    all_results, topic_contexts = [], []
    for topic in sub_topics:
        results = await multi_query_retrieve(queries=topic.get("search_queries", []), user_id=state.get("user_id"),
                                              filters=state.get("filters"), top_k_per_query=3)
        all_results.extend(results)
        ctx = format_context(results) if results else "(No papers found)"
        topic_contexts.append(f"## Sub-topic: {topic['name']} ({topic.get('domain','')})\n\n{ctx}")
    state["search_results"] = all_results
    state["context"] = "\n\n".join(topic_contexts)
    return state


async def generate_ideas(state: AgentState) -> AgentState:
    query = state.get("query", "")
    context = state.get("context", "")
    constraints = state.get("metadata", {}).get("constraints", [])
    constraints_text = "\n".join(f"- {c}" for c in constraints) if constraints else "None"
    answer = await llm_text_call(
        system_prompt=IDEATION_SYSTEM,
        user_prompt=f"Research topic: {query}\nConstraints:\n{constraints_text}\n\n### Cross-referenced Papers\n\n{context}",
        user_id=state.get("user_id"), trace_name="idea_gen_generate", temperature=0.7,
    state=state,
)
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results", []))
    return state


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("decompose_topic", decompose_topic)
    graph.add_node("cross_retrieve", cross_retrieve)
    graph.add_node("generate_ideas", generate_ideas)
    graph.set_entry_point("decompose_topic")
    graph.add_edge("decompose_topic", "cross_retrieve")
    graph.add_edge("cross_retrieve", "generate_ideas")
    graph.add_edge("generate_ideas", END)
    return graph.compile()

agent = build_graph()
