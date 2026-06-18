# FocusDawn 项目交接文档

更新时间：2026-06-16

## 1. 项目概况

- 项目名称：FocusDawn
- 项目定位：Windows 本地创作守护工具
- 核心目标：帮助用户形成“先创作，后娱乐”的日常习惯
- 工作方式：记录每日创作时长；未达成目标时检测游戏/游戏平台进程；先提醒用户关闭，超过宽限时间后可自动关闭
- 项目目录：`D:\AI_project\note`
- 数据库：`data\makedawn.db`
- 打包产物：`dist\FocusDawn.exe`

## 2. 技术栈与依赖

- Python 3.14
- tkinter / customtkinter：桌面 UI
- sqlite3：本地数据存储
- psutil：进程扫描和进程终止
- pystray：托盘常驻
- Pillow：图片资源、托盘图标、Canvas 背景合成
- PyInstaller：Windows 单文件 exe 打包

安装依赖：

```bash
pip install -r requirements.txt
```

当前 `requirements.txt`：

```text
psutil>=5.9
pystray>=0.19
Pillow>=12.0
customtkinter>=5.2.2
```

注意：进程检测和强制关闭依赖 `psutil`。打包时需要确认 PyInstaller 日志中出现 `hook-psutil.py` 或类似 psutil 相关记录，否则 exe 内可能无法检测进程。

## 3. 当前功能状态

已完成：

- 每日第一次启动时间记录
- 每日电脑使用时长统计
- 创作计时：开始、暂停、结束
- 每日创作目标设置
- 今日创作进度展示
- 连续达标天数统计
- 本周达标率统计
- 今日娱乐时长统计
- 数据分析页：7 天、30 天、全部历史
- 日志页：游戏/平台拦截记录、每日摘要
- 默认创作目标初始化：写推文、写公众号、写小说、学习 AI、读书、做视频
- 开始创作前选择目标方向
- 创作 session 绑定 goal_id / goal_name
- 一级「目标」模块支持卡片式目标列表、新建目标弹窗、编辑目标、归档目标、设置本周目标时间
- 首页支持“本周计划”卡片，最多展示 3 个目标
- 数据分析页支持创作方向排行榜、本周目标完成情况
- 首页支持连续创作当前/最高纪录
- 首页支持今日最长专注时段
- 数据分析页支持创作热力图和本周创作报告
- 数据分析页支持最近 8 周历史周报
- 软件启动时播放启动语音
- 游戏/游戏平台进程黑名单
- 未达标时检测黑名单进程并弹窗提醒
- 提醒弹窗显示 60 秒自动关闭倒计时
- 默认开启强制关闭
- 先提醒，60 秒后若进程仍存在则自动关闭
- 托盘常驻、隐藏窗口、退出
- Windows 开机自启动配置
- app icon / tray icon / exe icon 已更换为 FocusDawn 图标
- 打包生成 `dist\FocusDawn.exe`

## 4. 当前默认配置

位置：`config.py`

```python
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
DEFAULT_AUTO_KILL_ENABLED = True
DEFAULT_STARTUP_ENABLED = False
DEFAULT_ALERT_COOLDOWN_SECONDS = 60
AUTO_KILL_GRACE_SECONDS = 60
PROCESS_SCAN_INTERVAL_SECONDS = 5
```

当前策略：

- 每 5 秒扫描一次进程
- 如果未完成今日创作目标，且发现黑名单进程，先弹窗提醒
- 弹窗提醒后，如果 60 秒内用户未手动关闭，且进程仍在运行，则自动关闭
- 自动关闭会尝试先 `terminate()`，等待 2 秒后仍未退出则 `kill()`
- 关闭主进程时会尝试同时关闭其子进程

## 5. 当前黑名单说明

当前已包含：

- `steam.exe`：Steam 平台入口
- `wegame.exe`：WeGame 平台入口
- `tgp_daemon.exe`：WeGame/TGP 守护入口
- `client-win64-shipping.exe`：已有游戏进程
- `mistfallhunter-win64-shipping.exe`：雾影猎人 Demo / Mistfall Hunter Demo
- `wuthering waves.exe`：鸣潮

注意：

- 黑名单按进程名匹配，不按 Steam/WeGame 里的游戏显示名匹配。
- 添加新游戏时，应先启动游戏，再查看真实 `.exe` 进程名。
- 不建议默认加入 `steamservice.exe`、`wegameservice.exe` 这类服务进程，可能涉及权限或服务恢复问题。

## 6. 主要模块说明

### `main.py`

- 程序入口
- 创建并启动 `FocusDawnApp`

### `ui.py`

- 主窗口、导航、首页、数据分析、设置、日志
- `HeroProgressCard`：首页“今日创作进度”Canvas 卡片
- 开始创作前的目标选择面板
- 首页“本周目标进度”卡片
- 分析页“创作方向排行榜 / 本周目标完成情况”
- 一级「目标」模块：“目标管理与本周计划”，卡片式展示目标、进度、剩余/超额状态，支持编辑和归档
- 游戏/平台提醒弹窗
- 目标完成 toast
- 托盘图标和托盘菜单
- 设置页保存每日目标、黑名单、强制关闭、自启动

### `tracker.py`

- 后台线程核心逻辑
- 记录电脑使用时长
- 记录创作 session
- 保存当前创作 session 的 goal_id / goal_name
- 扫描黑名单进程
- 未达标时触发提醒回调
- 记录娱乐时长
- 处理 60 秒宽限后的自动关闭
- `force_close_blacklisted_processes()` 负责关闭黑名单命中的进程及子进程

### `storage.py`

- SQLite 初始化和读写
- 默认配置写入
- 数据库迁移
- 每日摘要、创作片段、游戏事件、设置项持久化
- 创作目标、周目标、按目标统计查询

### `analyzer.py`

- 汇总分析数据
- 统计总创作时长、娱乐时长、电脑使用时长
- 统计达标率、连续达标天数、本周达标率

### `startup.py`

- Windows 注册表开机自启动
- 注册名：`FocusDawn`

### `config.py`

- 默认目标
- 默认创作方向
- 未分类目标兼容旧数据
- 默认黑名单
- 扫描间隔
- 提醒冷却
- 自动关闭宽限时间

## 7. 数据库结构

数据库文件：`data\makedawn.db`

### `settings`

- `daily_goal_minutes`
- `game_process_blacklist`
- `auto_kill_enabled`
- `startup_enabled`
- `alert_cooldown_seconds`

### `daily_summary`

- `day`
- `first_start_at`
- `total_pc_seconds`
- `creative_seconds`
- `game_seconds`
- `target_minutes`
- `updated_at`

### `creative_sessions`

- `id`
- `day`
- `start_at`
- `end_at`
- `duration_seconds`
- `goal_id`
- `goal_name`
- `created_at`

旧数据迁移策略：

- 没有 `goal_id` 的旧记录自动归入 `goal_uncategorized`
- `goal_name` 显示为 `未分类`

### `goals`

- `id`
- `name`
- `icon`
- `color`
- `archived`：归档后不再出现在开始创作和本周计划中，历史 session 保留
- `created_at`
- `updated_at`

### `weekly_goals`

- `id`
- `goal_id`
- `goal_name`
- `target_minutes`
- `week_start_date`
- `created_at`
- `updated_at`

### `game_events`

- `id`
- `day`
- `detected_at`
- `process_names`
- `creative_remaining_seconds`
- `action_taken`

## 8. UI 状态

当前 UI 已完成 FocusDawn 品牌化：

- 窗口标题：`FocusDawn - 创作守护`
- 左上角品牌：`FocusDawn ✦`
- 标题栏、托盘、exe 使用 `assets\ui\app_icon.ico`
- 图标源图：`assets\ui\app_icon.png`
- 启动音频：`assets\audio\startup_voice.mp3`
- 首页“今日创作进度”已改为 Canvas 绘制，背景图、暗色遮罩、圆环、进度条和文字在同一层，避免控件叠背景图产生黑框
- 首页新增“本周目标进度”
- 开始创作按钮会先打开“选择创作目标”面板
- 导航栏新增一级「目标」模块，承载“目标管理与本周计划”
- 分析页新增目标维度统计
- 首页新增“连续创作”和“最长专注”反馈
- 数据分析页热力图按最近 35 天创作时长分级着色
- 数据分析页新增“本周创作报告”
- 启动后异步播放 `assets\audio\startup_voice.mp3`，使用 Windows `winmm`，不额外引入依赖
- 右侧“当前状态”仍是普通 CTk 控件结构

## 9. 启动与打包

开发运行：

```bash
python main.py
```

打包：

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

或：

```bat
build.bat
```

生成：

```text
dist\FocusDawn.exe
```

打包脚本会包含：

- `README.md`
- `requirements.txt`
- `assets`
- `assets\ui\app_icon.ico`

## 10. 最近关键修改

### 品牌修改

- 项目对外名称改为 FocusDawn
- exe 名称改为 `FocusDawn.exe`
- 开机自启动注册名改为 `FocusDawn`
- 新增 `assets\ui\app_icon.png`
- 新增 `assets\ui\app_icon.ico`

### 首页视觉

- 首页创作进度卡改为 `HeroProgressCard`
- 用 PIL 预合成背景图、遮罩和边框
- 避免 Canvas `stipple` 和控件透明导致的网格、角标、黑框问题

### 娱乐拦截

- 默认黑名单加入 Steam、WeGame、Mistfall Hunter Demo
- 默认开启强制关闭
- 从“检测到立即关闭”改为“先提醒，60 秒后仍存在再关闭”
- 提醒弹窗显示倒计时
- 安装并打包 psutil，确保 exe 内能扫描和关闭进程

### 创作目标 + 周目标

- 新增默认目标：写推文、写公众号、写小说、学习 AI、读书、做视频
- 新增兼容目标：未分类
- 开始创作前必须选择目标
- 结束/暂停创作后，session 保存目标信息
- 「目标」模块可以通过弹窗新建目标，并为当前周设置目标小时数
- 周目标时间使用预设选项：30 分钟、1/3/5/10 小时、自定义
- 目标可编辑名称、图标、颜色
- 目标可归档，历史记录不删除
- 数据分析按 `goal_id` 聚合，目标改名后不会被拆成多行
- 首页最多展示 3 个本周目标进度
- 分析页展示创作方向排行榜和本周目标完成情况

### 体验升级第二阶段

- 连续创作系统：显示当前连续天数和历史最高连续纪录
- 连续规则：当日创作时长达到当天目标才计入连续达标；中断则从 0 开始
- 今日最佳记录：首页显示当天最长专注 session
- 创作热力图：按最近 35 天创作时长分级着色
- 每周复盘：展示总创作时长、达标天数、连续创作、娱乐时长、创作最多的一天
- 每周复盘会和上周总创作时长对比，显示多/少创作了多久
- 历史周报：展示最近 8 周的创作时长、达标天数、娱乐时长、完成率、较上周变化
- 成就系统暂不实现，规划到第三阶段

第一阶段已完成范围：

- 创建默认目标
- 开始创作前选择目标
- 创作记录绑定目标
- 设置每周目标
- 首页显示本周目标进度
- 数据分析显示按目标统计

第二阶段已完成：

- 完整编辑目标名称、图标、颜色
- 删除目标时归档，不直接删除历史记录

后续建议：

- 趋势图按目标筛选
- 超额完成提示
- 成就系统：第一次达标、连续 7 天、连续 30 天、累计创作 100 小时等

## 11. 已知风险

- 黑名单仍按进程名匹配，可能误杀同名非游戏进程。
- 强制关闭游戏平台可能触发平台自身恢复机制，尤其是服务进程未关闭时。
- `tracker.py` 和 `ui.py` 里仍有部分历史中文字符串是乱码，建议尽快清理。
- 当前 `auto_kill_enabled` 默认开启，体验更强硬；如果未来面向普通用户，建议提供首次启动确认。
- 首页右侧“当前状态”仍使用 CTk 控件叠加结构，如果以后恢复背景图，仍可能遇到黑框问题。
- 周目标目前只支持当前周编辑，历史周计划编辑放第二阶段。
- 已归档目标暂不提供恢复入口，如需恢复可后续加入“已归档目标”列表。

## 12. 建议下一步

优先级建议：

1. 趋势图支持按目标筛选。
2. 历史周报支持点击展开该周各目标完成情况。
3. 已归档目标列表与恢复。
4. 成就系统：第一次达标、连续 7 天、连续 30 天、累计创作 100 小时等。
5. 增加“扫描当前娱乐进程”按钮，在设置页显示当前命中的进程。
6. 修复 UI/日志中的乱码字符串。
7. 将黑名单从纯文本升级为分组管理：游戏平台、游戏、附属进程。
8. 给 Steam/WeGame 关闭策略增加更细控制，例如是否关闭 webhelper/service。

## 13. 当前结论

FocusDawn 当前已经能完成第一版闭环：

- 记录创作
- 判断目标
- 发现娱乐入口
- 先提醒
- 超时后强制关闭
- 记录日志
- 打包为 Windows exe

下一阶段重点是把“目标系统”从可用推进到好用：补齐目标编辑/归档、历史周完成率、按目标筛选趋势图，让 FocusDawn 回答“时间花在了哪些重要方向上”。
