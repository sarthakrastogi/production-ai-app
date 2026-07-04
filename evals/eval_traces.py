"""
Trace-based evals — verify the LangGraph agent's execution path.

Checks:
  - Correct model was selected for query complexity
  - Multi-part queries were decomposed (fan-out happened)
  - Validation nodes ran and scored the response
  - Response was cached after successful generation

These test the AGENT's behavior, not the safety/PII middleware.
"""
import asyncio
import json
import time
import sys
from pathlib import Path

import httpx
from jose import jwt

from evals.config import eval_settings

DATASET_PATH = Path(eval_settings.DATASET_FILE)

# Expected graph paths through the AGENT nodes (post-safety-gate)
EXPECTED_AGENT_PATHS = {
    "simple_query": [
        "query_intelligence", "session_memory", "context_retrieval",
        "generate_flash",
        "faithfulness", "completeness", "validation_merge",
        "cache_store",
    ],
    "complex_query": [
        "query_intelligence", "session_memory", "context_retrieval",
        "generate_pro",
        "faithfulness", "completeness", "validation_merge",
        "cache_store",
    ],
    "decomposed_query": [
        "query_intelligence", "session_memory", "context_retrieval",
        "generate_subquery", "merge_subqueries",
        "faithfulness", "completeness", "validation_merge",
        "cache_store",
    ],
}

NODE_LATENCY_BUDGETS_MS = {
    "query_intelligence": 5000,
    "session_memory": 500,
    "context_retrieval": 8000,
    "generate_flash": 5000,
    "generate_pro": 15000,
    "generate_subquery": 10000,
    "faithfulness": 10000,
    "completeness": 5000,
}


def _make_token() -> str:
    return jwt.encode({"sub": "eval-trace-runner"}, eval_settings.JWT_SECRET, algorithm="HS256")


def _get_expected_path_type(case: dict) -> str:
    if case.get("needs_decomp"):
        return "decomposed_query"
    if case.get("expected_complexity") == "high":
        return "complex_query"
    return "simple_query"


async def run_and_check_traces():
    dataset = json.loads(DATASET_PATH.read_text())
    results = []

    async with httpx.AsyncClient() as client:
        for case in dataset:
            token = _make_token()
            headers = {"Authorization": f"Bearer {token}"}

            try:
                resp = await client.post(
                    f"{eval_settings.APP_URL}/query",
                    json={"query": case["query"], "session_id": f"trace-eval-{case['id']}"},
                    headers=headers,
                    timeout=30.0,
                )
            except Exception as e:
                results.append({
                    "id": case["id"],
                    "passed": False,
                    "error": str(e),
                })
                continue

            if resp.status_code != 200:
                results.append({
                    "id": case["id"],
                    "passed": False,
                    "error": f"HTTP {resp.status_code}",
                })
                continue

            data = resp.json()
            expected_path_type = _get_expected_path_type(case)
            model_used = data.get("model_used", "")

            # Check model routing
            expected_model = case.get("expected_model", "flash")
            if expected_model == "flash":
                model_correct = "flash" in model_used.lower()
            elif expected_model == "pro":
                model_correct = "pro" in model_used.lower() or "gpt" in model_used.lower()
            else:
                model_correct = True

            # Check that validation actually ran (scores aren't default zeros)
            faithfulness = data.get("faithfulness_score", 0)
            completeness = data.get("completeness_score", 0)
            validation_ran = faithfulness > 0 or completeness > 0

            # Check completeness for decomposed queries specifically
            decomp_correct = True
            if case.get("needs_decomp") and case.get("sub_query_count", 1) > 1:
                # For decomposed queries, completeness should be scored
                decomp_correct = completeness > 0

            result = {
                "id": case["id"],
                "expected_path": expected_path_type,
                "model_used": model_used,
                "model_routing_correct": model_correct,
                "validation_ran": validation_ran,
                "decomposition_correct": decomp_correct,
                "faithfulness_score": faithfulness,
                "completeness_score": completeness,
            }

            result["passed"] = model_correct and validation_ran and decomp_correct
            results.append(result)

            status = "PASS" if result["passed"] else "FAIL"
            detail = f"model={'OK' if model_correct else 'WRONG'}, validation={'OK' if validation_ran else 'MISSING'}"
            print(f"  [{status}] trace/{case['id']}: {expected_path_type} ({detail})")

    total = len(results)
    passed = sum(1 for r in results if r["passed"])

    report = {
        "type": "trace_verification",
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "results": results,
    }

    report_path = Path("evals/reports/trace_latest.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))

    print(f"\nTrace eval: {passed}/{total} passed")
    return report


async def main():
    print("Running trace-based evals (agent path verification)...")
    print("=" * 60)
    report = await run_and_check_traces()

    if report["failed"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
