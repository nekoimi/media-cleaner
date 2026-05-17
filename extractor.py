"""AV番号提取模块"""

import re
from pathlib import Path
from log import get_logger

logger = get_logger("extractor")


class AVCodeExtractor:
    def __init__(self):
        self.patterns = [
            r"\b([A-Z]{2,}-?\d{2,})\b",  # ABC-123 或 ABC123（至少2字母+2数字）
            r"\b(\d{2,}[A-Z]{2,}-\d{2,})\b",  # 123ABC-456
        ]

    def extract(self, filename: str) -> str | None:
        """从文件名提取AV番号

        Args:
            filename: 文件名（不含路径）

        Returns:
            提取的AV番号，如果没有匹配则返回None
        """
        stem = Path(filename).stem
        stem = stem.upper()

        cleaned = self._remove_website_prefix(stem)
        cleaned = self._remove_suffix(cleaned)

        for pattern in self.patterns:
            match = re.search(pattern, cleaned)
            if match:
                logger.debug("从 %s 提取到番号: %s (清理后: %s)", filename, match.group(1), cleaned)
                return match.group(1)

        logger.debug("从 %s 未提取到番号 (清理后: %s)", filename, cleaned)
        return None

    def _remove_website_prefix(self, text: str) -> str:
        """移除网址前缀"""
        url_patterns = [
            r"^HTTPS?://[^/]+/",  # http://.../ 或 https://.../
            r"^WWW\.",  # www.
        ]
        for pattern in url_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        return text

    def clean_filename(self, filename: str) -> str | None:
        """清理文件名：去域名、去URL、转大写、下划线转中横线

        Args:
            filename: 原始文件名（含扩展名）

        Returns:
            清理后的文件名，如果清理后无效则返回 None
        """
        p = Path(filename)
        stem = p.stem
        ext = p.suffix  # 保留原始扩展名

        # 移除 URL（任意位置）
        stem = re.sub(r"https?://[^\s/_-]+", "", stem, flags=re.IGNORECASE)

        # 移除域名（任意位置）：www.xxx.com / 489155.com@ / 77vr.com@ / site.net- 等
        stem = re.sub(r"www\.[^\s/_@-]+\.[a-z]{2,}", "", stem, flags=re.IGNORECASE)
        stem = re.sub(r"(?<!\w)[a-z0-9]+\.(?:com|net|org|co\.\w+)[@_-]?", "", stem, flags=re.IGNORECASE)

        # 下划线转中横线
        stem = stem.replace("_", "-")

        # 清理连续分隔符和首尾分隔符
        stem = re.sub(r"-{2,}", "-", stem)
        stem = stem.strip("-")

        # 转大写
        stem = stem.upper()

        if not stem:
            return None

        return stem + ext

    def _remove_suffix(self, text: str) -> str:
        """移除常见后缀（仅从末尾移除）"""
        suffixes = [
            "_FHD", "_HD", "_SD",
            "_UNCENSORED", "_UNC",
            "_CARIBBEANCOM", "_HEYZO", "_FC2",
            "_MP4", "_MKV", "_AVI",
        ]
        for suffix in suffixes:
            text = text.removesuffix(suffix)
        return text
