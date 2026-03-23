"""Agent 공통 헬퍼 — 검색, context 포맷, source 변환 등 재사용 함수."""
from __future__ import annotations

import json
import logging

from app.config import settings
from app.core import embeddings, vectorstore, llm
from app.core.tools import get_current_date_context

logger = logging.getLogger(__name__)


def inject_date_context(system_prompt: str, state: dict | None = None) -> str:
    """시스템 프롬프트에 현재 서버 날짜/시간 및 대화 히스토리를 주입한다.

    state에 metadata.date_context가 있으면 그것을 사용하고,
    없으면 서버 시간에서 직접 생성한다.
    """
    date_ctx = None
    conversation_history = None
    if state:
        metadata = state.get("metadata") or {}
        date_ctx = metadata.get("date_context")
        conversation_history = metadata.get("conversation_history")
    if not date_ctx:
        date_ctx = get_current_date_context()

    parts = [f"[Server Time Info]\n{date_ctx}"]
    if conversation_history:
        parts.append(f"[Previous Conversation]\n{conversation_history}")
    parts.append(system_prompt)
    return "\n\n".join(parts)


def format_context(search_results: list[dict]) -> str:
    """검색 결과를 LLM context 문자열로 포맷한다."""
    parts = []
    for i, doc in enumerate(search_results, 1):
        parts.append(
            f"[{i}] Title: {doc.get('title', 'N/A')}\n"
            f"    Author: {doc.get('author', 'N/A')}\n"
            f"    DOI: {doc.get('doi', 'N/A')}\n"
            f"    Date: {doc.get('coverdate', 'N/A')}\n"
            f"    Keywords: {doc.get('paper_keyword', doc.get('paper_keywords', 'N/A'))}\n"
            f"    Chunk ({doc.get('chunk_id', '?')}/{doc.get('chunk_total_counts', '?')}):\n"
            f"    {doc.get('paper_text', '')}\n"
        )
    return "\n".join(parts)


def build_sources(search_results: list[dict]) -> list[dict]:
    """검색 결과를 source 응답 형식으로 변환한다."""
    sources = []
    seen = set()
    for doc in search_results:
        paper_id = doc.get("doi") or doc.get("filename", "")
        key = f"{paper_id}_{doc.get('chunk_id', 0)}"
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "paper_id": paper_id,
            "title": doc.get("title", ""),
            "author": doc.get("author", ""),
            "doi": doc.get("doi"),
            "chunk_id": doc.get("chunk_id", 0),
            "chunk_text": doc.get("paper_text", "")[:300],
            "score": doc.get("score", 0.0),
        })
    return sources


async def retrieve_by_query(
    query: str,
    user_id: str | None = None,
    filters: dict | None = None,
    top_k: int | None = None,
) -> list[dict]:
    """쿼리로 Milvus hybrid search를 수행한다 (embed → search)."""
    query_vector = await embeddings.embed_query(query, user_id=user_id)
    filter_expr = _build_filter_expr(filters)
    k = top_k or settings.TOP_K

    results = await vectorstore.hybrid_search(
        query_vector=query_vector,
        query_text=query,
        filters=filter_expr,
        top_k=k,
        user_id=user_id,
    )
    return results


async def multi_query_retrieve(
    queries: list[str],
    user_id: str | None = None,
    filters: dict | None = None,
    top_k_per_query: int = 3,
) -> list[dict]:
    """여러 쿼리로 검색하여 결과를 합친다 (중복 제거)."""
    all_results = []
    seen_ids = set()

    for q in queries:
        results = await retrieve_by_query(q, user_id=user_id, filters=filters, top_k=top_k_per_query)
        for r in results:
            rid = r.get("id")
            if rid is not None and rid not in seen_ids:
                seen_ids.add(rid)
                all_results.append(r)

    return all_results


async def llm_json_call(
    system_prompt: str,
    user_prompt: str,
    user_id: str | None = None,
    trace_name: str = "llm_json_call",
    temperature: float = 0.3,
    state: dict | None = None,
) -> dict | list:
    """LLM을 호출하여 JSON 결과를 파싱한다. 현재 서버 날짜 정보를 자동 주입."""
    messages = [
        {"role": "system", "content": inject_date_context(system_prompt, state)},
        {"role": "user", "content": user_prompt},
    ]
    raw = await llm.chat_completion(
        messages=messages,
        temperature=temperature,
        trace_name=trace_name,
        user_id=user_id,
    )
    cleaned = raw.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM JSON output, returning raw text")
        return {"raw": raw}


async def llm_text_call(
    system_prompt: str,
    user_prompt: str,
    user_id: str | None = None,
    trace_name: str = "llm_text_call",
    temperature: float = 0.3,
    state: dict | None = None,
) -> str:
    """LLM을 호출하여 텍스트 결과를 반환한다. 현재 서버 날짜 정보를 자동 주입."""
    messages = [
        {"role": "system", "content": inject_date_context(system_prompt, state)},
        {"role": "user", "content": user_prompt},
    ]
    return await llm.chat_completion(
        messages=messages,
        temperature=temperature,
        trace_name=trace_name,
        user_id=user_id,
    )


def _build_filter_expr(filters: dict | None) -> str | None:
    """dict 필터를 Milvus filter expression으로 변환한다."""
    if not filters:
        return None
    parts = []
    if filters.get("coverdate_from"):
        val = str(filters["coverdate_from"]).replace("-", "").replace("/", "")[:8]
        parts.append(f"coverdate >= {int(val)}")
    if filters.get("coverdate_to"):
        val = str(filters["coverdate_to"]).replace("-", "").replace("/", "")[:8]
        parts.append(f"coverdate <= {int(val)}")
    if filters.get("author"):
        parts.append(f'author like "%{filters["author"]}%"')
    if filters.get("doi"):
        parts.append(f'doi == "{filters["doi"]}"')
    if filters.get("keywords"):
        parts.append(f'paper_keyword like "%{filters["keywords"]}%"')
    return " and ".join(parts) if parts else None
