from __future__ import annotations

import math
import sys
import time
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk
import pystray

from analyzer import build_analysis, seconds_to_minutes
from config import AUTO_KILL_GRACE_SECONDS, DEFAULT_DAILY_GOAL_MINUTES
from design_tokens import BUTTON_HEIGHT, COLORS, FONT_FAMILY, RADIUS, SPACE
from storage import (
    create_goal,
    get_creative_sessions,
    get_game_events,
    get_goal_time_stats,
    get_goals,
    get_last_goal,
    get_recent_summaries,
    get_recent_goals,
    get_setting,
    get_week_start,
    get_weekly_goal_progress,
    get_weekly_goals,
    init_db,
    record_game_event,
    set_weekly_goal,
    set_setting,
)
from startup import disable_startup, enable_startup, is_startup_enabled
from tracker import AppTracker

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ASSET_DIR = BASE_DIR / "assets" / "ui"
WEEKLY_TARGET_OPTIONS = ["30 分钟", "1 小时", "3 小时", "5 小时", "10 小时", "自定义"]
WEEKLY_TARGET_MINUTES = {
    "30 分钟": 30,
    "1 小时": 60,
    "3 小时": 180,
    "5 小时": 300,
    "10 小时": 600,
}
GOAL_ICON_OPTIONS = ["PenLine", "Newspaper", "BookOpen", "Sparkles", "Library", "Video", "Code", "Target"]
GOAL_COLOR_OPTIONS = {
    "晨蓝": "#4D8EFF",
    "森林绿": "#22C55E",
    "暮紫": "#A855F7",
    "日出橙": "#F97316",
    "麦穗黄": "#EAB308",
    "珊瑚红": "#EF4444",
}


def _fmt_seconds(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes = seconds // 60
    remainder = seconds % 60
    if minutes >= 60:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours} 小时 {mins:02d} 分"
    return f"{minutes} 分 {remainder:02d} 秒"


def _fmt_minutes(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes = seconds // 60
    if minutes >= 60:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours} 小时 {mins} 分"
    return f"{minutes} 分钟"


def _fmt_goal_minutes(minutes: int) -> str:
    minutes = max(0, int(minutes))
    if minutes >= 60:
        hours = minutes // 60
        remainder = minutes % 60
        return f"{hours}h {remainder}m" if remainder else f"{hours}h"
    return f"{minutes}m"


def _weekly_option_from_minutes(minutes: int) -> str:
    for label, value in WEEKLY_TARGET_MINUTES.items():
        if int(minutes) == value:
            return label
    return "自定义"


def _minutes_from_weekly_option(option: str, custom_hours: str) -> int:
    if option in WEEKLY_TARGET_MINUTES:
        return WEEKLY_TARGET_MINUTES[option]
    raw = custom_hours.strip()
    if not raw:
        return 0
    return max(0, int(float(raw) * 60))


class ProgressRing(tk.Canvas):
    def __init__(self, master, size: int = 210, **kwargs) -> None:
        super().__init__(
            master,
            width=size,
            height=size,
            bg=COLORS["card"],
            highlightthickness=0,
            **kwargs,
        )
        self.size = size
        self.progress = 0.0
        self.value_text = "0"
        self.sub_text = "/ 60 分钟"

    def set_progress(self, progress: float, value_text: str, sub_text: str) -> None:
        self.progress = max(0.0, min(1.0, progress))
        self.value_text = value_text
        self.sub_text = sub_text
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        pad = 18
        width = 16
        box = (pad, pad, self.size - pad, self.size - pad)
        self.create_oval(box, outline="#263550", width=width)
        extent = -359.9 * self.progress
        self.create_arc(box, start=90, extent=extent, outline=COLORS["brand"], width=width, style="arc")
        if self.progress > 0:
            self.create_arc(box, start=90 + extent * 0.5, extent=extent * 0.35, outline=COLORS["brand_light"], width=width, style="arc")
        self.create_text(
            self.size // 2,
            self.size // 2 - 10,
            text=self.value_text,
            fill=COLORS["text"],
            font=(FONT_FAMILY, 40, "bold"),
        )
        self.create_text(
            self.size // 2,
            self.size // 2 + 36,
            text=self.sub_text,
            fill=COLORS["text_soft"],
            font=(FONT_FAMILY, 15),
        )


class HeroProgressCard(tk.Canvas):
    def __init__(self, master, image_path: Path, **kwargs) -> None:
        super().__init__(
            master,
            height=238,
            bg=COLORS["card"],
            highlightthickness=0,
            **kwargs,
        )
        self.progress = 0.0
        self.current_minutes = 0
        self.target_minutes = DEFAULT_DAILY_GOAL_MINUTES
        self.remaining_minutes = DEFAULT_DAILY_GOAL_MINUTES
        self._raw_bg = Image.open(image_path).convert("RGBA")
        self._bg_photo: ImageTk.PhotoImage | None = None
        self.bind("<Configure>", lambda _event: self._draw())

    def set_metrics(
        self,
        progress: float,
        current_minutes: int,
        target_minutes: int,
        remaining_minutes: int,
    ) -> None:
        self.progress = max(0.0, min(1.0, progress))
        self.current_minutes = max(0, int(current_minutes))
        self.target_minutes = max(1, int(target_minutes))
        self.remaining_minutes = max(0, int(remaining_minutes))
        self._draw()

    def _rounded_rect(self, x0: float, y0: float, x1: float, y1: float, radius: float, **kwargs) -> None:
        self.create_rectangle(x0 + radius, y0, x1 - radius, y1, **kwargs)
        self.create_rectangle(x0, y0 + radius, x1, y1 - radius, **kwargs)
        self.create_oval(x0, y0, x0 + radius * 2, y0 + radius * 2, **kwargs)
        self.create_oval(x1 - radius * 2, y0, x1, y0 + radius * 2, **kwargs)
        self.create_oval(x0, y1 - radius * 2, x0 + radius * 2, y1, **kwargs)
        self.create_oval(x1 - radius * 2, y1 - radius * 2, x1, y1, **kwargs)

    def _draw(self) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.delete("all")

        bg = self._raw_bg.resize((width, height), Image.Resampling.LANCZOS)
        shade = Image.new("RGBA", (width, height), (7, 18, 38, 92))
        bg = Image.alpha_composite(bg, shade)
        border = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(border)
        draw.rounded_rectangle(
            (1, 1, width - 2, height - 2),
            radius=12,
            outline=(43, 61, 97, 210),
            width=1,
        )
        bg = Image.alpha_composite(bg, border)
        self._bg_photo = ImageTk.PhotoImage(bg)
        self.create_image(0, 0, image=self._bg_photo, anchor="nw")

        self.create_text(
            24,
            30,
            text="今日创作进度",
            fill=COLORS["text"],
            font=(FONT_FAMILY, 18, "bold"),
            anchor="w",
        )

        ring_size = 168
        ring_x = 46
        ring_y = 58
        box = (ring_x, ring_y, ring_x + ring_size, ring_y + ring_size)
        self.create_oval(box, outline="#263A60", width=15)
        extent = -359.9 * self.progress
        self.create_arc(box, start=90, extent=extent, outline=COLORS["brand"], width=15, style="arc")
        if self.progress > 0:
            self.create_arc(box, start=90 + extent, extent=-8, outline=COLORS["brand_light"], width=15, style="arc")

        center_x = ring_x + ring_size / 2
        center_y = ring_y + ring_size / 2
        self.create_text(
            center_x,
            center_y - 18,
            text=str(self.current_minutes),
            fill=COLORS["text"],
            font=(FONT_FAMILY, 44, "bold"),
        )
        self.create_text(
            center_x,
            center_y + 34,
            text=f"/ {self.target_minutes} 分钟",
            fill=COLORS["text"],
            font=(FONT_FAMILY, 18),
        )

        text_x = 300
        text_y = 88
        self.create_text(
            text_x,
            text_y,
            text=f"{self.current_minutes} / {self.target_minutes} 分钟",
            fill=COLORS["text"],
            font=(FONT_FAMILY, 36, "bold"),
            anchor="w",
        )
        self.create_text(
            text_x,
            text_y + 52,
            text=f"还需 {self.remaining_minutes} 分钟即可解锁娱乐",
            fill=COLORS["text_secondary"],
            font=(FONT_FAMILY, 15),
            anchor="w",
        )

        bar_x = text_x
        bar_y = text_y + 82
        bar_w = max(120, width - text_x - 34)
        bar_h = 24
        self._rounded_rect(bar_x, bar_y, bar_x + bar_w, bar_y + bar_h, 12, fill="#31405D", outline="")
        fill_w = max(bar_h, bar_w * self.progress) if self.progress > 0 else 0
        if fill_w:
            self._rounded_rect(bar_x, bar_y, bar_x + fill_w, bar_y + bar_h, 12, fill=COLORS["brand"], outline="")
        self.create_text(
            bar_x + 14,
            bar_y + bar_h / 2,
            text=f"{self.progress * 100:.0f}%",
            fill=COLORS["text"],
            font=(FONT_FAMILY, 12, "bold"),
            anchor="w",
        )
        self.create_text(
            text_x,
            bar_y + 50,
            text=f"目标 {self.target_minutes} 分钟  |  已完成 {self.current_minutes} 分钟",
            fill=COLORS["text_secondary"],
            font=(FONT_FAMILY, 13),
            anchor="w",
        )


class TrendChart(tk.Canvas):
    def __init__(self, master, height: int = 280, **kwargs) -> None:
        super().__init__(master, height=height, bg=COLORS["card"], highlightthickness=0, **kwargs)
        self.rows: list[dict[str, object]] = []
        self.mode = "creative"

    def set_data(self, rows: list[dict[str, object]], mode: str = "creative") -> None:
        self.rows = rows
        self.mode = mode
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        left = 52
        right = 24
        top = 22
        bottom = 46
        plot_w = max(1, width - left - right)
        plot_h = max(1, height - top - bottom)
        base_y = height - bottom

        rows = list(reversed(self.rows))
        if not rows:
            self.create_text(
                width // 2,
                height // 2,
                text="开始记录后，这里会出现趋势图",
                fill=COLORS["text_muted"],
                font=(FONT_FAMILY, 13),
            )
            return

        values = []
        for row in rows:
            key = "game_seconds" if self.mode == "game" else "creative_seconds"
            values.append(int(row.get(key) or 0))
        target = max([int(row.get("target_minutes") or 0) * 60 for row in rows] + [60])
        max_value = max(values + [target, 60])

        for index in range(5):
            y = base_y - plot_h * index / 4
            value = int(max_value * index / 4)
            self.create_line(left, y, width - right, y, fill="#25344D", width=1)
            self.create_text(14, y, text=f"{value // 60}m", fill=COLORS["text_muted"], font=(FONT_FAMILY, 10), anchor="w")

        if self.mode == "creative" and target > 0:
            target_y = base_y - target / max_value * plot_h
            self.create_line(left, target_y, width - right, target_y, fill=COLORS["text_muted"], width=1, dash=(5, 5))

        slot = plot_w / len(rows)
        bar_w = min(42, max(12, slot * 0.42))
        color = COLORS["warning"] if self.mode == "game" else COLORS["brand"]
        for idx, row in enumerate(rows):
            value = values[idx]
            x = left + slot * (idx + 0.5)
            h = max(3, value / max_value * plot_h)
            y0 = base_y - h
            fill = COLORS["success"] if self.mode == "creative" and value >= int(row.get("target_minutes") or 0) * 60 else color
            self.create_rectangle(x - bar_w / 2, y0, x + bar_w / 2, base_y, fill=fill, outline=fill)
            day = str(row.get("day") or "")
            label = day[5:].replace("-", "/") if len(day) >= 10 else day
            self.create_text(x, base_y + 18, text=label, fill=COLORS["text_secondary"], font=(FONT_FAMILY, 10))


class FocusDawnApp(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()
        init_db()

        self.title("FocusDawn - 创作守护")
        self.geometry("1366x768")
        self.minsize(1180, 720)
        self.configure(fg_color=COLORS["bg"])
        try:
            self._window_icon = tk.PhotoImage(file=str(ASSET_DIR / "app_icon.png"))
            self.iconphoto(True, self._window_icon)
            if sys.platform == "win32":
                self.iconbitmap(str(ASSET_DIR / "app_icon.ico"))
        except Exception:
            self._window_icon = None

        self.tracker = AppTracker(on_game_detected=self._handle_game_detected)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.goal_var = tk.StringVar()
        self.auto_kill_var = tk.BooleanVar()
        self.startup_var = tk.BooleanVar()
        self.sound_var = tk.BooleanVar(value=True)
        self.mode_var = tk.StringVar(value="娱乐锁定中")
        self.notice_var = tk.StringVar(value="先完成创作目标，再开始娱乐")
        self.hero_goal_var = tk.StringVar(value="0 / 60 分钟")
        self.hero_remaining_var = tk.StringVar(value="还需 60 分钟即可解锁娱乐")
        self.hero_status_var = tk.StringVar(value="娱乐锁定")
        self.hero_streak_var = tk.StringVar(value="0 天")
        self.hero_week_rate_var = tk.StringVar(value="0%")
        self.hero_game_var = tk.StringVar(value="0 分钟")
        self.today_status = tk.StringVar(value="先完成创作目标，再开始娱乐。")
        self.analysis_scope_var = tk.StringVar(value="7 天")
        self.runtime_var = tk.StringVar(value="已运行：00:00:00")

        self._tray_icon: pystray.Icon | None = None
        self._tray_thread: threading.Thread | None = None
        self._closing = False
        self._hidden_to_tray = False
        self._fast_refresh_after_id: str | None = None
        self._slow_refresh_after_id: str | None = None
        self._celebrated_day: str | None = None
        self._analysis_rows_cache: list[dict[str, object]] = []
        self._game_dialog: ctk.CTkToplevel | None = None
        self._game_dialog_after_id: str | None = None
        self.weekly_goal_entries: dict[str, tk.StringVar] = {}
        self.weekly_goal_option_vars: dict[str, tk.StringVar] = {}
        self.weekly_goal_custom_vars: dict[str, tk.StringVar] = {}
        self.new_goal_name_var = tk.StringVar()
        self.new_goal_icon_var = tk.StringVar(value="PenLine")
        self.new_goal_color_var = tk.StringVar(value="晨蓝")
        self.new_goal_target_var = tk.StringVar(value="1 小时")
        self.new_goal_custom_hours_var = tk.StringVar()
        self._started_at = time.monotonic()
        self.current_page = "today"
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.ui_images: dict[tuple[str, tuple[int, int]], ctk.CTkImage] = {}

        self._build_ui()
        self._load_settings()
        self.tracker.start()
        self._start_tray()
        self._refresh_now()
        self._schedule_fast_refresh()
        self._schedule_slow_refresh()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        header = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=SPACE["page"], pady=(22, 10))
        header.grid_columnconfigure(0, weight=1)

        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            brand,
            text="FocusDawn ✦",
            font=(FONT_FAMILY, 28, "bold"),
            text_color=COLORS["text"],
            fg_color="transparent",
        ).pack(anchor="w")
        ctk.CTkLabel(brand, text="先创作，后娱乐", font=(FONT_FAMILY, 13), text_color=COLORS["text_secondary"]).pack(anchor="w", pady=(4, 0))

        self.top_status = ctk.CTkFrame(header, fg_color=COLORS["card"], corner_radius=10)
        self.top_status.grid(row=0, column=1, sticky="e")
        self.top_status_title = ctk.CTkLabel(
            self.top_status,
            textvariable=self.mode_var,
            image=self._image("icon_lock_orange.png", (18, 18)),
            compound="left",
            font=(FONT_FAMILY, 13, "bold"),
            text_color=COLORS["warning"],
        )
        self.top_status_title.pack(anchor="e", padx=16, pady=(10, 0))
        ctk.CTkLabel(self.top_status, textvariable=self.notice_var, font=(FONT_FAMILY, 12), text_color=COLORS["text_secondary"]).pack(anchor="e", padx=16, pady=(2, 10))

        self.main = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        self.main.grid(row=1, column=0, sticky="nsew", padx=SPACE["page"], pady=(0, 8))
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)

        nav = ctk.CTkFrame(self.main, fg_color=COLORS["bg_secondary"], corner_radius=12)
        nav.grid(row=0, column=0, sticky="w", pady=(0, 14))
        nav_items = (
            ("today", "今日", "icon_home.png"),
            ("analysis", "数据分析", "icon_analytics.png"),
            ("goals", "目标", "icon_target.png"),
            ("settings", "设置", "icon_settings.png"),
            ("logs", "日志", "icon_log.png"),
        )
        for key, label, icon in nav_items:
            btn = ctk.CTkButton(
                nav,
                text=label,
                image=self._image(icon, (20, 20)),
                compound="left",
                height=40,
                width=116,
                corner_radius=10,
                border_width=0,
                font=(FONT_FAMILY, 13, "bold"),
                command=lambda page=key: self._show_page(page),
            )
            btn.pack(side="left", padx=4, pady=4)
            self.nav_buttons[key] = btn

        self.page_host = ctk.CTkFrame(self.main, fg_color="transparent")
        self.page_host.grid(row=1, column=0, sticky="nsew")
        self.page_host.grid_columnconfigure(0, weight=1)
        self.page_host.grid_rowconfigure(0, weight=1)

        self.pages: dict[str, ctk.CTkScrollableFrame] = {}
        for key in ("today", "analysis", "goals", "settings", "logs"):
            frame = ctk.CTkScrollableFrame(
                self.page_host,
                fg_color="transparent",
                corner_radius=0,
                scrollbar_button_color=COLORS["border"],
                scrollbar_button_hover_color=COLORS["brand"],
            )
            frame.grid_columnconfigure(0, weight=1)
            self.pages[key] = frame

        self._build_today_page(self.pages["today"])
        self._build_analysis_page(self.pages["analysis"])
        self._build_goals_page(self.pages["goals"])
        self._build_settings_page(self.pages["settings"])
        self._build_logs_page(self.pages["logs"])
        self._show_page("today")
        self._build_bottom_status_bar()

    def _card(self, parent, **kwargs) -> ctk.CTkFrame:
        return ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=RADIUS["card"], border_width=1, border_color="#243247", **kwargs)

    def _image(self, filename: str, size: tuple[int, int]) -> ctk.CTkImage:
        key = (filename, size)
        if key not in self.ui_images:
            image = Image.open(ASSET_DIR / filename).convert("RGBA")
            self.ui_images[key] = ctk.CTkImage(light_image=image, dark_image=image, size=size)
        return self.ui_images[key]

    def _build_bottom_status_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0, height=34)
        bar.grid(row=2, column=0, sticky="ew", padx=SPACE["page"], pady=(0, 8))
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            bar,
            text="守护中 ●",
            font=(FONT_FAMILY, 12, "bold"),
            text_color=COLORS["success"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            bar,
            textvariable=self.runtime_var,
            font=(FONT_FAMILY, 12),
            text_color=COLORS["text_secondary"],
        ).grid(row=0, column=1, sticky="w", padx=22)
        ctk.CTkSwitch(
            bar,
            text="提示音",
            variable=self.sound_var,
            progress_color=COLORS["brand"],
            button_color=COLORS["text_soft"],
            button_hover_color=COLORS["text"],
            font=(FONT_FAMILY, 12),
            text_color=COLORS["text_secondary"],
        ).grid(row=0, column=2, sticky="e", padx=(0, 18))
        ctk.CTkLabel(
            bar,
            text="版本：v1.2.0",
            font=(FONT_FAMILY, 12),
            text_color=COLORS["text_muted"],
        ).grid(row=0, column=3, sticky="e")

    def _show_page(self, key: str) -> None:
        self.current_page = key
        if key == "goals" and hasattr(self, "weekly_goal_settings_frame"):
            self._render_weekly_goal_settings()
        for page_key, page in self.pages.items():
            if page_key == key:
                page.grid(row=0, column=0, sticky="nsew")
            else:
                page.grid_remove()
        for item, button in self.nav_buttons.items():
            selected = item == key
            button.configure(
                fg_color=COLORS["brand"] if selected else COLORS["bg_secondary"],
                hover_color=COLORS["brand_hover"] if selected else COLORS["card"],
                text_color=COLORS["text"] if selected else COLORS["text_secondary"],
                border_width=1 if selected else 0,
                border_color=COLORS["brand_light"] if selected else COLORS["bg_secondary"],
            )

    def _build_today_page(self, page: ctk.CTkScrollableFrame) -> None:
        page.grid_columnconfigure(0, weight=64, uniform="dashboard")
        page.grid_columnconfigure(1, weight=36, uniform="dashboard")
        page.grid_rowconfigure(0, weight=0)
        page.grid_rowconfigure(1, weight=0)
        page.grid_rowconfigure(2, weight=1)

        hero = self._card(page)
        hero.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=(0, 16))
        hero.configure(height=238)
        hero.grid_propagate(False)
        hero.grid_columnconfigure(0, weight=1)
        hero.grid_rowconfigure(0, weight=1)
        self.hero_progress_card = HeroProgressCard(hero, ASSET_DIR / "bg_landscape.png")
        self.hero_progress_card.grid(row=0, column=0, sticky="nsew")

        status = self._card(page)
        status.grid(row=0, column=1, sticky="nsew", padx=(12, 0), pady=(0, 16))
        status.configure(height=238)
        status.grid_propagate(False)
        status.grid_columnconfigure(0, weight=0)
        status.grid_columnconfigure(1, weight=1)
        status.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(status, text="当前状态", font=(FONT_FAMILY, 18, "bold"), text_color=COLORS["text"]).grid(row=0, column=0, columnspan=2, sticky="w", padx=24, pady=(20, 8))
        self.status_icon = ctk.CTkLabel(
            status,
            text="",
            image=self._image("icon_lock_orange.png", (82, 82)),
            fg_color="transparent",
        )
        self.status_icon.grid(row=1, column=0, sticky="w", padx=(24, 18), pady=(0, 8))
        status_text = ctk.CTkFrame(status, fg_color="transparent")
        status_text.grid(row=1, column=1, sticky="w", padx=(0, 24), pady=(0, 8))
        self.status_title = ctk.CTkLabel(status_text, textvariable=self.hero_status_var, font=(FONT_FAMILY, 26, "bold"), text_color=COLORS["warning"])
        self.status_title.pack(anchor="w")
        self.status_body = ctk.CTkLabel(status_text, textvariable=self.today_status, font=(FONT_FAMILY, 14), text_color=COLORS["text_secondary"])
        self.status_body.pack(anchor="w", pady=(6, 0))
        tip = ctk.CTkFrame(status, fg_color=COLORS["bg_secondary"], corner_radius=10)
        tip.grid(row=2, column=0, columnspan=2, sticky="ew", padx=24, pady=(6, 18))
        ctk.CTkLabel(
            tip,
            text="小贴士  专注当下的 60 分钟，未来的你会感谢现在的自己。",
            image=self._image("icon_tip.png", (22, 22)),
            compound="left",
            font=(FONT_FAMILY, 13),
            text_color=COLORS["text_secondary"],
            wraplength=360,
        ).pack(anchor="w", padx=16, pady=12)

        metrics = ctk.CTkFrame(page, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="nsew", padx=(0, 12), pady=(0, 16))
        metrics.grid_columnconfigure((0, 1, 2), weight=1)
        self._metric_card(metrics, 0, "icon_calendar.png", "连续达标天数", self.hero_streak_var, "继续努力，养成创作习惯")
        self._metric_card(metrics, 1, "icon_target.png", "本周达标率", self.hero_week_rate_var, "本周目标完成情况")
        self._metric_card(metrics, 2, "icon_game_orange.png", "今日娱乐时长", self.hero_game_var, "娱乐有度，生活更精彩")

        self._build_action_panel(page, row=1, column=1)

        self._build_records_card(page, row=2, column=0)
        self._build_weekly_chart_card(page, row=2, column=1)
        self._build_weekly_goals_card(page, row=3, column=0)

    def _metric_card(self, parent, column: int, icon: str, title: str, variable: tk.StringVar, caption: str) -> None:
        card = self._card(parent)
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 12, 0))
        card.configure(height=104)
        card.grid_propagate(False)
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            card,
            text="",
            image=self._image(icon, (58, 58)),
            fg_color="transparent",
        ).grid(row=0, column=0, rowspan=3, sticky="w", padx=(14, 14), pady=20)
        ctk.CTkLabel(card, text=title, font=(FONT_FAMILY, 12), text_color=COLORS["text_secondary"]).grid(row=0, column=1, sticky="sw", padx=(0, 12), pady=(14, 0))
        ctk.CTkLabel(card, textvariable=variable, font=(FONT_FAMILY, 20, "bold"), text_color=COLORS["text"]).grid(row=1, column=1, sticky="w", padx=(0, 12))
        ctk.CTkLabel(card, text=caption, font=(FONT_FAMILY, 11), text_color=COLORS["text_muted"]).grid(row=2, column=1, sticky="nw", padx=(0, 12), pady=(0, 14))

    def _build_action_panel(self, parent, row: int, column: int) -> None:
        panel = ctk.CTkFrame(parent, fg_color="transparent")
        panel.grid(row=row, column=column, sticky="nsew", padx=(12, 0), pady=(0, 16))
        panel.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(
            panel,
            text="▶  开始创作",
            image=self._image("icon_play.png", (22, 22)),
            compound="left",
            height=46,
            corner_radius=RADIUS["button"],
            fg_color=COLORS["brand"],
            hover_color=COLORS["brand_hover"],
            font=(FONT_FAMILY, 14, "bold"),
            command=self._start_creative,
        ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        for col, text, command in (
            (0, "暂停", self._pause_creative),
            (1, "结束", self._stop_creative),
            (2, "刷新", self._refresh_now),
        ):
            icon = ("icon_pause.png", "icon_stop.png", "icon_refresh.png")[col]
            ctk.CTkButton(
                panel,
                text=text,
                image=self._image(icon, (20, 20)),
                compound="left",
                height=46,
                corner_radius=RADIUS["button"],
                fg_color="transparent",
                hover_color=COLORS["card"],
                border_width=1,
                border_color=COLORS["border"],
                text_color=COLORS["text_soft"],
                command=command,
            ).grid(row=1, column=col, sticky="ew", padx=(0 if col == 0 else 10, 0))

    def _build_records_card(self, parent, row: int, column: int) -> None:
        record = self._card(parent)
        record.grid(row=row, column=column, sticky="nsew", padx=(0, 12), pady=(0, 12))
        record.configure(height=226)
        record.grid_propagate(False)
        ctk.CTkLabel(record, text="今日创作记录", font=(FONT_FAMILY, 18, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=18, pady=(18, 10))
        self.sessions_table = ctk.CTkFrame(record, fg_color="transparent")
        self.sessions_table.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        ctk.CTkButton(
            record,
            text="查看更多记录  →",
            height=28,
            width=140,
            fg_color="transparent",
            hover_color=COLORS["bg_secondary"],
            text_color=COLORS["brand_light"],
            command=lambda: self._show_page("logs"),
        ).pack(anchor="center", pady=(0, 10))

    def _build_weekly_chart_card(self, parent, row: int, column: int) -> None:
        chart_card = self._card(parent)
        chart_card.grid(row=row, column=column, sticky="nsew", padx=(12, 0), pady=(0, 12))
        chart_card.configure(height=226)
        chart_card.grid_propagate(False)
        header = ctk.CTkFrame(chart_card, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(18, 0))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="本周创作概览", font=(FONT_FAMILY, 18, "bold"), text_color=COLORS["text"]).grid(row=0, column=0, sticky="w")
        ctk.CTkOptionMenu(
            header,
            values=["7 天", "30 天"],
            width=86,
            height=30,
            fg_color=COLORS["bg_secondary"],
            button_color=COLORS["border"],
            button_hover_color=COLORS["brand"],
            text_color=COLORS["text_soft"],
            command=lambda value: self._refresh_analysis_panel(),
        ).grid(row=0, column=1, sticky="e")
        self.week_chart = TrendChart(chart_card, height=170)
        self.week_chart.pack(fill="both", expand=True, padx=16, pady=(8, 12))

    def _build_weekly_goals_card(self, parent, row: int, column: int) -> None:
        card = self._card(parent)
        card.grid(row=row, column=column, columnspan=2, sticky="ew", pady=(0, 12))
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(18, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="本周计划", font=(FONT_FAMILY, 18, "bold"), text_color=COLORS["text"]).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            header,
            text="查看全部",
            width=92,
            height=30,
            fg_color="transparent",
            hover_color=COLORS["bg_secondary"],
            text_color=COLORS["brand_light"],
            command=lambda: self._show_page("analysis"),
        ).grid(row=0, column=1, sticky="e")
        self.weekly_goal_progress_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.weekly_goal_progress_frame.pack(fill="x", padx=18, pady=(0, 18))

    def _build_analysis_page(self, page: ctk.CTkScrollableFrame) -> None:
        page.grid_columnconfigure(0, weight=1)
        page.grid_columnconfigure(1, weight=1)
        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, SPACE["card"]))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="数据分析", font=(FONT_FAMILY, 26, "bold"), text_color=COLORS["text"]).grid(row=0, column=0, sticky="w")
        self.scope_menu = ctk.CTkOptionMenu(top, values=["7 天", "30 天", "全部"], variable=self.analysis_scope_var, command=lambda _: self._refresh_analysis_panel(), fg_color=COLORS["card"], button_color=COLORS["brand"], button_hover_color=COLORS["brand_hover"])
        self.scope_menu.grid(row=0, column=1, sticky="e")

        self.analysis_summary_row = ctk.CTkFrame(page, fg_color="transparent")
        self.analysis_summary_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, SPACE["card"]))
        self.analysis_summary_row.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.summary_values: dict[str, tk.StringVar] = {
            "days": tk.StringVar(value="0"),
            "creative": tk.StringVar(value="0 分钟"),
            "game": tk.StringVar(value="0 分钟"),
            "rate": tk.StringVar(value="0%"),
        }
        for idx, (icon, title, key) in enumerate((
            ("icon_calendar.png", "统计天数", "days"),
            ("icon_home.png", "创作总时长", "creative"),
            ("icon_game_orange.png", "娱乐总时长", "game"),
            ("icon_target.png", "达标率", "rate"),
        )):
            self._metric_card(self.analysis_summary_row, idx, icon, title, self.summary_values[key], "")

        creative_card = self._card(page)
        creative_card.grid(row=2, column=0, sticky="nsew", padx=(0, 12), pady=(0, SPACE["card"]))
        ctk.CTkLabel(creative_card, text="创作时长趋势", font=(FONT_FAMILY, 18, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=18, pady=(18, 0))
        self.creative_chart = TrendChart(creative_card, height=280)
        self.creative_chart.pack(fill="both", expand=True, padx=16, pady=16)

        game_card = self._card(page)
        game_card.grid(row=2, column=1, sticky="nsew", padx=(12, 0), pady=(0, SPACE["card"]))
        ctk.CTkLabel(game_card, text="娱乐时长趋势", font=(FONT_FAMILY, 18, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=18, pady=(18, 0))
        self.game_chart = TrendChart(game_card, height=280)
        self.game_chart.pack(fill="both", expand=True, padx=16, pady=16)

        heat_card = self._card(page)
        heat_card.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, SPACE["card"]))
        ctk.CTkLabel(heat_card, text="连续达标热力图", font=(FONT_FAMILY, 18, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=18, pady=(18, 0))
        self.heatmap_frame = ctk.CTkFrame(heat_card, fg_color="transparent")
        self.heatmap_frame.pack(fill="x", padx=18, pady=18)

        goal_card = self._card(page)
        goal_card.grid(row=4, column=0, sticky="nsew", padx=(0, 12), pady=(0, SPACE["card"]))
        ctk.CTkLabel(goal_card, text="创作方向排行榜", font=(FONT_FAMILY, 18, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=18, pady=(18, 10))
        self.goal_rank_frame = ctk.CTkFrame(goal_card, fg_color="transparent")
        self.goal_rank_frame.pack(fill="x", padx=14, pady=(0, 16))

        weekly_goal_card = self._card(page)
        weekly_goal_card.grid(row=4, column=1, sticky="nsew", padx=(12, 0), pady=(0, SPACE["card"]))
        ctk.CTkLabel(weekly_goal_card, text="本周目标完成情况", font=(FONT_FAMILY, 18, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=18, pady=(18, 10))
        self.analysis_weekly_goal_frame = ctk.CTkFrame(weekly_goal_card, fg_color="transparent")
        self.analysis_weekly_goal_frame.pack(fill="x", padx=14, pady=(0, 16))

    def _build_settings_page(self, page: ctk.CTkScrollableFrame) -> None:
        page.grid_columnconfigure(0, weight=1)
        panel = self._card(page)
        panel.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["card"]))
        panel.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(panel, text="设置", font=(FONT_FAMILY, 24, "bold"), text_color=COLORS["text"]).grid(row=0, column=0, columnspan=2, sticky="w", padx=24, pady=(24, 18))
        ctk.CTkLabel(panel, text="每日创作目标", text_color=COLORS["text_secondary"]).grid(row=1, column=0, sticky="w", padx=24, pady=10)
        ctk.CTkEntry(panel, textvariable=self.goal_var, height=42, fg_color=COLORS["bg_secondary"], border_color=COLORS["border"]).grid(row=1, column=1, sticky="ew", padx=24, pady=10)
        ctk.CTkLabel(panel, text="游戏进程黑名单", text_color=COLORS["text_secondary"]).grid(row=2, column=0, sticky="nw", padx=24, pady=10)
        self.blacklist_text = ctk.CTkTextbox(panel, height=180, fg_color=COLORS["bg_secondary"], border_color=COLORS["border"], border_width=1)
        self.blacklist_text.grid(row=2, column=1, sticky="ew", padx=24, pady=10)
        ctk.CTkCheckBox(panel, text="启用强制关闭游戏", variable=self.auto_kill_var, fg_color=COLORS["brand"], hover_color=COLORS["brand_hover"]).grid(row=3, column=1, sticky="w", padx=24, pady=10)
        ctk.CTkCheckBox(panel, text="开机自动启动", variable=self.startup_var, fg_color=COLORS["brand"], hover_color=COLORS["brand_hover"]).grid(row=4, column=1, sticky="w", padx=24, pady=10)
        ctk.CTkSwitch(panel, text="目标完成提示音", variable=self.sound_var, progress_color=COLORS["brand"]).grid(row=5, column=1, sticky="w", padx=24, pady=10)
        ctk.CTkButton(panel, text="保存设置", height=BUTTON_HEIGHT, fg_color=COLORS["brand"], hover_color=COLORS["brand_hover"], corner_radius=RADIUS["button"], command=self._save_settings).grid(row=6, column=1, sticky="ew", padx=24, pady=(18, 24))

    def _build_goals_page(self, page: ctk.CTkScrollableFrame) -> None:
        page.grid_columnconfigure(0, weight=1)
        goals_panel = self._card(page)
        goals_panel.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["card"]))
        goals_panel.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(goals_panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="目标管理与本周计划", font=(FONT_FAMILY, 26, "bold"), text_color=COLORS["text"]).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            header,
            text="+ 新建目标",
            width=120,
            height=38,
            fg_color=COLORS["brand"],
            hover_color=COLORS["brand_hover"],
            corner_radius=RADIUS["button"],
            command=self._show_create_goal_dialog,
        ).grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(goals_panel, text=f"本周从 {get_week_start()} 开始。为每个方向设置清晰的投入计划。", font=(FONT_FAMILY, 13), text_color=COLORS["text_secondary"]).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 18))

        self.weekly_goal_settings_frame = ctk.CTkFrame(goals_panel, fg_color="transparent")
        self.weekly_goal_settings_frame.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 14))
        ctk.CTkButton(goals_panel, text="保存本周计划", height=BUTTON_HEIGHT, fg_color=COLORS["brand"], hover_color=COLORS["brand_hover"], corner_radius=RADIUS["button"], command=self._save_weekly_goals).grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 22))

    def _build_logs_page(self, page: ctk.CTkScrollableFrame) -> None:
        page.grid_columnconfigure(0, weight=1)
        game_panel = self._card(page)
        game_panel.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["card"]))
        ctk.CTkLabel(game_panel, text="游戏拦截记录", font=(FONT_FAMILY, 18, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=18, pady=(18, 10))
        self.game_log_list = ctk.CTkFrame(game_panel, fg_color="transparent")
        self.game_log_list.pack(fill="x", padx=14, pady=(0, 16))

        summary_panel = self._card(page)
        summary_panel.grid(row=1, column=0, sticky="ew", pady=(0, SPACE["card"]))
        ctk.CTkLabel(summary_panel, text="最近每日汇总", font=(FONT_FAMILY, 18, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=18, pady=(18, 10))
        self.summary_list = ctk.CTkFrame(summary_panel, fg_color="transparent")
        self.summary_list.pack(fill="x", padx=14, pady=(0, 16))

    def _load_settings(self) -> None:
        goal = get_setting("daily_goal_minutes", str(DEFAULT_DAILY_GOAL_MINUTES)) or str(DEFAULT_DAILY_GOAL_MINUTES)
        blacklist = get_setting("game_process_blacklist", "") or ""
        auto_kill = get_setting("auto_kill_enabled", "0") or "0"
        self.goal_var.set(goal)
        self.blacklist_text.delete("1.0", "end")
        self.blacklist_text.insert("1.0", blacklist.replace(",", "\n"))
        self.auto_kill_var.set(str(auto_kill).strip().lower() in {"1", "true", "yes", "on"})
        self.startup_var.set(is_startup_enabled())
        self._render_weekly_goal_settings()

    def _render_weekly_goal_settings(self) -> None:
        for child in self.weekly_goal_settings_frame.winfo_children():
            child.destroy()
        self.weekly_goal_entries = {}
        self.weekly_goal_option_vars = {}
        self.weekly_goal_custom_vars = {}
        rows = get_weekly_goals()
        if not rows:
            ctk.CTkLabel(self.weekly_goal_settings_frame, text="暂无目标。", text_color=COLORS["text_muted"]).pack(anchor="w")
            return
        progress_by_goal = {str(item["goal_id"]): item for item in get_weekly_goal_progress()}
        for idx, row in enumerate(rows):
            goal_id = str(row["goal_id"])
            target_minutes = int(row.get("target_minutes") or 0)
            progress_item = progress_by_goal.get(goal_id, {})
            completed_minutes = int(progress_item.get("completed_minutes") or 0)
            progress = completed_minutes / target_minutes if target_minutes > 0 else 0
            shown_progress = min(1.0, progress)
            remaining = target_minutes - completed_minutes
            option_var = tk.StringVar(value=_weekly_option_from_minutes(target_minutes))
            custom_value = "" if option_var.get() != "自定义" or target_minutes == 0 else str(round(target_minutes / 60, 1)).rstrip("0").rstrip(".")
            custom_var = tk.StringVar(value=custom_value)
            self.weekly_goal_option_vars[goal_id] = option_var
            self.weekly_goal_custom_vars[goal_id] = custom_var
            self.weekly_goal_entries[goal_id] = custom_var

            card = ctk.CTkFrame(
                self.weekly_goal_settings_frame,
                fg_color=COLORS["card_soft"],
                corner_radius=16,
                border_width=1,
                border_color=COLORS["border"],
            )
            card.pack(fill="x", pady=(0, 12))
            card.grid_columnconfigure(1, weight=1)
            color = str(row.get("color") or COLORS["brand"])
            ctk.CTkLabel(card, text="●", text_color=color, font=(FONT_FAMILY, 26, "bold")).grid(row=0, column=0, rowspan=3, sticky="n", padx=(18, 14), pady=18)
            ctk.CTkLabel(card, text=str(row["goal_name"]), text_color=COLORS["text"], font=(FONT_FAMILY, 18, "bold")).grid(row=0, column=1, sticky="w", pady=(18, 4))
            status_text = "未设置周目标"
            if target_minutes > 0:
                status_text = "已超额完成" if remaining < 0 else f"剩余 {_fmt_goal_minutes(remaining)}"
            ctk.CTkLabel(
                card,
                text=f"已完成 {_fmt_goal_minutes(completed_minutes)} / 周目标 {_fmt_goal_minutes(target_minutes)} · {min(100, int(progress * 100))}%",
                text_color=COLORS["text_secondary"],
                font=(FONT_FAMILY, 13),
            ).grid(row=1, column=1, sticky="w")
            ctk.CTkLabel(
                card,
                text=status_text,
                text_color=COLORS["success"] if remaining < 0 else COLORS["text_muted"],
                font=(FONT_FAMILY, 12),
            ).grid(row=2, column=1, sticky="w", pady=(2, 14))

            control = ctk.CTkFrame(card, fg_color="transparent")
            control.grid(row=0, column=2, rowspan=2, sticky="e", padx=18, pady=(18, 0))
            ctk.CTkOptionMenu(
                control,
                values=WEEKLY_TARGET_OPTIONS,
                variable=option_var,
                width=112,
                height=34,
                fg_color=COLORS["bg_secondary"],
                button_color=COLORS["border"],
                button_hover_color=COLORS["brand"],
            ).grid(row=0, column=0, sticky="e", padx=(0, 8))
            ctk.CTkEntry(
                control,
                textvariable=custom_var,
                width=82,
                height=34,
                placeholder_text="自定义",
                fg_color=COLORS["bg_secondary"],
                border_color=COLORS["border"],
            ).grid(row=0, column=1, sticky="e")
            ctk.CTkLabel(control, text="小时 / 周", text_color=COLORS["text_secondary"], font=(FONT_FAMILY, 12)).grid(row=0, column=2, sticky="e", padx=(8, 0))

            bar = ctk.CTkProgressBar(card, height=10, fg_color=COLORS["bg_secondary"], progress_color=color)
            bar.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(0, 18), pady=(0, 18))
            bar.set(shown_progress)

    def _show_create_goal_dialog(self) -> None:
        self.new_goal_name_var.set("")
        self.new_goal_icon_var.set(GOAL_ICON_OPTIONS[0])
        self.new_goal_color_var.set("晨蓝")
        self.new_goal_target_var.set("1 小时")
        self.new_goal_custom_hours_var.set("")
        dialog = ctk.CTkToplevel(self)
        dialog.title("新建目标")
        dialog.geometry("460x430")
        dialog.attributes("-topmost", True)
        dialog.configure(fg_color=COLORS["bg"])
        ctk.CTkLabel(dialog, text="新建创作目标", font=(FONT_FAMILY, 22, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=24, pady=(24, 6))
        ctk.CTkLabel(dialog, text="选择一个方向，让后续统计更清楚。", font=(FONT_FAMILY, 13), text_color=COLORS["text_secondary"]).pack(anchor="w", padx=24, pady=(0, 18))

        form = ctk.CTkFrame(dialog, fg_color="transparent")
        form.pack(fill="x", padx=24)
        form.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(form, text="目标名称", text_color=COLORS["text_secondary"]).grid(row=0, column=0, sticky="w", pady=8)
        ctk.CTkEntry(form, textvariable=self.new_goal_name_var, placeholder_text="例如：开发 App", height=38, fg_color=COLORS["bg_secondary"], border_color=COLORS["border"]).grid(row=0, column=1, sticky="ew", pady=8)
        ctk.CTkLabel(form, text="图标", text_color=COLORS["text_secondary"]).grid(row=1, column=0, sticky="w", pady=8)
        ctk.CTkOptionMenu(form, values=GOAL_ICON_OPTIONS, variable=self.new_goal_icon_var, height=38, fg_color=COLORS["bg_secondary"], button_color=COLORS["border"], button_hover_color=COLORS["brand"]).grid(row=1, column=1, sticky="ew", pady=8)
        ctk.CTkLabel(form, text="颜色", text_color=COLORS["text_secondary"]).grid(row=2, column=0, sticky="w", pady=8)
        ctk.CTkOptionMenu(form, values=list(GOAL_COLOR_OPTIONS.keys()), variable=self.new_goal_color_var, height=38, fg_color=COLORS["bg_secondary"], button_color=COLORS["border"], button_hover_color=COLORS["brand"]).grid(row=2, column=1, sticky="ew", pady=8)
        ctk.CTkLabel(form, text="每周目标", text_color=COLORS["text_secondary"]).grid(row=3, column=0, sticky="w", pady=8)
        target_row = ctk.CTkFrame(form, fg_color="transparent")
        target_row.grid(row=3, column=1, sticky="ew", pady=8)
        target_row.grid_columnconfigure(0, weight=1)
        ctk.CTkOptionMenu(target_row, values=WEEKLY_TARGET_OPTIONS, variable=self.new_goal_target_var, height=38, fg_color=COLORS["bg_secondary"], button_color=COLORS["border"], button_hover_color=COLORS["brand"]).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkEntry(target_row, textvariable=self.new_goal_custom_hours_var, width=90, height=38, placeholder_text="自定义", fg_color=COLORS["bg_secondary"], border_color=COLORS["border"]).grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(target_row, text="小时 / 周", text_color=COLORS["text_secondary"], font=(FONT_FAMILY, 12)).grid(row=0, column=2, sticky="e", padx=(8, 0))

        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=(24, 0))
        buttons.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(buttons, text="取消", height=40, fg_color="transparent", border_width=1, border_color=COLORS["border"], command=dialog.destroy).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(buttons, text="创建目标", height=40, fg_color=COLORS["brand"], hover_color=COLORS["brand_hover"], command=lambda: self._create_goal_from_settings(dialog)).grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _create_goal_from_settings(self, dialog: ctk.CTkToplevel | None = None) -> None:
        try:
            goal = create_goal(
                self.new_goal_name_var.get(),
                self.new_goal_icon_var.get(),
                GOAL_COLOR_OPTIONS.get(self.new_goal_color_var.get(), COLORS["brand"]),
            )
            minutes = _minutes_from_weekly_option(self.new_goal_target_var.get(), self.new_goal_custom_hours_var.get())
            if minutes > 0:
                set_weekly_goal(str(goal["id"]), minutes)
        except ValueError as exc:
            messagebox.showerror("目标错误", str(exc))
            return
        self.new_goal_name_var.set("")
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        self._render_weekly_goal_settings()
        self._refresh_now()

    def _save_weekly_goals(self) -> None:
        for goal_id, option_var in self.weekly_goal_option_vars.items():
            custom_var = self.weekly_goal_custom_vars.get(goal_id, tk.StringVar(value=""))
            try:
                minutes = _minutes_from_weekly_option(option_var.get(), custom_var.get())
            except ValueError:
                messagebox.showerror("设置错误", "自定义周目标请输入小时数，例如 0.5 或 2.5。")
                return
            set_weekly_goal(goal_id, minutes)
        messagebox.showinfo("已保存", "本周目标已经保存。")
        self._render_weekly_goal_settings()
        self._refresh_now()

    def _save_settings(self) -> None:
        try:
            goal = max(1, int(self.goal_var.get().strip()))
        except ValueError:
            messagebox.showerror("设置错误", "每日创作目标必须是整数。")
            return
        blacklist = self.blacklist_text.get("1.0", "end").strip()
        set_setting("daily_goal_minutes", str(goal))
        set_setting("game_process_blacklist", blacklist)
        set_setting("auto_kill_enabled", "1" if self.auto_kill_var.get() else "0")
        set_setting("startup_enabled", "1" if self.startup_var.get() else "0")
        self.tracker.set_goal_minutes(goal)
        self.tracker.set_blacklist(blacklist.splitlines())
        self.tracker.set_auto_kill_enabled(self.auto_kill_var.get())
        try:
            enable_startup() if self.startup_var.get() else disable_startup()
        except Exception as exc:
            messagebox.showwarning("启动项设置失败", f"自动启动未能更新：{exc}")
        messagebox.showinfo("已保存", "设置已经保存。")
        self._refresh_now()

    def _start_creative(self) -> None:
        if self.tracker.get_snapshot().creative_active:
            self.today_status.set("创作计时已经在进行中。")
            return
        self._show_goal_picker()

    def _start_creative_with_goal(self, goal: dict[str, object], dialog: ctk.CTkToplevel | None = None) -> None:
        goal_id = str(goal.get("id") or "")
        goal_name = str(goal.get("name") or "未分类")
        started = self.tracker.start_creative(goal_id, goal_name)
        self.today_status.set(f"正在创作：{goal_name}。" if started else "创作计时已经在进行中。")
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        self._refresh_now()

    def _show_goal_picker(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("选择创作目标")
        dialog.geometry("560x620")
        dialog.attributes("-topmost", True)
        dialog.configure(fg_color=COLORS["bg"])
        ctk.CTkLabel(dialog, text="选择创作目标", font=(FONT_FAMILY, 24, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=24, pady=(22, 6))
        ctk.CTkLabel(dialog, text="本次创作结束后，时间会归入对应方向。", font=(FONT_FAMILY, 13), text_color=COLORS["text_secondary"]).pack(anchor="w", padx=24, pady=(0, 16))

        last_goal = get_last_goal()
        if last_goal:
            ctk.CTkButton(
                dialog,
                text=f"使用上次目标快速开始：{last_goal['name']}",
                height=42,
                fg_color=COLORS["brand"],
                hover_color=COLORS["brand_hover"],
                command=lambda goal=last_goal: self._start_creative_with_goal(goal, dialog),
            ).pack(fill="x", padx=24, pady=(0, 14))

        recent = get_recent_goals(limit=3)
        if recent:
            ctk.CTkLabel(dialog, text="最近使用目标", font=(FONT_FAMILY, 15, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=24, pady=(0, 8))
            recent_row = ctk.CTkFrame(dialog, fg_color="transparent")
            recent_row.pack(fill="x", padx=24, pady=(0, 16))
            for idx, goal in enumerate(recent):
                recent_row.grid_columnconfigure(idx, weight=1)
                ctk.CTkButton(
                    recent_row,
                    text=str(goal["name"]),
                    height=38,
                    fg_color=str(goal.get("color") or COLORS["brand"]),
                    hover_color=COLORS["brand_hover"],
                    command=lambda item=goal: self._start_creative_with_goal(item, dialog),
                ).grid(row=0, column=idx, sticky="ew", padx=(0 if idx == 0 else 8, 0))

        ctk.CTkLabel(dialog, text="全部目标", font=(FONT_FAMILY, 15, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=24, pady=(0, 8))
        list_frame = ctk.CTkScrollableFrame(dialog, fg_color=COLORS["card"], corner_radius=12, height=250)
        list_frame.pack(fill="both", expand=True, padx=24, pady=(0, 14))
        for row_index, goal in enumerate(get_goals()):
            row = ctk.CTkFrame(list_frame, fg_color=COLORS["bg_secondary"], corner_radius=10)
            row.pack(fill="x", padx=8, pady=6)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text="●", text_color=str(goal.get("color") or COLORS["brand"]), font=(FONT_FAMILY, 18, "bold")).grid(row=0, column=0, padx=(12, 8), pady=10)
            ctk.CTkLabel(row, text=str(goal["name"]), font=(FONT_FAMILY, 14, "bold"), text_color=COLORS["text"]).grid(row=0, column=1, sticky="w", pady=10)
            ctk.CTkButton(
                row,
                text="开始",
                width=76,
                height=32,
                fg_color=COLORS["brand"],
                hover_color=COLORS["brand_hover"],
                command=lambda item=goal: self._start_creative_with_goal(item, dialog),
            ).grid(row=0, column=2, padx=12, pady=10)

        create_row = ctk.CTkFrame(dialog, fg_color="transparent")
        create_row.pack(fill="x", padx=24, pady=(0, 22))
        create_row.grid_columnconfigure(0, weight=1)
        quick_name = tk.StringVar()
        ctk.CTkEntry(create_row, textvariable=quick_name, placeholder_text="新建目标名称", height=38, fg_color=COLORS["bg_secondary"], border_color=COLORS["border"]).grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ctk.CTkButton(
            create_row,
            text="新建并开始",
            width=120,
            height=38,
            fg_color=COLORS["brand"],
            hover_color=COLORS["brand_hover"],
            command=lambda: self._create_goal_and_start(quick_name.get(), dialog),
        ).grid(row=0, column=1, sticky="e")

    def _create_goal_and_start(self, name: str, dialog: ctk.CTkToplevel) -> None:
        try:
            goal = create_goal(name, "PenLine", COLORS["brand"])
        except ValueError as exc:
            messagebox.showerror("目标错误", str(exc))
            return
        self._start_creative_with_goal(goal, dialog)

    def _pause_creative(self) -> None:
        snapshot = self.tracker.get_snapshot()
        duration = self.tracker.pause_creative()
        goal_name = snapshot.active_goal_name or "未分类"
        self.today_status.set(f"已暂停「{goal_name}」，本次累计 {seconds_to_minutes(duration)} 分钟。" if duration > 0 else "当前没有正在进行的创作计时。")
        self._refresh_now()

    def _stop_creative(self) -> None:
        snapshot = self.tracker.get_snapshot()
        duration = self.tracker.stop_creative()
        goal_name = snapshot.active_goal_name or "未分类"
        self.today_status.set(f"已结束「{goal_name}」，本次累计 {seconds_to_minutes(duration)} 分钟。" if duration > 0 else "当前没有正在进行的创作计时。")
        self._refresh_now()

    def _refresh_live_metrics(self) -> None:
        snapshot = self.tracker.get_snapshot()
        elapsed = int(time.monotonic() - self._started_at)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        self.runtime_var.set(f"已运行：{hours:02d}:{minutes:02d}:{seconds:02d}")

        current_creative = snapshot.creative_seconds + snapshot.creative_session_seconds
        target_seconds = max(1, snapshot.target_minutes * 60)
        progress = min(1.0, current_creative / target_seconds)
        remaining = max(0, snapshot.remaining_creative_seconds)
        unlocked = remaining <= 0

        self.hero_goal_var.set(f"{current_creative // 60} / {snapshot.target_minutes} 分钟")
        self.hero_remaining_var.set("今日目标已完成，享受娱乐时间。" if unlocked else f"还需 {remaining // 60} 分钟即可解锁娱乐")
        self.hero_progress_card.set_metrics(
            progress,
            current_creative // 60,
            snapshot.target_minutes,
            remaining // 60,
        )
        self.hero_game_var.set(_fmt_minutes(snapshot.game_seconds))

        if unlocked:
            self.mode_var.set("已解锁娱乐")
            self.notice_var.set("今日目标已完成，享受娱乐时间")
            self.hero_status_var.set("已解锁娱乐")
            if snapshot.creative_active:
                self.today_status.set(f"正在创作：{snapshot.active_goal_name or '未分类'}。")
            else:
                self.today_status.set("今日目标已完成，享受娱乐时间。")
            self.status_title.configure(text_color=COLORS["success"])
            self.status_icon.configure(image=self._image("icon_unlock_green.png", (82, 82)))
            self.top_status_title.configure(image=self._image("icon_unlock_green.png", (18, 18)), text_color=COLORS["success"])
            if self._celebrated_day != snapshot.day:
                self._celebrated_day = snapshot.day
                self._show_completion_toast()
        else:
            self.mode_var.set("娱乐锁定中")
            self.notice_var.set("先完成创作目标，再开始娱乐")
            self.hero_status_var.set("娱乐锁定")
            if snapshot.creative_active:
                self.today_status.set(f"正在创作：{snapshot.active_goal_name or '未分类'}。")
            else:
                self.today_status.set("先完成创作目标，再开始娱乐。")
            self.status_title.configure(text_color=COLORS["warning"])
            self.status_icon.configure(image=self._image("icon_lock_orange.png", (82, 82)))
            self.top_status_title.configure(image=self._image("icon_lock_orange.png", (18, 18)), text_color=COLORS["warning"])

    def _refresh_analysis_panel(self) -> None:
        limit = 7 if self.analysis_scope_var.get() == "7 天" else 30 if self.analysis_scope_var.get() == "30 天" else None
        rows = get_recent_summaries(limit=limit)
        self._analysis_rows_cache = rows
        analysis = build_analysis(rows)
        total_game = sum(int(row.get("game_seconds") or 0) for row in rows)
        self.hero_streak_var.set(f"{analysis.consecutive_days} 天")
        self.hero_week_rate_var.set(f"{analysis.week_completion_rate * 100:.0f}%")
        self.summary_values["days"].set(str(analysis.days))
        self.summary_values["creative"].set(_fmt_seconds(analysis.total_creative_seconds))
        self.summary_values["game"].set(_fmt_seconds(total_game))
        self.summary_values["rate"].set(f"{analysis.completion_rate * 100:.0f}%")
        self.week_chart.set_data(rows[:7], "creative")
        self.creative_chart.set_data(rows, "creative")
        self.game_chart.set_data(rows, "game")
        self._render_heatmap(rows)
        self._render_weekly_goal_progress()
        self._render_goal_analysis()
        self._render_sessions()
        self._render_logs()

    def _render_heatmap(self, rows: list[dict[str, object]]) -> None:
        for child in self.heatmap_frame.winfo_children():
            child.destroy()
        ordered = list(reversed(rows[-30:] if len(rows) > 30 else rows))
        if not ordered:
            ctk.CTkLabel(self.heatmap_frame, text="暂无数据", text_color=COLORS["text_muted"]).pack(anchor="w")
            return
        for idx, row in enumerate(ordered):
            creative = int(row.get("creative_seconds") or 0)
            target = int(row.get("target_minutes") or 0) * 60
            color = COLORS["success"] if creative >= target and target > 0 else COLORS["border"]
            cell = ctk.CTkFrame(self.heatmap_frame, width=22, height=22, corner_radius=6, fg_color=color)
            cell.grid(row=idx // 15, column=idx % 15, padx=4, pady=4)
            cell.grid_propagate(False)

    def _render_table(self, parent: ctk.CTkFrame, headers: list[str], rows: list[list[str]], widths: list[int]) -> None:
        for child in parent.winfo_children():
            child.destroy()
        table = ctk.CTkFrame(parent, fg_color="transparent")
        table.pack(fill="x")
        for col, header in enumerate(headers):
            ctk.CTkLabel(table, text=header, width=widths[col], anchor="w", font=(FONT_FAMILY, 12, "bold"), text_color=COLORS["text_soft"], fg_color=COLORS["card"]).grid(row=0, column=col, sticky="ew", padx=1, pady=(0, 4))
            table.grid_columnconfigure(col, weight=1)
        for row_index, row in enumerate(rows, start=1):
            bg = COLORS["row_odd"] if row_index % 2 else COLORS["row_even"]
            for col, value in enumerate(row):
                ctk.CTkLabel(table, text=value, width=widths[col], anchor="w", font=(FONT_FAMILY, 12), text_color=COLORS["text_soft"], fg_color=bg, corner_radius=6).grid(row=row_index, column=col, sticky="ew", padx=1, pady=2)

    def _render_progress_list(self, parent: ctk.CTkFrame, rows: list[dict[str, object]], empty_text: str, max_rows: int | None = None) -> None:
        for child in parent.winfo_children():
            child.destroy()
        visible_rows = rows[:max_rows] if max_rows is not None else rows
        if not visible_rows:
            ctk.CTkLabel(parent, text=empty_text, text_color=COLORS["text_muted"], font=(FONT_FAMILY, 13)).pack(anchor="w", padx=4, pady=8)
            return
        for item in visible_rows:
            target = int(item.get("target_minutes") or 0)
            completed = int(item.get("completed_minutes") or 0)
            raw_progress = float(item.get("progress") or 0)
            progress = min(1.0, raw_progress)
            remaining = target - completed
            status = "已超额完成" if remaining < 0 else f"剩余 {_fmt_goal_minutes(remaining)}"
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=6)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text="●", text_color=str(item.get("color") or COLORS["brand"]), font=(FONT_FAMILY, 15, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8))
            ctk.CTkLabel(row, text=str(item.get("goal_name") or item.get("name") or "未分类"), font=(FONT_FAMILY, 13, "bold"), text_color=COLORS["text"]).grid(row=0, column=1, sticky="w")
            ctk.CTkLabel(row, text=f"{_fmt_goal_minutes(completed)} / {_fmt_goal_minutes(target)}  {min(100, int(raw_progress * 100))}%", font=(FONT_FAMILY, 12), text_color=COLORS["text_secondary"]).grid(row=0, column=2, sticky="e")
            ctk.CTkLabel(row, text=status, font=(FONT_FAMILY, 11), text_color=COLORS["success"] if remaining < 0 else COLORS["text_muted"]).grid(row=1, column=1, sticky="w", pady=(4, 0))
            bar = ctk.CTkProgressBar(row, height=10, fg_color=COLORS["bg_secondary"], progress_color=str(item.get("color") or COLORS["brand"]))
            bar.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(6, 0))
            bar.set(progress)

    def _render_weekly_goal_progress(self) -> None:
        rows = get_weekly_goal_progress()
        self._render_progress_list(self.weekly_goal_progress_frame, rows, "还没有设置本周计划。去「目标」模块添加计划。", max_rows=3)
        self._render_progress_list(self.analysis_weekly_goal_frame, rows, "还没有设置本周目标。")

    def _render_goal_analysis(self) -> None:
        for child in self.goal_rank_frame.winfo_children():
            child.destroy()
        rows = get_goal_time_stats(limit=8)
        total_seconds = sum(int(row.get("total_seconds") or 0) for row in rows)
        if not rows:
            ctk.CTkLabel(self.goal_rank_frame, text="还没有带目标的创作记录。", text_color=COLORS["text_muted"], font=(FONT_FAMILY, 13)).pack(anchor="w", padx=4, pady=8)
            return
        display_rows = []
        for row in rows:
            seconds = int(row.get("total_seconds") or 0)
            percent = int(seconds / total_seconds * 100) if total_seconds > 0 else 0
            display_rows.append([
                str(row.get("goal_name") or "未分类"),
                _fmt_seconds(seconds),
                f"{percent}%",
            ])
        self._render_table(self.goal_rank_frame, ["方向", "累计时长", "占比"], display_rows, [220, 160, 100])

    def _render_sessions(self) -> None:
        snapshot = self.tracker.get_snapshot()
        rows = []
        for session in get_creative_sessions(snapshot.day)[:8]:
            rows.append([session["start_at"], session["goal_name"], _fmt_seconds(int(session["duration_seconds"]))])
        if not rows:
            rows = [["今天还没有创作记录", "--", "--"]]
        self._render_table(self.sessions_table, ["开始时间", "目标", "时长"], rows, [220, 220, 120])

    def _render_logs(self) -> None:
        events = get_game_events(limit=20)
        event_rows = [
            [
                event["detected_at"],
                f"{event['day']} | {event['process_names']} | {event['action_taken']} | 剩余 {_fmt_seconds(int(event['creative_remaining_seconds']))}",
            ]
            for event in events
        ]
        if not event_rows:
            event_rows = [["暂无游戏拦截记录", "--"]]
        self._render_table(self.game_log_list, ["时间", "内容"], event_rows, [220, 680])

        summary_rows = []
        for row in get_recent_summaries(limit=30):
            creative = int(row.get("creative_seconds") or 0)
            target = int(row.get("target_minutes") or 0)
            summary_rows.append([
                str(row.get("day") or "--"),
                str(row.get("first_start_at") or "--"),
                _fmt_seconds(creative),
                _fmt_seconds(int(row.get("game_seconds") or 0)),
                _fmt_seconds(int(row.get("total_pc_seconds") or 0)),
                f"{target} 分钟",
                "达标" if creative >= target * 60 else "未达标",
            ])
        self._render_table(self.summary_list, ["日期", "首次开机", "创作", "娱乐", "电脑使用", "目标", "状态"], summary_rows, [110, 190, 110, 110, 130, 100, 90])

    def _show_completion_toast(self) -> None:
        if self.sound_var.get():
            try:
                self.bell()
            except Exception:
                pass
        toast = ctk.CTkToplevel(self)
        toast.title("FocusDawn")
        toast.geometry("360x120")
        toast.attributes("-topmost", True)
        toast.configure(fg_color=COLORS["card"])
        ctk.CTkLabel(toast, text="今日目标完成", font=(FONT_FAMILY, 18, "bold"), text_color=COLORS["success"]).pack(anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(toast, text="已解锁娱乐时间", font=(FONT_FAMILY, 14), text_color=COLORS["text_secondary"]).pack(anchor="w", padx=20)
        toast.after(2600, toast.destroy)

    def _handle_game_detected(self, process_names: list[str], remaining_seconds: int) -> None:
        self.after(0, lambda: self._show_game_dialog(process_names, remaining_seconds))

    def _show_game_dialog(self, process_names: list[str], remaining_seconds: int) -> None:
        if self._game_dialog is not None and self._game_dialog.winfo_exists():
            self._game_dialog.lift()
            self._game_dialog.focus_force()
            return

        dialog = ctk.CTkToplevel(self)
        self._game_dialog = dialog
        dialog.title("FocusDawn 提醒")
        dialog.geometry("500x320")
        dialog.attributes("-topmost", True)
        dialog.configure(fg_color=COLORS["bg"])
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._dismiss_game_dialog(dialog))

        countdown_var = tk.StringVar(value=f"{AUTO_KILL_GRACE_SECONDS} 秒后将自动关闭")
        ctk.CTkLabel(dialog, text="先完成创作目标", font=(FONT_FAMILY, 22, "bold"), text_color=COLORS["warning"]).pack(padx=24, pady=(24, 8))
        ctk.CTkLabel(dialog, text=f"检测到娱乐进程：{', '.join(process_names)}", font=(FONT_FAMILY, 14), text_color=COLORS["text"], justify="center").pack(padx=24, pady=(4, 4))
        ctk.CTkLabel(dialog, text=f"距离今日目标还差 {_fmt_seconds(remaining_seconds)}。", font=(FONT_FAMILY, 14), text_color=COLORS["text_secondary"], justify="center").pack(padx=24, pady=(0, 10))
        ctk.CTkLabel(dialog, textvariable=countdown_var, font=(FONT_FAMILY, 20, "bold"), text_color=COLORS["brand"]).pack(padx=24, pady=(4, 2))
        ctk.CTkLabel(dialog, text="你可以先手动关闭；倒计时结束后 FocusDawn 会尝试强制关闭。", font=(FONT_FAMILY, 12), text_color=COLORS["text_muted"], justify="center").pack(padx=24, pady=(2, 8))

        row = ctk.CTkFrame(dialog, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=16)
        row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(row, text="我去手动关闭", command=lambda: self._dismiss_game_dialog(dialog), fg_color=COLORS["brand"], hover_color=COLORS["brand_hover"]).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(row, text="立即关闭", fg_color="transparent", border_width=1, border_color=COLORS["border"], command=lambda: self._force_close_from_dialog(dialog, process_names, remaining_seconds)).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self._tick_game_dialog_countdown(dialog, countdown_var, AUTO_KILL_GRACE_SECONDS)

    def _tick_game_dialog_countdown(self, dialog: ctk.CTkToplevel, countdown_var: tk.StringVar, seconds_left: int) -> None:
        if not dialog.winfo_exists():
            return
        if seconds_left <= 0:
            countdown_var.set("正在自动关闭...")
            self._game_dialog_after_id = None
            self._refresh_now()
            return
        countdown_var.set(f"{seconds_left} 秒后将自动关闭")
        self._game_dialog_after_id = self.after(1000, lambda: self._tick_game_dialog_countdown(dialog, countdown_var, seconds_left - 1))

    def _dismiss_game_dialog(self, dialog: ctk.CTkToplevel) -> None:
        if self._game_dialog_after_id is not None:
            try:
                self.after_cancel(self._game_dialog_after_id)
            except Exception:
                pass
            self._game_dialog_after_id = None
        if dialog.winfo_exists():
            dialog.destroy()
        if self._game_dialog is dialog:
            self._game_dialog = None

    def _force_close_from_dialog(self, dialog: ctk.CTkToplevel, process_names: list[str], remaining_seconds: int) -> None:
        closed = self.tracker.force_close_blacklisted_processes()
        action_taken = f"用户点击关闭成功：{', '.join(closed)}" if closed else "用户点击关闭失败"
        record_game_event(self.tracker.get_snapshot().day, process_names, remaining_seconds, action_taken)
        self.tracker.clear_pending_game_alert()
        self.today_status.set(f"已关闭：{', '.join(closed)}" if closed else "未找到可关闭的黑名单进程。")
        self._dismiss_game_dialog(dialog)
        self._refresh_now()

    def _schedule_fast_refresh(self) -> None:
        self._fast_refresh_after_id = self.after(1000, self._fast_refresh_loop)

    def _fast_refresh_loop(self) -> None:
        self._refresh_live_metrics()
        self._schedule_fast_refresh()

    def _schedule_slow_refresh(self) -> None:
        self._slow_refresh_after_id = self.after(5000, self._slow_refresh_loop)

    def _slow_refresh_loop(self) -> None:
        self._refresh_analysis_panel()
        self._schedule_slow_refresh()

    def _refresh_now(self) -> None:
        self._refresh_live_metrics()
        self._refresh_analysis_panel()

    def _create_tray_image(self) -> Image.Image:
        try:
            image = Image.open(ASSET_DIR / "app_icon.png").convert("RGBA")
            return image.resize((64, 64), Image.Resampling.LANCZOS)
        except Exception:
            image = Image.new("RGBA", (64, 64), (15, 23, 42, 255))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((6, 6, 58, 58), radius=14, fill=(59, 130, 246, 255))
            draw.text((11, 18), "FD", fill=(248, 250, 252, 255))
            return image

    def _start_tray(self) -> None:
        if self._tray_icon is not None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("显示窗口", lambda *_: self.after(0, self._show_window)),
            pystray.MenuItem("隐藏窗口", lambda *_: self.after(0, self._hide_window)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda *_: self.after(0, self._quit_from_tray)),
        )
        self._tray_icon = pystray.Icon("FocusDawn", self._create_tray_image(), "FocusDawn 创作守护", menu)
        self._tray_thread = threading.Thread(target=self._tray_icon.run, name="FocusDawn-tray", daemon=True)
        self._tray_thread.start()

    def _show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()
        self._hidden_to_tray = False

    def _hide_window(self) -> None:
        self.withdraw()
        self._hidden_to_tray = True

    def _quit_from_tray(self) -> None:
        self._closing = True
        self._shutdown()

    def _on_close(self) -> None:
        if not self._closing:
            self._hide_window()
            return
        self._shutdown()

    def _shutdown(self) -> None:
        try:
            for after_id in (self._fast_refresh_after_id, self._slow_refresh_after_id, self._game_dialog_after_id):
                if after_id is not None:
                    try:
                        self.after_cancel(after_id)
                    except Exception:
                        pass
            self.tracker.stop()
        finally:
            if self._tray_icon is not None:
                try:
                    self._tray_icon.stop()
                except Exception:
                    pass
            self.destroy()
