import asyncio
import time
import httpx
import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import _bootstrap  # noqa: F401
from app.config import get_settings

async def main():
    s = get_settings()
    deadline = time.time() + 180
    last = None
    while time.time() < deadline:
        try:
            engine = create_async_engine(s.sqlalchemy_url, pool_pre_ping=True)
            async with engine.connect() as c:
                await c.execute(text('SELECT 1'))
            await engine.dispose()
            rr = redis.from_url(s.redis_url, decode_responses=True)
            assert await rr.ping()
            await rr.aclose()
            async with httpx.AsyncClient(timeout=5, trust_env=False) as c:
                x = await c.get(s.qdrant_url + '/collections')
                x.raise_for_status()
            print('INFRA READY: MySQL + Redis + Qdrant')
            return
        except Exception as exc:
            last = exc
            print('waiting infra...', type(exc).__name__, str(exc)[:120])
            await asyncio.sleep(3)
    raise SystemExit(f'infra not ready after 180s: {last}')

if __name__ == '__main__':
    asyncio.run(main())
