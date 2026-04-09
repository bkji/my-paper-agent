"""Embedding client — OpenAI-compatible API를 통해 임베딩 모델과 통신한다."""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.core.langfuse_client import observe, langfuse_context

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None

EMBEDDING_DIM = settings.EMBEDDING_DIM


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            base_url=settings.EMBEDDING_BASE_URL,
            headers={"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"},
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=30.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            proxy=None,
        )
    return _http_client


@observe(as_type="embedding", name="embed_texts")
async def embed_texts(
    texts: list[str],
    trace_name: str = "embed_texts",
    user_id: str | None = None,
) -> list[list[float]]:
    """텍스트 목록을 임베딩 벡터로 변환한다."""
    logger.info("embed_texts called: model=%s, text_count=%d", settings.EMBEDDING_MODEL, len(texts))
    langfuse_context(
        input={"text_count": len(texts), "total_chars": sum(len(t) for t in texts)},
        metadata={"model": settings.EMBEDDING_MODEL},
    )

    client = _get_http_client()
    response = await client.post(
        "/embeddings",
        json={"model": settings.EMBEDDING_MODEL, "input": texts},
    )
    response.raise_for_status()
    data = response.json()["data"]
    data.sort(key=lambda x: x["index"])
    result = [d["embedding"] for d in data]

    langfuse_context(
        output={"vector_count": len(result), "dim": len(result[0]) if result else 0},
        metadata={"model": settings.EMBEDDING_MODEL},
    )
    logger.info("embed_texts done: vector_count=%d", len(result))
    return result


@observe(name="embed_query")
async def embed_query(
    query: str,
    trace_name: str = "embed_query",
    user_id: str | None = None,
) -> list[float]:
    """단일 쿼리를 임베딩 벡터로 변환한다."""
    langfuse_context(input={"query": query[:200]}, metadata={"model": settings.EMBEDDING_MODEL})
    vectors = await embed_texts([query], trace_name=trace_name, user_id=user_id)
    langfuse_context(output={"dim": len(vectors[0]) if vectors else 0})
    return vectors[0]
