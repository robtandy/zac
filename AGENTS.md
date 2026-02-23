# AGENTS.md

This document describes the key packages, abstractions, and conventions in the project. It is intended to help AI agents and developers navigate and understand the codebase.

---

## `action-system` Package

### Overview
The `action-system` package is a framework for managing **actions**, **permissions**, and **execution** in a controlled and auditable way. It is designed to:
- Allow **handlers** (e.g., tools, APIs, or services) to register actions they can perform.
- Enforce **fine-grained permissions** for actions, with support for scoped and time-limited grants.
- Execute actions immediately if permitted, or **enqueue them for approval** if not.
- Persist **action requests** and **permission grants** in an SQLite database.
- Emit **events** for integration with other systems (e.g., notifications, logging, or UI updates).

---

### Key Abstractions

#### 1. **`ActionSystem` (`core.py`)**
- The **main entry point** for the system.
- Manages:
  - **Handler registration**: Register handlers that define actions and permissions.
  - **Action requests**: Execute actions immediately if permitted, or enqueue them for approval.
  - **Permission management**: Check, grant, or revoke permissions.
  - **Event emission**: Emit events for actions (e.g., `ACTION_ENQUEUED`, `ACTION_COMPLETED`, `PERMISSION_NEEDED`).
- Uses:
  - `Store` for persistence.
  - `PermissionManager` for permission logic.
  - `EventBus` for event handling.

#### 2. **`ActionHandler` (`handler.py`)**
- **Base class** for defining handlers (e.g., tools, APIs, or services).
- Subclasses must define:
  - `handler_id`: Unique identifier for the handler.
  - `name`: Human-readable name.
  - `permissions`: List of `PermissionDef` objects defining the permissions required for actions.
  - `execute()`: Method to perform the action.
- Provides:
  - `get_required_permission()`: Determines the permission required for an action.
  - `render_request()`: Customizes how action requests appear in the UI.
  - `as_tool_schema()`: Returns a tool definition for AI agent registration.

#### 3. **`PermissionDef` and `PermissionGrant` (`models.py`)**
- **`PermissionDef`**: Defines a permission (e.g., `"send_email"`), including its name, description, and accepted scope parameters (e.g., `{"recipient": "Email address to send to"}`).
- **`PermissionGrant`**: Represents a granted permission, including its scope, expiration, and who granted it.

#### 4. **`PermissionManager` (`permissions.py`)**
- Manages **permission grants** and **checks**. 
- Methods:
  - `check()`: Checks if a permission is granted for a given scope.
  - `grant()`: Grants a permission with optional scope and expiration.
  - `revoke()`: Revokes a permission grant.
  - `get_all_grants()`: Returns all granted permissions.

#### 5. **`Store` (`store.py`)**
- **SQLite-backed persistence** for:
  - **Permission grants**: Stores granted permissions.
  - **Action requests**: Stores action requests, their status, and results.
- Methods:
  - `save_grant()`: Saves a permission grant.
  - `get_grants()`: Retrieves grants for a handler and permission.
  - `save_action()`: Saves an action request.
  - `get_action()`: Retrieves an action request by ID.
  - `get_pending_actions()`: Retrieves all pending actions.

#### 6. **`EventBus` (`notifications.py`)**
- Emits **events** for actions and permissions (e.g., `ACTION_ENQUEUED`, `ACTION_COMPLETED`, `PERMISSION_NEEDED`).
- Allows other systems to **subscribe** to events (e.g., for logging, notifications, or UI updates).

#### 7. **`ActionRequest` and `ActionResult` (`models.py`)**
- **`ActionRequest`**: Represents a request to execute an action, including its parameters, status, and required permission.
- **`ActionResult`**: Represents the result of an action request, including its status, result, and error (if any).

---

### Workflow
1. **Register Handlers**: Handlers (e.g., email, file operations) register their actions and permissions with the `ActionSystem`.
2. **Request Actions**: A user or agent requests an action (e.g., `send_email`). The `ActionSystem` checks if the required permission is granted.
3. **Execute or Enqueue**:
   - If the permission is granted, the action is executed immediately.
   - If not, the action is enqueued for approval, and an event (`PERMISSION_NEEDED`) is emitted.
4. **Approve Actions**: A human (or automated system) approves the action, granting the required permission. The `ActionSystem` then executes the action.
5. **Persist State**: All action requests and permission grants are persisted in SQLite.

---

### Key Features
- **Fine-Grained Permissions**: Permissions can be scoped (e.g., `{"recipient": "alice@example.com"}`) and time-limited (e.g., expire after 1 hour).
- **Event-Driven**: Events are emitted for key actions (e.g., `ACTION_ENQUEUED`, `ACTION_COMPLETED`), allowing integration with other systems.
- **Persistence**: All state (actions, permissions) is persisted in SQLite.
- **Extensible**: Handlers can be added for any action (e.g., sending emails, reading files, executing commands).

---

### Example Use Case
1. An **email handler** registers with the `ActionSystem`, defining a `send_email` action and a `send_email` permission.
2. An **agent** requests to send an email to `alice@example.com`.
3. The `ActionSystem` checks if the `send_email` permission is granted for `{"recipient": "alice@example.com"}`.
   - If granted, the email is sent immediately.
   - If not, the action is enqueued, and a `PERMISSION_NEEDED` event is emitted.
4. A **human** approves the action, granting the `send_email` permission for `{"recipient": "alice@example.com"}`.
5. The `ActionSystem` executes the action and emits an `ACTION_COMPLETED` event.

---

## CLI Package (`packages/cli`)

### Overview
The CLI package provides the `zac` command-line interface. It manages the gateway daemon and launches the TUI.

### Key Files
- **`src/cli/main.py`**: Entry point, argument parsing, command dispatch
- **`src/cli/tui.py`**: Launches the TUI via `npx tsx`, auto-installs dependencies
- **`src/cli/daemon.py`**: Gateway daemon management (start, stop, restart, status)
- **`src/cli/paths.py`**: Path discovery, finds repo root and standard paths

### How It Works
1. User runs `zac` command
2. CLI starts the gateway daemon (if not running)
3. CLI launches the TUI which connects to the gateway

### Auto-Install Feature
The CLI automatically runs `npm install` in the TUI directory if `node_modules` is missing. This ensures users don't need to manually install Node.js dependencies on first run.

---

## Gateway Package (`packages/gateway`)

### Overview
The gateway is a WebSocket server that manages agent sessions and exposes the web UI.

### Key Files
- **`src/gateway/__main__.py`**: Entry point, auto-discovers web UI, auto-installs dependencies
- **`src/gateway/server.py`**: Main server implementation
- **`src/gateway/session.py`**: Client session management, handles messages, `/reload` command

### Web UI Integration
- The gateway serves the web UI from `packages/web/dist/` (pre-built)
- On `/reload` command, it rebuilds the web package via `npm run build`
- Automatically runs `npm install` in `packages/web` if `node_modules` is missing

### Session Management
- Each connected WebSocket client is bound to an `AgentClient` instance
- Handles commands: `prompt`, `steer`, `abort`, `context_request`, `model_list_request`
- Special `/reload` command hot-reloads Python agent modules and rebuilds web UI

---

## TUI Package (`packages/tui`)

### Overview
The Terminal User Interface - a Node.js/TypeScript app that connects to the gateway.

### Key Details
- Entry point: `packages/tui/src/index.ts`
- Runs via `npx tsx` (TypeScript executor)
- Connects to gateway via WebSocket (URL in `ZAC_GATEWAY_URL` env var)

---

## Web Package (`packages/web`)

### Overview
The web UI served by the gateway. Pre-built files in `dist/` are committed to the repo.

### Key Details
- Entry: `packages/web/src/index.ts`
- Build output: `packages/web/dist/`
- On `/reload`, the gateway rebuilds this package

---

## Conventions
- **Surgical Changes**: Only modify what is necessary to fulfill a task. Avoid refactoring unrelated code.
- **Simplicity First**: Write the minimum code required to solve the problem. Avoid speculative features or abstractions.
- **Event-Driven**: Use events to integrate systems (e.g., logging, notifications, UI updates).
- **Persistence**: Use SQLite for persisting state (e.g., actions, permissions).
