from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from config import (
    DATA_DIR,
    DB_PATH,
    DEFAULT_ALERT_COOLDOWN_SECONDS,
    DEFAULT_AUTO_KILL_ENABLED,
    DEFAULT_BLACKLIST,
    DEFAULT_DAILY_GOAL_MINUTES,
    DEFAULT_GOALS,
    DEFAULT_STARTUP_ENABLED,
    UNCATEGORIZED_GOAL_ID,
    UNCATEGORIZED_GOAL_NAME,
)


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_summary (
                day TEXT PRIMARY KEY,
                first_start_at TEXT,
                total_pc_seconds INTEGER NOT NULL DEFAULT 0,
                creative_seconds INTEGER NOT NULL DEFAULT 0,
                game_seconds INTEGER NOT NULL DEFAULT 0,
                target_minutes INTEGER NOT NULL DEFAULT 60,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS creative_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                icon TEXT NOT NULL,
                color TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weekly_goals (
                id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL,
                goal_name TEXT NOT NULL,
                target_minutes INTEGER NOT NULL,
                week_start_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(goal_id, week_start_date)
            );

            CREATE TABLE IF NOT EXISTS game_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                process_names TEXT NOT NULL,
                creative_remaining_seconds INTEGER NOT NULL,
                action_taken TEXT NOT NULL
            );
            """
        )
        _ensure_default_settings(conn)
        _ensure_migrations(conn)
        _ensure_default_goals(conn)


def _ensure_default_settings(conn: sqlite3.Connection) -> None:
    defaults = {
        "daily_goal_minutes": str(DEFAULT_DAILY_GOAL_MINUTES),
        "game_process_blacklist": "\n".join(DEFAULT_BLACKLIST),
        "auto_kill_enabled": "0" if not DEFAULT_AUTO_KILL_ENABLED else "1",
        "startup_enabled": "0" if not DEFAULT_STARTUP_ENABLED else "1",
        "alert_cooldown_seconds": str(DEFAULT_ALERT_COOLDOWN_SECONDS),
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.commit()


def _ensure_migrations(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(daily_summary)").fetchall()}
    if "game_seconds" not in columns:
        conn.execute("ALTER TABLE daily_summary ADD COLUMN game_seconds INTEGER NOT NULL DEFAULT 0")

    session_columns = {row["name"] for row in conn.execute("PRAGMA table_info(creative_sessions)").fetchall()}
    if "goal_id" not in session_columns:
        conn.execute("ALTER TABLE creative_sessions ADD COLUMN goal_id TEXT NOT NULL DEFAULT 'goal_uncategorized'")
    if "goal_name" not in session_columns:
        conn.execute("ALTER TABLE creative_sessions ADD COLUMN goal_name TEXT NOT NULL DEFAULT '未分类'")
    if "created_at" not in session_columns:
        conn.execute("ALTER TABLE creative_sessions ADD COLUMN created_at TEXT")
        conn.execute(
            """
            UPDATE creative_sessions
            SET created_at = COALESCE(end_at, start_at, ?)
            WHERE created_at IS NULL
            """,
            (now_iso(),),
        )

    _migrate_legacy_default_blacklist(conn)
    conn.commit()


def _ensure_default_goals(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()
    conn.execute(
        """
        INSERT OR IGNORE INTO goals (id, name, icon, color, archived, created_at, updated_at)
        VALUES (?, ?, ?, ?, 0, ?, ?)
        """,
        (UNCATEGORIZED_GOAL_ID, UNCATEGORIZED_GOAL_NAME, "Circle", "#64748B", timestamp, timestamp),
    )
    for goal in DEFAULT_GOALS:
        conn.execute(
            """
            INSERT OR IGNORE INTO goals (id, name, icon, color, archived, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (goal["id"], goal["name"], goal["icon"], goal["color"], timestamp, timestamp),
        )
    conn.commit()


def _migrate_legacy_default_blacklist(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        ("game_process_blacklist",),
    ).fetchone()
    if row is None:
        return

    legacy_default = "\n".join(
        [
            "steam.exe",
            "client-win64-shipping.exe",
            "wuthering waves.exe",
        ]
    )
    current_value = str(row["value"]).replace("\r\n", "\n").strip()
    if current_value != legacy_default:
        return

    conn.execute(
        "UPDATE settings SET value = ? WHERE key = ?",
        ("\n".join(DEFAULT_BLACKLIST), "game_process_blacklist"),
    )


def get_setting(key: str, default: str | None = None) -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        conn.commit()


def load_settings() -> dict[str, str]:
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_today_day() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_week_start(day: str | None = None) -> str:
    current = date.fromisoformat(day) if day else date.today()
    return (current - timedelta(days=current.weekday())).isoformat()


def ensure_daily_record(day: str | None = None, target_minutes: int | None = None) -> None:
    day = day or get_today_day()
    target_minutes = (
        target_minutes
        if target_minutes is not None
        else int(get_setting("daily_goal_minutes", str(DEFAULT_DAILY_GOAL_MINUTES)) or DEFAULT_DAILY_GOAL_MINUTES)
    )
    timestamp = now_iso()
    with _connect() as conn:
        row = conn.execute("SELECT day, first_start_at FROM daily_summary WHERE day = ?", (day,)).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO daily_summary (
                    day, first_start_at, total_pc_seconds, creative_seconds, target_minutes, updated_at
                ) VALUES (?, ?, 0, 0, ?, ?)
                """,
                (day, timestamp, target_minutes, timestamp),
            )
        else:
            conn.execute(
                """
                UPDATE daily_summary
                SET target_minutes = ?, updated_at = ?
                WHERE day = ?
                """,
                (target_minutes, timestamp, day),
            )
            if row["first_start_at"] is None:
                conn.execute(
                    "UPDATE daily_summary SET first_start_at = ? WHERE day = ?",
                    (timestamp, day),
                )
        conn.commit()


def touch_first_start(day: str | None = None) -> None:
    day = day or get_today_day()
    timestamp = now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO daily_summary (
                day, first_start_at, total_pc_seconds, creative_seconds, target_minutes, updated_at
            ) VALUES (?, ?, 0, 0, ?, ?)
            ON CONFLICT(day) DO UPDATE SET
                first_start_at = COALESCE(daily_summary.first_start_at, excluded.first_start_at),
                updated_at = excluded.updated_at
            """,
            (
                day,
                timestamp,
                int(get_setting("daily_goal_minutes", str(DEFAULT_DAILY_GOAL_MINUTES)) or DEFAULT_DAILY_GOAL_MINUTES),
                timestamp,
            ),
        )
        conn.commit()


def add_pc_seconds(day: str, seconds: int) -> None:
    if seconds <= 0:
        return
    with _connect() as conn:
        conn.execute(
            """
            UPDATE daily_summary
            SET total_pc_seconds = total_pc_seconds + ?, updated_at = ?
            WHERE day = ?
            """,
            (seconds, now_iso(), day),
        )
        conn.commit()


def add_game_seconds(day: str, seconds: int) -> None:
    if seconds <= 0:
        return
    with _connect() as conn:
        conn.execute(
            """
            UPDATE daily_summary
            SET game_seconds = game_seconds + ?, updated_at = ?
            WHERE day = ?
            """,
            (seconds, now_iso(), day),
        )
        conn.commit()


def add_creative_session(
    day: str,
    start_at: str,
    end_at: str,
    duration_seconds: int,
    goal_id: str | None = None,
    goal_name: str | None = None,
) -> None:
    if duration_seconds <= 0:
        return
    goal_id = goal_id or UNCATEGORIZED_GOAL_ID
    goal_name = goal_name or UNCATEGORIZED_GOAL_NAME
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO creative_sessions (day, start_at, end_at, duration_seconds, goal_id, goal_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (day, start_at, end_at, duration_seconds, goal_id, goal_name, now_iso()),
        )
        conn.execute(
            """
            UPDATE daily_summary
            SET creative_seconds = creative_seconds + ?, updated_at = ?
            WHERE day = ?
            """,
            (duration_seconds, now_iso(), day),
        )
        conn.commit()


def get_goals(include_archived: bool = False) -> list[dict[str, Any]]:
    with _connect() as conn:
        if include_archived:
            rows = conn.execute(
                """
                SELECT id, name, icon, color, archived, created_at, updated_at
                FROM goals
                ORDER BY archived ASC, name ASC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, name, icon, color, archived, created_at, updated_at
                FROM goals
                WHERE archived = 0 AND id != ?
                ORDER BY name ASC
                """,
                (UNCATEGORIZED_GOAL_ID,),
            ).fetchall()
    return [dict(row) for row in rows]


def get_goal(goal_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, icon, color, archived, created_at, updated_at
            FROM goals
            WHERE id = ?
            """,
            (goal_id,),
        ).fetchone()
    return dict(row) if row else None


def create_goal(name: str, icon: str = "PenLine", color: str = "#4D8EFF") -> dict[str, Any]:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("目标名称不能为空。")
    goal_id = f"goal_{uuid.uuid4().hex[:10]}"
    timestamp = now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO goals (id, name, icon, color, archived, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (goal_id, clean_name, icon.strip() or "PenLine", color.strip() or "#4D8EFF", timestamp, timestamp),
        )
        conn.commit()
    return {
        "id": goal_id,
        "name": clean_name,
        "icon": icon.strip() or "PenLine",
        "color": color.strip() or "#4D8EFF",
        "archived": 0,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def update_goal(goal_id: str, name: str, icon: str, color: str) -> None:
    if goal_id == UNCATEGORIZED_GOAL_ID:
        raise ValueError("未分类目标不能编辑。")
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("目标名称不能为空。")
    timestamp = now_iso()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE goals
            SET name = ?, icon = ?, color = ?, updated_at = ?
            WHERE id = ? AND archived = 0
            """,
            (clean_name, icon.strip() or "PenLine", color.strip() or "#4D8EFF", timestamp, goal_id),
        )
        conn.execute(
            """
            UPDATE weekly_goals
            SET goal_name = ?, updated_at = ?
            WHERE goal_id = ?
            """,
            (clean_name, timestamp, goal_id),
        )
        conn.commit()


def archive_goal(goal_id: str) -> None:
    if goal_id == UNCATEGORIZED_GOAL_ID:
        raise ValueError("未分类目标不能归档。")
    timestamp = now_iso()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE goals
            SET archived = 1, updated_at = ?
            WHERE id = ?
            """,
            (timestamp, goal_id),
        )
        conn.commit()


def get_last_goal() -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT g.id, g.name, g.icon, g.color, g.archived, g.created_at, g.updated_at
            FROM creative_sessions s
            LEFT JOIN goals g ON g.id = s.goal_id
            WHERE s.goal_id IS NOT NULL AND s.goal_id != ? AND COALESCE(g.archived, 0) = 0
            ORDER BY s.id DESC
            LIMIT 1
            """,
            (UNCATEGORIZED_GOAL_ID,),
        ).fetchone()
    return dict(row) if row and row["id"] else None


def get_recent_goals(limit: int = 3) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                g.id,
                COALESCE(g.name, s.goal_name) AS name,
                COALESCE(g.icon, 'Circle') AS icon,
                COALESCE(g.color, '#64748B') AS color,
                MAX(s.id) AS last_session_id
            FROM creative_sessions s
            LEFT JOIN goals g ON g.id = s.goal_id
            WHERE COALESCE(g.archived, 0) = 0
            GROUP BY s.goal_id, COALESCE(g.name, s.goal_name), COALESCE(g.icon, 'Circle'), COALESCE(g.color, '#64748B')
            ORDER BY last_session_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def set_weekly_goal(goal_id: str, target_minutes: int, week_start_date: str | None = None) -> None:
    target_minutes = max(0, int(target_minutes))
    week_start_date = week_start_date or get_week_start()
    goal = get_goal(goal_id)
    if goal is None:
        return
    weekly_id = f"weekly_{goal_id}_{week_start_date.replace('-', '_')}"
    timestamp = now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO weekly_goals (id, goal_id, goal_name, target_minutes, week_start_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(goal_id, week_start_date) DO UPDATE SET
                goal_name = excluded.goal_name,
                target_minutes = excluded.target_minutes,
                updated_at = excluded.updated_at
            """,
            (weekly_id, goal_id, goal["name"], target_minutes, week_start_date, timestamp, timestamp),
        )
        conn.commit()


def get_weekly_goals(week_start_date: str | None = None) -> list[dict[str, Any]]:
    week_start_date = week_start_date or get_week_start()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                g.id AS goal_id,
                g.name AS goal_name,
                g.icon,
                g.color,
                COALESCE(w.target_minutes, 0) AS target_minutes,
                COALESCE(w.week_start_date, ?) AS week_start_date
            FROM goals g
            LEFT JOIN weekly_goals w ON w.goal_id = g.id AND w.week_start_date = ?
            WHERE g.archived = 0 AND g.id != ?
            ORDER BY g.name ASC
            """,
            (week_start_date, week_start_date, UNCATEGORIZED_GOAL_ID),
        ).fetchall()
    return [dict(row) for row in rows]


def get_weekly_goal_progress(week_start_date: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    week_start_date = week_start_date or get_week_start()
    week_end = (date.fromisoformat(week_start_date) + timedelta(days=6)).isoformat()
    query = """
        SELECT
            w.goal_id,
            w.goal_name,
            COALESCE(g.icon, 'Circle') AS icon,
            COALESCE(g.color, '#64748B') AS color,
            w.target_minutes,
            w.week_start_date,
            COALESCE(SUM(s.duration_seconds), 0) AS completed_seconds
        FROM weekly_goals w
        LEFT JOIN goals g ON g.id = w.goal_id
        LEFT JOIN creative_sessions s
            ON s.goal_id = w.goal_id
            AND s.day BETWEEN ? AND ?
        WHERE w.week_start_date = ? AND w.target_minutes > 0
        GROUP BY w.goal_id, w.goal_name, g.icon, g.color, w.target_minutes, w.week_start_date
        ORDER BY
            CASE WHEN w.target_minutes > 0 THEN CAST(COALESCE(SUM(s.duration_seconds), 0) AS REAL) / (w.target_minutes * 60) ELSE 0 END DESC,
            w.goal_name ASC
    """
    params: list[Any] = [week_start_date, week_end, week_start_date]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        completed_minutes = int(item["completed_seconds"] or 0) // 60
        target_minutes = int(item["target_minutes"] or 0)
        progress = completed_minutes / target_minutes if target_minutes > 0 else 0
        item["completed_minutes"] = completed_minutes
        item["progress"] = progress
        result.append(item)
    return result


def get_goal_time_stats(limit: int | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT
            s.goal_id,
            COALESCE(g.name, MAX(s.goal_name)) AS goal_name,
            COALESCE(g.icon, 'Circle') AS icon,
            COALESCE(g.color, '#64748B') AS color,
            COALESCE(SUM(s.duration_seconds), 0) AS total_seconds,
            COUNT(s.id) AS session_count
        FROM creative_sessions s
        LEFT JOIN goals g ON g.id = s.goal_id
        GROUP BY s.goal_id, g.name, g.icon, g.color
        ORDER BY total_seconds DESC
    """
    params: list[Any] = []
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_streak_stats() -> dict[str, int]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT day, creative_seconds, target_minutes
            FROM daily_summary
            ORDER BY day ASC
            """
        ).fetchall()

    completed_days = {
        row["day"]
        for row in rows
        if int(row["creative_seconds"] or 0) >= int(row["target_minutes"] or 0) * 60
    }

    today = date.today()
    current_streak = 0
    cursor = today
    while cursor.isoformat() in completed_days:
        current_streak += 1
        cursor -= timedelta(days=1)

    best_streak = 0
    running = 0
    previous_day: date | None = None
    for row in rows:
        day = date.fromisoformat(str(row["day"]))
        is_completed = str(row["day"]) in completed_days
        if is_completed:
            if previous_day is not None and day == previous_day + timedelta(days=1):
                running += 1
            else:
                running = 1
            best_streak = max(best_streak, running)
        else:
            running = 0
        previous_day = day

    return {
        "current_streak": current_streak,
        "best_streak": best_streak,
    }


def get_best_creative_session(day: str | None = None) -> dict[str, Any] | None:
    day = day or get_today_day()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT day, goal_id, goal_name, start_at, end_at, duration_seconds
            FROM creative_sessions
            WHERE day = ?
            ORDER BY duration_seconds DESC, id DESC
            LIMIT 1
            """,
            (day,),
        ).fetchone()
    return dict(row) if row else None


def get_weekly_review(week_start_date: str | None = None) -> dict[str, Any]:
    week_start_date = week_start_date or get_week_start()
    start = date.fromisoformat(week_start_date)
    end = start + timedelta(days=6)
    previous_start = start - timedelta(days=7)
    previous_end = start - timedelta(days=1)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT day, creative_seconds, game_seconds, target_minutes
            FROM daily_summary
            WHERE day BETWEEN ? AND ?
            ORDER BY day ASC
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        previous = conn.execute(
            """
            SELECT COALESCE(SUM(creative_seconds), 0) AS creative_seconds
            FROM daily_summary
            WHERE day BETWEEN ? AND ?
            """,
            (previous_start.isoformat(), previous_end.isoformat()),
        ).fetchone()

    row_by_day = {str(row["day"]): row for row in rows}
    total_creative_seconds = sum(int(row["creative_seconds"] or 0) for row in rows)
    total_game_seconds = sum(int(row["game_seconds"] or 0) for row in rows)
    completed_days = sum(
        1
        for row in rows
        if int(row["creative_seconds"] or 0) >= int(row["target_minutes"] or 0) * 60
    )
    best_day = None
    best_day_seconds = 0
    longest_creative_streak = 0
    running_creative_streak = 0
    today = date.today()
    for offset in range(7):
        day = start + timedelta(days=offset)
        row = row_by_day.get(day.isoformat())
        creative_seconds = int(row["creative_seconds"] or 0) if row else 0
        if creative_seconds > best_day_seconds:
            best_day = day.isoformat()
            best_day_seconds = creative_seconds
        if day <= today and creative_seconds > 0:
            running_creative_streak += 1
            longest_creative_streak = max(longest_creative_streak, running_creative_streak)
        else:
            running_creative_streak = 0

    previous_creative_seconds = int(previous["creative_seconds"] or 0) if previous else 0
    return {
        "week_start_date": start.isoformat(),
        "week_end_date": end.isoformat(),
        "total_creative_seconds": total_creative_seconds,
        "total_game_seconds": total_game_seconds,
        "completed_days": completed_days,
        "creative_streak_days": longest_creative_streak,
        "best_day": best_day,
        "best_day_creative_seconds": best_day_seconds,
        "previous_creative_seconds": previous_creative_seconds,
        "creative_delta_seconds": total_creative_seconds - previous_creative_seconds,
    }


def update_daily_target(day: str, target_minutes: int) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE daily_summary
            SET target_minutes = ?, updated_at = ?
            WHERE day = ?
            """,
            (target_minutes, now_iso(), day),
        )
        conn.commit()


def record_game_event(
    day: str,
    process_names: list[str],
    creative_remaining_seconds: int,
    action_taken: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO game_events (day, detected_at, process_names, creative_remaining_seconds, action_taken)
            VALUES (?, ?, ?, ?, ?)
            """,
            (day, now_iso(), ", ".join(sorted(process_names)), creative_remaining_seconds, action_taken),
        )
        conn.commit()


def get_daily_summary(day: str | None = None) -> dict[str, Any] | None:
    day = day or get_today_day()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM daily_summary WHERE day = ?", (day,)).fetchone()
    return dict(row) if row else None


def get_recent_summaries(limit: int | None = 30) -> list[dict[str, Any]]:
    with _connect() as conn:
        if limit is None:
            rows = conn.execute(
                """
                SELECT
                    d.day,
                    d.first_start_at,
                    d.total_pc_seconds,
                    d.creative_seconds,
                    d.game_seconds,
                    d.target_minutes,
                    d.updated_at,
                    COALESCE(COUNT(c.id), 0) AS creative_session_count
                FROM daily_summary d
                LEFT JOIN creative_sessions c ON c.day = d.day
                GROUP BY d.day, d.first_start_at, d.total_pc_seconds, d.creative_seconds, d.target_minutes, d.updated_at
                ORDER BY d.day DESC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    d.day,
                    d.first_start_at,
                    d.total_pc_seconds,
                    d.creative_seconds,
                    d.game_seconds,
                    d.target_minutes,
                    d.updated_at,
                    COALESCE(COUNT(c.id), 0) AS creative_session_count
                FROM daily_summary d
                LEFT JOIN creative_sessions c ON c.day = d.day
                GROUP BY d.day, d.first_start_at, d.total_pc_seconds, d.creative_seconds, d.target_minutes, d.updated_at
                ORDER BY d.day DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def get_creative_sessions(day: str | None = None) -> list[dict[str, Any]]:
    day = day or get_today_day()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT day, start_at, end_at, duration_seconds, goal_id, goal_name, created_at
            FROM creative_sessions
            WHERE day = ?
            ORDER BY id DESC
            """,
            (day,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_game_events(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT day, detected_at, process_names, creative_remaining_seconds, action_taken
            FROM game_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
