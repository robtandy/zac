"""Core action system — the main entry point."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .exceptions import (
    ActionNotFoundError,
    HandlerExecutionError,
    HandlerNotFoundError,
)
from .handler import ActionHandler
from .models import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    Expiration,
    PermissionGrant,
)
from .notifications import (
    ACTION_COMPLETED,
    ACTION_ENQUEUED,
    ACTION_FAILED,
    PERMISSION_NEEDED,
    EventBus,
)
from .permissions import PermissionManager
from .store import Store


class ActionSystem:
    """Main entry point for the action/permission system.

    Register handlers, request actions, manage permissions.
    Actions are executed immediately if permitted, or enqueued for approval.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._store = Store(db_path)
        self._permissions = PermissionManager(self._store)
        self._handlers: dict[str, ActionHandler] = {}
        self.events = EventBus()

    def close(self) -> None:
        """Close the backing store."""
        self._store.close()

    # ── Handler Registration ──

    def register_handler(self, handler: ActionHandler) -> None:
        """Register an action handler."""
        # Stamp handler_id onto its permission defs
        for perm in handler.permissions:
            perm.handler_id = handler.handler_id
        self._handlers[handler.handler_id] = handler

    def get_handler(self, handler_id: str) -> ActionHandler:
        try:
            return self._handlers[handler_id]
        except KeyError:
            raise HandlerNotFoundError(handler_id)

    def list_handlers(self) -> list[ActionHandler]:
        return list(self._handlers.values())

    # ── Action Requests ──

    def request_action(
        self,
        handler_id: str,
        action_name: str,
        params: dict[str, Any] | None = None,
    ) -> ActionResult:
        """Request an action. Executes immediately if permitted, otherwise enqueues."""
        params = params or {}
        handler = self.get_handler(handler_id)

        # Determine required permission
        perm_name, perm_scope = handler.get_required_permission(action_name, params)

        # Create the action request
        request = ActionRequest(
            handler_id=handler_id,
            action_name=action_name,
            params=params,
            permission_name=perm_name,
            permission_scope=perm_scope,
        )

        # Check permission
        if self._permissions.check(handler_id, perm_name, perm_scope):
            return self._execute(handler, request)
        else:
            # Enqueue for approval
            request.status = ActionStatus.PENDING
            self._store.save_action(request)
            self.events.emit(
                ACTION_ENQUEUED, action=request, handler=handler
            )
            self.events.emit(
                PERMISSION_NEEDED,
                action=request,
                handler=handler,
                permission_name=perm_name,
                scope=perm_scope,
            )
            return ActionResult(
                action_id=request.id,
                status=ActionStatus.PENDING,
            )

    def _execute(
        self, handler: ActionHandler, request: ActionRequest
    ) -> ActionResult:
        """Execute a handler action and persist the result."""
        request.status = ActionStatus.RUNNING
        self._store.save_action(request)
        try:
            result = handler.execute(request.action_name, request.params)
            request.status = ActionStatus.COMPLETED
            request.result = result
            request.completed_at = datetime.now(timezone.utc)
            self._store.save_action(request)
            self.events.emit(ACTION_COMPLETED, action=request, handler=handler)
            return ActionResult(
                action_id=request.id,
                status=ActionStatus.COMPLETED,
                result=result,
            )
        except Exception as exc:
            request.status = ActionStatus.FAILED
            request.error = str(exc)
            request.completed_at = datetime.now(timezone.utc)
            self._store.save_action(request)
            self.events.emit(ACTION_FAILED, action=request, handler=handler, error=exc)
            return ActionResult(
                action_id=request.id,
                status=ActionStatus.FAILED,
                error=str(exc),
            )

    def approve_action(self, action_id: str) -> ActionResult:
        """Approve and execute a pending action.

        Call this after the user has granted the required permission.
        """
        request = self._store.get_action(action_id)
        if request is None:
            raise ActionNotFoundError(action_id)

        if request.status != ActionStatus.PENDING:
            return ActionResult(
                action_id=request.id,
                status=request.status,
                result=request.result,
                error=request.error,
            )

        handler = self.get_handler(request.handler_id)

        # Re-check permission (it should be granted now)
        if not self._permissions.check(
            request.handler_id, request.permission_name, request.permission_scope
        ):
            return ActionResult(
                action_id=request.id,
                status=ActionStatus.PENDING,
                error="Permission still not granted",
            )

        # Mark as approved before execution begins
        request.status = ActionStatus.APPROVED
        self._store.save_action(request)

        return self._execute(handler, request)

    def get_action_status(self, action_id: str) -> ActionRequest:
        request = self._store.get_action(action_id)
        if request is None:
            raise ActionNotFoundError(action_id)
        return request

    def get_pending_actions(self) -> list[ActionRequest]:
        return self._store.get_pending_actions()

    # ── Permission Management ──

    def check_permission(
        self,
        handler_id: str,
        permission_name: str,
        scope: dict[str, Any] | None = None,
    ) -> bool:
        """Check if a permission is granted. Agent can call this."""
        return self._permissions.check(handler_id, permission_name, scope)

    def grant_permission(
        self,
        handler_id: str,
        permission_name: str,
        scope: dict[str, Any] | None = None,
        expiration: Expiration = Expiration.INDEFINITE,
        granted_by: str = "user",
    ) -> PermissionGrant:
        """Grant a permission. Only the human should call this."""
        return self._permissions.grant(
            handler_id, permission_name, scope, expiration, granted_by
        )

    def revoke_permission(self, grant_id: str) -> None:
        """Revoke a permission grant."""
        self._permissions.revoke(grant_id)

    def get_all_grants(self) -> list[PermissionGrant]:
        return self._permissions.get_all_grants()

    # ── Tool Schemas ──

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return tool schemas for all registered handlers."""
        return [h.as_tool_schema() for h in self._handlers.values()]
