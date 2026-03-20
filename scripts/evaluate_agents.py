"""qa_dataset 기반 에이전트 자동 평가 스크립트.

평가 항목:
1. 날짜 파싱 정확도 (date_parser → 기대값 비교)
2. Intent 분류 정확도 (supervisor → agent_type 비교)
3. 필터 적용 정확도 (filters → expected_filters 비교)
4. 전체 파이프라인 응답 여부 (answer 생성 성공/실패)
"""
import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from collections import Counter, defaultdict

import pymysql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from app.core.date_parser import extract_date_filters
from app.core.langfuse_client import init_langfuse

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REF_DT = datetime(2026, 3, 20)


def load_qa_dataset(limit=None):
    conn = pymysql.connect(
        host=os.getenv("MARIADB_HOST"), port=int(os.getenv("MARIADB_PORT")),
        user=os.getenv("MARIADB_USER"), password=os.getenv("MARIADB_PASSWORD"),
        database=os.getenv("MARIADB_DATABASE"), charset="utf8mb4",
    )
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    sql = "SELECT * FROM qa_dataset ORDER BY qa_id"
    if limit:
        sql += f" LIMIT {limit}"
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def evaluate_date_parsing(rows):
    """날짜 파싱 정확도 평가."""
    total = passed = failed = skipped = 0
    failures_by_type = defaultdict(list)

    for row in rows:
        if row["date_type"] == "D0" or not row["date_expression"]:
            skipped += 1
            continue
        total += 1

        result = extract_date_filters(row["date_expression"], reference_date=REF_DT)
        expected_from = row.get("parsed_from")
        expected_to = row.get("parsed_to")

        if result is None:
            failed += 1
            failures_by_type[row["date_type"]].append(
                f'"{row["date_expression"]}" => None (expected {expected_from}~{expected_to})'
            )
            continue

        actual_from = result.get("coverdate_from")
        actual_to = result.get("coverdate_to")

        if actual_from == expected_from and actual_to == expected_to:
            passed += 1
        else:
            failed += 1
            failures_by_type[row["date_type"]].append(
                f'"{row["date_expression"]}" => {actual_from}~{actual_to} (expected {expected_from}~{expected_to})'
            )

    return {
        "total": total, "passed": passed, "failed": failed, "skipped": skipped,
        "rate": (passed / total * 100) if total > 0 else 0,
        "failures_by_type": dict(failures_by_type),
    }


async def evaluate_intent_classification(rows, sample_size=100):
    """Intent 분류 정확도 평가 (LLM 호출 포함, 샘플링)."""
    from app.agents.supervisor import supervisor

    import random
    random.seed(42)
    sampled = random.sample(rows, min(sample_size, len(rows)))

    total = correct = wrong = error_count = 0
    confusion = defaultdict(Counter)  # confusion[expected][actual] = count

    for row in sampled:
        total += 1
        expected_type = row["agent_type"]
        query = row["query_text"]

        try:
            state = {
                "query": query,
                "user_id": "eval",
                "filters": {},
                "metadata": {},
            }
            # extract_dates + classify_intent만 실행 (route_to_agent 제외)
            from app.agents.supervisor import extract_dates, classify_intent
            state = await extract_dates(state)
            state = await classify_intent(state)

            actual_type = state.get("metadata", {}).get("agent_type", "unknown")

            if actual_type == expected_type:
                correct += 1
            else:
                wrong += 1
            confusion[expected_type][actual_type] += 1

        except Exception as e:
            error_count += 1
            logger.warning("Intent eval error for qa_id=%s: %s", row.get("qa_id"), e)

    return {
        "total": total, "correct": correct, "wrong": wrong, "errors": error_count,
        "accuracy": (correct / total * 100) if total > 0 else 0,
        "confusion": {k: dict(v) for k, v in confusion.items()},
    }


async def evaluate_filter_accuracy(rows, sample_size=50):
    """필터 적용 정확도: date_parser → expected_filters 비교."""
    total = correct = wrong = skipped = 0

    for row in rows[:sample_size]:
        expected_filters_str = row.get("expected_filters")
        if not expected_filters_str:
            skipped += 1
            continue

        try:
            expected = json.loads(expected_filters_str)
        except (json.JSONDecodeError, TypeError):
            skipped += 1
            continue

        total += 1
        query = row["query_text"]

        date_result = extract_date_filters(query, reference_date=REF_DT)
        actual_filters = {}
        if date_result:
            actual_filters = date_result

        # author 등 다른 필터는 현재 자동 추출 안 함 → 날짜 필터만 비교
        expected_dates = {
            k: v for k, v in expected.items()
            if k in ("coverdate_from", "coverdate_to")
        }
        actual_dates = {
            k: v for k, v in actual_filters.items()
            if k in ("coverdate_from", "coverdate_to")
        }

        if expected_dates == actual_dates:
            correct += 1
        else:
            wrong += 1

    return {
        "total": total, "correct": correct, "wrong": wrong, "skipped": skipped,
        "accuracy": (correct / total * 100) if total > 0 else 0,
    }


async def evaluate_e2e_pipeline(rows, sample_size=10):
    """E2E 파이프라인: supervisor 전체 실행 → 답변 생성 여부."""
    from app.agents.supervisor import supervisor

    import random
    random.seed(42)
    sampled = random.sample(rows, min(sample_size, len(rows)))

    total = success = no_answer = error_count = 0
    results_detail = []

    for row in sampled:
        total += 1
        try:
            state = {
                "query": row["query_text"],
                "user_id": "eval",
                "filters": {},
                "metadata": {},
            }
            result = await supervisor.ainvoke(state)
            answer = result.get("answer", "")
            agent = result.get("metadata", {}).get("agent_type", "?")
            filters = result.get("filters")

            if answer and len(answer) > 10:
                success += 1
                status = "OK"
            else:
                no_answer += 1
                status = "NO_ANSWER"

            results_detail.append({
                "qa_id": row.get("qa_id"),
                "query": row["query_text"][:80],
                "expected_agent": row["agent_type"],
                "actual_agent": agent,
                "filters": filters,
                "answer_len": len(answer),
                "status": status,
            })

        except Exception as e:
            error_count += 1
            results_detail.append({
                "qa_id": row.get("qa_id"),
                "query": row["query_text"][:80],
                "expected_agent": row["agent_type"],
                "actual_agent": "ERROR",
                "status": f"ERROR: {e}",
            })

    return {
        "total": total, "success": success, "no_answer": no_answer, "errors": error_count,
        "success_rate": (success / total * 100) if total > 0 else 0,
        "details": results_detail,
    }


async def main():
    init_langfuse()

    print("=" * 60)
    print("Co-Scientist Agent 평가")
    print("=" * 60)

    # 데이터 로드
    rows = load_qa_dataset()
    print(f"\nqa_dataset: {len(rows)}건 로드")

    # 1. 날짜 파싱
    print("\n" + "-" * 40)
    print("1. 날짜 파싱 정확도")
    date_result = evaluate_date_parsing(rows)
    print(f"   총 {date_result['total']}건 (D0 제외 {date_result['skipped']}건)")
    print(f"   통과: {date_result['passed']}건 / 실패: {date_result['failed']}건")
    print(f"   정확도: {date_result['rate']:.1f}%")
    if date_result["failures_by_type"]:
        for dt, fails in date_result["failures_by_type"].items():
            print(f"   [{dt}] 실패 {len(fails)}건:")
            for f in fails[:3]:
                print(f"     - {f}")

    # 2. Intent 분류 (LLM 호출, 100건 샘플)
    print("\n" + "-" * 40)
    print("2. Intent 분류 정확도 (100건 샘플)")
    intent_result = await evaluate_intent_classification(rows, sample_size=100)
    print(f"   총 {intent_result['total']}건")
    print(f"   정확: {intent_result['correct']}건 / 오분류: {intent_result['wrong']}건 / 에러: {intent_result['errors']}건")
    print(f"   정확도: {intent_result['accuracy']:.1f}%")
    # 주요 오분류
    if intent_result["confusion"]:
        print("   주요 오분류:")
        for expected, actuals in sorted(intent_result["confusion"].items()):
            for actual, cnt in sorted(actuals.items(), key=lambda x: -x[1]):
                if actual != expected and cnt > 0:
                    print(f"     {expected} → {actual}: {cnt}건")

    # 3. 필터 정확도
    print("\n" + "-" * 40)
    print("3. 필터 적용 정확도")
    filter_result = await evaluate_filter_accuracy(rows, sample_size=200)
    print(f"   총 {filter_result['total']}건 (필터 없는 건 제외 {filter_result['skipped']}건)")
    print(f"   정확: {filter_result['correct']}건 / 불일치: {filter_result['wrong']}건")
    print(f"   정확도: {filter_result['accuracy']:.1f}%")

    # 4. E2E 파이프라인 (10건 샘플)
    print("\n" + "-" * 40)
    print("4. E2E 파이프라인 (10건 샘플)")
    e2e_result = await evaluate_e2e_pipeline(rows, sample_size=10)
    print(f"   총 {e2e_result['total']}건")
    print(f"   성공: {e2e_result['success']}건 / 응답 없음: {e2e_result['no_answer']}건 / 에러: {e2e_result['errors']}건")
    print(f"   성공률: {e2e_result['success_rate']:.1f}%")
    for d in e2e_result["details"]:
        status = d["status"]
        print(f"   [{status}] {d['expected_agent']}→{d['actual_agent']} | {d['query']}")

    # 결과 저장
    report = {
        "evaluated_at": datetime.now().isoformat(),
        "dataset_size": len(rows),
        "date_parsing": date_result,
        "intent_classification": intent_result,
        "filter_accuracy": filter_result,
        "e2e_pipeline": e2e_result,
    }
    with open("_eval_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n평가 보고서 저장: _eval_report.json")


if __name__ == "__main__":
    asyncio.run(main())
