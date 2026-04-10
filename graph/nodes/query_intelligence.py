from pathlib import Path
from typing import Literal
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from app.graph.state import SupportBotState
from app.observability.logging import get_logger
from app.resilience.retry import llm_retry

PROMPT_VERSION = "v1"
_PROMPT_TEMPLATE = Path(f"prompts/{PROMPT_VERSION}/query_intelligence.txt").read_text()


class QueryAnalysis(BaseModel):
    intent: str
    sub_queries: list[str]
    complexity: Literal["low", "high"]
    needs_decomp: bool


_llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash").with_structured_output(
    QueryAnalysis
)


@llm_retry
async def _analyse(prompt: str) -> QueryAnalysis:
    return await _llm.ainvoke(prompt)


async def query_intelligence_node(state: SupportBotState) -> dict:
    log = get_logger(state["request_id"], node="query_intelligence")

    history_text = "\n".join(
        f"{turn['role'].upper()}: {turn['content']}"
        for turn in (state.get("session_history") or [])[-6:]  # last 3 exchanges
    ) or "None"

    prompt = _PROMPT_TEMPLATE.format(
        query=state["scrubbed_query"],
        session_history=history_text,
    )

    result: QueryAnalysis = await _analyse(prompt)

    log.info(
        "query_intelligence_complete",
        intent=result.intent,
        num_sub_queries=len(result.sub_queries),
        complexity=result.complexity,
        needs_decomp=result.needs_decomp,
        prompt_version=PROMPT_VERSION,
    )

    return {
        "intent": result.intent,
        "sub_queries": result.sub_queries,
        "complexity": result.complexity,
        "needs_decomp": result.needs_decomp,
        "prompt_version": PROMPT_VERSION,
    }
