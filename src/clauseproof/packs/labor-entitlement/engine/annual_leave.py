"""未休年休假折算引擎（迁自来源 ``engine.annual_leave``）。

应休天数按累计工作年限分档（常数包）；当年度折算 = 已过日历天数（含终止当日）
÷ 年天数 × 应休；未休天数 = floor(折算应休 − 已安排)，下限 0；另付金额 =
日工资 × 未休天数 ×（未休倍数 − 已付比例）。
"""

from datetime import date
from decimal import Decimal, ROUND_FLOOR

from ..decimalutil import quantize_money
from ..errors import InputError

MILESTONE = "M3"

_ZERO = Decimal(0)

_BASIS = ["ALR-3", "ALR-5", "MOHRSS-ORDER-1-ART10", "MOHRSS-ORDER-1-ART11",
          "MOHRSS-ORDER-1-ART12"]


def _entitlement_days(service_years, ruleset):
    for tier in ruleset.entitlement_tiers():
        low = tier["min_service_years"]
        high = tier["max_service_years_exclusive"]
        if service_years >= low and (high is None or service_years < high):
            return tier["days"]
    return _ZERO


def _monthly_average(wages, ruleset):
    window = int(ruleset.avg_wage_months())
    sample = wages[-window:] if len(wages) > window else wages
    return sum(sample) / Decimal(len(sample))


def compute(facts, ruleset):
    """计算未休年休假折算；返回天数 + 日工资 + 应付金额 + 条款依据。"""
    terminate_date = facts.terminate_date
    if terminate_date is None:
        raise InputError("年休假折算需要 terminate_date（当年度折算终点）")
    wages = list(facts.monthly_wages)
    if not wages:
        raise InputError("年休假折算需要 monthly_wages（月工资序列）")
    entitlement = _entitlement_days(facts.cumulative_service_years, ruleset)
    year_start = date(terminate_date.year, 1, 1)
    elapsed_days = (terminate_date - year_start).days + 1
    prorated = Decimal(elapsed_days) / ruleset.days_per_year() * entitlement
    unused_raw = prorated - facts.annual_leave_taken_days
    unused_days = unused_raw.to_integral_value(rounding=ROUND_FLOOR)
    if unused_days < _ZERO:
        unused_days = _ZERO
    monthly = _monthly_average(wages, ruleset)
    daily = monthly / ruleset.monthly_pay_days()
    payable_total = daily * unused_days * ruleset.unused_multiple()
    already_paid = daily * unused_days * ruleset.already_paid_portion()
    additional = payable_total - already_paid
    steps = _build_steps(entitlement, elapsed_days, prorated,
                         facts.annual_leave_taken_days, unused_days, monthly, daily,
                         additional)
    return {
        "entitlement_days": entitlement,
        "prorated_days": prorated,
        "taken_days": facts.annual_leave_taken_days,
        "unused_days": unused_days,
        "daily_wage": daily,
        "monthly_wage": quantize_money(monthly),
        "payable_total": quantize_money(payable_total),
        "already_paid": quantize_money(already_paid),
        "additional_due": quantize_money(additional),
        "amount": quantize_money(additional),
        "steps": steps,
        "basis": list(_BASIS),
    }


def _build_steps(entitlement, elapsed_days, prorated, taken, unused, monthly, daily,
                 additional):
    steps = ["年度应休天数（按累计工作年限分档）：%s 天" % entitlement]
    steps.append("当年度已过日历天数：%d 天 → 折算应休 %.6f 天"
                 % (elapsed_days, prorated))
    steps.append("扣除当年度已安排 %s 天后，应休未休天数（向下取整）= %s 天"
                 % (taken, unused))
    steps.append("日工资 = 月平均应得工资 %s 元 ÷ 月计薪天数 = %s 元"
                 % (quantize_money(monthly), daily))
    steps.append("未休年休假工资报酬（另付部分）= 日工资 × 未休天数 ×（未休倍数 − 已付比例）= %s 元"
                 % quantize_money(additional))
    return steps


__all__ = ["MILESTONE", "compute"]