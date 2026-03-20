"""Document ingestion — 논문을 MariaDB에 저장하고, chunk하여 Milvus에 적재한다."""
from __future__ import annotations

import logging
import uuid

from app.config import settings
from app.core.langfuse_client import observe, langfuse_context
from app.core import database, embeddings
from app.services.chunker import chunk_text

logger = logging.getLogger(__name__)


def _to_int_date(value) -> int:
    if isinstance(value, int):
        return value
    if not value:
        return 0
    try:
        return int(str(value).replace("-", "").replace("/", "")[:8])
    except (ValueError, TypeError):
        return 0


def _to_int(value, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


@observe(name="ingest_paper")
async def ingest_paper(paper: dict, user_id: str | None = None) -> dict:
    """논문 1건을 수집한다: MariaDB 저장 → chunk → embed → Milvus 적재."""
    from app.core import vectorstore

    paper_id = paper.get("id") or str(uuid.uuid4())
    chunks = chunk_text(paper["paper_text"])
    chunk_total_counts = len(chunks)

    paper["id"] = paper_id
    paper["chunk_total_counts"] = chunk_total_counts
    await database.save_paper(paper, user_id=user_id)

    embed_vectors = await embeddings.embed_texts(chunks, user_id=user_id)

    chunk_docs = []
    for idx, (chunk_piece, embedding) in enumerate(zip(chunks, embed_vectors)):
        chunk_docs.append({
            "mariadb_id": _to_int(paper.get("mariadb_id"), 0),
            "filename": paper.get("filename", ""),
            "doi": paper.get("doi", ""),
            "coverdate": _to_int_date(paper.get("coverdate")),
            "title": paper.get("title", ""),
            "paper_keyword": paper.get("paper_keywords", ""),
            "paper_text": chunk_piece,
            "volume": _to_int(paper.get("volume"), 0),
            "issue": _to_int(paper.get("issue"), 0),
            "totalpage": _to_int(paper.get("totalpage"), 0),
            "referencetotal": _to_int(paper.get("referencetotal"), 0),
            "author": paper.get("author", ""),
            "references": paper.get("references", ""),
            "chunk_id": idx,
            "chunk_total_counts": chunk_total_counts,
            "bm25_keywords": paper.get("paper_keywords", ""),
            "embedding_model_id": settings.EMBEDDING_MODEL,
            "embeddings": embedding,
        })

    client = vectorstore.get_milvus_client()
    client.insert(collection_name=settings.MILVUS_COLLECTION, data=chunk_docs)
    logger.info("ingest_paper: inserted %d chunks into Milvus", len(chunk_docs))

    result = {"paper_id": paper_id, "chunk_total_counts": chunk_total_counts, "status": "success"}
    langfuse_context(output=result)
    return result
