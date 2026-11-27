"""加班费引擎（迁自来源 ``engine.overtime``）。

计算基数 = 解除前 N 个月平均应得工资（低于最低工资取下限）；小时工资 = 基数 ÷
（月计薪天数 × 日标准工时）；日期类型由**该年度该地区**节假日日历单点判定；
倍率三档全部取自常数包；显式 ``kind`` 覆盖日历判定。
"""

from decimal import Decimal

from ..decimalutil import quantize_money
from ..errors import InputError

MILESTONE = "M3"

_ZERO = Decimal(0)

#: 日历日期类型 → 倍率档位（档位名取自常数包）
RATE_KIND_BY_DAY_TYPE = {
    "statutory_holiday": "statutory_holiday",
    "rest_day": "rest_day_no_compensatory",
    "adjusted_workday": "rest_day_no_compensatory",
    "workday": "workday_extension",
}

_KIND_TO_DAY_TYPE = {
    "workday_extension": "workday",
    "rest_day": "rest_day",
    "statutory_holiday": "statutory_holiday",
}

_BASIS = ["LL-44", "LL-36"]


def _monthly_average(wages, ruleset):
    window = int(ruleset.avg_wage_months())
    sample = wages[-window:] if len(wages) > window else wages
    return sum(sample) / Decimal(len(sample))


def _day_type_for(item, ruleset):
    kind = getattr(item, "kind", "auto")
    if kind == "auto":
        return ruleset.holiday_day_type(item.date.isoformat()), "calendar"
    return _KIND_TO_DAY_TYPE[kind], "explicit"


def compute(facts, ruleset):
    """计算加班费；返回逐条明细 + 合计 + 过程 + 条款依据。"""
    wages = list(facts.monthly_wages)
    if not wages:
        raise InputError("加班费计算需要 monthly_wages（月工资序列）")
    base = _monthly_average(wages, ruleset)
    min_wage = ruleset.min_wage_monthly()
    min_wage_applied = base < min_wage
    if min_wage_applied:
        base = min_wage
    hourly = base / ruleset.monthly_pay_days() / ruleset.overtime_standard_daily_hours()
    entries = []
    total = _ZERO
    for item in facts.overtime:
        day_type, source = _day_type_for(item, ruleset)
        rate = ruleset.overtime_rate(RATE_KIND_BY_DAY_TYPE[day_type])
        amount = hourly * item.hours * rate
        total = total + amount
        entries.append({
            "date": item.date.isoformat(),
            "day_type": day_type,
            "rate": rate,
            "hours": item.hours,
            "entry_amount": quantize_money(amount),
            "day_type_source": source,
        })
    steps = _build_steps(base, min_wage_applied, min_wage, hourly, entries, total)
    return {
        "hourly_base": hourly,
        "min_wage_applied": min_wage_applied,
        "entries": entries,
        "total": quantize_money(total),
        "amount": quantize_money(total),
        "work_system": getattr(facts, "work_system", "standard"),
        "steps": steps,
        "basis": list(_BASIS),
    }


def _build_steps(base, min_wage_applied, min_wage, hourly, entries, total):
    steps = ["加班基数：月平均应得工资 = %s 元" % quantize_money(base)]
    if min_wage_applied:
        steps.append("最低工资下限生效：基数取 %s 元" % min_wage)
    steps.append("小时工资 = 基数 ÷（月计薪天数 × 日标准工时）= %s"
                 % quantize_money(hourly))
    steps.append("逐条按日历日期类型取倍率：%d 条" % len(entries))
    steps.append("加班费合计 = %s" % quantize_money(total))
    return steps


__all__ = ["MILESTONE", "RATE_KIND_BY_DAY_TYPE", "compute"]