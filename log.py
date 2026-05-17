"""日志配置模块"""

import logging
import tkinter as tk
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILENAME = "media_cleaner.log"


class GUIHandler(logging.Handler):
    """将日志写入 tkinter Text 控件的 handler，线程安全"""

    def __init__(self, root: tk.Tk, text_widget: tk.Text):
        super().__init__()
        self.root = root
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        self.root.after(0, self._append, msg)

    def _append(self, msg: str):
        self.text_widget.insert(tk.END, msg + "\n")
        self.text_widget.see(tk.END)


def setup_logging(root: tk.Tk, log_text_widget: tk.Text, level: int = logging.DEBUG):
    """初始化日志系统

    Args:
        root: tkinter 根窗口
        log_text_widget: 用于显示日志的 tk.Text 控件
        level: 日志级别
    """
    logger = logging.getLogger("media_cleaner")
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # 文件 handler
    log_file = Path.cwd() / LOG_FILENAME
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # GUI handler
    gui_handler = GUIHandler(root, log_text_widget)
    gui_handler.setLevel(level)
    gui_handler.setFormatter(formatter)
    logger.addHandler(gui_handler)


def get_logger(name: str) -> logging.Logger:
    """获取子 logger"""
    return logging.getLogger(f"media_cleaner.{name}")
