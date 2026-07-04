import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from app.middleware.input_guard import input_guard_middleware


@pytest.fixture
def make_request():
    def _make(method="POST", path="/query", body=None):
        request = MagicMock()
        request.method = method
        request.url.path = path
        if body is not None:
            import json
            request.body = AsyncMock(return_value=json.dumps(body).encode())
        else:
            request.body = AsyncMock(return_value=b"")
        return request
    return _make


@pytest.mark.asyncio
async def test_passes_valid_query(make_request):
    request = make_request(body={"query": "How do I reset my AirPods?"})
    call_next = AsyncMock(return_value="response")
    result = await input_guard_middleware(request, call_next)
    assert result == "response"


@pytest.mark.asyncio
async def test_rejects_empty_query(make_request):
    request = make_request(body={"query": ""})
    call_next = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await input_guard_middleware(request, call_next)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_rejects_oversized_query(make_request):
    request = make_request(body={"query": "x" * 5000})
    call_next = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await input_guard_middleware(request, call_next)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_skips_non_query_endpoints(make_request):
    request = make_request(method="GET", path="/health")
    call_next = AsyncMock(return_value="ok")
    result = await input_guard_middleware(request, call_next)
    assert result == "ok"
