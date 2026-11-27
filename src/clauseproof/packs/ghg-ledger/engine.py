"""组织碳核算引擎内核（**零 I/O / 零时钟 / 零政策数值字面量**）。

迁移的是来源产品「GB/T 32150 新旧双标尺 × 年度 × 行业」三维规则包的判定面，
合并来源的四个纯计算模块（decimals / engine 表达式树 / coordinates / units）：

- **Decimal 全链路**：计算路径禁 float（``as_decimal`` 只把字符串/int/Decimal
  规整为 Decimal；float 走 ``repr`` 再转，不丢精度口径）；
- **公式表达式树**：白名单运算（mul / add / sub / div / var / const）；
  ``const`` 只允许引用系数 id（``{"op":"const","value":1.0}`` 非法——零字面量）；
  除数为 0 抛 :class:`CalcError`；
- **三维坐标**：``<标准>/<年度>/<行业>`` 一维化键；合法性判据全部来自 manifest
  （代码内零坐标字面量）；
- **单位换算**：量纲 → 基准单位 → 换算因子（表来自随包 ``units.json``）；
  跨量纲直接报错；复合因子单位 ``<排放单位>_per_<活动单位>``。

本模块不读文件：规则包/单位表/manifest 以内存 dict 传入（装配面在 registry）。
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: 复合因子单位分隔符（单一真相源）
PER_SEPARATOR = "_per_"


class GhgError(ValueError):
    """输入不可用（字段缺失 / 结构非法）；内核映射退出码 2。"""


class InputError(GhgError):
    """输入不可用或参数错误。"""


class CoordinateError(InputError):
    """坐标不存在或无法解析。"""


class MixedCoordinateError(InputError):
    """一次核算里出现两个及以上规则包坐标（跨坐标混算）。"""


class FactorUnavailable(InputError):
    """因子来源三层（实测/官方库/行业缺省）均不可用。"""


class UnitError(InputError):
    """单位未知或量纲不一致。"""


class RulesetValidationError(InputError):
    """规则包结构或表达式非法。"""


class CalcError(InputError):
    """计算过程非法（除零、引用缺失等）。"""


class BoundaryError(InputError):
    """边界识别失败（缺 source_id / 未知源 / 声明的差异与结构不符）。"""


class QualityError(InputError):
    """校核层输入不可用。"""


class QuotaUnavailable(InputError):
    """配额试算参数不可用（未核对 / 需外部输入未提供）。"""


class RulesetNotEffective(InputError):
    """门控拦截：规则包存在未核对（pending）条目，禁止进入计算路径。"""

    def __init__(self, coordinate: str, entries) -> None:
        self.coordinate = coordinate
        self.entries = sorted(entries)
        sample = "、".join(self.entries[:5])
        more = "" if len(self.entries) <= 5 else "（等 %d 项）" % len(self.entries)
        super().__init__(
            "规则包 %s 存在未核对条目，已拒绝进入计算路径：%s%s"
            % (coordinate, sample, more))


# ---------------------------------------------------------------------------
# Decimal 口径（来源 decimals 模块）
# ---------------------------------------------------------------------------
#: 内部计算精度（有效位数）
PRECISION = 28
#: 输出呈现小数位（排放量 tCO2e 保留 3 位）
OUTPUT_PLACES = 3
#: 中间比强度等辅助量的小数位
RATIO_PLACES = 6


def scale_for(places: int) -> Decimal:
    """返回指定小数位的量化刻度（places=3 → Decimal('0.001')）。"""
    if not isinstance(places, int) or places < 0:
        raise ValueError("places 必须为非负整数")
    return Decimal(1).scaleb(-places)


def as_decimal(value: Any) -> Decimal:
    """把 int/str/Decimal 转成 Decimal；显式拒绝 float（尾差不得从入口渗入）。"""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise CalcError("bool 不是合法数值输入")
    if isinstance(value, float):
        raise CalcError(
            "禁止 float 进入计算路径；请用字符串或 Decimal 表达数值")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation:
            raise CalcError("无法解析为 Decimal：%r" % (value,))
    raise CalcError("不可计算的值类型：%s" % type(value).__name__)


def quantize(value: Any, places: int = OUTPUT_PLACES) -> Decimal:
    """按指定小数位四舍五入（ROUND_HALF_UP）——呈现口径。"""
    return as_decimal(value).quantize(
        scale_for(places), rounding=ROUND_HALF_UP)


def to_text(value: Any, places: int = OUTPUT_PLACES) -> str:
    """量化后转字符串（无科学计数法；去尾零；空值回落 "0"）。"""
    q = quantize(value, places)
    text = format(q, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


# ---------------------------------------------------------------------------
# 公式表达式树（来源 engine 模块）
# ---------------------------------------------------------------------------
OPS = ("mul", "add", "sub", "div", "var", "const")
_BINARY_OPS = ("sub", "div")
_NARY_OPS = ("mul", "add")

VAR_ACTIVITY = "activity_data"
VAR_FACTOR = "emission_factor"
VAR_OXIDATION = "oxidation_rate"
FORMULA_VARS = (VAR_ACTIVITY, VAR_FACTOR, VAR_OXIDATION)
OPTIONAL_FORMULA_VARS = (VAR_OXIDATION,)


def validate(expr, path="$") -> bool:
    """校验表达式结构；非法即抛 :class:`RulesetValidationError`（fail fast）。"""
    if not isinstance(expr, dict):
        raise RulesetValidationError("表达式节点必须是对象，位置 %s" % path)
    op = expr.get("op")
    if op not in OPS:
        raise RulesetValidationError("非法运算符 %r，位置 %s" % (op, path))
    extra = set(expr.keys()) - {"op", "args", "ref"}
    if extra:
        raise RulesetValidationError(
            "表达式节点含未知字段 %s，位置 %s" % (sorted(extra), path))
    if op in ("var", "const"):
        ref = expr.get("ref")
        if not isinstance(ref, str) or not ref:
            raise RulesetValidationError("%s 节点缺少 ref，位置 %s" % (op, path))
        if "args" in expr:
            raise RulesetValidationError("%s 节点不得含 args，位置 %s" % (op, path))
        return True
    args = expr.get("args")
    if not isinstance(args, list) or not args:
        raise RulesetValidationError("%s 节点缺少 args，位置 %s" % (op, path))
    if op in _BINARY_OPS and len(args) != 2:
        raise RulesetValidationError("%s 需要恰好 2 个参数，位置 %s" % (op, path))
    if op in _NARY_OPS and len(args) < 1:
        raise RulesetValidationError("%s 至少需要 1 个参数，位置 %s" % (op, path))
    for idx, child in enumerate(args):
        validate(child, "%s.args[%d]" % (path, idx))
    return True


def evaluate(expr, scope) -> Decimal:
    """按表达式树求值，返回 Decimal；缺失引用抛 :class:`CalcError`。"""
    validate(expr)
    op = expr["op"]
    if op == "var":
        return _lookup(expr["ref"], scope, "变量")
    if op == "const":
        return _lookup(expr["ref"], scope, "系数")
    values = [evaluate(child, scope) for child in expr["args"]]
    if op == "mul":
        acc = values[0]
        for value in values[1:]:
            acc = acc * value
        return acc
    if op == "add":
        acc = values[0]
        for value in values[1:]:
            acc = acc + value
        return acc
    if op == "sub":
        return values[0] - values[1]
    if op == "div":
        if values[1] == 0:
            raise CalcError("除数为 0，表达式 %r" % (expr,))
        return values[0] / values[1]
    raise RulesetValidationError("非法运算符 %r" % op)


def _lookup(ref, scope, kind) -> Decimal:
    if not isinstance(scope, dict) or ref not in scope:
        raise CalcError("表达式引用的%s不存在：%s" % (kind, ref))
    value = scope[ref]
    if value is None:
        raise CalcError("表达式引用的%s值为空（可能是未核对条目）：%s" % (kind, ref))
    return as_decimal(value)


def collect_refs(expr) -> List[str]:
    """收集表达式引用的全部 ref（去重排序），用于溯源与规则包校验。"""
    refs = set()

    def visit(node):
        if isinstance(node, dict):
            if node.get("op") in ("var", "const") and isinstance(node.get("ref"), str):
                refs.add(node["ref"])
            for arg in node.get("args", []) or []:
                visit(arg)

    visit(expr)
    return sorted(refs)


def collect_refs_by_op(expr) -> Dict[str, List[str]]:
    """按 ``op`` 分类收集 ref（变量引用与系数引用校验依据不同，不能混作一份清单）。"""
    out = {"var": set(), "const": set()}

    def visit(node):
        if isinstance(node, dict):
            op = node.get("op")
            if op in out and isinstance(node.get("ref"), str):
                out[op].add(node["ref"])
            for arg in node.get("args", []) or []:
                visit(arg)

    visit(expr)
    return {key: sorted(values) for key, values in out.items()}


# ---------------------------------------------------------------------------
# 三维坐标（来源 coordinates 模块）
# ---------------------------------------------------------------------------
class Coordinate(object):
    """一个规则包坐标（``<standard>/<year>/<industry>``）。"""

    __slots__ = ("standard", "year", "industry")

    def __init__(self, standard, year, industry) -> None:
        if not standard or not industry:
            raise CoordinateError("坐标字段不得为空：%r/%r/%r" % (standard, year, industry))
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            raise CoordinateError("年度必须为整数：%r" % (year,))
        self.standard = str(standard)
        self.year = year_int
        self.industry = str(industry)

    @property
    def key(self) -> str:
        return "%s/%d/%s" % (self.standard, self.year, self.industry)

    def as_dict(self) -> Dict[str, Any]:
        return {"standard": self.standard, "year": self.year, "industry": self.industry}

    def __eq__(self, other) -> bool:
        return isinstance(other, Coordinate) and self.key == other.key

    def __hash__(self) -> int:
        return hash(self.key)

    def __repr__(self) -> str:
        return "Coordinate(%s)" % self.key

    def __str__(self) -> str:
        return self.key


# ---------------------------------------------------------------------------
# 单位换算（来源 units 模块；表来自随包 units.json）
# ---------------------------------------------------------------------------
def split_compound_unit(unit):
    """``<排放单位>_per_<活动单位>`` → 二元组；非复合单位返回 ``(unit, None)``。"""
    if unit and PER_SEPARATOR in unit:
        numerator, denominator = unit.split(PER_SEPARATOR, 1)
        return numerator or None, denominator or None
    return unit, None


class UnitTable(object):
    """量纲 → 基准单位 → 换算因子 的换算表。"""

    def __init__(self, raw: Mapping) -> None:
        self._raw = raw
        self._dim_of = {}
        self._factor = {}
        for dimension, spec in (raw.get("dimensions") or {}).items():
            base = spec["base"]
            for unit, factor in spec["units"].items():
                if unit in self._dim_of:
                    raise UnitError("单位在多个量纲中重复定义：%s" % unit)
                self._dim_of[unit] = dimension
                self._factor[unit] = as_decimal(str(factor))
            if self._factor.get(base) != as_decimal(1):
                raise UnitError("量纲 %s 的基准单位 %s 换算因子必须为 1" % (dimension, base))

    def known(self, unit) -> bool:
        return unit in self._dim_of

    def scale(self, unit) -> Decimal:
        try:
            return self._factor[unit]
        except KeyError:
            raise UnitError("未知单位：%s" % unit)

    def base_of(self, unit) -> str:
        return self._raw["dimensions"][self.dimension_of(unit)]["base"]

    def dimension_of(self, unit) -> str:
        try:
            return self._dim_of[unit]
        except KeyError:
            raise UnitError("未知单位：%s" % unit)

    def unit_list(self) -> List[str]:
        return sorted(self._dim_of.keys())

    def dimensions(self) -> Dict[str, Any]:
        return dict(self._raw.get("dimensions") or {})

    def to_base(self, value, unit) -> Tuple[Decimal, str]:
        dim = self.dimension_of(unit)
        base = self._raw["dimensions"][dim]["base"]
        return as_decimal(value) * self._factor[unit], base

    def convert(self, value, from_unit, to_unit) -> Decimal:
        """同量纲换算；跨量纲直接报错（防止 t 换 MWh 这类量纲混用）。"""
        dim_from = self.dimension_of(from_unit)
        dim_to = self.dimension_of(to_unit)
        if dim_from != dim_to:
            raise UnitError(
                "量纲不一致，禁止换算：%s(%s) → %s(%s)"
                % (from_unit, dim_from, to_unit, dim_to))
        base_value = as_decimal(value) * self._factor[from_unit]
        return base_value / self._factor[to_unit]


__all__ = [
    "Decimal", "GhgError", "InputError", "CoordinateError", "MixedCoordinateError",
    "FactorUnavailable", "UnitError", "RulesetValidationError", "CalcError",
    "BoundaryError", "QualityError", "QuotaUnavailable", "RulesetNotEffective",
    "as_decimal", "quantize", "to_text", "scale_for",
    "OPS", "VAR_ACTIVITY", "VAR_FACTOR", "VAR_OXIDATION", "FORMULA_VARS",
    "OPTIONAL_FORMULA_VARS", "validate", "evaluate", "collect_refs",
    "collect_refs_by_op", "Coordinate", "split_compound_unit", "UnitTable",
    "PER_SEPARATOR",
]