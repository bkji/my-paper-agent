"""Agent 공통 헬퍼 — 검색, context 포맷, source 변환 등 재사용 함수."""
from __future__ import annotations

import asyncio
import json
import logging
import re

from app.config import settings
from app.core import embeddings, vectorstore, llm
from app.core.tools import get_current_date_context

logger = logging.getLogger(__name__)


def _extract_nth_paper_from_history(query: str, conversation_history: str) -> str | None:
    """'N번째 논문' 패턴을 감지하여 히스토리에서 해당 순번의 논문 제목을 추출한다."""
    # "1번째", "첫번째", "첫 번째", "두번째", "두 번째", "세번째" 등
    ordinal_map = {"첫": 1, "두": 2, "세": 3, "네": 4, "다섯": 5}
    idx = None
    from_citation = False  # "참조 문헌 N번" 패턴인지 여부

    # "참조 문헌 N번" / "참조문헌 N번" 패턴
    m = re.search(r'참조\s*문헌\s*(\d+)\s*번', query)
    if m:
        idx = int(m.group(1))
        from_citation = True

    # 숫자 + 번째 패턴
    if idx is None:
        m = re.search(r'(\d+)\s*번째\s*논문', query)
        if m:
            idx = int(m.group(1))

    # 한글 서수 패턴
    if idx is None:
        m = re.search(r'(첫|두|세|네|다섯)\s*번째\s*논문', query)
        if m:
            idx = ordinal_map.get(m.group(1))

    if idx is None or idx < 1:
        return None

    # "참조 문헌 N번" → 참조 문헌 섹션에서 추출 (유사도 순)
    # "N번째 논문" → LLM 본문에서 추출 (사용자가 보는 순서)
    titles = []
    if from_citation:
        # 참조 문헌 섹션에서만 추출
        in_citation_section = False
        for line in conversation_history.split("\n"):
            if "참조 문헌" in line or "참조문헌" in line:
                in_citation_section = True
                continue
            if in_citation_section and line.startswith("사용자:"):
                in_citation_section = False
            if not in_citation_section:
                continue
            tm = re.search(r'\d+[.)]\s*제목:\s*(.+?)(?:\s*,\s*저자|\s*,\s*DOI|\s*\(|\s*$)', line)
            if tm:
                titles.append(tm.group(1).strip().rstrip(",;."))
    else:
        # LLM 본문에서만 추출 (참조 문헌 섹션 제외)
        in_citation_section = False
        for line in conversation_history.split("\n"):
            if "참조 문헌" in line or "참조문헌" in line:
                in_citation_section = True
                continue
            if in_citation_section and line.startswith("사용자:"):
                in_citation_section = False
            if in_citation_section:
                continue
            tm = re.search(r'\d+[.)]\s*제목:\s*(.+?)(?:\s*,\s*저자|\s*,\s*DOI|\s*$)', line)
            if not tm:
                tm = re.search(r'\d+[.)]\s*([A-Za-z][A-Za-z\w\s\-:,()]{5,})', line)
            if tm:
                titles.append(tm.group(1).strip().rstrip(",;."))

    if titles and idx <= len(titles):
        title = titles[idx - 1]
        src_label = "citation" if from_citation else "body"
        logger.info("[Common] extracted %d-th paper title from %s: '%s'", idx, src_label, title[:60])
        return title

    return None


def extract_paper_title_from_history(state: dict) -> str | None:
    """대화 히스토리에서 이전 턴에 참조된 논문 제목을 추출한다.

    지원 패턴:
    - "논문의 2.1 부분 번역해줘" → 이전 턴 논문 제목 추출
    - "이 논문", "그 논문", "위 논문" → 이전 턴 논문 제목 추출
    - "1번째 논문", "첫번째 논문", "두번째 논문" → 이전 응답 본문에서 N번째 논문 추출
    - "참조 문헌 1번", "참조문헌 3번" → 참조 문헌 섹션에서 N번째 논문 추출

    Returns:
        논문 제목 키워드 (str) or None
    """
    query = state.get("query", "")
    conversation_history = (state.get("metadata") or {}).get("conversation_history", "")

    # 현재 쿼리에 이미 긴 영문 제목이 있으면 히스토리 탐색 불필요
    if re.search(r'[A-Za-z]{3,}\s+[A-Za-z]{3,}\s+[A-Za-z]{3,}.*논문', query):
        return None

    if not conversation_history:
        return None

    # "N번째 논문" 패턴 → 이전 응답에서 순번으로 논문 제목 추출
    nth_title = _extract_nth_paper_from_history(query, conversation_history)
    if nth_title:
        return nth_title

    # "논문의", "이 논문", "그 논문" 등 논문 참조 표현 확인
    if not re.search(r'논문의|이\s*논문|그\s*논문|위\s*논문|해당\s*논문|같은\s*논문', query):
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


def _accumulate_usage(state: dict, usage_out: dict):
    """토큰 사용량을 state.metadata.usage에 누적한다 (하위 호환용, 내부 합산).

    주의: API 응답에는 _set_final_usage()로 설정된 최종 생성 usage만 반환.
    이 함수는 내부 추적/디버깅 목적으로 유지.
    """
    metadata = state.setdefault("metadata", {})
    existing = metadata.setdefault("_internal_usage", {})
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        existing[key] = existing.get(key, 0) + usage_out.get(key, 0)


def _set_final_usage(state: dict, usage_out: dict):
    """최종 답변 생성 LLM 호출의 토큰 사용량을 API 응답용으로 설정한다.

    API 응답의 usage 필드에는 이 값만 반환된다.
    내부 LLM 호출(의도 분류, 조건 추출 등)은 Langfuse에서 개별 추적.
    """
    metadata = state.setdefault("metadata", {})
    metadata["usage"] = {
        "prompt_tokens": usage_out.get("prompt_tokens", 0),
        "completion_tokens": usage_out.get("completion_tokens", 0),
        "total_tokens": usage_out.get("total_tokens", 0),
    }


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
            "score_rrf": doc.get("score_rrf", 0.0),
            "score_dense": doc.get("score_dense", 0.0),
            "score_sparse": doc.get("score_sparse", 0.0),
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


# 동시 검색 수 제한 — 임베딩/Milvus 서버 과부하 방지
_SEARCH_SEMAPHORE = asyncio.Semaphore(5)


async def _retrieve_with_limit(
    query: str,
    user_id: str | None,
    filters: dict | None,
    top_k: int,
) -> list[dict]:
    """세마포어로 동시 검색 수를 제한한다."""
    async with _SEARCH_SEMAPHORE:
        return await retrieve_by_query(query, user_id=user_id, filters=filters, top_k=top_k)


async def multi_query_retrieve(
    queries: list[str],
    user_id: str | None = None,
    filters: dict | None = None,
    top_k_per_query: int = 3,
) -> list[dict]:
    """여러 쿼리로 검색하여 결과를 합친다 (중복 제거, 병렬 실행, 동시성 제한)."""
    if not queries:
        return []

    # 모든 쿼리를 병렬로 실행 (세마포어로 동시 5개 제한)
    tasks = [
        _retrieve_with_limit(q, user_id=user_id, filters=filters, top_k=top_k_per_query)
        for q in queries
    ]
    results_list = await asyncio.gather(*tasks)

    # 중복 제거하며 합침
    all_results = []
    seen_ids = set()
    for results in results_list:
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
    usage_out: dict = {}
    raw = await llm.chat_completion(
        messages=messages,
        temperature=temperature,
        trace_name=trace_name,
        user_id=user_id,
        usage_out=usage_out,
    )
    # 내부 호출(분류/조건추출 등) → _internal_usage에만 누적, API 응답 usage에는 미포함
    if state is not None and usage_out:
        _accumulate_usage(state, usage_out)  # _internal_usage에 누적
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

    usage_out: dict = {}
    result = await llm.chat_completion(
        messages=messages,
        temperature=temperature,
        trace_name=trace_name,
        user_id=user_id,
        usage_out=usage_out,
    )
    # 최종 답변 생성 → API 응답 usage에 설정 (내부 호출 합산이 아닌 이 호출만)
    if state is not None and usage_out:
        _set_final_usage(state, usage_out)
    return result


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
