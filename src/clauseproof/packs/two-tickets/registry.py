"""随包数据装配面（器官判定内核不读文件；本模块只在装配边界定位数据目录）。

三份规则库文件与来源 **逐字节相同**（``manifest.json`` 登记 sha256/bytes）：

- ``rules-form.json`` / ``rules-time.json`` / ``rules-content.json``：
  39 条规则 / 7 票种 / 7 类 check_type；依据 **9 条已核对、30 条待核对**
  （待核对规则的「不合规」结论一律降级「待人工确认」——条款 pending 如实登记）。
"""

import os

VERSION = "2026-10-02"
SLUG = "two-tickets"
SUMMARY = (
    "电力两票（工作票/操作票）核查：7 票种 × 7 类 check_type + 三级结论 + "
    "依据闸（待核对降级待人工确认）+ 条款与复核锚；票面解析留输入层"
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

#: 判据 4 的进包清单（manifest.json 自登记清单不含自身）
DATA_FILES = (
    "clauses.json",
    "rules-content.json",
    "rules-form.json",
    "rules-time.json",
    "ticket-cases.json",
)


def data_dir():
    return DATA_DIR


__all__ = ["VERSION", "SLUG", "SUMMARY", "DATA_DIR", "DATA_FILES", "data_dir"]