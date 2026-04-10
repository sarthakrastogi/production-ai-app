"""
PII scrubbing and attack detection: two independent LangGraph nodes.
LangGraph fans them out in parallel natively from the entry point.
No asyncio.gather needed — and both appear as separate spans in LangSmith.
"""
import asyncio
import httpx
import pybreaker

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

from app.graph.state import SupportBotState
from app.observability.logging import get_logger
from app.resilience.breakers import rival_breaker
from app.resilience.retry import http_retry
from app.config import settings

_analyzer = AnalyzerEngine()
_anonymizer = AnonymizerEngine()


# ── Node A: PII scrubbing ─────────────────────────────────────────────────────

def _scrub_pii_sync(text: str) -> tuple[str, list[str]]:
    """Sync + CPU-bound — pushed to thread pool via run_in_executor."""
    results = _analyzer.analyze(text=text, language="en")
    anonymized = _anonymizer.anonymize(text=text, analyzer_results=results)
    found_types = list({r.entity_type for r in results})
    return anonymized.text, found_types


async def pii_scrub_node(state: SupportBotState) -> dict:
    log = get_logger(state["request_id"], node="pii_scrub")
    loop = asyncio.get_event_loop()
    scrubbed_query, pii_found = await loop.run_in_executor(
        None, _scrub_pii_sync, state["raw_query"]
    )
    log.info("pii_scrub_complete", pii_found=pii_found)
    return {"scrubbed_query": scrubbed_query, "pii_found": pii_found}


# ── Node B: Attack detection ──────────────────────────────────────────────────

@http_retry
async def _call_rival(query: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.RIVAL_URL}/detect",
            json={"query": query},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()


async def attack_detect_node(state: SupportBotState) -> dict:
    log = get_logger(state["request_id"], node="attack_detect")
    try:
        with rival_breaker:
            result = await _call_rival(state["raw_query"])
    except pybreaker.CircuitBreakerError:
        log.warning("rival_circuit_open")
        result = {"is_attack": False, "confidence": 0.0}
    except Exception as exc:
        log.warning("rival_call_failed", error=str(exc))
        result = {"is_attack": False, "confidence": 0.0}

    log.info(
        "attack_detect_complete",
        is_attack=result["is_attack"],
        confidence=result["confidence"],
    )
    return {
        "is_attack": result["is_attack"],
        "attack_confidence": result["confidence"],
    }


# ── Node C: Safety merge (runs after both complete) ───────────────────────────

async def safety_merge_node(state: SupportBotState) -> dict:
    """
    No-op merge point. LangGraph waits for both pii_scrub and attack_detect
    to finish before entering this node. We log the combined result here.
    """
    log = get_logger(state["request_id"], node="safety_merge")
    log.info(
        "safety_gate_complete",
        pii_found=state.get("pii_found", []),
        is_attack=state.get("is_attack", False),
        scrubbed_query_length=len(state.get("scrubbed_query", "")),
    )
    return {}
