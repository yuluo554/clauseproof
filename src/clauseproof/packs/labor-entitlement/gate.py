"""status 门控（单点）与可计算规则集（迁自来源 ``gate``）。

纪律：只有本模块能产出可计算的规则集；引擎签名只接受 ``EffectiveRuleset``。
``pending`` 条目一旦进入计算路径即 ``GateError``；``allow_pending=True`` 只供
预览参数元信息，**不得据此输出任何金额**。
"""

from decimal import Decimal

from .decimalutil import to_decimal
from .errors import GateError, ParamSchemaError
from .params import STATUS_PENDING, Constants, Ruleset

_PENDING_HINT = (
    "参数条目尚未核对（status=pending），按「未挂原文核对不得进入计算路径」纪律拒绝计算。"
    "请先按数据台账逐条核对官方原文并置 status=verified。"
)


def pending_entries(ruleset, constants=None):
    pending = []
    for path, entry in sorted(ruleset.entries().items()):
        if entry.status == STATUS_PENDING:
            pending.append("ruleset.%s" % path)
    if constants is not None:
        for path, entry in sorted(constants.entries().items()):
            if entry.status == STATUS_PENDING:
                pending.append("constants.%s" % path)
    return pending


class EffectiveRuleset:
    """门控通过后的可计算规则集（引擎取数唯一来源）。"""

    __slots__ = ("_ruleset", "_constants", "_allow_pending")

    def __init__(self, ruleset, constants, allow_pending=False):
        self._ruleset = ruleset
        self._constants = constants
        self._allow_pending = bool(allow_pending)

    @property
    def region_code(self):
        return self._ruleset.region_code

    @property
    def region_name(self):
        return self._ruleset.region_name

    @property
    def year(self):
        return self._ruleset.year

    @property
    def coordinate(self):
        return (self.region_code, self.year)

    @property
    def allow_pending(self):
        return self._allow_pending

    def _param(self, name):
        entry = self._ruleset.get(name)
        if entry.status == STATUS_PENDING and not self._allow_pending:
            raise GateError("参数 %s 未核对（pending）" % entry.path, [_PENDING_HINT])
        return entry.value()

    def _const(self, path):
        entry = self._constants.get(path)
        if entry.status == STATUS_PENDING and not self._allow_pending:
            raise GateError("常数 %s 未核对（pending）" % entry.path, [_PENDING_HINT])
        return entry.value()

    def _const_entry(self, path):
        entry = self._constants.get(path)
        if entry.status == STATUS_PENDING and not self._allow_pending:
            raise GateError("常数 %s 未核对（pending）" % entry.path, [_PENDING_HINT])
        return entry

    def social_avg_wage_monthly(self):
        return to_decimal(self._param("social_avg_wage_monthly"), "social_avg_wage_monthly")

    def social_avg_wage_caliber(self):
        return str(self._ruleset.get("social_avg_wage_monthly").raw.get("caliber", ""))

    def social_avg_wage_basis_year(self):
        return self._ruleset.get("social_avg_wage_monthly").raw.get("basis_year")

    def min_wage_monthly(self):
        return to_decimal(self._param("min_wage_monthly"), "min_wage_monthly")

    def _calendar(self):
        entry = self._ruleset.get("holiday_calendar")
        if entry.status == STATUS_PENDING and not self._allow_pending:
            raise GateError("参数 %s 未核对（pending）" % entry.path, [_PENDING_HINT])

    def holiday_days(self):
        self._calendar()
        return self._ruleset.holiday_days()

    def rest_days(self):
        self._calendar()
        return self._ruleset.rest_days()

    def adjusted_workdays(self):
        self._calendar()
        return self._ruleset.adjusted_workdays()

    def holiday_day_type(self, day):
        self._calendar()
        return self._ruleset.holiday_day_type(day)

    def param_source(self, name):
        return self._ruleset.get(name).source

    # ---- 法定常数（经济补偿）
    def severance_cap_multiple(self):
        return to_decimal(self._const("severance.cap_multiple_of_social_avg"),
                          "severance.cap_multiple_of_social_avg")

    def severance_cap_years(self):
        return to_decimal(self._const("severance.cap_years"), "severance.cap_years")

    def avg_wage_months(self):
        return to_decimal(self._const("severance.avg_wage_months"),
                          "severance.avg_wage_months")

    def full_year_threshold_months(self):
        return to_decimal(self._const("severance.rounding.full_year_threshold_months"),
                          "severance.rounding.full_year_threshold_months")

    def round_up_to_year(self):
        return to_decimal(self._const("severance.rounding.round_up_to_year"),
                          "severance.rounding.round_up_to_year")

    def round_down_to_half_month(self):
        return to_decimal(self._const("severance.rounding.round_down_to_half_month"),
                          "severance.rounding.round_down_to_half_month")

    def compensation_multiple(self):
        return to_decimal(self._const("severance.compensation_multiple"),
                          "severance.compensation_multiple")

    # ---- 法定常数（加班费）
    def overtime_rate(self, kind):
        return to_decimal(self._const("overtime.rates.%s" % kind),
                          "overtime.rates.%s" % kind)

    def overtime_standard_daily_hours(self):
        return to_decimal(self._const("overtime.standard_daily_hours"),
                          "overtime.standard_daily_hours")

    # ---- 法定常数（年休假）
    def monthly_pay_days(self):
        return to_decimal(self._const("annual_leave.monthly_pay_days"),
                          "annual_leave.monthly_pay_days")

    def entitlement_tiers(self):
        tiers = []
        raw = (self._constants.raw.get("constants") or {}).get("annual_leave") or {}
        for index, tier in enumerate(raw.get("entitlement_tiers") or []):
            self._const_entry("annual_leave.entitlement_tiers[%d]" % index)
            tiers.append({
                "min_service_years": to_decimal(tier.get("min_service_years"),
                                                "min_service_years"),
                "max_service_years_exclusive": (
                    None if tier.get("max_service_years_exclusive") is None
                    else to_decimal(tier.get("max_service_years_exclusive"),
                                    "max_service_years_exclusive")
                ),
                "days": to_decimal(tier.get("days"), "days"),
                "basis": list(tier.get("basis") or []),
            })
        if not tiers:
            raise ParamSchemaError("常数包缺少 annual_leave.entitlement_tiers")
        return tiers

    def unused_multiple(self):
        return to_decimal(self._const("annual_leave.unused_multiple"),
                          "annual_leave.unused_multiple")

    def already_paid_portion(self):
        return to_decimal(self._const("annual_leave.already_paid_portion"),
                          "annual_leave.already_paid_portion")

    def days_per_year(self):
        return to_decimal(self._const("annual_leave.days_per_year"),
                          "annual_leave.days_per_year")

    # ---- 法定常数（二倍工资）
    def double_wage_start_after_months(self):
        return to_decimal(self._const("double_wage.start_after_months"),
                          "double_wage.start_after_months")

    def double_wage_max_months(self):
        return to_decimal(self._const("double_wage.max_months"),
                          "double_wage.max_months")

    def double_wage_difference_multiple(self):
        return to_decimal(self._const("double_wage.difference_multiple"),
                          "double_wage.difference_multiple")


def effective_ruleset(ruleset, constants=None, allow_pending=False, data_dir=None):
    if constants is None:
        from .params import load_constants

        constants = load_constants(data_dir)
    if not allow_pending:
        pending = pending_entries(ruleset, constants)
        if pending:
            raise GateError(
                "门控拦截：%d 个条目尚未核对（pending），不得进入计算路径" % len(pending),
                pending + [_PENDING_HINT],
            )
    return EffectiveRuleset(ruleset, constants, allow_pending=allow_pending)


__all__ = ["EffectiveRuleset", "effective_ruleset", "pending_entries"]