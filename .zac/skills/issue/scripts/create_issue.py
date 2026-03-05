#!/usr/bin/env python3
"""Create a local issue in the SQLite database."""

import argparse
import os
import sqlite3
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description="Create a local issue")
    parser.add_argument("title", help="Issue title")
    parser.add_argument("description", help="Issue description")
    parser.add_argument("--status", default="OPEN", 
                        choices=["OPEN", "CLOSED", "INPUT_REQUIRED"],
                        help="Issue status (default: OPEN)")
    args = parser.parse_args()

    db_path = ".zac/ISSUES.db"
    
    # Create DB and table if they don't exist
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            cost REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    
    # Add cost column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE issues ADD COLUMN cost REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Create comments table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            author TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL,
            FOREIGN KEY (issue_id) REFERENCES issues(id) ON DELETE CASCADE
        )
    """)
    
    # Insert the new issue
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO issues (title, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (args.title, args.description, args.status, now, now)
    )
    
    conn.commit()
    issue_id = cursor.lastrowid
    conn.close()
    
    print(f"Created issue #{issue_id}: {args.title} [{args.status}]")


if __name__ == "__main__":
    main()