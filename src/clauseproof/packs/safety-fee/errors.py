"""异常类型（迁自来源 ``errors``；退出码映射见 :mod:`clauseproof.cli`）。

来源退出码：``0`` 完成 / ``1`` 门控或红线阻断 / ``2`` 输入/配置/规则不可用 /
``3`` 缺可选依赖。本器官：``1`` 由 ``fail`` 表达；其余可预期错误 → ``ValueError``
（退出码 2）；条文库版本/锚点问题 → ``ContractError``（3）。
"""


class FeeError(Exception):
    """基础异常。"""


class MissingInput(FeeError):
    """档案缺必填字段或依据选择所需属性（**必索**，绝不静默取 0/1）。"""


class SchemaError(FeeError):
    """规则包 / 文件结构非法。"""


class IntegrityError(FeeError):
    """规则文件指纹不符（规则包被手改）。"""


class ConfigError(FeeError):
    """配置缺失/非法（如未知门控作用域）。"""


class NotCovered(FeeError):
    """行业或规则不在覆盖范围（不臆造结论）。"""


class NoRulesetForYear(FeeError):
    """年度没有适用的规则集版本。"""


class AmbiguousRuleset(FeeError):
    """同一时点匹配到多个规则集（配置错误）。"""


__all__ = ["FeeError", "MissingInput", "SchemaError", "IntegrityError",
           "ConfigError", "NotCovered", "NoRulesetForYear", "AmbiguousRuleset"]