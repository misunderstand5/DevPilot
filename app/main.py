from pathlib import Path
import time

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.chat import router as chat_router
from app.api.auth import router as auth_router
from app.api.documents import router as doc_router
from app.api.sessions import router as session_router
from app.api.dashboard import router as dashboard_router
from app.api.memories import router as memory_router
from app.api.integrations import router as integration_router
from app.api.rbac import router as rbac_router
from app.config import get_settings
from app.db import session_scope
from app.redis_store import redis_store

settings = get_settings()
if settings.insecure_production_auth:
    raise RuntimeError("AUTH_SECRET_KEY must be changed before APP_ENV=production")
app = FastAPI(title="DevPilot Agent API", version="0.1.0")
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(doc_router)
app.include_router(session_router)
app.include_router(dashboard_router)
app.include_router(memory_router)
app.include_router(integration_router)
app.include_router(rbac_router)

web_dir = Path(__file__).resolve().parent / "web"
app.mount("/static", StaticFiles(directory=web_dir), name="static")


@app.get("/", include_in_schema=False)
async def web_console():
    return FileResponse(web_dir / "index.html")


@app.get("/health")
async def health():
    async def probe(name, call):
        started = time.perf_counter()
        try:
            detail = await call()
            return {"status": "healthy", "latency_ms": int((time.perf_counter() - started) * 1000), **(detail or {})}
        except Exception as exc:
            return {"status": "unavailable", "latency_ms": int((time.perf_counter() - started) * 1000),
                    "error": exc.__class__.__name__}

    async def mysql_probe():
        async with session_scope() as db:
            await db.execute(text("SELECT 1"))
        return {}

    async def redis_probe():
        if not await redis_store.ping():
            raise RuntimeError("redis ping failed")
        return {}

    async def qdrant_probe():
        async with httpx.AsyncClient(timeout=2.5, trust_env=False) as client:
            response = await client.get(settings.qdrant_url.rstrip("/") + "/collections")
            response.raise_for_status()
            names = [item["name"] for item in response.json().get("result", {}).get("collections", [])]
            required = [settings.qdrant_collection, settings.qdrant_memory_collection]
            return {"collections": names, "required_collections_ready": all(name in names for name in required)}

    async def model_probe():
        async with httpx.AsyncClient(timeout=2.5, trust_env=False) as client:
            response = await client.get(settings.resolved_local_model_base_url.rstrip("/") + "/models")
            response.raise_for_status()
            return {"model": settings.resolved_local_model_name}

    mysql = await probe("mysql", mysql_probe)
    redis = await probe("redis", redis_probe)
    qdrant = await probe("qdrant", qdrant_probe)
    local_model = await probe("local_model", model_probe)
    local_model_ok = local_model["status"] == "healthy"
    ready = all(component["status"] == "healthy" for component in (mysql, redis, qdrant))
    return {
        "app": "ok", "ready": ready,
        "components": {
            "mysql": mysql, "redis": redis, "qdrant": qdrant, "local_model": local_model,
            "github_mcp": {
                "status": "configured" if settings.github_mcp_enabled and settings.github_mcp_url else "disabled",
                "required": False,
            },
        },
        "mysql": mysql["status"] == "healthy",
        "redis": redis["status"] == "healthy",
        "qdrant": qdrant["status"] == "healthy",
        "llm_mode": settings.llm_mode,
        "llm_model": settings.resolved_local_model_name,
        "local_model_online": local_model_ok,
        "generation_mode": "local_model" if local_model_ok else "deterministic_fallback",
        "model_roles": {
            "LOCAL": settings.resolved_local_model_name,
            "STRONG": settings.strong_model_name if settings.strong_model_configured else None,
        },
        "cloud_internal_data_allowed": settings.allow_cloud_internal_data,
    }


@app.get("/ready", include_in_schema=False)
async def readiness():
    result = await health()
    return {"ready": result["ready"], "components": result["components"]}
