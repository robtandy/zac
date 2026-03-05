---
name: issue
description: Create and list local issues stored in an SQLite database. Use when you want to record an issue locally rather than on GitHub.
---

# Local Issue Management Skill

## When to Use

Use this skill when you need to create or list local issues stored in an SQLite database instead of GitHub issues.

## Instructions

### Extract the Issue Details

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
  - `simple` - Compact table without descriptions
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

List in simple table format:
```bash
.zac/skills/issue/scripts/list_issues.py --format simple
```

List in JSON format:
```bash
.zac/skills/issue/scripts/list_issues.py --format json
```

## Notes

- The database is located at `.zac/ISSUES.db` (relative to the current directory)
- Issues are created with status "OPEN" by default
- The table includes `created_at` and `updated_at` timestamps