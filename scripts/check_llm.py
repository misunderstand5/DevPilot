import asyncio
from openai import AsyncOpenAI
import _bootstrap  # noqa: F401
from app.config import get_settings
import httpx
async def main():
    s=get_settings()
    if s.llm_mode=='mock':
        print('LLM_MODE=mock; switch .env to openai_compatible after vLLM is ready.')
        return
    c=AsyncOpenAI(base_url=s.llm_base_url,api_key=s.llm_api_key,http_client=httpx.AsyncClient(trust_env=False),)
    r=await c.chat.completions.create(model=s.llm_model,messages=[{'role':'user','content':'只回复 OK'}],max_tokens=10,temperature=0)
    print('LLM OK:',r.choices[0].message.content)

if __name__=='__main__': asyncio.run(main())
