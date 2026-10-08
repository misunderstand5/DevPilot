"""One tiny, non-business-data request to verify the configured STRONG endpoint."""
import asyncio
import sys
from pathlib import Path

import httpx
from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings


async def main():
    settings = Settings()
    client = AsyncOpenAI(
        base_url=settings.strong_model_base_url,
        api_key=settings.strong_model_api_key,
        http_client=httpx.AsyncClient(timeout=60, trust_env=False),
    )
    try:
        response = await client.chat.completions.create(
            model=settings.strong_model_name,
            messages=[{"role": "user", "content": "Reply with exactly: STRONG_OK"}],
            temperature=0,
            max_tokens=8,
        )
        content = response.choices[0].message.content or ""
        print("MODELSCOPE_OK" if "STRONG_OK" in content else "MODELSCOPE_RESPONDED")
    except Exception as exc:
        print("MODELSCOPE_FAILED:" + exc.__class__.__name__)
        raise SystemExit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
