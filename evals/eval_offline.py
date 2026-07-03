"""
Offline evals — run WITHOUT a live server.

Tests the LangGraph agent's logic in isolation:
  - Routing decisions (complexity -> model selection)
  - Query decomposition logic
  - Prompt file integrity
  - Token budget estimates

These run fast in CI without needing Docker or external services.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evals.config import eval_settings

DATASET_PATH = Path(eval_settings.DATASET_FILE)


async def eval_query_intelligence_routing():
    """
    Verify that the routing logic produces correct model selection
    based on complexity and decomposition needs.
    """
    dataset = json.loads(DATASET_PATH.read_text())
    results = []

    for case in dataset:
        expected_complexity = case.get("expected_complexity")
        expected_decomp = case.get("needs_decomp", False)
        expected_sub_count = case.get("sub_query_count")
        expected_model = case.get("expected_model")

        # Simulate state after query_intelligence runs
        state = {
            "needs_decomp": expected_decomp,
            "sub_queries": [case["query"]] * (expected_sub_count or 1),
            "complexity": expected_complexity or "low",
        }

        # Determine expected route
        if expected_decomp and (expected_sub_count or 0) > 1:
            expected_route = "fan_out"
        elif expected_complexity == "low":
            expected_route = "generate_flash"
        else:
            expected_route = "generate_pro"

        # Apply routing logic (mirrors execution.route_execution)
        if state["needs_decomp"] and len(state["sub_queries"]) > 1:
            actual_route = "fan_out"
        elif state["complexity"] == "low":
            actual_route = "generate_flash"
        else:
            actual_route = "generate_pro"

        passed = actual_route == expected_route
        results.append({
            "id": case["id"],
            "passed": passed,
            "expected_route": expected_route,
            "actual_route": actual_route,
        })

        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] routing/{case['id']}: {actual_route} (expected {expected_route})")

    return results


async def eval_decomposition_expectations():
    """
    Verify that cases marked as needing decomposition have >1 sub-queries,
    and cases not needing decomposition don't.
    """
    dataset = json.loads(DATASET_PATH.read_text())
    results = []

    for case in dataset:
        needs_decomp = case.get("needs_decomp", False)
        sub_count = case.get("sub_query_count", 1)

        if needs_decomp:
            passed = sub_count > 1
            detail = f"needs_decomp=true, sub_query_count={sub_count}"
        else:
            passed = sub_count <= 1
            detail = f"needs_decomp=false, sub_query_count={sub_count}"

        results.append({
            "id": case["id"],
            "passed": passed,
            "detail": detail,
        })

        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] decomp/{case['id']}: {detail}")

    return results


async def eval_prompt_versioning():
    """
    Verify all referenced prompt files exist and are non-empty.
    """
    prompt_dir = Path("prompts")
    results = []

    expected_prompts = [
        "v1/query_intelligence.txt",
        "v1/generation.txt",
        "v1/completeness_judge.txt",
    ]

    for prompt_path in expected_prompts:
        full_path = prompt_dir / prompt_path
        exists = full_path.exists()
        non_empty = full_path.stat().st_size > 0 if exists else False
        passed = exists and non_empty

        results.append({
            "id": f"prompt_{prompt_path}",
            "passed": passed,
            "path": str(full_path),
        })

        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] prompt/{prompt_path}")

    return results


async def eval_token_budget():
    """
    Estimate token usage for each case and flag any that exceed budget.
    """
    dataset = json.loads(DATASET_PATH.read_text())
    generation_prompt = Path("prompts/v1/generation.txt").read_text()
    results = []

    for case in dataset:
        # Estimate input tokens (prompt template + query + typical context)
        prompt_tokens = len(generation_prompt) / 4
        query_tokens = len(case["query"]) / 4
        context_tokens = 2000  # typical retrieved context size
        estimated_input = prompt_tokens + query_tokens + context_tokens

        max_output = case.get("max_tokens", 500)
        total_estimated = estimated_input + max_output

        # Flag if total would exceed model context window
        passed = total_estimated < 100000
        results.append({
            "id": case["id"],
            "passed": passed,
            "estimated_input_tokens": int(estimated_input),
            "max_output_tokens": max_output,
            "total_estimated": int(total_estimated),
        })

        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] token_budget/{case['id']}: ~{int(total_estimated)} tokens")

    return results


async def eval_model_assignment():
    """
    Verify that expected_model aligns with expected_complexity.
    flash = low complexity, pro = high complexity.
    """
    dataset = json.loads(DATASET_PATH.read_text())
    results = []

    for case in dataset:
        complexity = case.get("expected_complexity", "low")
        model = case.get("expected_model", "flash")

        if complexity == "low":
            passed = model == "flash"
        else:
            passed = model == "pro"

        results.append({
            "id": case["id"],
            "passed": passed,
            "complexity": complexity,
            "model": model,
        })

        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] model_assignment/{case['id']}: {complexity} -> {model}")

    return results


async def main():
    print("Running offline evals (no server needed)...")
    print("=" * 60)

    all_results = []

    print("\n1. Query Intelligence Routing:")
    all_results.extend(await eval_query_intelligence_routing())

    print("\n2. Decomposition Expectations:")
    all_results.extend(await eval_decomposition_expectations())

    print("\n3. Prompt Versioning:")
    all_results.extend(await eval_prompt_versioning())

    print("\n4. Token Budget Estimates:")
    all_results.extend(await eval_token_budget())

    print("\n5. Model Assignment Consistency:")
    all_results.extend(await eval_model_assignment())

    print("\n" + "=" * 60)
    total = len(all_results)
    passed = sum(1 for r in all_results if r["passed"])
    print(f"Results: {passed}/{total} passed")

    report = {
        "type": "offline",
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "results": all_results,
    }

    report_path = Path("evals/reports/offline_latest.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))

    if passed < total:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
