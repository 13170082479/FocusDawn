from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

from config import (
    AUTO_KILL_GRACE_SECONDS,
    DEFAULT_ALERT_COOLDOWN_SECONDS,
    DEFAULT_AUTO_KILL_ENABLED,
    DEFAULT_BLACKLIST,
    DEFAULT_DAILY_GOAL_MINUTES,
    PROCESS_SCAN_INTERVAL_SECONDS,
    UNCATEGORIZED_GOAL_ID,
    UNCATEGORIZED_GOAL_NAME,
)
from storage import (
    add_creative_session,
    add_game_seconds,
    add_pc_seconds,
    ensure_daily_record,
    get_daily_summary,
    get_setting,
    get_today_day,
    record_game_event,
    set_setting,
    touch_first_start,
)


def _parse_blacklist(raw: str | None) -> list[str]:
    if not raw:
        return []
    names = []
    for line in raw.replace(",", "\n").splitlines():
        item = line.strip().lower()
        if item:
            names.append(item)
    return names


def _setting_bool(key: str, default: bool) -> bool:
    value = get_setting(key, "1" if default else "0")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class TrackerSnapshot:
    day: str
    first_start_at: str | None
    total_pc_seconds: int
    creative_seconds: int
    game_seconds: int
    target_minutes: int
    creative_active: bool
    creative_session_seconds: int
    active_goal_id: str | None
    active_goal_name: str | None
    blacklist: list[str]
    remaining_creative_seconds: int


class AppTracker:
    def __init__(self, on_game_detected: Callable[[list[str], int], None] | None = None) -> None:
        self.on_game_detected = on_game_detected
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._current_day = get_today_day()
        self._last_tick = time.monotonic()
        self._last_game_tick = time.monotonic()
        self._creative_active = False
        self._creative_started_at: datetime | None = None
        self._creative_session_seconds = 0
        self._active_goal_id: str | None = None
        self._active_goal_name: str | None = None
        self._last_alert_at = 0.0
        self._pending_auto_kill_since: float | None = None
        self._pending_process_names: list[str] = []
        self._pending_remaining_seconds = 0

    def start(self) -> None:
        ensure_daily_record(self._current_day, int(get_setting("daily_goal_minutes", str(DEFAULT_DAILY_GOAL_MINUTES)) or DEFAULT_DAILY_GOAL_MINUTES))
        touch_first_start(self._current_day)
        self._thread = threading.Thread(target=self._run, name="makedawn-tracker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.stop_creative()

    def start_creative(self, goal_id: str | None = None, goal_name: str | None = None) -> bool:
        with self._lock:
            if self._creative_active:
                return False
            self._creative_active = True
            self._creative_started_at = datetime.now()
            self._creative_session_seconds = 0
            self._active_goal_id = goal_id or UNCATEGORIZED_GOAL_ID
            self._active_goal_name = goal_name or UNCATEGORIZED_GOAL_NAME
            return True

    def stop_creative(self) -> int:
        with self._lock:
            if not self._creative_active or self._creative_started_at is None:
                return 0
            end_at = datetime.now()
            start_at = self._creative_started_at
            duration = max(1, int((end_at - start_at).total_seconds()))
            add_creative_session(
                self._current_day,
                start_at.isoformat(timespec="seconds"),
                end_at.isoformat(timespec="seconds"),
                duration,
                self._active_goal_id,
                self._active_goal_name,
            )
            self._creative_active = False
            self._creative_started_at = None
            self._creative_session_seconds = 0
            self._active_goal_id = None
            self._active_goal_name = None
            return duration

    def pause_creative(self) -> int:
        return self.stop_creative()

    def set_goal_minutes(self, minutes: int) -> None:
        set_setting("daily_goal_minutes", str(max(1, minutes)))
        ensure_daily_record(self._current_day, minutes)

    def set_blacklist(self, items: list[str]) -> None:
        cleaned = [item.strip().lower() for item in items if item.strip()]
        set_setting("game_process_blacklist", "\n".join(cleaned))

    def set_auto_kill_enabled(self, enabled: bool) -> None:
        set_setting("auto_kill_enabled", "1" if enabled else "0")

    def clear_pending_game_alert(self) -> None:
        self._pending_auto_kill_since = None
        self._pending_process_names = []
        self._pending_remaining_seconds = 0

    def force_close_blacklisted_processes(self) -> list[str]:
        if psutil is None:
            return []
        blacklist = _parse_blacklist(get_setting("game_process_blacklist", "\n".join(DEFAULT_BLACKLIST)))
        closed = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name in blacklist:
                    targets = []
                    try:
                        targets.extend(proc.children(recursive=True))
                    except Exception:
                        pass
                    targets.append(proc)
                    for target in targets:
                        try:
                            if target.is_running():
                                target.terminate()
                        except Exception:
                            pass
                    _, alive = psutil.wait_procs(targets, timeout=2)
                    for target in alive:
                        try:
                            target.kill()
                        except Exception:
                            pass
                    closed.append(proc.info.get("name") or name)
            except Exception:
                continue
        return closed

    def get_snapshot(self) -> TrackerSnapshot:
        summary = get_daily_summary(self._current_day) or {}
        target_minutes = int(summary.get("target_minutes") or get_setting("daily_goal_minutes", str(DEFAULT_DAILY_GOAL_MINUTES)) or DEFAULT_DAILY_GOAL_MINUTES)
        creative_seconds = int(summary.get("creative_seconds") or 0)
        game_seconds = int(summary.get("game_seconds") or 0)
        live_session_seconds = self._creative_session_seconds
        with self._lock:
            if self._creative_active and self._creative_started_at is not None:
                live_session_seconds = max(
                    live_session_seconds,
                    int((datetime.now() - self._creative_started_at).total_seconds()),
                )
        return TrackerSnapshot(
            day=self._current_day,
            first_start_at=summary.get("first_start_at"),
            total_pc_seconds=int(summary.get("total_pc_seconds") or 0),
            creative_seconds=creative_seconds,
            game_seconds=game_seconds,
            target_minutes=target_minutes,
            creative_active=self._creative_active,
            creative_session_seconds=live_session_seconds,
            active_goal_id=self._active_goal_id,
            active_goal_name=self._active_goal_name,
            blacklist=_parse_blacklist(get_setting("game_process_blacklist", "\n".join(DEFAULT_BLACKLIST))),
            remaining_creative_seconds=max(0, target_minutes * 60 - creative_seconds - live_session_seconds),
        )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            now = time.monotonic()
            elapsed = max(1, int(now - self._last_tick))
            self._last_tick = now

            current_day = get_today_day()
            if current_day != self._current_day:
                self.stop_creative()
                self._current_day = current_day
                self._last_game_tick = time.monotonic()
                ensure_daily_record(self._current_day)
                touch_first_start(self._current_day)

            add_pc_seconds(self._current_day, elapsed)

            with self._lock:
                if self._creative_active and self._creative_started_at is not None:
                    self._creative_session_seconds = max(
                        0,
                        int((datetime.now() - self._creative_started_at).total_seconds()),
                    )

            self._check_games()
            self._stop_event.wait(PROCESS_SCAN_INTERVAL_SECONDS)

    def _check_games(self) -> None:
        if psutil is None:
            return

        blacklist = _parse_blacklist(get_setting("game_process_blacklist", "\n".join(DEFAULT_BLACKLIST)))
        if not blacklist:
            return

        found = []
        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info.get("name") or "").strip().lower()
                if name in blacklist:
                    found.append(proc.info.get("name") or name)
            except Exception:
                continue

        if not found:
            if self._pending_auto_kill_since is not None and self._pending_process_names:
                record_game_event(
                    self._current_day,
                    self._pending_process_names,
                    self._pending_remaining_seconds,
                    "用户已手动关闭",
                )
            self._last_game_tick = time.monotonic()
            self._pending_auto_kill_since = None
            self._pending_process_names = []
            self._pending_remaining_seconds = 0
            return

        snapshot = self.get_snapshot()
        if snapshot.remaining_creative_seconds <= 0:
            self._last_game_tick = time.monotonic()
            self._pending_auto_kill_since = None
            self._pending_process_names = []
            self._pending_remaining_seconds = 0
            return

        game_elapsed = max(1, int(time.monotonic() - self._last_game_tick))
        self._last_game_tick = time.monotonic()
        add_game_seconds(self._current_day, game_elapsed)

        now = time.monotonic()
        if self._pending_auto_kill_since is None:
            self._pending_auto_kill_since = now
            self._pending_process_names = list(found)
            self._pending_remaining_seconds = snapshot.remaining_creative_seconds

        delayed_auto_kill_enabled = _setting_bool("auto_kill_enabled", DEFAULT_AUTO_KILL_ENABLED)
        if delayed_auto_kill_enabled and now - self._pending_auto_kill_since >= AUTO_KILL_GRACE_SECONDS:
            closed = self.force_close_blacklisted_processes()
            action_taken = f"自动关闭成功：{', '.join(closed)}" if closed else "自动关闭失败"
            record_game_event(
                self._current_day,
                found,
                snapshot.remaining_creative_seconds,
                action_taken,
            )
            if closed:
                self._pending_auto_kill_since = None
                self._pending_process_names = []
                self._pending_remaining_seconds = 0
            return

        cooldown = int(get_setting("alert_cooldown_seconds", str(DEFAULT_ALERT_COOLDOWN_SECONDS)) or DEFAULT_ALERT_COOLDOWN_SECONDS)
        if now - self._last_alert_at < cooldown:
            return
        self._last_alert_at = now

        auto_kill_enabled = False
        action_taken = f"已提醒，{AUTO_KILL_GRACE_SECONDS} 秒后自动关闭"
        if auto_kill_enabled:
            closed = self.force_close_blacklisted_processes()
            if closed:
                action_taken = "自动关闭"

        record_game_event(
            self._current_day,
            found,
            snapshot.remaining_creative_seconds,
            action_taken,
        )
        if self.on_game_detected:
            self.on_game_detected(found, snapshot.remaining_creative_seconds)
