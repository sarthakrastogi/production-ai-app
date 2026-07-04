import pytest

from app.graph.state import SupportBotState, append_list


def test_append_list_reducer():
    assert append_list(["a", "b"], ["c"]) == ["a", "b", "c"]


def test_append_list_handles_none():
    assert append_list(None, ["c"]) == ["c"]
    assert append_list(["a"], None) == ["a"]


def test_state_has_all_required_fields():
    required_fields = [
        "raw_query", "session_id", "request_id",
        "scrubbed_query", "pii_found", "is_attack", "attack_confidence",
        "intent", "sub_queries", "complexity", "needs_decomp",
        "prompt_version", "current_subquery",
        "session_history", "retrieved_context",
        "sub_responses", "raw_response", "model_used",
        "faithfulness_score", "completeness_score", "validation_passed",
        "final_response",
    ]
    annotations = SupportBotState.__annotations__
    for field in required_fields:
        assert field in annotations, f"Missing field: {field}"
