"""멀티턴 대화 테스트 — Python에서 supervisor를 직접 호출하는 예시.

서버는 stateless이므로, 매 턴마다 이전 대화 히스토리를 messages에 포함하여 전달한다.
Langfuse에서는 하나의 session_id로 대화 흐름을 추적할 수 있다.

사용법:
    D:/WPy64-312101_paper/python/python.exe scripts/test_multi_turn.py
    D:/WPy64-312101_paper/python/python.exe scripts/test_multi_turn.py -u "bkji"
"""
import argparse
import asyncio
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.langfuse_client import (
    init_langfuse, observe, trace_attributes, flush_langfuse, set_trace_io,
)
from app.agents.supervisor import supervisor


# 멀티턴 테스트 시나리오
CONVERSATION = [
    "OLED 관련 최신 논문 알려줘",
    "그 중에서 청색 발광 소재 관련 논문만 요약해줘",
    "해당 연구들의 트렌드를 분석해줘",
]


@observe(name="multi_turn_query")
async def call_agent(query: str, user_id: str, messages: list[dict], turn: int = 1):
    """supervisor를 직접 호출 — 이전 대화 히스토리 포함."""
    with trace_attributes(
        user_id=user_id,
        trace_name=f"test_multi_turn_t{turn}",
        metadata={"source": "script", "turn": str(turn)},
    ):
        set_trace_io(input={
            "query": query,
            "user_id": user_id,
            "turn": turn,
        })

        state = {
            "query": query,
            "user_id": user_id,
            "filters": {},
            "metadata": {},
        }
        # 이전 대화 히스토리를 metadata.messages에 전달 → supervisor.build_history에서 처리
        if messages:
            state["metadata"]["messages"] = messages

        result = await supervisor.ainvoke(state)

        answer = result.get("answer", "")
        agent_type = (result.get("metadata") or {}).get("agent_type")
        set_trace_io(output={
            "answer": answer[:500],
            "agent_type": agent_type,
        })
        return result


async def main(user_id: str, queries: list[str]):
    init_langfuse()

    session_id = f"session-{uuid.uuid4().hex[:8]}"
    messages: list[dict] = []  # 대화 히스토리 누적

    print(f"[세션] {session_id}")
    print(f"[사용자] {user_id}")
    print(f"[턴 수] {len(queries)}")
    print("=" * 60)

    for turn, query in enumerate(queries, 1):
        print(f"\n{'='*60}")
        print(f"[Turn {turn}] {query}")
        print("-" * 60)

        # 현재 사용자 질문을 히스토리에 추가
        messages.append({"role": "user", "content": query})

        result = await call_agent(query, user_id, messages, turn=turn)

        flush_langfuse()

        answer = result.get("answer", "")
        agent_type = (result.get("metadata") or {}).get("agent_type")

        # assistant 응답을 히스토리에 추가
        messages.append({"role": "assistant", "content": answer})

        print(f"[에이전트] {agent_type}")
        print(f"[답변]\n{answer[:300]}{'...' if len(answer) > 300 else ''}")

    print(f"\n{'='*60}")
    print(f"[완료] 총 {len(queries)}턴 대화 종료")
    print(f"[세션] {session_id}")
    print(f"[히스토리] {len(messages)}개 메시지")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="멀티턴 대화 테스트")
    parser.add_argument("-u", "--user", default="test_user", help="사용자 ID")
    parser.add_argument(
        "-q", "--queries", nargs="+",
        help="질문 목록 (미지정 시 기본 시나리오 사용)",
    )
    args = parser.parse_args()

    queries = args.queries or CONVERSATION
    asyncio.run(main(args.user, queries))
