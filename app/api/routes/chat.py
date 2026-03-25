"""Chat API — 단일 엔드포인트로 모든 Agent를 호출한다."""
import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agents.supervisor import supervisor
from app.agents.citation_agent import format_citation_text
from app.api.deps import verify_api_key, build_chat_state
from app.core import llm
from app.core.langfuse_client import observe, trace_attributes, flush_langfuse
from app.models.schemas import ChatRequest, ChatResponse, UsageInfo

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=None, dependencies=[Depends(verify_api_key)])
async def chat(request: ChatRequest):
    logger.info("POST /api/chat: agent_type=%s, stream=%s, query=%s",
                request.agent_type, request.stream, request.query[:100])

    state = build_chat_state(request)

    if request.stream:
        state["metadata"]["_stream_mode"] = True
        return StreamingResponse(
            _stream_response(state),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming — @observe가 전체 구간을 커버
    return await _non_stream_chat(request, state)


@observe(name="api_chat")
async def _non_stream_chat(request: ChatRequest, state: dict) -> ChatResponse:
    with trace_attributes(user_id=request.user_id, metadata={"agent_type": request.agent_type or "auto"}):
        result = await supervisor.ainvoke(state)

    usage = (result.get("metadata") or {}).get("usage") or {}
    return ChatResponse(
        answer=result.get("answer", ""),
        sources=result.get("sources"),
        trace_id=result.get("trace_id"),
        usage=UsageInfo(**usage) if usage else None,
    )


def _sse_event(event: str, data: dict) -> str:
    """SSE 포맷: event 타입 + JSON data."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── 스트리밍: @observe pipeline + Queue ──────────────────────────


@observe(name="api_chat_stream")
async def _run_stream_pipeline(state: dict, queue: asyncio.Queue):
    """@observe 안에서 전체 파이프라인 실행 → 1 trace 보장."""
    with trace_attributes(
        user_id=state.get("user_id"),
        metadata={"source": "api_chat_stream"},
    ):
        await queue.put(("status", "논문 검색 및 질문 분석 중..."))

        try:
            result = await supervisor.ainvoke(state)
        except Exception as e:
            logger.error("[ChatStream] supervisor error: %s", e)
            await queue.put(("error", f"처리 중 오류 발생: {e}"))
            return {}

        llm_messages = (result.get("metadata") or {}).get("_llm_messages")
        temperature = (result.get("metadata") or {}).get("_llm_temperature", 0.3)
        sources = result.get("sources") or []

        if not llm_messages:
            answer = result.get("answer", "관련 논문을 찾지 못했습니다.")
            await queue.put(("token", answer))
            await queue.put(("sources", sources))
            usage = (result.get("metadata") or {}).get("usage") or {}
            await queue.put(("usage", usage))
            return result

        await queue.put(("status", "답변 생성 중..."))

        usage_out: dict = {}
        try:
            async for token in llm.chat_completion_stream(
                messages=llm_messages,
                temperature=temperature,
                trace_name="chat_stream_generate",
                user_id=state.get("user_id"),
                usage_out=usage_out,
            ):
                await queue.put(("token", token))
        except Exception as e:
            logger.error("[ChatStream] LLM streaming error: %s", e)
            await queue.put(("error", f"답변 생성 중 오류: {e}"))

        citation = format_citation_text(sources)
        if citation:
            await queue.put(("token", citation))

        await queue.put(("sources", sources))
        await queue.put(("usage", usage_out))

        return result


async def _stream_response(state: dict):
    """SSE generator — @observe pipeline에서 Queue로 받은 이벤트를 SSE로 변환."""
    stream_id = uuid.uuid4().hex[:12]
    queue: asyncio.Queue = asyncio.Queue()
    usage_data: dict = {}

    task = asyncio.create_task(_run_stream_pipeline(state, queue))

    try:
        while True:
            done_tasks, _ = await asyncio.wait(
                [asyncio.ensure_future(queue.get()), task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for t in done_tasks:
                if t is task:
                    while not queue.empty():
                        msg_type, data = queue.get_nowait()
                        event = _handle_msg(msg_type, data, usage_data)
                        if event:
                            yield event
                    yield _sse_event("done", {
                        "stream_id": stream_id,
                        "usage": usage_data if usage_data else None,
                    })
                    task.result()
                    return
                else:
                    msg_type, data = t.result()
                    event = _handle_msg(msg_type, data, usage_data)
                    if event:
                        yield event

    except Exception as e:
        logger.error("[ChatStream] unexpected error: %s", e)
        yield _sse_event("error", {"message": f"예기치 않은 오류: {e}"})
        yield _sse_event("done", {"stream_id": stream_id})
    finally:
        if not task.done():
            task.cancel()
        flush_langfuse()


def _handle_msg(msg_type: str, data, usage_data: dict):
    """Queue 메시지를 SSE 이벤트 문자열로 변환."""
    if msg_type == "status":
        return _sse_event("status", {"message": data})
    elif msg_type == "token":
        return _sse_event("token", {"content": data})
    elif msg_type == "sources":
        if data:
            return _sse_event("sources", {
                "sources": [s if isinstance(s, dict) else s.model_dump() for s in data],
            })
    elif msg_type == "usage":
        if data:
            usage_data.update(data)
    elif msg_type == "error":
        return _sse_event("error", {"message": data})
    return None
