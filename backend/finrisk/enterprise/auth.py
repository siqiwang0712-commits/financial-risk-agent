from __future__ import annotations

from .domain import Principal, Role

PERMISSIONS = {
    Role.ADMIN: {"read", "write", "review", "configure", "manage_users"},
    Role.RISK_MANAGER: {"read", "write", "review", "configure"},
    Role.ANALYST: {"read", "write"},
    Role.REVIEWER: {"read", "review"},
    Role.VIEWER: {"read"},
}


def authorize(principal: Principal, permission: str, organization_id: str) -> None:
    if principal.organization_id != organization_id:
        raise PermissionError("cross-organization access denied")
    if permission not in PERMISSIONS[principal.role]:
        raise PermissionError(f"role {principal.role} lacks {permission}")
