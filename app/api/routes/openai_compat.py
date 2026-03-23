"""OpenAI-compatible API wrapper — Open WebUI 등 외부 UI 연동용.

엔드포인트:
    GET  /v1/models              → 모델 목록
    POST /v1/chat/completions    → 채팅 (non-streaming / streaming)
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
from app.config import settings
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


@router.post("/chat/completions", dependencies=[Depends(_verify_api_key)])
async def chat_completions(request: OAIRequest):
    query = ""
    system_ctx = ""
    for msg in request.messages:
        if msg.role == "system":
            system_ctx = msg.content
    for msg in reversed(request.messages):
        if msg.role == "user":
            query = msg.content
            break

    if system_ctx:
        query = f"[System context: {system_ctx}]\n\n{query}"

    if not query:
        return _make_response("질문을 입력해 주세요.", request.model)

    state = {
        "query": query,
        "user_id": "openwebui",
        "filters": {},
        "metadata": {},
    }

    with trace_attributes(user_id="openwebui", metadata={"source": "openai_compat"}):
        result = await supervisor.ainvoke(state)

    answer = result.get("answer", "")

    sources = result.get("sources")
    if sources:
        answer += "\n\n---\n**참고 문헌:**\n"
        for i, src in enumerate(sources[:5], 1):
            title = getattr(src, "title", None) or src.get("title", "")
            doi = getattr(src, "doi", None) or src.get("doi", "")
            ref = f"  DOI: {doi}" if doi else ""
            answer += f"{i}. {title}{ref}\n"

    if request.stream:
        return StreamingResponse(
            _stream_response(answer, request.model),
            media_type="text/event-stream",
        )

    return _make_response(answer, request.model)


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


async def _stream_response(content: str, model: str):
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    sentences = content.split("\n")

    for sentence in sentences:
        chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {"content": sentence + "\n"}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    done_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
