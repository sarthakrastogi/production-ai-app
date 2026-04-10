from typing import TypedDict, Literal, Annotated
import operator


def append_list(existing: list, new: list) -> list:
    """Reducer that appends to a list — used for parallel sub_responses."""
    return (existing or []) + (new or [])


class SupportBotState(TypedDict):
    # --- input ---
    raw_query: str
    session_id: str
    request_id: str

    # --- safety ---
    scrubbed_query: str
    pii_found: list[str]
    is_attack: bool
    attack_confidence: float

    # --- query intelligence ---
    intent: str
    sub_queries: list[str]
    complexity: Literal["low", "high"]
    needs_decomp: bool
    prompt_version: str
    current_subquery: str  # used per-node in fan-out

    # --- context ---
    session_history: list[dict]
    retrieved_context: list[str]

    # --- execution ---
    # annotated with the append reducer so parallel Send nodes can all write
    sub_responses: Annotated[list[str], append_list]
    raw_response: str
    model_used: str

    # --- validation ---
    faithfulness_score: float
    completeness_score: float
    validation_passed: bool

    # --- output ---
    final_response: str
