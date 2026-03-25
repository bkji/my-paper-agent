"""Pydantic schemas — API 요청/응답 모델."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str       # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    query: str
    agent_type: Optional[str] = None
    user_id: Optional[str] = None
    filters: Optional[dict] = None
    messages: Optional[list[ChatMessage]] = None
    stream: Optional[bool] = False


class SourceDocument(BaseModel):
    paper_id: str
    title: str
    author: Optional[str] = None
    doi: Optional[str] = None
    chunk_id: int
    chunk_text: str
    score: float
    score_rrf: Optional[float] = None
    score_dense: Optional[float] = None
    score_sparse: Optional[float] = None


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    answer: str
    sources: Optional[list[SourceDocument]] = None
    trace_id: Optional[str] = None
    usage: Optional[UsageInfo] = None


class IngestRequest(BaseModel):
    filename: str
    doi: Optional[str] = None
    coverdate: Optional[str] = None
    title: str
    paper_keywords: Optional[str] = None
    paper_text: str
    volume: Optional[str] = None
    issue: Optional[str] = None
    totalpage: Optional[int] = None
    referencetotal: Optional[int] = None
    author: Optional[str] = None
    references: Optional[str] = None
    embedding_model_id: str = "bge-m3"


class IngestResponse(BaseModel):
    paper_id: str
    chunk_total_counts: int
    status: str
