"""Paper Search & QA Agent — Milvus hybrid search 기반 논문 검색 및 질의응답."""
from __future__ import annotations

import logging

from langgraph.graph import StateGraph, END

from app.agents.state import AgentState
from app.agents.common import retrieve_by_query, format_context, build_sources, inject_date_context
from app.core import llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Co-Scientist assistant for display technology researchers.
Answer the question based on the provided research paper excerpts.
Always cite the source papers (title, DOI, author) when referencing information.
If the context does not contain enough information, say so clearly.
Answer in the same language as the user's question."""

CONTEXT_TEMPLATE = """### Retrieved Paper Excerpts

{context}

### Question
{query}

### Instructions
- Answer based on the paper excerpts above.
- Cite sources using [Title (Author, Year)] format.
- If information is insufficient, state what is missing."""


async def retrieve(state: AgentState) -> AgentState:
    query = state.get("query", "")
    user_id = state.get("user_id")
    filters = state.get("filters")

    logger.info("[PaperQA] retrieve: query='%s'", query[:100])

    search_results = await retrieve_by_query(query, user_id=user_id, filters=filters)
    context = format_context(search_results)

    state["search_results"] = search_results
    state["context"] = context
    logger.info("[PaperQA] retrieve done: %d results", len(search_results))
    return state


async def generate(state: AgentState) -> AgentState:
    query = state.get("query", "")
    context = state.get("context", "")
    search_results = state.get("search_results", [])
    user_id = state.get("user_id")

    logger.info("[PaperQA] generate: context_len=%d", len(context))

    if not search_results:
        state["answer"] = "관련 논문을 찾지 못했습니다. 다른 키워드로 검색해 보세요."
        state["sources"] = []
        return state

    messages = [
        {"role": "system", "content": inject_date_context(SYSTEM_PROMPT, state)},
        {"role": "user", "content": CONTEXT_TEMPLATE.format(context=context, query=query)},
    ]

    answer = await llm.chat_completion(
        messages=messages, temperature=0.3,
        trace_name="paper_qa_generate", user_id=user_id,
    )

    state["answer"] = answer
    state["sources"] = build_sources(search_results)
    logger.info("[PaperQA] generate done: answer_len=%d", len(answer))
    return state


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


agent = build_graph()
