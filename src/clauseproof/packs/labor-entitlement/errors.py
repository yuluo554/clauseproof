"""器官内部异常（迁自来源 ``errors``；边界统一映射见 ``__init__.evaluate``）。

器官契约只有两种"坏"：输入不合法（``ValueError`` → 退出码 2）与条文库不可用
（``ContractError``/``BasisMissing`` → 退出码 3 / 2）。本模块保留来源异常类型，
便于逐条测试；器官入口把它们折算到上述两种契约错误，不暴露第三种退出码。
"""


class LccError(Exception):
    """来源异常基类：携带消息与可选明细。"""

    def __init__(self, message, details=None):
        super().__init__(message)
        self.message = message
        self.details = list(details or [])

    def render(self):
        lines = [self.message]
        for item in self.details:
            lines.append("  - %s" % item)
        return "\n".join(lines)

    def __str__(self):
        return self.render()


class InputError(LccError):
    """输入事实缺失/格式错/字段非法。"""


class ParamCoordinateError(LccError):
    """请求的（地区, 年度）无对应参数包，或参数包坐标与请求不一致。"""


class ParamSchemaError(LccError):
    """参数包/常数包不符合 schema。"""


class GateError(LccError):
    """status 门控拦截：命中未核对（pending）条目。"""


class LawBasisError(LccError):
    """结论引用的条款 id 在条款库中不存在。"""


class ComputationError(LccError):
    """计算过程中的非法状态。"""


class NotImplementedYet(LccError):
    """未实现的通路（本器官不迁，保留类型供来源测试对照）。"""


class OptionalDependencyError(LccError):
    """可选依赖缺失（本器官不迁交付面，保留类型供对照）。"""


__all__ = [
    "LccError",
    "InputError",
    "ParamCoordinateError",
    "ParamSchemaError",
    "GateError",
    "LawBasisError",
    "ComputationError",
    "NotImplementedYet",
    "OptionalDependencyError",
]