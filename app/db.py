from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flag TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    response_msg TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    submitted_at REAL
);

CREATE INDEX IF NOT EXISTS idx_flags_status ON flags(status);
CREATE INDEX IF NOT EXISTS idx_flags_created_at ON flags(created_at);

CREATE TABLE IF NOT EXISTS teams (
    team_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    ip TEXT NOT NULL DEFAULT '',
    highlighted INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS teamtask_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round INTEGER NOT NULL DEFAULT 0,
    team_id INTEGER NOT NULL,
    task_id INTEGER NOT NULL,
    status INTEGER NOT NULL DEFAULT -1,
    stolen INTEGER NOT NULL DEFAULT 0,
    lost INTEGER NOT NULL DEFAULT 0,
    score REAL NOT NULL DEFAULT 0,
    checks INTEGER NOT NULL DEFAULT 0,
    checks_passed INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    forcead_timestamp TEXT NOT NULL DEFAULT '',
    observed_at REAL NOT NULL,
    UNIQUE(round, team_id, task_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_team_task ON teamtask_snapshots(team_id, task_id, round);
CREATE INDEX IF NOT EXISTS idx_snapshots_task_round ON teamtask_snapshots(task_id, round);

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    def init(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def set_state(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_state(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, time.time()),
            )

    def get_state(self, key: str, default: str = "") -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else default

    def add_flags(self, flags: list[str], source: str) -> dict[str, int]:
        added = 0
        duplicates = 0
        now = time.time()
        with self.connect() as conn:
            for flag in flags:
                try:
                    conn.execute(
                        "INSERT INTO flags(flag, source, status, created_at) VALUES (?, ?, 'queued', ?)",
                        (flag, source, now),
                    )
                    added += 1
                except sqlite3.IntegrityError:
                    duplicates += 1
        return {"added": added, "duplicates": duplicates}

    def claim_queued_flags(self, limit: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, flag FROM flags WHERE status = 'queued' ORDER BY created_at LIMIT ?",
                (limit,),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                conn.execute(f"UPDATE flags SET status = 'submitting' WHERE id IN ({placeholders})", ids)
            return rows

    def mark_submit_results(self, results: list[tuple[str, str, str]]) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.executemany(
                "UPDATE flags SET status = ?, response_msg = ?, submitted_at = ? WHERE flag = ?",
                [(status, msg, now, flag) for flag, status, msg in results],
            )

    def requeue_flags(self, flags: list[str], message: str) -> None:
        with self.connect() as conn:
            conn.executemany(
                "UPDATE flags SET status = 'queued', response_msg = ? WHERE flag = ?",
                [(message, flag) for flag in flags],
            )

    def upsert_teams(self, teams: list[dict[str, Any]]) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO teams(team_id, name, ip, highlighted, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(team_id) DO UPDATE SET
                    name=excluded.name,
                    ip=excluded.ip,
                    highlighted=excluded.highlighted,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        int(team.get("id", 0)),
                        str(team.get("name", "")),
                        str(team.get("ip", "")),
                        1 if team.get("highlighted") else 0,
                        now,
                    )
                    for team in teams
                    if team.get("id") is not None
                ],
            )

    def upsert_tasks(self, tasks: list[dict[str, Any]]) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO tasks(task_id, name, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at
                """,
                [(int(task.get("id", 0)), str(task.get("name", "")), now) for task in tasks if task.get("id") is not None],
            )

    def insert_snapshots(self, rows: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO teamtask_snapshots(
                    round, team_id, task_id, status, stolen, lost, score,
                    checks, checks_passed, message, forcead_timestamp, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        int(row.get("round") or 0),
                        int(row.get("team_id") or 0),
                        int(row.get("task_id") or 0),
                        int(row.get("status") or -1),
                        int(row.get("stolen") or 0),
                        int(row.get("lost") or 0),
                        float(row.get("score") or 0),
                        int(row.get("checks") or 0),
                        int(row.get("checks_passed") or 0),
                        str(row.get("message") or ""),
                        str(row.get("timestamp") or ""),
                        time.time(),
                    )
                    for row in rows
                    if row.get("team_id") is not None and row.get("task_id") is not None
                ],
            )

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(query, params).fetchall()

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(query, params).fetchone()
