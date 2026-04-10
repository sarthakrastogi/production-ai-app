from pathlib import Path
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.types import Send

from app.graph.state import SupportBotState
from app.observability.logging import get_logger
from app.resilience.retry import llm_retry
from app.config import settings

_GENERATION_PROMPT = Path("prompts/v1/generation.txt").read_text()


def _get_model(complexity: str):
    if complexity == "low":
        return ChatGoogleGenerativeAI(model=settings.LOW_COMPLEXITY_MODEL)
    model_name = settings.HIGH_COMPLEXITY_MODEL
    if model_name.startswith("gpt"):
        return ChatOpenAI(model=model_name)
    return ChatGoogleGenerativeAI(model=model_name)


def _build_prompt(query: str, context: list[str], history: list[dict]) -> str:
    context_text = "\n\n".join(context) if context else "No retrieved context available."
    history_text = "\n".join(
        f"{t['role'].upper()}: {t['content']}" for t in (history or [])[-6:]
    ) or "None"
    return _GENERATION_PROMPT.format(
        query=query,
        context=context_text,
        history=history_text,
    )


# ── Single query nodes ────────────────────────────────────────────────────────

@llm_retry
async def _generate(query: str, context: list[str], history: list[dict], complexity: str) -> tuple[str, str]:
    model = _get_model(complexity)
    prompt = _build_prompt(query, context, history)
    result = await model.ainvoke(prompt)
    model_name = settings.LOW_COMPLEXITY_MODEL if complexity == "low" else settings.HIGH_COMPLEXITY_MODEL
    return result.content, model_name


async def generate_flash_node(state: SupportBotState) -> dict:
    log = get_logger(state["request_id"], node="generate_flash")
    response, model_name = await _generate(
        state["scrubbed_query"],
        state["retrieved_context"],
        state.get("session_history", []),
        "low",
    )
    log.info("generation_complete", model=model_name)
    return {"raw_response": response, "model_used": model_name}


async def generate_pro_node(state: SupportBotState) -> dict:
    log = get_logger(state["request_id"], node="generate_pro")
    response, model_name = await _generate(
        state["scrubbed_query"],
        state["retrieved_context"],
        state.get("session_history", []),
        "high",
    )
    log.info("generation_complete", model=model_name)
    return {"raw_response": response, "model_used": model_name}


# ── Parallel sub-query fan-out ────────────────────────────────────────────────

def fan_out_subqueries(state: SupportBotState) -> list[Send]:
    """
    Called as a conditional edge. Returns one Send per sub-query,
    each spawning an independent generate_subquery node.
    """
    return [
        Send("generate_subquery", {**state, "current_subquery": sq})
        for sq in state["sub_queries"]
    ]


async def generate_subquery_node(state: SupportBotState) -> dict:
    """Runs once per sub-query in parallel. Results accumulate via list reducer."""
    log = get_logger(state["request_id"], node="generate_subquery",
                     subquery=state["current_subquery"])

    response, model_name = await _generate(
        state["current_subquery"],
        state["retrieved_context"],
        state.get("session_history", []),
        state["complexity"],
    )
    log.info("subquery_complete", model=model_name)
    # sub_responses uses an append reducer — each parallel node safely adds one item
    return {"sub_responses": [response], "model_used": model_name}


async def merge_subqueries_node(state: SupportBotState) -> dict:
    """Merges parallel sub-responses into a single coherent raw_response."""
    merged = "\n\n".join(
        f"**Part {i+1}:** {r}" for i, r in enumerate(state.get("sub_responses", []))
    )
    return {"raw_response": merged}


# ── Routing ───────────────────────────────────────────────────────────────────

def route_execution(state: SupportBotState):
    if state["needs_decomp"] and len(state["sub_queries"]) > 1:
        return fan_out_subqueries(state)  # returns list[Send] for dynamic fan-out
    elif state["complexity"] == "low":
        return "generate_flash"
    else:
        return "generate_pro"
