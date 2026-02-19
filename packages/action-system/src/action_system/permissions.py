"""Permission checking and granting logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .models import Expiration, PermissionGrant
from .store import Store


def _compute_expires_at(expiration: Expiration) -> datetime | None:
    now = datetime.now(timezone.utc)
    match expiration:
        case Expiration.ONE_HOUR:
            return now + timedelta(hours=1)
        case Expiration.TODAY:
            # End of current UTC day
            return now.replace(hour=23, minute=59, second=59, microsecond=999999)
        case Expiration.INDEFINITE:
            return None


def _scope_matches(grant_scope: dict[str, Any], required_scope: dict[str, Any]) -> bool:
    """Check if a grant's scope covers the required scope.

    An empty grant scope is a wildcard — covers everything.
    Otherwise, every key in the grant scope must appear in the required
    scope with the same value.  This means a grant scoped to
    ``{"recipient": "bob"}`` covers ``{"recipient": "bob", "priority": "high"}``
    (the grant doesn't restrict priority), but a grant scoped to
    ``{"recipient": "bob", "cc": "alice"}`` does NOT cover
    ``{"recipient": "bob"}`` (the request doesn't satisfy the cc constraint).
    """
    if not grant_scope:
        return True
    for key, value in grant_scope.items():
        if required_scope.get(key) != value:
            return False
    return True


class PermissionManager:
    """Manages permission grants: check, grant, revoke."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def check(
        self,
        handler_id: str,
        permission_name: str,
        scope: dict[str, Any] | None = None,
    ) -> bool:
        """Check if a permission is currently granted for the given scope."""
        scope = scope or {}
        grants = self._store.get_grants(handler_id, permission_name)
        for grant in grants:
            if grant.is_expired():
                self._store.delete_grant(grant.id)
                continue
            if _scope_matches(grant.scope, scope):
                return True
        return False

    def grant(
        self,
        handler_id: str,
        permission_name: str,
        scope: dict[str, Any] | None = None,
        expiration: Expiration = Expiration.INDEFINITE,
        granted_by: str = "user",
    ) -> PermissionGrant:
        """Grant a permission. Only the human should call this."""
        grant = PermissionGrant(
            permission_name=permission_name,
            handler_id=handler_id,
            scope=scope or {},
            expiration=expiration,
            expires_at=_compute_expires_at(expiration),
            granted_by=granted_by,
        )
        self._store.save_grant(grant)
        return grant

    def revoke(self, grant_id: str) -> None:
        """Revoke a permission grant."""
        self._store.delete_grant(grant_id)

    def get_all_grants(self) -> list[PermissionGrant]:
        """Return all active (non-expired) grants."""
        grants = self._store.get_all_grants()
        active: list[PermissionGrant] = []
        for grant in grants:
            if grant.is_expired():
                self._store.delete_grant(grant.id)
            else:
                active.append(grant)
        return active
