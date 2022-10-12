import logging
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass

from quart import Quart

try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None

from .helpers import OptionalRequirementMissing, PasteMeta

logger = logging.getLogger("paste_bin")


class BaseCache(ABC):
    """
    The base cache class that all cache types should inherit from
    """
    @abstractmethod
    def __init__(self, app: Quart, **kw):
        ...

    @abstractmethod
    async def push_paste_all(
            self,
            paste_id: str,
            /,
            *,
            meta: PasteMeta | None = None,
            html: str | None = None,
            raw: bytes | None = None):
        """
        create or update parts (or all) of the cached paste
        """
        ...

    @abstractmethod
    async def push_paste_meta(self, paste_id: str, meta: PasteMeta):
        """
        create of update the cached meta of a paste
        """
        ...

    @abstractmethod
    async def get_paste_meta(self, paste_id: str) -> PasteMeta:
        """
        Get the cached paste meta, if in cache
        """
        ...

    @abstractmethod
    async def get_paste_rendered(self, paste_id: str) -> str | None:
        """
        Get the cached rendered paste content, if in cache
        """
        ...

    @abstractmethod
    async def get_paste_raw(self, paste_id: str) -> bytes | None:
        """
        Get the cached raw paste content, if in cache
        """
        ...


@dataclass
class InternalCacheItem:
    meta: PasteMeta
    rendered_paste: str | None = None
    raw_paste: bytes | None = None


class FakeCache(BaseCache):
    """
    This cache will never do any caching
    """
    def __init__(self, app, **kw):
        pass

    async def push_paste_all(self, paste_id, /, *, meta=None, html=None, raw=None):
        pass

    async def push_paste_meta(self, paste_id, meta):
        pass

    async def get_paste_meta(self, paste_id):
        pass

    async def get_paste_rendered(self, paste_id):
        pass

    async def get_paste_raw(self, paste_id):
        pass


class InternalCache(BaseCache):
    """
    Basic internal cache, that does not need a separate service
    """
    _max_meta_size: int
    _cache: OrderedDict[str, InternalCacheItem]

    def __init__(self, app, max_size: int = 5, **kw):
        self._max_meta_size = max_size
        self._cache = OrderedDict()

    @property
    def cache_len(self) -> int:
        """
        returns how many items are in cache
        """
        return len(self._cache)

    def _expire_old(self):
        if self.cache_len > self._max_meta_size:
            # remove all that are least accessed
            n_to_removed = self.cache_len - self._max_meta_size
            logger.debug("removing %s oldest items from cache", n_to_removed)
            [self._cache.popitem(last=True) for _ in range(n_to_removed)]

    def _read_cache(self, paste_id: str) -> InternalCacheItem | None:
        if (cached := self._cache.get(paste_id)) is not None:
            # we want most used items at front, so least accessed are removed first
            self._cache.move_to_end(paste_id, last=False)
            return cached

    def _write_cache(self, paste_id: str, to_cache: InternalCacheItem):
        # insert/overwrite cache
        self._cache[paste_id] = to_cache
        # we want most used items at front
        self._cache.move_to_end(paste_id, last=False)
        # expire old items
        self._expire_old()

    async def push_paste_all(self, paste_id, /, *, meta=None, html=None, raw=None):
        # take value of existing cache if None
        meta = meta if meta is not None else await self.get_paste_meta(paste_id)
        html = html if html is not None else await self.get_paste_rendered(paste_id)
        raw = raw if raw is not None else await self.get_paste_raw(paste_id)
        to_cache = InternalCacheItem(
            meta=meta, rendered_paste=html, raw_paste=raw)
        self._write_cache(paste_id, to_cache)

    async def push_paste_meta(self, paste_id, meta):
        await self.push_paste_all(paste_id, meta=meta, html=None, raw=None)

    async def get_paste_meta(self, paste_id):
        cached = self._read_cache(paste_id)
        return None if cached is None else cached.meta

    async def get_paste_rendered(self, paste_id):
        cached = self._read_cache(paste_id)
        return None if cached is None else cached.rendered_paste

    async def get_paste_raw(self, paste_id):
        cached = self._read_cache(paste_id)
        return None if cached is None else cached.raw_paste


class RedisCache(BaseCache):
    _conn: Redis

    def __init__(self, app: Quart, redis_url: str):
        self._conn = None

        if Redis is None:
            raise OptionalRequirementMissing(
                "redis requirement must be installed for redis cache"
            )

        @app.while_serving
        async def handle_lifespan():
            logger.info("connecting to redis...")
            self._conn = Redis.from_url(redis_url)
            logger.info("connected to redis")
            yield
            logger.info("closing redis connection...")
            await self._conn.close()
            logger.info("closed redis connection")

    async def push_paste_all(self, paste_id, /, *, meta=None, html=None, raw=None):
        to_cache = {}

        if meta:
            to_cache[f"{paste_id}__meta"] = meta.json()
        if html:
            to_cache[f"{paste_id}__html"] = html
        if raw:
            to_cache[f"{paste_id}__raw"] = raw

        await self._conn.mset(to_cache)

    async def push_paste_meta(self, paste_id, meta):
        await self.push_paste_all(paste_id, meta=meta)

    async def get_paste_meta(self, paste_id):
        cached = await self._conn.get(f"{paste_id}__meta")
        if cached:
            return PasteMeta.parse_raw(cached)

    async def get_paste_rendered(self, paste_id):
        cached = await self._conn.get(f"{paste_id}__html")
        if cached:
            return cached.decode()

    async def get_paste_raw(self, paste_id):
        return await self._conn.get(f"{paste_id}__raw")
