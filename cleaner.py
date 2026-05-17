"""清理逻辑模块"""

import os
import shutil
from pathlib import Path
from typing import Callable, Dict, List
from extractor import AVCodeExtractor
from log import get_logger

logger = get_logger("cleaner")


class VideoCleaner:
    VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".mpg", ".mpeg", ".rm", ".rmvb"}

    def __init__(self, progress_callback: Callable[[str, int, int], None] | None = None):
        self.progress_callback = progress_callback
        self.extractor = AVCodeExtractor()

    def find_empty_folders(self, root_path: str) -> List[str]:
        """递归查找所有空文件夹（从最深层开始）"""
        logger.info("开始扫描空文件夹: %s", root_path)
        empty_folders = []
        root = Path(root_path)

        processed = 0

        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            current_path = Path(dirpath)
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]

            processed += 1
            if self.progress_callback and processed % 50 == 0:
                self.progress_callback(f"已扫描 {processed} 个目录，发现 {len(empty_folders)} 个空文件夹", processed, 0)

            is_empty = not filenames and not dirnames
            if is_empty:
                empty_folders.append(str(current_path))

        if self.progress_callback:
            self.progress_callback(f"扫描完成，共扫描 {processed} 个目录", processed, processed)

        logger.info("扫描完成，共扫描 %d 个目录，发现 %d 个空文件夹", processed, len(empty_folders))
        return empty_folders

    def delete_empty_folders(self, empty_folders: List[str], dry_run: bool = True) -> List[str]:
        """删除空文件夹

        Returns:
            实际删除的文件夹列表
        """
        logger.info("删除空文件夹: dry_run=%s, 数量=%d", dry_run, len(empty_folders))
        deleted = []
        for folder in empty_folders:
            try:
                if dry_run:
                    deleted.append(folder)
                else:
                    os.rmdir(folder)
                    deleted.append(folder)
                    logger.info("已删除: %s", folder)
            except OSError as e:
                logger.warning("删除失败 %s: %s", folder, e)

        logger.info("删除完成，共删除 %d 个文件夹", len(deleted))
        return deleted

    def find_duplicate_videos(self, root_path: str) -> Dict[str, List[str]]:
        """基于AV番号查找重复视频

        Returns:
            {av_code: [file_path1, file_path2, ...]}
            只返回有重复的番号
        """
        logger.info("开始扫描重复视频: %s", root_path)
        av_files: Dict[str, List[str]] = {}
        root = Path(root_path)

        processed = 0
        video_count = 0

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue

            # 跳过隐藏目录中的文件
            if any(part.startswith(".") for part in file_path.relative_to(root).parts):
                continue

            processed += 1
            if self.progress_callback and processed % 200 == 0:
                self.progress_callback(f"已扫描 {processed} 个文件，发现 {video_count} 个视频", processed, 0)

            if file_path.suffix.lower() not in self.VIDEO_EXTENSIONS:
                continue

            video_count += 1
            av_code = self.extractor.extract(file_path.name)
            if av_code:
                av_code = av_code.upper()
                if av_code not in av_files:
                    av_files[av_code] = []
                av_files[av_code].append(str(file_path))

        if self.progress_callback:
            self.progress_callback(f"扫描完成，共扫描 {processed} 个文件", processed, processed)

        duplicates = {code: paths for code, paths in av_files.items() if len(paths) > 1}
        logger.info("扫描完成，共扫描 %d 个文件，发现 %d 个视频，%d 组重复", processed, video_count, len(duplicates))
        return duplicates

    def scan_videos_to_rename(self, root_path: str) -> List[Dict]:
        """扫描需要重命名的视频文件

        Returns:
            [{"old_path": ..., "new_path": ..., "old_name": ..., "new_name": ...}, ...]
        """
        logger.info("开始扫描需要重命名的视频: %s", root_path)
        root = Path(root_path)
        results = []
        processed = 0

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if any(part.startswith(".") for part in file_path.relative_to(root).parts):
                continue
            if file_path.suffix.lower() not in self.VIDEO_EXTENSIONS:
                continue

            processed += 1
            if self.progress_callback and processed % 200 == 0:
                self.progress_callback(f"已扫描 {processed} 个视频，发现 {len(results)} 个需要重命名", processed, 0)

            new_name = self.extractor.clean_filename(file_path.name)
            if new_name and new_name != file_path.name:
                new_path = file_path.parent / new_name
                results.append({
                    "old_path": str(file_path),
                    "new_path": str(new_path),
                    "old_name": file_path.name,
                    "new_name": new_name,
                })

        if self.progress_callback:
            self.progress_callback(f"扫描完成，共扫描 {processed} 个视频", processed, processed)

        logger.info("扫描完成，共扫描 %d 个视频，%d 个需要重命名", processed, len(results))
        return results

    def rename_videos(self, files_to_rename: List[Dict], dry_run: bool = True) -> List[Dict]:
        """执行视频重命名

        Args:
            files_to_rename: scan_videos_to_rename 返回的列表
            dry_run: True 时只记录不执行

        Returns:
            实际重命名的列表
        """
        logger.info("重命名视频: dry_run=%s, 数量=%d", dry_run, len(files_to_rename))
        renamed = []
        for item in files_to_rename:
            try:
                if dry_run:
                    renamed.append(item)
                else:
                    os.rename(item["old_path"], item["new_path"])
                    renamed.append(item)
                    logger.info("已重命名: %s -> %s", item["old_name"], item["new_name"])
            except OSError as e:
                logger.warning("重命名失败 %s: %s", item["old_name"], e)

        logger.info("重命名完成，共 %d 个", len(renamed))
        return renamed

    def scan_videos_for_strm(self, root_path: str, prefix: str, target_path: str = "") -> List[Dict]:
        """扫描视频文件，预览将要生成的 .strm 文件

        Args:
            root_path: 扫描根目录
            prefix: .strm 文件内容前缀
            target_path: 视频移动目标文件夹（为空则不移动）

        Returns:
            [{"video_path": ..., "strm_path": ..., "video_name": ..., "strm_name": ..., "content": ..., "move_to": ...}, ...]
        """
        logger.info("开始扫描视频用于生成STRM: %s, 前缀: %s, 目标: %s", root_path, prefix, target_path)
        root = Path(root_path)
        target = Path(target_path) if target_path else None
        results = []
        processed = 0

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if any(part.startswith(".") for part in file_path.relative_to(root).parts):
                continue
            if file_path.suffix.lower() not in self.VIDEO_EXTENSIONS:
                continue

            processed += 1
            if self.progress_callback and processed % 200 == 0:
                self.progress_callback(f"已扫描 {processed} 个视频，发现 {len(results)} 个可生成STRM", processed, 0)

            strm_path = file_path.with_suffix(".strm")
            strm_name = file_path.stem + ".strm"
            content = prefix + file_path.name

            relative = file_path.relative_to(root)
            move_to = str(target / relative) if target else ""

            results.append({
                "video_path": str(file_path),
                "strm_path": str(strm_path),
                "video_name": file_path.name,
                "strm_name": strm_name,
                "content": content,
                "move_to": move_to,
            })

        if self.progress_callback:
            self.progress_callback(f"扫描完成，共扫描 {processed} 个视频", processed, processed)

        logger.info("扫描完成，共扫描 %d 个视频，%d 个可生成STRM", processed, len(results))
        return results

    def generate_strm_files(self, items: List[Dict], dry_run: bool = True, move_video: bool = False) -> List[Dict]:
        """执行 .strm 文件生成，可选移动视频文件

        Args:
            items: scan_videos_for_strm 返回的列表
            dry_run: True 时只记录不执行
            move_video: True 时生成 .strm 后将视频移动到 move_to 路径

        Returns:
            实际生成的列表
        """
        logger.info("生成STRM文件: dry_run=%s, move_video=%s, 数量=%d", dry_run, move_video, len(items))
        generated = []
        for item in items:
            try:
                if dry_run:
                    generated.append(item)
                else:
                    Path(item["strm_path"]).write_text(item["content"], encoding="utf-8")
                    logger.info("已生成STRM: %s -> %s", item["strm_name"], item["content"])

                    if move_video and item.get("move_to"):
                        dest = Path(item["move_to"])
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(item["video_path"], str(dest))
                        logger.info("已移动视频: %s -> %s", item["video_name"], item["move_to"])

                    generated.append(item)
            except OSError as e:
                logger.warning("处理失败 %s: %s", item["video_name"], e)

        logger.info("STRM生成完成，共 %d 个", len(generated))
        return generated

    def get_total_folders(self, root_path: str) -> int:
        """获取获取总文件夹数"""
        return sum(1 for _ in Path(root_path).rglob("*") if _.is_dir())
