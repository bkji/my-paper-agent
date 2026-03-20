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


def ensure_database() -> None:
    """Milvus database가 없으면 생성한다."""
    from pymilvus import connections, db

    conn_alias = "default"
    connections.connect(
        alias=conn_alias,
        host=settings.MILVUS_HOST,
        port=settings.MILVUS_PORT,
    )
    existing = db.list_database(using=conn_alias)
    if settings.MILVUS_DATABASE not in existing:
        db.create_database(settings.MILVUS_DATABASE, using=conn_alias)
        logger.info("Milvus database '%s' created", settings.MILVUS_DATABASE)
    connections.disconnect(conn_alias)


def create_collection_if_not_exists() -> None:
    """컬렉션이 없으면 생성한다. database도 함께 보장."""
    from app.core.embeddings import EMBEDDING_DIM

    ensure_database()
    client = get_milvus_client()
    collection_name = settings.MILVUS_COLLECTION

    if client.has_collection(collection_name):
        logger.info("Collection '%s' already exists", collection_name)
        return

    schema = CollectionSchema(description="Paper chunks with dense and sparse vectors")

    schema.add_field(FieldSchema("id", DataType.INT64, is_primary=True, auto_id=True))
    schema.add_field(FieldSchema("mariadb_id", DataType.INT64))
    schema.add_field(FieldSchema("filename", DataType.VARCHAR, max_length=512))
    schema.add_field(FieldSchema("doi", DataType.VARCHAR, max_length=256))
    schema.add_field(FieldSchema("coverdate", DataType.INT64))
    schema.add_field(FieldSchema("title", DataType.VARCHAR, max_length=65535))
    schema.add_field(FieldSchema("paper_keyword", DataType.VARCHAR, max_length=65535))
    schema.add_field(FieldSchema("paper_text", DataType.VARCHAR, max_length=65535))
    schema.add_field(FieldSchema("volume", DataType.INT16))
    schema.add_field(FieldSchema("issue", DataType.INT16))
    schema.add_field(FieldSchema("totalpage", DataType.INT16))
    schema.add_field(FieldSchema("referencetotal", DataType.INT16))
    schema.add_field(FieldSchema("author", DataType.VARCHAR, max_length=65535))
    schema.add_field(FieldSchema("references", DataType.VARCHAR, max_length=65535))
    schema.add_field(FieldSchema("chunk_id", DataType.INT16))
    schema.add_field(FieldSchema("chunk_total_counts", DataType.INT16))
    schema.add_field(FieldSchema("bm25_keywords", DataType.VARCHAR, max_length=65535, enable_analyzer=True))
    schema.add_field(FieldSchema("parser_ver", DataType.VARCHAR, max_length=20))
    schema.add_field(FieldSchema("embeddings", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM))
    schema.add_field(FieldSchema("bm25_keywords_sparse", DataType.SPARSE_FLOAT_VECTOR))
    schema.add_field(FieldSchema("embedding_model_id", DataType.VARCHAR, max_length=128))

    bm25_fn = Function(
        name="bm25_fn",
        function_type=FunctionType.BM25,
        input_field_names=["bm25_keywords"],
        output_field_names=["bm25_keywords_sparse"],
    )
    schema.add_function(bm25_fn)

    client.create_collection(collection_name=collection_name, schema=schema)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embeddings",
        index_type="IVF_FLAT",
        metric_type="IP",
        params={"nlist": 128},
    )
    index_params.add_index(
        field_name="bm25_keywords_sparse",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="BM25",
        params={"bm25_k1": 1.2, "bm25_b": 0.75},
    )
    client.create_index(collection_name=collection_name, index_params=index_params)
    client.load_collection(collection_name)

    logger.info("Collection '%s' created and loaded", collection_name)


@observe(as_type="span", name="milvus_insert")
async def insert_chunks(
    chunks: list[dict[str, Any]],
    **kwargs,
) -> dict[str, Any]:
    """청크 데이터를 Milvus에 삽입한다."""
    client = get_milvus_client()
    result = client.insert(collection_name=settings.MILVUS_COLLECTION, data=chunks)
    inserted = result.get("insert_count", len(chunks))
    logger.info("insert_chunks done: inserted=%s", inserted)
    langfuse_context(output={"inserted": inserted})
    return result


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
