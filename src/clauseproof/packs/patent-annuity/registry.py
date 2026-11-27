"""随包数据装配面（器官判定内核不读文件；本模块只在装配边界定位数据目录）。

4 份规则包 + 规则 manifest + 条款快照与来源仓 **逐字节相同**（manifest 登记 sha256）。
"""

import os

VERSION = "2026-10-14"
SLUG = "patent-annuity"
SUMMARY = (
    "专利年费与费减判定（年费阶梯 × 专利类型 × 年度 + 滞纳金 + 费减资格/多政策择一 + "
    "组合排期；status 门控 + 政策条款锚点）"
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

DATA_FILES = (
    "clauses.json",
    "fee_schedule.v2024.json",
    "knowledge-clauses.json",
    "reduction_316.v2019.json",
    "reduction_594.v2024.json",
    "reduction_78.v2016.json",
    "rules-manifest.json",
)


def data_dir():
    return DATA_DIR


__all__ = ["VERSION", "SLUG", "SUMMARY", "DATA_DIR", "DATA_FILES", "data_dir"]