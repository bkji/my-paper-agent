"""Agent 공통 헬퍼 — 검색, context 포맷, source 변환 등 재사용 함수."""
from __future__ import annotations

import json
import logging
import re

from app.config import settings
from app.core import embeddings, vectorstore, llm
from app.core.tools import get_current_date_context

logger = logging.getLogger(__name__)


def extract_paper_title_from_history(state: dict) -> str | None:
    """대화 히스토리에서 이전 턴에 참조된 논문 제목을 추출한다.

    "논문의 2.1 부분 번역해줘" 같은 현재 쿼리에서 제목 없이 논문을 참조할 때,
    이전 사용자 메시지에서 가장 최근 논문 제목을 찾는다.

    Returns:
        논문 제목 키워드 (str) or None
    """
    query = state.get("query", "")
    # 현재 쿼리에 이미 긴 영문 제목이 있으면 히스토리 탐색 불필요
    if re.search(r'[A-Za-z]{3,}\s+[A-Za-z]{3,}\s+[A-Za-z]{3,}.*논문', query):
        return None

    # 현재 쿼리가 "논문의", "이 논문", "그 논문", "위 논문" 등 논문 참조 표현을 포함하는지 확인
    if not re.search(r'논문의|이\s*논문|그\s*논문|위\s*논문|해당\s*논문|같은\s*논문', query):
        return None

    conversation_history = (state.get("metadata") or {}).get("conversation_history", "")
    if not conversation_history:
        return None

    # 히스토리에서 사용자 메시지를 역순으로 탐색하여 가장 최근 논문 제목 찾기
    # 패턴: "영문 제목... 논문" 형태
    user_msgs = re.findall(r'사용자:\s*(.+)', conversation_history)
    for msg in reversed(user_msgs):
        # 긴 영문 구문 + "논문" 패턴 (논문 제목으로 추정)
        m = re.search(r'([A-Za-z][\w\s\-:,()]{10,}?)\s*논문', msg)
        if m:
            title = m.group(1).strip()
            logger.info("[Common] extracted paper title from history: '%s'", title[:60])
            return title

    # 어시스턴트 응답에서 제목 찾기 (제목: xxx 또는 **Title** 패턴)
    assistant_msgs = re.findall(r'어시스턴트:\s*(.+)', conversation_history)
    for msg in reversed(assistant_msgs):
        m = re.search(r'(?:제목|Title)[:\s]*([A-Za-z][\w\s\-:,()]{10,}?)(?:\s*[,\n|])', msg)
        if m:
            title = m.group(1).strip()
            logger.info("[Common] extracted paper title from assistant response: '%s'", title[:60])
            return title

    return None


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
    """LLM을 호출하여 텍스트 결과를 반환한다. 현재 서버 날짜 정보를 자동 주입.

    stream_mode가 활성화된 경우, LLM 호출 대신 messages를 state에 저장하고
    placeholder를 반환한다 (API 레이어에서 실시간 스트리밍 처리).
    """
    messages = [
        {"role": "system", "content": inject_date_context(system_prompt, state)},
        {"role": "user", "content": user_prompt},
    ]

    # Stream mode: LLM 호출 스킵, messages만 저장
    if state and (state.get("metadata") or {}).get("_stream_mode"):
        state["metadata"]["_llm_messages"] = messages
        state["metadata"]["_llm_temperature"] = temperature
        return ""

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
