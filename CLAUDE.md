# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

media-cleaner 是一个零外部依赖的 Python 桌面工具，用于管理大型 AV 视频目录。通过 tkinter GUI 提供三个核心功能：扫描/删除空文件夹、基于 AV 番号检测重复视频文件、清理视频文件名（去域名/URL 前缀并统一大写格式）。

## Commands

```bash
# 运行 GUI 应用
python main.py
```

无测试、无 linter 配置。

## Architecture

项目为扁平结构，所有 Python 文件位于根目录，直接 `python main.py` 启动。

**四层结构：**

- `main.py` — GUI 层（`VideoCleanerGUI`）。tkinter 界面，提供三个操作按钮：扫描空文件夹、查找重复视频、重命名视频。耗时操作通过 `threading.Thread` 后台执行，UI 更新通过 `root.after()` 回调主线程。
- `cleaner.py` — 核心逻辑（`VideoCleaner`）。空文件夹扫描使用 `os.walk(topdown=False)` 自底向上遍历；重复视频检测通过提取文件名中的 AV 番号进行分组；视频重命名通过 `extractor.clean_filename()` 生成规范化文件名。
- `extractor.py` — 番号提取与文件名清理（`AVCodeExtractor`）。`extract()` 正则匹配 `ABC-123` / `ABC123` / `123ABC-456` 格式，提取前会剥离 URL 前缀和常见后缀（`_FHD`, `_HD`, `_UNCENSORED` 等）。`clean_filename()` 在任意位置去除域名/URL、下划线转中横线、统一大写，用于重命名功能。
- `log.py` — 日志配置。自定义 `GUIHandler` 通过 `root.after()` 线程安全地将日志写入 GUI 的 `tk.Text` 控件，同时写入 `Path.cwd() / media_cleaner.log` 文件（日志路径为当前工作目录，非项目目录）。各模块通过 `get_logger(__name__)` 获取 logger。

**数据流：** GUI 选择目录 → 点击扫描按钮 → 后台线程执行 `VideoCleaner` 方法（通过 `progress_callback` 报告进度）→ 结果填充 Treeview → 用户可选择打开文件夹或删除空文件夹。

**安全设计：** 删除操作默认为 dry-run 模式；重复视频的删除功能被显式禁用（仅展示）。

## Key Technical Details

- 支持的视频格式：`.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.flv`, `.webm`, `.mpg`, `.mpeg`, `.rm`, `.rmvb`
- 跨平台打开文件夹：Windows 用 `explorer`，macOS 用 `open`，Linux 用 `xdg-open`
- 空文件夹扫描跳过以 `.` 开头的隐藏目录
