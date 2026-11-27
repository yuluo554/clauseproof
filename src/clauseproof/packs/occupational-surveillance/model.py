"""领域数据模型：输入契约（只读解析）与结果对象（迁自来源 ``model``）。

输入解析做字段级校验并抛 ``InputError``（携带原因码），不静默丢弃字段。
"""

import datetime as _dt
from decimal import Decimal, InvalidOperation

from .errors import InputError

EXAM_TYPES = ("pre_placement", "periodic", "post_placement", "emergency")
EXAM_TYPE_LABELS = {
    "pre_placement": "上岗前",
    "periodic": "在岗期间",
    "post_placement": "离岗时",
    "emergency": "应急",
}

VERDICT_COMPLIANT = "compliant"
VERDICT_PARTIAL = "partial"
VERDICT_NON_COMPLIANT = "non_compliant"
VERDICT_NOT_APPLICABLE = "not_applicable"
VERDICT_UNKNOWN = "unknown"
VERDICT_FAILED = "failed"

VERDICT_LABELS = {
    VERDICT_COMPLIANT: "符合",
    VERDICT_PARTIAL: "部分符合",
    VERDICT_NON_COMPLIANT: "不符合",
    VERDICT_NOT_APPLICABLE: "不适用",
    VERDICT_UNKNOWN: "待人工确认",
    VERDICT_FAILED: "未判定",
}

NONCOMPLIANT_VERDICTS = frozenset({VERDICT_PARTIAL, VERDICT_NON_COMPLIANT})

PERIOD_COMPLIANT = "compliant"
PERIOD_DUE = "due"
PERIOD_OVERDUE = "overdue"
PERIOD_NO_BASELINE = "no_baseline"
PERIOD_NOT_APPLICABLE = "not_applicable"
PERIOD_PENDING_INPUT = "input_required"
PERIOD_LABELS = {
    PERIOD_COMPLIANT: "未超期",
    PERIOD_DUE: "恰好到期（当日检查视为合规）",
    PERIOD_OVERDUE: "已超期",
    PERIOD_NO_BASELINE: "无基线（首次检查）",
    PERIOD_NOT_APPLICABLE: "无周期要求",
    PERIOD_PENDING_INPUT: "待输入",
}


def parse_iso_date(value, field="exam_date"):
    if isinstance(value, _dt.date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise InputError("字段 %s 必须是 ISO-8601 日期字符串（如 2026-09-15）" % field)
    text = value.strip()
    try:
        return _dt.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise InputError("字段 %s 不是合法 ISO-8601 日期 %r：%s" % (field, text, exc))


def parse_decimal(value, field):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InputError("字段 %s 不是合法数值 %r：%s" % (field, value, exc))


def _require(obj, key, kind=None):
    if key not in obj or obj[key] is None:
        raise InputError("缺少必填字段 %s" % key)
    if kind is not None:
        for k in (kind,) if isinstance(kind, type) else kind:
            if isinstance(obj[key], k):
                return obj[key]
        raise InputError("字段 %s 类型不符（期望 %s）" % (key, kind))
    return obj[key]


class FactorRef:
    __slots__ = ("factor_code", "exposure_value", "exposure_unit", "years")

    def __init__(self, factor_code, exposure_value=None, exposure_unit=None, years=None):
        self.factor_code = factor_code
        self.exposure_value = exposure_value
        self.exposure_unit = exposure_unit
        self.years = years

    def as_dict(self):
        return {
            "factor_code": self.factor_code,
            "exposure_value": None if self.exposure_value is None else str(self.exposure_value),
            "exposure_unit": self.exposure_unit,
            "years": self.years,
        }


class PositionProfile:
    __slots__ = ("position_id", "position_name", "employer_id", "exam_date",
                 "factors", "last_exam_dates")

    def __init__(self, position_id, exam_date, factors, position_name="",
                 employer_id="", last_exam_dates=None):
        self.position_id = position_id
        self.position_name = position_name
        self.employer_id = employer_id
        self.exam_date = exam_date
        self.factors = factors
        self.last_exam_dates = last_exam_dates or {}

    @property
    def factor_codes(self):
        return [f.factor_code for f in self.factors]

    @classmethod
    def from_dict(cls, obj):
        if not isinstance(obj, dict):
            raise InputError("岗位画像必须是 JSON 对象")
        position_id = str(_require(obj, "position_id", str)).strip()
        exam_date = parse_iso_date(_require(obj, "exam_date"), "exam_date")
        raw_factors = _require(obj, "factors", list)
        if not raw_factors:
            raise InputError("岗位画像的 factors 不得为空")
        factors = []
        for idx, raw in enumerate(raw_factors):
            if not isinstance(raw, dict):
                raise InputError("factors[%d] 必须是对象" % idx)
            code = str(_require(raw, "factor_code", str)).strip()
            exposure = raw.get("exposure") or {}
            if exposure and not isinstance(exposure, dict):
                raise InputError("factors[%d].exposure 必须是对象" % idx)
            value = parse_decimal(exposure.get("value"),
                                  "factors[%d].exposure.value" % idx)
            unit = exposure.get("unit")
            years = raw.get("years")
            if years is not None and not isinstance(years, int):
                raise InputError("factors[%d].years 必须是整数" % idx)
            factors.append(FactorRef(code, value, unit, years))
        last = obj.get("last_exam_dates") or {}
        if not isinstance(last, dict):
            raise InputError("last_exam_dates 必须是对象")
        last_dates = {}
        for key, value in last.items():
            if key not in EXAM_TYPES:
                raise InputError(
                    "last_exam_dates 含未知检查时点 %r（合法值：%s）"
                    % (key, ", ".join(EXAM_TYPES)))
            last_dates[key] = parse_iso_date(value, "last_exam_dates.%s" % key)
        return cls(position_id=position_id, exam_date=exam_date, factors=factors,
                   position_name=str(obj.get("position_name") or ""),
                   employer_id=str(obj.get("employer_id") or ""),
                   last_exam_dates=last_dates)


class HealthRecord:
    __slots__ = ("record_id", "employee_id", "employee_name", "position_id",
                 "factor_code", "exam_date", "exam_type", "items",
                 "conclusion_code", "notified_suspected", "employer_id",
                 "last_exam_date")

    def __init__(self, record_id, employee_id, position_id, factor_code, exam_date,
                 exam_type, items, conclusion_code="", notified_suspected=False,
                 employee_name="", employer_id="", last_exam_date=None):
        self.record_id = record_id
        self.employee_id = employee_id
        self.employee_name = employee_name
        self.employer_id = employer_id
        self.position_id = position_id
        self.factor_code = factor_code
        self.exam_date = exam_date
        self.exam_type = exam_type
        self.items = list(items)
        self.conclusion_code = conclusion_code
        self.notified_suspected = bool(notified_suspected)
        self.last_exam_date = last_exam_date

    @classmethod
    def from_dict(cls, obj):
        if not isinstance(obj, dict):
            raise InputError("监护档案必须是 JSON 对象")
        exam_type = str(_require(obj, "exam_type", str)).strip()
        if exam_type not in EXAM_TYPES:
            raise InputError(
                "exam_type %r 不识别（合法值：%s）"
                % (exam_type, ", ".join(EXAM_TYPES)), reason="unknown_exam_type")
        raw_items = _require(obj, "items", list)
        items = []
        for idx, item in enumerate(raw_items):
            if not isinstance(item, str):
                if isinstance(item, dict) and item.get("item_code"):
                    item = item["item_code"]
                else:
                    raise InputError("items[%d] 必须是项目代码字符串" % idx)
            items.append(str(item).strip())
        last = obj.get("last_exam_date")
        return cls(
            record_id=str(_require(obj, "record_id", str)).strip(),
            employee_id=str(_require(obj, "employee_id", str)).strip(),
            position_id=str(obj.get("position_id") or "").strip(),
            factor_code=str(_require(obj, "factor_code", str)).strip(),
            exam_date=parse_iso_date(_require(obj, "exam_date"), "exam_date"),
            exam_type=exam_type,
            items=items,
            conclusion_code=str(obj.get("conclusion_code") or ""),
            notified_suspected=obj.get("notified_suspected", False),
            employee_name=str(obj.get("employee_name") or ""),
            employer_id=str(obj.get("employer_id") or ""),
            last_exam_date=parse_iso_date(last, "last_exam_date") if last else None,
        )


class Applicability:
    __slots__ = ("state", "reason", "basis")

    def __init__(self, state, reason="", basis=""):
        self.state = state
        self.reason = reason
        self.basis = basis

    def as_dict(self):
        return {"state": self.state, "reason": self.reason, "basis": self.basis}


class ExamPlan:
    __slots__ = ("exam_type", "required_items", "supplementary_items",
                 "optional_items", "basis", "item_bases", "item_sources")

    def __init__(self, exam_type, required_items, supplementary_items, optional_items,
                 basis="", item_bases=None, item_sources=None):
        self.exam_type = exam_type
        self.required_items = list(required_items)
        self.supplementary_items = list(supplementary_items)
        self.optional_items = list(optional_items)
        self.basis = basis
        self.item_bases = dict(item_bases or {})
        self.item_sources = dict(item_sources or {})

    def item_basis(self, item_code):
        return self.item_bases.get(item_code) or self.basis

    def item_source(self, item_code):
        return dict(self.item_sources.get(item_code) or {})

    def as_dict(self):
        return {
            "exam_type": self.exam_type,
            "required_items": list(self.required_items),
            "supplementary_items": list(self.supplementary_items),
            "optional_items": list(self.optional_items),
            "basis": self.basis,
            "item_bases": dict(self.item_bases),
            "item_sources": {k: dict(v) for k, v in sorted(self.item_sources.items())},
        }


class FactorPlan:
    __slots__ = ("factor_code", "factor_name", "applicability", "exams",
                 "period", "basis")

    def __init__(self, factor_code, factor_name, applicability, exams, period, basis=""):
        self.factor_code = factor_code
        self.factor_name = factor_name
        self.applicability = applicability
        self.exams = dict(exams)
        self.period = period
        self.basis = basis

    def as_dict(self):
        return {
            "factor_code": self.factor_code,
            "factor_name": self.factor_name,
            "applicability": self.applicability.as_dict(),
            "exams": {k: v.as_dict() for k, v in sorted(self.exams.items())},
            "period": self.period,
            "basis": self.basis,
        }


class PlanResult:
    __slots__ = ("ruleset_id", "position_id", "factors", "missing_inputs",
                 "trace", "notes")

    def __init__(self, ruleset_id, position_id, factors, missing_inputs=None,
                 trace=None, notes=None):
        self.ruleset_id = ruleset_id
        self.position_id = position_id
        self.factors = list(factors)
        self.missing_inputs = list(missing_inputs or [])
        self.trace = list(trace or [])
        self.notes = list(notes or [])

    def as_dict(self):
        return {
            "ruleset_id": self.ruleset_id,
            "position_id": self.position_id,
            "factors": [f.as_dict() for f in self.factors],
            "missing_inputs": list(self.missing_inputs),
            "trace": list(self.trace),
            "notes": list(self.notes),
        }


class CoverageResult:
    __slots__ = ("record_id", "employee_id", "position_id", "factor_code",
                 "exam_type", "verdict", "missing_items", "extra_items",
                 "unmapped_items", "period_verdict", "findings", "trace",
                 "failed_reason", "failed_message")

    def __init__(self, record_id, employee_id="", factor_code="", exam_type="",
                 verdict=VERDICT_UNKNOWN, missing_items=None, extra_items=None,
                 unmapped_items=None, period_verdict="", findings=None, trace=None,
                 failed_reason="", failed_message="", position_id=""):
        self.record_id = record_id
        self.employee_id = employee_id
        self.position_id = position_id
        self.factor_code = factor_code
        self.exam_type = exam_type
        self.verdict = verdict
        self.missing_items = list(missing_items or [])
        self.extra_items = list(extra_items or [])
        self.unmapped_items = list(unmapped_items or [])
        self.period_verdict = period_verdict
        self.findings = list(findings or [])
        self.trace = list(trace or [])
        self.failed_reason = failed_reason
        self.failed_message = failed_message

    @property
    def is_noncompliant(self):
        return self.verdict in NONCOMPLIANT_VERDICTS

    def as_dict(self):
        return {
            "record_id": self.record_id,
            "employee_id": self.employee_id,
            "position_id": self.position_id,
            "factor_code": self.factor_code,
            "exam_type": self.exam_type,
            "verdict": self.verdict,
            "verdict_label": VERDICT_LABELS.get(self.verdict, self.verdict),
            "missing_items": list(self.missing_items),
            "extra_items": list(self.extra_items),
            "unmapped_items": list(self.unmapped_items),
            "period_verdict": self.period_verdict,
            "findings": list(self.findings),
            "trace": list(self.trace),
            "failed_reason": self.failed_reason,
            "failed_message": self.failed_message,
        }


__all__ = ["EXAM_TYPES", "EXAM_TYPE_LABELS", "VERDICT_COMPLIANT", "VERDICT_PARTIAL",
           "VERDICT_NON_COMPLIANT", "VERDICT_NOT_APPLICABLE", "VERDICT_UNKNOWN",
           "VERDICT_FAILED", "VERDICT_LABELS", "NONCOMPLIANT_VERDICTS",
           "PERIOD_COMPLIANT", "PERIOD_DUE", "PERIOD_OVERDUE", "PERIOD_NO_BASELINE",
           "PERIOD_NOT_APPLICABLE", "PERIOD_PENDING_INPUT", "PERIOD_LABELS",
           "parse_iso_date", "parse_decimal", "FactorRef", "PositionProfile",
           "HealthRecord", "Applicability", "ExamPlan", "FactorPlan", "PlanResult",
           "CoverageResult"]