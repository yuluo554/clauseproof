"""编排层（迁自来源 ``pipeline``）：唯一编排源。

职责：解析输入 → 按坐标加载参数包 → 门控 → 调用四引擎 → 汇总结果。
判定逻辑一律不下沉到本层；器官入口 ``evaluate`` 只把结果转成判定账本行。
"""

from dataclasses import dataclass, field

from . import params as params_module
from .engine import annual_leave as annual_leave_engine
from .engine import double_wage as double_wage_engine
from .engine import overtime as overtime_engine
from .engine import severance as severance_engine
from .errors import LccError
from .gate import effective_ruleset, pending_entries
from .model import CaseInput

DISCLAIMER = (
    "免责声明：本测算结果仅供参考，不构成法律意见；正式结论以劳动仲裁/法院裁判为准。"
    "所有计算均在本地完成，不上传任何数据。"
)

MODULES = ("severance", "overtime", "annual_leave", "double_wage")

_MODULE_LABELS = {
    "severance": "经济补偿/赔偿金",
    "overtime": "加班费",
    "annual_leave": "未休年休假折算",
    "double_wage": "未签书面劳动合同二倍工资",
}


@dataclass
class CalcRequest:
    case: CaseInput
    modules: tuple = MODULES
    data_dir: object = None
    preview: bool = False

    @property
    def region_code(self):
        return self.case.employment.region_code

    @property
    def year(self):
        return self.case.employment.year


@dataclass
class CalcResult:
    coordinate: tuple
    region_name: str = ""
    ruleset_status: str = ""
    case: object = None
    modules: dict = field(default_factory=dict)
    basis_ids: list = field(default_factory=list)
    param_sources: dict = field(default_factory=dict)
    notices: list = field(default_factory=list)
    disclaimer: str = DISCLAIMER
    preview: bool = False
    caliber: str = ""
    caliber_basis_year: object = None

    @property
    def has_amount(self):
        if self.preview:
            return False
        for payload in self.modules.values():
            if isinstance(payload, dict) and payload.get("amount") is not None:
                return True
        return False


def compute_full_calc(request):
    """执行一次完整计算（四模块或指定模块）；门控命中抛 ``GateError``。"""
    case = request.case
    employment = case.employment
    ruleset = params_module.load_ruleset(
        employment.region_code, employment.year, data_dir=request.data_dir)
    constants = params_module.load_constants(data_dir=request.data_dir)
    preview = bool(request.preview) and bool(pending_entries(ruleset, constants))
    effective = effective_ruleset(ruleset, constants, allow_pending=preview,
                                  data_dir=request.data_dir)
    result = CalcResult(
        coordinate=effective.coordinate,
        region_name=effective.region_name,
        ruleset_status=ruleset.status,
        case=case,
        preview=preview,
    )
    if preview:
        result.notices.append(
            "预览模式：参数条目存在未核对（pending）项，仅展示参数元信息，不输出任何金额结论。")
    result.param_sources = {
        "social_avg_wage_monthly": effective.param_source("social_avg_wage_monthly"),
        "min_wage_monthly": effective.param_source("min_wage_monthly"),
        "holiday_calendar": effective.param_source("holiday_calendar"),
    }
    result.caliber = effective.social_avg_wage_caliber()
    result.caliber_basis_year = effective.social_avg_wage_basis_year()
    if preview:
        return result
    basis_ids = []
    for name in request.modules:
        if name == "severance":
            if case.termination is None:
                result.notices.append("未提供 termination 段，跳过经济补偿/赔偿金计算。")
                continue
            payload = severance_engine.compute(employment, case.termination, effective)
        elif name == "overtime":
            payload = overtime_engine.compute(employment, effective)
        elif name == "annual_leave":
            payload = annual_leave_engine.compute(employment, effective)
        elif name == "double_wage":
            payload = double_wage_engine.compute(employment, effective)
        else:
            raise LccError("未知计算模块 %r" % (name,))
        result.modules[name] = payload
        basis_ids.extend(list(payload.get("basis") or []))
    result.basis_ids = _unique(basis_ids)
    return result


def _unique(items):
    unique = []
    for item in items:
        if item not in unique:
            unique.append(item)
    return unique


def module_label(name):
    return _MODULE_LABELS.get(name, name)


def build_case(raw):
    return CaseInput.from_dict(raw)


def build_request(case, modules=None, data_dir=None, preview=False):
    if modules is None:
        modules = MODULES
    return CalcRequest(case=case, modules=tuple(modules), data_dir=data_dir,
                       preview=bool(preview))


def parameter_overview(data_dir=None):
    return params_module.summarize(data_dir)


__all__ = ["DISCLAIMER", "MODULES", "CalcRequest", "CalcResult", "build_case",
           "build_request", "compute_full_calc", "module_label",
           "parameter_overview"]