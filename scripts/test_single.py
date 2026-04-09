"""단일 질문 테스트 — Python에서 supervisor를 직접 호출하는 예시.

사용법:
    D:/WPy64-312101_paper/python/python.exe scripts/test_single.py
    D:/WPy64-312101_paper/python/python.exe scripts/test_single.py -q "OLED 최신 논문 알려줘"
    D:/WPy64-312101_paper/python/python.exe scripts/test_single.py -q "재작년 논문있어?" -u "bkji"
"""
import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.langfuse_client import (
    init_langfuse, observe, trace_attributes, flush_langfuse, set_trace_io,
)
from app.agents.supervisor import supervisor


@observe(name="single_query")
async def call_agent(query: str, user_id: str):
    """supervisor를 직접 호출하여 에이전트 실행."""
    set_trace_io(input={"query": query, "user_id": user_id})

    state = {
        "query": query,
        "user_id": user_id,
        "filters": {},
        "metadata": {},
    }
    result = await supervisor.ainvoke(state)

    answer = result.get("answer", "")
    sources = result.get("sources") or []
    agent_type = (result.get("metadata") or {}).get("agent_type")
    set_trace_io(output={
        "answer": answer[:500],
        "agent_type": agent_type,
        "source_count": len(sources),
    })
    return result


async def main(query: str, user_id: str):
    init_langfuse()

    print(f"[질문] {query}")
    print(f"[사용자] {user_id}")
    print("-" * 60)

    # trace_attributes를 @observe 바깥에서 설정해야 trace 속성이 올바르게 적용됨
    with trace_attributes(
        user_id=user_id,
        trace_name="test_single",
        metadata={"source": "script"},
    ):
        result = await call_agent(query, user_id)

    # @observe span이 닫힌 뒤에 flush (span 안에서 flush하면 trace 유실)
    flush_langfuse()

    answer = result.get("answer", "")
    sources = result.get("sources") or []
    agent_type = (result.get("metadata") or {}).get("agent_type")

    print(f"[에이전트] {agent_type}")
    print(f"[답변]\n{answer}")
    if sources:
        print(f"\n[참조 논문] {len(sources)}건")
        for i, s in enumerate(sources[:5], 1):
            title = s.get("title", "") if isinstance(s, dict) else getattr(s, "title", "")
            print(f"  {i}. {title}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="단일 질문 테스트")
    parser.add_argument("-q", "--query", default="재작년 논문있어?", help="질문")
    parser.add_argument("-u", "--user", default="test_user", help="사용자 ID")
    args = parser.parse_args()

    asyncio.run(main(args.query, args.user))
