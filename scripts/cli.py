"""CLI — 터미널에서 Agent를 테스트한다 (멀티턴 지원)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import os
import io

# Windows 콘솔 UTF-8 출력
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.supervisor import supervisor, AGENT_REGISTRY
from app.core.langfuse_client import init_langfuse, trace_attributes


async def run_agent(
    query: str,
    agent_type: str | None = None,
    filters: dict | None = None,
    user_id: str | None = None,
    messages: list[dict] | None = None,
) -> str:
    """에이전트를 실행하고 결과를 출력한다. 답변 텍스트를 반환한다."""
    init_langfuse()

    state = {
        "query": query,
        "user_id": user_id or "cli",
        "filters": filters,
        "metadata": {},
    }
    if agent_type:
        state["metadata"]["agent_type"] = agent_type
    if messages:
        state["metadata"]["messages"] = messages

    with trace_attributes(user_id=state["user_id"], metadata={"agent_type": agent_type or "auto", "source": "cli"}):
        result = await supervisor.ainvoke(state)

    print(f"\n{'='*60}")
    print(f"Agent: {result.get('metadata', {}).get('agent_type', 'unknown')}")
    if result.get("filters"):
        print(f"Filters: {result['filters']}")
    print(f"{'='*60}")

    answer = result.get("answer", "(no answer)")
    print(answer)

    sources = result.get("sources", [])
    if sources:
        print(f"\n--- Sources ({len(sources)}) ---")
        for s in sources[:5]:
            print(f"  [{s.get('score', 0):.4f}] {s.get('title', 'N/A')[:80]}")

    return answer


async def interactive():
    init_langfuse()
    agent_type = None
    filters = None
    messages: list[dict] = []

    print("Co-Scientist Interactive CLI (type /help for commands)")
    print(f"{'='*60}\n")

    while True:
        # 턴 수 표시
        turn = len([m for m in messages if m["role"] == "user"]) + 1 if messages else 1
        try:
            user_input = input(f"[턴 {turn}] >>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        # ── 명령어 처리 ──
        if user_input == "/quit":
            break

        if user_input == "/help":
            print("  /new            새 대화 시작 (히스토리 초기화)")
            print("  /history        현재 대화 히스토리 보기")
            print("  /agents         에이전트 목록 보기")
            print("  /use <agent>    에이전트 강제 지정")
            print("  /filter <json>  날짜 필터 설정")
            print("  /clear          에이전트 + 필터 + 히스토리 모두 초기화")
            print("  /quit           종료")
            continue

        if user_input == "/new":
            messages.clear()
            print("새 대화를 시작합니다.\n")
            continue

        if user_input == "/history":
            if not messages:
                print("  (대화 히스토리 없음)")
            else:
                for i, m in enumerate(messages):
                    role = "사용자" if m["role"] == "user" else "AI"
                    content = m["content"]
                    if len(content) > 80:
                        content = content[:77] + "..."
                    print(f"  [{i+1}] {role}: {content}")
            continue

        if user_input == "/agents":
            for name, info in AGENT_REGISTRY.items():
                print(f"  {name}: {info['description']}")
            continue

        if user_input.startswith("/use "):
            agent_type = user_input[5:].strip()
            print(f"Agent set to: {agent_type}")
            continue

        if user_input.startswith("/filter "):
            try:
                filters = json.loads(user_input[8:])
                print(f"Filters set to: {filters}")
            except json.JSONDecodeError:
                print("Invalid JSON")
            continue

        if user_input == "/clear":
            agent_type = None
            filters = None
            messages.clear()
            print("에이전트, 필터, 히스토리를 모두 초기화했습니다.\n")
            continue

        # ── 질문 실행 ──
        messages.append({"role": "user", "content": user_input})

        answer = await run_agent(
            user_input,
            agent_type=agent_type,
            filters=filters,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": answer})
        print()


def main():
    parser = argparse.ArgumentParser(description="Co-Scientist CLI")
    parser.add_argument("-q", "--query", help="Single query to run")
    parser.add_argument("-a", "--agent", help="Agent type to use")
    parser.add_argument("-f", "--filters", help="JSON filters")
    parser.add_argument("-l", "--list", action="store_true", help="List agents")
    args = parser.parse_args()

    if args.list:
        for name, info in AGENT_REGISTRY.items():
            print(f"  {name}: {info['description']}")
        return

    if args.query:
        filters = json.loads(args.filters) if args.filters else None
        asyncio.run(run_agent(args.query, agent_type=args.agent, filters=filters))
    else:
        asyncio.run(interactive())


if __name__ == "__main__":
    main()
