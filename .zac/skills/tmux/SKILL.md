---
name: tmux
description: Create and interact with detached tmux sessions for running interactive programs. Use this to run long-lived processes, test TUI applications, or run multiple isolated terminal sessions.
---

# Tmux Skill

## The Problem

When running inside an existing tmux session, creating new sessions with `tmux new-session` can fail or behave unexpectedly. The solution is to use a **separate tmux socket** to create an isolated server.

## Key Pattern: Use `-L <socket-name>`

Always use `-L <socket-name>` to create a separate tmux server. This works regardless of whether you're already inside tmux.

## Creating a Session

```bash
# Create a detached session with a custom socket
tmux -L my-socket new-session -d -s <session-name> '<command>'

# Example: start a Python REPL
tmux -L my-socket new-session -d -s python 'python3'

# Example: start a node REPL
tmux -L my-socket new-session -d -s node 'node'

# Example: run a script
tmux -L my-socket new-session -d -s myapp '/path/to/script.sh'
```

## Sending Input

```bash
# Send text and Enter key
tmux -L my-socket send-keys -t <session-name> 'your input' Enter

# Send just a key (like Escape or Ctrl+C)
tmux -L my-socket send-keys -t <session-name> C-c
tmux -L my-socket send-keys -t <session-name> Escape

# Send special keys: C-a (Ctrl+a), C-d (Ctrl+d), etc.
tmux -L my-socket send-keys -t <session-name> C-d

# Note: C-m is Enter
```

## Viewing Output

```bash
# Capture the visible pane content
tmux -L my-socket capture-pane -t <session-name> -p

# Capture with more history (last 100 lines)
tmux -L my-socket capture-pane -t <session-name> -p -S -100

# For continuous monitoring, use watch:
watch -n 0.5 "tmux -L my-socket capture-pane -t <session-name> -p | tail -20"
```

## Session Management

```bash
# List sessions on your socket
tmux -L my-socket list-sessions

# Check if a session exists
tmux -L my-socket has-session -t <session-name> 2>/dev/null && echo "exists"

# Kill a specific session
tmux -L my-socket kill-session -t <session-name>

# Kill all sessions on a socket (kill the server)
tmux -L my-socket kill-server
```

## Window and Pane Operations

```bash
# Create a new window in a session
tmux -L my-socket new-window -t <session-name> -n <window-name> '<command>'

# Switch windows
tmux -L my-socket select-window -t <session-name>:<window-index>

# Split a pane vertically
tmux -L my-socket split-window -t <session-name> -h

# Split a pane horizontally
tmux -L my-socket split-window -t <session-name> -v
```

## Complete Example: Running a TUI Application

```bash
# 1. Create session with specific dimensions
tmux -L my-socket new-session -d -s app -x 80 -y24 'python3 -m cursesapp'

# 2. Wait for startup
sleep 2

# 3. Send input
tmux -L my-socket send-keys -t app "hello" Enter

# 4. View output
tmux -L my-socket capture-pane -t app -p

# 5. Send special keys (Escape to exit modes, etc.)
tmux -L my-socket send-keys -t app Escape

# 6. Cleanup
tmux -L my-socket kill-session -t app
```

## Socket Naming Conventions

- Use lowercase letters, numbers, and hyphens only
- Example: ` Zac`, `test-run`, `pi-session`
- Each socket runs an independent tmux server
- Remember your socket name - you'll need it for all commands!

## Troubleshooting

**"no server running" error:**
- The socket needs to be created first. Just use `-L <socket>` on the first command and tmux will start the server.

**Commands not working:**
- Make sure you're using the SAME socket name (`-L <socket>`) for ALL commands in a workflow
- List sessions to verify: `tmux -L my-socket list-sessions`

**Session not responding:**
- Try sending Ctrl+C: `tmux -L my-socket send-keys -t <session> C-c`
- Kill and recreate: `tmux -L my-socket kill-session -t <session>`
