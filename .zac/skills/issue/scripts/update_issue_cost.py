#!/usr/bin/env python3
"""Update the cost of an issue in the SQLite database."""

import argparse
import os
import sqlite3


def main():
    parser = argparse.ArgumentParser(description="Update issue cost")
    parser.add_argument("issue_id", type=int, help="Issue ID")
    parser.add_argument("cost", type=float, help="Cost to add (or set total)")
    parser.add_argument("--add", action="store_true", 
                        help="Add to existing cost instead of replacing")
    args = parser.parse_args()

    db_path = ".zac/ISSUES.db"
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if args.add:
        # Add to existing cost
        cursor.execute(
            "UPDATE issues SET cost = cost + ? WHERE id = ?",
            (args.cost, args.issue_id)
        )
    else:
        # Replace cost
        cursor.execute(
            "UPDATE issues SET cost = ? WHERE id = ?",
            (args.cost, args.issue_id)
        )
    
    if cursor.rowcount == 0:
        print(f"Error: Issue #{args.issue_id} not found")
        conn.close()
        return

    conn.commit()
    
    # Get the updated cost
    cursor.execute("SELECT cost FROM issues WHERE id = ?", (args.issue_id,))
    new_cost = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"Updated issue #{args.issue_id} cost: ${new_cost:.4f}")


if __name__ == "__main__":
    main()
