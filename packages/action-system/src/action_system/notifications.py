"""Simple event/callback notification system."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

EventCallback = Callable[..., None]


class EventBus:
    """Simple synchronous event bus with named events."""

    def __init__(self) -> None:
        self._listeners: dict[str, list[EventCallback]] = defaultdict(list)

    def on(self, event: str, callback: EventCallback) -> None:
        """Register a listener for an event."""
        self._listeners[event].append(callback)

    def off(self, event: str, callback: EventCallback) -> None:
        """Remove a listener."""
        try:
            self._listeners[event].remove(callback)
        except ValueError:
            pass

    def emit(self, event: str, **kwargs: Any) -> None:
        """Emit an event, calling all registered listeners."""
        for callback in self._listeners.get(event, []):
            callback(**kwargs)


# Standard event names
ACTION_ENQUEUED = "action_enqueued"
ACTION_COMPLETED = "action_completed"
ACTION_FAILED = "action_failed"
PERMISSION_NEEDED = "permission_needed"
