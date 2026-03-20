"""Chat API — 단일 엔드포인트로 모든 Agent를 호출한다."""
import logging
from fastapi import APIRouter
from app.agents.supervisor import supervisor
from app.core.langfuse_client import observe, trace_attributes
from app.models.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=ChatResponse)
@observe(name="api_chat")
async def chat(request: ChatRequest) -> ChatResponse:
    logger.info("POST /api/chat: agent_type=%s, query=%s", request.agent_type, request.query[:100])

    state = {
        "query": request.query,
        "user_id": request.user_id,
        "filters": request.filters,
        "metadata": {},
    }
    if request.agent_type:
        state["metadata"]["agent_type"] = request.agent_type

    with trace_attributes(user_id=request.user_id, metadata={"agent_type": request.agent_type or "auto"}):
        result = await supervisor.ainvoke(state)

    return ChatResponse(
        answer=result.get("answer", ""),
        sources=result.get("sources"),
        trace_id=result.get("trace_id"),
    )
