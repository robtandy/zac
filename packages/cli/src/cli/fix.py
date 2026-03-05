"""Fix mode - automatically fix GitHub issues."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from agent.config import get_api_key as _get_api_key_from_config
from agent.client import AgentClient
from agent.events import EventType

from .paths import DefaultPaths

app = typer.Typer(help="Fix GitHub issues automatically")

DEFAULT_MAX_COST = 5.0


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
    repo: str,
    max_issues: Optional[int] = None,
) -> list[dict]:
    """Get open issues that don't have an attached PR."""
    # Get issues with JSON output
    cmd = ["gh", "issue", "list", "--state", "open", "--json", "number,title,body,url"]
    if max_issues:
        cmd.extend(["--limit", str(max_issues)])

    result = subprocess.run(
        cmd,
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=True,
    )

    issues = json.loads(result.stdout)

    # Filter out issues that have PRs attached (check each issue for linked PRs)
    filtered_issues = []
    for issue in issues:
        # Check if issue has a linked PR using the API
        # The "pull_request" field is null if no PR is linked
        pr_check = subprocess.run(
            ["gh", "api", f"repos/{repo}/issues/{issue['number']}"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
        )
        if pr_check.returncode == 0:
            pr_data = json.loads(pr_check.stdout)
            # If pull_request is null, there's no PR attached
            if pr_data.get("pull_request") is None:
                filtered_issues.append(issue)

    return filtered_issues


def _get_issue_comments(issue_number: int) -> list[dict]:
    """Get comments on an issue."""
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "comments"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        return data.get("comments", [])
    return []


def _has_unresolved_conversations(issue_number: int) -> bool:
    """Check if issue has unresolved conversations (comments after issue was closed)."""
    # Get issue state and comments
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "state,comments"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        comments = data.get("comments", [])
        # For now, consider any issue with comments as having potential conversations
        # A more sophisticated check could look at comment timestamps vs issue close time
        return len(comments) > 0
    return False


def _comment_on_issue(issue_number: int, body: str) -> None:
    """Add a comment to an issue."""
    subprocess.run(
        ["gh", "issue", "comment", str(issue_number), "--body", body],
        cwd=Path.cwd(),
        check=True,
    )


def _create_worktree(branch_name: str) -> Path:
    """Create a new git worktree for the fix."""
    worktree_path = Path.cwd() / ".zac-fix-worktree"

    # Remove existing worktree if it exists
    if worktree_path.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree_path)], check=True)

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

You are now operating in FIX MODE. Your goal is to automatically fix GitHub issues in this repository.

## Your Mission

For each issue assigned to you:
1. Understand the issue by reading its description and examining the codebase
2. Reproduce the problem if possible
3. Write a failing test that demonstrates the bug
4. Fix the bug
5. Verify the fix by running the test
6. Create a pull request with your fix

## Operating Environment

- You run in a **headless environment** with no TUI
- You interact with the gateway programmatically
- All file operations and command execution are available to you

## Git Worktree

You are working in a **separate git worktree** created specifically for this fix. This keeps your changes isolated from the main codebase until you submit a PR.

## Workflow

### 1. Understand the Issue
- Use `gh issue view <number>` to see full issue details
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
- Link the PR to the issue using "Fixes #<number>" or "Closes #<number>"

## Cost Management

- You are being monitored for API costs
- If costs exceed the specified limit, you should stop and report
- Be efficient: understand the issue quickly, don't over-engineer the fix

## Asking for Help

If you cannot determine something and need user input:
- Comment on the GitHub issue
- Include "Zac: " at the start of your comment so we know you wrote it
- Ask a clear, specific question

## Important Rules

1. **Do not fix issues with unresolved conversations** - Skip any issue that has comments that haven't been addressed
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
) -> None:
    """Run fix mode - iterate through issues and fix them."""

    # Get repo from git remote
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Error: Not in a git repository", file=sys.stderr)
        raise typer.Exit(1)

    remote_url = result.stdout.strip()
    # Extract owner/repo from git@github.com:owner/repo.git or https://github.com/owner/repo.git
    if remote_url.startswith("git@github.com:"):
        repo = remote_url.replace("git@github.com:", "").replace(".git", "")
    elif "github.com/" in remote_url:
        repo = remote_url.split("github.com/")[-1].replace(".git", "")
    else:
        print(f"Error: Could not determine GitHub repo from remote: {remote_url}", file=sys.stderr)
        raise typer.Exit(1)

    print(f"Repository: {repo}")

    # Get open issues
    print("Fetching open issues...")
    issues = _get_open_issues(repo, max_issues)
    print(f"Found {len(issues)} open issues without PRs")

    if not issues:
        print("No issues to fix!")
        return

    # Get API key
    paths = DefaultPaths()
    api_key = _get_api_key(paths)
    os.environ["OPENROUTER_API_KEY"] = api_key

    total_cost = 0.0

    for i, issue in enumerate(issues):
        issue_number = issue["number"]
        issue_title = issue["title"]
        issue_url = issue["url"]

        print(f"\n{'='*60}")
        print(f"Issue #{issue_number}: {issue_title}")
        print(f"{'='*60}")

        # Check for unresolved conversations
        if _has_unresolved_conversations(issue_number):
            print(f"Skipping issue #{issue_number} - has unresolved conversations")
            continue

        # Check cost
        if total_cost >= max_cost:
            print(f"Cost limit exceeded (${total_cost:.2f} >= ${max_cost:.2f})")
            break

        # Create worktree for this fix
        branch_name = f"fix/issue-{issue_number}"
        try:
            worktree_path = _create_worktree(branch_name)
            print(f"Created worktree at {worktree_path}")
        except Exception as e:
            print(f"Error creating worktree: {e}")
            _comment_on_issue(
                issue_number,
                f"Zac: I was unable to create a worktree for this fix. Error: {e}"
            )
            continue

        # Build the prompt for this issue
        fix_prompt = f"""Please fix GitHub issue #{issue_number}.

Issue Title: {issue_title}
Issue URL: {issue_url}

The issue description is:
{issue.get('body', 'No description provided.')}

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

            # Comment on the issue with the result
            if "PR #" in response_text or "pull request" in response_text.lower():
                # Extract PR URL if possible
                pr_url = ""
                for line in response_text.split('\n'):
                    if 'github.com' in line and 'pull' in line.lower():
                        pr_url = line.strip()
                        break

                if pr_url:
                    _comment_on_issue(issue_number, f"Zac: I've attempted to fix this issue. {pr_url}")
                else:
                    _comment_on_issue(issue_number, "Zac: I've attempted to fix this issue. Please check the recently created pull request.")
            else:
                _comment_on_issue(issue_number, "Zac: I was unable to complete this fix. I've documented my attempt in the worktree.")

        except Exception as e:
            print(f"Error processing issue #{issue_number}: {e}")
            _comment_on_issue(
                issue_number,
                f"Zac: I encountered an error while trying to fix this issue: {e}"
            )
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
) -> None:
    """Fix GitHub issues automatically."""
    asyncio.run(_run_fix_mode(max_cost, max_issues, model, reasoning_effort))
