"""SQLite persistence for permission grants and action requests."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    ActionRequest,
    ActionStatus,
    Expiration,
    PermissionGrant,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS permission_grants (
    id TEXT PRIMARY KEY,
    permission_name TEXT NOT NULL,
    handler_id TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT '{}',
    expiration TEXT NOT NULL DEFAULT 'indefinite',
    expires_at TEXT,
    granted_at TEXT NOT NULL,
    granted_by TEXT NOT NULL DEFAULT 'user'
);

CREATE TABLE IF NOT EXISTS action_requests (
    id TEXT PRIMARY KEY,
    handler_id TEXT NOT NULL,
    action_name TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    permission_name TEXT NOT NULL DEFAULT '',
    permission_scope TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_grants_lookup
    ON permission_grants(handler_id, permission_name);

CREATE INDEX IF NOT EXISTS idx_requests_status
    ON action_requests(status);
"""


def _dt_to_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _str_to_dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    return datetime.fromisoformat(s)


class Store:
    """SQLite-backed persistence for grants and action requests."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # ── Permission Grants ──

    def save_grant(self, grant: PermissionGrant) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO permission_grants
               (id, permission_name, handler_id, scope, expiration, expires_at, granted_at, granted_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                grant.id,
                grant.permission_name,
                grant.handler_id,
                json.dumps(grant.scope),
                grant.expiration.value,
                _dt_to_str(grant.expires_at),
                _dt_to_str(grant.granted_at),
                grant.granted_by,
            ),
        )
        self._conn.commit()

    def get_grants(
        self, handler_id: str, permission_name: str
    ) -> list[PermissionGrant]:
        rows = self._conn.execute(
            """SELECT * FROM permission_grants
               WHERE handler_id = ? AND permission_name = ?""",
            (handler_id, permission_name),
        ).fetchall()
        return [self._row_to_grant(r) for r in rows]

    def get_all_grants(self) -> list[PermissionGrant]:
        rows = self._conn.execute("SELECT * FROM permission_grants").fetchall()
        return [self._row_to_grant(r) for r in rows]

    def delete_grant(self, grant_id: str) -> None:
        self._conn.execute(
            "DELETE FROM permission_grants WHERE id = ?", (grant_id,)
        )
        self._conn.commit()

    def _row_to_grant(self, row: sqlite3.Row) -> PermissionGrant:
        return PermissionGrant(
            id=row["id"],
            permission_name=row["permission_name"],
            handler_id=row["handler_id"],
            scope=json.loads(row["scope"]),
            expiration=Expiration(row["expiration"]),
            expires_at=_str_to_dt(row["expires_at"]),
            granted_at=_str_to_dt(row["granted_at"]),  # type: ignore[arg-type]
            granted_by=row["granted_by"],
        )

    # ── Action Requests ──

    def save_action(self, action: ActionRequest) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO action_requests
               (id, handler_id, action_name, params, permission_name, permission_scope,
                status, result, error, created_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                action.id,
                action.handler_id,
                action.action_name,
                json.dumps(action.params),
                action.permission_name,
                json.dumps(action.permission_scope),
                action.status.value,
                json.dumps(action.result) if action.result is not None else None,
                action.error,
                _dt_to_str(action.created_at),
                _dt_to_str(action.completed_at),
            ),
        )
        self._conn.commit()

    def get_action(self, action_id: str) -> ActionRequest | None:
        row = self._conn.execute(
            "SELECT * FROM action_requests WHERE id = ?", (action_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_action(row)

    def get_pending_actions(self) -> list[ActionRequest]:
        rows = self._conn.execute(
            "SELECT * FROM action_requests WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [self._row_to_action(r) for r in rows]

    def get_actions_by_status(self, status: ActionStatus) -> list[ActionRequest]:
        rows = self._conn.execute(
            "SELECT * FROM action_requests WHERE status = ? ORDER BY created_at",
            (status.value,),
        ).fetchall()
        return [self._row_to_action(r) for r in rows]

    def _row_to_action(self, row: sqlite3.Row) -> ActionRequest:
        result_raw = row["result"]
        result = json.loads(result_raw) if result_raw is not None else None
        return ActionRequest(
            id=row["id"],
            handler_id=row["handler_id"],
            action_name=row["action_name"],
            params=json.loads(row["params"]),
            permission_name=row["permission_name"],
            permission_scope=json.loads(row["permission_scope"]),
            status=ActionStatus(row["status"]),
            result=result,
            error=row["error"],
            created_at=_str_to_dt(row["created_at"]),  # type: ignore[arg-type]
            completed_at=_str_to_dt(row["completed_at"]),
        )
