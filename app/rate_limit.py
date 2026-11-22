"""Cache-based request throttling for public authentication endpoints."""

from django.conf import settings
from django.core.cache import cache


def client_ip(request):
    """Return the client IP, from CLIENT_IP_HEADER when a proxy sets it, else REMOTE_ADDR."""

    if settings.CLIENT_IP_HEADER:
        meta_key = "HTTP_" + settings.CLIENT_IP_HEADER.upper().replace("-", "_")
        # An IPv6 address is at most 45 characters; cap so a forged header cannot bloat keys.
        forwarded_ip = request.META.get(meta_key, "").strip()[:64]
        if forwarded_ip:
            return forwarded_ip

    return request.META.get("REMOTE_ADDR") or "unknown"


def register_attempt(request, scope, max_attempts, window_seconds):
    """Record one attempt for (scope, client IP) and report whether the limit is exceeded.

    Uses the default cache as a fixed-window counter per worker process. Set
    max_attempts to 0 to disable throttling for a scope.
    """

    if max_attempts <= 0:
        return False

    key = f"ratelimit:{scope}:{client_ip(request)}"

    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        count = 1

    return count > max_attempts
