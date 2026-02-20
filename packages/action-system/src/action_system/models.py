"""Data models for the action system."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ActionStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class Expiration(Enum):
    ONE_HOUR = "1h"
    TODAY = "today"
    INDEFINITE = "indefinite"


class PermissionDef(BaseModel):
    """A permission defined by a handler.

    Permissions are fine-grained and parameterized. The `parameters` dict
    describes what scope parameters this permission accepts
    (e.g. {"recipient": "Email address to send to"}).
    """

    name: str
    description: str
    handler_id: str = ""
    parameters: dict[str, str] = Field(default_factory=dict)


class PermissionGrant(BaseModel):
    """A granted permission with optional scope and expiration."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    permission_name: str = ""
    handler_id: str = ""
    scope: dict[str, Any] = Field(default_factory=dict)
    expiration: Expiration = Expiration.INDEFINITE
    expires_at: datetime | None = None
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    granted_by: str = "user"

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at


class ActionRequest(BaseModel):
    """A request to execute an action."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    handler_id: str = ""
    action_name: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    permission_name: str = ""
    permission_scope: dict[str, Any] = Field(default_factory=dict)
    status: ActionStatus = ActionStatus.PENDING
    result: Any = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class ActionResult(BaseModel):
    """Result returned from requesting an action."""

    action_id: str
    status: ActionStatus
    result: Any = None
    error: str | None = None

    @property
    def is_pending(self) -> bool:
        return self.status == ActionStatus.PENDING

    @property
    def is_completed(self) -> bool:
        return self.status == ActionStatus.COMPLETED
