"""폐쇄망용 에이전트 테스트 실행 스크립트.

agent_test_suite 테이블의 테스트를 실행하고 결과를 저장한다.
결과는 MariaDB(agent_test_results)와 JSON 파일에 모두 저장.

사용법:
  # 전체 실행
  python scripts/run_test_suite.py

  # 특정 에이전트만
  python scripts/run_test_suite.py --agent paper_qa

  # 특정 카테고리만
  python scripts/run_test_suite.py --category intent_check

  # 특정 에이전트 + 카테고리
  python scripts/run_test_suite.py --agent analytics --category date_filter

  # intent 분류만 테스트 (LLM 답변 생성 없이 빠르게)
  python scripts/run_test_suite.py --intent-only

  # 결과 비교 (이전 실행과 현재 비교)
  python scripts/run_test_suite.py --compare
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import io
import time
from datetime import datetime

import pymysql

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


# ── DB 연결 ──────────────────────────────────────────────────

def get_connection():
    return pymysql.connect(
        host=os.getenv("MARIADB_HOST"),
        port=int(os.getenv("MARIADB_PORT")),
        user=os.getenv("MARIADB_USER"),
        password=os.getenv("MARIADB_PASSWORD"),
        database=os.getenv("MARIADB_DATABASE"),
        charset="utf8mb4",
    )


def load_tests(agent=None, category=None):
    conn = get_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    sql = "SELECT * FROM agent_test_suite WHERE is_active = 1"
    params = []
    if agent:
        sql += " AND agent_type = %s"
        params.append(agent)
    if category:
        sql += " AND test_category = %s"
        params.append(category)
    sql += " ORDER BY test_id"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def ensure_results_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_test_results (
            result_id       INT AUTO_INCREMENT PRIMARY KEY,
            run_id          VARCHAR(30)   NOT NULL COMMENT '실행 ID (yyyymmdd_HHMMSS)',
            llm_model       VARCHAR(100),
            test_id         INT           NOT NULL,
            agent_type      VARCHAR(30)   COMMENT '기대 에이전트',
            actual_agent    VARCHAR(30)   COMMENT '실제 분류된 에이전트',
            agent_match     TINYINT       COMMENT '에이전트 분류 일치',
            test_category   VARCHAR(30),
            status          VARCHAR(10)   COMMENT 'PASS|FAIL|WARN|ERROR',
            query_text      TEXT,
            answer_text     TEXT,
            answer_len      INT,
            source_count    INT,
            elapsed_sec     FLOAT,
            filters_json    TEXT,
            keyword_hits    TEXT          COMMENT '매칭된 키워드 목록',
            keyword_score   FLOAT         COMMENT '키워드 매칭률 (0~1)',
            error_msg       TEXT,
            created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_run (run_id),
            INDEX idx_agent (agent_type),
            INDEX idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    conn.commit()
    cursor.close()
    conn.close()


# ── 테스트 실행 ──────────────────────────────────────────────

async def run_single_test(test: dict, idx: int, total: int, intent_only: bool = False) -> dict:
    """단일 테스트 실행."""
    from app.agents.supervisor import supervisor, extract_dates, classify_intent

    query = test["query_text"]
    start = time.time()

    # 멀티턴 대화 히스토리 복원
    messages = []
    if test.get("conversation_history"):
        try:
            messages = json.loads(test["conversation_history"])
        except (json.JSONDecodeError, TypeError):
            pass

    try:
        state = {
            "query": query,
            "user_id": "test_suite",
            "filters": {},
            "messages": messages,
            "metadata": {},
        }

        if intent_only:
            # intent 분류만 테스트 (빠름)
            state = await extract_dates(state)
            state = await classify_intent(state)
            actual_agent = state.get("metadata", {}).get("agent_type", "unknown")
            answer = ""
            sources = []
            filters = state.get("filters", {})
        else:
            # 전체 파이프라인 실행
            result = await supervisor.ainvoke(state)
            actual_agent = result.get("metadata", {}).get("agent_type", "unknown")
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            filters = result.get("filters", {})

        elapsed = time.time() - start

        # 에이전트 분류 일치 확인
        agent_match = actual_agent == test["agent_type"]

        # 키워드 매칭 체크
        keyword_hits = []
        keyword_score = 1.0
        if test.get("expected_keywords") and not intent_only:
            keywords = [k.strip() for k in test["expected_keywords"].split(",")]
            for kw in keywords:
                if kw.lower() in answer.lower():
                    keyword_hits.append(kw)
            keyword_score = len(keyword_hits) / len(keywords) if keywords else 1.0

        # 상태 판정
        if intent_only:
            status = "PASS" if agent_match else "FAIL"
        else:
            if not answer or len(answer) < 10:
                status = "FAIL"
            elif not agent_match:
                status = "WARN"
            elif keyword_score < 0.5:
                status = "WARN"
            else:
                status = "PASS"

        # 엣지케이스는 별도 판정
        if test["test_category"] == "edge_case":
            if answer and len(answer) > 10:
                status = "PASS"  # 에러 없이 답변 생성되면 통과

        label = f"[{idx+1}/{total}]"
        match_mark = "O" if agent_match else "X"
        print(f"{label} {status:5s} | {match_mark} {test['agent_type']:20s} → {actual_agent:20s} | "
              f"{elapsed:5.1f}s | {test['test_category']:15s} | {query[:45]}")

        return {
            "test_id": test["test_id"],
            "agent_type": test["agent_type"],
            "actual_agent": actual_agent,
            "agent_match": agent_match,
            "test_category": test["test_category"],
            "status": status,
            "query_text": query,
            "answer_text": answer,
            "answer_len": len(answer),
            "source_count": len(sources),
            "elapsed_sec": round(elapsed, 2),
            "filters_json": json.dumps(filters, ensure_ascii=False) if filters else None,
            "keyword_hits": ",".join(keyword_hits),
            "keyword_score": keyword_score,
            "error_msg": None,
        }

    except Exception as e:
        elapsed = time.time() - start
        print(f"[{idx+1}/{total}] ERROR | ? {test['agent_type']:20s} | "
              f"{elapsed:5.1f}s | {test['test_category']:15s} | {str(e)[:50]}")
        return {
            "test_id": test["test_id"],
            "agent_type": test["agent_type"],
            "actual_agent": "error",
            "agent_match": False,
            "test_category": test["test_category"],
            "status": "ERROR",
            "query_text": query,
            "answer_text": "",
            "answer_len": 0,
            "source_count": 0,
            "elapsed_sec": round(elapsed, 2),
            "filters_json": None,
            "keyword_hits": "",
            "keyword_score": 0,
            "error_msg": str(e)[:500],
        }


def save_results(results: list[dict], run_id: str):
    """결과를 MariaDB와 JSON에 저장."""
    conn = get_connection()
    cursor = conn.cursor()
    llm_model = os.getenv("LLM_MODEL", "unknown")

    for r in results:
        cursor.execute("""
            INSERT INTO agent_test_results
            (run_id, llm_model, test_id, agent_type, actual_agent, agent_match,
             test_category, status, query_text, answer_text, answer_len,
             source_count, elapsed_sec, filters_json, keyword_hits, keyword_score, error_msg)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            run_id, llm_model, r["test_id"], r["agent_type"], r["actual_agent"],
            1 if r["agent_match"] else 0,
            r["test_category"], r["status"], r["query_text"],
            r["answer_text"][:10000] if r["answer_text"] else None,
            r["answer_len"], r["source_count"], r["elapsed_sec"],
            r["filters_json"], r["keyword_hits"], r["keyword_score"],
            r["error_msg"],
        ))

    conn.commit()
    cursor.close()
    conn.close()

    # JSON 저장
    filename = f"_test_suite_{run_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump({
            "run_id": run_id,
            "llm_model": llm_model,
            "executed_at": datetime.now().isoformat(),
            "total": len(results),
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nJSON 저장: {filename}")


def print_summary(results: list[dict], run_id: str):
    """테스트 결과 요약 출력."""
    total = len(results)
    pass_cnt = sum(1 for r in results if r["status"] == "PASS")
    warn_cnt = sum(1 for r in results if r["status"] == "WARN")
    fail_cnt = sum(1 for r in results if r["status"] == "FAIL")
    err_cnt = sum(1 for r in results if r["status"] == "ERROR")
    match_cnt = sum(1 for r in results if r["agent_match"])
    total_time = sum(r["elapsed_sec"] for r in results)

    print(f"\n{'=' * 80}")
    print(f"테스트 결과 요약 (run_id: {run_id})")
    print(f"{'=' * 80}")
    print(f"LLM 모델: {os.getenv('LLM_MODEL', 'unknown')}")
    print(f"총 {total}건 | PASS: {pass_cnt} | WARN: {warn_cnt} | FAIL: {fail_cnt} | ERROR: {err_cnt}")
    print(f"Intent 분류 정확도: {match_cnt}/{total} ({match_cnt/total*100:.1f}%)")
    print(f"총 소요시간: {total_time:.1f}초 (평균 {total_time/total:.1f}초/건)")

    # 에이전트별 요약
    print(f"\n{'에이전트':<25s} {'총':>3s} {'PASS':>5s} {'WARN':>5s} {'FAIL':>5s} {'ERR':>4s} {'분류%':>6s}")
    print("-" * 55)
    agents = sorted(set(r["agent_type"] for r in results))
    for agent in agents:
        ar = [r for r in results if r["agent_type"] == agent]
        a_pass = sum(1 for r in ar if r["status"] == "PASS")
        a_warn = sum(1 for r in ar if r["status"] == "WARN")
        a_fail = sum(1 for r in ar if r["status"] == "FAIL")
        a_err = sum(1 for r in ar if r["status"] == "ERROR")
        a_match = sum(1 for r in ar if r["agent_match"])
        match_pct = a_match / len(ar) * 100 if ar else 0
        print(f"{agent:<25s} {len(ar):>3d} {a_pass:>5d} {a_warn:>5d} {a_fail:>5d} {a_err:>4d} {match_pct:>5.0f}%")

    # 카테고리별 요약
    print(f"\n{'카테고리':<20s} {'총':>3s} {'PASS':>5s} {'WARN':>5s} {'FAIL':>5s} {'ERR':>4s}")
    print("-" * 45)
    cats = sorted(set(r["test_category"] for r in results))
    for cat in cats:
        cr = [r for r in results if r["test_category"] == cat]
        c_pass = sum(1 for r in cr if r["status"] == "PASS")
        c_warn = sum(1 for r in cr if r["status"] == "WARN")
        c_fail = sum(1 for r in cr if r["status"] == "FAIL")
        c_err = sum(1 for r in cr if r["status"] == "ERROR")
        print(f"{cat:<20s} {len(cr):>3d} {c_pass:>5d} {c_warn:>5d} {c_fail:>5d} {c_err:>4d}")

    # 실패 목록
    failures = [r for r in results if r["status"] in ("FAIL", "ERROR")]
    if failures:
        print(f"\n실패/에러 목록:")
        for r in failures:
            err = f" ({r['error_msg'][:60]})" if r["error_msg"] else ""
            print(f"  [{r['status']}] {r['agent_type']} → {r['actual_agent']} | {r['query_text'][:55]}{err}")

    # 오분류 목록
    mismatches = [r for r in results if not r["agent_match"] and r["status"] != "ERROR"]
    if mismatches:
        print(f"\nIntent 오분류 목록:")
        for r in mismatches:
            print(f"  {r['agent_type']:20s} → {r['actual_agent']:20s} | {r['query_text'][:50]}")


def compare_runs():
    """최근 2회 실행 결과를 비교."""
    conn = get_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    cursor.execute("""
        SELECT DISTINCT run_id, llm_model, COUNT(*) cnt,
               SUM(agent_match) matches,
               SUM(CASE WHEN status='PASS' THEN 1 ELSE 0 END) passes,
               MIN(created_at) run_at
        FROM agent_test_results
        GROUP BY run_id, llm_model
        ORDER BY run_at DESC
        LIMIT 10
    """)
    runs = cursor.fetchall()

    if not runs:
        print("저장된 실행 결과가 없습니다.")
        cursor.close()
        conn.close()
        return

    print(f"\n{'=' * 80}")
    print("실행 결과 비교")
    print(f"{'=' * 80}")
    print(f"{'run_id':<20s} {'모델':<20s} {'총':>4s} {'PASS':>5s} {'분류%':>6s} {'실행시간':<20s}")
    print("-" * 80)
    for run in runs:
        match_pct = run["matches"] / run["cnt"] * 100 if run["cnt"] else 0
        print(f"{run['run_id']:<20s} {run['llm_model']:<20s} {run['cnt']:>4d} "
              f"{run['passes']:>5d} {match_pct:>5.1f}% {str(run['run_at']):<20s}")

    if len(runs) >= 2:
        latest = runs[0]["run_id"]
        prev = runs[1]["run_id"]
        print(f"\n최근 vs 이전: {latest} vs {prev}")

        # 에이전트별 비교
        cursor.execute("""
            SELECT r.agent_type,
                   SUM(CASE WHEN r.run_id=%s AND r.agent_match THEN 1 ELSE 0 END) latest_match,
                   SUM(CASE WHEN r.run_id=%s THEN 1 ELSE 0 END) latest_total,
                   SUM(CASE WHEN r.run_id=%s AND r.agent_match THEN 1 ELSE 0 END) prev_match,
                   SUM(CASE WHEN r.run_id=%s THEN 1 ELSE 0 END) prev_total
            FROM agent_test_results r
            WHERE r.run_id IN (%s, %s)
            GROUP BY r.agent_type
            ORDER BY r.agent_type
        """, (latest, latest, prev, prev, latest, prev))

        rows = cursor.fetchall()
        print(f"\n{'에이전트':<25s} {'최근':>10s} {'이전':>10s} {'변화':>6s}")
        print("-" * 55)
        for row in rows:
            l_pct = row["latest_match"] / row["latest_total"] * 100 if row["latest_total"] else 0
            p_pct = row["prev_match"] / row["prev_total"] * 100 if row["prev_total"] else 0
            diff = l_pct - p_pct
            sign = "+" if diff > 0 else ""
            print(f"{row['agent_type']:<25s} {l_pct:>9.0f}% {p_pct:>9.0f}% {sign}{diff:>5.1f}%")

    cursor.close()
    conn.close()


async def main():
    parser = argparse.ArgumentParser(description="폐쇄망용 에이전트 테스트 실행")
    parser.add_argument("--agent", type=str, help="특정 에이전트만 테스트 (예: paper_qa)")
    parser.add_argument("--category", type=str, help="특정 카테고리만 (intent_check|answer_quality|date_filter|multi_turn|edge_case)")
    parser.add_argument("--intent-only", action="store_true", help="intent 분류만 테스트 (답변 생성 없이)")
    parser.add_argument("--limit", type=int, default=0, help="테스트 건수 제한 (0=전체, 에이전트별 균등 샘플링)")
    parser.add_argument("--compare", action="store_true", help="이전 실행 결과와 비교")
    args = parser.parse_args()

    if args.compare:
        compare_runs()
        return

    ensure_results_table()

    tests = load_tests(agent=args.agent, category=args.category)

    # --limit: 에이전트별 균등 샘플링
    if args.limit and args.limit > 0 and len(tests) > args.limit:
        import random as _rnd
        _rnd.seed(42)
        # 에이전트별로 그룹핑 후 균등 배분
        by_agent = {}
        for t in tests:
            by_agent.setdefault(t["agent_type"], []).append(t)
        per_agent = max(1, args.limit // len(by_agent))
        sampled = []
        for agent_tests in by_agent.values():
            sampled.extend(_rnd.sample(agent_tests, min(per_agent, len(agent_tests))))
        # 부족분 랜덤 보충
        remaining = [t for t in tests if t not in sampled]
        if len(sampled) < args.limit and remaining:
            sampled.extend(_rnd.sample(remaining, min(args.limit - len(sampled), len(remaining))))
        tests = sampled[:args.limit]

    if not tests:
        print("실행할 테스트가 없습니다. agent_test_suite 테이블을 확인하세요.")
        return

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    llm_model = os.getenv("LLM_MODEL", "unknown")
    mode = "Intent 분류만" if args.intent_only else "전체 파이프라인"

    print(f"{'=' * 80}")
    print(f"Co-Scientist 에이전트 테스트 ({mode})")
    print(f"{'=' * 80}")
    print(f"Run ID    : {run_id}")
    print(f"LLM 모델  : {llm_model}")
    print(f"테스트 수  : {len(tests)}건")
    if args.agent:
        print(f"에이전트   : {args.agent}")
    if args.category:
        print(f"카테고리   : {args.category}")
    print(f"{'=' * 80}\n")

    results = []
    for i, test in enumerate(tests):
        r = await run_single_test(test, i, len(tests), intent_only=args.intent_only)
        results.append(r)

    # 결과 저장
    save_results(results, run_id)
    print_summary(results, run_id)

    print(f"\nMariaDB agent_test_results 테이블에 {len(results)}건 저장 완료")
    print(f"이전 결과와 비교하려면: python scripts/run_test_suite.py --compare")


if __name__ == "__main__":
    asyncio.run(main())
