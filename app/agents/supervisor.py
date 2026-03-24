"""Supervisor Agent — 사용자 의도를 파악하여 적절한 하위 Agent로 라우팅한다.

개선사항 (기존 대비):
- 자연어 날짜 표현을 자동 파싱하여 filters에 반영
  예: "2024년 11월 논문" → coverdate_from=20241101, coverdate_to=20241130
  예: "작년 여름 Micro LED" → coverdate_from=20250601, coverdate_to=20250831
"""
from __future__ import annotations

import logging
import re
from typing import Any

from langgraph.graph import StateGraph, END

from datetime import datetime

from app.agents.state import AgentState
from app.core.langfuse_client import observe, langfuse_context
from app.core.date_parser import extract_date_filters
from app.core.tools import get_current_datetime, get_current_date_context
from app.agents.common import llm_json_call
from app.agents.citation_agent import append_citation

logger = logging.getLogger(__name__)

AGENT_REGISTRY: dict[str, dict[str, Any]] = {
    # Phase 1
    "paper_qa": {
        "module": "app.agents.phase1.paper_qa",
        "description": "논문 검색 및 질의응답",
    },
    "literature_survey": {
        "module": "app.agents.phase1.literature_survey",
        "description": "주제별 문헌 리뷰 자동 생성",
    },
    "paper_deep_dive": {
        "module": "app.agents.phase1.paper_deep_dive",
        "description": "특정 논문 심층 분석",
    },
    "analytics": {
        "module": "app.agents.phase1.analytics",
        "description": "논문 통계/집계/목록 조회 (편수, 추이, 리스트, 그래프)",
    },
    # Phase 2
    "idea_generator": {
        "module": "app.agents.phase2.idea_generator",
        "description": "논문 교차 분석 기반 연구 아이디어 제안",
    },
    "cross_domain": {
        "module": "app.agents.phase2.cross_domain",
        "description": "타 분야 접근법을 디스플레이에 적용 제안",
    },
    "trend_analyzer": {
        "module": "app.agents.phase2.trend_analyzer",
        "description": "논문/뉴스 기반 기술 트렌드 분석",
    },
    # Phase 3
    "experiment_planner": {
        "module": "app.agents.phase3.experiment_planner",
        "description": "문헌 기반 실험 설계 제안",
    },
    "patent_landscaper": {
        "module": "app.agents.phase3.patent_landscaper",
        "description": "특허 동향 분석 및 공백 영역 식별",
    },
    "competitive_intel": {
        "module": "app.agents.phase3.competitive_intel",
        "description": "경쟁사 동향 모니터링 및 브리핑",
    },
    "material_advisor": {
        "module": "app.agents.phase3.material_advisor",
        "description": "목표 기반 재료/공정 비교 분석",
    },
    # Phase 4
    "report_drafter": {
        "module": "app.agents.phase4.report_drafter",
        "description": "연구 결과 기반 보고서/발표 초안 작성",
    },
    "peer_review": {
        "module": "app.agents.phase4.peer_review",
        "description": "논문/보고서에 대한 가상 리뷰",
    },
    "knowledge_connector": {
        "module": "app.agents.phase4.knowledge_connector",
        "description": "논문 저자 기반 사내 전문가 매칭",
    },
}

INTENT_SYSTEM_PROMPT = """You are an intent classifier. Classify the query into ONE agent type.
Return ONLY JSON: {"agent_type": "<type>", "reason": "<brief>"}

## Agent types:

analytics: 논문 편수, 건수, 목록, 리스트, 통계, 추이, 월별/연도별 집계, 제목 보여줘, 몇 편, 찾아줘, volume, issue
paper_qa: 논문 내용에 대한 질문, 기술 설명, 원리 질문
literature_survey: 문헌 리뷰, 서베이, 연구 동향 종합 정리
paper_deep_dive: 특정 논문 1편을 깊이 분석 (DOI나 제목 지정). DOI가 포함된 질문은 반드시 이 에이전트로 분류.
idea_generator: 새로운 연구 아이디어, 브레인스토밍
cross_domain: 타 분야 기술을 디스플레이에 적용
trend_analyzer: 기술 트렌드 분석, 기술 발전 타임라인
experiment_planner: 실험 설계, 실험 방법론
patent_landscaper: 특허 분석, 특허 동향
competitive_intel: 경쟁사 분석, 시장 동향
material_advisor: 재료/공정 비교, 소재 선택
report_drafter: 보고서/발표 초안 작성
peer_review: 논문 리뷰, 피드백
knowledge_connector: 전문가 매칭, 저자 네트워크

## Examples:

Query: "2024년 10월 논문 편수와 제목 보여줘"
→ {"agent_type": "analytics", "reason": "편수 and 제목 목록 request"}

Query: "최근 6개월 OLED 논문 몇 편이야?"
→ {"agent_type": "analytics", "reason": "논문 편수 count"}

Query: "2024년 논문 목록 보여줘"
→ {"agent_type": "analytics", "reason": "논문 목록 list request"}

Query: "월별 논문 추이 그래프"
→ {"agent_type": "analytics", "reason": "월별 추이 aggregation"}

Query: "Micro LED 결함 검출 방법은?"
→ {"agent_type": "paper_qa", "reason": "technical question about paper content"}

Query: "OLED 소재 연구 동향을 정리해줘"
→ {"agent_type": "literature_survey", "reason": "survey/review request"}

## Rules:
- 편수, 건수, 몇 편, 목록, 리스트, 제목 보여줘, 통계, 추이, 그래프, 찾아줘, volume, issue → analytics
- DOI가 포함된 질문 (예: "10.1002/jsid.2003") → paper_deep_dive
- Default: paper_qa
- Return valid JSON only

## More Examples:

Query: "led 관련 논문 찾아줘"
→ {"agent_type": "analytics", "reason": "논문 찾기 list request"}

Query: "volume 32, issue 10인 논문 제목들 보여줘"
→ {"agent_type": "analytics", "reason": "volume/issue filter list request"}

Query: "Micro LED 관련 논문 최근 5년 연도별 발표건수를 분석해줘"
→ {"agent_type": "analytics", "reason": "연도별 발표건수 aggregation"}

Query: "10.1002/jsid.2003 논문 정리해줘"
→ {"agent_type": "paper_deep_dive", "reason": "DOI specified, deep analysis"}"""


@observe(name="supervisor_extract_dates")
async def extract_dates(state: AgentState) -> AgentState:
    """쿼리에서 날짜 표현을 추출하여 filters에 반영한다. 서버 시간을 기준으로 상대 날짜를 계산."""
    query = state.get("query", "")
    filters = state.get("filters") or {}

    # 서버 현재 시간을 기준으로 날짜 파싱
    now = datetime.now()
    server_time = get_current_datetime()

    date_filters = extract_date_filters(query, reference_date=now)

    # 멀티턴: 현재 쿼리에 날짜 관련 표현이 전혀 없을 때만 히스토리에서 추출
    # "지난 여름", "최근", "작년" 등 날짜 표현이 있으면 히스토리 fallback 하지 않음
    # (LLM extract_conditions에서 처리)
    _has_date_hint = bool(re.search(
        r'\d{4}년|최근|작년|올해|지난|전년|금년|상반기|하반기|분기|개월|여름|겨울|봄|가을',
        query
    ))
    if not date_filters and not _has_date_hint:
        conversation_history = (state.get("metadata") or {}).get("conversation_history", "")
        if conversation_history:
            date_filters = extract_date_filters(conversation_history, reference_date=now)
            if date_filters:
                logger.info("[Supervisor] date extracted from conversation history: %s", date_filters)
    if date_filters:
        if "coverdate_from" not in filters:
            filters["coverdate_from"] = date_filters["coverdate_from"]
        if "coverdate_to" not in filters:
            filters["coverdate_to"] = date_filters["coverdate_to"]
        state["filters"] = filters
        logger.info(
            "[Supervisor] extracted date filters: from=%s, to=%s (server_time=%s)",
            date_filters.get("coverdate_from"), date_filters.get("coverdate_to"),
            server_time["datetime"],
        )
        langfuse_context(output={"date_filters": date_filters, "server_time": server_time["datetime"]})
    else:
        state["filters"] = filters if filters else None

    # DOI 추출: 쿼리에 DOI 패턴이 있으면 filters에 저장
    doi_match = re.search(r'(10\.\d{4,}/[^\s,;]+)', query)
    if doi_match:
        filters = state.get("filters") or {}
        filters["doi"] = doi_match.group(1)
        state["filters"] = filters
        logger.info("[Supervisor] extracted DOI: %s", doi_match.group(1))

    # 메타데이터에 서버 시간과 날짜 컨텍스트 저장 → 하위 agent들이 사용
    metadata = state.get("metadata") or {}
    metadata["server_time"] = server_time
    metadata["date_context"] = get_current_date_context()
    state["metadata"] = metadata

    return state


EXTRACT_CONDITIONS_PROMPT = """You are a query condition extractor for a paper database.
Extract ALL search conditions from the user's query.
Current server date: {current_date}

Return ONLY valid JSON:
{{
  "coverdate_from": "YYYYMMDD or null",
  "coverdate_to": "YYYYMMDD or null",
  "keyword": "search keyword or null",
  "author": "author name or null",
  "doi": "DOI string or null",
  "volume": volume_number_or_null,
  "issue": issue_number_or_null
}}

## Rules:
- Dates: Convert to YYYYMMDD format. "2024년 10월~12월" → from=20241001, to=20241231
- Relative dates: "최근 5년" from current date, "작년" = previous year
- keyword: Technical search term only (e.g. "OLED", "Micro LED", "holographic"). NOT "논문", "분석", "경향".
- doi: Extract if DOI pattern exists (e.g. "10.1002/jsid.2003")
- volume/issue: Extract numbers if mentioned
- Set null for fields not mentioned in the query

## Examples:
"2024년 10월~12월 논문 경향분석해줘" → {{"coverdate_from": "20241001", "coverdate_to": "20241231", "keyword": null, "author": null, "doi": null, "volume": null, "issue": null}}
"최근 3년 OLED 관련 논문" → {{"coverdate_from": "{three_years_ago}0101", "coverdate_to": "{current_date}", "keyword": "OLED", "author": null, "doi": null, "volume": null, "issue": null}}
"volume 32 issue 10 논문 보여줘" → {{"coverdate_from": null, "coverdate_to": null, "keyword": null, "author": null, "doi": null, "volume": 32, "issue": 10}}
"10.1002/jsid.2003 논문 정리해줘" → {{"coverdate_from": null, "coverdate_to": null, "keyword": null, "author": null, "doi": "10.1002/jsid.2003", "volume": null, "issue": null}}"""


@observe(name="supervisor_extract_conditions")
async def extract_conditions(state: AgentState) -> AgentState:
    """LLM을 사용하여 쿼리에서 날짜, 키워드, 저자, DOI 등 모든 검색 조건을 추출한다.

    regex 날짜 파싱 → LLM 보완 순서로 동작:
    1. regex로 날짜 추출 (빠르고 정확)
    2. LLM으로 추가 조건 추출 (키워드, 저자, DOI, volume, issue)
    3. regex가 날짜를 못 잡으면 LLM 결과로 보완
    """
    query = state.get("query", "")
    filters = state.get("filters") or {}
    metadata = state.get("metadata") or {}

    now = datetime.now()
    current_date = now.strftime("%Y%m%d")

    # LLM으로 모든 조건 추출
    try:
        prompt = EXTRACT_CONDITIONS_PROMPT.format(
            current_date=current_date,
            three_years_ago=str(now.year - 3),
        )
        result = await llm_json_call(
            system_prompt=prompt,
            user_prompt=query,
            trace_name="extract_conditions",
            user_id=state.get("user_id"),
            temperature=0.1,
            state=state,
        )

        # 날짜: regex 결과가 없을 때만 LLM 결과 사용
        if "coverdate_from" not in filters:
            cd_from = result.get("coverdate_from")
            if cd_from and str(cd_from).lower() not in ("null", "none", ""):
                try:
                    filters["coverdate_from"] = int(str(cd_from).replace("-", ""))
                except (ValueError, TypeError):
                    pass
        if "coverdate_to" not in filters:
            cd_to = result.get("coverdate_to")
            if cd_to and str(cd_to).lower() not in ("null", "none", ""):
                try:
                    filters["coverdate_to"] = int(str(cd_to).replace("-", ""))
                except (ValueError, TypeError):
                    pass

        # 키워드
        kw = result.get("keyword")
        if kw and str(kw).lower() not in ("null", "none", ""):
            metadata["analytics_keyword"] = kw

        # 저자
        author = result.get("author")
        if author and str(author).lower() not in ("null", "none", ""):
            metadata["analytics_author"] = author

        # DOI
        doi = result.get("doi")
        if doi and str(doi).lower() not in ("null", "none", ""):
            if "doi" not in filters:
                filters["doi"] = str(doi)

        # Volume/Issue
        vol = result.get("volume")
        if vol is not None and str(vol).lower() not in ("null", "none", ""):
            try:
                metadata["analytics_volume"] = int(vol)
            except (ValueError, TypeError):
                pass
        iss = result.get("issue")
        if iss is not None and str(iss).lower() not in ("null", "none", ""):
            try:
                metadata["analytics_issue"] = int(iss)
            except (ValueError, TypeError):
                pass

        logger.info("[Supervisor] LLM conditions: dates=%s~%s, kw=%s, doi=%s, vol=%s, iss=%s",
                    filters.get("coverdate_from"), filters.get("coverdate_to"),
                    metadata.get("analytics_keyword"), filters.get("doi"),
                    metadata.get("analytics_volume"), metadata.get("analytics_issue"))

    except Exception as e:
        logger.warning("[Supervisor] LLM condition extraction failed: %s", e)

    state["filters"] = filters if filters else None
    state["metadata"] = metadata
    return state


@observe(name="supervisor_classify")
async def classify_intent(state: AgentState) -> AgentState:
    """사용자 쿼리의 의도를 분류하여 적절한 agent_type을 결정한다."""
    logger.info("[Supervisor] classify_intent: query=%s", state.get("query", "")[:100])

    explicit_type = state.get("metadata", {}).get("agent_type")
    if explicit_type and explicit_type in AGENT_REGISTRY:
        state["metadata"] = state.get("metadata", {})
        state["metadata"]["agent_type"] = explicit_type
        state["metadata"]["classification"] = "explicit"
        langfuse_context(output={"agent_type": explicit_type, "classification": "explicit"})
        return state

    query = state.get("query", "")

    # 멀티턴: 대화 히스토리가 있으면 쿼리에 컨텍스트 추가
    conversation_history = (state.get("metadata") or {}).get("conversation_history", "")
    intent_query = query
    if conversation_history:
        intent_query = f"[이전 대화]\n{conversation_history}\n\n[현재 질문]\n{query}"

    try:
        result = await llm_json_call(
            system_prompt=INTENT_SYSTEM_PROMPT,
            user_prompt=intent_query,
            trace_name="classify_intent",
            user_id=state.get("user_id"),
            temperature=0.1,
            state=state,
        )
        agent_type = result.get("agent_type", "paper_qa")
        reason = result.get("reason", "")

        if agent_type not in AGENT_REGISTRY:
            logger.warning("[Supervisor] LLM returned unknown agent_type '%s', falling back to paper_qa", agent_type)
            agent_type = "paper_qa"

    except Exception as e:
        logger.warning("[Supervisor] Intent classification failed: %s, falling back to paper_qa", e)
        agent_type = "paper_qa"
        reason = f"classification error: {e}"

    state["metadata"] = state.get("metadata", {})
    state["metadata"]["agent_type"] = agent_type
    state["metadata"]["classification"] = "llm"
    state["metadata"]["classification_reason"] = reason

    logger.info("[Supervisor] classified intent: %s (reason: %s)", agent_type, reason)
    langfuse_context(output={"agent_type": agent_type, "classification": "llm", "reason": reason})
    return state


@observe(name="supervisor_route")
async def route_to_agent(state: AgentState) -> AgentState:
    """분류된 agent_type에 따라 해당 Agent를 실행한다."""
    agent_type = state.get("metadata", {}).get("agent_type", "paper_qa")
    logger.info("[Supervisor] route_to_agent: agent_type=%s", agent_type)

    if agent_type not in AGENT_REGISTRY:
        state["answer"] = f"Unknown agent type: {agent_type}"
        return state

    import importlib
    module = importlib.import_module(AGENT_REGISTRY[agent_type]["module"])
    agent = module.agent

    logger.info("[Supervisor] executing agent: %s", agent_type)
    result = await agent.ainvoke(state)

    state.update(result)
    return state


def build_supervisor() -> StateGraph:
    """Supervisor agent graph를 구성한다.

    흐름: extract_dates → extract_conditions → classify_intent → route_to_agent → append_citation

    - extract_dates: regex 기반 빠른 날짜 추출
    - extract_conditions: LLM 기반 추가 조건 추출 (키워드, 저자, DOI, volume, issue + 날짜 보완)
    - classify_intent: LLM 기반 의도 분류
    - route_to_agent: 해당 에이전트 실행
    - append_citation: 참조 문헌 + 저작권 고지
    """
    graph = StateGraph(AgentState)
    graph.add_node("extract_dates", extract_dates)
    graph.add_node("extract_conditions", extract_conditions)
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("route_to_agent", route_to_agent)
    graph.add_node("append_citation", append_citation)
    graph.set_entry_point("extract_dates")
    graph.add_edge("extract_dates", "extract_conditions")
    graph.add_edge("extract_conditions", "classify_intent")
    graph.add_edge("classify_intent", "route_to_agent")
    graph.add_edge("route_to_agent", "append_citation")
    graph.add_edge("append_citation", END)
    return graph.compile()


supervisor = build_supervisor()
