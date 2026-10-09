"""The cache backend for Redis: django-redis, failing soft (settings.REDIS_CACHE_OPTIONS: IGNORE_EXCEPTIONS)."""

import logging
import time

from django_redis.cache import RedisCache
from django_redis.exceptions import ConnectionInterrupted

logger = logging.getLogger(__name__)


class SoftRedisCache(RedisCache):
    """While Redis is down every call counts as a miss, and `add` answers None. allauth takes that for "somebody holds
    the lock" (`while not cache.add(lock)`) and answers 429 to every log-in, sign-up and password reset until Redis is
    back. Here `add` says "stored" instead, so the rate limits let requests through, as the others do.

    And a Redis that does not answer (its node gone, a firewall dropping the packets) costs each call its socket
    timeout, a second, and a request makes four to fourteen calls (throttles, cached pages, allauth's limits): every
    request would take seconds and the threads would run out. After a failed call this process asks Redis nothing for
    PAUSE seconds, every call a miss at once, then tries again (a circuit breaker, per process); it logs one warning a
    pause, not one a call (settings: DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS off)."""

    PAUSE = 5  # seconds
    down_until = 0.0  # time.monotonic() until which Redis is not asked: the class's, shared by the process's threads

    def add(self, *args, **kwargs):
        stored = super().add(*args, **kwargs)
        return True if stored is None else stored

    @property
    def client(self):
        return Guarded(super().client, self)


class Guarded:
    """The django-redis client of a SoftRedisCache, in front of each call: refused at once (as a lost connection,
    which django-redis turns into the miss or default) while the cache's pause lasts; a lost connection starts one."""

    def __init__(self, client, cache):
        self._client, self._cache = client, cache

    def __getattr__(self, name):
        attribute = getattr(self._client, name)
        if not callable(attribute):
            return attribute

        def call(*args, **kwargs):
            cache = type(self._cache)  # Django gives each thread a cache object of its own
            if time.monotonic() < cache.down_until:
                raise ConnectionInterrupted(connection=None)
            try:
                return attribute(*args, **kwargs)
            except ConnectionInterrupted as error:
                cache.down_until = time.monotonic() + cache.PAUSE
                logger.warning("%s: every cache call a miss for %s seconds", error, cache.PAUSE)
                raise

        return call
