"""사내 도메인 용어 매핑 — 사내 약어/은어를 표준 검색 키워드로 확장한다.

YAML 사전 파일(domain_glossary.yaml)을 로드하여, 사용자 쿼리에서
사내 용어를 발견하면 해당 표준 키워드를 쿼리에 추가한다.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class TermMapping:
    aliases: list[str]
    canonical: str
    search_keywords: list[str]
    _pattern: re.Pattern | None = field(default=None, repr=False)

    def __post_init__(self):
        # 길이 역순 정렬 (긴 패턴 먼저 매칭되도록)
        sorted_aliases = sorted(self.aliases, key=len, reverse=True)
        escaped = [re.escape(a) for a in sorted_aliases]
        self._pattern = re.compile("|".join(escaped), re.IGNORECASE)


class DomainGlossary:
    """사내 용어 사전. YAML 파일에서 로드하여 쿼리 확장에 사용."""

    def __init__(self, glossary_path: str | None = None):
        if glossary_path is None:
            glossary_path = os.path.join(
                os.path.dirname(__file__), "domain_glossary.yaml"
            )
        self.mappings: list[TermMapping] = []
        self._load(glossary_path)

    def _load(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            for item in data.get("terms", []):
                self.mappings.append(TermMapping(
                    aliases=item["aliases"],
                    canonical=item["canonical"],
                    search_keywords=item["search_keywords"],
                ))
            logger.info("[Glossary] %d개 용어 매핑 로드: %s", len(self.mappings), path)
        except FileNotFoundError:
            logger.warning("[Glossary] 용어 사전 파일 없음: %s", path)
        except Exception as e:
            logger.warning("[Glossary] 용어 사전 로드 실패: %s", e)

    def expand_query(self, query: str) -> dict[str, Any]:
        """쿼리에서 사내 용어를 찾아 확장 정보를 반환한다.

        Returns:
            {
                "matched_terms": [{"alias": "P공정", "canonical": "...", ...}],
                "expanded_query": "원본 쿼리 (photolithography, 포토, 노광)",
                "extra_keywords": ["photo", "photolithography", ...],
            }
        """
        matched = []
        extra_keywords = []

        for mapping in self.mappings:
            match = mapping._pattern.search(query)
            if match:
                matched.append({
                    "alias": match.group(),
                    "canonical": mapping.canonical,
                    "search_keywords": mapping.search_keywords,
                })
                extra_keywords.extend(mapping.search_keywords)

        if not matched:
            return {"matched_terms": [], "expanded_query": query, "extra_keywords": []}

        # 순서 유지 중복 제거
        seen = set()
        unique_keywords = []
        for kw in extra_keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        # 쿼리 확장: 원본 쿼리 뒤에 관련 키워드 추가
        keyword_str = ", ".join(unique_keywords)
        expanded = f"{query} ({keyword_str})"

        return {
            "matched_terms": matched,
            "expanded_query": expanded,
            "extra_keywords": unique_keywords,
        }


# 싱글턴 인스턴스
glossary = DomainGlossary()
