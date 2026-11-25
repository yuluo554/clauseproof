"""clauseproof 内核：账本模型 + 条文库 + 器官注册表。

三条内核约束（违反即 ``ContractError``，进程退出码 3）：
1. 无条款锚点不得下判定；
2. 器官不带自己的 CLI / 配置文件 / 输出排版；
3. 输出确定性：无时间戳、无绝对路径、字段顺序固定。
"""

from clauseproof.core.basis import Basis, BasisMissing, Clause
from clauseproof.core.ledger import (
    BLOCKING_VERDICTS,
    EXIT_BLOCKED,
    EXIT_CONTRACT,
    EXIT_INPUT,
    EXIT_OK,
    FAIL,
    NOT_APPLICABLE,
    PASS,
    VERDICTS,
    Anchor,
    ContractError,
    Finding,
    Report,
)
from clauseproof.core.registry import Pack, PackMissing, all_packs, get, register

__all__ = [
    "Basis",
    "BasisMissing",
    "Clause",
    "Anchor",
    "Finding",
    "Report",
    "ContractError",
    "Pack",
    "PackMissing",
    "register",
    "get",
    "all_packs",
    "PASS",
    "FAIL",
    "NOT_APPLICABLE",
    "VERDICTS",
    "BLOCKING_VERDICTS",
    "EXIT_OK",
    "EXIT_BLOCKED",
    "EXIT_INPUT",
    "EXIT_CONTRACT",
]