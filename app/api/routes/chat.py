"""Chat API — 단일 엔드포인트로 모든 Agent를 호출한다."""
import json
import logging
import time
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.supervisor import supervisor
from app.agents.citation_agent import format_citation_text
from app.core import llm
from app.core.langfuse_client import observe, trace_attributes
from app.models.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_state(request: ChatRequest) -> dict:
    """ChatRequest → supervisor state 변환."""
    state = {
        "query": request.query,
        "user_id": request.user_id,
        "filters": request.filters,
        "metadata": {},
    }
    if request.conversation_history:
        state["metadata"]["conversation_history"] = request.conversation_history
    if request.agent_type:
        state["metadata"]["agent_type"] = request.agent_type
    return state


@router.post("/", response_model=None)
@observe(name="api_chat")
async def chat(request: ChatRequest):
    logger.info("POST /api/chat: agent_type=%s, stream=%s, query=%s",
                request.agent_type, request.stream, request.query[:100])

    state = _build_state(request)

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

    # Non-streaming
    with trace_attributes(user_id=request.user_id, metadata={"agent_type": request.agent_type or "auto"}):
        result = await supervisor.ainvoke(state)

    return ChatResponse(
        answer=result.get("answer", ""),
        sources=result.get("sources"),
        trace_id=result.get("trace_id"),
    )


def _sse_event(event: str, data: dict) -> str:
    """SSE 포맷: event 타입 + JSON data."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_response(state: dict):
    """실시간 스트리밍: 검색/분류 후 LLM 답변을 토큰 단위로 전송한다.

    SSE 이벤트 종류:
      - status   : 파이프라인 진행 상태 (검색 중, 분류 중 등)
      - token    : LLM 토큰 1개
      - sources  : 참조 논문 목록
      - done     : 스트리밍 완료
      - error    : 에러 발생
    """
    stream_id = uuid.uuid4().hex[:12]

    # Phase 1: 검색 + 분류 (LLM 최종 호출은 스킵)
    yield _sse_event("status", {"message": "논문 검색 및 질문 분석 중..."})

    try:
        with trace_attributes(
            user_id=state.get("user_id"),
            metadata={"source": "api_chat_stream"},
        ):
            result = await supervisor.ainvoke(state)
    except Exception as e:
        logger.error("[ChatStream] supervisor error: %s", e)
        yield _sse_event("error", {"message": f"처리 중 오류 발생: {e}"})
        yield _sse_event("done", {"stream_id": stream_id})
        return

    llm_messages = (result.get("metadata") or {}).get("_llm_messages")
    temperature = (result.get("metadata") or {}).get("_llm_temperature", 0.3)
    sources = result.get("sources") or []

    if not llm_messages:
        # LLM messages가 없으면 기존 answer를 한 번에 전송
        answer = result.get("answer", "관련 논문을 찾지 못했습니다.")
        yield _sse_event("token", {"content": answer})
        if sources:
            yield _sse_event("sources", {"sources": [s if isinstance(s, dict) else s.dict() for s in sources]})
        yield _sse_event("done", {"stream_id": stream_id})
        return

    # Phase 2: LLM 실시간 스트리밍
    yield _sse_event("status", {"message": "답변 생성 중..."})

    full_answer = ""
    try:
        async for token in llm.chat_completion_stream(
            messages=llm_messages,
            temperature=temperature,
            trace_name="chat_stream_generate",
            user_id=state.get("user_id"),
        ):
            full_answer += token
            yield _sse_event("token", {"content": token})
    except Exception as e:
        logger.error("[ChatStream] LLM streaming error: %s", e)
        yield _sse_event("error", {"message": f"답변 생성 중 오류: {e}"})

    # Phase 3: 참조 문헌 + 저작권 고지
    citation = format_citation_text(sources)
    if citation:
        yield _sse_event("token", {"content": citation})

    # Phase 4: 소스 목록 전송
    if sources:
        yield _sse_event("sources", {"sources": [s if isinstance(s, dict) else s.dict() for s in sources]})

    yield _sse_event("done", {"stream_id": stream_id})
