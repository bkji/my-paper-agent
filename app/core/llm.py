"""LLM client — OpenAI-compatible API를 통해 LLM과 통신한다."""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from app.config import settings
from app.core.langfuse_client import observe, langfuse_context

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            base_url=settings.LLM_BASE_URL,
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
        )
    return _http_client


@observe(as_type="generation", name="llm_chat_completion")
async def chat_completion(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    trace_name: str = "llm_chat_completion",
    user_id: str | None = None,
) -> str:
    """OpenAI-compatible chat completion을 호출한다."""
    logger.info(
        "chat_completion called: model=%s, messages=%d, temperature=%s",
        settings.LLM_MODEL, len(messages), temperature,
    )

    client = _get_http_client()
    payload = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    response = await client.post("/chat/completions", json=payload)
    response.raise_for_status()
    data = response.json()

    result = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})

    langfuse_context(
        output={"response": result[:500]},
        metadata={
            "model": settings.LLM_MODEL,
            "prompt_tokens": str(usage.get("prompt_tokens", "")),
            "completion_tokens": str(usage.get("completion_tokens", "")),
        },
    )
    logger.info(
        "chat_completion done: prompt_tokens=%s, completion_tokens=%s",
        usage.get("prompt_tokens"), usage.get("completion_tokens"),
    )
    return result


@observe(as_type="generation", name="llm_chat_completion_stream")
async def chat_completion_stream(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    trace_name: str = "llm_chat_completion_stream",
    user_id: str | None = None,
) -> AsyncIterator[str]:
    """LM Studio streaming chat completion."""
    logger.info("chat_completion_stream called: model=%s", settings.LLM_MODEL)

    client = _get_http_client()
    payload = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    full_response = ""
    async with client.stream("POST", "/chat/completions", json=payload) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            chunk = json.loads(data_str)
            delta = chunk["choices"][0].get("delta", {})
            content = delta.get("content", "")
            if content:
                full_response += content
                yield content

    langfuse_context(output={"response": full_response[:500]})
    logger.info("chat_completion_stream done: response_len=%d", len(full_response))
