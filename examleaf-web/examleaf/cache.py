"""The cache backend for Redis: django-redis, failing soft (settings.REDIS_CACHE_OPTIONS: IGNORE_EXCEPTIONS)."""

from django_redis.cache import RedisCache


class SoftRedisCache(RedisCache):
    """While Redis is down every call counts as a miss, and `add` answers None. allauth takes that for "somebody holds
    the lock" (`while not cache.add(lock)`) and answers 429 to every log-in, sign-up and password reset until Redis is
    back. Here `add` says "stored" instead, so the rate limits let requests through, as the others do."""

    def add(self, *args, **kwargs):
        stored = super().add(*args, **kwargs)
        return True if stored is None else stored
