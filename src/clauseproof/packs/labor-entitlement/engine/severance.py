"""经济补偿 / 赔偿金引擎（迁自来源 ``engine.severance``）。

数值一律取自 ``EffectiveRuleset``，禁止硬编码：
  1. 口径判定：解除情形 → N / N+1 / 2N / none
  2. 工作年限取整：完整月数 + 余日（≥15 天计半个月）；满阈值个月不满 1 年按 1 年
  3. 月工资：解除前 N 个月平均应得工资；低于最低工资时按最低工资
  4. 三倍封顶：月工资 > 社平 × 倍数时按封顶基数，且年限 ≤ 上限（严格大于）
  5. 金额：N = 基数 × 年限；N+1 = N + 代通知金（上一个月工资）；2N = × 赔偿金倍数
"""

from datetime import date
from decimal import Decimal, ROUND_FLOOR

from ..decimalutil import quantize_money
from ..errors import ComputationError, InputError

MILESTONE = "M2"

_ZERO = Decimal(0)
_HALF = Decimal("0.5")
_TWELVE = Decimal(12)
# 余日折算阈值（天）：≥15 天计半个月（既定计算口径；通用计算常量）
_REMAINDER_HALF_MONTH_DAYS = 15

FORMULA_BY_GROUND = {
    "mutual_agreement": "N",
    "employee_fault_dismissal": "none",
    "employer_unilateral_no_fault": "N",
    "economic_layoff": "N",
    "illegal_termination": "2N",
    "contract_expiry_employer_no_renewal": "N",
    "employee_resignation_art38": "N",
    "employee_resignation_voluntary": "none",
}

FORMULA_CLAUSE_IDS = {
    "N": ["LCL-46", "LCL-47"],
    "N+1": ["LCL-40", "LCL-47"],
    "2N": ["LCL-48", "LCL-87"],
    "none": [],
}

_REASON_BY_GROUND = {
    "mutual_agreement": "协商一致解除（第 36 条）→ 应支付经济补偿",
    "employee_fault_dismissal": "劳动者过错解除（第 39 条）→ 无需支付经济补偿",
    "employer_unilateral_no_fault": "无过失性辞退（第 40 条）",
    "economic_layoff": "经济性裁员（第 41 条）→ 应支付经济补偿",
    "illegal_termination": "违法解除（第 48/87 条）→ 支付赔偿金",
    "contract_expiry_employer_no_renewal": "合同到期用人单位不续订（第 46 条第 5 项）→ 应支付经济补偿",
    "employee_resignation_art38": "劳动者被迫解除（第 38 条）→ 应支付经济补偿",
    "employee_resignation_voluntary": "劳动者主动辞职 → 无需支付经济补偿",
}


def _days_in_month(year, month):
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def _add_months(day, months):
    """加 ``months`` 个日历月；目标月无该日时取该月最后一天（月末夹取）。"""
    total = day.month - 1 + int(months)
    year = day.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(day.day, _days_in_month(year, month)))


def _months_and_remainder(start, end):
    if end < start:
        raise ComputationError("终止日期早于起始日期，无法计算工作年限")
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if _add_months(start, months) > end:
        months -= 1
    anchor = _add_months(start, months)
    return months, (end - anchor).days


def service_years_for_compensation(hire_date, terminate_date, ruleset):
    """工作年限取整（第 47 条 + 既定计算口径）。"""
    months, remainder = _months_and_remainder(hire_date, terminate_date)
    service_months = Decimal(months)
    if remainder >= _REMAINDER_HALF_MONTH_DAYS:
        service_months = service_months + _HALF
    full_years = (service_months / _TWELVE).to_integral_value(rounding=ROUND_FLOOR)
    rem_months = service_months - full_years * _TWELVE
    if rem_months >= ruleset.full_year_threshold_months():
        return full_years + ruleset.round_up_to_year()
    if rem_months > _ZERO:
        return full_years + ruleset.round_down_to_half_month()
    return full_years


def determine_formula(termination):
    """口径判定：解除情形 → ``{"ground", "formula", "basis", "reason"}``。"""
    ground = getattr(termination, "ground", None)
    if ground not in FORMULA_BY_GROUND:
        raise InputError("未知解除情形 %r" % (ground,))
    if ground == "employer_unilateral_no_fault":
        if not termination.notified_30d_in_advance:
            formula = "N+1"
            reason = "无过失性辞退（第 40 条）且未提前 30 日通知 → 额外支付一个月工资（代通知金）"
        else:
            formula = "N"
            reason = "无过失性辞退（第 40 条）已提前 30 日通知 → 仅支付经济补偿"
    else:
        formula = FORMULA_BY_GROUND[ground]
        reason = _REASON_BY_GROUND[ground]
    return {
        "ground": ground,
        "formula": formula,
        "basis": list(FORMULA_CLAUSE_IDS[formula]),
        "reason": reason,
    }


def _monthly_average(wages, ruleset):
    window = int(ruleset.avg_wage_months())
    sample = wages[-window:] if len(wages) > window else wages
    return sum(sample) / Decimal(len(sample))


def compute(facts, termination, ruleset):
    """计算经济补偿/赔偿金；返回金额 + 口径 + 过程 + 条款依据。"""
    if termination is None:
        raise InputError("经济补偿计算需要 termination 段（解除情形）")
    if facts.terminate_date is None:
        raise InputError("经济补偿计算需要 terminate_date（工作年限终点）")
    decision = determine_formula(termination)
    formula = decision["formula"]
    service_years = service_years_for_compensation(
        facts.hire_date, facts.terminate_date, ruleset)
    wages = list(facts.monthly_wages)
    if not wages:
        raise InputError("经济补偿计算需要 monthly_wages（解除前月工资序列）")
    avg = _monthly_average(wages, ruleset)
    min_wage = ruleset.min_wage_monthly()
    min_wage_applied = avg < min_wage
    basis_wage = min_wage if min_wage_applied else avg
    cap_base = ruleset.social_avg_wage_monthly() * ruleset.severance_cap_multiple()
    cap_applied = basis_wage > cap_base
    calc_base = cap_base if cap_applied else basis_wage
    years_used = service_years
    if cap_applied and years_used > ruleset.severance_cap_years():
        years_used = ruleset.severance_cap_years()
    if formula == "none":
        amount = _ZERO
    elif formula == "2N":
        amount = calc_base * years_used * ruleset.compensation_multiple()
    else:
        amount = calc_base * years_used
        if formula == "N+1":
            amount = amount + wages[-1]
    window = int(ruleset.avg_wage_months())
    sample_count = min(len(wages), window)
    steps = _build_steps(decision, service_years, avg, sample_count, min_wage_applied,
                         min_wage, cap_base, cap_applied, years_used, wages[-1], formula)
    return {
        "formula": formula,
        "ground": decision["ground"],
        "service_years": service_years,
        "monthly_wage_avg": quantize_money(avg),
        "last_month_wage": quantize_money(wages[-1]),
        "min_wage_applied": min_wage_applied,
        "cap_applied": cap_applied,
        "cap_base": quantize_money(cap_base),
        "basis_wage": quantize_money(calc_base),
        "years_used": years_used,
        "years_capped": years_used,
        "amount": quantize_money(amount),
        "steps": steps,
        "basis": list(decision["basis"]),
        "reason": decision["reason"],
    }


def _build_steps(decision, service_years, avg, sample_count, min_wage_applied, min_wage,
                 cap_base, cap_applied, years_used, last_month_wage, formula):
    steps = ["口径判定：%s" % decision["reason"]]
    steps.append("工作年限取整：%s 年" % service_years)
    steps.append("月工资口径：解除前 %d 个月平均应得工资 = %s"
                 % (sample_count, quantize_money(avg)))
    if min_wage_applied:
        steps.append("最低工资下限生效：取 %s 元" % min_wage)
    if cap_applied:
        steps.append("三倍封顶生效：基数取 %s 元（社平工资 × 倍数）"
                     % quantize_money(cap_base))
        steps.append("封顶时年限不超过上限：年限取 %s 年" % years_used)
    if formula == "none":
        steps.append("该情形无需支付经济补偿 → 金额 0")
    elif formula == "2N":
        steps.append("违法解除赔偿金 = 基数 × 年限 × 赔偿金倍数")
    elif formula == "N+1":
        steps.append("经济补偿 = 基数 × 年限；代通知金 = 上一个月工资 %s"
                     % quantize_money(last_month_wage))
    else:
        steps.append("经济补偿 = 基数 × 年限")
    return steps


__all__ = ["MILESTONE", "FORMULA_BY_GROUND", "FORMULA_CLAUSE_IDS",
           "determine_formula", "service_years_for_compensation", "compute"]