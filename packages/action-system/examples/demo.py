"""Demo: run the action system with the echo handler and web UI.

Usage:
    python -m examples.demo

Then open http://localhost:8991 and try:
    - The pending echo action will appear (no permissions granted yet)
    - Click ⚙️ to see required permissions
    - Grant the permission with your chosen expiration
    - Watch it auto-execute
"""

from __future__ import annotations

from action_system import (
    ACTION_COMPLETED,
    ACTION_ENQUEUED,
    ActionSystem,
)
from action_system.server import serve
from examples.echo_handler import EchoHandler


def main() -> None:
    system = ActionSystem(db_path="demo.db")
    system.register_handler(EchoHandler())

    # Set up event listeners
    system.events.on(ACTION_ENQUEUED, lambda action, handler: print(f"📋 Enqueued: {action.action_name} ({action.id})"))
    system.events.on(ACTION_COMPLETED, lambda action, handler: print(f"✅ Completed: {action.action_name} → {action.result}"))

    # Enqueue a test action (will be pending — no permissions yet)
    result = system.request_action("echo", "echo", {"message": "Hello from the demo!", "channel": "test"})
    print(f"Requested echo action: {result.status.value} (id: {result.action_id})")

    # Also enqueue one without channel scope
    result2 = system.request_action("echo", "echo", {"message": "No channel specified"})
    print(f"Requested echo action: {result2.status.value} (id: {result2.action_id})")

    print("\nOpen http://localhost:8991 to manage permissions and approve actions.\n")
    serve(system, port=8991)


if __name__ == "__main__":
    main()
