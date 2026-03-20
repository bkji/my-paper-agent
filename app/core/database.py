"""MariaDB client — SQLAlchemy를 통해 논문 원본 데이터를 관리한다."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.core.langfuse_client import observe, langfuse_context
from app.models.db_models import Base, Paper

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.MARIADB_URL,
    pool_size=20,
    max_overflow=30,
    pool_recycle=3600,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine)


def init_tables() -> None:
    """모든 테이블을 생성한다."""
    Base.metadata.create_all(bind=engine)
    logger.info("MariaDB tables created")


def get_db() -> Generator[Session, None, None]:
    """DB 세션을 반환한다. FastAPI Depends에서 사용."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@observe(name="db_get_paper")
async def get_paper_by_id(paper_id: str, **kwargs) -> dict[str, Any] | None:
    """논문 ID로 원본 논문 전체 데이터를 조회한다."""
    logger.info("get_paper_by_id: paper_id=%s", paper_id)
    with SessionLocal() as db:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if paper is None:
            langfuse_context(output={"found": False})
            return None
        result = _paper_to_dict(paper)
    langfuse_context(output={"found": True, "title": result.get("title", "")[:100]})
    return result


@observe(name="db_get_paper_by_doi")
async def get_papers_by_doi(doi: str, **kwargs) -> list[dict[str, Any]]:
    """DOI로 논문을 조회한다."""
    logger.info("get_papers_by_doi: doi=%s", doi)
    with SessionLocal() as db:
        papers = db.query(Paper).filter(Paper.doi == doi).all()
        result = [_paper_to_dict(p) for p in papers]
    langfuse_context(output={"count": len(result)})
    return result


@observe(name="db_search_papers")
async def search_papers(
    keyword: str | None = None,
    author: str | None = None,
    coverdate_from: str | None = None,
    coverdate_to: str | None = None,
    limit: int = 20,
    **kwargs,
) -> list[dict[str, Any]]:
    """조건으로 논문을 검색한다."""
    logger.info("search_papers: keyword=%s, author=%s", keyword, author)
    with SessionLocal() as db:
        query = db.query(Paper)
        if keyword:
            query = query.filter(Paper.title.contains(keyword) | Paper.paper_keywords.contains(keyword))
        if author:
            query = query.filter(Paper.author.contains(author))
        if coverdate_from:
            query = query.filter(Paper.coverdate >= coverdate_from)
        if coverdate_to:
            query = query.filter(Paper.coverdate <= coverdate_to)
        papers = query.order_by(Paper.coverdate.desc()).limit(limit).all()
        result = [_paper_to_dict(p) for p in papers]
    langfuse_context(output={"count": len(result)})
    return result


@observe(name="db_save_paper")
async def save_paper(paper: dict[str, Any], **kwargs) -> str:
    """논문 데이터를 MariaDB에 저장한다."""
    paper_id = paper.get("id") or str(uuid.uuid4())
    logger.info("save_paper: paper_id=%s", paper_id)
    with SessionLocal() as db:
        db_paper = Paper(
            id=paper_id,
            filename=paper.get("filename", ""),
            doi=paper.get("doi"),
            coverdate=paper.get("coverdate"),
            title=paper.get("title", ""),
            paper_keywords=paper.get("paper_keywords"),
            paper_text=paper.get("paper_text", ""),
            volume=paper.get("volume"),
            issue=paper.get("issue"),
            totalpage=paper.get("totalpage"),
            referencetotal=paper.get("referencetotal"),
            author=paper.get("author"),
            references=paper.get("references"),
            chunk_total_counts=paper.get("chunk_total_counts"),
            embedding_model_id=paper.get("embedding_model_id"),
        )
        db.merge(db_paper)
        db.commit()
    langfuse_context(output={"paper_id": paper_id})
    return paper_id


def _paper_to_dict(paper: Paper) -> dict[str, Any]:
    return {
        "id": paper.id,
        "filename": paper.filename,
        "doi": paper.doi,
        "coverdate": paper.coverdate,
        "title": paper.title,
        "paper_keywords": paper.paper_keywords,
        "paper_text": paper.paper_text,
        "volume": paper.volume,
        "issue": paper.issue,
        "totalpage": paper.totalpage,
        "referencetotal": paper.referencetotal,
        "author": paper.author,
        "references": paper.references,
        "chunk_total_counts": paper.chunk_total_counts,
        "embedding_model_id": paper.embedding_model_id,
    }
