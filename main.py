"""GUI主程序"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
import subprocess
import platform
from typing import List, Dict
from cleaner import VideoCleaner
from log import setup_logging, get_logger

logger = get_logger("main")


class VideoCleanerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("媒体文件清理工具")
        self.root.geometry("900x700")
        self.root.resizable(True, True)

        self.target_dir = tk.StringVar()
        self.strm_prefix = tk.StringVar()
        self.strm_target = tk.StringVar()
        self.cleaner = None
        self.current_thread = None

        self.current_mode = None  # "empty_folders", "duplicates", "rename", "strm"
        self.scanned_data = []  # 存储当前扫描的数据
        self.selected_items = set()  # 选中的项

        self._setup_ui()
        setup_logging(self.root, self.log_text)

    def _setup_ui(self):
        padding = {"padx": 10, "pady": 5}

        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="目标目录:").pack(anchor=tk.W, **padding)

        dir_frame = ttk.Frame(main_frame)
        dir_frame.pack(fill=tk.X, **padding)

        dir_entry = ttk.Entry(dir_frame, textvariable=self.target_dir)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(dir_frame, text="选择目录", command=self._select_directory).pack(side=tk.LEFT, padx=5)

        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        actions_frame = ttk.LabelFrame(main_frame, text="操作", padding=5)
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

        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        results_frame = ttk.LabelFrame(main_frame, text="扫描结果", padding=5)
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
