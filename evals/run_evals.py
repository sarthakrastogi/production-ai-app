"""
Eval runner for the AI support bot CI/CD pipeline.

Tests the LangGraph agent's behavior:
  - Response quality (faithfulness & completeness scores)
  - Model routing (did it pick the right model for complexity?)
  - Query decomposition (did multi-part queries get split correctly?)
  - Latency per query
  - Token usage / cost estimates

Outputs a JSON report and compares against baseline if available.
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
BASELINE_PATH = Path(eval_settings.BASELINE_FILE)

TOKEN_COST_PER_1K = {
    "gemini-3.5-flash": 0.0001,
    "gemini-3.1-pro": 0.007,
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.00015,
}


def _make_token(user_id: str = "eval-runner") -> str:
    return jwt.encode({"sub": user_id}, eval_settings.JWT_SECRET, algorithm="HS256")


async def run_single_eval(client: httpx.AsyncClient, case: dict) -> dict:
    token = _make_token()
    headers = {"Authorization": f"Bearer {token}"}

    start = time.perf_counter()
    try:
        resp = await client.post(
            f"{eval_settings.APP_URL}/query",
            json={"query": case["query"], "session_id": f"eval-{case['id']}"},
            headers=headers,
            timeout=eval_settings.EVAL_TIMEOUT_MS / 1000,
        )
        latency_ms = (time.perf_counter() - start) * 1000

        if resp.status_code != 200:
            return {
                "id": case["id"],
                "passed": False,
                "latency_ms": latency_ms,
                "error": f"HTTP {resp.status_code}: {resp.text}",
            }

        data = resp.json()

    except httpx.TimeoutException:
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "id": case["id"],
            "passed": False,
            "latency_ms": latency_ms,
            "error": "Timeout",
        }
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "id": case["id"],
            "passed": False,
            "latency_ms": latency_ms,
            "error": str(e),
        }

    result = {
        "id": case["id"],
        "latency_ms": round(latency_ms, 2),
        "model_used": data.get("model_used", "unknown"),
        "faithfulness_score": data.get("faithfulness_score", 0),
        "completeness_score": data.get("completeness_score", 0),
        "validation_passed": data.get("validation_passed", False),
        "response_length": len(data.get("response", "")),
    }

    # --- Check: Latency ---
    max_latency = case.get("max_latency_ms", 15000)
    latency_ok = latency_ms <= max_latency

    # --- Check: Faithfulness (is the response grounded in retrieved context?) ---
    faith_ok = result["faithfulness_score"] >= eval_settings.FAITHFULNESS_THRESHOLD

    # --- Check: Completeness (did it answer all sub-questions?) ---
    comp_ok = result["completeness_score"] >= eval_settings.COMPLETENESS_THRESHOLD

    # --- Check: Model routing (did it use the right model?) ---
    expected_model = case.get("expected_model")
    model_used = result["model_used"]
    if expected_model == "flash":
        model_ok = "flash" in model_used.lower()
    elif expected_model == "pro":
        model_ok = "pro" in model_used.lower() or "gpt" in model_used.lower()
    else:
        model_ok = True

    # --- Estimate token cost ---
    estimated_tokens = (len(case["query"]) + result["response_length"]) / 4
    cost_per_1k = TOKEN_COST_PER_1K.get(model_used, 0.001)
    result["estimated_cost_usd"] = round((estimated_tokens / 1000) * cost_per_1k, 6)
    result["estimated_tokens"] = int(estimated_tokens)

    result["checks"] = {
        "latency": latency_ok,
        "faithfulness": faith_ok,
        "completeness": comp_ok,
        "model_routing": model_ok,
    }
    result["passed"] = all(result["checks"].values())

    return result


async def run_all_evals() -> dict:
    dataset = json.loads(DATASET_PATH.read_text())
    results = []

    async with httpx.AsyncClient() as client:
        for case in dataset:
            result = await run_single_eval(client, case)
            results.append(result)
            status = "PASS" if result.get("passed") else "FAIL"
            print(f"  [{status}] {result['id']} ({result.get('latency_ms', 0):.0f}ms)")

    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    total_latency = sum(r.get("latency_ms", 0) for r in results)
    total_cost = sum(r.get("estimated_cost_usd", 0) for r in results)

    report = {
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total, 3) if total else 0,
            "avg_latency_ms": round(total_latency / total, 2) if total else 0,
            "total_estimated_cost_usd": round(total_cost, 6),
            "p95_latency_ms": round(
                sorted(r.get("latency_ms", 0) for r in results)[int(total * 0.95)] if total else 0, 2
            ),
        },
        "results": results,
    }

    return report


def compare_with_baseline(report: dict) -> dict:
    if not BASELINE_PATH.exists():
        return {"baseline_available": False, "regressions": []}

    baseline = json.loads(BASELINE_PATH.read_text())
    regressions = []

    baseline_summary = baseline.get("summary", {})
    current_summary = report["summary"]

    # Latency regression
    baseline_latency = baseline_summary.get("avg_latency_ms", 0)
    if baseline_latency > 0:
        latency_change = (current_summary["avg_latency_ms"] - baseline_latency) / baseline_latency
        if latency_change > eval_settings.LATENCY_REGRESSION_THRESHOLD:
            regressions.append({
                "metric": "avg_latency_ms",
                "baseline": baseline_latency,
                "current": current_summary["avg_latency_ms"],
                "change_pct": round(latency_change * 100, 1),
                "threshold_pct": eval_settings.LATENCY_REGRESSION_THRESHOLD * 100,
            })

    # Cost regression
    baseline_cost = baseline_summary.get("total_estimated_cost_usd", 0)
    if baseline_cost > 0:
        cost_change = (current_summary["total_estimated_cost_usd"] - baseline_cost) / baseline_cost
        if cost_change > eval_settings.COST_REGRESSION_THRESHOLD:
            regressions.append({
                "metric": "total_estimated_cost_usd",
                "baseline": baseline_cost,
                "current": current_summary["total_estimated_cost_usd"],
                "change_pct": round(cost_change * 100, 1),
                "threshold_pct": eval_settings.COST_REGRESSION_THRESHOLD * 100,
            })

    # Pass rate regression (any drop is a regression)
    baseline_pass_rate = baseline_summary.get("pass_rate", 0)
    if current_summary["pass_rate"] < baseline_pass_rate:
        regressions.append({
            "metric": "pass_rate",
            "baseline": baseline_pass_rate,
            "current": current_summary["pass_rate"],
            "change_pct": round(
                (current_summary["pass_rate"] - baseline_pass_rate) * 100, 1
            ),
        })

    # Per-case regressions
    baseline_results = {r["id"]: r for r in baseline.get("results", [])}
    for result in report["results"]:
        case_id = result["id"]
        if case_id in baseline_results:
            prev = baseline_results[case_id]
            if prev.get("passed") and not result.get("passed"):
                regressions.append({
                    "metric": f"case_{case_id}_regression",
                    "detail": "Previously passing case now fails",
                    "current_checks": result.get("checks", {}),
                })

    return {
        "baseline_available": True,
        "regressions": regressions,
        "has_regressions": len(regressions) > 0,
    }


async def main():
    print("Running eval suite...")
    print("=" * 60)

    report = await run_all_evals()

    print("=" * 60)
    print(f"\nResults: {report['summary']['passed']}/{report['summary']['total']} passed")
    print(f"Avg latency: {report['summary']['avg_latency_ms']:.0f}ms")
    print(f"P95 latency: {report['summary']['p95_latency_ms']:.0f}ms")
    print(f"Estimated cost: ${report['summary']['total_estimated_cost_usd']:.4f}")

    # Compare with baseline
    comparison = compare_with_baseline(report)
    report["baseline_comparison"] = comparison

    if comparison.get("has_regressions"):
        print("\n!! REGRESSIONS DETECTED:")
        for reg in comparison["regressions"]:
            detail = reg.get("detail") or f"{reg.get('change_pct', 0)}% change"                                       
            print(f"  - {reg['metric']}: {detail}")                                                                   
            
    # Write report
    report_path = Path("evals/reports/latest.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport written to {report_path}")

    # Exit code: fail if regressions or low pass rate
    if comparison.get("has_regressions"):
        print("\nFAILED: Regressions detected against baseline")
        sys.exit(1)
    elif report["summary"]["pass_rate"] < 0.8:
        print(f"\nFAILED: Pass rate {report['summary']['pass_rate']:.0%} below 80% threshold")
        sys.exit(1)
    else:
        print("\nPASSED")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
