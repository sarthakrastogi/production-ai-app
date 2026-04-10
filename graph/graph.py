import asyncpg
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.graph.state import SupportBotState
from app.graph.nodes.safety_gate import (
    pii_scrub_node,
    attack_detect_node,
    safety_merge_node,
)
from app.graph.nodes.query_intelligence import query_intelligence_node
from app.graph.nodes.session_memory import session_memory_node
from app.graph.nodes.context_retrieval import context_retrieval_node
from app.graph.nodes.execution import (
    generate_flash_node,
    generate_pro_node,
    generate_subquery_node,
    merge_subqueries_node,
    route_execution,
)
from app.graph.nodes.output_validation import (
    faithfulness_node,
    completeness_node,
    validation_merge_node,
)
from app.graph.nodes.cache_store import cache_store_node
from app.config import settings


def _route_after_safety(state: SupportBotState) -> str:
    return END if state.get("is_attack") else "query_intelligence"


async def build_graph(pool: asyncpg.Pool):
    """
    Compile and return the LangGraph graph with PostgresSaver checkpointer.
    Call once at app startup.

    Parallel patterns used:
    1. pii_scrub + attack_detect  — two edges from START, merge at safety_merge
    2. faithfulness + completeness — two edges from execution, merge at validation_merge
    3. generate_subquery fan-out  — dynamic via Send API (number known only at runtime)
    """
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()

    g = StateGraph(SupportBotState)

    # ── Register nodes ────────────────────────────────────────────────────────
    g.add_node("pii_scrub", pii_scrub_node)
    g.add_node("attack_detect", attack_detect_node)
    g.add_node("safety_merge", safety_merge_node)
    g.add_node("query_intelligence", query_intelligence_node)
    g.add_node("session_memory", session_memory_node)
    g.add_node("context_retrieval", context_retrieval_node)
    g.add_node("generate_flash", generate_flash_node)
    g.add_node("generate_pro", generate_pro_node)
    g.add_node("generate_subquery", generate_subquery_node)
    g.add_node("merge_subqueries", merge_subqueries_node)
    g.add_node("faithfulness", faithfulness_node)
    g.add_node("completeness", completeness_node)
    g.add_node("validation_merge", validation_merge_node)
    g.add_node("cache_store", cache_store_node)

    # ── Edges ─────────────────────────────────────────────────────────────────

    # Fan-out: both safety nodes start together from the entry point
    g.set_entry_point("pii_scrub")
    g.set_entry_point("attack_detect")
    # LangGraph runs both in parallel; safety_merge waits for both to finish
    g.add_edge("pii_scrub", "safety_merge")
    g.add_edge("attack_detect", "safety_merge")

    # After merge: reject attacks, otherwise continue
    g.add_conditional_edges("safety_merge", _route_after_safety)

    g.add_edge("query_intelligence", "session_memory")
    g.add_edge("session_memory", "context_retrieval")

    # Execution branch: Flash / Pro / Send fan-out
    g.add_conditional_edges(
        "context_retrieval",
        route_execution,
        {
            "generate_flash": "generate_flash",
            "generate_pro": "generate_pro",
            # Send API handles the fan-out case dynamically
        },
    )

    # All single-query execution paths feed both validation nodes in parallel
    for exec_node in ("generate_flash", "generate_pro"):
        g.add_edge(exec_node, "faithfulness")
        g.add_edge(exec_node, "completeness")

    # Sub-query fan-out merges first, then splits into validation
    g.add_edge("generate_subquery", "merge_subqueries")
    g.add_edge("merge_subqueries", "faithfulness")
    g.add_edge("merge_subqueries", "completeness")

    # Both validation nodes converge at validation_merge
    g.add_edge("faithfulness", "validation_merge")
    g.add_edge("completeness", "validation_merge")

    g.add_edge("validation_merge", "cache_store")
    g.add_edge("cache_store", END)

    return g.compile(checkpointer=checkpointer)
