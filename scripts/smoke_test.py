import asyncio
import os
import httpx

API_URL = os.getenv("DEVPILOT_API_URL", "http://127.0.0.1:8001").rstrip("/")


def print_response(response: httpx.Response):
    try:
        print(response.json())
    except ValueError:
        print(response.text or "<empty response body>")

async def main():
    async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
        h = await client.get(f'{API_URL}/health')
        print('HEALTH', h.status_code)
        print_response(h)
        h.raise_for_status()
        for query in [
            '订单服务怎么部署？',
            'user/login 密码错误是什么错误码？',
            'order-service 最近7天部署情况怎么样？',
            '现在有哪些未解决故障？',
        ]:
            r = await client.post(f'{API_URL}/api/v1/chat', json={'query':query,'user_id':'smoke-user'})
            print('\nQ:', query)
            print('HTTP', r.status_code)
            print_response(r)
            r.raise_for_status()

if __name__ == '__main__':
    asyncio.run(main())
