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

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.supervisor import supervisor
from app.agents.citation_agent import format_citation_text
from app.api.deps import verify_api_key
from app.core import llm
from app.core.langfuse_client import trace_attributes, flush_langfuse

logger = logging.getLogger(__name__)
router = APIRouter()

MODEL_ID = "co-scientist-bk03"


class OAIMessage(BaseModel):
    role: str
    content: str


class OAIStreamOptions(BaseModel):
    include_usage: Optional[bool] = False


class OAIRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[OAIMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    stream_options: Optional[OAIStreamOptions] = None
    user: Optional[str] = None


def _extract_user_id(request: Request, body: OAIRequest) -> str:
    """Open WebUI 요청에서 실제 사용자 ID를 추출한다.

    우선순위:
    1. body.user 필드 (OpenAI API 표준)
    2. X-OpenWebUI-User-Name 헤더
    3. X-OpenWebUI-User-Email 헤더
    4. fallback: PC 이름 (get_default_user_id)
    """
    if body.user:
        return body.user
    header_name = request.headers.get("x-openwebui-user-name")
    if header_name:
        return header_name
    header_email = request.headers.get("x-openwebui-user-email")
    if header_email:
        return header_email
    return "unknown"


@router.get("/models", dependencies=[Depends(verify_api_key)])
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


def _build_state(body: OAIRequest, user_id: str) -> dict:
    """요청 메시지에서 query를 추출하고, messages를 supervisor에 넘긴다.

    대화 히스토리 조립(압축, 포맷팅)은 supervisor.build_history에서 통합 처리한다.
    """
    query = ""
    system_ctx = ""
    chat_messages: list[dict] = []

    for msg in body.messages:
        if msg.role == "system":
            system_ctx = msg.content
        elif msg.role in ("user", "assistant"):
            chat_messages.append({"role": msg.role, "content": msg.content})

    for msg in reversed(body.messages):
        if msg.role == "user":
            query = msg.content
            break

    if system_ctx:
        query = f"[System context: {system_ctx}]\n\n{query}"

    state = {
        "query": query,
        "user_id": user_id,
        "filters": {},
        "metadata": {},
    }
    # messages 배열을 그대로 전달 → supervisor.build_history에서 변환
    if chat_messages:
        state["metadata"]["messages"] = chat_messages

    return state


@router.post("/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request, body: OAIRequest):
    user_id = _extract_user_id(request, body)
    state = _build_state(body, user_id)

    if not state["query"]:
        if body.stream:
            include_usage = bool(body.stream_options and body.stream_options.include_usage)
            return StreamingResponse(
                _fake_stream("질문을 입력해 주세요.", body.model, include_usage=include_usage),
                media_type="text/event-stream",
            )
        return _make_response("질문을 입력해 주세요.", body.model)

    if body.stream:
        include_usage = bool(body.stream_options and body.stream_options.include_usage)
        return StreamingResponse(
            _real_stream(state, body.model, user_id, include_usage=include_usage),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming: 기존 방식
    with trace_attributes(user_id=user_id, metadata={"source": "openai_compat"}):
        result = await supervisor.ainvoke(state)

    usage = (result.get("metadata") or {}).get("usage") or {}
    return _make_response(result.get("answer", ""), body.model, usage=usage)


async def _real_stream(
    state: dict, model: str, user_id: str = "", include_usage: bool = False,
):
    """실시간 스트리밍: 검색/분류 후 LLM 응답을 토큰 단위로 전송한다."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    try:
        # trace_attributes가 전체 스트리밍 구간을 감싼다
        with trace_attributes(user_id=user_id, metadata={"source": "openai_compat_stream"}):
            # 첫 번째 chunk: role 전송 (OpenAI 스펙 필수)
            yield _sse_role_chunk(chunk_id, model, include_usage)

            # Phase 1: 검색 + 분류 (LLM 최종 호출은 스킵)
            state["metadata"]["_stream_mode"] = True
            result = await supervisor.ainvoke(state)

            llm_messages = (result.get("metadata") or {}).get("_llm_messages")
            temperature = (result.get("metadata") or {}).get("_llm_temperature", 0.3)
            sources = result.get("sources") or []

            if not llm_messages:
                # LLM messages가 없으면 (에러 또는 빈 결과) 기존 answer를 스트리밍
                answer = result.get("answer", "관련 논문을 찾지 못했습니다.")
                citation = format_citation_text(sources)
                full_text = answer.rstrip() + citation
                async for chunk in _fake_stream(full_text, model, send_role=False, include_usage=include_usage):
                    yield chunk
                return

            # Phase 2: LLM 실시간 스트리밍
            full_answer = ""
            usage_out: dict = {}
            try:
                async for token in llm.chat_completion_stream(
                    messages=llm_messages,
                    temperature=temperature,
                    trace_name="stream_generate",
                    user_id=user_id,
                    usage_out=usage_out,
                ):
                    full_answer += token
                    yield _sse_chunk(chunk_id, model, token, include_usage)
            except Exception as e:
                logger.error("[Stream] LLM streaming error: %s", e)
                error_msg = f"\n\n(스트리밍 중 오류 발생: {e})"
                yield _sse_chunk(chunk_id, model, error_msg, include_usage)

            # Phase 3: 참조 문헌 + 저작권 고지
            citation = format_citation_text(sources)
            if citation:
                yield _sse_chunk(chunk_id, model, citation, include_usage)

            # finish_reason: "stop" chunk
            done_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop", "logprobs": None}],
            }
            if include_usage:
                done_chunk["usage"] = None
            yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"

            # usage chunk (stream_options.include_usage=true 일 때만)
            if include_usage:
                usage_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [],
                    "usage": {
                        "prompt_tokens": usage_out.get("prompt_tokens", 0),
                        "completion_tokens": usage_out.get("completion_tokens", 0),
                        "total_tokens": usage_out.get("total_tokens", 0),
                    },
                }
                yield f"data: {json.dumps(usage_chunk, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
    finally:
        flush_langfuse()


def _sse_role_chunk(chunk_id: str, model: str, include_usage: bool = False) -> str:
    """스트리밍 첫 번째 chunk: role=assistant 전송 (OpenAI 스펙 필수)."""
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None, "logprobs": None}],
    }
    if include_usage:
        chunk["usage"] = None
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _sse_chunk(chunk_id: str, model: str, content: str, include_usage: bool = False) -> str:
    """SSE 포맷의 스트리밍 청크를 생성한다."""
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None, "logprobs": None}],
    }
    if include_usage:
        chunk["usage"] = None
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


async def _fake_stream(
    content: str, model: str, send_role: bool = True, include_usage: bool = False,
):
    """완성된 텍스트를 줄 단위로 스트리밍한다 (fallback용)."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    # 첫 번째 chunk: role 전송
    if send_role:
        yield _sse_role_chunk(chunk_id, model, include_usage)

    sentences = content.split("\n")
    for i, sentence in enumerate(sentences):
        # 줄바꿈 복원 (마지막 줄에는 추가하지 않음)
        text = sentence + "\n" if i < len(sentences) - 1 else sentence
        if text:
            yield _sse_chunk(chunk_id, model, text, include_usage)

    # finish_reason: "stop" chunk
    done_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop", "logprobs": None}],
    }
    if include_usage:
        done_chunk["usage"] = None
    yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"

    # usage chunk (fake_stream은 토큰 사용량 불명이므로 0으로 전송)
    if include_usage:
        usage_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
        yield f"data: {json.dumps(usage_chunk, ensure_ascii=False)}\n\n"

    yield "data: [DONE]\n\n"


def _make_response(content: str, model: str, usage: dict | None = None) -> dict:
    usage = usage or {}
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
                "logprobs": None,
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }
