---
name: self-test
description: Test changes to Zac by running a new instance in tmux. Use this when you've made code changes and want to verify they work without interrupting your current session.
---

# Self-Testing Skill

## When to Use

Use this skill when you've modified Zac's code (yourself) and want to test the changes in an isolated environment. This lets you interact with a fresh instance while keeping your current session intact.

## Instructions

### Step 1: Start a New tmux Session with Zac

Run a new tmux session and launch Zac inside it:

```bash
tmux new-session -d -s zac-test '.venv/bin/zac'
```

This creates a session named `zac-test` and starts the Zac binary inside it.

### Step 2: Send Commands to the Test Session

Use `tmux send-keys` to send input to the test Zac instance. For example, to send a message:

```bash
tmux send-keys -t zac-test "Hello, this is a test" C-m
```

The `C-m` simulates pressing Enter.

### Step 3: View the Output

Capture the pane content to see responses:

```bash
tmux capture-pane -t zac-test -p
```

For continuous output, you can watch it:

```bash
watch -n 0.5 'tmux capture-pane -t zac-test -p | tail -20'
```

### Step 4: Clean Up

When done testing, kill the session:

```bash
tmux kill-session -t zac-test
```

## Example Workflow

1. Make code changes to Zac
2. Start test session: `tmux new-session -d -s zac-test '.venv/bin/zac'`
3. Send test input: `tmux send-keys -t zac-test "your test message" C-m`
4. View response: `tmux capture-pane -t zac-test -p`
5. Repeat steps 3-4 as needed
6. Clean up: `tmux kill-session -t zac-test`

## Tips

- Use meaningful test messages that exercise the code paths you changed
- If Zac hangs or crashes, you can always kill the session and start fresh
- The working directory will be `/root/zac-dev` - adjust paths as needed
