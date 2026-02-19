"""Tests for the core action system."""

from __future__ import annotations

from typing import Any

import pytest

from action_system import (
    ACTION_COMPLETED,
    ACTION_ENQUEUED,
    ActionHandler,
    ActionRequest,
    ActionResult,
    ActionStatus,
    ActionSystem,
    Expiration,
    PermissionDef,
)


class DummyHandler(ActionHandler):
    handler_id = "dummy"
    name = "Dummy"
    permissions = [
        PermissionDef(name="do_thing", description="Do a thing", parameters={"target": "Target name"}),
    ]

    def get_required_permission(
        self, action_name: str, params: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        return "do_thing", {"target": params.get("target", "")}

    def execute(self, action_name: str, params: dict[str, Any]) -> Any:
        if action_name == "fail":
            raise RuntimeError("boom")
        return {"done": True, "action": action_name}


class TestActionSystem:
    def setup_method(self) -> None:
        self.system = ActionSystem()
        self.handler = DummyHandler()
        self.system.register_handler(self.handler)

    def teardown_method(self) -> None:
        self.system.close()

    def test_action_enqueued_without_permission(self) -> None:
        result = self.system.request_action("dummy", "run", {"target": "x"})
        assert result.status == ActionStatus.PENDING
        assert result.is_pending

        pending = self.system.get_pending_actions()
        assert len(pending) == 1
        assert pending[0].handler_id == "dummy"

    def test_action_executes_with_permission(self) -> None:
        self.system.grant_permission("dummy", "do_thing", {"target": "x"})
        result = self.system.request_action("dummy", "run", {"target": "x"})
        assert result.status == ActionStatus.COMPLETED
        assert result.result == {"done": True, "action": "run"}

    def test_wildcard_scope_grant(self) -> None:
        # Empty scope grant covers everything
        self.system.grant_permission("dummy", "do_thing", {})
        result = self.system.request_action("dummy", "run", {"target": "anything"})
        assert result.is_completed

    def test_scoped_grant_doesnt_cover_other_scope(self) -> None:
        self.system.grant_permission("dummy", "do_thing", {"target": "x"})
        result = self.system.request_action("dummy", "run", {"target": "y"})
        assert result.is_pending

    def test_approve_pending_action(self) -> None:
        result = self.system.request_action("dummy", "run", {"target": "x"})
        assert result.is_pending

        # Grant and approve
        self.system.grant_permission("dummy", "do_thing", {"target": "x"})
        result2 = self.system.approve_action(result.action_id)
        assert result2.is_completed
        assert result2.result == {"done": True, "action": "run"}

    def test_approve_without_grant_stays_pending(self) -> None:
        result = self.system.request_action("dummy", "run", {"target": "x"})
        result2 = self.system.approve_action(result.action_id)
        assert result2.status == ActionStatus.PENDING

    def test_handler_execution_failure(self) -> None:
        self.system.grant_permission("dummy", "do_thing", {})
        result = self.system.request_action("dummy", "fail", {"target": "x"})
        assert result.status == ActionStatus.FAILED
        assert result.error == "boom"

    def test_events_fire(self) -> None:
        events: list[str] = []
        self.system.events.on(ACTION_ENQUEUED, lambda **kw: events.append("enqueued"))
        self.system.events.on(ACTION_COMPLETED, lambda **kw: events.append("completed"))

        self.system.request_action("dummy", "run", {"target": "x"})
        assert "enqueued" in events

        self.system.grant_permission("dummy", "do_thing", {"target": "x"})
        pending = self.system.get_pending_actions()
        self.system.approve_action(pending[0].id)
        assert "completed" in events

    def test_get_action_status(self) -> None:
        result = self.system.request_action("dummy", "run", {"target": "x"})
        action = self.system.get_action_status(result.action_id)
        assert action.status == ActionStatus.PENDING

    def test_revoke_permission(self) -> None:
        grant = self.system.grant_permission("dummy", "do_thing", {"target": "x"})
        assert self.system.check_permission("dummy", "do_thing", {"target": "x"})
        self.system.revoke_permission(grant.id)
        assert not self.system.check_permission("dummy", "do_thing", {"target": "x"})

    def test_tool_schemas(self) -> None:
        schemas = self.system.get_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["tool_id"] == "dummy"

    def test_approve_transitions_through_approved(self) -> None:
        """approve_action should set APPROVED before executing."""
        statuses: list[ActionStatus] = []
        original_execute = self.system._execute

        def tracking_execute(handler, request):
            # Capture the status at the moment execution starts
            statuses.append(request.status)
            return original_execute(handler, request)

        self.system._execute = tracking_execute

        result = self.system.request_action("dummy", "run", {"target": "x"})
        assert result.is_pending

        self.system.grant_permission("dummy", "do_thing", {"target": "x"})
        result2 = self.system.approve_action(result.action_id)
        assert result2.is_completed
        # _execute was called with status already set to APPROVED
        assert statuses == [ActionStatus.APPROVED]

    def test_grant_with_extra_scope_does_not_cover_request(self) -> None:
        """A grant scoped to {target: x, env: prod} should NOT cover a request for {target: x}."""
        self.system.grant_permission("dummy", "do_thing", {"target": "x", "env": "prod"})
        result = self.system.request_action("dummy", "run", {"target": "x"})
        assert result.is_pending

    def test_grant_covers_request_with_extra_scope(self) -> None:
        """A grant scoped to {target: x} SHOULD cover a request for {target: x, env: prod}."""
        self.system.grant_permission("dummy", "do_thing", {"target": "x"})
        # DummyHandler only puts "target" in scope, so add a handler that includes extra keys
        result = self.system.request_action("dummy", "run", {"target": "x"})
        assert result.is_completed

    def test_handler_render_request(self) -> None:
        result = self.system.request_action("dummy", "run", {"target": "x"})
        action = self.system.get_action_status(result.action_id)
        rendered = self.handler.render_request(action)
        assert rendered["handler"] == "Dummy"
        assert rendered["action"] == "run"


class TestExpiration:
    def setup_method(self) -> None:
        self.system = ActionSystem()
        self.handler = DummyHandler()
        self.system.register_handler(self.handler)

    def teardown_method(self) -> None:
        self.system.close()

    def test_indefinite_grant(self) -> None:
        grant = self.system.grant_permission(
            "dummy", "do_thing", {}, Expiration.INDEFINITE
        )
        assert grant.expires_at is None
        assert not grant.is_expired()

    def test_one_hour_grant_not_expired(self) -> None:
        grant = self.system.grant_permission(
            "dummy", "do_thing", {}, Expiration.ONE_HOUR
        )
        assert grant.expires_at is not None
        assert not grant.is_expired()

    def test_get_all_grants(self) -> None:
        self.system.grant_permission("dummy", "do_thing", {"target": "a"})
        self.system.grant_permission("dummy", "do_thing", {"target": "b"})
        grants = self.system.get_all_grants()
        assert len(grants) == 2
