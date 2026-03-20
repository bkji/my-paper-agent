"""Milvus client — m_sid_v_09_01 컬렉션에 대한 검색을 수행한다."""
from __future__ import annotations

import logging
from typing import Any

from pymilvus import (
    MilvusClient,
    AnnSearchRequest,
    RRFRanker,
    DataType,
    CollectionSchema,
    FieldSchema,
    Function,
    FunctionType,
)

from app.config import settings
from app.core.langfuse_client import observe, langfuse_context

logger = logging.getLogger(__name__)

_client: MilvusClient | None = None

OUTPUT_FIELDS = [
    "id", "mariadb_id", "filename", "doi", "coverdate", "title", "paper_keyword",
    "paper_text", "volume", "issue", "totalpage", "referencetotal",
    "author", "chunk_id", "chunk_total_counts", "bm25_keywords",
    "embedding_model_id",
]


def get_milvus_client() -> MilvusClient:
    """Milvus 싱글턴 클라이언트를 반환한다."""
    global _client
    if _client is None:
        _client = MilvusClient(
            uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}",
            db_name=settings.MILVUS_DATABASE,
        )
        logger.info(
            "Milvus client created: %s:%s, db=%s",
            settings.MILVUS_HOST, settings.MILVUS_PORT, settings.MILVUS_DATABASE,
        )
    return _client


@observe(as_type="retriever", name="milvus_hybrid_search")
async def hybrid_search(
    query_vector: list[float],
    query_text: str | None = None,
    filters: str | None = None,
    top_k: int | None = None,
    trace_name: str = "milvus_hybrid_search",
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    """Dense + Sparse(BM25) hybrid search를 RRF로 결합하여 수행한다."""
    k = top_k or settings.TOP_K
    client = get_milvus_client()

    dense_req = AnnSearchRequest(
        data=[query_vector],
        anns_field="embeddings",
        param={"metric_type": "IP", "params": {"nprobe": 16}},
        limit=k,
        expr=filters,
    )

    search_requests = [dense_req]

    if query_text:
        sparse_req = AnnSearchRequest(
            data=[query_text],
            anns_field="bm25_keywords_sparse",
            param={"metric_type": "BM25"},
            limit=k,
            expr=filters,
        )
        search_requests.append(sparse_req)

    results = client.hybrid_search(
        collection_name=settings.MILVUS_COLLECTION,
        reqs=search_requests,
        ranker=RRFRanker(k=60),
        limit=k,
        output_fields=OUTPUT_FIELDS,
    )

    hits = []
    for hit in results[0]:
        doc = hit.get("entity", hit)
        doc["score"] = hit.get("distance", 0.0)
        hits.append(doc)

    logger.info("hybrid_search done: top_k=%d, results=%d, filters=%s", k, len(hits), filters)
    langfuse_context(output={"result_count": len(hits), "top_k": k, "filters": filters})
    return hits


@observe(as_type="retriever", name="milvus_vector_search")
async def vector_search(
    query_vector: list[float],
    filters: str | None = None,
    top_k: int | None = None,
    **kwargs,
) -> list[dict[str, Any]]:
    """Dense vector search만 수행한다."""
    k = top_k or settings.TOP_K
    client = get_milvus_client()
    results = client.search(
        collection_name=settings.MILVUS_COLLECTION,
        data=[query_vector],
        anns_field="embeddings",
        search_params={"metric_type": "IP", "params": {"nprobe": 16}},
        limit=k,
        filter=filters,
        output_fields=OUTPUT_FIELDS,
    )

    hits = []
    for hit in results[0]:
        doc = hit.get("entity", hit)
        doc["score"] = hit.get("distance", 0.0)
        hits.append(doc)

    logger.info("vector_search done: top_k=%d, results=%d", k, len(hits))
    langfuse_context(output={"result_count": len(hits)})
    return hits


@observe(as_type="retriever", name="milvus_bm25_search")
async def bm25_search(
    query_text: str,
    filters: str | None = None,
    top_k: int | None = None,
    **kwargs,
) -> list[dict[str, Any]]:
    """BM25 sparse search만 수행한다."""
    k = top_k or settings.TOP_K
    client = get_milvus_client()
    results = client.search(
        collection_name=settings.MILVUS_COLLECTION,
        data=[query_text],
        anns_field="bm25_keywords_sparse",
        search_params={"metric_type": "BM25"},
        limit=k,
        filter=filters,
        output_fields=OUTPUT_FIELDS,
    )

    hits = []
    for hit in results[0]:
        doc = hit.get("entity", hit)
        doc["score"] = hit.get("distance", 0.0)
        hits.append(doc)

    logger.info("bm25_search done: top_k=%d, results=%d", k, len(hits))
    langfuse_context(output={"result_count": len(hits)})
    return hits
