"""Live RBAC smoke test. Requires the API and migrated infrastructure."""

import asyncio

import httpx

import _bootstrap  # noqa: F401
from app.config import get_settings


async def login(client: httpx.AsyncClient, username: str, password: str) -> tuple[str, dict]:
    response = await client.post("/api/v1/auth/login", json={
        "tenant": get_settings().auth_default_tenant,
        "username": username,
        "password": password,
    })
    response.raise_for_status()
    payload = response.json()
    return payload["access_token"], payload["user"]


async def main() -> None:
    settings = get_settings()
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8001", timeout=20, trust_env=False) as client:
        admin_token, admin = await login(client, "admin", settings.auth_admin_password)
        engineer_token, engineer = await login(client, "engineer", settings.auth_engineer_password)
        assert "tenant_admin" in admin["roles"]
        assert "developer" in engineer["roles"]
        assert "system.config.manage" not in admin["permissions"]
        assert "tenant.user.read" not in engineer["permissions"]

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        engineer_headers = {"Authorization": f"Bearer {engineer_token}"}
        assert (await client.get("/api/v1/rbac/users", headers=admin_headers)).status_code == 200
        assert (await client.get("/api/v1/rbac/users", headers=engineer_headers)).status_code == 403
        assert (await client.get("/api/v1/dashboard", headers=engineer_headers)).status_code == 200
        assert (await client.get("/api/v1/documents", headers=engineer_headers)).status_code == 200
    print("rbac_smoke=ok admin=tenant_admin engineer=developer isolation=verified")


if __name__ == "__main__":
    asyncio.run(main())
