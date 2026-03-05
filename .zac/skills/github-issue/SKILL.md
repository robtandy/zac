---
name: github-issue
description: Create a GitHub issue in the zac-dev repo using the gh CLI. Use when you need to file an issue with a provided title and body.
---

# GitHub Issue Creation Skill

## When to Use

Use this skill when you need to create a GitHub issue in the zac-dev repository.

## Instructions

### Important

Do not attempt to understand or fix the issue!  If the user wants to create a github issue, they merely want it recorded up at github so it can be fixed later.

### Extract the Issue Details

The user asks you to create an issue describes it.  Determine an appropriate title and use the user's description as the body.
- A short, appropriate title that you create to summarize the issue (~50 chars)
- The body as the **verbatim** text provided by the user (unchanged)

### Create the Issue

Run the create issue script with the title and description as arguments:

```bash
.zac/skills/github-issue/scripts/create_issue.sh "<title>" "<description>" [--repo <owner/repo>] [--label <label>]
```

The script accepts:
- `title` - Issue title (required)
- `description` - Issue description (required)
- `--repo` - Repository (default: robtandy/zac)
- `--label` - Label to add (optional, can be specified multiple times)

### Example

If the user provides:
```
There's a bug in the file handling code. When I try to delete a file that doesn't exist, the system crashes instead of showing a friendly error message. Can we fix this?
```

You would run:
```bash
.zac/skills/github-issue/scripts/create_issue.sh "System crashes when deleting non-existent file" "There's a bug in the file handling code. When I try to delete a file that doesn't exist, the system crashes instead of showing a friendly error message. Can we fix this?"
```

Or with a label:
```bash
.zac/skills/github-issue/scripts/create_issue.sh "Bug in file handling" "Description here" --label bug
```

## Notes

- The default repository is `robtandy/zac`
- The script uses the `gh` CLI to create issues