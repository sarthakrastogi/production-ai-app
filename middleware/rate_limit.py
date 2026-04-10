from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request


def get_user_id(request: Request) -> str:
    """Use authenticated user ID for rate limiting, fall back to IP."""
    return getattr(request.state, "user_id", get_remote_address(request))


limiter = Limiter(key_func=get_user_id)
