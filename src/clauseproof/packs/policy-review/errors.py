"""异常类型（迁自来源 ``errors``；退出码映射见 :mod:`clauseproof.cli`）。

- 输入 / 用法问题 → ``UsageError`` → 退出码 2；
- 规则包 / 条文包不可用 → ``RulesPackageError`` → 退出码 2（来源为 3；
  本器官把「规则包不可用」归入输入不可用，契约违约另由 ``ContractError`` 表示，
  口径差见 docs §5）。
"""


class PolicyError(Exception):
    """基础异常。"""


class UsageError(PolicyError):
    """输入文本 / 文档结构不可用。"""


class RulesPackageError(PolicyError):
    """规则包 / 条文包缺失或校验失败。"""


__all__ = ["PolicyError", "UsageError", "RulesPackageError"]