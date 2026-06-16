from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def seconds_to_minutes(seconds: int) -> float:
    return round(seconds / 60.0, 1)


def minutes_to_text(minutes: float) -> str:
    return f"{minutes:.1f} 分钟"


@dataclass
class AnalysisSummary:
    days: int
    total_creative_seconds: int
    total_game_seconds: int
    total_pc_seconds: int
    average_daily_creative_seconds: float
    average_daily_game_seconds: float
    average_daily_pc_seconds: float
    completion_rate: float
    total_sessions: int
    best_day: str | None
    best_day_creative_seconds: int
    consecutive_days: int
    week_completion_rate: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "days": self.days,
            "total_creative_seconds": self.total_creative_seconds,
            "total_game_seconds": self.total_game_seconds,
            "total_pc_seconds": self.total_pc_seconds,
            "average_daily_creative_seconds": self.average_daily_creative_seconds,
            "average_daily_game_seconds": self.average_daily_game_seconds,
            "average_daily_pc_seconds": self.average_daily_pc_seconds,
            "completion_rate": self.completion_rate,
            "total_sessions": self.total_sessions,
            "best_day": self.best_day,
            "best_day_creative_seconds": self.best_day_creative_seconds,
            "consecutive_days": self.consecutive_days,
            "week_completion_rate": self.week_completion_rate,
        }


def build_analysis(rows: list[dict[str, Any]]) -> AnalysisSummary:
    if not rows:
        return AnalysisSummary(0, 0, 0, 0, 0.0, 0.0, 0.0, 0, None, 0, 0, 0.0)

    total_creative_seconds = sum(int(row["creative_seconds"]) for row in rows)
    total_game_seconds = sum(int(row.get("game_seconds", 0)) for row in rows)
    total_pc_seconds = sum(int(row["total_pc_seconds"]) for row in rows)
    days = len(rows)
    average_daily_creative_seconds = total_creative_seconds / days if days else 0.0
    average_daily_game_seconds = total_game_seconds / days if days else 0.0
    average_daily_pc_seconds = total_pc_seconds / days if days else 0.0

    completed = 0
    total_sessions = 0
    best_day = None
    best_seconds = -1
    consecutive_days = 0
    for row in rows:
        creative_seconds = int(row["creative_seconds"])
        target_seconds = int(row["target_minutes"]) * 60
        total_sessions += int(row.get("creative_session_count", 0))
        if creative_seconds >= target_seconds:
            completed += 1
        if creative_seconds > best_seconds:
            best_seconds = creative_seconds
            best_day = str(row["day"])
    for row in rows:
        creative_seconds = int(row["creative_seconds"])
        target_seconds = int(row["target_minutes"]) * 60
        if creative_seconds >= target_seconds:
            consecutive_days += 1
        else:
            break

    completion_rate = completed / days if days else 0.0
    week_rows = rows[:7]
    week_completed = 0
    for row in week_rows:
        if int(row["creative_seconds"]) >= int(row["target_minutes"]) * 60:
            week_completed += 1
    week_completion_rate = week_completed / len(week_rows) if week_rows else 0.0

    return AnalysisSummary(
        days=days,
        total_creative_seconds=total_creative_seconds,
        total_game_seconds=total_game_seconds,
        total_pc_seconds=total_pc_seconds,
        average_daily_creative_seconds=average_daily_creative_seconds,
        average_daily_game_seconds=average_daily_game_seconds,
        average_daily_pc_seconds=average_daily_pc_seconds,
        completion_rate=completion_rate,
        total_sessions=total_sessions,
        best_day=best_day,
        best_day_creative_seconds=max(best_seconds, 0),
        consecutive_days=consecutive_days,
        week_completion_rate=week_completion_rate,
    )
