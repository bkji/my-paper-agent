"""Paper Search & QA Agent — Milvus hybrid search 기반 논문 검색 및 질의응답."""
from __future__ import annotations

import logging

from langgraph.graph import StateGraph, END

from app.agents.state import AgentState
from app.agents.common import retrieve_by_query, format_context, build_sources, inject_date_context, llm_json_call
from app.core import llm, database

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


TITLE_EXTRACT_PROMPT = """Extract the paper title keyword from the user's query if they are asking about a specific paper.
Return ONLY JSON: {"title_keyword": "<keyword or null>"}

Examples:
"Subjective assessment of visual fidelity 논문 요약해줘" → {"title_keyword": "Subjective assessment of visual fidelity"}
"holographic grating 논문에 대해 알려줘" → {"title_keyword": "holographic grating"}
"Micro LED 결함 검출 방법은?" → {"title_keyword": null}
"최근 OLED 연구 동향은?" → {"title_keyword": null}"""


async def retrieve(state: AgentState) -> AgentState:
    query = state.get("query", "")
    user_id = state.get("user_id")
    filters = state.get("filters")

    logger.info("[PaperQA] retrieve: query='%s'", query[:100])

    # DOI가 명시된 경우 MariaDB에서 원문 조회
    if filters and filters.get("doi"):
        paper = await database.get_paper_fulltext_by_doi(filters["doi"])
        if paper:
            logger.info("[PaperQA] found paper by DOI from MariaDB: '%s'", paper["title"][:60])
            state["search_results"] = [paper]
            state["context"] = (
                f"[1] Title: {paper.get('title', '')}\n"
                f"    Author: {paper.get('author', '')}\n"
                f"    DOI: {paper.get('doi', '')}\n"
                f"    Date: {paper.get('coverdate', '')}\n"
                f"    Keywords: {paper.get('paper_keyword', '')}\n"
                f"    Full Text:\n    {paper.get('paper_text', '')}\n"
            )
            return state

    # 특정 논문 제목이 언급된 경우 MariaDB에서 원문 조회 시도
    try:
        title_result = await llm_json_call(
            system_prompt=TITLE_EXTRACT_PROMPT,
            user_prompt=query,
            trace_name="paper_qa_extract_title",
            user_id=user_id,
            temperature=0.1,
            state=state,
        )
        title_keyword = title_result.get("title_keyword")
        if title_keyword and title_keyword.lower() not in ("null", "none", ""):
            paper = await database.get_paper_fulltext_by_title(title_keyword)
            if paper:
                logger.info("[PaperQA] found paper by title from MariaDB: '%s'", paper["title"][:60])
                state["search_results"] = [paper]
                state["context"] = (
                    f"[1] Title: {paper.get('title', '')}\n"
                    f"    Author: {paper.get('author', '')}\n"
                    f"    DOI: {paper.get('doi', '')}\n"
                    f"    Date: {paper.get('coverdate', '')}\n"
                    f"    Keywords: {paper.get('paper_keyword', '')}\n"
                    f"    Full Text:\n    {paper.get('paper_text', '')}\n"
                )
                return state
    except Exception as e:
        logger.warning("[PaperQA] title extraction failed: %s, falling back to Milvus", e)

    # Fallback: Milvus 벡터 검색
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

    # 컨텍스트가 너무 길면 잘라냄 (LLM context window 보호)
    max_context_chars = 12000
    if len(context) > max_context_chars:
        context = context[:max_context_chars] + "\n\n... (truncated)"

    messages = [
        {"role": "system", "content": inject_date_context(SYSTEM_PROMPT, state)},
        {"role": "user", "content": CONTEXT_TEMPLATE.format(context=context, query=query)},
    ]

    # Stream mode: LLM 호출 스킵, messages만 저장
    metadata = state.get("metadata") or {}
    if metadata.get("_stream_mode"):
        metadata["_llm_messages"] = messages
        metadata["_llm_temperature"] = 0.3
        state["metadata"] = metadata
        state["answer"] = ""
        state["sources"] = build_sources(search_results)
        return state

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
