---
name: github-issue
description: Create a GitHub issue in the zac-dev repo using the gh CLI. Use when you need to file an issue with a provided title and body.
---

# GitHub Issue Creation Skill

## When to Use

Use this skill when you need to create a GitHub issue in the zac-dev repository. The user will provide the issue title and description as arguments.

## Instructions

### Extract the Issue Details

The user will provide free-form text describing the issue. Parse this to determine:
- A short, appropriate title that you create to summarize the issue (~50 chars)
- The body as the **verbatim** text provided by the user (unchanged)

### Create the Issue

Run the following command with the extracted title and body:

```bash
gh issue create --title "<title>" --body "<body>" --repo zac-dev/zac-dev
```

### Example

If the user provides:
```
There's a bug in the file handling code. When I try to delete a file that doesn't exist, the system crashes instead of showing a friendly error message. Can we fix this?
```

I would:
- Title: "System crashes when deleting non-existent file"
- Body (verbatim): "There's a bug in the file handling code. When I try to delete a file that doesn't exist, the system crashes instead of showing a friendly error message. Can we fix this?"

Run:
```bash
gh issue create --title "System crashes when deleting non-existent file" --body "There's a bug in the file handling code. When I try to delete a file that doesn't exist, the system crashes instead of showing a friendly error message. Can we fix this?" --repo zac-dev/zac-dev
```

## Notes

- The `--repo zac-dev/zac-dev` flag targets the zac-dev repository
- If the body is empty, you can omit the `--body` flag and `gh` will prompt for it
- You can add labels with `--label "bug"` or `--label "enhancement"` if requested by the user
