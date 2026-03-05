---
name: issue
description: Create a local issue stored in an SQLite database. Use when you want to record an issue locally rather than on GitHub.
---

# Local Issue Creation Skill

## When to Use

Use this skill when you need to create a local issue stored in an SQLite database instead of a GitHub issue.

## Instructions

### Extract the Issue Details

The user asks you to create an issue and provides a description. Determine an appropriate title and use the user's description as the body.
- A short, appropriate title that you create to summarize the issue (~50 chars)
- The body as the **verbatim** text provided by the user (unchanged)

### Create the Issue

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

## Example

If the user provides:
```
There's a bug in the file handling code. When I try to delete a file that doesn't exist, the system crashes instead of showing a friendly error message. Can we fix this?
```

You would run:
```bash
.zac/skills/issue/scripts/create_issue.py "System crashes when deleting non-existent file" "There's a bug in the file handling code. When I try to delete a file that doesn't exist, the system crashes instead of showing a friendly error message. Can we fix this?"
```

## Notes

- The database is located at `/root/zac-dev/.zac/ISSUES.db`
- Issues are created with status "OPEN" by default
- The table includes `created_at` and `updated_at` timestamps