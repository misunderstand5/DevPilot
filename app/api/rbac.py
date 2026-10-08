import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import session_scope
from app.security import AuthUser, current_user, require_permission
from app.services.rbac import ROLE_INHERITANCE, permissions_for_roles


router = APIRouter(prefix="/api/v1/rbac", tags=["rbac"])


class RoleAssignment(BaseModel):
    role: str = Field(pattern="^(end_user|developer)$")


class ScopeAssignment(BaseModel):
    permission: str = Field(min_length=1, max_length=128)
    resource_type: str = Field(pattern="^(SERVICE|REPOSITORY)$")
    resource_key: str = Field(min_length=1, max_length=255)


async def _tenant_user(user_id: str, actor: AuthUser):
    async with session_scope() as db:
        result = await db.execute(text("""SELECT id,username,status FROM app_user
            WHERE id=:id AND tenant_id=:tenant LIMIT 1"""), {"id": user_id, "tenant": actor.tenant_id})
        row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="user not found in current tenant")
    return row


@router.get("/roles")
async def roles(actor: AuthUser = Depends(current_user)):
    require_permission(actor, "tenant.user.read")
    return [{"code": role, "inherits": list(ROLE_INHERITANCE[role]),
             "permissions": sorted(permissions_for_roles((role,)))}
            for role in ("end_user", "developer", "tenant_admin")]


@router.get("/users")
async def users(actor: AuthUser = Depends(current_user)):
    require_permission(actor, "tenant.user.read")
    async with session_scope() as db:
        result = await db.execute(text("""SELECT u.id,u.username,u.status,
            GROUP_CONCAT(r.code ORDER BY r.code) AS roles
            FROM app_user u LEFT JOIN rbac_user_role ur ON ur.user_id=u.id
            LEFT JOIN rbac_role r ON r.id=ur.role_id
            WHERE u.tenant_id=:tenant GROUP BY u.id,u.username,u.status ORDER BY u.username"""),
                                  {"tenant": actor.tenant_id})
        rows = result.fetchall()
    return [{"id": str(row.id), "username": row.username, "status": row.status,
             "roles": (row.roles or "end_user").split(",")} for row in rows]


@router.put("/users/{user_id}/role")
async def assign_role(user_id: str, req: RoleAssignment, actor: AuthUser = Depends(current_user)):
    require_permission(actor, "tenant.role.assign")
    target = await _tenant_user(user_id, actor)
    async with session_scope() as db:
        protected = await db.execute(text("""SELECT COUNT(*) FROM rbac_user_role ur
            JOIN rbac_role r ON r.id=ur.role_id
            WHERE ur.user_id=:user AND r.code IN ('tenant_admin','system_admin')"""), {"user": user_id})
        if int(protected.scalar() or 0):
            raise HTTPException(status_code=403, detail="protected administrator roles require platform workflow")
        await db.execute(text("""DELETE ur FROM rbac_user_role ur JOIN rbac_role r ON r.id=ur.role_id
            WHERE ur.user_id=:user AND r.code IN ('end_user','developer')"""), {"user": user_id})
        await db.execute(text("""INSERT INTO rbac_user_role(user_id,role_id,assigned_by)
            SELECT :user,id,:actor FROM rbac_role WHERE code=:role"""),
                         {"user": user_id, "actor": actor.id, "role": req.role})
        await db.execute(text("""INSERT INTO rbac_audit_log(tenant_id,actor_user_id,action,target_type,target_id,detail_json)
            VALUES(:tenant,:actor,'role.assign','user',:user,:detail)"""), {
                "tenant": actor.tenant_id, "actor": actor.id, "user": user_id,
                "detail": json.dumps({"role": req.role}, ensure_ascii=False),
            })
    return {"id": str(target.id), "username": target.username, "role": req.role}


@router.post("/users/{user_id}/scopes")
async def grant_scope(user_id: str, req: ScopeAssignment, actor: AuthUser = Depends(current_user)):
    manager = "service.authorization.manage" if req.resource_type == "SERVICE" else "repository.authorization.manage"
    require_permission(actor, manager)
    await _tenant_user(user_id, actor)
    async with session_scope() as db:
        await db.execute(text("""INSERT INTO rbac_resource_scope(user_id,permission_code,resource_type,resource_key)
            VALUES(:user,:permission,:type,:key)
            ON DUPLICATE KEY UPDATE expires_at=NULL"""), {
                "user": user_id, "permission": req.permission,
                "type": req.resource_type, "key": req.resource_key,
            })
        await db.execute(text("""INSERT INTO rbac_audit_log(tenant_id,actor_user_id,action,target_type,target_id,detail_json)
            VALUES(:tenant,:actor,'scope.grant',:type,:key,:detail)"""), {
                "tenant": actor.tenant_id, "actor": actor.id, "type": req.resource_type,
                "key": req.resource_key, "detail": json.dumps({"user_id": user_id, "permission": req.permission}),
            })
    return {"user_id": user_id, **req.model_dump()}


@router.delete("/users/{user_id}/scopes")
async def revoke_scope(user_id: str, req: ScopeAssignment, actor: AuthUser = Depends(current_user)):
    manager = "service.authorization.manage" if req.resource_type == "SERVICE" else "repository.authorization.manage"
    require_permission(actor, manager)
    await _tenant_user(user_id, actor)
    async with session_scope() as db:
        await db.execute(text("""DELETE FROM rbac_resource_scope
            WHERE user_id=:user AND permission_code=:permission AND resource_type=:type AND resource_key=:key"""),
                         {"user": user_id, "permission": req.permission,
                          "type": req.resource_type, "key": req.resource_key})
    return {"deleted": True}
