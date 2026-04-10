import httpx
import pybreaker

from app.graph.state import SupportBotState
from app.observability.logging import get_logger
from app.resilience.breakers import gptcache_breaker
from app.config import settings


async def cache_store_node(state: SupportBotState) -> dict:
    log = get_logger(state["request_id"], node="cache_store")

    try:
        with gptcache_breaker:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{settings.GPTCACHE_URL}/put",
                    json={
                        "prompt": state["raw_query"],
                        "answer": state["final_response"],
                    },
                    timeout=2.0,
                )
    except pybreaker.CircuitBreakerError:
        log.warning("gptcache_circuit_open")
    except Exception as exc:
        # Non-fatal. A failed cache write just means the next similar query
        # won't hit the cache — the user gets their response regardless.
        log.warning("cache_store_failed", error=str(exc))

    # Log the full summary for this request
    log.info(
        "request_complete",
        model_used=state.get("model_used"),
        faithfulness=round(state.get("faithfulness_score", 0), 3),
        completeness=round(state.get("completeness_score", 0), 3),
        validation_passed=state.get("validation_passed"),
        pii_found=state.get("pii_found", []),
        prompt_version=state.get("prompt_version"),
        num_sub_queries=len(state.get("sub_queries", [])),
        needs_decomp=state.get("needs_decomp"),
    )

    return {}
