import json
from fastapi import Request, HTTPException
from app.config import settings


async def input_guard_middleware(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/query":
        body = await request.body()
        # re-attach body so downstream handlers can still read it
        request._body = body

        try:
            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        query = data.get("query", "")

        if not isinstance(query, str):
            raise HTTPException(status_code=400, detail="query must be a string")

        if not query.strip():
            raise HTTPException(status_code=400, detail="query must not be empty")

        if len(query) > settings.MAX_INPUT_CHARS:
            raise HTTPException(
                status_code=400,
                detail=f"query exceeds maximum length of {settings.MAX_INPUT_CHARS} characters",
            )

    return await call_next(request)
