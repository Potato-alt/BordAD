from __future__ import annotations

from app.db import Database


STATUS_NAMES = {
    -1: "N/A",
    101: "UP",
    102: "CORRUPT",
    103: "MUMBLE",
    104: "DOWN",
    110: "CHECK_FAILED",
}


def get_summary(db: Database) -> dict[str, int | str]:
    counts = {"queued": 0, "submitting": 0, "accepted": 0, "rejected": 0, "error": 0}
    for row in db.fetch_all("SELECT status, COUNT(*) AS count FROM flags GROUP BY status"):
        counts[str(row["status"])] = int(row["count"])
    counts["last_poll_error"] = db.get_state("last_poll_error", "")
    counts["last_submit_error"] = db.get_state("last_submit_error", "")
    return counts


def get_recent_flags(db: Database, limit: int = 50):
    return db.fetch_all(
        """
        SELECT flag, source, status, response_msg, created_at, submitted_at
        FROM flags
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )


def get_service_matrix(db: Database):
    return db.fetch_all(
        """
        WITH latest AS (
            SELECT s.*
            FROM teamtask_snapshots s
            JOIN (
                SELECT team_id, task_id, MAX(round) AS max_round
                FROM teamtask_snapshots
                GROUP BY team_id, task_id
            ) m ON m.team_id = s.team_id AND m.task_id = s.task_id AND m.max_round = s.round
        )
        SELECT latest.*, teams.name AS team_name, tasks.name AS task_name
        FROM latest
        LEFT JOIN teams ON teams.team_id = latest.team_id
        LEFT JOIN tasks ON tasks.task_id = latest.task_id
        ORDER BY tasks.name, teams.name
        """
    )


def get_attack_recommendations(db: Database, our_team_id: int, limit: int = 20):
    return db.fetch_all(
        """
        WITH latest AS (
            SELECT s.*
            FROM teamtask_snapshots s
            JOIN (
                SELECT team_id, task_id, MAX(round) AS max_round
                FROM teamtask_snapshots
                GROUP BY team_id, task_id
            ) m ON m.team_id = s.team_id AND m.task_id = s.task_id AND m.max_round = s.round
        ), previous AS (
            SELECT s.*
            FROM teamtask_snapshots s
            JOIN latest l ON l.team_id = s.team_id AND l.task_id = s.task_id
            WHERE s.round < l.round
            GROUP BY s.team_id, s.task_id
            HAVING s.round = MAX(s.round)
        ), task_heat AS (
            SELECT task_id, COUNT(*) AS teams_losing
            FROM latest
            WHERE team_id != ? AND lost > 0
            GROUP BY task_id
        )
        SELECT
            l.team_id,
            l.task_id,
            COALESCE(teams.name, 'team #' || l.team_id) AS team_name,
            COALESCE(tasks.name, 'task #' || l.task_id) AS task_name,
            l.round,
            l.status,
            l.lost,
            l.stolen,
            MAX(0, l.lost - COALESCE(p.lost, 0)) AS lost_delta,
            COALESCE(task_heat.teams_losing, 0) AS teams_losing,
            (MAX(0, l.lost - COALESCE(p.lost, 0)) * 5 + COALESCE(task_heat.teams_losing, 0) * 3 + CASE WHEN l.status = 101 THEN 10 ELSE 0 END) AS priority
        FROM latest l
        LEFT JOIN previous p ON p.team_id = l.team_id AND p.task_id = l.task_id
        LEFT JOIN task_heat ON task_heat.task_id = l.task_id
        LEFT JOIN teams ON teams.team_id = l.team_id
        LEFT JOIN tasks ON tasks.task_id = l.task_id
        WHERE l.team_id != ?
        ORDER BY priority DESC, lost_delta DESC, l.lost DESC
        LIMIT ?
        """,
        (our_team_id, our_team_id, limit),
    )


def get_defense_recommendations(db: Database, our_team_id: int, limit: int = 20):
    return db.fetch_all(
        """
        WITH latest AS (
            SELECT s.*
            FROM teamtask_snapshots s
            JOIN (
                SELECT team_id, task_id, MAX(round) AS max_round
                FROM teamtask_snapshots
                WHERE team_id = ?
                GROUP BY team_id, task_id
            ) m ON m.team_id = s.team_id AND m.task_id = s.task_id AND m.max_round = s.round
        ), previous AS (
            SELECT s.*
            FROM teamtask_snapshots s
            JOIN latest l ON l.team_id = s.team_id AND l.task_id = s.task_id
            WHERE s.round < l.round
            GROUP BY s.team_id, s.task_id
            HAVING s.round = MAX(s.round)
        ), external_heat AS (
            SELECT task_id, SUM(lost) AS total_lost
            FROM teamtask_snapshots
            WHERE team_id != ?
            GROUP BY task_id
        )
        SELECT
            l.team_id,
            l.task_id,
            COALESCE(tasks.name, 'task #' || l.task_id) AS task_name,
            l.round,
            l.status,
            l.lost,
            l.stolen,
            MAX(0, l.lost - COALESCE(p.lost, 0)) AS lost_delta,
            COALESCE(external_heat.total_lost, 0) AS external_total_lost,
            (MAX(0, l.lost - COALESCE(p.lost, 0)) * 8 + CASE WHEN COALESCE(external_heat.total_lost, 0) > 0 THEN 10 ELSE 0 END + CASE WHEN l.status = 101 THEN 5 ELSE 0 END) AS priority
        FROM latest l
        LEFT JOIN previous p ON p.team_id = l.team_id AND p.task_id = l.task_id
        LEFT JOIN external_heat ON external_heat.task_id = l.task_id
        LEFT JOIN tasks ON tasks.task_id = l.task_id
        ORDER BY priority DESC, lost_delta DESC, l.lost DESC
        LIMIT ?
        """,
        (our_team_id, our_team_id, limit),
    )
