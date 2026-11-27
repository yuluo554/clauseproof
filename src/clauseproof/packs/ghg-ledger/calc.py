"""逐源核算与校核层（来源 calc + quality 模块的判定面）。

**核算**（``compute``）：

- 纳入判定统一走 :func:`rules.identify_boundary`；应核算源缺活动数据即抛
  :class:`BoundaryError`（不得静默按空核算）；
- 因子选择优先级：``measured``（档案实测）> ``official_db``（官方因子库）>
  ``industry_default``（规则包，按类别分派）；档案自报来源不在白名单内按不可用
  处理（防"自称"绕过）；三层皆不可用 → :class:`FactorUnavailable`；
- 单位链显式化：活动数据 → 基本单位，因子 → 每基本单位，排放 → tCO2e；
  每一步记录在 unit_chain（供溯源表回指）；
- 公式求值经 :mod:`engine`（表达式树来自规则包，非代码内联）；
  氧化率系数仅对燃烧类源适用（其余恒等 1）。

**校核**（``run_checks``）：四类检查（unit_consistency / magnitude_outlier /
yoy_jump / intensity_plausibility），一切阈值取自规则包 ``quality.thresholds``；
``pending`` 规则与不可用阈值对应的检查不执行，记入 ``rules_skipped``。
"""

from typing import Any, Dict, List, Mapping, Optional

from . import engine as E
from . import rules

UNIT_EMISSION = "tCO2e"
FACTOR_PLACES = 6
_OXIDATION_CATEGORIES = ("combustion",)
_DECLARED_FACTOR_SOURCES = ("measured", "official_db", "industry_default")
_DIMENSIONLESS = ("1", "", None)

LEVEL_ERROR = "error"
LEVEL_WARNING = "warning"
LEVEL_INFO = "info"
LEVELS = (LEVEL_ERROR, LEVEL_WARNING, LEVEL_INFO)

TYPE_UNIT = "unit_consistency"
TYPE_MAGNITUDE = "magnitude_outlier"
TYPE_YOY = "yoy_jump"
TYPE_INTENSITY = "intensity_plausibility"

TH_MAGNITUDE = "magnitude"
TH_YOY = "yoy"
TH_INTENSITY_MIN = "intensity_min"
TH_INTENSITY_MAX = "intensity_max"

RATIO_TEXT_PLACES = 2
RATIO_TEXT_SCALE = E.scale_for(RATIO_TEXT_PLACES)
_PERCENT = E.as_decimal("100")
SCHEMA_QUALITY = "ghg-qualityreport/v1"


def _factor_text(value):
    return E.to_text(E.quantize(value, FACTOR_PLACES), FACTOR_PLACES)


def _coefficient(pack, name):
    entry = (pack.get("engine") or {}).get("coefficients", {}).get(name)
    if entry is None:
        raise E.CalcError("规则包缺少系数：%s" % name)
    return entry


class UnitChain(object):
    """显式单位换算链：活动数据 → 基本单位，因子 → 每基本单位，排放 → tCO2e。"""

    def __init__(self, units):
        self.units = units
        self.steps = []

    def activity_to_base(self, value, unit):
        value = E.as_decimal(value)
        if unit in _DIMENSIONLESS:
            return value, unit
        dimension = self.units.dimension_of(unit)
        base = self.units.dimensions()[dimension]["base"]
        if unit == base:
            return value, base
        converted = self.units.convert(value, unit, base)
        self.steps.append({"target": "activity", "from_unit": unit, "to_unit": base,
                           "scale": str(self.units.scale(unit) / self.units.scale(base))})
        return converted, base

    def factor_to_base(self, value, unit, activity_base):
        value = E.as_decimal(value)
        numerator, denominator = E.split_compound_unit(unit)
        emission_unit = numerator or UNIT_EMISSION
        if denominator is None:
            return value, emission_unit
        if not self.units.known(denominator):
            raise E.UnitError("因子单位的分母未知：%s（因子单位 %s）" % (denominator, unit))
        if activity_base in _DIMENSIONLESS:
            raise E.UnitError(
                "活动数据无单位，无法换算因子 %s（因子分母 %s）" % (unit, denominator))
        if self.units.dimension_of(denominator) != self.units.dimension_of(activity_base):
            raise E.UnitError(
                "因子分母与活动数据量纲不一致：%s(%s) vs %s(%s)"
                % (denominator, self.units.dimension_of(denominator),
                   activity_base, self.units.dimension_of(activity_base)))
        scale = self.units.scale(activity_base) / self.units.scale(denominator)
        if scale == 1:
            return value, emission_unit
        converted = value * scale
        self.steps.append({
            "target": "factor", "from_unit": unit,
            "to_unit": "%s%s%s" % (emission_unit, E.PER_SEPARATOR, activity_base),
            "scale": str(scale)})
        return converted, emission_unit

    def emission_to_unit(self, value, unit):
        value = E.as_decimal(value)
        if unit in _DIMENSIONLESS or unit == UNIT_EMISSION:
            return value
        if not self.units.known(unit):
            raise E.UnitError("排放量单位未知：%s" % unit)
        converted = self.units.convert(value, unit, UNIT_EMISSION)
        self.steps.append({
            "target": "emission", "from_unit": unit, "to_unit": UNIT_EMISSION,
            "scale": str(self.units.scale(unit) / self.units.scale(UNIT_EMISSION))})
        return converted

    def trace(self):
        return list(self.steps)


def _default_factor_entry(pack, category):
    defaults = (pack.get("factors") or {}).get("industry_default_values", {}) or {}
    by_category = defaults.get("by_category") or {}
    if category and category in by_category:
        return by_category[category], "industry_default:%s" % category
    return defaults.get("default_factor"), "industry_default"


def _select_factor(profile_source, pack, category):
    """按规则包优先级选择排放因子 → ``(value, unit, source_label, provenance)``。"""
    priority = list((pack.get("factors") or {}).get("priority") or ())
    declared = profile_source.get("factor")
    if declared and declared.get("value") is not None:
        label = declared.get("source")
        if label not in _DECLARED_FACTOR_SOURCES:
            raise E.FactorUnavailable(
                "档案自报因子来源非法：%r（允许：%s）"
                % (label, "、".join(_DECLARED_FACTOR_SOURCES)))
        if priority and label not in priority:
            raise E.FactorUnavailable(
                "档案自报因子来源 %r 不在规则包优先级 %s 内" % (label, priority))
        if label == "industry_default":
            entry, _ = _default_factor_entry(pack, category)
            expected = None if entry is None else entry.get("value")
            if expected is None or E.as_decimal(declared["value"]) != E.as_decimal(expected):
                raise E.FactorUnavailable(
                    "档案自报行业缺省因子，但数值与规则包缺省值不一致（源 %s）"
                    % profile_source.get("source_id"))
        return (E.as_decimal(declared["value"]), declared.get("unit"), label,
                {"declared_source": declared.get("source"), "ref": declared.get("ref")})
    entry, label = _default_factor_entry(pack, category)
    if entry is None or entry.get("value") is None \
            or entry.get("status") != rules.STATUS_VERIFIED:
        raise E.FactorUnavailable(
            "排放源类别 %s 的行业缺省因子不可用（未核对或缺失）；"
            "实测/官方因子库亦未提供 → 不得静默取 0 或 1" % category)
    return (E.as_decimal(entry["value"]), entry.get("unit"), label,
            {"ref": entry.get("ref"), "clause": entry.get("clause")})


def _oxidation_ratio(pack, category, units):
    """燃烧类源的氧化率系数（% → 无量纲）；其余源恒等 1。"""
    if category not in _OXIDATION_CATEGORIES:
        return E.as_decimal(1)
    entry = _coefficient(pack, "oxidation_rate")
    if entry.get("value") is None or entry.get("status") != rules.STATUS_VERIFIED:
        raise E.CalcError("氧化率系数不可用（未核对）：oxidation_rate")
    unit = entry.get("unit")
    if unit in _DIMENSIONLESS:
        return E.as_decimal(entry["value"])
    return units.convert(E.as_decimal(entry["value"]), unit, "1")


def compute(payload, coord, pack, units):
    """逐源核算，返回结构化结果（含逐源明细、显式单位链与汇总）。"""
    formula = (pack.get("engine") or {}).get("formula")
    if formula is None:
        raise E.CalcError("规则包缺少公式定义")
    expr = formula["expr"]
    E.validate(expr)
    refs = E.collect_refs(expr)

    include_optional = bool(payload.get("include_optional"))
    report = rules.identify_boundary(payload, coord, pack,
                                     include_optional=include_optional)
    if report["missing_inputs"]:
        raise E.BoundaryError(
            "档案缺少应核算排放源的活动数据：%s（缺失输入 → 不得静默按空核算）"
            % "、".join(report["missing_inputs"]))

    catalog = {src["id"]: src for src in pack.get("boundary", {}).get("sources", [])}
    provided = {item["source_id"]: item for item in payload.get("sources", []) or []}

    lines = []
    total = E.as_decimal(0)
    for sid in sorted(report["included"]):
        src = catalog[sid]
        item = provided[sid]
        category = src.get("category")
        activity = item.get("activity") or {}

        chain = UnitChain(units)
        act_value, act_base = chain.activity_to_base(activity["value"],
                                                     activity.get("unit"))
        factor_value, factor_unit, factor_source, factor_prov = _select_factor(
            item, pack, category)
        factor_base, emission_unit = chain.factor_to_base(factor_value, factor_unit,
                                                          act_base)
        oxidation = _oxidation_ratio(pack, category, units)

        scope = {E.VAR_ACTIVITY: act_value, E.VAR_FACTOR: factor_base}
        if E.VAR_OXIDATION in refs:
            scope[E.VAR_OXIDATION] = oxidation

        emission = E.evaluate(expr, scope)
        emission = chain.emission_to_unit(emission, emission_unit)
        total += emission

        lines.append({
            "source_id": sid,
            "source_name": src.get("name"),
            "category": category,
            "activity": {"value": activity.get("value"), "unit": activity.get("unit")},
            "activity_base": {"value": E.to_text(act_value), "unit": act_base},
            "factor": {"value": _factor_text(factor_value), "unit": factor_unit,
                       "source": factor_source},
            "factor_base": {"value": _factor_text(factor_base),
                            "unit": "%s%s%s" % (emission_unit, E.PER_SEPARATOR,
                                                act_base)},
            "oxidation_rate": str(oxidation),
            "unit_chain": chain.trace(),
            "emission": E.to_text(emission),
            "emission_raw": str(emission),
            "clause": src.get("clause"),
            "provenance": {"rule_entry_id": sid, "coordinate": coord.key,
                           "source_clause": src.get("clause"), "factor": factor_prov},
        })

    return {"coordinate": coord.as_dict(), "coordinate_key": coord.key,
            "unit": UNIT_EMISSION, "lines": lines, "total": E.to_text(total),
            "total_raw": str(total), "line_count": len(lines),
            "boundary": report, "schema": "ghg-calcresult/v1"}


# ---------------------------------------------------------------------------
# 校核层（四类检查）
# ---------------------------------------------------------------------------
def _threshold(pack, key):
    entry = ((pack.get("quality") or {}).get("thresholds") or {}).get(key)
    if not isinstance(entry, dict):
        return None
    if entry.get("status") != rules.STATUS_VERIFIED or entry.get("value") is None:
        return None
    return E.as_decimal(entry["value"])


def _rules_by_type(pack):
    out = {}
    for rule in (pack.get("quality") or {}).get("rules", []) or []:
        out.setdefault(rule.get("type"), []).append(rule)
    return out


def _issue(rule, source_id, message, level=None):
    return {"rule_id": rule.get("id"), "type": rule.get("type"),
            "level": level or rule.get("level"), "source_id": source_id,
            "message": message, "clause": rule.get("clause"),
            "advice": rule.get("advice")}


def _lines_of(calc):
    return list((calc or {}).get("lines") or [])


def _declared_sources(profile):
    out = {}
    for item in (profile or {}).get("sources", []) or []:
        sid = item.get("source_id")
        if sid:
            out[sid] = item
    return out


def _unit_known(units, unit):
    if unit in _DIMENSIONLESS:
        return True
    if units is None:
        return True
    return units.known(unit)


def _check_unit_consistency(units, profile, calc, rules_list):
    """单位一致性：活动数据单位 ↔ 因子单位 ↔ 规则包口径可换算且量纲一致。"""
    issues = []
    lines = {line["source_id"]: line for line in _lines_of(calc)}
    declared = _declared_sources(profile)
    for rule in rules_list:
        for sid in sorted(declared):
            activity = (declared[sid].get("activity") or {})
            unit = activity.get("unit")
            if activity.get("value") is None:
                continue
            if not _unit_known(units, unit):
                issues.append(_issue(rule, sid,
                                     "活动数据单位无法识别：%r（不在单位换算表中）" % (unit,)))
        for sid in sorted(lines):
            line = lines[sid]
            act_unit = (line.get("activity") or {}).get("unit")
            fac_unit = (line.get("factor") or {}).get("unit")
            _numerator, denominator = E.split_compound_unit(fac_unit)
            if denominator is None or units is None:
                continue
            if not _unit_known(units, act_unit):
                continue
            if not units.known(denominator):
                issues.append(_issue(rule, sid, "因子单位分母无法识别：%r（因子单位 %s）"
                                     % (denominator, fac_unit)))
                continue
            if units.dimension_of(denominator) != units.dimension_of(act_unit):
                issues.append(_issue(rule, sid,
                                     "因子分母与活动数据量纲不一致：%s vs %s（因子单位 %s）"
                                     % (denominator, act_unit, fac_unit)))
                continue
            if denominator != act_unit:
                issues.append(_issue(rule, sid,
                                     "活动数据单位 %s 与因子单位分母 %s 口径不一致（已显式换算）"
                                     % (act_unit, denominator), level=LEVEL_WARNING))
    return issues


def _check_magnitude(pack, calc, rules_list):
    threshold = _threshold(pack, TH_MAGNITUDE)
    if threshold is None:
        return None
    lines = _lines_of(calc)
    if len(lines) < 2:
        return []
    total = sum((E.as_decimal(line["emission_raw"]) for line in lines), E.as_decimal(0))
    if total == 0:
        return []
    issues = []
    for rule in rules_list:
        for line in lines:
            share = E.as_decimal(line["emission_raw"]) / total
            if share > threshold:
                issues.append(_issue(rule, line["source_id"],
                                     "单源排放量占全厂合计 %s，超过规则包量级筛查阈值 %s"
                                     % (_ratio_text(share), _ratio_text(threshold))))
    return issues


def _check_yoy(pack, calc, rules_list, baseline):
    if baseline is None:
        return None
    threshold = _threshold(pack, TH_YOY)
    if threshold is None:
        return None
    now = {line["source_id"]: line for line in _lines_of(calc)}
    before = {line["source_id"]: line for line in _lines_of(baseline)}
    issues = []
    for rule in rules_list:
        for sid in sorted(set(now) & set(before)):
            new_value = _activity_value(now[sid])
            old_value = _activity_value(before[sid])
            if new_value is None or old_value in (None, E.as_decimal(0)):
                continue
            change = abs(new_value - old_value) / abs(old_value)
            if change > threshold:
                issues.append(_issue(rule, sid,
                                     "活动数据跨年度变化率 %s，超过规则包阈值 %s"
                                     "（上年度 %s → 本年度 %s）"
                                     % (_ratio_text(change), _ratio_text(threshold),
                                        _plain(old_value), _plain(new_value))))
    return issues


def _check_intensity(pack, profile, calc, rules_list):
    low = _threshold(pack, TH_INTENSITY_MIN)
    high = _threshold(pack, TH_INTENSITY_MAX)
    if low is None or high is None:
        return None
    output = (profile or {}).get("output") or {}
    if output.get("value") is None:
        return None
    quantity = E.as_decimal(output["value"])
    if quantity == 0:
        return None
    total = sum((E.as_decimal(line["emission_raw"]) for line in _lines_of(calc)),
                E.as_decimal(0))
    intensity = total / quantity
    if low <= intensity <= high:
        return []
    issues = []
    for rule in rules_list:
        issues.append(_issue(
            rule, None,
            "比强度 %s 落在规则包区间 [%s, %s] 之外（排放量 %s / 产量 %s %s）"
            % (_ratio_text(intensity), _ratio_text(low), _ratio_text(high),
               _plain(total), _plain(quantity), output.get("unit") or "-")))
    return issues


def run_checks(profile, calc, coord, pack, units=None, baseline=None):
    """执行四类数据质量检查，返回分级问题清单（只读，不修改 profile/calc）。"""
    if calc is None:
        raise E.QualityError("校核层需要核算结果（calc 不得为空）")
    by_type = _rules_by_type(pack)
    issues = []
    executed = []
    skipped = []

    def _dispatch(check_type, runner, *args):
        rules_list = by_type.get(check_type)
        if not rules_list:
            return
        result = runner(*args)
        if result is None:
            skipped.append({"type": check_type,
                            "rule_ids": [r.get("id") for r in rules_list],
                            "reason": _skip_reason(check_type, baseline)})
            return
        executed.extend(r.get("id") for r in rules_list)
        issues.extend(result)

    _dispatch(TYPE_UNIT, _check_unit_consistency, units, profile, calc,
              by_type.get(TYPE_UNIT) or [])
    _dispatch(TYPE_MAGNITUDE, _check_magnitude, pack, calc,
              by_type.get(TYPE_MAGNITUDE) or [])
    _dispatch(TYPE_YOY, _check_yoy, pack, calc, by_type.get(TYPE_YOY) or [], baseline)
    _dispatch(TYPE_INTENSITY, _check_intensity, pack, profile, calc,
              by_type.get(TYPE_INTENSITY) or [])

    counts = {level: 0 for level in LEVELS}
    for issue in issues:
        counts[issue["level"]] = counts.get(issue["level"], 0) + 1
    ordered = sorted(issues, key=lambda i: (LEVELS.index(i["level"])
                                            if i["level"] in LEVELS else len(LEVELS),
                                            i["rule_id"] or "", i["source_id"] or ""))
    return {"schema": SCHEMA_QUALITY, "coordinate": coord.key, "issues": ordered,
            "counts": counts, "issue_count": len(ordered),
            "rules_total": sum(len(v) for v in by_type.values()),
            "rules_executed": sorted(set(executed)), "rules_skipped": skipped}


def _skip_reason(check_type, baseline):
    if check_type == TYPE_YOY and baseline is None:
        return "未提供上一年度核算结果（yoy_jump 需跨年度对比）"
    if check_type == TYPE_INTENSITY:
        return "档案未提供产量（output）或规则包比强度阈值未生效"
    if check_type == TYPE_MAGNITUDE:
        return "规则包量级阈值未生效"
    return "规则包阈值未生效（未核对）"


def _activity_value(line):
    base = line.get("activity_base") or {}
    if base.get("value") is None:
        return None
    return E.as_decimal(base["value"])


def _plain(value):
    text = format(E.as_decimal(value), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _ratio_text(value):
    percent = E.as_decimal(value) * _PERCENT
    return "%s%%" % _plain(percent.quantize(RATIO_TEXT_SCALE))


__all__ = [
    "UNIT_EMISSION", "FACTOR_PLACES", "LEVELS", "LEVEL_ERROR", "LEVEL_WARNING",
    "LEVEL_INFO", "TYPE_UNIT", "TYPE_MAGNITUDE", "TYPE_YOY", "TYPE_INTENSITY",
    "UnitChain", "compute", "run_checks", "SCHEMA_QUALITY",
]