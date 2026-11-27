"""随包数据装配面（器官判定内核不读文件；本模块只在装配边界读一次）。

数据文件与来源仓 **逐字节相同**（``manifest.json`` 登记 sha256/bytes）：
8 份 ``地区 × 年度`` 规则包、全国法定常数包、地区主数据、法条条款库。
"""

import os

VERSION = "2026-10-13"
SLUG = "labor-entitlement"
SUMMARY = (
    "劳动用工权益判定（经济补偿/赔偿金 + 加班费 + 未休年休假 + 二倍工资；"
    "地区×年度参数包 + status 门控 + 法条条款锚点）"
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

RULES_DIR = DATA_DIR
CONSTANTS_FILE = os.path.join(DATA_DIR, "constants.json")
REGIONS_FILE = os.path.join(DATA_DIR, "regions.json")
LAW_FILE = os.path.join(DATA_DIR, "law-clauses.json")
MANIFEST_FILE = os.path.join(DATA_DIR, "manifest.json")

#: 判据 4 的进包清单（manifest.json 自登记清单不含自身）
DATA_FILES = (
    "clauses.json",
    "constants.json",
    "law-clauses.json",
    "regions.json",
    "ruleset-110000-2025.json",
    "ruleset-110000-2026.json",
    "ruleset-310000-2025.json",
    "ruleset-310000-2026.json",
    "ruleset-320000-2025.json",
    "ruleset-320000-2026.json",
    "ruleset-440000-2025.json",
    "ruleset-440000-2026.json",
)


def data_dir():
    """固定数据目录（不读环境变量、不读 cwd——来源定位链留输入层）。"""
    return DATA_DIR


__all__ = ["VERSION", "SLUG", "SUMMARY", "DATA_DIR", "DATA_FILES", "data_dir"]