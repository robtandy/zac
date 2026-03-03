---
name: code-zac
description: A sub-agent running in tmux that performs coding tasks. Use when user wants background tasks or parallel work. Start with tmux, send tasks via send-keys, check results via capture-pane.
tools: Bash
---

# code-zac Agent

A sub-agent running in tmux that can perform coding tasks independently while you focus on other things.

## Starting code-zac

```bash
tmux kill-session -t code-zac 2>/dev/null
tmux new-session -d -s code-zac "cd /root/zac-dev && .venv/bin/zac"
```

## Interacting with code-zac

**Send a task:**
```bash
tmux send-keys -t code-zac "your task description" Enter
```

**Check response:**
```bash
tmux capture-pane -t code-zac -p | tail -20
```

**Attach directly:**
```bash
tmux attach -t code-zac
# Ctrl+b d to detach
```

## Workflow

1. User gives you a task for code-zac
2. Send the task via `tmux send-keys`
3. Let it work - don't check in unless user asks
4. When ready, check response with `tmux capture-pane`
5. Relay brief status to user (they prefer high-level updates)

## Tips

- Don't poll constantly - give it time to work
- User wants brief updates, not full output dumps
- code-zac runs the same zac CLI - it has full tool access
- It's long-lived and persists across tasks
