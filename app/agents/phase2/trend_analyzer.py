"""Trend Analyzer Agent — 논문 기반 기술 트렌드를 분석한다."""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.common import llm_text_call, retrieve_by_query, format_context, build_sources

logger = logging.getLogger(__name__)

ANALYZE_SYSTEM = """You are a Co-Scientist specializing in technology trend analysis for display R&D.
Based on papers retrieved from different time periods, analyze trends.

## Display Technology Categories (SID/Wiley 분류 기준)
1. Active-Matrix Devices and Displays
2. Applied Vision and Human Factors
3. Backlighting and Solid State Lighting Technologies
4. Display Electronics
5. Display Manufacturing Technologies
6. Display Measurements
7. Display Systems; Optical and Electronic
8. Electronic Paper and Flexible Displays
9. Liquid Crystal and other Non-emissive Displays
10. Organic Light Emitting Devices and Displays
11. Plasma and other Emissive Displays
12. Projection Displays and Systems

## 분석 규칙:
- 사용자가 **특정 주제 없이** 트렌드/경향 분석을 요청하면:
  - 위 카테고리별로 논문을 분류하고, 카테고리별 논문 수와 비중을 표로 정리
  - 어떤 카테고리가 활발한지, 어떤 기술이 부상/쇠퇴하는지 분석
- 사용자가 **특정 주제**를 언급하면 (예: "Micro LED 트렌드"), 해당 주제 논문만 분석

## 분석 항목:
1. Executive Summary (카테고리별 분포 포함)
2. Rising Technologies (부상 기술)
3. Declining/Mature Technologies (성숙/쇠퇴 기술)
4. Key Research Groups (주요 연구 그룹)
5. Geographic Trends (지역별 동향)
6. Keyword Evolution (키워드 변화)
7. Prediction (향후 2-3년 전망)
8. Strategic Recommendations (전략 제언)

Cite papers [Author, Year]. Answer in the same language as the user's question."""


async def collect_temporal_data(state: AgentState) -> AgentState:
    results = await retrieve_by_query(query=state.get("query",""), user_id=state.get("user_id"),
                                       filters=state.get("filters"), top_k=30)
    results.sort(key=lambda x: x.get("coverdate", ""), reverse=True)
    state["search_results"] = results
    state["context"] = format_context(results)
    return state


async def analyze_trends(state: AgentState) -> AgentState:
    if not state.get("search_results"):
        state["answer"] = "해당 주제에 대한 논문 데이터가 부족합니다."
        state["sources"] = []
        return state
    answer = await llm_text_call(
        system_prompt=ANALYZE_SYSTEM,
        user_prompt=f"Technology area: {state.get('query','')}\n\n### Papers (newest first)\n\n{state.get('context','')}",
        user_id=state.get("user_id"), trace_name="trend_analyze", temperature=0.4,
    state=state,
)
    state["answer"] = answer
    state["sources"] = build_sources(state.get("search_results", []))
    return state


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("collect_temporal_data", collect_temporal_data)
    graph.add_node("analyze_trends", analyze_trends)
    graph.set_entry_point("collect_temporal_data")
    graph.add_edge("collect_temporal_data", "analyze_trends")
    graph.add_edge("analyze_trends", END)
    return graph.compile()

agent = build_graph()
