import time
from typing import Any

from fastapi import Request

from app.core.errors import RateLimitError
from app.db.redis import get_redis


def _client_ip(request: Request) -> str:
    settings = get_settings_safe()
    if settings is not None and getattr(settings, "behind_proxy", False):
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            # The rightmost entry is the one appended by our own trusted proxy;
            # leftmost entries are client-controlled and spoofable.
            return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def get_settings_safe() -> Any:
    from app.core.config import get_settings

    try:
        return get_settings()
    except Exception:
        return None


async def enforce_rate_limit(
    key: str, limit: int, window_seconds: int = 60
) -> None:
    """Fixed-window counter in Redis. Raises RateLimitError when exceeded."""
    try:
        r = get_redis()
        bucket = int(time.time() // window_seconds)
        redis_key = f"rl:{key}:{bucket}"
        count = await r.incr(redis_key)
        if count == 1:
            await r.expire(redis_key, window_seconds + 1)
        if count > limit:
            raise RateLimitError(
                details={"retry_after_seconds": window_seconds}
            )
    except RateLimitError:
        raise
    except Exception:
        # Redis unavailable: fail open rather than take the panel down.
        return


async def rate_limit_request(request: Request, limit: int | None = None) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    effective = limit or settings.rate_limit_default_per_minute
    await enforce_rate_limit(f"http:{_client_ip(request)}", effective)
