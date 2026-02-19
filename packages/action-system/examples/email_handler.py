"""Example: Email action handler demonstrating the plugin pattern."""

from __future__ import annotations

from typing import Any

from action_system import ActionHandler, ActionRequest, PermissionDef


class EmailHandler(ActionHandler):
    """Handler for sending emails.

    Defines a parameterized permission scoped by recipient.
    """

    handler_id = "email"
    name = "Email"
    permissions = [
        PermissionDef(
            name="send_email",
            description="Send an email to a recipient",
            parameters={"recipient": "Email address of the recipient"},
        ),
        PermissionDef(
            name="read_inbox",
            description="Read emails from the inbox",
            parameters={},
        ),
    ]

    def get_required_permission(
        self, action_name: str, params: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        if action_name == "send":
            return "send_email", {"recipient": params.get("to", "")}
        elif action_name == "read":
            return "read_inbox", {}
        return super().get_required_permission(action_name, params)

    def execute(self, action_name: str, params: dict[str, Any]) -> Any:
        if action_name == "send":
            # In reality, this would send an email
            return {
                "sent": True,
                "to": params["to"],
                "subject": params.get("subject", ""),
                "message_id": "msg_12345",
            }
        elif action_name == "read":
            return {
                "emails": [
                    {"from": "alice@example.com", "subject": "Hello", "unread": True},
                ]
            }
        raise ValueError(f"Unknown action: {action_name}")

    def render_request(self, request: ActionRequest) -> dict[str, Any]:
        base = super().render_request(request)
        if request.action_name == "send":
            base["display"] = {
                "title": f"Send email to {request.params.get('to', '?')}",
                "detail": f"Subject: {request.params.get('subject', '(none)')}",
                "body_preview": request.params.get("body", "")[:200],
            }
        elif request.action_name == "read":
            base["display"] = {"title": "Read inbox"}
        return base

    def as_tool_schema(self) -> dict[str, Any]:
        return {
            "tool_id": self.handler_id,
            "name": self.name,
            "actions": [
                {
                    "name": "send",
                    "description": "Send an email",
                    "parameters": {
                        "to": {"type": "string", "description": "Recipient email"},
                        "subject": {"type": "string", "description": "Email subject"},
                        "body": {"type": "string", "description": "Email body"},
                    },
                },
                {
                    "name": "read",
                    "description": "Read inbox emails",
                    "parameters": {},
                },
            ],
        }
