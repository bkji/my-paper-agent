#!/bin/bash
# Co-Scientist MCP Server 실행
# 사용법:
#   ./run_mcp.sh              — stdio 모드 (Claude Desktop 등)
#   ./run_mcp.sh sse          — SSE 모드 (원격 접속, 포트 20032)
#   ./run_mcp.sh sse 8080     — SSE 모드 (지정 포트)

PYTHON="D:/WPy64-312101_paper/python/python.exe"
export PYTHONPATH="$(dirname "$0")"

if [ "$1" = "sse" ]; then
    PORT="${2:-20032}"
    $PYTHON mcp_server.py --transport sse --port "$PORT"
else
    $PYTHON mcp_server.py
fi
