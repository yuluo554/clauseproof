"""随包数据装配面（器官判定内核不读文件；本模块只在装配边界定位数据目录）。

数据文件与来源仓 **逐字节相同**（``manifest.json`` 登记 sha256/bytes）：
两版规则包（GBZ 188—2014 / GBZ 188—2025）+ 规则 manifest + 条款快照。
"""

import os

VERSION = "2026-10-14"
SLUG = "occupational-surveillance"
SUMMARY = (
    "职业健康监护核查（GBZ 188 双版本：因素×检查项目×周期矩阵 + 监护档案覆盖度 + "
    "版本差异对照；status 门控 + 条款锚点）"
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

#: 判据 4 的进包清单（manifest.json 自登记清单不含自身）
DATA_FILES = (
    "clauses.json",
    "knowledge-clauses.json",
    "rules-manifest.json",
    "ruleset-2014.json",
    "ruleset-2025.json",
)


def data_dir():
    return DATA_DIR


__all__ = ["VERSION", "SLUG", "SUMMARY", "DATA_DIR", "DATA_FILES", "data_dir"]