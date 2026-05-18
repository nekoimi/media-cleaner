"""GUI主程序"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
import subprocess
import platform
from typing import List, Dict
from cleaner import VideoCleaner
from jellyfin import JellyfinMigrator
from log import setup_logging, get_logger

logger = get_logger("main")


class ToolTip:
    """鼠标悬浮提示"""

    def __init__(self, widget):
        self.widget = widget
        self.tip_window = None
        self.text = ""

    def show(self, text, x, y):
        if text == self.text and self.tip_window:
            return
        self.hide()
        self.text = text
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x + 16}+{y + 10}")
        label = tk.Label(tw, text=text, background="#ffffe0", relief=tk.SOLID, borderwidth=1, font=("", 9))
        label.pack()

    def hide(self):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None
            self.text = ""


class VideoCleanerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("媒体文件清理工具")
        self.root.resizable(True, True)
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - 900) // 2
        y = (screen_height - 700) // 2
        self.root.geometry(f"900x700+{x}+{y}")

        self.target_dir = tk.StringVar()
        self.strm_prefix = tk.StringVar()
        self.strm_target = tk.StringVar()
        self.cleaner = None
        self.current_thread = None

        self.current_mode = None  # "empty_folders", "duplicates", "rename", "strm"
        self.scanned_data = []  # 存储当前扫描的数据
        self.selected_items = set()  # 选中的项

        # Jellyfin 迁移
        self.old_db_path = tk.StringVar()
        self.new_db_path = tk.StringVar()
        self.jellyfin_migrator = None
        self.mapping_data = []

        self._setup_ui()
        setup_logging(self.root, self.log_text)

    def _setup_ui(self):
        padding = {"padx": 10, "pady": 5}

        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Notebook with two tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        tab_cleaner = ttk.Frame(self.notebook)
        tab_jellyfin = ttk.Frame(self.notebook)
        self.notebook.add(tab_cleaner, text="媒体文件清理")
        self.notebook.add(tab_jellyfin, text="Jellyfin 迁移")

        # Tab 2: Jellyfin 迁移
        self._setup_jellyfin_tab(tab_jellyfin)

        # === Tab 1: 媒体文件清理 ===
        ttk.Label(tab_cleaner, text="目标目录:").pack(anchor=tk.W, **padding)

        dir_frame = ttk.Frame(tab_cleaner)
        dir_frame.pack(fill=tk.X, **padding)

        dir_entry = ttk.Entry(dir_frame, textvariable=self.target_dir)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(dir_frame, text="选择目录", command=self._select_directory).pack(side=tk.LEFT, padx=5)

        ttk.Separator(tab_cleaner, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        actions_frame = ttk.LabelFrame(tab_cleaner, text="操作", padding=5)
        actions_frame.pack(fill=tk.X, **padding)

        btn_frame = ttk.Frame(actions_frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="扫描空文件夹", command=self._scan_empty_folders).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(btn_frame, text="查找重复视频", command=self._find_duplicates).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(btn_frame, text="重命名视频", command=self._rename_videos).pack(side=tk.LEFT, padx=5, pady=5)

        strm_frame = ttk.Frame(actions_frame)
        strm_frame.pack(fill=tk.X)
        ttk.Button(strm_frame, text="生成STRM", command=self._scan_strm).pack(side=tk.LEFT, padx=5, pady=5)
        strm_entry = ttk.Entry(strm_frame, textvariable=self.strm_prefix)
        strm_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        self.strm_prefix.set("")
        strm_entry.insert(0, "输入路径前缀，如 http://example.com/")
        strm_entry.bind("<FocusIn>", lambda e: strm_entry.delete(0, tk.END) if strm_entry.get() == "输入路径前缀，如 http://example.com/" else None)
        strm_entry.bind("<FocusOut>", lambda e: strm_entry.insert(0, "输入路径前缀，如 http://example.com/") if not strm_entry.get() else None)

        strm_target_frame = ttk.Frame(actions_frame)
        strm_target_frame.pack(fill=tk.X)
        ttk.Button(strm_target_frame, text="选择移动目标", command=self._select_strm_target).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Entry(strm_target_frame, textvariable=self.strm_target, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)

        ttk.Separator(tab_cleaner, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        results_frame = ttk.LabelFrame(tab_cleaner, text="扫描结果", padding=5)
        results_frame.pack(fill=tk.BOTH, expand=True, **padding)

        self.result_label = ttk.Label(results_frame, text="等待扫描...")
        self.result_label.pack(anchor=tk.W, pady=(0, 5))

        tree_container = ttk.Frame(results_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)

        columns = ("path", "new_name")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("path", text="路径")
        self.tree.column("path", width=700, anchor=tk.W)
        self.tree.heading("new_name", text="新文件名")
        self.tree.column("new_name", width=0, stretch=False)

        scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self._on_item_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)

        result_buttons = ttk.Frame(results_frame)
        result_buttons.pack(fill=tk.X, pady=5)

        ttk.Button(result_buttons, text="打开选中项所在文件夹", command=self._open_selected_folders).pack(side=tk.LEFT, padx=5)
        ttk.Button(result_buttons, text="删除选中项", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(result_buttons, text="重命名选中项", command=self._execute_rename).pack(side=tk.LEFT, padx=5)
        ttk.Button(result_buttons, text="生成选中项STRM", command=self._execute_strm).pack(side=tk.LEFT, padx=5)
        ttk.Button(result_buttons, text="全选", command=self._select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(result_buttons, text="清空选择", command=self._clear_selection).pack(side=tk.LEFT, padx=5)

        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        log_frame = ttk.LabelFrame(main_frame, text="日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, **padding)

        self.log_text = tk.Text(log_frame, wrap=tk.WORD, height=5)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.progress = ttk.Progressbar(main_frame, mode="determinate")
        self.progress.pack(fill=tk.X, **padding)

    def _setup_jellyfin_tab(self, parent):
        padding = {"padx": 10, "pady": 5}

        # 数据库选择区域
        db_frame = ttk.LabelFrame(parent, text="数据库文件", padding=5)
        db_frame.pack(fill=tk.X, **padding)

        old_db_row = ttk.Frame(db_frame)
        old_db_row.pack(fill=tk.X, pady=2)
        ttk.Label(old_db_row, text="旧数据库 (MP4):", width=16).pack(side=tk.LEFT)
        ttk.Entry(old_db_row, textvariable=self.old_db_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(old_db_row, text="选择文件", command=self._select_old_db).pack(side=tk.LEFT)

        new_db_row = ttk.Frame(db_frame)
        new_db_row.pack(fill=tk.X, pady=2)
        ttk.Label(new_db_row, text="新数据库 (STRM):", width=16).pack(side=tk.LEFT)
        ttk.Entry(new_db_row, textvariable=self.new_db_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(new_db_row, text="选择文件", command=self._select_new_db).pack(side=tk.LEFT)

        # 操作按钮
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, **padding)
        ttk.Button(btn_frame, text="读取数据库", command=self._read_databases).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="执行迁移", command=self._execute_migration).pack(side=tk.LEFT, padx=5)

        # 映射结果
        results_frame = ttk.LabelFrame(parent, text="映射结果", padding=5)
        results_frame.pack(fill=tk.BOTH, expand=True, **padding)

        self.jellyfin_result_label = ttk.Label(results_frame, text="请选择数据库文件后点击「读取数据库」")
        self.jellyfin_result_label.pack(anchor=tk.W, pady=(0, 5))

        tree_container = ttk.Frame(results_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)

        columns = ("code", "old_path", "new_path", "favorite", "played", "play_count", "position", "status")
        self.jellyfin_tree = ttk.Treeview(tree_container, columns=columns, show="headings", selectmode="extended")

        headers = {
            "code": ("番号", 100),
            "old_path": ("旧路径", 250),
            "new_path": ("新路径", 250),
            "favorite": ("收藏", 50),
            "played": ("已观看", 50),
            "play_count": ("播放次数", 70),
            "position": ("播放进度", 80),
            "status": ("状态", 80),
        }
        for col, (text, width) in headers.items():
            self.jellyfin_tree.heading(col, text=text)
            self.jellyfin_tree.column(col, width=width, anchor=tk.W)

        scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.jellyfin_tree.yview)
        self.jellyfin_tree.configure(yscrollcommand=scrollbar.set)
        self.jellyfin_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 路径列悬浮提示
        self._jellyfin_tooltip = ToolTip(self.jellyfin_tree)
        self._jellyfin_tooltip_path_cols = {"old_path", "new_path"}
        self.jellyfin_tree.bind("<Motion>", self._on_jellyfin_tree_motion)
        self.jellyfin_tree.bind("<Leave>", lambda e: self._jellyfin_tooltip.hide())

    def _on_jellyfin_tree_motion(self, event):
        region = self.jellyfin_tree.identify("region", event.x, event.y)
        if region != "cell":
            self._jellyfin_tooltip.hide()
            return
        col = self.jellyfin_tree.identify_column(event.x)
        col_id = self.jellyfin_tree["columns"][int(col[1:]) - 1]
        if col_id not in self._jellyfin_tooltip_path_cols:
            self._jellyfin_tooltip.hide()
            return
        item_id = self.jellyfin_tree.identify_row(event.y)
        if not item_id:
            self._jellyfin_tooltip.hide()
            return
        values = self.jellyfin_tree.item(item_id, "values")
        col_index = list(self.jellyfin_tree["columns"]).index(col_id)
        text = values[col_index] if col_index < len(values) else ""
        if text:
            self._jellyfin_tooltip.show(text, event.x_root, event.y_root)
        else:
            self._jellyfin_tooltip.hide()

    def _select_old_db(self):
        path = filedialog.askopenfilename(
            title="选择旧数据库文件",
            filetypes=[("SQLite 数据库", "*.db"), ("所有文件", "*.*")]
        )
        if path:
            self.old_db_path.set(path)

    def _select_new_db(self):
        path = filedialog.askopenfilename(
            title="选择新数据库文件",
            filetypes=[("SQLite 数据库", "*.db"), ("所有文件", "*.*")]
        )
        if path:
            self.new_db_path.set(path)

    def _read_databases(self):
        old_path = self.old_db_path.get().strip()
        new_path = self.new_db_path.get().strip()
        if not old_path or not new_path:
            messagebox.showwarning("提示", "请先选择旧数据库和新数据库文件")
            return
        if not os.path.exists(old_path):
            messagebox.showerror("错误", f"旧数据库文件不存在: {old_path}")
            return
        if not os.path.exists(new_path):
            messagebox.showerror("错误", f"新数据库文件不存在: {new_path}")
            return

        if self.current_thread and self.current_thread.is_alive():
            messagebox.showwarning("提示", "有操作正在进行，请等待完成")
            return

        self.progress["mode"] = "determinate"
        self.progress["value"] = 0
        self.jellyfin_result_label.config(text="正在读取数据库...")
        self.jellyfin_tree.delete(*self.jellyfin_tree.get_children())
        self.mapping_data = []

        def make_callback():
            def cb(info):
                if isinstance(info, tuple):
                    current, total, msg = info
                    if total > 0:
                        pct = int(current / total * 100)
                        self.root.after(0, lambda p=pct: self.progress.configure(value=p))
                    self.root.after(0, lambda m=msg: self.jellyfin_result_label.config(text=m))
                else:
                    self.root.after(0, lambda: self.jellyfin_result_label.config(text=str(info)))
            return cb

        def task():
            try:
                self.jellyfin_migrator = JellyfinMigrator()

                old_data = self.jellyfin_migrator.read_old_db(old_path, make_callback())
                new_data = self.jellyfin_migrator.read_new_db(new_path, make_callback())
                mapping = self.jellyfin_migrator.build_mapping(old_data, new_data)

                self.root.after(0, lambda: self._display_mapping(mapping))
            except Exception as e:
                logger.error("读取数据库失败: %s", e)
                self.root.after(0, lambda: messagebox.showerror("错误", f"读取数据库失败: {e}"))
                self.root.after(0, lambda: self.jellyfin_result_label.config(text="读取失败"))
            finally:
                self.root.after(0, lambda: self.progress.configure(value=100))

        self.current_thread = threading.Thread(target=task, daemon=True)
        self.current_thread.start()

    def _display_mapping(self, mapping):
        self.mapping_data = mapping
        self.jellyfin_tree.delete(*self.jellyfin_tree.get_children())

        for item in mapping:
            ud = item.get("user_data") or {}
            status_text = {"matched": "可迁移", "old_only": "仅旧库", "new_only": "仅新库"}.get(item["status"], item["status"])

            self.jellyfin_tree.insert("", tk.END, values=(
                item["code"],
                item.get("old_path") or "",
                item.get("new_path") or "",
                "是" if ud.get("IsFavorite") else "",
                "是" if ud.get("Played") else "",
                ud.get("PlayCount") or 0,
                ud.get("PlaybackPositionTicks") or 0,
                status_text,
            ))

        matched = sum(1 for m in mapping if m["status"] == "matched")
        old_only = sum(1 for m in mapping if m["status"] == "old_only")
        new_only = sum(1 for m in mapping if m["status"] == "new_only")
        self.jellyfin_result_label.config(
            text=f"读取完成: {matched} 条可迁移, {old_only} 条仅旧库, {new_only} 条仅新库"
        )

    def _execute_migration(self):
        if not self.mapping_data:
            messagebox.showwarning("提示", "请先读取数据库")
            return

        matched = [m for m in self.mapping_data if m["status"] == "matched"]
        if not matched:
            messagebox.showwarning("提示", "没有可迁移的匹配记录")
            return

        new_path = self.new_db_path.get().strip()
        if not messagebox.askyesno("确认迁移", f"即将向新数据库写入 {len(matched)} 条 UserData 记录。\n\n请确保已备份数据库文件: {new_path}\n\n是否继续?"):
            return

        if self.current_thread and self.current_thread.is_alive():
            messagebox.showwarning("提示", "有操作正在进行，请等待完成")
            return

        self.progress["mode"] = "determinate"
        self.progress["value"] = 0
        self.jellyfin_result_label.config(text="正在执行迁移...")

        def make_callback():
            def cb(info):
                if isinstance(info, tuple):
                    current, total, msg = info
                    if total > 0:
                        pct = int(current / total * 100)
                        self.root.after(0, lambda p=pct: self.progress.configure(value=p))
                    self.root.after(0, lambda m=msg: self.jellyfin_result_label.config(text=m))
                else:
                    self.root.after(0, lambda: self.jellyfin_result_label.config(text=str(info)))
            return cb

        def task():
            try:
                migrated = self.jellyfin_migrator.migrate_userdata(
                    new_path, self.mapping_data, make_callback()
                )
                self.root.after(0, lambda: messagebox.showinfo("完成", f"迁移完成: 成功 {migrated} 条"))
            except Exception as e:
                logger.error("迁移失败: %s", e)
                self.root.after(0, lambda: messagebox.showerror("错误", f"迁移失败: {e}"))
            finally:
                self.root.after(0, lambda: self.progress.configure(value=100))

        self.current_thread = threading.Thread(target=task, daemon=True)
        self.current_thread.start()

    def _select_directory(self):
        path = filedialog.askdirectory(title="选择视频目录")
        if path:
            self.target_dir.set(path)

    def _select_strm_target(self):
        path = filedialog.askdirectory(title="选择视频移动目标文件夹")
        if path:
            self.strm_target.set(path)

    def _start_operation(self):
        if self.current_thread and self.current_thread.is_alive():
            return False

        self.progress.configure(mode="indeterminate")
        self.progress.start(50)
        self.tree.delete(*self.tree.get_children())
        self.tree.column("new_name", width=0, stretch=False)
        self.tree.heading("new_name", text="新文件名")
        self.current_mode = None
        self.scanned_data = []
        return True

    def _end_operation(self):
        self.progress.stop()
        self.progress.configure(mode="determinate", value=100)

    def _scan_empty_folders(self):
        if not self.target_dir.get():
            logger.warning("请先选择目标目录")
            return

        if not self._start_operation():
            return

        def progress_callback(message: str, current: int, total: int):
            self.root.after(0, lambda: self.result_label.config(text=message))

        def worker():
            try:
                self.cleaner = VideoCleaner(progress_callback=progress_callback)
                self.root.after(0, lambda: self.result_label.config(text="正在扫描空文件夹..."))
                logger.info("开始扫描空文件夹: %s", self.target_dir.get())

                empty_folders = self.cleaner.find_empty_folders(self.target_dir.get())

                self.root.after(0, lambda: self._display_empty_folders(empty_folders))
            except Exception as e:
                logger.error("扫描空文件夹失败: %s", e)
                self.root.after(0, self._end_operation)

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.current_thread.start()

    def _display_empty_folders(self, empty_folders: List[str]):
        self._end_operation()

        self.current_mode = "empty_folders"
        self.scanned_data = empty_folders

        if not empty_folders:
            self.result_label.config(text="未发现空文件夹")
        else:
            self.result_label.config(text=f"发现 {len(empty_folders)} 个空文件夹")
            for folder in empty_folders:
                self.tree.insert("", tk.END, values=(folder,), tags=(folder,))

        logger.info("扫描完成，发现 %d 个空文件夹", len(empty_folders))

    def _find_duplicates(self):
        if not self.target_dir.get():
            logger.warning("请先选择目标目录")
            return

        if not self._start_operation():
            return

        def progress_callback(message: str, current: int, total: int):
            self.root.after(0, lambda: self.result_label.config(text=message))

        def worker():
            try:
                self.cleaner = VideoCleaner(progress_callback=progress_callback)
                self.root.after(0, lambda: self.result_label.config(text="正在扫描重复视频..."))
                logger.info("开始扫描重复视频: %s", self.target_dir.get())

                duplicates = self.cleaner.find_duplicate_videos(self.target_dir.get())

                self.root.after(0, lambda: self._display_duplicates(duplicates))
            except Exception as e:
                logger.error("扫描重复视频失败: %s", e)
                self.root.after(0, self._end_operation)

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.current_thread.start()

    def _display_duplicates(self, duplicates: Dict[str, List[str]]):
        self._end_operation()

        self.current_mode = "duplicates"
        self.scanned_data = []

        if not duplicates:
            self.result_label.config(text="未发现重复的视频文件")
        else:
            total_files = sum(len(files) for files in duplicates.values())
            self.result_label.config(text=f"发现 {len(duplicates)} 组重复视频，共 {total_files} 个文件")

            for code, files in sorted(duplicates.items()):
                self.tree.insert("", tk.END, values=(f"[{code}] {len(files)} 个文件",), tags=(code,))
                for file_path in files:
                    self.tree.insert("", tk.END, values=(f"  {file_path}",), tags=(file_path,))
                    self.scanned_data.append(file_path)

        logger.info("扫描完成，发现 %d 组重复视频", len(duplicates))

    def _rename_videos(self):
        if not self.target_dir.get():
            logger.warning("请先选择目标目录")
            return

        if not self._start_operation():
            return

        def progress_callback(message: str, current: int, total: int):
            self.root.after(0, lambda: self.result_label.config(text=message))

        def worker():
            try:
                self.cleaner = VideoCleaner(progress_callback=progress_callback)
                self.root.after(0, lambda: self.result_label.config(text="正在扫描需要重命名的视频..."))
                logger.info("开始扫描需要重命名的视频: %s", self.target_dir.get())

                files_to_rename = self.cleaner.scan_videos_to_rename(self.target_dir.get())

                self.root.after(0, lambda: self._display_rename_preview(files_to_rename))
            except Exception as e:
                logger.error("扫描重命名失败: %s", e)
                self.root.after(0, self._end_operation)

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.current_thread.start()

    def _display_rename_preview(self, files_to_rename: List[Dict]):
        self._end_operation()

        self.current_mode = "rename"
        self.scanned_data = files_to_rename

        # 显示第二列
        self.tree.column("new_name", width=300, stretch=True)

        if not files_to_rename:
            self.result_label.config(text="没有需要重命名的视频")
        else:
            self.result_label.config(text=f"发现 {len(files_to_rename)} 个需要重命名的视频")
            for item in files_to_rename:
                self.tree.insert("", tk.END, values=(item["old_name"], item["new_name"]), tags=(item["old_path"],))

        logger.info("扫描完成，发现 %d 个需要重命名的视频", len(files_to_rename))

    def _execute_rename(self):
        if not self.scanned_data or self.current_mode != "rename":
            return

        selected_old_paths = self._get_selected_paths()
        if not selected_old_paths:
            messagebox.showinfo("提示", "请先选择要重命名的项")
            return

        files_to_rename = [item for item in self.scanned_data if item["old_path"] in selected_old_paths]

        confirm = messagebox.askyesno(
            "确认重命名",
            f"确定要重命名 {len(files_to_rename)} 个视频文件吗？"
        )
        if not confirm:
            return

        def worker():
            try:
                renamed = self.cleaner.rename_videos(files_to_rename, dry_run=False)
                self.root.after(0, lambda: self._refresh_rename_tree(renamed))
                logger.info("重命名完成，共重命名 %d 个文件", len(renamed))
            except Exception as e:
                logger.error("重命名错误: %s", e)

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.current_thread.start()

    def _refresh_rename_tree(self, renamed: List[Dict]):
        renamed_paths = {item["old_path"] for item in renamed}
        for item_id in self.tree.get_children():
            tags = self.tree.item(item_id)["tags"]
            if tags and tags[0] in renamed_paths:
                self.tree.delete(item_id)
        self.result_label.config(text=f"已重命名 {len(renamed)} 个文件")

    def _scan_strm(self):
        if not self.target_dir.get():
            logger.warning("请先选择目标目录")
            return

        prefix = self.strm_prefix.get()
        if not prefix or prefix == "输入路径前缀，如 http://example.com/":
            messagebox.showwarning("提示", "请先输入路径前缀")
            return

        if not self._start_operation():
            return

        def progress_callback(message: str, current: int, total: int):
            self.root.after(0, lambda: self.result_label.config(text=message))

        target = self.strm_target.get()

        def worker():
            try:
                self.cleaner = VideoCleaner(progress_callback=progress_callback)
                self.root.after(0, lambda: self.result_label.config(text="正在扫描视频用于生成STRM..."))
                logger.info("开始扫描视频用于生成STRM: %s, 目标: %s", self.target_dir.get(), target)

                items = self.cleaner.scan_videos_for_strm(self.target_dir.get(), prefix, target)

                self.root.after(0, lambda: self._display_strm_preview(items))
            except Exception as e:
                logger.error("扫描STRM失败: %s", e)
                self.root.after(0, self._end_operation)

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.current_thread.start()

    def _display_strm_preview(self, items: List[Dict]):
        self._end_operation()

        self.current_mode = "strm"
        self.scanned_data = items

        self.tree.column("new_name", width=300, stretch=True)
        self.tree.heading("new_name", text="STRM内容")

        if not items:
            self.result_label.config(text="没有找到视频文件")
        else:
            self.result_label.config(text=f"发现 {len(items)} 个视频可生成STRM")
            for item in items:
                self.tree.insert("", tk.END, values=(item["video_name"], item["content"]), tags=(item["video_path"],))

        logger.info("扫描完成，发现 %d 个视频可生成STRM", len(items))

    def _execute_strm(self):
        if not self.scanned_data or self.current_mode != "strm":
            return

        selected_paths = self._get_selected_paths()
        if not selected_paths:
            messagebox.showinfo("提示", "请先选择要生成STRM的项")
            return

        items = [item for item in self.scanned_data if item["video_path"] in selected_paths]

        move_video = bool(self.strm_target.get())
        msg = f"确定要为 {len(items)} 个视频生成 .strm 文件吗？"
        if move_video:
            msg += f"\n\n生成后视频将移动到：{self.strm_target.get()}"

        confirm = messagebox.askyesno("确认生成STRM", msg)
        if not confirm:
            return

        def worker():
            try:
                generated = self.cleaner.generate_strm_files(items, dry_run=False, move_video=move_video)
                self.root.after(0, lambda: self._refresh_strm_tree(generated))
                logger.info("STRM生成完成，共 %d 个文件", len(generated))
            except Exception as e:
                logger.error("STRM生成错误: %s", e)

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.current_thread.start()

    def _refresh_strm_tree(self, generated: List[Dict]):
        generated_paths = {item["video_path"] for item in generated}
        for item_id in self.tree.get_children():
            tags = self.tree.item(item_id)["tags"]
            if tags and tags[0] in generated_paths:
                self.tree.delete(item_id)
        self.result_label.config(text=f"已生成 {len(generated)} 个STRM文件")

    def _get_selected_paths(self) -> List[str]:
        """获取选中项的路径。"""
        selected_paths = []
        for item_id in self.tree.selection():
            tags = self.tree.item(item_id)["tags"]
            if not tags:
                continue
            tag = tags[0]
            if self.current_mode == "empty_folders":
                selected_paths.append(tag)
            elif self.current_mode in ("duplicates", "rename", "strm"):
                # 文件路径是绝对路径，分组标题（如 ABC-123）不是
                if os.path.isabs(tag):
                    selected_paths.append(tag)
        return selected_paths

    def _open_folder(self, path: str):
        system = platform.system()
        try:
            if system == "Windows":
                if os.path.isdir(path):
                    subprocess.run(f'explorer "{path}"', shell=True, check=True)
                else:
                    subprocess.run(f'explorer /select,"{path}"', shell=True, check=True)
            elif system == "Darwin":
                subprocess.run(["open", "-R", path], check=True)
            else:
                subprocess.run(["xdg-open", path], check=True)
        except Exception as e:
            logger.error("无法打开文件夹: %s", e)

    def _open_selected_folders(self):
        selected = self._get_selected_paths()
        if not selected:
            messagebox.showinfo("提示", "请先选择要打开的项")
            return

        for path in selected:
            self._open_folder(path)

    def _delete_selected(self):
        if self.current_thread and self.current_thread.is_alive():
            return

        selected = self._get_selected_paths()
        if not selected:
            messagebox.showinfo("提示", "请先选择要删除的项")
            return

        if self.current_mode != "empty_folders":
            messagebox.showwarning("警告", "重复视频列表暂不支持直接删除")
            return

        confirm = messagebox.askyesno(
            "确认删除",
            f"确定要删除 {len(selected)} 个空文件夹吗？\n\n此操作不可撤销！"
        )
        if not confirm:
            return

        def worker():
            try:
                deleted = []
                for folder in selected:
                    try:
                        os.rmdir(folder)
                        deleted.append(folder)
                        logger.info("已删除: %s", folder)
                    except OSError as e:
                        logger.warning("删除失败 %s: %s", folder, e)

                self.root.after(0, lambda: self._refresh_tree())
                logger.info("删除完成，共删除 %d 个文件夹", len(deleted))
            except Exception as e:
                logger.error("删除错误: %s", e)

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.current_thread.start()

    def _refresh_tree(self):
        # 删除选中项
        for item_id in self.tree.selection():
            self.tree.delete(item_id)

        # 清理空的分组标题（重复视频模式下，子项全部删除后残留的标题行）
        if self.current_mode == "duplicates":
            for item_id in self.tree.get_children():
                if not self.tree.get_children(item_id):
                    tags = self.tree.item(item_id)["tags"]
                    if tags and not os.path.isabs(tags[0]):
                        self.tree.delete(item_id)

    def _on_item_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            values = self.tree.item(item_id)["values"]
            if values and values[0]:
                path = values[0].strip()
                if path:
                    self._open_folder(path)

    def _on_right_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)

            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label="打开所在文件夹", command=lambda: self._on_item_double_click(event))
            if self.current_mode == "empty_folders":
                menu.add_command(label="删除", command=self._delete_selected)
            elif self.current_mode == "rename":
                menu.add_command(label="重命名", command=self._execute_rename)
            elif self.current_mode == "strm":
                menu.add_command(label="生成STRM", command=self._execute_strm)

            menu.post(event.x_root, event.y_root)

    def _select_all(self):
        children = self.tree.get_children()
        self.tree.selection_set(children)

    def _clear_selection(self):
        self.tree.selection_remove(self.tree.selection())


def main():
    root = tk.Tk()
    app = VideoCleanerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
