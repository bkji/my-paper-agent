"""Citation & Disclaimer Agent — 응답 끝에 참조 문헌 + 저작권 고지를 추가한다.

모든 에이전트 응답 후 supervisor에서 마지막 단계로 실행된다.
RAG 검색 결과(sources)가 있는 경우에만 참조 문헌을 추가한다.
"""
from __future__ import annotations

import logging
from app.agents.state import AgentState
from app.config import settings

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "본 서비스는 삼성디스플레이 임직원의 내부 목적에 한해 제공됩니다. "
    "외부 공개, 마케팅, 제3자 제공 또는 상업적 활용은 엄격히 금지됩니다.\n"
    "Copyright © 1999-2026 John Wiley & Sons, Inc or related companies. "
    "All rights reserved, including rights for text and data mining and "
    "training of artificial intelligence technologies or similar technologies."
)


def _normalize_doi(doi: str | None) -> str:
    """DOI를 full link 형식으로 변환한다."""
    if not doi:
        return ""
    doi = doi.strip()
    if doi.startswith("http"):
        return doi
    return f"https://doi.org/{doi}"


def format_citation_text(sources: list[dict]) -> str:
    """sources 리스트로부터 참조 문헌 + 저작권 고지 텍스트를 생성한다.

    스트리밍/비스트리밍 모두에서 재사용 가능한 헬퍼 함수.
    """
    parts = []

    if sources:
        seen_titles = set()
        unique_sources = []
        for src in sources:
            title = src.get("title", "").strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_sources.append(src)

        if unique_sources:
            parts.append("\n\n---\n**참조 문헌:**\n")
            for i, src in enumerate(unique_sources, 1):
                title = src.get("title", "N/A")
                author = src.get("author", "") or ""
                doi_link = _normalize_doi(src.get("doi"))

                line = f"{i}. 제목: {title}"
                if author:
                    line += f", 저자: {author}"
                if doi_link:
                    line += f", DOI: {doi_link}"
                if settings.SHOW_CITATION_SCORE:
                    score_rrf = src.get("score_rrf", 0.0)
                    score_dense = src.get("score_dense", 0.0)
                    score_sparse = src.get("score_sparse", 0.0)
                    if score_rrf > 0 or score_dense > 0 or score_sparse > 0:
                        parts_score = []
                        if score_dense > 0:
                            parts_score.append(f"Dense: {score_dense:.4f}")
                        if score_sparse > 0:
                            parts_score.append(f"BM25: {score_sparse:.4f}")
                        if score_rrf > 0:
                            parts_score.append(f"RRF: {score_rrf:.4f}")
                        line += f" ({', '.join(parts_score)})"
                parts.append(line)

    parts.append(f"\n\n---\n{DISCLAIMER}")
    return "\n".join(parts)


async def append_citation(state: AgentState) -> AgentState:
    """응답에 참조 문헌과 저작권 고지를 추가한다."""
    answer = state.get("answer", "")
    sources = state.get("sources") or []

    # Stream mode: citation은 API에서 스트리밍 후 별도 처리
    if (state.get("metadata") or {}).get("_stream_mode"):
        return state

    if not answer:
        return state

    citation = format_citation_text(sources)
    state["answer"] = answer.rstrip() + citation
    logger.info("[Citation] appended citation (%d sources) + disclaimer", len(sources))
    return state
