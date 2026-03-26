"""API 공통 의존성 — 인증 등 라우터 간 공유되는 Depends를 정의한다."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.models.schemas import ChatRequest

_bearer_scheme = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> None:
    """OPENAI_COMPAT_API_KEY가 설정되어 있으면 Bearer 토큰을 검증한다. 미설정이면 인증 없이 통과."""
    expected = settings.OPENAI_COMPAT_API_KEY
    if not expected:
        return
    if credentials is None or credentials.credentials != expected:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


def build_chat_state(request: ChatRequest) -> dict:
    """ChatRequest → supervisor state 변환 (chat, chat_v2 공용)."""
    state = {
        "query": request.query,
        "user_id": request.user_id,
        "filters": request.filters,
        "metadata": {},
    }
    if request.messages:
        state["metadata"]["messages"] = [m.model_dump() for m in request.messages]
    if request.agent_type:
        state["metadata"]["agent_type"] = request.agent_type
    return state


def extract_usage(result: dict) -> dict:
    """supervisor 결과에서 usage를 추출한다. 항상 유효한 dict를 반환."""
    usage = (result.get("metadata") or {}).get("usage") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }
