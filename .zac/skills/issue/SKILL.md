---
name: issue
description: Create, list, and comment on local issues stored in an SQLite database. Use when you want to record an issue locally rather than on GitHub.
---

# Local Issue Management Skill

## When to Use

Use this skill when you need to create or manage local issues stored in an SQLite database instead of GitHub issues.

---

## Issue Lifecycle

An issue moves through the following lifecycle:

```
[OPEN]  <--->  [INPUT_REQUIRED]  ---->  [CLOSED]
  ^            |                         
  |            |                         
  |            v                         
  +----(user comments)----(zac needs clarification)
```

### Status Meanings

- **OPEN**: Issue is ready to be worked on by Zac
- **INPUT_REQUIRED**: Zac has asked a question and is waiting for user input
- **CLOSED**: Issue has been resolved

### Status Transitions

1. **OPEN** → **INPUT_REQUIRED**: Zac encounters a blocker and needs clarification. Zac adds a comment (author="zac") and the status is automatically set to `INPUT_REQUIRED`.

2. **INPUT_REQUIRED** → **OPEN**: User provides an answer by adding a comment (author="user"). The status is automatically set back to `OPEN`, indicating Zac can resume work.

3. **OPEN** → **CLOSED**: Zac successfully fixes the issue and creates a pull request.

### Comment Authors

Comments can have different authors:
- **`user`**: Comments from the user (default). When added to an `INPUT_REQUIRED` issue, it reopens the issue.
- **`zac`**: Comments from Zac (the agent). When Zac adds a comment, it indicates the issue needs user input and sets status to `INPUT_REQUIRED`.

---

## Extract Issue Details

The user asks you to create an issue and provides a description. Determine an appropriate title and use the user's description as the body.
- A short, appropriate title that you create to summarize the issue (~50 chars)
- The body as the **verbatim** text provided by the user (unchanged)

---

## Create an Issue

Run the create issue script with the title and description as arguments:

```bash
.zac/skills/issue/scripts/create_issue.py "<title>" "<description>"
```

The script accepts:
- `title` - Issue title (required)
- `description` - Issue description (required)
- `--status` - Issue status (optional, default: OPEN)

### Valid Status Values

- `OPEN` - Issue is open and needs to be addressed
- `CLOSED` - Issue has been resolved
- `INPUT_REQUIRED` - Issue needs more information from the user

### Example

```bash
.zac/skills/issue/scripts/create_issue.py "System crashes when deleting non-existent file" "There's a bug in the file handling code..."
```

---

## List Issues

Run the list issues script to display issues:

```bash
.zac/skills/issue/scripts/list_issues.py [--status OPEN|CLOSED|INPUT_REQUIRED] [--format markdown|json|simple]
```

The script accepts:
- `--status` - Filter by status (optional)
- `--format` - Output format:
  - `markdown` (default) - Shows detailed info with descriptions
  - `simple` - Compact table with truncated descriptions
  - `json` - JSON output

### Examples

List all issues with descriptions:
```bash
.zac/skills/issue/scripts/list_issues.py
```

List only open issues:
```bash
.zac/skills/issue/scripts/list_issues.py --status OPEN
```

---

## Update Issue Cost

Run the update issue cost script to set or add cost to an issue:

```bash
.zac/skills/issue/scripts/update_issue_cost.py <issue_id> <cost> [--add]
```

The script accepts:
- `issue_id` - Issue ID to update (required)
- `cost` - Cost value (required)
- `--add` - Add to existing cost instead of replacing (optional)

### Examples

Set cost to $1.50 for issue #3:
```bash
.zac/skills/issue/scripts/update_issue_cost.py 3 1.50
```

Add $0.25 to existing cost for issue #3:
```bash
.zac/skills/issue/scripts/update_issue_cost.py 3 0.25 --add
```

---

## Add a Comment

Run the add comment script to add a comment to an issue:

```bash
.zac/skills/issue/scripts/add_comment.py <issue_id> "<body>" [--author <author>]
```

The script accepts:
- `issue_id` - Issue ID to add comment to (required)
- `body` - Comment text (required)
- `--author` - Author name (optional, default: user)

### Examples

Add a comment to issue #1:
```bash
.zac/skills/issue/scripts/add_comment.py 1 "This is a comment"
```

Add a comment from Zac (the agent):
```bash
.zac/skills/issue/scripts/add_comment.py 1 "What should the output format be?" --author zac
```

---

## List Comments

Run the list comments script to view comments on an issue:

```bash
.zac/skills/issue/scripts/list_comments.py <issue_id> [--format markdown|json]
```

The script accepts:
- `issue_id` - Issue ID to list comments for (required)
- `--format` - Output format (optional, default: markdown)

### Example

```bash
.zac/skills/issue/scripts/list_comments.py 1
```

## Notes

- The database is located at `.zac/ISSUES.db` (relative to the current directory)
- Issues are created with status `OPEN` and cost `$0.00` by default
- The table includes `cost`, `created_at` and `updated_at` fields
- Comments have a foreign key to the issue
- When Zac adds a comment (author=`zac`), the issue status is set to `INPUT_REQUIRED`
- When a user adds a comment (author=`user`), the issue status is set to `OPEN` (if it was `INPUT_REQUIRED`)