import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    pass


def check_ratelimit(key_prefix: str, limit: int = 5, period: int = 60) -> bool:
    """
    Atomic rate limiter using Django's cache backend.

        Uses two atomic primitives:
        cache.add()   — SET key=1 only if it does NOT already exist (atomic)
        cache.incr()  — atomically increment and return the new value

    Under concurrent load both threads call cache.add(). Exactly one wins
    (Redis SETNX is atomic). The loser proceeds to incr(), which returns the
    correct count with no gap.

    RateLimitError is intentionally NOT caught here — callers must handle it.
    Only genuine cache backend failures are caught and logged.
    """
    key = f"ratelimit:{key_prefix}"

    try:
        # Try to initialise the key. Returns True only if key didn't exist.
        # If True, this is the first request in the window — always allow it.
        added = cache.add(key, 1, timeout=period)
        if added:
            return True

        # Key already existed — atomically increment and check the count.
        count = cache.incr(key)

        if count > limit:
            raise RateLimitError("Too many attempts. Please try again later.")

        return True

    except RateLimitError:
        raise

    except Exception as e:
        # Only real cache backend failures land here (Redis down, timeout, etc.)
        logger.error("Cache backend error in rate limiter (key=%s): %s", key, e)
        # Fail open: better to let a request through than to lock everyone out
        # because Redis is temporarily unreachable.
        return True