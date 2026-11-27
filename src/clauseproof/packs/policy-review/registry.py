"""随包数据装配面（器官判定内核不读文件；本模块只在装配边界定位数据目录）。

15 份规则/依据文件与来源 **逐字节相同**（``manifest.json`` 登记 sha256/bytes）：

- ``pattern-p01.json`` … ``pattern-p10.json``：十类高风险模式（正则 + 否定/中和 +
  升级条件 + 硬/背景锚点）；
- ``statute-PIPL.json`` / ``statute-DATA_SEC.json`` / ``statute-APP.json`` /
  ``statute-NECESSARY.json`` / ``statute-CROSS_BORDER.json``：五源条文包（165 条锚点）。
"""

import os

VERSION = "2026-10-18"
SLUG = "policy-review"
SUMMARY = (
    "隐私政策条款风险审查：条款切分 + 十类模式确定性匹配（影子串归一化/否定抑制）+ "
    "法条锚点映射 + 三级分级（高/中/提示）；纯本地、零网络、零 LLM"
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

#: 判据 4 的进包清单（manifest.json 自登记清单不含自身）
DATA_FILES = (
    "clauses.json",
    "pattern-p01.json",
    "pattern-p02.json",
    "pattern-p03.json",
    "pattern-p04.json",
    "pattern-p05.json",
    "pattern-p06.json",
    "pattern-p07.json",
    "pattern-p08.json",
    "pattern-p09.json",
    "pattern-p10.json",
    "statute-APP.json",
    "statute-CROSS_BORDER.json",
    "statute-DATA_SEC.json",
    "statute-NECESSARY.json",
    "statute-PIPL.json",
    "synthetic-cases.json",
)


def data_dir():
    return DATA_DIR


__all__ = ["VERSION", "SLUG", "SUMMARY", "DATA_DIR", "DATA_FILES", "data_dir"]