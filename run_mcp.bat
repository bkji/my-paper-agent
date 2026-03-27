@echo off
REM Co-Scientist MCP Server 실행
REM 사용법:
REM   run_mcp.bat              — stdio 모드 (Claude Desktop 등)
REM   run_mcp.bat sse          — SSE 모드 (원격 접속, 포트 20032)
REM   run_mcp.bat sse 8080     — SSE 모드 (지정 포트)

set PYTHON=D:\WPy64-312101_paper\python\python.exe
set PYTHONPATH=%~dp0

if "%1"=="sse" (
    if "%2"=="" (
        %PYTHON% mcp_server.py --transport sse --port 20032
    ) else (
        %PYTHON% mcp_server.py --transport sse --port %2
    )
) else (
    %PYTHON% mcp_server.py
)
