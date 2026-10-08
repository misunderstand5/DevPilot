import pytest
from fastapi import HTTPException

from app.security import AuthUser, require_permission
from app.services.rbac import ScopeGrant, expanded_roles, permissions_for_roles, scope_allows


def test_developer_inherits_end_user_permissions():
    assert expanded_roles(["developer"]) == {"developer", "end_user"}
    permissions = permissions_for_roles(["developer"])
    assert "agent.chat.use" in permissions
    assert "trace.own.read" in permissions


def test_tenant_admin_inherits_developer_but_system_admin_is_independent():
    tenant_permissions = permissions_for_roles(["tenant_admin"])
    system_permissions = permissions_for_roles(["system_admin"])
    assert "tenant.user.create" in tenant_permissions
    assert "agent.chat.use" in tenant_permissions
    assert "system.config.manage" in system_permissions
    assert "agent.chat.use" not in system_permissions
    assert "memory.own.read" not in system_permissions


def test_scope_supports_exact_and_wildcard_grants():
    exact = [ScopeGrant("ops.service.read", "SERVICE", "order-service")]
    wildcard = [ScopeGrant("*", "SERVICE", "*")]
    assert scope_allows(exact, "ops.service.read", "SERVICE", "order-service")
    assert not scope_allows(exact, "ops.service.read", "SERVICE", "payment-service")
    assert scope_allows(wildcard, "ops.ticket.read", "SERVICE", "payment-service")


def test_require_permission_enforces_resource_scope():
    user = AuthUser(
        id="u", tenant_id="t", tenant_slug="tenant", username="dev", role="developer",
        roles=("developer",), permissions=frozenset(permissions_for_roles(["developer"])),
        scopes=(ScopeGrant("ops.service.read", "SERVICE", "order-service"),),
    )
    require_permission(user, "ops.service.read", resource_type="SERVICE", resource_key="order-service")
    with pytest.raises(HTTPException) as denied:
        require_permission(user, "ops.service.read", resource_type="SERVICE", resource_key="payment-service")
    assert denied.value.status_code == 403
