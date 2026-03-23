"""Citation & Disclaimer Agent — 응답 끝에 참조 문헌 + 저작권 고지를 추가한다.

모든 에이전트 응답 후 supervisor에서 마지막 단계로 실행된다.
RAG 검색 결과(sources)가 있는 경우에만 참조 문헌을 추가한다.
"""
from __future__ import annotations

import logging
from app.agents.state import AgentState

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


async def append_citation(state: AgentState) -> AgentState:
    """응답에 참조 문헌과 저작권 고지를 추가한다."""
    answer = state.get("answer", "")
    sources = state.get("sources") or []

    if not answer:
        return state

    parts = [answer.rstrip()]

    # 참조 문헌 (sources가 있는 경우만)
    if sources:
        # title 기준 중복 제거
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
                parts.append(line)

    # 저작권 고지 (항상 추가)
    parts.append(f"\n\n---\n{DISCLAIMER}")

    state["answer"] = "\n".join(parts)
    logger.info("[Citation] appended citation (%d sources) + disclaimer", len(sources))
    return state
