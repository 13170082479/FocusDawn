from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "makedawn.db"

DEFAULT_DAILY_GOAL_MINUTES = 60
DEFAULT_BLACKLIST = [
    "steam.exe",
    "wegame.exe",
    "tgp_daemon.exe",
    "client-win64-shipping.exe",
    "mistfallhunter-win64-shipping.exe",
    "wuthering waves.exe",
]

DEFAULT_GOALS = [
    {"id": "goal_tweet", "name": "写推文", "icon": "PenLine", "color": "#4D8EFF"},
    {"id": "goal_article", "name": "写公众号", "icon": "Newspaper", "color": "#22C55E"},
    {"id": "goal_novel", "name": "写小说", "icon": "BookOpen", "color": "#A855F7"},
    {"id": "goal_ai", "name": "学习 AI", "icon": "Sparkles", "color": "#F97316"},
    {"id": "goal_reading", "name": "读书", "icon": "Library", "color": "#EAB308"},
    {"id": "goal_video", "name": "做视频", "icon": "Video", "color": "#EF4444"},
]
UNCATEGORIZED_GOAL_ID = "goal_uncategorized"
UNCATEGORIZED_GOAL_NAME = "未分类"
DEFAULT_AUTO_KILL_ENABLED = True
DEFAULT_STARTUP_ENABLED = False
DEFAULT_ALERT_COOLDOWN_SECONDS = 60
AUTO_KILL_GRACE_SECONDS = 60
PROCESS_SCAN_INTERVAL_SECONDS = 5
UI_REFRESH_INTERVAL_MS = 1000
