"""异常类型（迁自来源 ``errors``；退出码映射见 :mod:`clauseproof.cli`）。

来源的退出码语义：``0`` 全部符合 / ``1`` 检出不符合或未评估 / ``2`` 输入不可用 /
``3`` 缺可选依赖。本器官只保留判定面：``2`` 由内核把 ``ValueError`` 映射，
``3`` 由 ``ContractError`` 映射（条文库版本不符 / 条款缺失）。
"""


class AuditError(Exception):
    """基础异常。"""


class RulesetError(AuditError):
    """规则包加载 / 校验失败（规则数据不可用 → 退出码 2，与来源一致）。"""


class PendingEntryError(RulesetError):
    """试图使用 ``status=pending`` 的条目（未核对不得进入判定路径）。"""

    def __init__(self, entries):
        self.entries = list(entries)
        super().__init__(
            "以下条目 status=pending，未挂原文核对不得进入判定路径: "
            + ", ".join(str(entry) for entry in self.entries)
        )


class UnattributedEntryError(RulesetError):
    """``status=verified`` 但缺出处（channel / checked_at）的条目。"""

    def __init__(self, entries):
        self.entries = list(entries)
        super().__init__(
            "以下条目 status=verified 但缺出处（channel/checked_at 为空），"
            "不可追溯的『已核对』不得进入判定路径: "
            + ", ".join(str(entry) for entry in self.entries)
        )


class InputError(AuditError):
    """输入参数卡不可用（结构非法 / 规则包选择未知）。"""


__all__ = [
    "AuditError",
    "RulesetError",
    "PendingEntryError",
    "UnattributedEntryError",
    "InputError",
]