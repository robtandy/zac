"""Action System — standalone zero-trust action queue with fine-grained permissions."""

from .core import ActionSystem
from .handler import ActionHandler
from .models import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    Expiration,
    PermissionDef,
    PermissionGrant,
)
from .notifications import (
    ACTION_COMPLETED,
    ACTION_ENQUEUED,
    ACTION_FAILED,
    PERMISSION_NEEDED,
)

__all__ = [
    "ActionSystem",
    "ActionHandler",
    "ActionRequest",
    "ActionResult",
    "ActionStatus",
    "Expiration",
    "PermissionDef",
    "PermissionGrant",
    "ACTION_COMPLETED",
    "ACTION_ENQUEUED",
    "ACTION_FAILED",
    "PERMISSION_NEEDED",
]
