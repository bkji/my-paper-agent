"""Co-Scientist Agent — FastAPI 메인 애플리케이션."""
from __future__ import annotations

import logging

from fastapi import FastAPI

from app.api.routes import chat, documents, agents
from app.core.langfuse_client import init_langfuse, flush_langfuse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Co-Scientist Agent",
    version="0.2.0",
    description="Display R&D Co-Scientist Agent with date-aware search",
)


@app.get("/")
async def root():
    return {
        "service": "Co-Scientist Agent",
        "version": "0.2.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "chat": "/api/chat",
            "agents": "/api/agents",
            "documents": "/api/documents",
        },
    }


app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])


@app.on_event("startup")
async def startup():
    logger.info("Co-Scientist Agent starting up")
    enabled = init_langfuse()
    logger.info("Langfuse tracing enabled: %s", enabled)


@app.on_event("shutdown")
async def shutdown():
    flush_langfuse()
    logger.info("Co-Scientist Agent shut down")
