"""体检指标判定内核（**零 I/O / 零时钟 / 零环境变量 / 零区间字面量**）。

逐条移植 target-map ① 行来源产品的判定口径（``engine/compare.py`` +
``model.py`` 的四态 + 三级优先），只保留"输入 → 判定"这一段：

- **三级优先选区间**：① 报告自印区间 > ② 内置来源标注默认值（且必须适用于该主体）
  > ③ 无区间 → 拒判（``not_assessed``）；
- **四态比较**：``high`` / ``low`` / ``normal`` / ``not_assessed``；
- **边界语义由区间自带**（``closed`` 闭区间 / ``open`` 开区间），不在代码里硬编码
  某个标准的习惯；单侧区间对缺失的一侧不设限；
- **适用域硬门**：``applies_to.sex`` 是原文自带的主体限制，主体未知 → 不适用
  （宁拒判，不拿不适用的区间下结论）。

区间数值**只能来自** :mod:`registry`（知识库）；本模块不得出现区间字面量。
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

# ------------------------------------------------------------------ 判定四态
FLAG_HIGH = "high"
FLAG_LOW = "low"
FLAG_NORMAL = "normal"
FLAG_NOT_ASSESSED = "not_assessed"
ALL_FLAGS = (FLAG_HIGH, FLAG_LOW, FLAG_NORMAL, FLAG_NOT_ASSESSED)

# ------------------------------------------------------------------ 区间来源
RANGE_SOURCE_REPORT = "report_printed"
RANGE_SOURCE_BUILTIN = "builtin_default"
RANGE_SOURCE_NONE = "none"
ALL_RANGE_SOURCES = (RANGE_SOURCE_REPORT, RANGE_SOURCE_BUILTIN, RANGE_SOURCE_NONE)

# ------------------------------------------------------------------ 边界语义
BOUNDS_CLOSED = "closed"
BOUNDS_OPEN = "open"
ALL_BOUNDS = (BOUNDS_CLOSED, BOUNDS_OPEN)

# ------------------------------------------------------------------ 适用域
SEX_ANY = "any"
SEX_MALE = "male"
SEX_FEMALE = "female"
ALL_SEX = (SEX_ANY, SEX_MALE, SEX_FEMALE)

# ------------------------------------------------------------------ 核对状态
STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"

#: 报告自印区间的条文锚点（本器官唯一"当下可用"的依据）
CLAUSE_REPORT_PRINTED = "range:report-printed"


class CheckupError(ValueError):
    """输入不合法（测量记录结构缺陷）。内核映射退出码 2。"""


class RangeError(CheckupError):
    """区间字段非法：边界语义未知、上下限颠倒、上下限同缺却声称有来源。

    此类错误**必须显式抛出**，绝不回落成"没有区间"——那会把结构缺陷静默读成
    "拒判"，让本该报警的条目看起来一切正常。
    """


# ------------------------------------------------------------------ 数据模型
@dataclass(frozen=True)
class RefRange:
    """参考区间。``source`` 记录它从哪来（三级优先的依据）。"""

    low: Optional[float] = None
    high: Optional[float] = None
    bounds: str = BOUNDS_CLOSED
    source: str = RANGE_SOURCE_NONE


@dataclass(frozen=True)
class Indicator:
    """一条内置区间条目（知识库单元的只读视图）。"""

    canonical_name: str
    display_name: str
    aliases: Tuple[str, ...]
    unit: str
    unit_aliases: Tuple[str, ...]
    low: Optional[float]
    high: Optional[float]
    bounds: str
    sex: str
    standard: str
    status: str

    @property
    def is_effective(self) -> bool:
        """只有 ``verified`` 能进判定路径（未核对条目走"拒判"）。"""
        return self.status == STATUS_VERIFIED

    @property
    def names(self) -> Tuple[str, ...]:
        """全部候选名（规范名 + 别名），声明序。"""
        return (self.canonical_name,) + tuple(self.aliases)

    @property
    def units(self) -> Tuple[str, ...]:
        return (self.unit,) + tuple(self.unit_aliases)

    def default_range(self) -> RefRange:
        return RefRange(low=self.low, high=self.high, bounds=self.bounds,
                        source=RANGE_SOURCE_BUILTIN)


@dataclass(frozen=True)
class RawJudgement:
    """内部判定（尚未挂条款锚点）。对外映射由 pack 完成。"""

    canonical_name: str
    flag: str
    code: str
    message: str
    range_used: RefRange
    range_source: str
    evidence: Mapping[str, Any]
    clause_id: Optional[str]


# ------------------------------------------------------------------ 区间校验
def validate_range(ref: RefRange) -> None:
    """区间结构校验（判定路径的入口门）。"""
    if ref.bounds not in ALL_BOUNDS:
        raise RangeError("未知的边界语义 bounds=%r（合法值：%s）"
                         % (ref.bounds, ", ".join(ALL_BOUNDS)))
    if ref.source not in ALL_RANGE_SOURCES:
        raise RangeError("未知的区间来源 source=%r" % (ref.source,))
    if ref.low is None and ref.high is None:
        if ref.source != RANGE_SOURCE_NONE:
            raise RangeError("区间上下限同时缺失，却声称来源为 %r" % (ref.source,))
        return
    if ref.low is not None and ref.high is not None and ref.low > ref.high:
        raise RangeError("区间下限定为 %r 高于上限 %r" % (ref.low, ref.high))


def compare(value: float, ref: RefRange) -> str:
    """四态边界比较（不含"区间从哪来"的判断）。"""
    validate_range(ref)

    if ref.low is None and ref.high is None:
        return FLAG_NOT_ASSESSED

    if ref.high is not None:
        if value > ref.high:
            return FLAG_HIGH
        if ref.bounds == BOUNDS_OPEN and value == ref.high:
            return FLAG_HIGH

    if ref.low is not None:
        if value < ref.low:
            return FLAG_LOW
        if ref.bounds == BOUNDS_OPEN and value == ref.low:
            return FLAG_LOW

    return FLAG_NORMAL


def range_applies_to(constraint: str, subject_sex: Optional[str]) -> bool:
    """适用域硬门：``any`` 适用；主体未知 → 不适用；其余须主体一致。"""
    if constraint not in ALL_SEX:
        raise RangeError("未知的适用域 applies_to.sex=%r（合法值：%s）"
                         % (constraint, ", ".join(ALL_SEX)))
    if constraint == SEX_ANY:
        return True
    if subject_sex is None:
        return False
    return constraint == subject_sex


def select_range(measurement_range: Optional[RefRange],
                 default: Optional[RefRange] = None,
                 subject_sex: Optional[str] = None,
                 default_constraint: str = SEX_ANY) -> RefRange:
    """三级优先选区间（唯一实现处）。"""
    if measurement_range is not None:
        printed = RefRange(low=measurement_range.low, high=measurement_range.high,
                           bounds=measurement_range.bounds,
                           source=RANGE_SOURCE_REPORT)
        validate_range(printed)
        return printed

    if default is not None and range_applies_to(default_constraint, subject_sex):
        builtin = RefRange(low=default.low, high=default.high, bounds=default.bounds,
                           source=RANGE_SOURCE_BUILTIN)
        validate_range(builtin)
        return builtin

    return RefRange(low=None, high=None, bounds=BOUNDS_CLOSED, source=RANGE_SOURCE_NONE)


# ------------------------------------------------------------------ 名称/单位归一
def normalize_name(raw_name: str, indicators: Sequence[Indicator]) -> Optional[Indicator]:
    """按声明序把原文指标名归一到知识库条目（认不出 → ``None``）。

    归一顺序：精确命中规范名或别名 → 去空白后精确命中（大小写不敏感）。
    不做模糊匹配/子串匹配——"猜"会把相邻项目判错。
    """
    if not isinstance(raw_name, str) or not raw_name.strip():
        return None
    text = raw_name.strip()
    for indicator in indicators:
        if text in indicator.names:
            return indicator
    folded = text.replace(" ", "").lower()
    for indicator in indicators:
        for name in indicator.names:
            if name.replace(" ", "").lower() == folded:
                return indicator
    return None


def normalize_unit(raw_unit: str, indicator: Indicator) -> Optional[str]:
    """把原文单位归一到该条目的规范单位（认不出 → ``None``）。"""
    if not isinstance(raw_unit, str) or not raw_unit.strip():
        return None
    text = raw_unit.strip()
    for unit in indicator.units:
        if text == unit:
            return indicator.unit
    folded = re.sub(r"\s+", "", text).lower()
    for unit in indicator.units:
        if re.sub(r"\s+", "", unit).lower() == folded:
            return indicator.unit
    return None


def find_indicator(canonical_name: str, indicators: Sequence[Indicator]) -> Optional[Indicator]:
    for indicator in indicators:
        if indicator.canonical_name == canonical_name:
            return indicator
    return None


def clause_id_for(indicator: Optional[Indicator], source: str) -> Optional[str]:
    """依据锚点的 clause_id：报告自印区间 → 单独一条；内置 → 该指标的标准条目。"""
    if source == RANGE_SOURCE_REPORT:
        return CLAUSE_REPORT_PRINTED
    if source == RANGE_SOURCE_BUILTIN and indicator is not None:
        return "wst:%s" % indicator.canonical_name
    return None


# ------------------------------------------------------------------ 判定
def judge_measurement(subject: Mapping, indicators: Sequence[Indicator]) -> RawJudgement:
    """对单条测量记录做判定（纯函数）。

    ``subject`` 已由调用方校验结构；本函数只负责判定语义。
    """
    raw_name = subject.get("canonical_name", "")
    indicator = normalize_name(raw_name, indicators)

    value = subject["value"]
    raw_unit = subject.get("unit", "")
    printed = _printed_range(subject.get("range"))
    subject_sex = subject.get("subject_sex")
    if subject_sex is not None and subject_sex not in ALL_SEX:
        raise CheckupError("未知的 subject_sex=%r（合法值：%s）"
                           % (subject_sex, ", ".join(ALL_SEX)))

    if indicator is None:
        return RawJudgement(
            canonical_name=str(raw_name), flag=FLAG_NOT_ASSESSED, code="indicator_unknown",
            message="指标名不在内置知识库：%r（不猜、不判）" % raw_name,
            range_used=RefRange(source=RANGE_SOURCE_NONE),
            range_source=RANGE_SOURCE_NONE,
            evidence={"raw_name": raw_name, "value": value, "unit": raw_unit},
            clause_id=None,
        )

    canonical_unit = normalize_unit(raw_unit, indicator)
    if canonical_unit is None:
        return RawJudgement(
            canonical_name=indicator.canonical_name, flag=FLAG_NOT_ASSESSED,
            code="unit_unknown",
            message="单位不在该指标的单位别名集里：%r（不猜换算，拒判）" % raw_unit,
            range_used=RefRange(source=RANGE_SOURCE_NONE),
            range_source=RANGE_SOURCE_NONE,
            evidence={"raw_unit": raw_unit, "expected_units": list(indicator.units),
                      "value": value},
            clause_id=None,
        )

    # 内置默认值只在**已核对**时进入判定路径；pending → 等同没有区间（源产品纪律）
    default = indicator.default_range() if indicator.is_effective else None
    ref = select_range(printed, default, subject_sex=subject_sex,
                       default_constraint=indicator.sex)
    flag = compare(value, ref)
    clause_id = clause_id_for(indicator, ref.source)

    evidence = {
        "canonical_name": indicator.canonical_name,
        "value": value,
        "unit": canonical_unit,
        "range_source": ref.source,
        "range_low": ref.low,
        "range_high": ref.high,
        "bounds": ref.bounds,
        "applies_to_sex": indicator.sex,
        "subject_sex": subject_sex,
        "standard": indicator.standard,
        "registry_status": indicator.status,
    }

    if flag == FLAG_NOT_ASSESSED:
        # 为什么拒判要写清楚：是"未核对"还是"没有区间"，是两件不同的事
        if printed is None and not indicator.is_effective:
            code, message = "builtin_pending", (
                "内置区间未核对（status=%s，来源 %s），拒判；以报告单印制区间为准"
                % (indicator.status, indicator.standard))
        elif printed is None and not range_applies_to(indicator.sex, subject_sex):
            code, message = "range_not_applicable", (
                "内置区间适用于 sex=%s，本次主体为 %r，拒判"
                % (indicator.sex, subject_sex))
        else:
            code, message = "no_range", "无可用参考区间，拒判（只记事实数值）"
        evidence["refused_reason"] = code
        return RawJudgement(
            canonical_name=indicator.canonical_name, flag=flag, code=code, message=message,
            range_used=ref, range_source=ref.source, evidence=evidence, clause_id=None)

    if flag == FLAG_HIGH:
        code, message = "above_high", ("高于参考区间上限 %r（区间 %r–%r，来源 %s）"
                                       % (ref.high, ref.low, ref.high, ref.source))
    elif flag == FLAG_LOW:
        code, message = "below_low", ("低于参考区间下限 %r（区间 %r–%r，来源 %s）"
                                      % (ref.low, ref.low, ref.high, ref.source))
    else:
        code, message = "within_range", ("在参考区间内（区间 %r–%r，来源 %s）"
                                         % (ref.low, ref.high, ref.source))
    return RawJudgement(
        canonical_name=indicator.canonical_name, flag=flag, code=code, message=message,
        range_used=ref, range_source=ref.source, evidence=evidence, clause_id=clause_id)


def _printed_range(raw: Any) -> Optional[RefRange]:
    """把 subject 里的 ``range`` 对象转成 :class:`RefRange`（缺省 → ``None``）。"""
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise CheckupError("range 必须是对象（low/high/bounds）")
    low = raw.get("low")
    high = raw.get("high")
    for name, value in (("low", low), ("high", high)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise CheckupError("range.%s 必须是数值或 null，得到 %r" % (name, value))
    bounds = raw.get("bounds", BOUNDS_CLOSED)
    return RefRange(low=low, high=high, bounds=bounds, source=RANGE_SOURCE_REPORT)


def validate_subject(subject: Mapping) -> None:
    """输入结构校验（不合法抛 :class:`CheckupError`，内核映射 2）。"""
    if not isinstance(subject, Mapping):
        raise CheckupError("测量记录必须是 JSON 对象，得到 %s" % type(subject).__name__)
    name = subject.get("canonical_name")
    if not isinstance(name, str) or not name.strip():
        raise CheckupError("缺少合法 canonical_name（须为非空字符串）")
    value = subject.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CheckupError("value 必须是数值，得到 %r" % (value,))
    unit = subject.get("unit", "")
    if unit is not None and not isinstance(unit, str):
        raise CheckupError("unit 必须是字符串，得到 %r" % (unit,))
    subject_sex = subject.get("subject_sex")
    if subject_sex is not None and subject_sex not in ALL_SEX:
        raise CheckupError("未知的 subject_sex=%r（合法值：%s）"
                           % (subject_sex, ", ".join(ALL_SEX)))
    # 区间结构在这里先过一次门（结构缺陷是输入问题，不是"拒判"）
    printed = _printed_range(subject.get("range"))
    if printed is not None:
        validate_range(printed)


__all__ = [
    "FLAG_HIGH", "FLAG_LOW", "FLAG_NORMAL", "FLAG_NOT_ASSESSED", "ALL_FLAGS",
    "RANGE_SOURCE_REPORT", "RANGE_SOURCE_BUILTIN", "RANGE_SOURCE_NONE", "ALL_RANGE_SOURCES",
    "BOUNDS_CLOSED", "BOUNDS_OPEN", "ALL_BOUNDS",
    "SEX_ANY", "SEX_MALE", "SEX_FEMALE", "ALL_SEX",
    "STATUS_VERIFIED", "STATUS_PENDING", "CLAUSE_REPORT_PRINTED",
    "CheckupError", "RangeError", "RefRange", "Indicator", "RawJudgement",
    "validate_range", "compare", "range_applies_to", "select_range",
    "normalize_name", "normalize_unit", "find_indicator", "clause_id_for",
    "judge_measurement", "validate_subject",
]