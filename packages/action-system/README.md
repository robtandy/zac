# Action System

Zero-trust action queue with fine-grained, parameterized permissions.

## Quick Start

```python
from action_system import ActionSystem, ActionHandler, PermissionDef, Expiration

# Define a handler
class MyHandler(ActionHandler):
    handler_id = "my_handler"
    name = "My Handler"
    permissions = [
        PermissionDef(name="do_stuff", description="Do stuff", parameters={"target": "What to act on"}),
    ]

    def get_required_permission(self, action_name, params):
        return "do_stuff", {"target": params.get("target", "")}

    def execute(self, action_name, params):
        return {"result": f"Did {action_name} on {params['target']}"}

# Create system and register
system = ActionSystem(db_path="actions.db")  # or ":memory:"
system.register_handler(MyHandler())

# Request an action (will be enqueued — no permissions yet)
result = system.request_action("my_handler", "run", {"target": "foo"})
print(result.status)  # ActionStatus.PENDING

# Grant permission (human does this via UI)
system.grant_permission("my_handler", "do_stuff", {"target": "foo"}, Expiration.INDEFINITE)

# Approve the pending action
result = system.approve_action(result.action_id)
print(result.status)  # ActionStatus.COMPLETED

# Or next time, it runs immediately
result = system.request_action("my_handler", "run", {"target": "foo"})
print(result.status)  # ActionStatus.COMPLETED
```

## Permission Expiration

- `Expiration.ONE_HOUR` — expires in 1 hour
- `Expiration.TODAY` — expires end of UTC day
- `Expiration.INDEFINITE` — never expires (until revoked)

## Events

```python
from action_system import ACTION_ENQUEUED, ACTION_COMPLETED

system.events.on(ACTION_ENQUEUED, lambda action, handler: print(f"Queued: {action.id}"))
system.events.on(ACTION_COMPLETED, lambda action, handler: print(f"Done: {action.id}"))
```

## Tests

```bash
pytest tests/
```
