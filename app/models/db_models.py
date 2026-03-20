"""SQLAlchemy models — MariaDB 테이블 정의."""
from __future__ import annotations

from sqlalchemy import Column, String, Integer, Text, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Paper(Base):
    """논문 원본 데이터 (전체 텍스트 포함)."""

    __tablename__ = "papers"

    id = Column(String(64), primary_key=True)
    filename = Column(String(512), nullable=False)
    doi = Column(String(256), index=True)
    coverdate = Column(String(32), index=True)
    title = Column(String(1024), nullable=False)
    paper_keywords = Column(Text)
    paper_text = Column(Text, nullable=False)
    volume = Column(String(32))
    issue = Column(String(32))
    totalpage = Column(Integer)
    referencetotal = Column(Integer)
    author = Column(Text)
    references = Column(Text)
    chunk_total_counts = Column(Integer)
    embedding_model_id = Column(String(128))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
