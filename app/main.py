"""Co-Scientist Agent — FastAPI 메인 애플리케이션."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, chat_v2, documents, agents, openai_compat
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.langfuse_client import init_langfuse, flush_langfuse, shutdown_langfuse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Co-Scientist Agent",
    version="0.2.0",
    description="Display R&D Co-Scientist Agent with date-aware search",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LangfuseFlushMiddleware(BaseHTTPMiddleware):
    """모든 요청 완료 후 Langfuse 버퍼를 플러시하여 trace 유실을 방지한다.

    스트리밍 응답은 각 route의 finally에서 이미 flush하므로,
    이 미들웨어는 비스트리밍 요청의 안전망 역할을 한다.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # 스트리밍 응답이 아닌 경우에만 flush (스트리밍은 route에서 직접 처리)
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" not in content_type:
            flush_langfuse()
        return response


app.add_middleware(LangfuseFlushMiddleware)


@app.get("/")
async def root():
    return {
        "service": "Co-Scientist Agent",
        "version": "0.2.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "chat": "/api/chat",
            "chat_v2": "/api/chat_v2",
            "agents": "/api/agents",
            "documents": "/api/documents",
            "openai_compat": "/v1/chat/completions",
        },
    }


app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(chat_v2.router, prefix="/api/chat_v2", tags=["chat-v2"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(openai_compat.router, prefix="/v1", tags=["openai-compat"])


@app.on_event("startup")
async def startup():
    logger.info("Co-Scientist Agent starting up")
    enabled = init_langfuse()
    logger.info("Langfuse tracing enabled: %s", enabled)


@app.on_event("shutdown")
async def shutdown():
    shutdown_langfuse()
    logger.info("Co-Scientist Agent shut down")
