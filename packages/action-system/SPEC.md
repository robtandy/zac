# Action/Permission System - Standalone Python Framework

## Overview
A standalone, zero-trust action queue and permission system. Handlers register as plugins with fine-grained, parameterized permissions. Actions are either executed immediately (if permitted) or enqueued for approval.

## Core Design

### Handlers
- Python base class `ActionHandler`
- Each handler declares its permissions via a class-level definition
- Permissions are fine-grained and parameterized (e.g. "send_email" with scope "recipient=bob@example.com")
- Handlers register with the action system and also expose themselves as tool definitions (dict schema)
- Each handler controls how its action requests are displayed in the UI (render method)

### Permissions
- Zero-trust: all handlers start with no permissions granted
- Permissions are defined by handlers, parameterized with scope
- Grants are stateful and persisted (SQLite)
- Each grant has an expiration: "1h", "today", "indefinite"
- Only the human can grant permissions (not the AI agent)
- Agent can check if a permission is granted

### Action Flow
1. Agent (or any consumer) requests an action via the system
2. System checks if required permission is granted
3. If granted -> execute handler, return result
4. If not granted -> enqueue, notify user, return "pending" status
5. User can grant permission via UI (gear icon on queued item)
6. Once granted, queued action executes and agent is notified of completion

### Data Model
- `Permission`: handler_id, name, description, parameters_schema (JSON)
- `PermissionGrant`: permission_id, scope_params (JSON), expires_at, granted_at, granted_by
- `ActionRequest`: id, handler_id, action_name, params (JSON), status (pending/approved/running/completed/failed/expired), result (JSON), created_at, completed_at
- `ActionHandler` (registered in-memory): id, name, permissions[], actions[]

### Notification System
- Callbacks/hooks for: action_enqueued, action_completed, action_failed, permission_needed
- Support async notification (callbacks or simple event system)

### API Surface
- `ActionSystem` - main entry point
  - `register_handler(handler)`
  - `request_action(handler_id, action_name, params) -> ActionResult`
  - `check_permission(handler_id, permission_name, scope) -> bool`
  - `grant_permission(permission_name, scope, expiration) -> GrantId`
  - `revoke_permission(grant_id)`
  - `get_pending_actions() -> list[ActionRequest]`
  - `get_action_status(action_id) -> ActionRequest`
- `ActionHandler` base class
  - `permissions: list[PermissionDef]`
  - `execute(action_name, params) -> result`
  - `render_request(action_request) -> dict` (UI display data)
  - `as_tool_schema() -> dict` (for AI agent tool registration)

### Persistence
- SQLite for grants and action queue
- JSON serialization for params/scope

### Tech
- Python 3.11+
- Strong typing throughout
- No heavy frameworks - keep deps minimal
- asyncio-friendly but sync-first API
- pytest for tests
