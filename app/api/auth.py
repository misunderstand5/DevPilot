import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import session_scope
from app.security import AuthUser, create_access_token, current_user, hash_password, require_admin, verify_password


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    tenant: str = Field(default="devpilot", min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=200)
    role: str = Field(default="MEMBER", pattern="^(ADMIN|MEMBER)$")


def public_user(user: AuthUser) -> dict:
    return {"id": user.id, "tenant_id": user.tenant_id, "tenant": user.tenant_slug,
            "username": user.username, "role": user.role}


@router.post("/login")
async def login(req: LoginRequest):
    async with session_scope() as db:
        result = await db.execute(text("""
            SELECT u.id,u.tenant_id,t.slug AS tenant_slug,u.username,u.password_hash,u.role,u.status
            FROM app_user u JOIN tenant t ON t.id=u.tenant_id
            WHERE t.slug=:tenant AND u.username=:username LIMIT 1
        """), {"tenant": req.tenant.strip(), "username": req.username.strip()})
        row = result.first()
    if not row or row.status != "ACTIVE" or not verify_password(req.password, row.password_hash):
        raise HTTPException(status_code=401, detail="invalid tenant, username or password")
    user = AuthUser(id=row.id, tenant_id=row.tenant_id, tenant_slug=row.tenant_slug,
                    username=row.username, role=row.role)
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": public_user(user)}


@router.get("/me")
async def me(user: AuthUser = Depends(current_user)):
    return public_user(user)


@router.post("/users")
async def create_user(req: CreateUserRequest, admin: AuthUser = Depends(current_user)):
    require_admin(admin)
    user_id = str(uuid.uuid4())
    try:
        async with session_scope() as db:
            await db.execute(text("""
                INSERT INTO app_user(id,tenant_id,username,password_hash,role,status)
                VALUES(:id,:tenant,:username,:password,:role,'ACTIVE')
            """), {"id": user_id, "tenant": admin.tenant_id, "username": req.username.strip(),
                    "password": hash_password(req.password), "role": req.role})
    except Exception as exc:
        raise HTTPException(status_code=409, detail="username already exists in this tenant") from exc
    return {"id": user_id, "tenant_id": admin.tenant_id, "username": req.username.strip(), "role": req.role}
