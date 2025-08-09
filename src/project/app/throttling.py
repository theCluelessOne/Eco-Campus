# app/throttling.py
import time
from django.core.cache import cache
from django.http import HttpResponse

def simple_rate_limit(key_prefix: str, limit: int, window_sec: int):
    """
    Very small IP-based rate limiter.
    Returns HTTP 429 when more than `limit` requests occur within `window_sec`.
    """
    def deco(view):
        def _wrapped(request, *args, **kwargs):
            ip = request.META.get("REMOTE_ADDR", "unknown")
            key = f"rl:{key_prefix}:{ip}"
            now = int(time.monotonic())  # monotonic clock is safer for buckets

            bucket = cache.get(key)
            if not bucket:
                bucket = {"start": now, "count": 0}

            # reset window
            if now - bucket["start"] >= window_sec:
                bucket = {"start": now, "count": 0}

            bucket["count"] += 1
            cache.set(key, bucket, window_sec)

            if bucket["count"] > limit:
                return HttpResponse("Rate limit exceeded. Try again shortly.", status=429)

            return view(request, *args, **kwargs)
        return _wrapped
    return deco
