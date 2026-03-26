"""Chat API v2 — SSE 스트리밍 개선 + Langfuse 1-trace 보장.

v1(`/api/chat`) 대비 개선:
  1. sse-starlette 기반 개별 토큰 즉시 전송 (버퍼링/뭉침 해소)
  2. 스트리밍에서도 질문 1건 = Langfuse trace 1개 보장
     (@observe 함수 안에서 전체 파이프라인 실행, Queue로 generator에 전달)
  3. 스트리밍 종료 시 Langfuse flush 보장
  4. done 이벤트에 elapsed_ms, usage 포함
"""
import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.agents.supervisor import supervisor
from app.agents.citation_agent import format_citation_text
from app.api.deps import verify_api_key, build_chat_state, extract_usage
from app.core import llm
from app.core.langfuse_client import observe, trace_attributes, flush_langfuse
from app.models.schemas import ChatRequest, ChatResponse, UsageInfo

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 헬퍼 ─────────────────────────────────────────────────────────


def _sse(event: str, data: dict) -> ServerSentEvent:
    """SSE 이벤트 객체 생성 — sse-starlette가 개별 전송을 보장한다."""
    return ServerSentEvent(
        event=event,
        data=json.dumps(data, ensure_ascii=False),
    )


def _elapsed_ms(t_start: float) -> int:
    return int((time.time() - t_start) * 1000)


# ── Non-streaming ────────────────────────────────────────────────


@observe(name="api_chat_v2")
async def _non_stream_response(request: ChatRequest, state: dict) -> ChatResponse:
    """Non-streaming: @observe로 전체 구간 트레이싱."""
    with trace_attributes(
        user_id=request.user_id,
        metadata={"agent_type": request.agent_type or "auto", "source": "api_chat_v2"},
    ):
        result = await supervisor.ainvoke(state)
    usage = extract_usage(result)
    return ChatResponse(
        answer=result.get("answer", ""),
        sources=result.get("sources"),
        trace_id=result.get("trace_id"),
        usage=UsageInfo(**usage),
    )


# ── Streaming ────────────────────────────────────────────────────


@observe(name="api_chat_v2_stream")
async def _run_stream_pipeline(state: dict, queue: asyncio.Queue):
    """@observe 안에서 전체 파이프라인을 실행한다.

    이 함수가 @observe로 감싸져 있으므로 내부의 모든 @observe 호출
    (supervisor 노드, LLM 호출 등)이 하나의 trace에 span으로 연결된다.

    결과는 queue를 통해 generator에 실시간 전달한다.
    """
    with trace_attributes(
        user_id=state.get("user_id"),
        metadata={"source": "api_chat_v2_stream"},
    ):
        # Phase 1: 검색 + 분류
        await queue.put(("status", "논문 검색 및 질문 분석 중..."))

        try:
            result = await supervisor.ainvoke(state)
        except Exception as e:
            logger.error("[ChatStreamV2] supervisor error: %s", e)
            await queue.put(("error", f"처리 중 오류 발생: {e}"))
            return {}

        llm_messages = (result.get("metadata") or {}).get("_llm_messages")
        temperature = (result.get("metadata") or {}).get("_llm_temperature", 0.3)
        sources = result.get("sources") or []

        # LLM messages가 없으면 (analytics 등) 기존 answer 전달
        if not llm_messages:
            answer = result.get("answer", "관련 논문을 찾지 못했습니다.")
            await queue.put(("token", answer))
            await queue.put(("sources", sources))
            await queue.put(("usage", extract_usage(result)))
            return result

        # Phase 2: LLM 실시간 스트리밍
        await queue.put(("status", "답변 생성 중..."))

        usage_out: dict = {}
        try:
            async for token in llm.chat_completion_stream(
                messages=llm_messages,
                temperature=temperature,
                trace_name="chat_v2_stream_generate",
                user_id=state.get("user_id"),
                usage_out=usage_out,
            ):
                await queue.put(("token", token))
        except Exception as e:
            logger.error("[ChatStreamV2] LLM streaming error: %s", e)
            await queue.put(("error", f"답변 생성 중 오류: {e}"))

        # Phase 3: 참조 문헌
        citation = format_citation_text(sources)
        if citation:
            await queue.put(("token", citation))

        # Phase 4: 소스 + usage
        await queue.put(("sources", sources))
        await queue.put(("usage", usage_out))

        return result


async def _stream_response_v2(state: dict):
    """SSE generator — @observe pipeline에서 Queue로 받은 이벤트를 SSE로 변환.

    이벤트 종류:
      - status  : 파이프라인 진행 상태
      - token   : LLM 토큰 1개
      - sources : 참조 논문 목록
      - done    : 스트리밍 완료 (stream_id, elapsed_ms, usage 포함)
      - error   : 에러 발생
    """
    stream_id = uuid.uuid4().hex[:12]
    t_start = time.time()
    queue: asyncio.Queue = asyncio.Queue()
    usage_data: dict = {}

    # @observe 함수를 background task로 실행
    # → 1 trace 안에서 supervisor + LLM 스트리밍 모두 span으로 연결
    task = asyncio.create_task(_run_stream_pipeline(state, queue))

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
                    event = _handle_queue_msg(msg_type, data, usage_data)
                    if event:
                        yield event

        # task 완료 후 queue 소진
        while not queue.empty():
            msg_type, data = queue.get_nowait()
            event = _handle_queue_msg(msg_type, data, usage_data)
            if event:
                yield event

        # task 예외 확인
        try:
            task.result()
        except Exception as e:
            logger.error("[ChatStreamV2] pipeline error: %s", e)
            yield _sse("error", {"message": f"파이프라인 오류: {e}"})

        yield _sse("done", {
            "stream_id": stream_id,
            "elapsed_ms": _elapsed_ms(t_start),
            "usage": usage_data if usage_data else None,
        })

    except Exception as e:
        logger.error("[ChatStreamV2] unexpected error: %s", e)
        yield _sse("error", {"message": f"예기치 않은 오류: {e}"})
        yield _sse("done", {
            "stream_id": stream_id,
            "elapsed_ms": _elapsed_ms(t_start),
        })
    finally:
        if not task.done():
            task.cancel()
        flush_langfuse()
        logger.info(
            "[ChatStreamV2] stream_id=%s completed (%.1fs)",
            stream_id, time.time() - t_start,
        )


def _handle_queue_msg(msg_type: str, data, usage_data: dict):
    """Queue 메시지를 SSE 이벤트로 변환한다."""
    if msg_type == "status":
        return _sse("status", {"message": data})
    elif msg_type == "token":
        return _sse("token", {"content": data})
    elif msg_type == "sources":
        if data:
            return _sse("sources", {
                "sources": [
                    s if isinstance(s, dict) else s.model_dump()
                    for s in data
                ],
            })
    elif msg_type == "usage":
        if data:
            usage_data.update(data)
    elif msg_type == "error":
        return _sse("error", {"message": data})
    return None


# ── 엔드포인트 ───────────────────────────────────────────────────


@router.post("/", response_model=None, dependencies=[Depends(verify_api_key)])
async def chat_v2(request: ChatRequest):
    """채팅 API v2 — SSE 스트리밍 개선 + Langfuse 1-trace 보장.

    v1(`/api/chat`)과 요청/응답 스키마 동일. stream=true 시 개선된 SSE 전송.

    스트리밍 SSE 이벤트 형식:
        event: status
        data: {"message": "답변 생성 중..."}

        event: token
        data: {"content": "토큰텍스트"}

        event: sources
        data: {"sources": [...]}

        event: done
        data: {"stream_id": "abc123", "elapsed_ms": 3200, "usage": {...}}

        event: error
        data: {"message": "에러 내용"}
    """
    logger.info(
        "POST /api/chat_v2: agent_type=%s, stream=%s, query=%s",
        request.agent_type, request.stream, request.query[:100],
    )

    state = build_chat_state(request)

    if request.stream:
        state["metadata"]["_stream_mode"] = True
        return EventSourceResponse(
            _stream_response_v2(state),
            headers={"X-Accel-Buffering": "no"},
            ping=15,
        )

    # Non-streaming — @observe가 전체 구간을 커버
    return await _non_stream_response(request, state)
