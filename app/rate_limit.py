"""Cache-based request throttling for public authentication endpoints."""

from django.core.cache import cache


def register_attempt(request, scope, max_attempts, window_seconds):
    """Record one attempt for (scope, client IP) and report whether the limit is exceeded.

    Uses the default cache as a fixed-window counter per worker process. Set
    max_attempts to 0 to disable throttling for a scope.
    """

    if max_attempts <= 0:
        return False

    key = f"ratelimit:{scope}:{request.META.get('REMOTE_ADDR') or 'unknown'}"

    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        count = 1

    return count > max_attempts
