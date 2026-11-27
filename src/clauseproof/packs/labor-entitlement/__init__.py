"""器官 ``labor-entitlement``：劳动用工权益判定（四引擎 × 地区×年度参数 × 条款锚点）。

一句话：**给一份雇佣/解除事实 + 地区×年度坐标，算经济补偿/赔偿金、加班费、
未休年休假折算、未签书面劳动合同二倍工资，逐项挂法条锚点；未核对参数拒绝
进入计算路径。**

来源四引擎（severance / overtime / annual_leave / double_wage）与参数门控逐条
迁移；**CLI/GUI/报告导出/PyInstaller 打包/真值生成器都是交付或工具面，不迁**
（器官零文件 IO——参数包由装配面 :mod:`registry` 读入，判定内核只收内存对象；
零环境变量、零时钟）。

判定账本口径（SKELETON-SPEC §3–§5）：

============================  ==========================================
来源结论                       本器官 verdict
============================  ==========================================
模块计算完成（有金额）           ``pass``（锚点：该模块法条条款；金额入 evidence）
模块因缺事实跳过                 ``not_applicable``（锚点：数据契约）
预览模式（pending，不出金额）     ``not_applicable``（锚点：状态门控契约）
status 门控拦截（非预览）         ``ValueError`` → 退出码 2（与来源 2 一致）
============================  ==========================================

**与 ``income-tax``（#10）的边界**：本器官判「劳动关系解除/加班/年休假/书面合同」
的用人单位给付义务，参数是**地区×年度**社平工资/最低工资/节假日日历；``income-tax``
判「个人所得税」的预扣/汇算/专项附加扣除/年终奖，参数是**年度**个税规则包。
两者 slug / 规则代码（``labor.*`` vs ``tax.*``）/ 测试零复用；社保联动只在
``income-tax``（个税口径），本器官不做社保代扣。

依据只从条文库取：``basis.anchor(clause_id)``；条文库版本 = 参数包核对日期
``2026-10-13``。版本不符 → ``ContractError``（退出码 3）；条款缺失 →
``BasisMissing``（本产品内核映射退出码 2，与既有器官同口径）。
"""

from typing import Iterable, Mapping, Tuple

from clauseproof.core.basis import Basis
from clauseproof.core.ledger import (
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Finding,
)
from clauseproof.core.registry import Pack, register

from . import pipeline
from . import registry as pack_data
from .errors import (
    ComputationError,
    GateError,
    InputError,
    LccError,
    ParamCoordinateError,
    ParamSchemaError,
)
from .model import CaseInput

SLUG = pack_data.SLUG
VERSION = pack_data.VERSION
SUMMARY = pack_data.SUMMARY

#: 输入必填字段（employment = 雇佣事实；termination / modules / preview 可选）
INPUT_FIELDS = ("employment",)

RULE_SEVERANCE = "labor.severance"
RULE_OVERTIME = "labor.overtime"
RULE_ANNUAL_LEAVE = "labor.annual_leave"
RULE_DOUBLE_WAGE = "labor.double_wage"

_RULE_BY_MODULE = {
    "severance": RULE_SEVERANCE,
    "overtime": RULE_OVERTIME,
    "annual_leave": RULE_ANNUAL_LEAVE,
    "double_wage": RULE_DOUBLE_WAGE,
}

#: 模块结果锚点（数据契约 / 法条）
MODULE_CLAUSE = {
    "severance": "LCL-47",
    "overtime": "LL-44",
    "annual_leave": "ALR-3",
    "double_wage": "LCL-82",
}

#: 经济补偿口径 → 法条锚点（``none`` 无给付义务，挂口径契约）
FORMULA_CLAUSE = {
    "N": "LCL-47",
    "N+1": "LCL-40",
    "2N": "LCL-87",
    "none": "contract.caliber",
}

CLAUSE_GATE = "contract.gate"
CLAUSE_MODULE = "contract.module"

_ALLOWED_KEYS = {"employment", "termination", "modules", "preview", "case_id", "note"}

#: 来源异常 → 器官契约（输入不合法 = ValueError → 退出码 2）
_INPUT_ERRORS = (
    InputError,
    ParamCoordinateError,
    ParamSchemaError,
    GateError,
    ComputationError,
)


def _require_basis_version(basis: Basis) -> None:
    if basis.version != pack_data.VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据参数包核对日期 %s，条文库实为 %s"
            % (pack_data.VERSION, basis.version)
        )


def _validate_subject(subject: Mapping) -> Tuple[CaseInput, Tuple[str, ...], bool]:
    if not isinstance(subject, Mapping):
        raise ValueError("输入必须是 JSON 对象")
    unknown = sorted(set(subject) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError("输入含未知字段：%s" % ", ".join(unknown))
    if "employment" not in subject:
        raise ValueError("输入缺少 employment 段")
    modules_raw = subject.get("modules")
    if modules_raw is None:
        modules = pipeline.MODULES
    else:
        if not isinstance(modules_raw, list) or not modules_raw:
            raise ValueError("modules 必须是非空字符串数组")
        modules = tuple(str(item) for item in modules_raw)
        unknown_modules = sorted(set(modules) - set(pipeline.MODULES))
        if unknown_modules:
            raise ValueError("未知计算模块：%s" % ", ".join(unknown_modules))
    preview = bool(subject.get("preview", False))
    try:
        case = CaseInput.from_dict(subject)
    except LccError as exc:
        raise ValueError(str(exc))
    return case, modules, preview


def _module_message(name: str, payload: Mapping) -> str:
    amount = payload.get("amount")
    label = pipeline.module_label(name)
    if name == "severance":
        return ("%s：口径 %s，工作年限 %s 年，金额 %s 元"
                % (label, payload.get("formula"), payload.get("years_used"), amount))
    if name == "overtime":
        return ("%s：%d 条加班明细，合计 %s 元（小时工资基数 %s）"
                % (label, len(payload.get("entries") or []), amount,
                   payload.get("hourly_base")))
    if name == "annual_leave":
        return ("%s：应休 %s 天，未休 %s 天，另付 %s 元"
                % (label, payload.get("entitlement_days"),
                   payload.get("unused_days"), amount))
    return ("%s：%s 个月，差额 %s 元"
            % (label, payload.get("months"), amount))


def _module_evidence(name: str, payload: Mapping) -> dict:
    keys = {
        "severance": ("formula", "ground", "service_years", "years_used",
                      "monthly_wage_avg", "basis_wage", "cap_applied",
                      "min_wage_applied", "amount"),
        "overtime": ("hourly_base", "min_wage_applied", "total", "amount"),
        "annual_leave": ("entitlement_days", "prorated_days", "taken_days",
                         "unused_days", "daily_wage", "additional_due", "amount"),
        "double_wage": ("signed", "start_date", "end_date", "months",
                        "monthly_wage", "total_difference", "amount"),
    }[name]
    evidence = {"module": name, "basis_ids": list(payload.get("basis") or [])}
    for key in keys:
        value = payload.get(key)
        if value is not None:
            evidence[key] = str(value) if not isinstance(value, bool) else value
    evidence["steps"] = list(payload.get("steps") or [])
    return evidence


def _module_finding(name: str, payload: Mapping, basis: Basis) -> Finding:
    if name == "severance":
        formula = str(payload.get("formula"))
        clause_id = FORMULA_CLAUSE.get(formula, MODULE_CLAUSE["severance"])
    else:
        clause_id = MODULE_CLAUSE[name]
    return Finding(
        rule_id=_RULE_BY_MODULE[name],
        verdict=PASS,
        message=_module_message(name, payload),
        anchor=basis.anchor(clause_id),
        evidence=_module_evidence(name, payload),
    )


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    _require_basis_version(basis)
    case, modules, preview = _validate_subject(subject)
    try:
        result = pipeline.compute_full_calc(
            pipeline.build_request(case, modules=modules, preview=preview))
    except _INPUT_ERRORS as exc:
        raise ValueError(str(exc))

    findings = []
    if result.preview:
        for name in modules:
            findings.append(Finding(
                rule_id=_RULE_BY_MODULE[name],
                verdict=NOT_APPLICABLE,
                message="预览模式：%s 未输出金额（参数条目 pending，门控未放行）"
                        % pipeline.module_label(name),
                anchor=basis.anchor(CLAUSE_GATE),
                evidence={
                    "module": name,
                    "preview": True,
                    "ruleset_status": result.ruleset_status,
                    "coordinate": list(result.coordinate),
                },
            ))
        return tuple(findings)

    for name in modules:
        payload = result.modules.get(name)
        if payload is None:
            findings.append(Finding(
                rule_id=_RULE_BY_MODULE[name],
                verdict=NOT_APPLICABLE,
                message="%s 未计算：输入缺少该模块所需事实（不硬判）"
                        % pipeline.module_label(name),
                anchor=basis.anchor(CLAUSE_MODULE),
                evidence={"module": name, "skipped": True,
                          "notices": list(result.notices)},
            ))
            continue
        findings.append(_module_finding(name, payload, basis))
    return tuple(findings)


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate"]