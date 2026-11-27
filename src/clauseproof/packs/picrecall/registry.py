"""随包数据装配面（器官判定内核不读文件；本模块只在装配边界定位数据目录）。

数据：pHash 真样例（18 张近似重复族 + 3 张独立截图）与条文库（5 条数据契约）。
"""

import os

VERSION = "2026-10-14"
SLUG = "picrecall"
SUMMARY = (
    "截图相似分组与保留建议（pHash 汉明距离单链聚类 + 分辨率/大小/mtime 优先级；"
    "只出建议绝不删除 + 数据契约锚点）"
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

DATA_FILES = ("clauses.json", "phash-cases.json", "phash-clean.json")


def data_dir():
    return DATA_DIR


__all__ = ["VERSION", "SLUG", "SUMMARY", "DATA_DIR", "DATA_FILES", "data_dir"]