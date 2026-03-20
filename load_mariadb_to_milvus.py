"""
MariaDB paper.sid_v_09_01 데이터를 Milvus m_paper.m_sid_v_09_01 컬렉션에 적재하는 스크립트
- paper_text → bge-m3 임베딩 (LM Studio API)
- bm25_keywords → BM25 sparse vector (Milvus built-in function)
- embedding_model_id 필드 추가
"""

import os
import sys
import requests
import mariadb
from dotenv import load_dotenv
from pymilvus import (
    connections, db, utility,
    CollectionSchema, FieldSchema, DataType, Collection, Function, FunctionType,
)

load_dotenv()

# MariaDB
DB_CONFIG = {
    "host": os.getenv("MARIADB_HOST", "localhost"),
    "port": int(os.getenv("MARIADB_PORT", "3306")),
    "user": os.getenv("MARIADB_USER"),
    "password": os.getenv("MARIADB_PASSWORD"),
}
MARIA_DATABASE = os.getenv("MARIADB_DATABASE", "paper")
MARIA_TABLE = "sid_v_09_01"

# Milvus
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
MILVUS_DATABASE = os.getenv("MILVUS_DATABASE", "m_paper")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "m_sid_v_09_01")

# Embedding
LMSTUDIO_URL = os.getenv("LMSTUDIO_URL", "http://localhost:20020")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-bge-m3")
EMBEDDING_DIM = 1024


def fetch_from_mariadb():
    conn = mariadb.connect(**DB_CONFIG, database=MARIA_DATABASE)
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM `{MARIA_TABLE}`")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    print(f"MariaDB에서 {len(rows)}건 조회 완료")
    return rows


def get_embeddings(texts, batch_size=8):
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = requests.post(
            f"{LMSTUDIO_URL}/v1/embeddings",
            json={"model": EMBEDDING_MODEL, "input": batch},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        # LM Studio는 index 순서대로 반환하지 않을 수 있으므로 정렬
        data.sort(key=lambda x: x["index"])
        all_embeddings.extend([d["embedding"] for d in data])
        print(f"  임베딩 {i + len(batch)}/{len(texts)} 완료")
    return all_embeddings


def create_milvus_collection():
    # database 생성
    existing_dbs = db.list_database()
    if MILVUS_DATABASE not in existing_dbs:
        db.create_database(MILVUS_DATABASE)
        print(f"Milvus database '{MILVUS_DATABASE}' 생성")
    db.using_database(MILVUS_DATABASE)

    # 기존 collection 삭제
    if utility.has_collection(MILVUS_COLLECTION):
        utility.drop_collection(MILVUS_COLLECTION)
        print(f"기존 collection '{MILVUS_COLLECTION}' 삭제")

    # 스키마 정의
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="mariadb_id", dtype=DataType.INT64),
        FieldSchema(name="filename", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="doi", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="coverdate", dtype=DataType.INT64),
        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="paper_keyword", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="paper_text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="volume", dtype=DataType.INT16),
        FieldSchema(name="issue", dtype=DataType.INT16),
        FieldSchema(name="totalpage", dtype=DataType.INT16),
        FieldSchema(name="referencetotal", dtype=DataType.INT16),
        FieldSchema(name="author", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="references", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="chunk_id", dtype=DataType.INT16),
        FieldSchema(name="chunk_total_counts", dtype=DataType.INT16),
        FieldSchema(name="bm25_keywords", dtype=DataType.VARCHAR, max_length=65535, enable_analyzer=True),
        FieldSchema(name="parser_ver", dtype=DataType.VARCHAR, max_length=20),
        # 신규 필드
        FieldSchema(name="embeddings", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
        FieldSchema(name="bm25_keywords_sparse", dtype=DataType.SPARSE_FLOAT_VECTOR),
        FieldSchema(name="embedding_model_id", dtype=DataType.VARCHAR, max_length=128),
    ]

    # BM25 function
    bm25_function = Function(
        name="bm25_fn",
        input_field_names=["bm25_keywords"],
        output_field_names=["bm25_keywords_sparse"],
        function_type=FunctionType.BM25,
    )

    schema = CollectionSchema(fields=fields, enable_dynamic_field=False)
    schema.add_function(bm25_function)

    collection = Collection(name=MILVUS_COLLECTION, schema=schema)
    print(f"Collection '{MILVUS_COLLECTION}' 생성 완료")
    return collection


def insert_data(collection, rows, embeddings):
    data = []
    for i, row in enumerate(rows):
        entity = {
            "mariadb_id": int(row["mariadb_id"]),
            "filename": str(row["filename"] or ""),
            "doi": str(row["doi"] or ""),
            "coverdate": int(row["coverdate"] or 0),
            "title": str(row["title"] or ""),
            "paper_keyword": str(row["paper_keyword"] or ""),
            "paper_text": str(row["paper_text"] or ""),
            "volume": int(row["volume"] or 0),
            "issue": int(row["issue"] or 0),
            "totalpage": int(row["totalpage"] or 0),
            "referencetotal": int(row["referencetotal"] or 0),
            "author": str(row["author"] or ""),
            "references": str(row["references"] or ""),
            "chunk_id": int(row["chunk_id"] or 0),
            "chunk_total_counts": int(row["chunk_total_counts"] or 0),
            "bm25_keywords": str(row["bm25_keywords"] or ""),
            "parser_ver": str(row["parser_ver"] or ""),
            "embeddings": embeddings[i],
            "embedding_model_id": EMBEDDING_MODEL,
        }
        data.append(entity)

    collection.insert(data)
    collection.flush()
    print(f"{len(rows)}건 INSERT 완료")


def create_indexes(collection):
    # embeddings: IVF_FLAT, IP, nlist=128
    collection.create_index(
        field_name="embeddings",
        index_params={
            "index_type": "IVF_FLAT",
            "metric_type": "IP",
            "params": {"nlist": 128},
        },
    )
    print("embeddings 인덱스 생성 완료 (IVF_FLAT, IP, nlist=128)")

    # bm25_keywords_sparse: SPARSE_INVERTED_INDEX, BM25
    collection.create_index(
        field_name="bm25_keywords_sparse",
        index_params={
            "index_type": "SPARSE_INVERTED_INDEX",
            "metric_type": "BM25",
            "params": {"bm25_k1": 1.2, "bm25_b": 0.75},
        },
    )
    print("bm25_keywords_sparse 인덱스 생성 완료 (SPARSE_INVERTED_INDEX, BM25)")

    # 스칼라 필드 인덱스
    scalar_index_fields = ["coverdate", "paper_keyword", "title", "volume", "issue", "author"]
    for field_name in scalar_index_fields:
        collection.create_index(
            field_name=field_name,
            index_params={"index_type": "INVERTED"},
        )
        print(f"{field_name} 인덱스 생성 완료 (INVERTED)")


def main():
    # 1. MariaDB에서 데이터 조회
    rows = fetch_from_mariadb()

    # 2. 임베딩 생성
    print("임베딩 생성 중...")
    texts = [str(r["paper_text"] or "") for r in rows]
    embeddings = get_embeddings(texts)

    # 3. Milvus 접속
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    print(f"Milvus 접속 완료 ({MILVUS_HOST}:{MILVUS_PORT})")

    # 4. Collection 생성
    collection = create_milvus_collection()

    # 5. 데이터 삽입
    insert_data(collection, rows, embeddings)

    # 6. 인덱스 생성
    create_indexes(collection)

    # 7. 검증
    collection.load()
    count = collection.num_entities
    print(f"검증: collection 내 총 {count}건")

    connections.disconnect("default")


if __name__ == "__main__":
    main()
