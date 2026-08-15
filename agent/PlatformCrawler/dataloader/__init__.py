"""PlatformCrawler.dataloader：清洗（C1–C8）+ 按 DATASET_SPEC 组装 D_platform。"""

from .builder import build_d_platform, save_d_platform
from .cleaner import clean_records, load_bilibili_comment_csv
from .validate import validate_d_platform

__all__ = [
    "load_bilibili_comment_csv",
    "clean_records",
    "build_d_platform",
    "save_d_platform",
    "validate_d_platform",
]
