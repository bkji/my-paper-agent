"""공통 Agent state 정의."""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """모든 Agent가 공유하는 state 구조."""
    query: str
    user_id: str | None
    filters: dict | None
    messages: list[dict[str, str]]
    search_results: list[dict[str, Any]]
    context: str
    answer: str
    sources: list[dict[str, Any]]
    trace_id: str | None
    metadata: dict[str, Any]
