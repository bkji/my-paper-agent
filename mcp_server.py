"""Co-Scientist MCP Server — 외부 에이전트가 MCP 프로토콜로 호출할 수 있는 Tool 서버.

실행:
    # stdio 모드 (Claude Desktop, Cursor 등에서 사용)
    python mcp_server.py

    # SSE 모드 (원격 접속용)
    python mcp_server.py --transport sse --port 20032
"""
from __future__ import annotations

import asyncio
import argparse
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.types import Tool, TextContent

# ── 프로젝트 초기화 ──
from app.core.langfuse_client import init_langfuse
from app.agents.supervisor import supervisor, AGENT_REGISTRY
from app.api.deps import extract_usage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,  # MCP stdio 모드에서는 stderr로 로그
)
logger = logging.getLogger("mcp_server")

# ── MCP Server 인스턴스 ──
server = Server("co-scientist")


# ────────────────────────────────────────
# Tool 정의
# ────────────────────────────────────────

TOOLS = [
    Tool(
        name="ask_co_scientist",
        description=(
            "논문 데이터베이스(MariaDB+Milvus)를 활용하는 R&D 지원 AI에게 질문합니다. "
            "논문 검색, 문헌 리뷰, 통계/집계, 트렌드 분석, 아이디어 제안, 실험 설계, "
            "특허 분석, 경쟁사 동향, 재료/공정 비교, 보고서 작성, 피어 리뷰 등 "
            "14개 전문 에이전트가 질문 의도에 맞게 자동 라우팅됩니다. "
            "날짜 표현(예: '최근 3년', '2024년 하반기')도 자동 파싱됩니다."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "사용자 질문 (한국어 또는 영어)",
                },
                "agent_type": {
                    "type": "string",
                    "description": (
                        "특정 에이전트를 지정할 때 사용. 미지정 시 자동 분류. "
                        "가능한 값: paper_qa, literature_survey, paper_deep_dive, "
                        "analytics, idea_generator, cross_domain, trend_analyzer, "
                        "experiment_planner, patent_landscaper, competitive_intel, "
                        "material_advisor, report_drafter, peer_review, knowledge_connector"
                    ),
                    "enum": [
                        "paper_qa", "literature_survey", "paper_deep_dive",
                        "analytics", "idea_generator", "cross_domain",
                        "trend_analyzer", "experiment_planner", "patent_landscaper",
                        "competitive_intel", "material_advisor", "report_drafter",
                        "peer_review", "knowledge_connector",
                    ],
                },
                "filters": {
                    "type": "object",
                    "description": (
                        "검색 필터 (선택). 날짜는 query에서 자동 파싱되므로 보통 불필요. "
                        "직접 지정 시: coverdate_from/coverdate_to (YYYYMMDD 정수), "
                        "keyword, author, doi, volume, issue"
                    ),
                    "properties": {
                        "coverdate_from": {"type": "integer", "description": "시작일 (YYYYMMDD)"},
                        "coverdate_to": {"type": "integer", "description": "종료일 (YYYYMMDD)"},
                        "keyword": {"type": "string"},
                        "author": {"type": "string"},
                        "doi": {"type": "string"},
                        "volume": {"type": "string"},
                        "issue": {"type": "string"},
                    },
                },
                "messages": {
                    "type": "array",
                    "description": "멀티턴 대화 히스토리 (선택). 이전 대화 맥락을 유지할 때 사용.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {
                                "type": "string",
                                "enum": ["user", "assistant"],
                            },
                            "content": {"type": "string"},
                        },
                        "required": ["role", "content"],
                    },
                },
                "user_id": {
                    "type": "string",
                    "description": "사용자 식별자 (선택, Langfuse 트레이싱용)",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="list_agents",
        description=(
            "Co-Scientist에서 사용 가능한 14개 전문 에이전트 목록과 설명을 반환합니다. "
            "어떤 에이전트가 있는지 확인하고 싶을 때 사용하세요."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="search_papers",
        description=(
            "논문 데이터베이스에서 특정 조건으로 논문을 검색합니다. "
            "편수, 목록, 통계 등 데이터 조회에 특화된 analytics 에이전트를 직접 호출합니다."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "검색 질문. 예: '2024년 Micro LED 논문 몇 편?', "
                        "'OLED 관련 최근 논문 목록', '연도별 논문 추이'"
                    ),
                },
                "filters": {
                    "type": "object",
                    "description": "검색 필터 (선택)",
                    "properties": {
                        "coverdate_from": {"type": "integer"},
                        "coverdate_to": {"type": "integer"},
                        "keyword": {"type": "string"},
                        "author": {"type": "string"},
                    },
                },
            },
            "required": ["query"],
        },
    ),
]


# ────────────────────────────────────────
# Tool 핸들러
# ────────────────────────────────────────

async def _run_supervisor(
    query: str,
    agent_type: str | None = None,
    filters: dict | None = None,
    messages: list[dict] | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """supervisor 파이프라인을 실행하고 결과를 반환한다."""
    state: dict[str, Any] = {
        "query": query,
        "user_id": user_id,
        "filters": filters,
        "metadata": {},
    }
    if messages:
        state["metadata"]["messages"] = messages
    if agent_type:
        state["metadata"]["agent_type"] = agent_type

    result = await supervisor.ainvoke(state)

    # 소스 문서 정리
    sources = result.get("sources") or []
    source_list = []
    for s in sources:
        source_list.append({
            "paper_id": s.get("paper_id", ""),
            "title": s.get("title", ""),
            "author": s.get("author", ""),
            "doi": s.get("doi", ""),
            "score": s.get("score", 0),
        })

    usage = extract_usage(result)
    agent_used = (result.get("metadata") or {}).get("agent_type", "unknown")

    return {
        "answer": result.get("answer", ""),
        "agent_type": agent_used,
        "sources": source_list,
        "usage": usage,
        "trace_id": result.get("trace_id"),
    }


def _format_result(result: dict) -> list[TextContent]:
    """supervisor 결과를 MCP TextContent로 포맷한다."""
    parts = [result["answer"]]

    if result.get("sources"):
        parts.append("\n\n---\n📚 참조 논문:")
        for i, s in enumerate(result["sources"], 1):
            line = f"  {i}. {s['title']}"
            if s.get("doi"):
                line += f" (DOI: {s['doi']})"
            if s.get("author"):
                line += f" — {s['author']}"
            parts.append(line)

    parts.append(f"\n[에이전트: {result.get('agent_type', 'unknown')}]")

    return [TextContent(type="text", text="\n".join(parts))]


# ────────────────────────────────────────
# MCP 프로토콜 핸들러
# ────────────────────────────────────────

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    logger.info("Tool called: %s, args: %s", name, json.dumps(arguments, ensure_ascii=False)[:200])

    if name == "ask_co_scientist":
        result = await _run_supervisor(
            query=arguments["query"],
            agent_type=arguments.get("agent_type"),
            filters=arguments.get("filters"),
            messages=arguments.get("messages"),
            user_id=arguments.get("user_id"),
        )
        return _format_result(result)

    elif name == "list_agents":
        agents_info = {
            k: v["description"] for k, v in AGENT_REGISTRY.items()
        }
        return [TextContent(
            type="text",
            text=json.dumps(agents_info, ensure_ascii=False, indent=2),
        )]

    elif name == "search_papers":
        result = await _run_supervisor(
            query=arguments["query"],
            agent_type="analytics",
            filters=arguments.get("filters"),
        )
        return _format_result(result)

    else:
        return [TextContent(type="text", text=f"알 수 없는 도구: {name}")]


# ────────────────────────────────────────
# 엔트리포인트
# ────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Co-Scientist MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "sse", "streamable-http"], default="stdio",
        help="전송 방식: stdio (기본, Claude Desktop용), sse (레거시 원격), streamable-http (최신 원격)",
    )
    parser.add_argument(
        "--port", type=int, default=20032,
        help="SSE 모드 포트 (기본: 20032)",
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="SSE 모드 호스트 (기본: 0.0.0.0)",
    )
    args = parser.parse_args()

    # Langfuse 초기화
    init_langfuse()

    if args.transport == "stdio":
        from mcp.server.stdio import stdio_server

        logger.info("Starting MCP server (stdio mode)")

        async def run_stdio():
            async with stdio_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream, server.create_initialization_options())

        asyncio.run(run_stdio())

    elif args.transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
        import uvicorn

        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await server.run(streams[0], streams[1], server.create_initialization_options())

        starlette_app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )

        logger.info("Starting MCP server (SSE mode) on %s:%d", args.host, args.port)
        uvicorn.run(starlette_app, host=args.host, port=args.port)

    elif args.transport == "streamable-http":
        from mcp.server.streamable_http import StreamableHTTPServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route
        import uvicorn

        async def handle_mcp(request):
            transport = StreamableHTTPServerTransport(
                mcp_session_id=request.headers.get("mcp-session-id"),
            )
            async with transport.connect() as streams:
                await server.run(streams[0], streams[1], server.create_initialization_options())
            return transport.response

        starlette_app = Starlette(
            routes=[
                Route("/mcp", endpoint=handle_mcp, methods=["POST"]),
            ],
        )

        logger.info("Starting MCP server (streamable-http) on %s:%d/mcp", args.host, args.port)
        uvicorn.run(starlette_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
