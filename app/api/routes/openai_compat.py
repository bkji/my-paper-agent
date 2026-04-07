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

import asyncio
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
from app.api.deps import verify_api_key, extract_usage
from app.core import llm
from app.core.langfuse_client import observe, trace_attributes, flush_langfuse, set_trace_io

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
@router.get("/models/", dependencies=[Depends(verify_api_key)], include_in_schema=False)
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
@router.post("/chat/completions/", dependencies=[Depends(verify_api_key)], include_in_schema=False)
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

    # Non-streaming
    return await _non_stream_oai(state, body.model, user_id)


async def _non_stream_oai(state: dict, model: str, user_id: str) -> dict:
    """trace_attributes를 @observe 바깥에서 설정하여 Unnamed trace 방지."""
    with trace_attributes(user_id=user_id, metadata={"source": "openai_compat"}, trace_name="api_openai_compat"):
        return await _non_stream_oai_observed(state, model, user_id)


@observe(name="api_openai_compat")
async def _non_stream_oai_observed(state: dict, model: str, user_id: str) -> dict:
    """Non-streaming: @observe로 1 trace 보장."""
    set_trace_io(input={"query": state.get("query", ""), "stream": False})
    result = await supervisor.ainvoke(state)
    answer = result.get("answer", "")
    set_trace_io(output={"answer": answer[:500], "agent_type": (result.get("metadata") or {}).get("agent_type"), "source_count": len(result.get("sources") or [])})
    return _make_response(answer, model, usage=extract_usage(result))


async def _run_oai_stream_pipeline(state: dict, queue: asyncio.Queue, user_id: str):
    """trace_attributes를 @observe 바깥에서 설정하여 Unnamed trace 방지."""
    with trace_attributes(user_id=user_id, metadata={"source": "openai_compat_stream"}, trace_name="api_openai_compat_stream"):
        return await _run_oai_stream_pipeline_observed(state, queue, user_id)


@observe(name="api_openai_compat_stream")
async def _run_oai_stream_pipeline_observed(state: dict, queue: asyncio.Queue, user_id: str):
    """@observe 안에서 전체 파이프라인 실행 → 1 trace 보장."""
    set_trace_io(input={"query": state.get("query", ""), "stream": True})
    state["metadata"]["_stream_mode"] = True

    try:
        result = await supervisor.ainvoke(state)
    except Exception as e:
        logger.error("[OAIStream] supervisor error: %s", e)
        await queue.put(("error", str(e)))
        return {}

    llm_messages = (result.get("metadata") or {}).get("_llm_messages")
    temperature = (result.get("metadata") or {}).get("_llm_temperature", 0.3)
    sources = result.get("sources") or []

    if not llm_messages:
        answer = result.get("answer", "관련 논문을 찾지 못했습니다.")
        citation = format_citation_text(sources)
        full_text = answer.rstrip() + citation
        await queue.put(("full_text", full_text))
        await queue.put(("usage", extract_usage(result)))
        set_trace_io(output={"answer": answer[:500], "agent_type": (result.get("metadata") or {}).get("agent_type"), "source_count": len(sources)})
        return result

    usage_out: dict = {}
    full_response = ""
    try:
        async for token in llm.chat_completion_stream(
            messages=llm_messages,
            temperature=temperature,
            trace_name="stream_generate",
            user_id=user_id,
            usage_out=usage_out,
        ):
            full_response += token
            await queue.put(("token", token))
    except Exception as e:
        logger.error("[OAIStream] LLM streaming error: %s", e)
        await queue.put(("error_token", str(e)))

    citation = format_citation_text(sources)
    if citation:
        await queue.put(("token", citation))

    # usage_out이 비어있으면 추정
    if not usage_out.get("prompt_tokens"):
        prompt_est = sum(len(m.get("content", "")) for m in llm_messages) // 4
        comp_est = len(full_response) // 4
        usage_out.setdefault("prompt_tokens", prompt_est)
        usage_out.setdefault("completion_tokens", comp_est)
        usage_out.setdefault("total_tokens", prompt_est + comp_est)

    await queue.put(("usage", usage_out))

    set_trace_io(output={
        "answer": (result.get("answer") or full_response)[:500],
        "agent_type": (result.get("metadata") or {}).get("agent_type"),
        "source_count": len(sources),
    })
    return result


async def _real_stream(
    state: dict, model: str, user_id: str = "", include_usage: bool = False,
):
    """실시간 스트리밍: @observe pipeline에서 Queue로 받아 OpenAI chunk로 변환."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    queue: asyncio.Queue = asyncio.Queue()
    usage_data: dict = {}

    # 첫 번째 chunk: role 전송
    yield _sse_role_chunk(chunk_id, model, include_usage)

    task = asyncio.create_task(_run_oai_stream_pipeline(state, queue, user_id))

    try:
        while not task.done():
            get_fut = asyncio.ensure_future(queue.get())
            done_tasks, pending = await asyncio.wait(
                [get_fut, task], return_when=asyncio.FIRST_COMPLETED,
            )
            for p in pending:
                if p is get_fut:
                    p.cancel()

            for t in done_tasks:
                if t is not task and not t.cancelled():
                    msg_type, data = t.result()
                    chunk = _handle_oai_msg(msg_type, data, chunk_id, model, include_usage, usage_data)
                    if chunk:
                        yield chunk

        # task 완료 후 queue 소진
        while not queue.empty():
            msg_type, data = queue.get_nowait()
            chunk = _handle_oai_msg(msg_type, data, chunk_id, model, include_usage, usage_data)
            if chunk:
                yield chunk

        # task 예외 확인
        try:
            task.result()
        except Exception as e:
            logger.error("[OAIStream] pipeline error: %s", e)
            yield _sse_chunk(chunk_id, model, f"\n\n(파이프라인 오류: {e})", include_usage)

        # finish_reason: "stop"
        done_chunk = {
            "id": chunk_id, "object": "chat.completion.chunk",
            "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop", "logprobs": None}],
        }
        if include_usage:
            done_chunk["usage"] = None
        yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"

        # usage chunk
        if include_usage:
            usage_chunk = {
                "id": chunk_id, "object": "chat.completion.chunk",
                "created": int(time.time()), "model": model,
                "choices": [],
                "usage": {
                    "prompt_tokens": usage_data.get("prompt_tokens", 0),
                    "completion_tokens": usage_data.get("completion_tokens", 0),
                    "total_tokens": usage_data.get("total_tokens", 0),
                },
            }
            yield f"data: {json.dumps(usage_chunk, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error("[OAIStream] unexpected error: %s", e)
        yield _sse_chunk(chunk_id, model, f"\n\n(오류: {e})", include_usage)
        stop_chunk = {
            "id": chunk_id, "object": "chat.completion.chunk",
            "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop", "logprobs": None}],
        }
        yield f"data: {json.dumps(stop_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        # @observe span이 완전히 닫힌 뒤 flush (trace 유실 방지)
        flush_langfuse()


def _handle_oai_msg(msg_type, data, chunk_id, model, include_usage, usage_data):
    """Queue 메시지를 OpenAI SSE chunk 문자열로 변환."""
    if msg_type == "token":
        return _sse_chunk(chunk_id, model, data, include_usage)
    elif msg_type == "full_text":
        # analytics 등 non-LLM 결과를 한번에 전송
        return _sse_chunk(chunk_id, model, data, include_usage)
    elif msg_type == "usage":
        if data:
            usage_data.update(data)
    elif msg_type == "error":
        return _sse_chunk(chunk_id, model, f"\n\n(처리 중 오류: {data})", include_usage)
    elif msg_type == "error_token":
        return _sse_chunk(chunk_id, model, f"\n\n(스트리밍 중 오류: {data})", include_usage)
    return None


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
