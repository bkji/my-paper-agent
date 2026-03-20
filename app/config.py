"""설정 — .env에서 환경변수를 로드한다.

폐쇄망 서버 이전 시 .env 파일만 변경하면 된다.
LLM/Embedding 모두 OpenAI-compatible API 형태로 통일.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- LLM (OpenAI-compatible: LM Studio / vLLM) ---
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:20020/v1")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "lm-studio")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen3-0.6b")

    # --- Embedding (OpenAI-compatible: LM Studio / TEI) ---
    EMBEDDING_BASE_URL: str = os.getenv("EMBEDDING_BASE_URL", "http://localhost:20020/v1")
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "lm-studio")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-bge-m3")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))

    # --- Milvus ---
    MILVUS_HOST: str = os.getenv("MILVUS_HOST", "localhost")
    MILVUS_PORT: int = int(os.getenv("MILVUS_PORT", "19530"))
    MILVUS_DATABASE: str = os.getenv("MILVUS_DATABASE", "m_paper")
    MILVUS_COLLECTION: str = os.getenv("MILVUS_COLLECTION", "m_sid_v_09_01")

    # --- MariaDB ---
    MARIADB_HOST: str = os.getenv("MARIADB_HOST", "localhost")
    MARIADB_PORT: int = int(os.getenv("MARIADB_PORT", "3306"))
    MARIADB_USER: str = os.getenv("MARIADB_USER", "root")
    MARIADB_PASSWORD: str = os.getenv("MARIADB_PASSWORD", "")
    MARIADB_DATABASE: str = os.getenv("MARIADB_DATABASE", "paper")
    MARIADB_URL: str = os.getenv(
        "MARIADB_URL",
        f"mysql+pymysql://{os.getenv('MARIADB_USER', 'root')}:"
        f"{os.getenv('MARIADB_PASSWORD', '')}@"
        f"{os.getenv('MARIADB_HOST', 'localhost')}:"
        f"{os.getenv('MARIADB_PORT', '3306')}/"
        f"{os.getenv('MARIADB_DATABASE', 'paper')}",
    )

    # --- Langfuse (관측성/트레이싱) ---
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "http://localhost:20025")

    # --- RAG 파라미터 ---
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))
    TOP_K: int = int(os.getenv("TOP_K", "5"))


settings = Settings()
