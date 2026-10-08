from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import bindparam, text

from app.db import session_scope


ROLE_INHERITANCE = {
    "end_user": (),
    "developer": ("end_user",),
    "tenant_admin": ("developer",),
    # system_admin is deliberately independent from tenant content roles.
    "system_admin": (),
}

ROLE_PERMISSIONS = {
    "end_user": {
        "agent.chat.use",
        "session.own.read", "session.own.write", "session.own.delete",
        "memory.own.read", "memory.own.write", "memory.own.delete",
        "kb.document.read",
        "ops.service.read", "ops.deployment.read", "ops.incident.read", "ops.ticket.read",
        "mcp.github.commit.read",
    },
    "developer": {
        "agent.config.own.create", "agent.config.own.update", "agent.config.own.delete",
        "trace.own.read", "eval.own.execute", "eval.own.read", "mcp.integration.own.test",
    },
    "tenant_admin": {
        "tenant.user.read", "tenant.user.create", "tenant.user.disable", "tenant.role.assign",
        "tenant.analytics.read", "tenant.audit.metadata.read",
        "kb.document.create", "kb.document.update", "kb.document.delete", "kb.acl.manage",
        "kb.document.manage_all", "agent.config.tenant.publish",
        "service.authorization.manage", "repository.authorization.manage",
    },
    "system_admin": {
        "tenant.lifecycle.manage", "system.health.read", "system.config.manage",
        "model.provider.manage", "mcp.server.manage", "observability.metrics.read",
        "observability.logs.read", "observability.traces.read", "cluster.resource.read",
        "cluster.config.manage", "audit.platform.read",
    },
}

LEGACY_ROLE_MAP = {"ADMIN": "tenant_admin", "MEMBER": "end_user"}


def expanded_roles(roles: Iterable[str]) -> set[str]:
    expanded: set[str] = set()

    def visit(role: str) -> None:
        if role in expanded:
            return
        expanded.add(role)
        for parent in ROLE_INHERITANCE.get(role, ()):
            visit(parent)

    for item in roles:
        visit(item)
    return expanded


def permissions_for_roles(roles: Iterable[str]) -> set[str]:
    permissions: set[str] = set()
    for role in expanded_roles(roles):
        permissions.update(ROLE_PERMISSIONS.get(role, set()))
    return permissions


@dataclass(frozen=True)
class ScopeGrant:
    permission: str
    resource_type: str
    resource_key: str


async def load_user_authorization(user_id: str, legacy_role: str) -> tuple[tuple[str, ...], frozenset[str], tuple[ScopeGrant, ...]]:
    """Load normalized RBAC state, with a safe migration fallback."""
    fallback_role = LEGACY_ROLE_MAP.get(legacy_role, legacy_role.lower())
    try:
        async with session_scope() as db:
            role_rows = await db.execute(text("""
                SELECT r.code FROM rbac_user_role ur
                JOIN rbac_role r ON r.id=ur.role_id
                WHERE ur.user_id=:user AND (ur.expires_at IS NULL OR ur.expires_at>NOW())
            """), {"user": user_id})
            roles = tuple(sorted({str(row[0]) for row in role_rows})) or (fallback_role,)
            permission_rows = await db.execute(text("""
                SELECT DISTINCT p.code FROM rbac_user_role ur
                JOIN rbac_role_permission rp ON rp.role_id=ur.role_id
                JOIN rbac_permission p ON p.id=rp.permission_id
                WHERE ur.user_id=:user AND (ur.expires_at IS NULL OR ur.expires_at>NOW())
            """), {"user": user_id})
            permissions = {str(row[0]) for row in permission_rows}
            # Inheritance is evaluated in application code, so custom database
            # role rows can coexist with the four built-in roles.
            permissions.update(permissions_for_roles(roles))
            scope_rows = await db.execute(text("""
                SELECT permission_code,resource_type,resource_key
                FROM rbac_resource_scope
                WHERE user_id=:user AND (expires_at IS NULL OR expires_at>NOW())
            """), {"user": user_id})
            scopes = tuple(ScopeGrant(str(row[0]), str(row[1]), str(row[2])) for row in scope_rows)
            return roles, frozenset(permissions), scopes
    except Exception:
        roles = (fallback_role,)
        return roles, frozenset(permissions_for_roles(roles)), ()


def scope_allows(scopes: Iterable[ScopeGrant | dict], permission: str, resource_type: str, resource_key: str) -> bool:
    for scope in scopes:
        if isinstance(scope, dict):
            scope_permission = scope.get("permission") or scope.get("permission_code")
            scope_type = scope.get("resource_type")
            scope_key = scope.get("resource_key")
        else:
            scope_permission, scope_type, scope_key = scope.permission, scope.resource_type, scope.resource_key
        if scope_permission in {permission, "*"} and scope_type in {resource_type, "*"} and scope_key in {resource_key, "*"}:
            return True
    return False


async def accessible_service_names(user) -> set[str] | None:
    """None means tenant-wide; an empty set means no authorized service."""
    if "service.authorization.manage" in user.permissions:
        return None
    keys = {
        scope.resource_key for scope in user.scopes
        if scope.resource_type == "SERVICE"
        and scope.permission in {"*", "ops.service.read", "ops.deployment.read", "ops.incident.read", "ops.ticket.read"}
    }
    if "*" in keys:
        return None
    return keys
