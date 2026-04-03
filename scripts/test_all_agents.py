"""전체 에이전트 종합 테스트 — 14개 에이전트 + 멀티턴 + 엣지케이스 테스트."""
from __future__ import annotations

import asyncio
import json
import sys
import os
import io
import time
import mariadb
from datetime import datetime
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from app.agents.supervisor import supervisor

# ============================================================
# 테스트 케이스 정의
# ============================================================
TEST_CASES = [
    # === Phase 1 ===
    # analytics - 편수/목록
    {"agent": "analytics", "query": "2024년 10월 발표된 논문 편수와 제목을 보여줘", "category": "analytics_list"},
    {"agent": "analytics", "query": "전체 논문 몇 편이야?", "category": "analytics_count"},
    {"agent": "analytics", "query": "2024년 12월 논문 목록 보여줘", "category": "analytics_list_dec"},
    {"agent": "analytics", "query": "연도별 논문 편수 추이를 보여줘", "category": "analytics_trend"},
    {"agent": "analytics", "query": "holographic 관련 논문 있어?", "category": "analytics_keyword"},

    # paper_qa - 논문 내용 질문
    {"agent": "paper_qa", "query": "Micro LED 결함 검출 방법에 대해 알려줘", "category": "paper_qa_tech"},
    {"agent": "paper_qa", "query": "foveated rendering이란 무엇인가?", "category": "paper_qa_concept"},
    {"agent": "paper_qa", "query": "OLED 발광 효율을 높이는 방법은?", "category": "paper_qa_method"},

    # paper_qa - 특정 논문 원문 기반
    {"agent": "paper_qa", "query": "Subjective assessment of visual fidelity 논문을 요약해줘", "category": "paper_qa_summary"},
    {"agent": "paper_qa", "query": "High-speed and contactless inspection of defective micro-LEDs 논문의 핵심 기여는?", "category": "paper_qa_fulltext"},

    # literature_survey
    {"agent": "literature_survey", "query": "디스플레이 기술의 최근 연구 동향을 정리해줘", "category": "lit_survey"},

    # paper_deep_dive
    {"agent": "paper_deep_dive", "query": "Wide-viewing-angle dual-view integral imaging display 논문을 심층 분석해줘", "category": "deep_dive"},

    # === Phase 2 ===
    # idea_generator
    {"agent": "idea_generator", "query": "Micro LED와 holographic grating을 결합한 새로운 연구 아이디어를 제안해줘", "category": "idea_gen"},

    # cross_domain
    {"agent": "cross_domain", "query": "의료 영상 기술을 디스플레이 분야에 적용할 수 있는 방법은?", "category": "cross_domain"},

    # trend_analyzer
    {"agent": "trend_analyzer", "query": "Micro LED 기술의 발전 트렌드를 분석해줘", "category": "trend"},

    # === Phase 3 ===
    # experiment_planner
    {"agent": "experiment_planner", "query": "OLED 발광층 효율 개선을 위한 실험 설계를 제안해줘", "category": "exp_plan"},

    # material_advisor
    {"agent": "material_advisor", "query": "Micro LED용 발광 소재를 비교 분석해줘", "category": "material"},

    # patent_landscaper
    {"agent": "patent_landscaper", "query": "홀로그래픽 디스플레이 관련 특허 동향을 분석해줘", "category": "patent"},

    # competitive_intel
    {"agent": "competitive_intel", "query": "삼성과 LG의 디스플레이 기술 경쟁 현황을 분석해줘", "category": "comp_intel"},

    # === Phase 4 ===
    # report_drafter
    {"agent": "report_drafter", "query": "2024년 디스플레이 기술 동향 보고서 초안을 작성해줘", "category": "report"},

    # peer_review
    {"agent": "peer_review", "query": "Wide-viewing-angle dual-view integral imaging display 논문을 리뷰해줘", "category": "peer_review"},

    # knowledge_connector
    {"agent": "knowledge_connector", "query": "foveated rendering 분야 전문가를 추천해줘", "category": "knowledge"},

    # === 날짜 파싱 테스트 ===
    {"agent": "analytics", "query": "최근 6개월 논문 편수 알려줘", "category": "date_relative"},
    {"agent": "analytics", "query": "2024년 하반기 논문 목록", "category": "date_range"},

    # === 엣지케이스 ===
    {"agent": "paper_qa", "query": "존재하지 않는 XYZ 기술에 대해 알려줘", "category": "edge_not_found"},
    {"agent": "analytics", "query": "2020년 논문 있어?", "category": "edge_no_data"},
]


async def run_test(case: dict, idx: int, total: int) -> dict:
    """테스트 케이스를 실행하고 결과를 반환한다."""
    query = case["query"]
    start = time.time()

    try:
        state = {
            "query": query,
            "user_id": "test_all_agents",
            "filters": {},
            "metadata": {},
        }
        result = await supervisor.ainvoke(state)

        elapsed = time.time() - start
        agent_type = result.get("metadata", {}).get("agent_type", "unknown")
        answer = result.get("answer", "")
        filters = result.get("filters") or {}
        sources = result.get("sources", [])

        status = "PASS" if answer and len(answer) > 10 else "FAIL"
        if "찾지 못했습니다" in answer or "찾을 수 없습니다" in answer:
            if case["category"] in ("edge_not_found", "edge_no_data"):
                status = "PASS"  # 예상된 결과
            else:
                status = "WARN"

        print(f"[{idx+1}/{total}] {status} | {agent_type:20s} | {elapsed:5.1f}s | {case['category']:20s} | {query[:50]}")
        if status != "PASS":
            print(f"         Answer: {answer[:100]}")

        return {
            "status": status,
            "expected_agent": case["agent"],
            "actual_agent": agent_type,
            "query": query,
            "answer": answer,
            "category": case["category"],
            "elapsed": elapsed,
            "filters": filters,
            "source_count": len(sources),
            "answer_len": len(answer),
            "agent_match": agent_type == case["agent"],
        }

    except Exception as e:
        elapsed = time.time() - start
        print(f"[{idx+1}/{total}] ERROR | {'?':20s} | {elapsed:5.1f}s | {case['category']:20s} | {str(e)[:80]}")
        return {
            "status": "ERROR",
            "expected_agent": case["agent"],
            "actual_agent": "error",
            "query": query,
            "answer": str(e),
            "category": case["category"],
            "elapsed": elapsed,
            "filters": {},
            "source_count": 0,
            "answer_len": 0,
            "agent_match": False,
        }


def save_results_to_mariadb(results: list[dict]):
    """테스트 결과를 MariaDB qa_test_results 테이블에 저장한다."""
    conn = mariadb.connect(
        host=os.getenv("MARIADB_HOST", "localhost"),
        port=int(os.getenv("MARIADB_PORT", "3306")),
        user=os.getenv("MARIADB_USER"),
        password=os.getenv("MARIADB_PASSWORD"),
        database=os.getenv("MARIADB_DATABASE", "paper"),
    )
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS qa_test_results (
            test_id INT AUTO_INCREMENT PRIMARY KEY,
            test_run_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            llm_model VARCHAR(100),
            category VARCHAR(50),
            expected_agent VARCHAR(30),
            actual_agent VARCHAR(30),
            agent_match TINYINT,
            status VARCHAR(10),
            query_text TEXT,
            answer_text TEXT,
            answer_len INT,
            source_count INT,
            elapsed_sec FLOAT,
            filters_json TEXT,
            INDEX idx_test_run (test_run_at),
            INDEX idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    llm_model = os.getenv("LLM_MODEL", "unknown")
    run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for r in results:
        cursor.execute("""
            INSERT INTO qa_test_results
            (test_run_at, llm_model, category, expected_agent, actual_agent,
             agent_match, status, query_text, answer_text, answer_len,
             source_count, elapsed_sec, filters_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_at, llm_model, r["category"], r["expected_agent"], r["actual_agent"],
            1 if r["agent_match"] else 0, r["status"], r["query"],
            r["answer"][:10000], r["answer_len"],
            r["source_count"], round(r["elapsed"], 2),
            json.dumps(r["filters"], ensure_ascii=False),
        ))

    conn.commit()
    count = len(results)
    cursor.close()
    conn.close()
    print(f"\nMariaDB qa_test_results에 {count}건 저장 완료")


async def main():
    total = len(TEST_CASES)
    print(f"=" * 80)
    print(f"Co-Scientist 전체 에이전트 테스트 ({total}건)")
    print(f"LLM: {os.getenv('LLM_MODEL', 'unknown')}")
    print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"=" * 80)

    results = []
    for i, case in enumerate(TEST_CASES):
        r = await run_test(case, i, total)
        results.append(r)

    # 요약
    print(f"\n{'=' * 80}")
    print("테스트 요약")
    print(f"{'=' * 80}")

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    warn_count = sum(1 for r in results if r["status"] == "WARN")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    error_count = sum(1 for r in results if r["status"] == "ERROR")
    agent_match = sum(1 for r in results if r["agent_match"])
    total_time = sum(r["elapsed"] for r in results)

    print(f"PASS: {pass_count}/{total}  WARN: {warn_count}  FAIL: {fail_count}  ERROR: {error_count}")
    print(f"Intent 분류 정확도: {agent_match}/{total} ({agent_match/total*100:.0f}%)")
    print(f"총 소요시간: {total_time:.1f}초 (평균 {total_time/total:.1f}초/건)")

    # 실패 목록
    failures = [r for r in results if r["status"] in ("FAIL", "ERROR")]
    if failures:
        print(f"\n실패 목록:")
        for r in failures:
            print(f"  [{r['status']}] {r['category']}: {r['query'][:60]}")

    # MariaDB 저장
    save_results_to_mariadb(results)

    # JSON 결과 파일 저장
    os.makedirs("output", exist_ok=True)
    with open("output/_test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("output/_test_results.json 저장 완료")


if __name__ == "__main__":
    asyncio.run(main())
