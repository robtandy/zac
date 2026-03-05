---
name: running-zac
description: Run Zac in a tmux session for TUI mode or fix mode. Use this when you need to run Zac interactively or test fixes.
---

# Running Zac Skill

## When to Use

Use this skill when you need to run Zac, either in TUI mode for interactive use or in fix mode to automatically fix issues. Running in tmux allows you to keep your current session intact.

> **Note:** This skill uses a separate tmux socket to work even when you're already inside a tmux session. See the [tmux skill](../tmux/SKILL.md) for detailed tmux commands and troubleshooting.

## TUI Mode (Default)

Start Zac in TUI mode for interactive conversations:

```bash
tmux -L zac-socket new-session -d -s zac '.venv/bin/zac'
```

This creates a session named `zac` and starts Zac in interactive TUI mode.

### Send Messages

Use `tmux send-keys` to send input to Zac:

```bash
tmux -L zac-socket send-keys -t zac "Your message here" C-m
```

The `C-m` simulates pressing Enter.

### View Output

Capture the pane content to see responses:

```bash
tmux -L zac-socket capture-pane -t zac -p
```

For continuous output monitoring:

```bash
watch -n 0.5 'tmux -L zac-socket capture-pane -t zac -p | tail -20'
```

---

## Fix Mode

Start Zac in fix mode to automatically fix issues from the local database:

```bash
tmux -L zac-socket new-session -d -s zac-fix '.venv/bin/zac fix --max-cost <cost> --max-issues <num> --model <model> --reasoning <effort>'
```

### Common Fix Mode Options

- `--max-cost`: Maximum API cost in dollars (default: 5.0)
- `--max-issues`: Maximum number of issues to attempt (optional)
- `--model`: Model ID to use (optional)
- `--reasoning`: Reasoning effort - low, medium, high, xhigh (optional)
- `--db`: Path to issues database (default: .zac/ISSUES.db)
- `--issue`: Target a specific issue by ID (optional)

### Example

```bash
# Fix all open issues (up to cost limit)
tmux -L zac-socket new-session -d -s zac-fix '.venv/bin/zac fix --max-cost 1'

# Fix a specific issue by ID
tmux -L zac-socket new-session -d -s zac-fix '.venv/bin/zac fix --issue 42'

# Fix with specific model and reasoning effort
tmux -L zac-socket new-session -d -s zac-fix '.venv/bin/zac fix --max-cost 1 --max-issues 1 --model minimax/minimax-m2.5 --reasoning xhigh'
```

### View Fix Mode Output

```bash
tmux -L zac-socket capture-pane -t zac-fix -p
```

---

## Clean Up

When done, kill the tmux session:

```bash
tmux -L zac-socket kill-session -t zac      # For TUI mode
tmux -L zac-socket kill-session -t zac-fix  # For fix mode
```

Or kill the entire server:

```bash
tmux -L zac-socket kill-server
```

---

## Tips

- The working directory will be `/root/zac-dev` - adjust paths as needed
- Use separate sessions for TUI and fix mode to avoid conflicts
- If Zac hangs or crashes, you can kill the session and start fresh
- The socket name `zac-socket` isolates Zac's tmux from any existing tmux session you may be in
- See the [tmux skill](../tmux/SKILL.md) for more advanced operations like window/pane management