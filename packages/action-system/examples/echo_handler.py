"""Echo handler — simplest possible handler for testing and UI integration."""

from __future__ import annotations

from typing import Any

from action_system import ActionHandler, ActionRequest, PermissionDef


class EchoHandler(ActionHandler):
    """Echoes back whatever you send it. Perfect for testing the full flow."""

    handler_id = "echo"
    name = "Echo"
    permissions = [
        PermissionDef(
            name="echo",
            description="Echo a message back",
            parameters={"channel": "Where to echo (optional)"},
        ),
    ]

    def get_required_permission(
        self, action_name: str, params: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        scope: dict[str, Any] = {}
        if channel := params.get("channel"):
            scope["channel"] = channel
        return "echo", scope

    def execute(self, action_name: str, params: dict[str, Any]) -> Any:
        message = params.get("message", "")
        channel = params.get("channel", "default")
        return {
            "echoed": True,
            "message": message,
            "channel": channel,
        }

    def render_request(self, request: ActionRequest) -> dict[str, Any]:
        base = super().render_request(request)
        base["display"] = {
            "title": "Echo message",
            "detail": request.params.get("message", "(empty)"),
            "channel": request.params.get("channel", "default"),
        }
        return base

    def as_tool_schema(self) -> dict[str, Any]:
        return {
            "tool_id": self.handler_id,
            "name": self.name,
            "actions": [
                {
                    "name": "echo",
                    "description": "Echo a message back",
                    "parameters": {
                        "message": {"type": "string", "description": "Message to echo"},
                        "channel": {"type": "string", "description": "Channel (optional)"},
                    },
                },
            ],
        }
