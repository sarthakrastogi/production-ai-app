import pytest

from app.graph.nodes.execution import route_execution


def _make_state(complexity="low", needs_decomp=False, sub_queries=None):
    return {
        "needs_decomp": needs_decomp,
        "sub_queries": sub_queries or ["test query"],
        "complexity": complexity,
        "raw_query": "test",
        "session_id": "test",
        "request_id": "test",
        "scrubbed_query": "test",
        "pii_found": [],
        "is_attack": False,
        "attack_confidence": 0.0,
        "intent": "test",
        "prompt_version": "v1",
        "current_subquery": "",
        "session_history": [],
        "retrieved_context": [],
        "sub_responses": [],
        "raw_response": "",
        "model_used": "",
        "faithfulness_score": 0.0,
        "completeness_score": 0.0,
        "validation_passed": False,
        "final_response": "",
    }


def test_routes_to_flash_for_low_complexity():
    state = _make_state(complexity="low", needs_decomp=False)
    result = route_execution(state)
    assert result == "generate_flash"


def test_routes_to_pro_for_high_complexity():
    state = _make_state(complexity="high", needs_decomp=False)
    result = route_execution(state)
    assert result == "generate_pro"


def test_routes_to_fan_out_for_decomposition():
    state = _make_state(
        complexity="high",
        needs_decomp=True,
        sub_queries=["q1", "q2", "q3"],
    )
    result = route_execution(state)
    # fan_out returns a list of Send objects
    assert isinstance(result, list)
    assert len(result) == 3
