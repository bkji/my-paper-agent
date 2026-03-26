"""Langfuse v3 tracing — @observe 데코레이터 기반.

사용법:
    from app.core.langfuse_client import observe, langfuse_context

    @observe(as_type="generation", name="llm_call")
    async def my_llm_call(messages):
        ...
        langfuse_context(output={"tokens": 100})
        return result

진입점(CLI, API)에서 trace_attributes로 user_id/metadata를 전파:
    with trace_attributes(user_id="kim", metadata={"ip": "..."}):
        await my_llm_call(messages)
"""
from __future__ import annotations

import atexit
import logging
import socket
from contextlib import nullcontext
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_initialized = False
_host_info: Optional[dict] = None


def get_host_info() -> dict:
    """현재 PC의 hostname과 IP를 반환한다 (캐싱)."""
    global _host_info
    if _host_info is not None:
        return _host_info
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
    except Exception:
        hostname = "unknown"
        ip = "0.0.0.0"
    _host_info = {"hostname": hostname, "ip": ip}
    return _host_info


def get_default_user_id() -> str:
    """user_id가 없을 때 PC이름을 기본값으로 반환한다."""
    return get_host_info()["hostname"]


def init_langfuse() -> bool:
    """Langfuse client를 초기화한다. 앱 시작 시 1회 호출."""
    global _initialized
    if _initialized:
        return True

    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        logger.warning("Langfuse keys not configured — tracing disabled")
        return False

    try:
        from langfuse import Langfuse

        Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
        _initialized = True
        atexit.register(flush_langfuse)
        logger.info("Langfuse v3 initialized (host=%s)", settings.LANGFUSE_HOST)
        return True
    except Exception as e:
        logger.warning("Langfuse initialization failed: %s", e)
        return False


def flush_langfuse():
    """Langfuse 버퍼를 플러시한다."""
    try:
        from langfuse import get_client
        client = get_client()
        client.flush()
        logger.debug("Langfuse flushed")
    except Exception as e:
        logger.warning("Langfuse flush failed: %s", e)


# @observe 데코레이터 & context 헬퍼 — langfuse 미설치 시 no-op fallback
try:
    from langfuse import observe as observe  # noqa: F401
    from langfuse import propagate_attributes as _propagate_attributes
    from langfuse import get_client as _get_client
except Exception:
    logger.warning("langfuse import failed — tracing decorators disabled (no-op)")

    def observe(func=None, **kwargs):  # type: ignore[misc]
        if func is not None:
            return func
        return lambda f: f

    def _propagate_attributes(**kwargs):  # type: ignore[misc]
        return nullcontext()

    def _get_client(**kwargs):  # type: ignore[misc]
        return None


def trace_attributes(
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """trace-level 속성을 하위 @observe 호출에 전파하는 context manager."""
    effective_user_id = user_id or get_default_user_id()
    host_info = get_host_info()
    merged_metadata = {
        "hostname": host_info["hostname"],
        "ip": host_info["ip"],
        **(metadata or {}),
    }
    return _propagate_attributes(
        user_id=effective_user_id,
        metadata=merged_metadata,
    )


def langfuse_context(**kwargs):
    """현재 @observe span에 추가 정보를 기록한다.

    generation 전용 파라미터(usage, usage_details, model, model_parameters,
    cost_details, completion_start_time, prompt)가 포함되어 있으면
    update_current_generation()을 호출하고, 그렇지 않으면
    update_current_span()을 호출한다.

    편의를 위해 'usage' 키는 자동으로 'usage_details'로 변환된다.
    """
    try:
        client = _get_client()
        if not client:
            return

        # 'usage' → 'usage_details' 자동 변환 (Langfuse v4+)
        if "usage" in kwargs and "usage_details" not in kwargs:
            kwargs["usage_details"] = kwargs.pop("usage")

        _generation_keys = {
            "usage_details", "cost_details", "model",
            "model_parameters", "completion_start_time", "prompt",
        }
        if _generation_keys & kwargs.keys():
            client.update_current_generation(**kwargs)
        else:
            client.update_current_span(**kwargs)
    except Exception:
        pass


def add_trace_tags(tags: list[str]):
    """현재 trace에 tags를 추가한다 (Langfuse UI 필터링/분석용)."""
    try:
        client = _get_client()
        if client:
            trace_id = client.get_current_trace_id()
            if trace_id:
                client._create_trace_tags_via_ingestion(trace_id=trace_id, tags=tags)
    except Exception as e:
        logger.debug("add_trace_tags failed: %s", e)


def set_trace_io(input: Any = None, output: Any = None):
    """현재 trace의 input/output을 설정한다 (최상위 trace에 표시됨)."""
    try:
        client = _get_client()
        if client:
            kwargs = {}
            if input is not None:
                kwargs["input"] = input
            if output is not None:
                kwargs["output"] = output
            if kwargs:
                client.set_current_trace_io(**kwargs)
    except Exception as e:
        logger.debug("set_trace_io failed: %s", e)
