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

Use the following Python code to create the issue in the SQLite database:

```python
import sqlite3
import os
from datetime import datetime

DB_PATH = "/root/zac-dev/.zac/ISSUES.db"

# Create DB and table if they don't exist
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS issues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
""")

# Insert the new issue with default status "OPEN"
created_at = datetime.utcnow().isoformat()
cursor.execute(
    "INSERT INTO issues (title, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
    (title, body, "OPEN", created_at, created_at)
)

conn.commit()
issue_id = cursor.lastrowid
conn.close()

print(f"Created issue #{issue_id}: {title}")
```

Replace `title` and `body` with the extracted issue details.

## Valid Status Values

- `OPEN` - Issue is open and needs to be addressed
- `CLOSED` - Issue has been resolved
- `INPUT_REQUIRED` - Issue needs more information from the user

## Notes

- The database is located at `/root/zac-dev/.zac/ISSUES.db`
- Issues are created with status "OPEN" by default
- The table includes `created_at` and `updated_at` timestamps
