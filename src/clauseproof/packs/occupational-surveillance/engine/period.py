"""检查周期判定（迁自来源 ``engine.period``）。

判据是 current_exam_date vs last_exam_date + N 月，**不做「今天」判定**；
due 当日检查计入合规；无基线（首次检查）记 no_baseline，不报超期；
月加法自写（零依赖），月末夹取。
"""

import calendar
import datetime as _dt

from ..model import (PERIOD_COMPLIANT, PERIOD_DUE, PERIOD_NOT_APPLICABLE,
                     PERIOD_OVERDUE, PERIOD_PENDING_INPUT, PERIOD_NO_BASELINE,
                     parse_iso_date)


def _clamp_day(year, month, day):
    last = calendar.monthrange(year, month)[1]
    return min(day, last)


def add_months(value, months):
    if isinstance(value, str):
        value = parse_iso_date(value)
    if not isinstance(value, _dt.date):
        raise TypeError("add_months 需要 date 或 ISO 字符串，实际 %r" % (value,))
    if not isinstance(months, int) or months < 0:
        raise ValueError("months 必须是非负整数，实际 %r" % (months,))
    total = value.month - 1 + months
    year = value.year + total // 12
    month = total % 12 + 1
    return _dt.date(year, month, _clamp_day(year, month, value.day))


def judge_period(period_rule, last_exam_date=None, current_exam_date=None):
    kind = period_rule.get("kind")
    result = {"verdict": "", "due_date": None, "months": None, "note": ""}
    if kind == "pending":
        result["verdict"] = PERIOD_PENDING_INPUT
        result["note"] = "周期条目尚未核对，不参与判定"
        return result
    if kind == "input_required":
        result["verdict"] = PERIOD_PENDING_INPUT
        result["note"] = period_rule.get("basis") or "周期需按具体情况确定（规则包不承载）"
        return result
    if kind == "none":
        result["verdict"] = PERIOD_NOT_APPLICABLE
        result["note"] = "该危害因素无检查周期要求"
        return result
    if kind != "months":
        raise ValueError("未知周期类型 %r" % (kind,))
    months = period_rule.get("value")
    if not isinstance(months, int) or months <= 0:
        raise ValueError("period.value 必须是正整数月数，实际 %r" % (months,))
    result["months"] = months
    if last_exam_date is None:
        result["verdict"] = PERIOD_NO_BASELINE
        result["note"] = "无上次检查记录（首次检查），不判超期"
        return result
    last = parse_iso_date(last_exam_date, "last_exam_date")
    current = parse_iso_date(current_exam_date, "current_exam_date")
    due = add_months(last, months)
    result["due_date"] = due.isoformat()
    if current < due:
        result["verdict"] = PERIOD_COMPLIANT
    elif current == due:
        result["verdict"] = PERIOD_DUE
    else:
        result["verdict"] = PERIOD_OVERDUE
        result["note"] = "距上次检查 %d 天，超过规则包规定周期" % (current - due).days
    return result


def is_period_noncompliant(period_verdict):
    return period_verdict == PERIOD_OVERDUE


__all__ = ["add_months", "judge_period", "is_period_noncompliant"]