"""器官目录：每个器官一个子包 ``<slug>/``，导入时向注册表登记自己的 ``Pack``。

**显式清单，不用 pkgutil 扫描**：扫描式加载会把「某个器官忘了登记」变成静默空跑，
而显式清单在导入失败时立刻红。目录名 = 器官 slug（含连字符），故模块名一律经
``importlib`` 按字符串导入，包内引用用相对导入。

新增器官的三步（SKELETON-SPEC §1/§2）：

1. 在 ``clauseproof/packs/<slug>/__init__.py`` 里 ``register(Pack(...))``；
2. 把模块名加进下面的 ``BUILTIN_MODULES``；
3. 补 ``tests/test_<slug>.py`` 与 ``docs/<slug>.md``（输入 / 规则 / 输出示例）。
"""

import importlib
from typing import Tuple

#: 已迁入的内置器官模块名（相对 ``clauseproof.packs``）。按 slug 字典序维护。
BUILTIN_MODULES: Tuple[str, ...] = (
    "bid-conformity",
    "checkup-ranges",
    "cost-card",
    "ebike-limits",
    "expense-ledger",
    "extreme-terms",
    "food-label",
    "ghg-ledger",
    "income-tax",
    "invoice-ledger",
    "labeling-claims",
    "labor-entitlement",
    "lease-terms",
    "occupational-surveillance",
    "petfood-label",
    "policy-intake",
)


def load_builtin() -> None:
    """导入全部内置器官模块（每个模块在 import 时登记自己的 Pack）。"""
    for name in BUILTIN_MODULES:
        importlib.import_module("clauseproof.packs." + name)