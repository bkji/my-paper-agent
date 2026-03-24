"""API 공통 의존성 — 인증 등 라우터 간 공유되는 Depends를 정의한다."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

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
