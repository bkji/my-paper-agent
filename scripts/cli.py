"""CLI — 터미널에서 Agent를 테스트한다."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.supervisor import supervisor, AGENT_REGISTRY
from app.core.langfuse_client import init_langfuse, trace_attributes


async def run_agent(query: str, agent_type: str | None = None, filters: dict | None = None, user_id: str | None = None):
    init_langfuse()

    state = {
        "query": query,
        "user_id": user_id or "cli",
        "filters": filters,
        "metadata": {},
    }
    if agent_type:
        state["metadata"]["agent_type"] = agent_type

    with trace_attributes(user_id=state["user_id"], metadata={"agent_type": agent_type or "auto", "source": "cli"}):
        result = await supervisor.ainvoke(state)

    print(f"\n{'='*60}")
    print(f"Agent: {result.get('metadata', {}).get('agent_type', 'unknown')}")
    if result.get("filters"):
        print(f"Filters: {result['filters']}")
    print(f"{'='*60}")
    print(result.get("answer", "(no answer)"))

    sources = result.get("sources", [])
    if sources:
        print(f"\n--- Sources ({len(sources)}) ---")
        for s in sources[:5]:
            print(f"  [{s.get('score', 0):.4f}] {s.get('title', 'N/A')[:80]}")


async def interactive():
    init_langfuse()
    agent_type = None
    filters = None

    print("Co-Scientist Interactive CLI (type /quit to exit)")
    print("Commands: /agents, /use <agent>, /filter <json>, /clear, /quit\n")

    while True:
        try:
            user_input = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input == "/quit":
            break
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
            print("Cleared agent and filters")
            continue

        await run_agent(user_input, agent_type=agent_type, filters=filters)


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
