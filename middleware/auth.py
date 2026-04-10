from fastapi import Request, HTTPException
from jose import jwt, JWTError
from app.config import settings


async def auth_middleware(request: Request, call_next):
    # skip health check endpoint
    if request.url.path in ("/health", "/docs", "/openapi.json"):
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed token")

    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        request.state.user_id = payload["sub"]
        request.state.user_payload = payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    return await call_next(request)
