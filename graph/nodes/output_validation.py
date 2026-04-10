"""
Output validation: two independent LangGraph nodes run in parallel.

  faithfulness_node  — Ragas: are all claims grounded in retrieved context?
  completeness_node  — LLM-as-judge: did we answer all sub-queries?

Both fan out from the execution node(s) and converge at validation_merge.
asyncio.gather is NOT used here — LangGraph handles the concurrency.
"""
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness

from app.graph.state import SupportBotState
from app.metrics.completeness import score_completeness
from app.observability.logging import get_logger
from app.config import settings

_faithfulness_scorer = Faithfulness(
    llm=llm_factory("gpt-4o-mini", client=AsyncOpenAI())
)


# ── Node A: Ragas faithfulness ────────────────────────────────────────────────

async def faithfulness_node(state: SupportBotState) -> dict:
    log = get_logger(state["request_id"], node="faithfulness")
    context = state.get("retrieved_context", [])

    if not context:
        # Nothing to ground against — skip scoring
        log.info("faithfulness_skipped", reason="no_context")
        return {"faithfulness_score": 1.0}

    result = await _faithfulness_scorer.ascore(
        user_input=state["scrubbed_query"],
        response=state["raw_response"],
        retrieved_contexts=context,
    )
    score = float(result.value)
    log.info("faithfulness_complete", score=round(score, 3))
    return {"faithfulness_score": score}


# ── Node B: Completeness (LLM-as-judge) ──────────────────────────────────────

async def completeness_node(state: SupportBotState) -> dict:
    log = get_logger(state["request_id"], node="completeness")
    score = await score_completeness(
        intent=state["intent"],
        sub_queries=state["sub_queries"],
        response=state["raw_response"],
    )
    log.info("completeness_complete", score=round(score, 3))
    return {"completeness_score": score}


# ── Node C: Validation merge ──────────────────────────────────────────────────

async def validation_merge_node(state: SupportBotState) -> dict:
    """
    Merge point after both validation nodes complete.
    Decides pass/fail and sets final_response.
    """
    log = get_logger(state["request_id"], node="validation_merge")

    faithfulness = state.get("faithfulness_score", 1.0)
    completeness = state.get("completeness_score", 1.0)
    passed = (
        faithfulness >= settings.FAITHFULNESS_THRESHOLD
        and completeness >= settings.COMPLETENESS_THRESHOLD
    )

    if not passed:
        log.warning(
            "validation_failed",
            faithfulness=round(faithfulness, 3),
            completeness=round(completeness, 3),
        )
    else:
        log.info(
            "validation_passed",
            faithfulness=round(faithfulness, 3),
            completeness=round(completeness, 3),
        )

    return {
        "validation_passed": passed,
        "final_response": state["raw_response"],
    }
