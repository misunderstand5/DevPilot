import asyncio,time,statistics
import httpx
import redis.asyncio as redis
import _bootstrap  # noqa: F401
from app.config import get_settings

async def call(client,query,user):
    t=time.perf_counter(); r=await client.post('http://127.0.0.1:8001/api/v1/chat',json={'query':query,'user_id':user}); r.raise_for_status(); return (time.perf_counter()-t)*1000,r.json()

async def main():
    s=get_settings(); rr=redis.from_url(s.redis_url,decode_responses=True)
    keys=await rr.keys('agent:cache:*')
    if keys: await rr.delete(*keys)
    await rr.aclose()
    query='订单服务生产部署流程是什么？'
    async with httpx.AsyncClient(timeout=180, trust_env=False) as c:
        cold,_=await call(c,query,'cache-cold'); warm=[]; last=None
        for i in range(10):
            ms,last=await call(c,query,f'cache-{i}'); warm.append(ms)
    w=sorted(warm)
    print({'cold_ms':round(cold,1),'warm_p50_ms':round(statistics.median(warm),1),'warm_p95_ms':round(w[8],1),'cached_flag':last.get('cached')})

if __name__=='__main__': asyncio.run(main())
