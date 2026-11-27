"""异常类型（迁自来源 ``rules.RuleError``；退出码映射见 :mod:`clauseproof.cli`）。

规则库不可用（缺必填字段 / 依据无出处 / 未知 check_type / 票种非法）
→ ``ValueError`` → 退出码 2（与来源一致）。
"""


class TicketError(Exception):
    """基础异常。"""


class RuleError(TicketError):
    """规则库加载 / 校验失败（规则数据不可用）。"""


class InputError(TicketError):
    """票面参数卡不可用（结构非法 / 票种未知 / 字段类型非法）。"""


__all__ = ["TicketError", "RuleError", "InputError"]