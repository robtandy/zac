#!/usr/bin/env python3
"""Add a comment to an issue in the SQLite database."""

import argparse
import os
import sqlite3
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description="Add a comment to an issue")
    parser.add_argument("issue_id", type=int, help="Issue ID")
    parser.add_argument("body", help="Comment body")
    parser.add_argument("--author", default="user", help="Comment author (default: user)")
    args = parser.parse_args()

    db_path = ".zac/ISSUES.db"
    
    if not os.path.exists(db_path):
        print("Error: Database does not exist")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if issue exists
    cursor.execute("SELECT id FROM issues WHERE id = ?", (args.issue_id,))
    if not cursor.fetchone():
        print(f"Error: Issue #{args.issue_id} not found")
        conn.close()
        return
    
    # Insert the comment
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO comments (issue_id, body, author, created_at) VALUES (?, ?, ?, ?)",
        (args.issue_id, args.body, args.author, now)
    )
    
    # Update issue's updated_at
    cursor.execute(
        "UPDATE issues SET updated_at = ? WHERE id = ?",
        (now, args.issue_id)
    )
    
    conn.commit()
    comment_id = cursor.lastrowid
    conn.close()
    
    print(f"Added comment #{comment_id} to issue #{args.issue_id}")


if __name__ == "__main__":
    main()