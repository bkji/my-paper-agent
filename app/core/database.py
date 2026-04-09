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
    """DOI로 논문을 조회한다. 부분 일치도 지원 (e.g. '10.1002/jsid.2003')."""
    logger.info("get_papers_by_doi: doi=%s", doi)
    with SessionLocal() as db:
        # 정확히 일치 먼저 시도
        papers = db.query(Paper).filter(Paper.doi == doi).all()
        # 없으면 부분 일치 (URL prefix 포함된 DOI 대응)
        if not papers:
            papers = db.query(Paper).filter(Paper.doi.contains(doi)).all()
        result = [_paper_to_dict(p) for p in papers]
    langfuse_context(output={"count": len(result)})
    return result


@observe(name="db_get_paper_fulltext_by_doi")
async def get_paper_fulltext_by_doi(doi: str, **kwargs) -> dict[str, Any] | None:
    """DOI(부분 일치)로 논문 원문(전체 텍스트)을 조회한다."""
    from sqlalchemy import text as sql_text

    logger.info("get_paper_fulltext_by_doi: doi=%s", doi)

    sql = f"""
        SELECT mariadb_id, filename, doi, coverdate, title, paper_keyword,
               paper_text, volume, issue, totalpage, referencetotal,
               author, `references`, chunk_id, chunk_total_counts
        FROM {settings.MARIADB_TABLE}
        WHERE (chunk_id = 1 OR chunk_id IS NULL)
          AND doi LIKE :doi_pattern
        ORDER BY coverdate DESC
        LIMIT 1
    """

    with SessionLocal() as db:
        result = db.execute(sql_text(sql), {"doi_pattern": f"%{doi}%"})
        row = result.fetchone()
        if row is None:
            langfuse_context(output={"found": False})
            return None
        paper = {
            "mariadb_id": row[0], "filename": row[1], "doi": row[2],
            "coverdate": row[3], "title": row[4], "paper_keyword": row[5],
            "paper_text": row[6], "volume": row[7], "issue": row[8],
            "totalpage": row[9], "referencetotal": row[10],
            "author": row[11], "references": row[12],
            "chunk_id": row[13], "chunk_total_counts": row[14],
        }

    langfuse_context(output={"found": True, "title": paper["title"][:100]})
    logger.info("get_paper_fulltext_by_doi: found '%s'", paper["title"][:60])
    return paper


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


def _build_keyword_conditions(
    keyword: str,
    params: dict[str, Any],
    extra_keywords: list[str] | None = None,
) -> str:
    """키워드 검색 조건을 생성한다. 복합 키워드('Micro LED')는 변형도 함께 검색.

    Args:
        extra_keywords: 사내 도메인 용어 확장 키워드. OR 조건으로 추가.
    """
    # 기본 LIKE 검색
    conditions = ["(title LIKE :kw OR paper_keyword LIKE :kw OR bm25_keywords LIKE :kw)"]
    params["kw"] = f"%{keyword}%"

    # 복합 키워드: 공백/하이픈 변형도 검색 (e.g. "Micro LED" → "micro-LED", "microLED")
    parts = keyword.split()
    if len(parts) >= 2:
        # 하이픈 연결: "Micro LED" → "Micro-LED"
        hyphenated = "-".join(parts)
        conditions.append("(title LIKE :kw_hyp OR paper_keyword LIKE :kw_hyp OR bm25_keywords LIKE :kw_hyp)")
        params["kw_hyp"] = f"%{hyphenated}%"
        # 붙여쓰기: "Micro LED" → "MicroLED"
        joined = "".join(parts)
        conditions.append("(title LIKE :kw_join OR paper_keyword LIKE :kw_join OR bm25_keywords LIKE :kw_join)")
        params["kw_join"] = f"%{joined}%"

    # 사내 도메인 용어 확장 키워드 추가
    if extra_keywords:
        for i, ek in enumerate(extra_keywords):
            param_name = f"kw_dom_{i}"
            conditions.append(
                f"(title LIKE :{param_name} OR paper_keyword LIKE :{param_name} "
                f"OR bm25_keywords LIKE :{param_name})"
            )
            params[param_name] = f"%{ek}%"

    return "(" + " OR ".join(conditions) + ")"


@observe(name="db_aggregate_papers")
async def aggregate_papers(
    coverdate_from: int | None = None,
    coverdate_to: int | None = None,
    keyword: str | None = None,
    author: str | None = None,
    group_by: str = "month",
    volume: int | None = None,
    issue: int | None = None,
    extra_keywords: list[str] | None = None,
    **kwargs,
) -> list[dict[str, Any]]:
    """논문을 기간/키워드/저자별로 집계한다. MariaDB에서 직접 SQL 수행.

    Args:
        group_by: "month" (YYYYMM), "year" (YYYY), "quarter" (YYYYQ*)
    Returns:
        [{"period": "202401", "count": 5, "titles": ["...", ...]}, ...]
    """
    logger.info("aggregate_papers: from=%s, to=%s, keyword=%s, group_by=%s",
                coverdate_from, coverdate_to, keyword, group_by)

    from sqlalchemy import text as sql_text

    # chunk_id=1인 것만 세야 논문 편수가 됨 (chunk 중복 제거)
    where_parts = ["(chunk_id = 1 OR chunk_id IS NULL)"]
    params: dict[str, Any] = {}

    if coverdate_from:
        where_parts.append("coverdate >= :cd_from")
        params["cd_from"] = int(coverdate_from)
    if coverdate_to:
        where_parts.append("coverdate <= :cd_to")
        params["cd_to"] = int(coverdate_to)
    if keyword:
        where_parts.append(_build_keyword_conditions(keyword, params, extra_keywords))
    elif extra_keywords:
        # keyword 없이 도메인 용어 확장 키워드만 있는 경우
        where_parts.append(_build_keyword_conditions(extra_keywords[0], params, extra_keywords[1:]))
    if author:
        where_parts.append("author LIKE :au")
        params["au"] = f"%{author}%"
    if volume is not None:
        where_parts.append("volume = :vol")
        params["vol"] = int(volume)
    if issue is not None:
        where_parts.append("issue = :iss")
        params["iss"] = int(issue)

    where_clause = " AND ".join(where_parts)

    if group_by == "year":
        group_expr = "FLOOR(coverdate / 10000)"
        period_expr = "CAST(FLOOR(coverdate / 10000) AS CHAR)"
    elif group_by == "quarter":
        group_expr = "CONCAT(FLOOR(coverdate / 10000), 'Q', CEIL(MOD(FLOOR(coverdate / 100), 100) / 3))"
        period_expr = group_expr
    else:  # month
        group_expr = "FLOOR(coverdate / 100)"
        period_expr = "CAST(FLOOR(coverdate / 100) AS CHAR)"

    sql = f"""
        SELECT {period_expr} AS period,
               COUNT(*) AS cnt,
               GROUP_CONCAT(DISTINCT LEFT(title, 80) SEPARATOR ' || ') AS titles
        FROM {settings.MARIADB_TABLE}
        WHERE {where_clause}
        GROUP BY {group_expr}
        ORDER BY {group_expr}
    """

    with SessionLocal() as db:
        result = db.execute(sql_text(sql), params)
        rows = [{"period": str(row[0]), "count": row[1], "titles": (row[2] or "").split(" || ")} for row in result]

    langfuse_context(output={"group_by": group_by, "period_count": len(rows), "total": sum(r["count"] for r in rows)})
    return rows


@observe(name="db_list_papers")
async def list_papers(
    coverdate_from: int | None = None,
    coverdate_to: int | None = None,
    keyword: str | None = None,
    author: str | None = None,
    limit: int = 100,
    volume: int | None = None,
    issue: int | None = None,
    extra_keywords: list[str] | None = None,
    **kwargs,
) -> list[dict[str, Any]]:
    """조건에 맞는 논문 목록을 반환한다 (chunk_id=1만, 중복 없는 논문 단위).

    집계가 아닌 리스트가 필요할 때 사용.
    """
    from sqlalchemy import text as sql_text

    where_parts = ["(chunk_id = 1 OR chunk_id IS NULL)"]
    params: dict[str, Any] = {}

    if coverdate_from:
        where_parts.append("coverdate >= :cd_from")
        params["cd_from"] = int(coverdate_from)
    if coverdate_to:
        where_parts.append("coverdate <= :cd_to")
        params["cd_to"] = int(coverdate_to)
    if keyword:
        where_parts.append(_build_keyword_conditions(keyword, params, extra_keywords))
    elif extra_keywords:
        where_parts.append(_build_keyword_conditions(extra_keywords[0], params, extra_keywords[1:]))
    if author:
        where_parts.append("author LIKE :au")
        params["au"] = f"%{author}%"
    if volume is not None:
        where_parts.append("volume = :vol")
        params["vol"] = int(volume)
    if issue is not None:
        where_parts.append("issue = :iss")
        params["iss"] = int(issue)

    where_clause = " AND ".join(where_parts)
    params["lim"] = limit

    sql = f"""
        SELECT mariadb_id, filename, doi, coverdate, title, paper_keyword, author, volume, issue
        FROM {settings.MARIADB_TABLE}
        WHERE {where_clause}
        ORDER BY coverdate DESC
        LIMIT :lim
    """

    with SessionLocal() as db:
        result = db.execute(sql_text(sql), params)
        rows = []
        for row in result:
            rows.append({
                "mariadb_id": row[0], "filename": row[1], "doi": row[2],
                "coverdate": row[3], "title": row[4], "paper_keyword": row[5],
                "author": row[6], "volume": row[7], "issue": row[8],
            })

    langfuse_context(output={"count": len(rows)})
    return rows


@observe(name="db_get_paper_fulltext_by_title")
async def get_paper_fulltext_by_title(title_query: str, **kwargs) -> dict[str, Any] | None:
    """제목(부분 일치)으로 논문 원문(전체 텍스트)을 조회한다.

    MariaDB sid_v_09_01에서 chunk_id=1인 원본 행을 반환.
    paper_text에 전체 원문이 포함되어 있음.
    """
    from sqlalchemy import text as sql_text

    logger.info("get_paper_fulltext_by_title: title_query=%s", title_query[:80])

    sql = f"""
        SELECT mariadb_id, filename, doi, coverdate, title, paper_keyword,
               paper_text, volume, issue, totalpage, referencetotal,
               author, `references`, chunk_id, chunk_total_counts
        FROM {settings.MARIADB_TABLE}
        WHERE (chunk_id = 1 OR chunk_id IS NULL)
          AND title LIKE :tq
        ORDER BY coverdate DESC
        LIMIT 1
    """

    with SessionLocal() as db:
        result = db.execute(sql_text(sql), {"tq": f"%{title_query}%"})
        row = result.fetchone()
        if row is None:
            langfuse_context(output={"found": False})
            return None
        paper = {
            "mariadb_id": row[0], "filename": row[1], "doi": row[2],
            "coverdate": row[3], "title": row[4], "paper_keyword": row[5],
            "paper_text": row[6], "volume": row[7], "issue": row[8],
            "totalpage": row[9], "referencetotal": row[10],
            "author": row[11], "references": row[12],
            "chunk_id": row[13], "chunk_total_counts": row[14],
        }

    langfuse_context(output={"found": True, "title": paper["title"][:100]})
    logger.info("get_paper_fulltext_by_title: found '%s' (text_len=%d)",
                paper["title"][:60], len(paper.get("paper_text") or ""))
    return paper


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
