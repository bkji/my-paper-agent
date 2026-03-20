"""Text chunker — 논문 텍스트를 고정 크기 chunk로 분할한다."""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[str]:
    """텍스트를 chunk_size 단위로 분할한다."""
    size = chunk_size or settings.CHUNK_SIZE
    overlap = chunk_overlap or settings.CHUNK_OVERLAP

    logger.info("chunk_text called: text_len=%d, chunk_size=%d, overlap=%d", len(text), size, overlap)

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap

    logger.info("chunk_text result: %d chunks", len(chunks))
    return chunks
