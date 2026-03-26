"""
Advanced Text Chunker v2 — 논문 텍스트를 위한 고급 청킹 전략.

5가지 전략을 제공하며, 기존 chunker.py와 동일한 인터페이스(chunk_text)로 교체 가능.

전략 목록:
  1. fixed       — 기존과 동일 (고정 크기 문자 분할)
  2. recursive   — 구분자 우선순위 기반 재귀 분할 (★ 추천 기본값)
  3. sentence    — 문장 단위 분할 후 병합
  4. semantic    — 임베딩 코사인 유사도 기반 의미 경계 분할
  5. section     — 논문 섹션 구조 인식 + recursive 분할

교체 방법:
  chunker.py의 chunk_text를 아래로 교체:
    from app.services.chunker_v2 import chunk_text
  또는 전략 지정:
    from app.services.chunker_v2 import chunk_text_with_strategy
    chunks = chunk_text_with_strategy(text, strategy="recursive")
"""
from __future__ import annotations

import logging
import math
import re
from typing import Literal

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------
Strategy = Literal["fixed", "recursive", "sentence", "semantic", "section"]

# ---------------------------------------------------------------------------
# 1. Fixed Chunking (기존 방식)
# ---------------------------------------------------------------------------

def _chunk_fixed(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """고정 크기 문자 분할 — 기존 chunker.py와 동일."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - chunk_overlap
    return chunks


# ---------------------------------------------------------------------------
# 2. Recursive Chunking (★ 추천)
# ---------------------------------------------------------------------------

# 구분자 우선순위: 단락 > 줄바꿈 > 문장 끝 > 공백 > 문자
_DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]


def _split_by_separator(text: str, separator: str) -> list[str]:
    """separator로 분할하되, separator를 앞 조각 끝에 보존."""
    if not separator:
        return list(text)
    parts = text.split(separator)
    # separator를 앞 조각에 붙여줌 (". " 등이 사라지지 않도록)
    result = []
    for i, part in enumerate(parts):
        if i < len(parts) - 1:
            result.append(part + separator)
        else:
            if part:
                result.append(part)
    return result


def _chunk_recursive(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    separators: list[str] | None = None,
) -> list[str]:
    """
    구분자 우선순위 기반 재귀 분할.

    NVIDIA 2024 벤치마크 권장: 400~512 토큰, 10~20% overlap.
    LangChain RecursiveCharacterTextSplitter와 동일한 로직.
    """
    seps = separators if separators is not None else list(_DEFAULT_SEPARATORS)

    if not text:
        return []

    # 현재 레벨의 구분자 선택
    current_sep = ""
    remaining_seps = []
    for i, sep in enumerate(seps):
        if sep == "":
            current_sep = sep
            remaining_seps = []
            break
        if sep in text:
            current_sep = sep
            remaining_seps = seps[i + 1:]
            break

    # 분할
    pieces = _split_by_separator(text, current_sep)

    # 병합: chunk_size 이내로 조각을 합침
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for piece in pieces:
        piece_len = len(piece)

        # 단일 조각이 chunk_size보다 크면 재귀 분할
        if piece_len > chunk_size:
            # 현재까지 모은 것을 flush
            if current_chunk:
                chunks.append("".join(current_chunk))
                current_chunk = []
                current_len = 0

            if remaining_seps:
                sub_chunks = _chunk_recursive(piece, chunk_size, chunk_overlap, remaining_seps)
                chunks.extend(sub_chunks)
            else:
                # 최종 fallback: 강제 고정 크기 분할
                chunks.extend(_chunk_fixed(piece, chunk_size, chunk_overlap))
            continue

        # chunk_size 초과 시 flush
        if current_len + piece_len > chunk_size:
            if current_chunk:
                chunks.append("".join(current_chunk))
                # overlap 처리: 마지막 조각들을 overlap만큼 유지
                overlap_pieces: list[str] = []
                overlap_len = 0
                for p in reversed(current_chunk):
                    if overlap_len + len(p) <= chunk_overlap:
                        overlap_pieces.insert(0, p)
                        overlap_len += len(p)
                    else:
                        break
                current_chunk = overlap_pieces
                current_len = overlap_len

        current_chunk.append(piece)
        current_len += piece_len

    # 마지막 청크
    if current_chunk:
        chunks.append("".join(current_chunk))

    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# 3. Sentence Chunking
# ---------------------------------------------------------------------------

_SENTENCE_RE = re.compile(
    r'(?<=[.!?])\s+'      # 영어 문장 끝
    r'|(?<=[。！？])\s*'   # 한중일 문장 끝
    r'|(?<=\n)\s*'         # 줄바꿈
)


def _split_sentences(text: str) -> list[str]:
    """텍스트를 문장 단위로 분할."""
    parts = _SENTENCE_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _chunk_sentence(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """
    문장 단위 분할 후 chunk_size 이내로 병합.

    문장 경계를 존중하므로 의미가 중간에 잘리지 않음.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return [text] if text.strip() else []

    chunks: list[str] = []
    current_sentences: list[str] = []
    current_len = 0

    for sent in sentences:
        sent_len = len(sent)

        # 단일 문장이 chunk_size보다 크면 단독 청크로
        if sent_len > chunk_size:
            if current_sentences:
                chunks.append(" ".join(current_sentences))
                current_sentences = []
                current_len = 0
            # 긴 문장은 recursive로 분할
            chunks.extend(_chunk_recursive(sent, chunk_size, chunk_overlap))
            continue

        if current_len + sent_len + 1 > chunk_size:
            chunks.append(" ".join(current_sentences))
            # overlap: 뒤에서부터 overlap 크기만큼 문장 유지
            overlap_sents: list[str] = []
            overlap_len = 0
            for s in reversed(current_sentences):
                if overlap_len + len(s) + 1 <= chunk_overlap:
                    overlap_sents.insert(0, s)
                    overlap_len += len(s) + 1
                else:
                    break
            current_sentences = overlap_sents
            current_len = overlap_len

        current_sentences.append(sent)
        current_len += sent_len + 1

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# 4. Semantic Chunking (임베딩 유사도 기반)
# ---------------------------------------------------------------------------

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """두 벡터의 코사인 유사도."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _chunk_semantic_async(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    similarity_threshold: float = 0.5,
    breakpoint_percentile: float = 90.0,
) -> list[str]:
    """
    Semantic Chunking — 임베딩 유사도 기반 의미 경계 분할.

    원리:
    1. 텍스트를 문장으로 분할
    2. 각 문장을 임베딩
    3. 인접 문장 간 코사인 유사도 계산
    4. 유사도가 임계값 아래로 떨어지는 지점에서 분할

    ※ 임베딩 호출이 필요하므로 async 함수. 비용: 문장 수 × 1 embedding call.
    """
    from app.core.embeddings import embedding_client

    sentences = _split_sentences(text)
    if len(sentences) <= 1:
        return [text] if text.strip() else []

    # 문장 임베딩 (배치 호출로 효율화)
    embeddings = await embedding_client.embed_texts(sentences)

    # 인접 문장 간 유사도 계산
    similarities: list[float] = []
    for i in range(len(embeddings) - 1):
        sim = _cosine_similarity(embeddings[i], embeddings[i + 1])
        similarities.append(sim)

    # 분할 임계값 결정 (percentile 기반)
    if similarities:
        sorted_sims = sorted(similarities)
        idx = int(len(sorted_sims) * (1 - breakpoint_percentile / 100))
        threshold = sorted_sims[max(0, idx)]
        # 사용자 지정 threshold가 있으면 그것과 비교하여 더 엄격한 것 사용
        threshold = min(threshold, similarity_threshold)
    else:
        threshold = similarity_threshold

    # 유사도가 threshold 이하인 지점에서 분할
    breakpoints: list[int] = []
    for i, sim in enumerate(similarities):
        if sim < threshold:
            breakpoints.append(i + 1)  # i+1번째 문장 이전에서 분할

    # 분할 지점으로 문장 그룹화
    groups: list[list[str]] = []
    start = 0
    for bp in breakpoints:
        group = sentences[start:bp]
        if group:
            groups.append(group)
        start = bp
    # 마지막 그룹
    if start < len(sentences):
        groups.append(sentences[start:])

    # 그룹을 청크로 변환 (chunk_size 초과 시 재분할)
    chunks: list[str] = []
    for group in groups:
        group_text = " ".join(group)
        if len(group_text) <= chunk_size:
            chunks.append(group_text)
        else:
            # 너무 큰 그룹은 sentence chunking으로 재분할
            sub_chunks = _chunk_sentence(group_text, chunk_size, chunk_overlap)
            chunks.extend(sub_chunks)

    return [c for c in chunks if c.strip()]


def _chunk_semantic_sync(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    similarity_threshold: float = 0.5,
) -> list[str]:
    """Semantic chunking의 동기 래퍼 (이벤트 루프가 없는 환경용)."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        # 이미 이벤트 루프가 돌고 있으면 nest_asyncio 또는 fallback
        logger.warning("Semantic chunking called in running loop, falling back to sentence chunking")
        return _chunk_sentence(text, chunk_size, chunk_overlap)
    except RuntimeError:
        return asyncio.run(_chunk_semantic_async(text, chunk_size, chunk_overlap, similarity_threshold))


# ---------------------------------------------------------------------------
# 5. Section-Aware Chunking (논문 구조 인식)
# ---------------------------------------------------------------------------

# 논문 섹션을 감지하는 패턴들 (줄 전체 매치)
_SECTION_PATTERNS = [
    # 대문자 섹션: "ABSTRACT", "INTRODUCTION" 등 (줄 전체가 섹션명)
    re.compile(r'^(ABSTRACT|INTRODUCTION|BACKGROUND|RELATED\s+WORK|METHODS?|METHODOLOGY|'
               r'MATERIALS?\s+AND\s+METHODS?|EXPERIMENTAL?|RESULTS?|DISCUSSION|'
               r'CONCLUSION|CONCLUSIONS|SUMMARY|ACKNOWLEDGMENTS?|REFERENCES|'
               r'APPENDIX|SUPPLEMENTARY)\s*$', re.MULTILINE | re.IGNORECASE),
    # 숫자 접두사 섹션: "1. Introduction", "2.1 Methods" (숫자+점+공백+제목)
    re.compile(r'^(\d+\.?\d*\.?\s+[A-Z][A-Za-z\s&:,\-]{2,40})\s*$', re.MULTILINE),
    # Title Case 섹션 (줄 전체가 섹션명)
    re.compile(r'^(Introduction|Background|Related Work|Literature Review|'
               r'Method(?:ology)?|Materials? and Methods?|Experimental Setup|'
               r'Results?|Discussion|Conclusion|Summary|Future Work|'
               r'Acknowledgments?|References|Appendix)\s*$', re.MULTILINE),
]


def _detect_sections(text: str) -> list[tuple[str, str]]:
    """
    논문 텍스트에서 섹션을 감지하여 (section_name, section_text) 리스트 반환.

    섹션을 감지하지 못하면 전체 텍스트를 하나의 섹션으로 반환.
    """
    # 모든 패턴에서 매치 찾기
    matches: list[tuple[int, str]] = []
    for pattern in _SECTION_PATTERNS:
        for m in pattern.finditer(text):
            section_name = m.group(0).strip()
            matches.append((m.start(), section_name))

    if not matches:
        return [("full_text", text)]

    # 위치순 정렬 + 중복 제거
    matches.sort(key=lambda x: x[0])
    seen_positions: set[int] = set()
    unique_matches: list[tuple[int, str]] = []
    for pos, name in matches:
        if pos not in seen_positions:
            seen_positions.add(pos)
            unique_matches.append((pos, name))

    # 섹션별 텍스트 추출
    sections: list[tuple[str, str]] = []

    # 첫 섹션 이전 텍스트 (제목, 저자 등)
    if unique_matches[0][0] > 0:
        preamble = text[:unique_matches[0][0]].strip()
        if preamble:
            sections.append(("Preamble", preamble))

    for i, (pos, name) in enumerate(unique_matches):
        if i + 1 < len(unique_matches):
            end = unique_matches[i + 1][0]
        else:
            end = len(text)
        section_text = text[pos:end].strip()
        # 섹션 제목 줄 제거 (본문만)
        lines = section_text.split("\n", 1)
        body = lines[1].strip() if len(lines) > 1 else ""
        # 섹션명 정규화: 번호 제거 + 최대 30자
        clean_name = re.sub(r'^\d+\.?\d*\.?\s*', '', name).strip()
        if not clean_name:
            clean_name = name.strip()
        clean_name = clean_name[:30]
        if body:
            sections.append((clean_name, body))

    return sections if sections else [("full_text", text)]


def _chunk_section(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """
    논문 섹션 구조 인식 + recursive 분할.

    1. 섹션을 감지하여 분리
    2. 각 섹션을 recursive chunking으로 분할
    3. 각 청크 앞에 [섹션명] 메타데이터 추가

    장점: 섹션 경계를 넘지 않으므로 의미 일관성 보장.
    """
    sections = _detect_sections(text)

    chunks: list[str] = []
    for section_name, section_text in sections:
        if not section_text.strip():
            continue

        # 섹션 메타데이터 접두사
        prefix = f"[Section: {section_name}]\n"
        available_size = chunk_size - len(prefix)

        if available_size <= 50:
            # prefix가 너무 길면 메타데이터 생략
            sub_chunks = _chunk_recursive(section_text, chunk_size, chunk_overlap)
        else:
            sub_chunks = _chunk_recursive(section_text, available_size, chunk_overlap)
            sub_chunks = [prefix + c for c in sub_chunks]

        chunks.extend(sub_chunks)

    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Public API — drop-in replacement
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[str]:
    """
    기존 chunker.py와 동일한 인터페이스.

    기본 전략: recursive (CHUNKING_STRATEGY 환경변수로 변경 가능).
    """
    strategy = getattr(settings, "CHUNKING_STRATEGY", "recursive")
    return chunk_text_with_strategy(text, strategy=strategy, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def chunk_text_with_strategy(
    text: str,
    strategy: Strategy = "recursive",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    **kwargs,
) -> list[str]:
    """
    전략을 지정하여 청킹.

    Args:
        text: 청킹할 텍스트
        strategy: "fixed" | "recursive" | "sentence" | "semantic" | "section"
        chunk_size: 청크 크기 (기본값: settings.CHUNK_SIZE)
        chunk_overlap: 청크 오버랩 (기본값: settings.CHUNK_OVERLAP)
        **kwargs: 전략별 추가 파라미터
            - semantic: similarity_threshold (float, 기본 0.5)

    Returns:
        청크 리스트
    """
    size = chunk_size or settings.CHUNK_SIZE
    overlap = chunk_overlap or settings.CHUNK_OVERLAP

    logger.info(
        "chunk_text_v2 called: strategy=%s, text_len=%d, chunk_size=%d, overlap=%d",
        strategy, len(text), size, overlap,
    )

    if strategy == "fixed":
        chunks = _chunk_fixed(text, size, overlap)
    elif strategy == "recursive":
        chunks = _chunk_recursive(text, size, overlap)
    elif strategy == "sentence":
        chunks = _chunk_sentence(text, size, overlap)
    elif strategy == "semantic":
        chunks = _chunk_semantic_sync(text, size, overlap, kwargs.get("similarity_threshold", 0.5))
    elif strategy == "section":
        chunks = _chunk_section(text, size, overlap)
    else:
        logger.warning("Unknown strategy '%s', falling back to recursive", strategy)
        chunks = _chunk_recursive(text, size, overlap)

    logger.info("chunk_text_v2 result: %d chunks (strategy=%s)", len(chunks), strategy)
    return chunks


async def chunk_text_async(
    text: str,
    strategy: Strategy = "semantic",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    **kwargs,
) -> list[str]:
    """
    비동기 청킹 (semantic 전략에서 임베딩 호출이 필요할 때 사용).

    non-semantic 전략은 내부적으로 동기 함수를 호출.
    """
    size = chunk_size or settings.CHUNK_SIZE
    overlap = chunk_overlap or settings.CHUNK_OVERLAP

    if strategy == "semantic":
        return await _chunk_semantic_async(
            text, size, overlap,
            similarity_threshold=kwargs.get("similarity_threshold", 0.5),
            breakpoint_percentile=kwargs.get("breakpoint_percentile", 90.0),
        )
    else:
        return chunk_text_with_strategy(text, strategy=strategy, chunk_size=size, chunk_overlap=overlap, **kwargs)
