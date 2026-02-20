# zac-mono

Monorepo for **Zac**, an AI agent system with zero-trust action/permission management. Users interact with an AI coding agent ("pi") through a terminal or web chat interface, while a permission system gates what actions the agent can take on the user's behalf.

## Architecture

```
┌─────────┐  ┌─────────┐
│   TUI   │  │   Web   │   Clients (TypeScript)
│ (Node)  │  │(Browser)│
└────┬────┘  └────┬────┘
     │ WebSocket  │
     └─────┬──────┘
           │
     ┌─────▼─────┐
     │  Gateway   │             Python, async
     │ (WS server)│
     └─────┬─────┘
           │ stdin/stdout (JSON-RPC)
     ┌─────▼─────┐
     │   Agent    │             Python, subprocess wrapper
     │  (pi RPC)  │
     └───────────┘

     ┌──────────────┐
     │ Action System │          Python, standalone
     │ (permissions) │
     └──────────────┘
```

**Data flow:** User types a message in the TUI or Web UI. The client sends a `ClientMessage` over WebSocket to the Gateway. The Gateway forwards the prompt to the Agent package, which manages a `pi` subprocess in RPC mode. The agent streams events back through the Gateway to all connected clients in real time.

## Packages

| Package | Language | Path | Purpose |
|---------|----------|------|---------|
| **action-system** | Python | `packages/action-system/` | Zero-trust action queue with parameterized, expiring permissions |
| **agent** | Python | `packages/agent/` | Async wrapper around the `pi` coding agent subprocess (JSON-RPC over stdin/stdout) |
| **gateway** | Python | `packages/gateway/` | WebSocket server bridging clients to the agent; also serves static files for the web UI |
| **tui** | TypeScript/Node | `packages/tui/` | Terminal chat client using `pi-tui` |
| **web** | TypeScript/Browser | `packages/web/` | Browser chat client bundled with esbuild |

### Package dependency graph

```
gateway ──depends-on──▶ agent
tui    ──connects-to──▶ gateway (WebSocket)
web    ──connects-to──▶ gateway (WebSocket)
action-system             (standalone, no cross-package deps yet)
```

## Protocol

All clients and the gateway communicate via the same WebSocket protocol.

### Client → Gateway

```typescript
type ClientMessage =
  | { type: "prompt"; message: string }   // send user message
  | { type: "steer"; message: string }    // redirect agent mid-execution
  | { type: "abort" }                     // cancel current execution
```

### Gateway → Clients

```typescript
type ServerEvent =
  | { type: "user_message"; message: string }
  | { type: "turn_start" }
  | { type: "text_delta"; delta: string }
  | { type: "tool_start"; tool_name: string; tool_call_id: string; args: Record<string, unknown> }
  | { type: "tool_update"; tool_call_id: string; tool_name: string; partial_result: string }
  | { type: "tool_end"; tool_call_id: string; tool_name: string; result: string; is_error: boolean }
  | { type: "turn_end" }
  | { type: "agent_end" }
  | { type: "error"; message: string }
```

The Gateway translates pi's RPC events into this protocol. Clients render `text_delta` events as streaming markdown and track tool executions via the `tool_*` events.

## Key concepts

### Zero-trust action system (`action-system`)

The action system enforces that the AI agent cannot perform side-effects without explicit human permission. Key design points:

- **Handlers** are plugins that declare their capabilities and required permissions via `ActionHandler` subclasses.
- **Permissions** are parameterized and scoped (e.g. "send_email" scoped to `recipient=alice@example.com`).
- **Grants** expire (`ONE_HOUR`, `TODAY`, or `INDEFINITE`) and are persisted in SQLite.
- **Action flow:** request → check permission → execute immediately if granted, otherwise enqueue for human approval.
- **Events:** `ACTION_ENQUEUED`, `ACTION_COMPLETED`, `ACTION_FAILED`, `PERMISSION_NEEDED` via an in-process `EventBus`.
- Handlers also expose `as_tool_schema()` to generate tool definitions consumable by an AI model.

See `packages/action-system/SPEC.md` for the full design and `packages/action-system/README.md` for usage examples.

### Agent wrapper (`agent`)

`AgentClient` manages a `pi` subprocess in `--mode rpc --no-session` mode:

- `start()` / `stop()` — lifecycle management.
- `prompt(message)` — send a prompt; returns an async iterator of `AgentEvent` objects.
- `steer(message)` — inject guidance while the agent is working.
- `abort()` — cancel the current execution.

Event types: `TURN_START`, `TEXT_DELTA`, `TOOL_START`, `TOOL_UPDATE`, `TOOL_END`, `TURN_END`, `AGENT_END`, `ERROR`.

### Gateway (`gateway`)

An async WebSocket server (using the `websockets` library) that:

- Manages a single `Session` binding one agent to N connected clients.
- Broadcasts agent events to all clients in real time.
- Optionally serves static files for the web UI (`--web-dir`).
- Supports TLS via `--tls-cert` / `--tls-key`.

Run with: `python -m gateway [--host HOST] [--port PORT] [--web-dir DIR] [--debug]`

### Clients (`tui` and `web`)

Both clients implement the same `GatewayConnection` pattern (WebSocket with auto-reconnect) and `ChatUI` abstraction (handle events, render messages). The TUI renders in the terminal using `@mariozechner/pi-tui`; the Web UI renders in the browser with `marked` for markdown.

## Development setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- [`uv`](https://docs.astral.sh/uv/) (Python package/workspace manager)

### Install dependencies

```bash
# Python packages (from repo root)
uv sync

# TUI
cd packages/tui && npm install

# Web
cd packages/web && npm install
```

### Run tests

```bash
# All Python tests from repo root
uv run pytest

# Specific package
uv run pytest packages/action-system/tests/
uv run pytest packages/agent/tests/
uv run pytest packages/gateway/tests/
```

### Run the system

```bash
# 1. Start the gateway
uv run python -m gateway --debug

# 2a. Connect via TUI (in another terminal)
cd packages/tui && npm start

# 2b. Or build and serve the web UI
cd packages/web && npm run build
uv run python -m gateway --web-dir packages/web/dist
# Then open http://localhost:8765 in a browser
```

The TUI reads `ZAC_GATEWAY_URL` (default `ws://localhost:8765`). The Web UI infers the WebSocket URL from the page URL or accepts a `?ws=` query parameter.

## Repository layout

```
zac-mono/
├── pyproject.toml                 # uv workspace config, pytest config
├── uv.lock
├── packages/
│   ├── action-system/
│   │   ├── src/action_system/
│   │   │   ├── core.py            # ActionSystem main class
│   │   │   ├── models.py          # ActionStatus, PermissionDef, ActionRequest, etc.
│   │   │   ├── handler.py         # ActionHandler base class
│   │   │   ├── permissions.py     # PermissionManager (check/grant/revoke)
│   │   │   ├── store.py           # SQLite persistence
│   │   │   ├── notifications.py   # EventBus
│   │   │   └── exceptions.py
│   │   ├── examples/              # Echo, email handler demos
│   │   ├── tests/test_core.py
│   │   ├── SPEC.md                # Full design spec
│   │   └── README.md
│   ├── agent/
│   │   ├── src/agent/
│   │   │   ├── client.py          # AgentClient (high-level async API)
│   │   │   ├── process.py         # PiProcess (subprocess management)
│   │   │   ├── events.py          # EventType enum, AgentEvent dataclass
│   │   │   └── exceptions.py
│   │   └── tests/
│   ├── gateway/
│   │   ├── src/gateway/
│   │   │   ├── server.py          # WebSocket server, HTTP static serving
│   │   │   ├── session.py         # Session (client ↔ agent binding)
│   │   │   ├── protocol.py        # ClientMessage, ServerEvent definitions
│   │   │   └── __main__.py        # CLI entry point
│   │   └── tests/
│   ├── tui/
│   │   ├── src/
│   │   │   ├── index.ts           # Entry point
│   │   │   ├── chat.ts            # ChatUI (terminal rendering)
│   │   │   ├── connection.ts      # GatewayConnection (WS client)
│   │   │   ├── protocol.ts        # Type definitions
│   │   │   └── theme.ts           # Terminal colors
│   │   └── package.json
│   └── web/
│       ├── src/
│       │   ├── index.html
│       │   ├── main.ts            # Entry point
│       │   ├── chat.ts            # ChatUI (DOM rendering)
│       │   ├── connection.ts      # GatewayConnection (WS client)
│       │   ├── protocol.ts        # Type definitions
│       │   └── styles.css
│       ├── dist/                   # Build output
│       └── package.json
```

## Build tools

| Tool | Role |
|------|------|
| `uv` | Python workspace management, dependency resolution, virtual env |
| `npm` | Node.js dependency management for TUI and Web |
| `esbuild` | Bundles the Web UI into `dist/` |
| `tsx` | Runs TypeScript directly for TUI development |
| `pytest` | Python test runner (configured at repo root) |
