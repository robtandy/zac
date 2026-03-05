---
name: running-zac
description: Run Zac in a tmux session for TUI mode or fix mode. Use this when you need to run Zac interactively or test fixes.
---

# Running Zac Skill

## When to Use

Use this skill when you need to run Zac, either in TUI mode for interactive use or in fix mode to automatically fix issues. Running in tmux allows you to keep your current session intact.

## TUI Mode (Default)

Start Zac in TUI mode for interactive conversations:

```bash
tmux new-session -d -s zac '.venv/bin/zac'
```

This creates a session named `zac` and starts Zac in interactive TUI mode.

### Send Messages

Use `tmux send-keys` to send input to Zac:

```bash
tmux send-keys -t zac "Your message here" C-m
```

The `C-m` simulates pressing Enter.

### View Output

Capture the pane content to see responses:

```bash
tmux capture-pane -t zac -p
```

For continuous output monitoring:

```bash
watch -n 0.5 'tmux capture-pane -t zac -p | tail -20'
```

---

## Fix Mode

Start Zac in fix mode to automatically fix issues from the local database:

```bash
tmux new-session -d -s zac-fix '.venv/bin/zac fix --max-cost <cost> --max-issues <num> --model <model> --reasoning <effort>'
```

### Common Fix Mode Options

- `--max-cost`: Maximum API cost in dollars (default: 5.0)
- `--max-issues`: Maximum number of issues to attempt (optional)
- `--model`: Model ID to use (optional)
- `--reasoning`: Reasoning effort - low, medium, high, xhigh (optional)
- `--db`: Path to issues database (default: .zac/ISSUES.db)

### Example

```bash
tmux new-session -d -s zac-fix '.venv/bin/zac fix --max-cost 1 --max-issues 1 --model minimax/minimax-m2.5 --reasoning xhigh'
```

### View Fix Mode Output

```bash
tmux capture-pane -t zac-fix -p
```

---

## Clean Up

When done, kill the tmux session:

```bash
tmux kill-session -t zac      # For TUI mode
tmux kill-session -t zac-fix  # For fix mode
```

---

## Tips

- The working directory will be `/root/zac-dev` - adjust paths as needed
- Use separate sessions for TUI and fix mode to avoid conflicts
- If Zac hangs or crashes, you can kill the session and start fresh