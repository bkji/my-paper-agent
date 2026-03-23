"""OpenAI-compatible API wrapper — Open WebUI 등 외부 UI 연동용.

엔드포인트:
    GET  /v1/models              → 모델 목록
    POST /v1/chat/completions    → 채팅 (non-streaming / streaming)

스트리밍 모드:
    stream=true일 때 실제 LLM 스트리밍을 사용한다.
    1) 검색/분류 파이프라인 실행 (stream_mode: LLM 최종 호출 스킵)
    2) 저장된 messages로 llm.chat_completion_stream() 실시간 스트리밍
    3) 스트리밍 완료 후 참조 문헌 + 저작권 고지 전송
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.agents.supervisor import supervisor
from app.agents.citation_agent import format_citation_text
from app.config import settings
from app.core import llm
from app.core.langfuse_client import trace_attributes

logger = logging.getLogger(__name__)
router = APIRouter()

MODEL_ID = "co-scientist-bk03"

_bearer_scheme = HTTPBearer(auto_error=False)


async def _verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> None:
    expected = settings.OPENAI_COMPAT_API_KEY
    if not expected:
        return
    if credentials is None or credentials.credentials != expected:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


class OAIMessage(BaseModel):
    role: str
    content: str


class OAIRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[OAIMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False


@router.get("/models", dependencies=[Depends(_verify_api_key)])
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "created": 1700000000,
                "owned_by": "co-scientist-bk03",
            }
        ],
    }


def _build_state(request: OAIRequest) -> dict:
    """요청 메시지에서 query, conversation_history를 추출하여 state를 구성한다."""
    query = ""
    system_ctx = ""
    chat_history: list[dict] = []

    for msg in request.messages:
        if msg.role == "system":
            system_ctx = msg.content
        elif msg.role in ("user", "assistant"):
            chat_history.append({"role": msg.role, "content": msg.content})

    for msg in reversed(request.messages):
        if msg.role == "user":
            query = msg.content
            break

    if system_ctx:
        query = f"[System context: {system_ctx}]\n\n{query}"

    # 멀티턴: 이전 대화 히스토리를 컨텍스트로 포함
    conversation_context = ""
    if len(chat_history) > 1:
        prev_turns = chat_history[:-1]
        lines = []
        for turn in prev_turns[-6:]:
            role_label = "사용자" if turn["role"] == "user" else "어시스턴트"
            content = turn["content"]
            if turn["role"] == "assistant" and len(content) > 300:
                content = content[:300] + "..."
            lines.append(f"{role_label}: {content}")
        conversation_context = "\n".join(lines)

    state = {
        "query": query,
        "user_id": "openwebui",
        "filters": {},
        "metadata": {},
    }
    if conversation_context:
        state["metadata"]["conversation_history"] = conversation_context

    return state


@router.post("/chat/completions", dependencies=[Depends(_verify_api_key)])
async def chat_completions(request: OAIRequest):
    state = _build_state(request)

    if not state["query"]:
        if request.stream:
            return StreamingResponse(
                _fake_stream("질문을 입력해 주세요.", request.model),
                media_type="text/event-stream",
            )
        return _make_response("질문을 입력해 주세요.", request.model)

    if request.stream:
        return StreamingResponse(
            _real_stream(state, request.model),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming: 기존 방식
    with trace_attributes(user_id="openwebui", metadata={"source": "openai_compat"}):
        result = await supervisor.ainvoke(state)

    return _make_response(result.get("answer", ""), request.model)


async def _real_stream(state: dict, model: str):
    """실시간 스트리밍: 검색/분류 후 LLM 응답을 토큰 단위로 전송한다."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    # Phase 1: 검색 + 분류 (LLM 최종 호출은 스킵)
    state["metadata"]["_stream_mode"] = True

    with trace_attributes(user_id="openwebui", metadata={"source": "openai_compat_stream"}):
        result = await supervisor.ainvoke(state)

    llm_messages = (result.get("metadata") or {}).get("_llm_messages")
    temperature = (result.get("metadata") or {}).get("_llm_temperature", 0.3)
    sources = result.get("sources") or []

    if not llm_messages:
        # LLM messages가 없으면 (에러 또는 빈 결과) 기존 answer를 스트리밍
        answer = result.get("answer", "관련 논문을 찾지 못했습니다.")
        citation = format_citation_text(sources)
        full_text = answer.rstrip() + citation
        async for chunk in _fake_stream(full_text, model):
            yield chunk
        return

    # Phase 2: LLM 실시간 스트리밍
    full_answer = ""
    try:
        async for token in llm.chat_completion_stream(
            messages=llm_messages,
            temperature=temperature,
            trace_name="stream_generate",
            user_id="openwebui",
        ):
            full_answer += token
            yield _sse_chunk(chunk_id, model, token)
    except Exception as e:
        logger.error("[Stream] LLM streaming error: %s", e)
        error_msg = f"\n\n(스트리밍 중 오류 발생: {e})"
        yield _sse_chunk(chunk_id, model, error_msg)

    # Phase 3: 참조 문헌 + 저작권 고지
    citation = format_citation_text(sources)
    if citation:
        yield _sse_chunk(chunk_id, model, citation)

    # Done
    done_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def _sse_chunk(chunk_id: str, model: str, content: str) -> str:
    """SSE 포맷의 스트리밍 청크를 생성한다."""
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


async def _fake_stream(content: str, model: str):
    """완성된 텍스트를 줄 단위로 스트리밍한다 (fallback용)."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    sentences = content.split("\n")

    for sentence in sentences:
        yield _sse_chunk(chunk_id, model, sentence + "\n")

    done_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def _make_response(content: str, model: str) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
