"""器官 ``occupational-surveillance``：职业健康监护核查（GBZ 188 双版本）。

一句话：**给一份岗位画像和/或监护档案，判应检项目与周期、档案覆盖度、
两版标准差异，逐项挂 GBZ 条款号；未核对条目拒绝进入核查路径。**

来源判定面（监护矩阵 / 覆盖度四态 / 周期判定 / 版本锚定 / 版本对照 / status 门控）
逐条迁移；**GUI / 报告导出 / 批量扫盘 / 基准 runner / 真值库都是交付或工具面，
不迁**（器官零文件 IO——规则包由装配面 :mod:`registry` 读入，判定内核只收内存对象；
零环境变量、零时钟）。

判定账本口径（SKELETON-SPEC §3–§5）：

============================  ==========================================
来源结论                       本器官 verdict
============================  ==========================================
覆盖度 ``compliant``            ``pass``（锚点：因素条款）
覆盖度 ``partial`` / ``non_compliant``  ``fail``（锚点：因素条款；阻断 → 退出码 1）
覆盖度 ``not_applicable``       ``not_applicable``（不适用 ≠ 违规）
覆盖度 ``unknown`` / ``failed``  ``not_applicable``（非结论，不冒充合规）
矩阵适用性 ``applicable``       ``pass``（锚点：因素条款）
矩阵 ``not_applicable`` / ``input_required``  ``not_applicable``
版本差异条目                    ``pass``（锚点：因素条款 / 对照契约）
============================  ==========================================

**GBZ 口径**：GBZ 188—2025（国卫通〔2025〕10 号）自 **2026-08-01** 施行并代替
GBZ 188—2014；版本按**体检日期**锚定（切口日之前旧版、当日及之后新版）。
第 8–9 章 15 个因素仅因素身份核对、明细 pending——门控如实拦截，不静默放行
（条款 pending 在本器官 docs §2 逐条登记）。

依据只从条文库取：``basis.anchor(clause_id)``；条文库版本 = 知识库核对日期
``2026-10-14``。版本不符 → ``ContractError``（退出码 3）；条款缺失 →
``BasisMissing``（本产品内核映射退出码 2，与既有器官同口径）。
"""

from typing import Iterable, Mapping

from clauseproof.core.basis import Basis
from clauseproof.core.ledger import (
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Finding,
)
from clauseproof.core.registry import Pack, register

from . import pipeline
from . import registry as pack_data
from .engine import compare as compare_engine
from .engine import coverage as coverage_engine
from .engine import matrix as matrix_engine
from .errors import (AmbiguousYearError, GateBlocked, InputError,
                     MissingInputError, OhsCheckError)
from .model import EXAM_TYPES

SLUG = pack_data.SLUG
VERSION = pack_data.VERSION
SUMMARY = pack_data.SUMMARY

#: 输入必填字段（case_id = 一次判定运行的稳定标识；position/records/compare 三选一）
INPUT_FIELDS = ("case_id",)

RULE_PLAN = "occupational.plan"
RULE_COVERAGE = "occupational.coverage"
RULE_COMPARE = "occupational.compare"

CLAUSE_GATE = "contract.gate"
CLAUSE_COMPARE = "contract.compare"
CLAUSE_MODULE = "contract.module"

_ALLOWED_KEYS = {"position", "records", "compare", "case_id", "note"}
_INPUT_ERRORS = (OhsCheckError, AmbiguousYearError, GateBlocked, InputError,
                 MissingInputError, ValueError)


def _require_basis_version(basis: Basis) -> None:
    if basis.version != pack_data.VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据知识库核对日期 %s，条文库实为 %s"
            % (pack_data.VERSION, basis.version)
        )


def _anchor_for(basis: Basis, context, ruleset_id, factor_code):
    """因素代码 → 条文锚点（失败回落版本锚定契约）。"""
    ruleset = context.ruleset(ruleset_id)
    factor = ruleset.factor(factor_code)
    if factor is not None and basis.clause(factor["factor_id"]) is not None:
        return basis.anchor(factor["factor_id"])
    return basis.anchor("contract.version")


def _validate_subject(subject: Mapping):
    if not isinstance(subject, Mapping):
        raise ValueError("输入必须是 JSON 对象")
    unknown = sorted(set(subject) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError("输入含未知字段：%s" % ", ".join(unknown))
    if not str(subject.get("case_id") or "").strip():
        raise ValueError("输入缺少 case_id（一次判定运行的稳定标识）")
    if not any(key in subject for key in ("position", "records", "compare")):
        raise ValueError("输入至少需要 position / records / compare 之一")
    return subject


def _plan_findings(subject, context, basis):
    position = subject.get("position")
    if position is None:
        return []
    profile = pipeline.build_position(position)
    result = pipeline.compute_plan(profile, context)
    findings = []
    for factor_plan in result.factors:
        anchor = _anchor_for(basis, context, result.ruleset_id,
                             factor_plan.factor_code)
        applicable = factor_plan.applicability.state == matrix_engine.STATE_APPLICABLE
        evidence = {
            "ruleset_id": result.ruleset_id,
            "position_id": profile.position_id,
            "factor_code": factor_plan.factor_code,
            "factor_name": factor_plan.factor_name,
            "applicability": factor_plan.applicability.state,
            "applicability_reason": factor_plan.applicability.reason,
            "period": dict(factor_plan.period),
            "required_items": {
                exam_type: list(exam.required_items)
                for exam_type, exam in sorted(factor_plan.exams.items())
            },
        }
        findings.append(Finding(
            rule_id="%s:%s:%s" % (RULE_PLAN, profile.position_id,
                                  factor_plan.factor_code),
            verdict=PASS if applicable else NOT_APPLICABLE,
            message=("%s：%s；应检项 %s"
                     % (factor_plan.factor_name, factor_plan.applicability.reason,
                        " / ".join("%s %d 项" % (exam_type, len(exam.required_items))
                                   for exam_type, exam in sorted(factor_plan.exams.items()))
                        if applicable else "不产出（适用性未确认）")),
            anchor=anchor,
            evidence=evidence,
        ))
    return findings


def _coverage_findings(subject, context, basis):
    records = subject.get("records") or []
    if not isinstance(records, list):
        raise ValueError("records 必须是数组")
    findings = []
    for raw in records:
        record = pipeline.build_record(raw)
        result = pipeline.compute_coverage(record, context)
        ruleset_id = pipeline.resolve_ruleset_for(record.exam_date,
                                                  context).ruleset_id
        anchor = _anchor_for(basis, context, ruleset_id, record.factor_code)
        if result.verdict == "compliant":
            verdict = PASS
        elif result.verdict in ("partial", "non_compliant"):
            verdict = FAIL
        else:
            verdict = NOT_APPLICABLE
        evidence = {
            "record_id": result.record_id,
            "employee_id": result.employee_id,
            "factor_code": result.factor_code,
            "exam_type": result.exam_type,
            "verdict": result.verdict,
            "period_verdict": result.period_verdict,
            "missing_items": list(result.missing_items),
            "unmapped_items": list(result.unmapped_items),
            "findings": list(result.findings),
            "failed_reason": result.failed_reason,
        }
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_COVERAGE, result.record_id),
            verdict=verdict,
            message=("覆盖度 %s（%s/%s）：缺项 %d 项%s"
                     % (result.verdict, result.factor_code, result.exam_type,
                        len(result.missing_items),
                        "；周期 %s" % result.period_verdict
                        if result.period_verdict else "")),
            anchor=anchor,
            evidence=evidence,
        ))
    return findings


def _compare_findings(subject, context, basis):
    spec = subject.get("compare")
    if spec is None:
        return []
    if not isinstance(spec, Mapping):
        raise ValueError("compare 必须是对象 {ruleset_a, ruleset_b}")
    unknown = sorted(set(spec) - {"ruleset_a", "ruleset_b"})
    if unknown:
        raise ValueError("compare 含未知字段：%s" % ", ".join(unknown))
    ruleset_a = spec.get("ruleset_a")
    ruleset_b = spec.get("ruleset_b")
    if not ruleset_a or not ruleset_b:
        raise ValueError("compare 需要 ruleset_a 与 ruleset_b")
    report = pipeline.compare(str(ruleset_a), str(ruleset_b), context)
    findings = []
    for entry in report.entries:
        code = str(entry.key).split("/")[0]
        side = ruleset_b if entry.kind == "factor_added" else ruleset_a
        try:
            anchor = _anchor_for(basis, context, side, code)
        except (KeyError, ValueError):
            anchor = basis.anchor(CLAUSE_COMPARE)
        findings.append(Finding(
            rule_id="%s:%s:%s" % (RULE_COMPARE, entry.kind, entry.key),
            verdict=PASS,
            message="%s（%s）%s" % (entry.label, entry.kind, entry.detail),
            anchor=anchor,
            evidence={"kind": entry.kind, "key": entry.key, "detail": entry.detail,
                      "basis_a": entry.basis_a, "basis_b": entry.basis_b},
        ))
    findings.append(Finding(
        rule_id="%s:summary" % RULE_COMPARE,
        verdict=PASS,
        message="版本对照：%s → %s，差异 %d 条"
                % (report.ruleset_a, report.ruleset_b, len(report.entries)),
        anchor=basis.anchor(CLAUSE_COMPARE),
        evidence={"entries": len(report.entries), "notes": list(report.notes),
                  "by_kind": {kind: len(report.by_kind(kind))
                              for kind in sorted({e.kind for e in report.entries})}},
    ))
    return findings


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    _require_basis_version(basis)
    _validate_subject(subject)
    try:
        context = pipeline.build_context()
        findings = []
        findings.extend(_plan_findings(subject, context, basis))
        findings.extend(_coverage_findings(subject, context, basis))
        findings.extend(_compare_findings(subject, context, basis))
    except _INPUT_ERRORS as exc:
        raise ValueError(str(exc))
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