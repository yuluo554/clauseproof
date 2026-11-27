"""输入事实模型（迁自来源 ``model``；校验失败一律 ``InputError``）。

所有金额/天数在进入引擎前已 Decimal 化；模型不可变，避免引擎误改输入。
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from .decimalutil import to_decimal
from .errors import InputError

WORK_SYSTEMS = ("standard", "comprehensive", "irregular")

TERMINATION_GROUNDS = (
    "mutual_agreement",
    "employee_fault_dismissal",
    "employer_unilateral_no_fault",
    "economic_layoff",
    "illegal_termination",
    "contract_expiry_employer_no_renewal",
    "employee_resignation_art38",
    "employee_resignation_voluntary",
)

OVERTIME_KINDS = ("workday_extension", "rest_day", "statutory_holiday")


def parse_date(value, field_name="date"):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise InputError("%s: 日期为空" % field_name)
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise InputError("%s: 日期格式非法 %r（应为 YYYY-MM-DD）" % (field_name, value))
    raise InputError("%s: 不支持的日期类型 %s" % (field_name, type(value).__name__))


@dataclass(frozen=True)
class OvertimeEntry:
    date: date
    hours: Decimal
    kind: str = "auto"

    @staticmethod
    def from_dict(raw, index=0):
        if not isinstance(raw, dict):
            raise InputError("overtime[%d]: 应为对象" % index)
        kind = str(raw.get("kind", "auto"))
        if kind != "auto" and kind not in OVERTIME_KINDS:
            raise InputError("overtime[%d]: kind 非法 %r，应为 auto 或 %s"
                             % (index, kind, "/".join(OVERTIME_KINDS)))
        hours = to_decimal(raw.get("hours", 0), "overtime[%d].hours" % index)
        if hours < 0:
            raise InputError("overtime[%d].hours 不得为负" % index)
        return OvertimeEntry(
            date=parse_date(raw.get("date"), "overtime[%d].date" % index),
            hours=hours,
            kind=kind,
        )


@dataclass(frozen=True)
class EmploymentFacts:
    region_code: str
    year: int
    hire_date: date
    terminate_date: object = None
    monthly_wages: tuple = field(default_factory=tuple)
    work_system: str = "standard"
    cumulative_service_years: Decimal = Decimal(0)
    contract_signed: bool = True
    contract_signed_date: object = None
    overtime: tuple = field(default_factory=tuple)
    annual_leave_taken_days: Decimal = Decimal(0)

    @staticmethod
    def from_dict(raw):
        if not isinstance(raw, dict):
            raise InputError("employment 事实应为对象")
        region_code = str(raw.get("region_code") or "").strip()
        if not region_code:
            raise InputError("employment.region_code 必填（地区×年度参数坐标）")
        try:
            year = int(raw.get("year"))
        except (TypeError, ValueError):
            raise InputError("employment.year 必填且为四位年度")
        hire_date = parse_date(raw.get("hire_date"), "employment.hire_date")
        terminate_date = None
        if raw.get("terminate_date"):
            terminate_date = parse_date(raw.get("terminate_date"),
                                        "employment.terminate_date")
            if terminate_date < hire_date:
                raise InputError("employment.terminate_date 早于 hire_date（日期区间倒置）")
        work_system = str(raw.get("work_system", "standard"))
        if work_system not in WORK_SYSTEMS:
            raise InputError("employment.work_system 非法 %r，应为 %s"
                             % (work_system, "/".join(WORK_SYSTEMS)))
        wages = []
        for index, item in enumerate(raw.get("monthly_wages") or []):
            value = to_decimal(item, "employment.monthly_wages[%d]" % index)
            if value < 0:
                raise InputError("employment.monthly_wages[%d] 不得为负" % index)
            wages.append(value)
        service_years = to_decimal(raw.get("cumulative_service_years", 0),
                                   "employment.cumulative_service_years")
        if service_years < 0:
            raise InputError("employment.cumulative_service_years 不得为负")
        taken = to_decimal(raw.get("annual_leave_taken_days", 0),
                           "employment.annual_leave_taken_days")
        if taken < 0:
            raise InputError("employment.annual_leave_taken_days 不得为负")
        contract_signed_date = None
        if raw.get("contract_signed_date"):
            contract_signed_date = parse_date(raw.get("contract_signed_date"),
                                              "employment.contract_signed_date")
        overtime = tuple(
            OvertimeEntry.from_dict(item, index)
            for index, item in enumerate(raw.get("overtime") or [])
        )
        return EmploymentFacts(
            region_code=region_code,
            year=year,
            hire_date=hire_date,
            terminate_date=terminate_date,
            monthly_wages=tuple(wages),
            work_system=work_system,
            cumulative_service_years=service_years,
            contract_signed=bool(raw.get("contract_signed", True)),
            contract_signed_date=contract_signed_date,
            overtime=overtime,
            annual_leave_taken_days=taken,
        )


@dataclass(frozen=True)
class TerminationFacts:
    ground: str
    notified_30d_in_advance: object = None
    employee_fault: bool = False
    mutual_agreement: bool = False

    @staticmethod
    def from_dict(raw):
        if not isinstance(raw, dict):
            raise InputError("termination 事实应为对象")
        ground = str(raw.get("ground") or "").strip()
        if ground not in TERMINATION_GROUNDS:
            raise InputError("termination.ground 非法 %r，应为 %s"
                             % (ground, " / ".join(TERMINATION_GROUNDS)))
        notified = raw.get("notified_30d_in_advance")
        if notified is not None:
            notified = bool(notified)
        return TerminationFacts(
            ground=ground,
            notified_30d_in_advance=notified,
            employee_fault=bool(raw.get("employee_fault", False)),
            mutual_agreement=bool(raw.get("mutual_agreement", False)),
        )


@dataclass(frozen=True)
class CaseInput:
    employment: EmploymentFacts
    termination: object = None

    @staticmethod
    def from_dict(raw):
        if not isinstance(raw, dict):
            raise InputError("输入应为 JSON 对象")
        if "employment" not in raw:
            raise InputError("输入缺少 employment 段")
        termination = None
        if raw.get("termination"):
            termination = TerminationFacts.from_dict(raw["termination"])
        return CaseInput(
            employment=EmploymentFacts.from_dict(raw["employment"]),
            termination=termination,
        )


__all__ = ["WORK_SYSTEMS", "TERMINATION_GROUNDS", "OVERTIME_KINDS", "parse_date",
           "OvertimeEntry", "EmploymentFacts", "TerminationFacts", "CaseInput"]