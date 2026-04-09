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

import httpx

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
            httpx_client=httpx.Client(proxy=None),
        )
        _initialized = True
        atexit.register(shutdown_langfuse)
        logger.info("Langfuse v3 initialized (host=%s)", settings.LANGFUSE_HOST)
        return True
    except Exception as e:
        logger.warning("Langfuse initialization failed: %s", e)
        return False


def flush_langfuse():
    """Langfuse 버퍼를 플러시한다.

    중요: @observe 데코레이터로 감싼 함수의 **바깥에서** 호출해야 한다.
    @observe 함수 안에서 flush하면 span이 아직 열려있는 상태에서
    불완전한 데이터가 전송되어 trace가 유실될 수 있다. (GitHub #2495)

    올바른 사용:
        result = await my_observe_decorated_function()
        flush_langfuse()  # @observe가 span을 닫은 뒤

    잘못된 사용:
        @observe(name="my_func")
        async def my_func():
            ...
            flush_langfuse()  # ← span이 아직 열려있음 → trace 유실!
            return result
    """
    try:
        from langfuse import get_client
        client = get_client()
        if client:
            client.flush()
            logger.debug("Langfuse flushed successfully")
        else:
            logger.debug("Langfuse flush skipped — no client")
    except Exception as e:
        logger.warning("Langfuse flush failed: %s", e)


def shutdown_langfuse():
    """Langfuse client를 종료한다 (앱 종료 시 호출).

    shutdown()은 내부적으로 flush() 후 worker thread까지 정리한다.
    """
    try:
        from langfuse import get_client
        client = get_client()
        if client:
            client.shutdown()
            logger.info("Langfuse shutdown completed")
    except Exception as e:
        logger.warning("Langfuse shutdown failed: %s", e)


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
    trace_name: Optional[str] = None,
):
    """trace-level 속성을 하위 @observe 호출에 전파하는 context manager.

    주의: @observe 데코레이터 **바깥에서** 호출해야 trace 속성이 올바르게 적용된다.
    @observe 안에서 호출하면 Unnamed trace가 생성될 수 있다.

    올바른 사용:
        with trace_attributes(user_id="kim", trace_name="my_trace"):
            await my_observe_decorated_function()
    """
    effective_user_id = user_id or get_default_user_id()
    host_info = get_host_info()
    merged_metadata = {
        "hostname": host_info["hostname"],
        "ip": host_info["ip"],
        **(metadata or {}),
    }
    kwargs = dict(
        user_id=effective_user_id,
        metadata=merged_metadata,
    )
    if trace_name:
        kwargs["trace_name"] = trace_name
    return _propagate_attributes(**kwargs)


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
    """현재 trace + 현재 span의 input/output을 설정한다.

    Langfuse SDK v4 (OTel 기반)에서는 trace-level IO만으로는 UI에 표시되지 않을 수 있다.
    현재 @observe span의 input/output도 함께 설정하여 확실히 표시되도록 한다.
    """
    try:
        client = _get_client()
        if not client:
            return

        kwargs = {}
        if input is not None:
            kwargs["input"] = input
        if output is not None:
            kwargs["output"] = output
        if not kwargs:
            return

        # 1) trace-level IO 설정
        try:
            client.set_current_trace_io(**kwargs)
        except Exception:
            pass

        # 2) 현재 span IO도 설정 (OTel 기반 SDK에서 UI 표시 보장)
        try:
            client.update_current_span(**kwargs)
        except Exception:
            pass
    except Exception as e:
        logger.debug("set_trace_io failed: %s", e)
