"""Fix mode - automatically fix local issues."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import typer

from agent.config import get_api_key as _get_api_key_from_config
from agent.client import AgentClient
from agent.events import EventType

from .paths import DefaultPaths

app = typer.Typer(help="Fix local issues automatically")

DEFAULT_MAX_COST = 5.0
DEFAULT_DB_PATH = ".zac/ISSUES.db"


def _get_api_key(paths: DefaultPaths) -> str:
    """Get the OpenRouter API key."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        return api_key

    # Try user config
    from agent.config import load_user_config
    user_config = load_user_config()
    if "open-router-api-key" in user_config:
        return user_config["open-router-api-key"]

    print("OpenRouter API key not found.", file=sys.stderr)
    print("You can get one from https://openrouter.ai/settings", file=sys.stderr)
    api_key = input("Enter your OpenRouter API key: ").strip()

    if not api_key:
        print("Error: API key is required", file=sys.stderr)
        raise typer.Exit(1)

    return api_key


def _get_open_issues(
    db_path: str,
    max_issues: Optional[int] = None,
    issue_id: Optional[int] = None,
) -> list[dict]:
    """Get open issues from the local SQLite database."""
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # If a specific issue ID is provided, fetch only that issue
    if issue_id is not None:
        cursor.execute(
            "SELECT id, title, description, status, created_at, updated_at FROM issues WHERE id = ?",
            (issue_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return []

        issues = []
        for row in rows:
            issues.append({
                "id": row["id"],
                "title": row["title"],
                "description": row["description"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })
        return issues

    cursor.execute(
        "SELECT id, title, description, status, created_at, updated_at FROM issues WHERE status = ? ORDER BY created_at ASC",
        ("OPEN",),
    )
    rows = cursor.fetchall()
    conn.close()

    issues = []
    for row in rows:
        issues.append({
            "id": row["id"],
            "title": row["title"],
            "description": row["description"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })

    if max_issues:
        issues = issues[:max_issues]

    return issues


def _update_issue_status(db_path: str, issue_id: int, status: str) -> None:
    """Update the status of an issue in the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "UPDATE issues SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, issue_id),
    )

    conn.commit()
    conn.close()


def _add_comment(db_path: str, issue_id: int, body: str, author: str = "zac") -> None:
    """Add a comment to an issue in the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO comments (issue_id, body, author, created_at) VALUES (?, ?, ?, ?)",
        (issue_id, body, author, now),
    )
    cursor.execute(
        "UPDATE issues SET updated_at = ? WHERE id = ?",
        (now, issue_id),
    )

    conn.commit()
    conn.close()


def _get_comments(db_path: str, issue_id: int) -> list[dict]:
    """Get comments for an issue from the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, body, author, created_at FROM comments WHERE issue_id = ? ORDER BY created_at ASC",
        (issue_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def _create_worktree(branch_name: str) -> Path:
    """Create a new git worktree for the fix."""
    worktree_path = Path.cwd() / ".zac-fix-worktree"

    # Remove existing worktree if it exists
    if worktree_path.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree_path)], check=True)
    
    # Remove existing branch if it exists
    subprocess.run(["git", "branch", "-D", branch_name], capture_output=True)

    # Create new worktree with new branch
    subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
        check=True,
    )

    return worktree_path


def _get_fix_system_prompt() -> str:
    """Get the system prompt for fix mode."""
    return """

# FIX MODE - Autonomous Issue Fixing

You are now operating in FIX MODE. Your goal is to automatically fix local issues in this repository.

## Your Mission

For each issue assigned to you:
1. Understand the issue by reading its description and examining the codebase
2. Reproduce the problem if possible
3. Write a failing test that demonstrates the bug
4. Fix the bug
5. Verify the fix by running the test
6. Create a pull request with your fix

## Issue Comments

When you need clarification from the user, just ask your question. The system will:
1. Detect that you need clarification (by analyzing your response)
2. Add your response as a comment to the issue
3. Change the issue status to INPUT_REQUIRED (so you don't work on it while waiting)
4. Stop working on this issue until the user provides an answer

You can also check existing comments on the issue to see previous questions and answers.

## Operating Environment

- You run in a **headless environment** with no TUI
- You interact with the gateway programmatically
- All file operations and command execution are available to you

## Git Worktree

You are working in a **separate git worktree** created specifically for this fix. This keeps your changes isolated from the main codebase until you submit a PR.

## Workflow

### 1. Understand the Issue
- Read the issue description carefully
- Check if there are any existing comments on the issue
- Read the relevant code to understand what the issue describes
- Identify the files and functions that need to be modified

### 2. Reproduce the Problem
- Try to reproduce the bug described in the issue
- If it's a code bug, run the relevant code to see the error
- Document what you observe

### 3. Write a Failing Test
- Create a test that demonstrates the bug
- Run the test to confirm it fails
- This proves you understand the problem

### 4. Fix the Problem
- Implement the fix in the code
- Run the test again to confirm it passes
- Make sure you don't break any existing tests

### 5. Create a Pull Request
- Commit your changes with a descriptive message
- Push the branch to the remote
- Create a PR with a clear description of the fix

## Cost Management

- You are being monitored for API costs
- If costs exceed the specified limit, you should stop and report
- Be efficient: understand the issue quickly, don't over-engineer the fix

## Important Rules

1. **Ask clarifying questions when needed** - The system will detect your need for clarification and add your question as a comment
2. **Work in the worktree** - All code changes should be in the worktree directory
3. **Test your changes** - Always verify fixes work before submitting PR
4. **Be concise** - Don't add unnecessary changes or over-engineer solutions
5. **Respect the cost limit** - Stop if API costs exceed the threshold

## Tools Available

You have all the normal Zac tools available:
- read: Read files
- write: Create/modify files
- edit: Make surgical edits
- bash: Run commands

Use them effectively to accomplish your mission!
"""


async def _run_fix_mode(
    max_cost: float,
    max_issues: Optional[int],
    model: Optional[str],
    reasoning_effort: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
    issue_id: Optional[int] = None,
) -> None:
    """Run fix mode - iterate through local issues and fix them."""

    print(f"Database: {db_path}")

    # Get open issues from local database
    print("Fetching open issues...")
    issues = _get_open_issues(db_path, max_issues, issue_id)
    print(f"Found {len(issues)} open issues")

    if issue_id is not None and not issues:
        print(f"Issue #{issue_id} not found or not accessible.")
        return

    if not issues:
        print("No issues to fix!")
        return

    # Get API key
    paths = DefaultPaths()
    api_key = _get_api_key(paths)
    os.environ["OPENROUTER_API_KEY"] = api_key

    total_cost = 0.0

    for i, issue in enumerate(issues):
        issue_id = issue["id"]
        issue_title = issue["title"]
        issue_description = issue["description"]

        print(f"\n{'='*60}")
        print(f"Issue #{issue_id}: {issue_title}")
        print(f"{'='*60}")

        # Get existing comments for this issue
        comments = _get_comments(db_path, issue_id)
        if comments:
            print(f"Comments on this issue:")
            for comment in comments:
                print(f"  [{comment['author']}] {comment['body'][:100]}...")
            print()

        # Check cost
        if total_cost >= max_cost:
            print(f"Cost limit exceeded (${total_cost:.2f} >= ${max_cost:.2f})")
            break

        # Create worktree for this fix
        branch_name = f"fix/issue-{issue_id}"
        try:
            worktree_path = _create_worktree(branch_name)
            print(f"Created worktree at {worktree_path}")
        except Exception as e:
            print(f"Error creating worktree: {e}")
            _update_issue_status(db_path, issue_id, "INPUT_REQUIRED")
            continue

        # Build the prompt for this issue
        comments_text = ""
        if comments:
            comments_text = "\n## Existing Comments:\n"
            for comment in comments:
                comments_text += f"- [{comment['author']}] {comment['body']}\n"

        fix_prompt = f"""Please fix local issue #{issue_id}.

Issue Title: {issue_title}

The issue description is:
{issue_description}
{comments_text}
Your task is to:
1. Understand the issue
2. Reproduce the problem
3. Write a failing test
4. Fix the bug
5. Verify the fix works
6. Create a pull request

Work in the directory: {worktree_path}

When you've completed the fix or encountered a blocker, respond with either:
- A summary of what you did and the PR URL (if successful)
- A question starting with "Zac: " if you need clarification

Good luck!
"""

        # Run the agent with the fix prompt
        client = AgentClient(
            model=model,
            system_prompt=_get_fix_system_prompt(),
            reasoning_effort=reasoning_effort,
        )
        await client.start()

        try:
            response_text = ""
            async for event in client.prompt(fix_prompt):
                if event.type == EventType.TEXT_DELTA:
                    response_text += event.delta
                    # Optionally stream output
                    print(event.delta, end="", flush=True)
                elif event.type == EventType.ERROR:
                    print(f"\nError: {event.message}", file=sys.stderr)

            print()

            # Try to extract cost info (this would need to be tracked properly)
            # For now, we'll estimate based on the response length
            estimated_cost = len(response_text) / 1000 * 0.001  # Rough estimate
            total_cost += estimated_cost

            print(f"Estimated cost for this issue: ${estimated_cost:.4f}")
            print(f"Total cost so far: ${total_cost:.4f}")

            # Check if Zac needs clarification by looking for questions
            # If the response contains a question mark and seems to be asking for input
            needs_clarification = "?" in response_text and any(
                keyword in response_text.lower() 
                for keyword in ["should", "could", "would", "what", "how", "which", "prefer", "clarify"]
            )
            
            if needs_clarification:
                # Add entire response as a comment from zac
                _add_comment(db_path, issue_id, response_text.strip(), "zac")
                _update_issue_status(db_path, issue_id, "INPUT_REQUIRED")
                print(f"Issue #{issue_id} needs clarification. Added comment and set status to INPUT_REQUIRED.")
            # Update issue status based on result
            elif "PR #" in response_text or "pull request" in response_text.lower():
                # Extract PR URL if possible
                pr_url = ""
                for line in response_text.split('\n'):
                    if 'github.com' in line and 'pull' in line.lower():
                        pr_url = line.strip()
                        break

                if pr_url:
                    print(f"Issue #{issue_id} fixed. PR: {pr_url}")
                    _update_issue_status(db_path, issue_id, "CLOSED")
                else:
                    print(f"Issue #{issue_id} fixed. PR created.")
                    _update_issue_status(db_path, issue_id, "CLOSED")
            else:
                print(f"Issue #{issue_id} could not be completed.")
                _update_issue_status(db_path, issue_id, "INPUT_REQUIRED")

        except Exception as e:
            print(f"Error processing issue #{issue_id}: {e}")
            _update_issue_status(db_path, issue_id, "INPUT_REQUIRED")
        finally:
            await client.stop()

    print(f"\n{'='*60}")
    print(f"Fix mode complete. Total estimated cost: ${total_cost:.4f}")
    print(f"{'='*60}")


@app.command()
def fix(
    max_cost: Annotated[float, typer.Option("--max-cost", help="Maximum API cost in dollars")] = DEFAULT_MAX_COST,
    max_issues: Annotated[Optional[int], typer.Option("--max-issues", help="Maximum number of issues to attempt")] = None,
    model: Annotated[Optional[str], typer.Option("--model", help="Model ID")] = None,
    reasoning_effort: Annotated[Optional[str], typer.Option("--reasoning", help="Reasoning effort (low, medium, high, xhigh)")] = None,
    db: Annotated[str, typer.Option("--db", help="Path to issues database")] = DEFAULT_DB_PATH,
    issue: Annotated[Optional[int], typer.Option("--issue", help="Target a specific issue by ID")] = None,
) -> None:
    """Fix local issues automatically."""
    asyncio.run(_run_fix_mode(max_cost, max_issues, model, reasoning_effort, db, issue))