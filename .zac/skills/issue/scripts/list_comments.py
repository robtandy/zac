#!/usr/bin/env python3
"""List comments for an issue from the SQLite database."""

import argparse
import os
import sqlite3


def main():
    parser = argparse.ArgumentParser(description="List comments for an issue")
    parser.add_argument("issue_id", type=int, help="Issue ID")
    parser.add_argument("--format", default="markdown", choices=["markdown", "json"],
                        help="Output format")
    args = parser.parse_args()

    db_path = ".zac/ISSUES.db"
    
    if not os.path.exists(db_path):
        print("Error: Database does not exist")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get issue
    cursor.execute("SELECT id, title FROM issues WHERE id = ?", (args.issue_id,))
    issue = cursor.fetchone()
    if not issue:
        print(f"Error: Issue #{args.issue_id} not found")
        conn.close()
        return
    
    # Get comments
    cursor.execute(
        "SELECT id, body, author, created_at FROM comments WHERE issue_id = ? ORDER BY created_at ASC",
        (args.issue_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if args.format == "json":
        import json
        print(json.dumps([dict(row) for row in rows], indent=2))
        return

    # Markdown format
    print(f"## Issue #{issue['id']}: {issue['title']}")
    print()
    
    if not rows:
        print("No comments yet.")
        return
    
    for row in rows:
        print(f"### Comment #{row['id']}")
        print(f"**Author:** {row['author']}")
        print(f"**Created:** {row['created_at'][:19].replace('T', ' ')}")
        print()
        print(row['body'])
        print()


if __name__ == "__main__":
    main()