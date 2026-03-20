"""Supervisor Agent — 사용자 의도를 파악하여 적절한 하위 Agent로 라우팅한다.

개선사항 (기존 대비):
- 자연어 날짜 표현을 자동 파싱하여 filters에 반영
  예: "2024년 11월 논문" → coverdate_from=20241101, coverdate_to=20241130
  예: "작년 여름 Micro LED" → coverdate_from=20250601, coverdate_to=20250831
"""
from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import StateGraph, END

from datetime import datetime

from app.agents.state import AgentState
from app.core.langfuse_client import observe, langfuse_context
from app.core.date_parser import extract_date_filters
from app.core.tools import get_current_datetime, get_current_date_context
from app.agents.common import llm_json_call

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

INTENT_SYSTEM_PROMPT = """You are an intent classifier for a display R&D Co-Scientist system.
Classify the user query into exactly ONE of the following agent types.
Return JSON: {"agent_type": "<type>", "reason": "<brief reason>"}

Available agents:
- paper_qa: Simple question about papers, searching for specific information in literature
- literature_survey: Request for comprehensive literature review on a topic
- paper_deep_dive: Deep analysis of a specific paper (by DOI, title, or detailed reference)
- analytics: Paper statistics, counts, lists, trends over time (monthly/yearly counts, paper lists by condition, aggregation)
- idea_generator: Request for new research ideas, brainstorming, novel approaches
- cross_domain: Applying concepts from other fields to display technology
- trend_analyzer: Technology trend analysis, timeline, evolution of a field
- experiment_planner: Designing experiments, experimental methodology, test plans
- patent_landscaper: Patent analysis, patent landscape, IP white spaces
- competitive_intel: Competitor analysis, company benchmarking, market intelligence
- material_advisor: Material selection, process comparison, material properties
- report_drafter: Writing reports, presentations, summaries
- peer_review: Reviewing a manuscript, providing feedback on a paper
- knowledge_connector: Finding experts, author network, collaboration opportunities

Rules:
- If the query asks for counts, statistics, paper lists, monthly/yearly trends → analytics
- If the query is a simple factual question about papers → paper_qa
- If the query asks for a survey/review/overview → literature_survey
- If ambiguous, default to paper_qa
- Always respond with valid JSON only"""


@observe(name="supervisor_extract_dates")
async def extract_dates(state: AgentState) -> AgentState:
    """쿼리에서 날짜 표현을 추출하여 filters에 반영한다. 서버 시간을 기준으로 상대 날짜를 계산."""
    query = state.get("query", "")
    filters = state.get("filters") or {}

    # 서버 현재 시간을 기준으로 날짜 파싱
    now = datetime.now()
    server_time = get_current_datetime()

    date_filters = extract_date_filters(query, reference_date=now)
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

    # 메타데이터에 서버 시간과 날짜 컨텍스트 저장 → 하위 agent들이 사용
    metadata = state.get("metadata") or {}
    metadata["server_time"] = server_time
    metadata["date_context"] = get_current_date_context()
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
    try:
        result = await llm_json_call(
            system_prompt=INTENT_SYSTEM_PROMPT,
            user_prompt=query,
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

    개선된 흐름: extract_dates → classify_intent → route_to_agent
    """
    graph = StateGraph(AgentState)
    graph.add_node("extract_dates", extract_dates)
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("route_to_agent", route_to_agent)
    graph.set_entry_point("extract_dates")
    graph.add_edge("extract_dates", "classify_intent")
    graph.add_edge("classify_intent", "route_to_agent")
    graph.add_edge("route_to_agent", END)
    return graph.compile()


supervisor = build_supervisor()
