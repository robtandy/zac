#!/usr/bin/env python3
"""List issues from the SQLite database in markdown table format."""

import argparse
import os
import sqlite3


def main():
    parser = argparse.ArgumentParser(description="List local issues")
    parser.add_argument("--status", choices=["OPEN", "CLOSED", "INPUT_REQUIRED"], 
                        help="Filter by status")
    parser.add_argument("--format", default="markdown", choices=["markdown", "json"],
                        help="Output format")
    args = parser.parse_args()

    db_path = ".zac/ISSUES.db"
    
    if not os.path.exists(db_path):
        print("No issues found (database does not exist)")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if args.status:
        cursor.execute(
            "SELECT id, title, description, status, created_at FROM issues WHERE status = ? ORDER BY id ASC",
            (args.status,),
        )
    else:
        cursor.execute(
            "SELECT id, title, description, status, created_at FROM issues ORDER BY id ASC"
        )
    
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No issues found")
        return

    if args.format == "json":
        import json
        issues = [dict(row) for row in rows]
        print(json.dumps(issues, indent=2))
        return

    # Markdown table format
    print("| ID | Title | Status | Created |")
    print("|----|-------|--------|---------|")
    for row in rows:
        print(f"| {row['id']} | {row['title']} | {row['status']} | {row['created_at'][:10]} |")


if __name__ == "__main__":
    main()