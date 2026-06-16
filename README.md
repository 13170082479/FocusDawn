# FocusDawn

FocusDawn 是一个 Windows 本地创作守护工具，核心目标是帮助你形成“先创作，后娱乐”的日常习惯。

## 现在支持什么

- 记录每天第一次开机时间
- 统计当天电脑使用时长
- 统计当天创作时长
- 设置每日创作目标
- 维护游戏进程黑名单
- 在未达标时弹窗提醒
- 可选强制关闭黑名单进程
- 开机自启动
- 托盘常驻
- 数据分析页支持周视图、月视图和全部历史
- 展示连续达标天数、今日娱乐时长、达标率等反馈

## 界面风格

- 深色模式优先
- 卡片式布局
- 首页突出“今日创作进度”
- 数据分析页使用柱状图展示趋势
- 目标完成时会弹出庆祝提示

## 运行方式

```bash
pip install -r requirements.txt
python main.py
```

## 打包 exe

Windows 下可使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

或者：

```bat
build.bat
```

打包完成后，程序会生成到 `dist\FocusDawn.exe`。

## 数据位置

- SQLite 数据库：`data/makedawn.db`

## 重要文件

- `main.py` - 程序入口
- `ui.py` - 桌面界面
- `tracker.py` - 开机、创作和进程监控
- `storage.py` - SQLite 数据读写
- `analyzer.py` - 数据分析汇总
- `startup.py` - Windows 开机自启动
- `config.py` - 默认配置

## 黑名单扫描方式

当前采用的是进程名轮询扫描：

- 用户手动添加进程名
- `psutil` 每 5 秒检查一次当前运行进程
- 如果命中黑名单且创作未达标，就会弹窗提醒
- 如果开启“强制关闭”，会尝试结束对应进程

## 建议

第一版建议优先使用“提醒 + 手动关闭”模式，尽量减少误杀。
