"""Chat API v2 — SSE 스트리밍 개선 + Langfuse 트레이싱 수정.

v1(`/api/chat`) 대비 개선:
  1. sse-starlette 기반 개별 토큰 즉시 전송 (버퍼링/뭉침 해소)
  2. Langfuse trace가 스트리밍 전체 구간을 커버 (trace 소실 방지)
  3. 스트리밍 종료 시 Langfuse flush 보장
  4. done 이벤트에 elapsed_ms 포함 (서버 처리시간 확인용)
"""
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.agents.supervisor import supervisor
from app.agents.citation_agent import format_citation_text
from app.api.deps import verify_api_key
from app.core import llm
from app.core.langfuse_client import observe, trace_attributes, flush_langfuse
from app.models.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 헬퍼 ─────────────────────────────────────────────────────────


def _build_state(request: ChatRequest) -> dict:
    """ChatRequest → supervisor state 변환."""
    state = {
        "query": request.query,
        "user_id": request.user_id,
        "filters": request.filters,
        "metadata": {},
    }
    if request.messages:
        state["metadata"]["messages"] = [m.model_dump() for m in request.messages]
    if request.agent_type:
        state["metadata"]["agent_type"] = request.agent_type
    return state


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
    return ChatResponse(
        answer=result.get("answer", ""),
        sources=result.get("sources"),
        trace_id=result.get("trace_id"),
    )


# ── Streaming ────────────────────────────────────────────────────


async def _stream_response_v2(state: dict):
    """실시간 SSE 스트리밍 — Langfuse trace가 전체 구간을 커버한다.

    v1과의 차이:
      - @observe를 endpoint에 걸지 않고, trace_attributes를 generator 전체에 감쌈
        → generator가 살아 있는 동안 trace context 유지 → trace 소실 방지
      - ServerSentEvent 객체를 yield → sse-starlette가 개별 이벤트를 즉시 flush
      - finally에서 flush_langfuse() → 비정상 종료(클라이언트 disconnect) 시에도 trace 저장

    이벤트 종류:
      - status  : 파이프라인 진행 상태
      - token   : LLM 토큰 1개
      - sources : 참조 논문 목록
      - done    : 스트리밍 완료 (stream_id, elapsed_ms 포함)
      - error   : 에러 발생
    """
    stream_id = uuid.uuid4().hex[:12]
    t_start = time.time()

    try:
        # trace_attributes가 generator 전체 구간을 감싼다.
        # 내부에서 호출되는 @observe 함수들(supervisor, llm)이 이 trace에 연결된다.
        with trace_attributes(
            user_id=state.get("user_id"),
            metadata={"source": "api_chat_v2_stream", "stream_id": stream_id},
        ):
            # ── Phase 1: 검색 + 분류 (LLM 최종 호출은 _stream_mode로 스킵) ──
            yield _sse("status", {"message": "논문 검색 및 질문 분석 중..."})

            try:
                result = await supervisor.ainvoke(state)
            except Exception as e:
                logger.error("[ChatStreamV2] supervisor error: %s", e)
                yield _sse("error", {"message": f"처리 중 오류 발생: {e}"})
                yield _sse("done", {
                    "stream_id": stream_id,
                    "elapsed_ms": _elapsed_ms(t_start),
                })
                return

            llm_messages = (result.get("metadata") or {}).get("_llm_messages")
            temperature = (result.get("metadata") or {}).get("_llm_temperature", 0.3)
            sources = result.get("sources") or []

            # LLM messages가 없으면 (analytics 등) 기존 answer를 한 번에 전송
            if not llm_messages:
                answer = result.get("answer", "관련 논문을 찾지 못했습니다.")
                yield _sse("token", {"content": answer})
                if sources:
                    yield _sse("sources", {
                        "sources": [
                            s if isinstance(s, dict) else s.dict()
                            for s in sources
                        ],
                    })
                yield _sse("done", {
                    "stream_id": stream_id,
                    "elapsed_ms": _elapsed_ms(t_start),
                })
                return

            # ── Phase 2: LLM 실시간 스트리밍 ──
            yield _sse("status", {"message": "답변 생성 중..."})

            full_answer = ""
            try:
                async for token in llm.chat_completion_stream(
                    messages=llm_messages,
                    temperature=temperature,
                    trace_name="chat_v2_stream_generate",
                    user_id=state.get("user_id"),
                ):
                    full_answer += token
                    yield _sse("token", {"content": token})
            except Exception as e:
                logger.error("[ChatStreamV2] LLM streaming error: %s", e)
                yield _sse("error", {"message": f"답변 생성 중 오류: {e}"})

            # ── Phase 3: 참조 문헌 + 저작권 고지 ──
            citation = format_citation_text(sources)
            if citation:
                yield _sse("token", {"content": citation})

            # ── Phase 4: 소스 목록 + 완료 ──
            if sources:
                yield _sse("sources", {
                    "sources": [
                        s if isinstance(s, dict) else s.dict()
                        for s in sources
                    ],
                })

            yield _sse("done", {
                "stream_id": stream_id,
                "elapsed_ms": _elapsed_ms(t_start),
            })

    finally:
        # 스트리밍 종료(정상/비정상 모두) 시 Langfuse 버퍼 즉시 플러시
        # → trace가 Langfuse 서버에 확실히 전송됨
        flush_langfuse()
        logger.info(
            "[ChatStreamV2] stream_id=%s completed (%.1fs)",
            stream_id, time.time() - t_start,
        )


# ── 엔드포인트 ───────────────────────────────────────────────────


@router.post("/", response_model=None, dependencies=[Depends(verify_api_key)])
async def chat_v2(request: ChatRequest):
    """채팅 API v2 — SSE 스트리밍 개선 + Langfuse 트레이싱 수정.

    v1(`/api/chat`)과 요청/응답 스키마 동일. stream=true 시 개선된 SSE 전송.

    스트리밍 SSE 이벤트 형식:
        event: token
        data: {"content": "토큰텍스트"}

        event: status
        data: {"message": "답변 생성 중..."}

        event: sources
        data: {"sources": [...]}

        event: done
        data: {"stream_id": "abc123", "elapsed_ms": 3200}

        event: error
        data: {"message": "에러 내용"}
    """
    logger.info(
        "POST /api/chat_v2: agent_type=%s, stream=%s, query=%s",
        request.agent_type, request.stream, request.query[:100],
    )

    state = _build_state(request)

    if request.stream:
        state["metadata"]["_stream_mode"] = True
        # sse-starlette의 EventSourceResponse:
        #   - 개별 이벤트를 즉시 flush (토큰 뭉침 방지)
        #   - keepalive ping으로 연결 유지
        #   - 클라이언트 disconnect 시 generator 정리
        return EventSourceResponse(
            _stream_response_v2(state),
            headers={"X-Accel-Buffering": "no"},
            ping=15,  # 15초마다 keepalive ping (연결 유지)
        )

    # Non-streaming — @observe가 전체 구간을 커버
    return await _non_stream_response(request, state)
