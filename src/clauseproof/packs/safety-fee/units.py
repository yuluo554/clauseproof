"""定义性单位换算（迁自来源 ``rules.units``）。

单位定义是**定义性事实**（1 万元 = 10000 元），不是政策数值；
政策数值一律只能来自规则包。单位不一致但可定义性换算 → 换算并记 warning
（绝不静默通过）；不可判定 → 报错（退出码 2）。
"""

from decimal import Decimal
from typing import Dict, Optional, Tuple

from .errors import SchemaError

_REQUIRED = ("CNY", "CNY10k", "CNY100m", "ton")


class UnitConverter:
    def __init__(self, factors: Dict[str, Decimal]) -> None:
        missing = [key for key in _REQUIRED if key not in factors]
        if missing:
            raise SchemaError("units.json 缺少必需单位：%s" % ", ".join(missing))
        self._factors = dict(factors)

    @property
    def factors(self) -> Dict[str, Decimal]:
        return dict(self._factors)

    def factor(self, unit: str) -> Decimal:
        try:
            return self._factors[unit]
        except KeyError:
            raise SchemaError("未知单位：%r（units.json 未登记）" % unit)

    def to_base(self, value: Decimal, unit: str) -> Tuple[Decimal, Optional[str]]:
        factor = self.factor(unit)
        if factor == Decimal(1):
            return value, None
        converted = value * factor
        return converted, ("输入单位 %s 与规则包期望单位不一致，已按定义性换算（×%s）"
                           % (unit, factor))


def build_units(payload: dict) -> UnitConverter:
    factors = payload.get("factors")
    if not isinstance(factors, dict):
        raise SchemaError("units.json 结构错误：缺少 factors 对象")
    return UnitConverter({key: Decimal(str(value)) for key, value in factors.items()})


__all__ = ["UnitConverter", "build_units"]