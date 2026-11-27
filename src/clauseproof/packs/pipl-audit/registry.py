"""随包数据装配面（器官判定内核不读文件；本模块只在装配边界定位数据目录）。

两份规则包与来源 **逐字节相同**（``manifest.json`` 登记 sha256/bytes）：

- ``ruleset-pipl-audit-2025.json``：权威规则包（3 份依据 × 4 门槛 × 26 检查项，
  全部 ``verified`` 且出处齐全）；
- ``ruleset-pipl-audit-demo.json``：来源 ``data/samples`` 的**合成示例包**
  （门槛值为合成示例值，**非法规门槛**；只用于复现来源快速开始，不得据以作出
  任何合规结论）。示例包的条款坐标一律以 ``示例（合成）`` 前缀登记。
"""

import os

VERSION = "2026-10-13"
SLUG = "pipl-audit"
SUMMARY = (
    "个人信息保护合规审计判定（审计义务门槛 + 义务分栏 + 27 项检查单四态 + "
    "汇总语义；条款锚点 + status 门控）"
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

#: 权威规则包 id（缺省选择；subject 的 ``ruleset`` 可覆盖为示例包）
DEFAULT_RULESET = "pipl-audit-2025"

#: 判据 4 的进包清单（manifest.json 自登记清单不含自身）
DATA_FILES = (
    "clauses.json",
    "ruleset-pipl-audit-2025.json",
    "ruleset-pipl-audit-demo.json",
    "truth-cases.json",
)


def data_dir():
    return DATA_DIR


__all__ = ["VERSION", "SLUG", "SUMMARY", "DATA_DIR", "DEFAULT_RULESET",
           "DATA_FILES", "data_dir"]