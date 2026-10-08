import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from fastapi import Header, HTTPException
from sqlalchemy import text

from app.config import get_settings
from app.db import session_scope


PBKDF2_ITERATIONS = 310_000


@dataclass(frozen=True)
class AuthUser:
    id: str
    tenant_id: str
    tenant_slug: str
    username: str
    role: str


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), base64.urlsafe_b64decode(salt), int(iterations)
        )
        return hmac.compare_digest(base64.urlsafe_b64encode(actual).decode(), expected)
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_access_token(user: AuthUser) -> str:
    settings = get_settings()
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({
        "iss": "devpilot", "sub": user.id, "tenant_id": user.tenant_id,
        "tenant_slug": user.tenant_slug, "username": user.username, "role": user.role,
        "iat": now, "exp": now + settings.auth_token_minutes * 60,
    }, separators=(",", ":")).encode())
    signature = _b64(hmac.new(settings.auth_secret_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def decode_access_token(token: str) -> AuthUser:
    settings = get_settings()
    try:
        header, payload, signature = token.split(".")
        expected = _b64(hmac.new(
            settings.auth_secret_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256
        ).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        data = json.loads(_unb64(payload))
        if data.get("iss") != "devpilot" or int(data["exp"]) < int(time.time()):
            raise ValueError("expired token")
        return AuthUser(
            id=str(data["sub"]), tenant_id=str(data["tenant_id"]),
            tenant_slug=str(data["tenant_slug"]), username=str(data["username"]), role=str(data["role"]),
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="invalid or expired access token") from exc


async def current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="bearer token required")
    user = decode_access_token(authorization.split(" ", 1)[1].strip())
    async with session_scope() as db:
        result = await db.execute(text("""
            SELECT u.id,u.tenant_id,t.slug AS tenant_slug,u.username,u.role,u.status
            FROM app_user u JOIN tenant t ON t.id=u.tenant_id
            WHERE u.id=:id LIMIT 1
        """), {"id": user.id})
        row = result.first()
    if not row or row.status != "ACTIVE":
        raise HTTPException(status_code=401, detail="user disabled or not found")
    return AuthUser(id=row.id, tenant_id=row.tenant_id, tenant_slug=row.tenant_slug,
                    username=row.username, role=row.role)


def require_admin(user: AuthUser):
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="admin role required")
