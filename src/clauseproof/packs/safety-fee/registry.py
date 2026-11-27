"""随包数据装配面（器官判定内核不读文件；本模块只在装配边界定位数据目录）。

来源规则包 **逐字节相同**（``manifest.json`` 登记 sha256/bytes）：

- ``rules-manifest.json`` / ``units.json``：规则集坐标 + 指纹 + 定义性单位换算；
- ``ruleset-{2022,2012}.json`` / ``spending-*.json`` / ``progress-*.json``：
  两版计提标准（2022 十二行业 / 2012 九类）、支出范围条目（41/30）、进度门槛；
- 2012 版 ``progress.json`` 的 status 为 **pending**（原文结构与 2022 版不同，
  门槛未落值）——progress 作用域门控会如实拦截（条款 pending 不静默放行）。
"""

import os

VERSION = "2026-10-14"
SLUG = "safety-fee"
SUMMARY = (
    "安全生产费用提取与使用：十二行业计提（产量/超额累退/比例）+ 依据选择判定 + "
    "支出范围四态核查 + 使用进度披露 + 双版本对照；规则包逐字节随包"
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

#: 判据 4 的进包清单（manifest.json 自登记清单不含自身）
DATA_FILES = (
    "clauses.json",
    "progress-2012.json",
    "progress-2022.json",
    "ruleset-2012.json",
    "ruleset-2022.json",
    "rules-manifest.json",
    "spending-2012.json",
    "spending-2022.json",
    "truth-cases.json",
    "units.json",
)


def data_dir():
    return DATA_DIR


__all__ = ["VERSION", "SLUG", "SUMMARY", "DATA_DIR", "DATA_FILES", "data_dir"]