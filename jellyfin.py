"""Jellyfin 数据库迁移模块

基于 AV 番号将旧数据库（MP4）的 UserData 迁移到新数据库（STRM）。
"""

import sqlite3
from extractor import AVCodeExtractor
from log import get_logger

logger = get_logger("jellyfin")

USERDATA_FIELDS = ["IsFavorite", "Played", "PlayCount", "PlaybackPositionTicks", "LastPlayedDate"]


class JellyfinMigrator:
    def __init__(self):
        self.extractor = AVCodeExtractor()

    def _should_skip(self, path: str, name: str) -> bool:
        """判断是否应跳过该条目（Trailer/预告片等）"""
        if not path:
            return True
        path_lower = path.lower()
        name_lower = (name or "").lower()
        if path_lower.endswith("trailer.strm") or path_lower.endswith("trailer.mp4"):
            return True
        if "/trailers/" in path_lower or "\\trailers\\" in path_lower:
            return True
        if "trailer" in name_lower:
            return True
        return False

    def read_old_db(self, db_path: str, progress_callback=None) -> dict:
        """读取旧数据库，提取番号与 UserData

        Returns:
            dict[code] = {old_item_id, path, user_data: {IsFavorite, Played, ...}}
        """
        if progress_callback:
            progress_callback((0, 0, "正在读取旧数据库..."))

        result = {}
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            sql = """
                SELECT b.Id, b.Path, b.Name,
                       u.UserId, u.CustomDataKey, u.IsFavorite, u.Played, u.PlayCount,
                       u.PlaybackPositionTicks, u.LastPlayedDate
                FROM BaseItems b
                JOIN UserData u ON b.Id = u.ItemId
            """
            rows = conn.execute(sql).fetchall()
            total = len(rows)
            skipped = 0

            for i, row in enumerate(rows):
                path = row["Path"] or ""
                name = row["Name"] or ""

                if self._should_skip(path, name):
                    skipped += 1
                    continue

                code = self.extractor.extract(path)
                if not code:
                    skipped += 1
                    continue

                user_data = {field: row[field] for field in USERDATA_FIELDS}
                user_data["UserId"] = row["UserId"]
                user_data["CustomDataKey"] = row["CustomDataKey"]
                result[code] = {
                    "old_item_id": row["Id"],
                    "path": path,
                    "user_data": user_data,
                }

                if progress_callback and (i + 1) % 50 == 0:
                    progress_callback((i + 1, total, f"旧数据库: 已处理 {i + 1}/{total}"))

            if progress_callback:
                progress_callback((total, total, f"旧数据库读取完成: {len(result)} 条有效记录, {skipped} 条已跳过"))
            logger.info("旧数据库读取完成: %d 条有效, %d 条跳过", len(result), skipped)
        finally:
            conn.close()

        return result

    def read_new_db(self, db_path: str, progress_callback=None) -> dict:
        """读取新数据库，提取番号与新 ItemId

        Returns:
            dict[code] = {new_item_id, path}
        """
        if progress_callback:
            progress_callback((0, 0, "正在读取新数据库..."))

        result = {}
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT Id, Path, Name FROM BaseItems").fetchall()
            total = len(rows)
            skipped = 0

            for i, row in enumerate(rows):
                path = row["Path"] or ""
                name = row["Name"] or ""

                if self._should_skip(path, name):
                    skipped += 1
                    continue

                code = self.extractor.extract(path)
                if not code:
                    skipped += 1
                    continue

                result[code] = {
                    "new_item_id": row["Id"],
                    "path": path,
                }

                if progress_callback and (i + 1) % 50 == 0:
                    progress_callback((i + 1, total, f"新数据库: 已处理 {i + 1}/{total}"))

            if progress_callback:
                progress_callback((total, total, f"新数据库读取完成: {len(result)} 条有效记录, {skipped} 条已跳过"))
            logger.info("新数据库读取完成: %d 条有效, %d 条跳过", len(result), skipped)
        finally:
            conn.close()

        return result

    def build_mapping(self, old_data: dict, new_data: dict) -> list:
        """按番号建立映射关系

        Returns:
            list of dict: [{code, old_item_id, new_item_id, old_path, new_path, user_data, status}]
            status: "matched" | "old_only" | "new_only"
        """
        mapping = []
        all_codes = set(old_data.keys()) | set(new_data.keys())

        for code in sorted(all_codes):
            old = old_data.get(code)
            new = new_data.get(code)

            if old and new:
                mapping.append({
                    "code": code,
                    "old_item_id": old["old_item_id"],
                    "new_item_id": new["new_item_id"],
                    "old_path": old["path"],
                    "new_path": new["path"],
                    "user_data": old["user_data"],
                    "status": "matched",
                })
            elif old:
                mapping.append({
                    "code": code,
                    "old_item_id": old["old_item_id"],
                    "new_item_id": None,
                    "old_path": old["path"],
                    "new_path": None,
                    "user_data": old["user_data"],
                    "status": "old_only",
                })
            else:
                mapping.append({
                    "code": code,
                    "old_item_id": None,
                    "new_item_id": new["new_item_id"],
                    "old_path": None,
                    "new_path": new["path"],
                    "user_data": None,
                    "status": "new_only",
                })

        matched = sum(1 for m in mapping if m["status"] == "matched")
        old_only = sum(1 for m in mapping if m["status"] == "old_only")
        new_only = sum(1 for m in mapping if m["status"] == "new_only")
        logger.info("映射构建完成: %d 匹配, %d 仅旧库, %d 仅新库", matched, old_only, new_only)

        return mapping

    def migrate_userdata(self, db_path: str, mapping: list, progress_callback=None) -> int:
        """执行 UserData 迁移，直接修改新数据库

        Returns:
            成功迁移的记录数
        """
        matched = [m for m in mapping if m["status"] == "matched"]
        if not matched:
            if progress_callback:
                progress_callback((0, 0, "没有可迁移的匹配记录"))
            return 0

        total = len(matched)
        if progress_callback:
            progress_callback((0, total, f"开始迁移 {total} 条记录..."))

        conn = sqlite3.connect(db_path)
        migrated = 0
        skipped = 0
        try:
            for i, item in enumerate(matched):
                new_item_id = item["new_item_id"]
                user_data = item["user_data"]
                user_id = user_data.get("UserId")

                if not user_id:
                    logger.warning("跳过 %s: 缺少 UserId", item["code"])
                    skipped += 1
                    continue

                # 检查新库中是否已有该记录
                existing = conn.execute(
                    "SELECT 1 FROM UserData WHERE ItemId = ? AND UserId = ?",
                    (new_item_id, user_id)
                ).fetchone()

                if existing:
                    # 已有记录，UPDATE
                    conn.execute(
                        """UPDATE UserData SET
                            IsFavorite = ?,
                            Played = ?,
                            PlayCount = ?,
                            PlaybackPositionTicks = ?,
                            LastPlayedDate = ?
                        WHERE ItemId = ? AND UserId = ?""",
                        (
                            user_data.get("IsFavorite"),
                            user_data.get("Played"),
                            user_data.get("PlayCount"),
                            user_data.get("PlaybackPositionTicks"),
                            user_data.get("LastPlayedDate"),
                            new_item_id,
                            user_id,
                        )
                    )
                    logger.info("已更新 %s (已有 UserData)", item["code"])
                else:
                    # 无记录，INSERT
                    conn.execute(
                        """INSERT INTO UserData
                            (ItemId, UserId, CustomDataKey, IsFavorite, Played, PlayCount,
                             PlaybackPositionTicks, LastPlayedDate)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            new_item_id,
                            user_id,
                            user_data.get("CustomDataKey"),
                            user_data.get("IsFavorite"),
                            user_data.get("Played"),
                            user_data.get("PlayCount"),
                            user_data.get("PlaybackPositionTicks"),
                            user_data.get("LastPlayedDate"),
                        )
                    )
                    logger.info("已插入 %s (新建 UserData)", item["code"])

                migrated += 1
                if progress_callback and (i + 1) % 10 == 0:
                    progress_callback((i + 1, total, f"迁移进度: {i + 1}/{total}"))

            conn.commit()
            if progress_callback:
                progress_callback((total, total, f"迁移完成: 成功 {migrated}/{total} 条, 跳过 {skipped} 条"))
            logger.info("迁移完成: %d/%d 条成功, %d 条跳过", migrated, len(matched), skipped)
        except Exception as e:
            conn.rollback()
            import traceback
            traceback.print_exc()
            logger.error("迁移失败: %s", e)
            raise
        finally:
            conn.close()

        return migrated
