import hashlib
import json
import time
import redis.asyncio as redis
from app.config import get_settings


class RedisStore:
    def __init__(self):
        self.settings = get_settings()
        self.client = redis.from_url(self.settings.redis_url, decode_responses=True)

    async def ping(self) -> bool:
        return bool(await self.client.ping())

    @staticmethod
    def _cache_key(query: str, context_key: str, kb_version: str) -> str:
        return "agent:cache:" + hashlib.sha256(f"{kb_version}|{context_key}|{query}".encode()).hexdigest()

    async def get_cached_answer(self, query: str, context_key: str = "", kb_version: str = "v2.4"):
        key = self._cache_key(query, context_key, kb_version)
        raw = await self.client.get(key)
        return json.loads(raw) if raw else None

    async def set_cached_answer(self, query: str, value: dict, context_key: str = "", kb_version: str = "v2.4"):
        key = self._cache_key(query, context_key, kb_version)
        await self.client.set(
            key,
            json.dumps(value, ensure_ascii=False, default=str),
            ex=self.settings.cache_ttl_seconds,
        )

    async def append_session_message(self, session_id: str, message: dict):
        key = f"agent:session:{session_id}:messages"
        seq_key = f"agent:session:{session_id}:message_seq"
        if not await self.client.exists(seq_key):
            await self.client.setnx(seq_key, await self.client.llen(key))
        enriched = {**message, "_seq": await self.client.incr(seq_key)}
        await self.client.rpush(key, json.dumps(enriched, ensure_ascii=False, default=str))
        await self.client.ltrim(key, -self.settings.context_history_message_limit, -1)
        await self.client.expire(key, self.settings.session_ttl_seconds)
        await self.client.expire(seq_key, self.settings.session_ttl_seconds)
        return enriched

    async def recent_messages(self, session_id: str, limit: int = 10):
        rows = await self.client.lrange(f"agent:session:{session_id}:messages", -limit, -1)
        return [json.loads(x) for x in rows]

    async def get_conversation_state(self, session_id: str) -> dict:
        raw = await self.client.get(f"agent:session:{session_id}:state")
        return json.loads(raw) if raw else {}

    async def set_conversation_state(self, session_id: str, state: dict):
        await self.client.set(
            f"agent:session:{session_id}:state",
            json.dumps(state, ensure_ascii=False, default=str),
            ex=self.settings.session_ttl_seconds,
        )

    async def get_request_result(self, user_id: str, request_id: str) -> dict | None:
        raw = await self.client.get(f"agent:request:{user_id}:{request_id}:result")
        return json.loads(raw) if raw else None

    async def set_request_result(self, user_id: str, request_id: str, value: dict):
        await self.client.set(
            f"agent:request:{user_id}:{request_id}:result",
            json.dumps(value, ensure_ascii=False, default=str),
            ex=min(self.settings.session_ttl_seconds, 3600),
        )

    async def acquire_session_lock(self, session_id: str, token: str, ttl_seconds: int = 180) -> bool:
        return bool(await self.client.set(f"agent:session:{session_id}:lock", token, nx=True, ex=ttl_seconds))

    async def release_session_lock(self, session_id: str, token: str):
        await self.client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1, f"agent:session:{session_id}:lock", token,
        )

    async def allowed(self, user_id: str) -> bool:
        minute = int(time.time() // 60)
        key = f"agent:rate:{user_id}:{minute}"
        n = await self.client.incr(key)
        if n == 1:
            await self.client.expire(key, 70)
        return n <= self.settings.rate_limit_per_minute


redis_store = RedisStore()
