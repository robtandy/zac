"""Base class for action handlers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import ActionRequest, PermissionDef


class ActionHandler(ABC):
    """Base class for action handlers.

    Subclasses must define:
    - `handler_id`: unique identifier
    - `name`: human-readable name
    - `permissions`: list of PermissionDefs this handler requires
    - `execute()`: perform the action
    """

    handler_id: str
    name: str
    permissions: list[PermissionDef]

    @abstractmethod
    def execute(self, action_name: str, params: dict[str, Any]) -> Any:
        """Execute an action. Return the result."""
        ...

    def get_required_permission(
        self, action_name: str, params: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        """Return (permission_name, scope) required for this action.

        Override to implement custom permission logic. Default returns
        the first permission with no scope.
        """
        if self.permissions:
            return self.permissions[0].name, {}
        raise ValueError(f"No permissions defined for handler {self.handler_id}")

    def render_request(self, request: ActionRequest) -> dict[str, Any]:
        """Return UI display data for an action request.

        Override to customize how this handler's requests appear in the UI.
        Default returns a simple dict with the action info.
        """
        return {
            "handler": self.name,
            "action": request.action_name,
            "params": request.params,
            "status": request.status.value,
            "permission_needed": request.permission_name,
            "permission_scope": request.permission_scope,
        }

    def as_tool_schema(self) -> dict[str, Any]:
        """Return a tool definition dict for AI agent registration.

        Override to customize. Default builds from handler metadata.
        """
        actions: list[dict[str, Any]] = []
        for perm in self.permissions:
            actions.append({
                "name": perm.name,
                "description": perm.description,
                "parameters": perm.parameters,
            })

        return {
            "tool_id": self.handler_id,
            "name": self.name,
            "actions": actions,
        }
