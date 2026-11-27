"""器官 ``safety-fee``：安全生产费用提取与使用核查。

一句话：**给一份企业档案（行业/年度/计提依据量），按财资〔2022〕136号
（或历史年度锚定的财企〔2012〕16号）判计提依据、算应计提金额（产量/超额累退/
比例、逐段量化），逐笔核查支出范围四态、判使用进度披露义务，并给出双版本差异；
结论旁挂条款锚点。**

来源判定面（计提机制 / 超额累退分段 / 依据选择 / 单位换算 / status 门控 /
支出范围四态 / 使用进度 / 双版本对照）逐条迁移；**批量扫描与跨年对账、报告导出
（MD/XLSX）、GUI、真值基准 runner、数据生成器都是交付或工具面，不迁**
（器官零文件 IO——规则包由装配面 :mod:`pipeline` 读入，判定内核只收内存对象；
零环境变量、零时钟）。

判定账本口径（SKELETON-SPEC §3–§5）：

===============================  ==============================================
来源结论                         本器官 verdict
===============================  ==============================================
规则包坐标（每次运行一条）          ``pass``（锚点：规则包契约）
计提计算成功（含依据选择留痕）      ``pass``（锚点：行业/变体条款）
门控拦截（pending / 未核对）        ``fail``（阻断 → 退出码 1，与来源 rc 1 一致）
支出 ``符合`` / ``部分符合``        ``pass``（锚点：支出条目条款）
支出 ``不符合``（红线）             ``fail``（阻断 → 退出码 1）
支出 ``未评估``                    ``not_applicable``（无锚点；不冒充"符合"）
使用进度（须披露 / 不需披露）        ``pass``（非阻断结论；锚点：进度条款）
进度 ``不适用``（应计提 0）         ``not_applicable``
双版本差异对照                     ``pass``（锚点：对照契约）
汇总（有阻断 / 无）                 ``fail`` / ``pass``
===============================  ==============================================

依据只从条文库取：``basis.anchor(clause_id)``。条文库版本 = 依据基准日
``2026-10-14``。版本不符 / 锚点缺失 → ``ContractError``（退出码 3）。
档案缺必填字段或依据选择属性 → ``ValueError``（退出码 2，与来源一致）。
"""

from decimal import Decimal
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

from . import pipeline, registry, spending
from .errors import FeeError

SLUG = registry.SLUG
VERSION = registry.VERSION
SUMMARY = registry.SUMMARY

#: 输入必填字段
INPUT_FIELDS = ("case_id",)

RULE_RULES = "fee.rules"
RULE_GATE = "fee.gate"
RULE_BASIS = "fee.basis"
RULE_ACCRUAL = "fee.accrual"
RULE_SPENDING = "fee.spending"
RULE_PROGRESS = "fee.progress"
RULE_DIFF = "fee.diff"
RULE_SUMMARY = "fee.summary"

CLAUSE_VERSION = "contract.version"
CLAUSE_RULES = "contract.rules"
CLAUSE_GATE = "contract.gate"
CLAUSE_ACCRUAL = "contract.accrual"
CLAUSE_BASIS = "contract.basis"
CLAUSE_TIERED = "contract.tiered"
CLAUSE_UNITS = "contract.units"
CLAUSE_SPENDING = "contract.spending"
CLAUSE_NOT_ASSESSED = "contract.not_assessed"
CLAUSE_PROGRESS = "contract.progress"
CLAUSE_DIFF = "contract.diff"
CLAUSE_INPUT = "contract.input"
CLAUSE_SUMMARY = "contract.summary"

_ALLOWED_KEYS = {"case_id", "profile", "ledger", "progress", "compare", "note"}


def _require_basis_version(basis: Basis) -> None:
    if basis.version != VERSION:
        raise ContractError("条文库版本不符：本器官依据基准日 %s，条文库实为 %s"
                            % (VERSION, basis.version))


def _anchor(basis: Basis, clause_id: str):
    if basis.clause(clause_id) is None:
        raise ContractError("条文库缺少本器官的必要条款：%s" % clause_id)
    return basis.anchor(clause_id)


def _industry_clause(version: str, industry_id: str) -> str:
    return "fee:%s:industry:%s" % (version, industry_id)


def _variant_clause(version: str, industry_id: str, variant_id: str) -> str:
    return "fee:%s:variant:%s:%s" % (version, industry_id, variant_id)


def _basis_clause(version: str, kind: str) -> str:
    return "fee:%s:basis:%s" % (version, kind)


def _progress_clause(version: str, threshold_id: str) -> str:
    return "fee:%s:progress:%s" % (version, threshold_id)


def _spending_clause(version: str, entry_id: str) -> str:
    return "fee:%s:spending:%s" % (version, entry_id)


def _validate_subject(subject: Mapping) -> Mapping:
    if not isinstance(subject, Mapping):
        raise ValueError("输入必须是 JSON 对象")
    unknown = sorted(set(subject) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError("输入含未知字段：%s" % ", ".join(unknown))
    if not str(subject.get("case_id") or "").strip():
        raise ValueError("输入缺少 case_id（一次判定运行的稳定标识）")
    if not isinstance(subject.get("profile"), Mapping):
        raise ValueError("输入缺少 profile（企业档案对象）")
    ledger = subject.get("ledger")
    if ledger is not None and not isinstance(ledger, list):
        raise ValueError("ledger 必须是数组")
    progress = subject.get("progress")
    if progress is not None and not isinstance(progress, Mapping):
        raise ValueError("progress 必须是对象 {used, accrued?, threshold_id?}")
    compare = subject.get("compare")
    if compare is not None and not isinstance(compare, (bool, Mapping)):
        raise ValueError("compare 必须是布尔值或 {from_year, to_year}")
    return subject


def _load_context():
    try:
        return pipeline.context()
    except FeeError as exc:
        raise ValueError("规则包不可用：%s" % exc)


def _rules_finding(ctx, basis: Basis) -> Finding:
    refs = ctx.manifest.refs
    counts = []
    for ref in refs:
        ruleset = ctx.ruleset(ref)
        counts.append("%s（%s：行业 %d）" % (ref.doc_no, ref.version,
                                            len(ruleset.get("industries", []))))
    return Finding(
        rule_id=RULE_RULES,
        verdict=PASS,
        message=("规则包：%s；复核周期 %s / 下次复核 %s"
                 % ("；".join(counts), ctx.manifest.review_interval or "未登记",
                    ctx.manifest.next_review or "未登记")),
        anchor=_anchor(basis, CLAUSE_RULES),
        evidence={
            "rulesets": [ref.as_dict() for ref in refs],
            "review_interval": ctx.manifest.review_interval,
            "next_review": ctx.manifest.next_review,
        },
    )


def _gate_finding(scope: str, gate, basis: Basis) -> Finding:
    blockers = gate.blockers
    detail = "；".join("%s [%s] %s" % (b.path, b.status, b.clause)
                       for b in blockers[:5])
    if len(blockers) > 5:
        detail += "；…共 %d 条" % len(blockers)
    return Finding(
        rule_id="%s:%s" % (RULE_GATE, scope),
        verdict=FAIL,
        message=("门控拦截（作用域 %s）：%d 条未核对条目不得进入计算路径——%s"
                 % (scope, len(blockers), detail)),
        anchor=_anchor(basis, CLAUSE_GATE),
        evidence=gate.as_dict(),
    )


def _calc_findings(report, version: str, basis: Basis):
    findings = []
    decision = report.basis or {}
    if decision and decision.get("kind") != "none":
        if decision.get("chosen_variant"):
            clause_id = _variant_clause(version, report.case.industry_id,
                                        decision["chosen_variant"])
        else:
            clause_id = _basis_clause(version, decision["kind"])
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_BASIS, decision["kind"]),
            verdict=PASS,
            message=("依据选择（%s，%s）：%s"
                     % (decision["kind"], decision.get("clause", ""),
                        "；".join(decision.get("notes") or [])
                        or "已按规则包判定")),
            anchor=_anchor(basis, clause_id),
            evidence=dict(decision),
        ))

    result = report.result
    variant_id = report.case.variant_id or decision.get("chosen_variant")
    if variant_id:
        clause_id = _variant_clause(version, report.case.industry_id, variant_id)
    else:
        clause_id = _industry_clause(version, report.case.industry_id)
    findings.append(Finding(
        rule_id=RULE_ACCRUAL,
        verdict=PASS,
        message=("应计提 %s 元（%s）：%s；条款 %s"
                 % (result.amount, result.industry_name, result.formula, result.clause)),
        anchor=_anchor(basis, clause_id),
        evidence=result.as_dict(),
    ))
    return findings


def _spending_findings(result: dict, version: str, basis: Basis):
    if result.get("gate_blocked"):
        return [_gate_finding("check", result["gate"], basis)]
    report = result["report"]
    findings = []
    for finding in report.findings:
        if finding.state == spending.STATE_NONCOMPLIANT:
            verdict = FAIL
            anchor = _anchor(basis, _spending_clause(version, finding.entry_id))
        elif finding.state == spending.STATE_NOT_ASSESSED:
            verdict = NOT_APPLICABLE
            anchor = None
        else:
            verdict = PASS
            anchor = _anchor(basis, _spending_clause(version, finding.entry_id))
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_SPENDING, finding.item_key),
            verdict=verdict,
            message=("支出 %s（%s）：%s；条款 %s；%s"
                     % (finding.item_key, finding.subject, finding.state,
                        finding.clause or "无", finding.reason)),
            anchor=anchor,
            evidence=finding.as_dict(),
        ))
    return findings


def _progress_findings(result: dict, version: str, basis: Basis) -> Finding:
    if result.get("gate_blocked"):
        return _gate_finding("progress", result["gate"], basis)
    report = result["report"]
    clause_id = _progress_clause(version, "default")
    if not report.applicable:
        return Finding(
            rule_id=RULE_PROGRESS,
            verdict=NOT_APPLICABLE,
            message="使用进度不适用（应计提金额为 0）",
            anchor=_anchor(basis, clause_id),
            evidence=report.as_dict(),
        )
    if report.disclosure_required:
        message = ("使用进度 %s 低于门槛 %s：须按规定披露并于下一年度 4 月底前提交"
                   "书面说明（非阻断）" % (report.ratio, report.threshold))
    else:
        message = ("使用进度 %s 达到门槛 %s：无需额外披露（%s）"
                   % (report.ratio, report.threshold, "；".join(report.points) or "—"))
    return Finding(
        rule_id=RULE_PROGRESS,
        verdict=PASS,
        message=message,
        anchor=_anchor(basis, clause_id),
        evidence=report.as_dict(),
    )


def _diff_finding(report, basis: Basis) -> Finding:
    counts = report.counts()
    return Finding(
        rule_id=RULE_DIFF,
        verdict=PASS,
        message=("%s → %s 差异 %d 条（%s）；已比对行业 %d 个"
                 % (report.old_doc_no, report.new_doc_no, len(report.items),
                    "、".join("%s=%d" % (key, counts[key]) for key in sorted(counts))
                    or "无", len(report.compared_industries))),
        anchor=_anchor(basis, CLAUSE_DIFF),
        evidence=report.as_dict(),
    )


def _summary_finding(findings, basis: Basis) -> Finding:
    fails = [finding for finding in findings if finding.verdict == FAIL]
    accrual = None
    for finding in findings:
        if finding.rule_id == RULE_ACCRUAL:
            accrual = finding.evidence.get("amount")
    parts = ["应计提 %s 元" % accrual if accrual else "计提未产出"]
    spending_findings = [finding for finding in findings
                         if finding.rule_id.startswith(RULE_SPENDING + ":")]
    if spending_findings:
        counts = {}
        for finding in spending_findings:
            state = finding.evidence.get("state")
            counts[state] = counts.get(state, 0) + 1
        parts.append("支出 %s" % "、".join("%s=%d" % (key, counts[key])
                                          for key in sorted(counts)))
    progress = [finding for finding in findings if finding.rule_id == RULE_PROGRESS]
    if progress:
        evidence = progress[0].evidence
        if evidence.get("applicable") is False:
            parts.append("使用进度不适用")
        elif evidence.get("disclosure_required"):
            parts.append("使用进度 %s 低于门槛 %s（须披露）"
                         % (evidence.get("ratio"), evidence.get("threshold")))
        else:
            parts.append("使用进度 %s（达门槛）" % evidence.get("ratio"))
    message = "；".join(parts)
    if fails:
        message = "检出阻断 %d 条：%s（%s）" % (len(fails),
                                              "、".join(item.rule_id for item in fails[:5]),
                                              message)
        return Finding(rule_id=RULE_SUMMARY, verdict=FAIL, message=message,
                       anchor=_anchor(basis, CLAUSE_SUMMARY),
                       evidence={"blocking": len(fails), "total": len(findings)})
    return Finding(rule_id=RULE_SUMMARY, verdict=PASS,
                   message="无阻断；" + message,
                   anchor=_anchor(basis, CLAUSE_SUMMARY),
                   evidence={"blocking": 0, "total": len(findings)})


def evaluate_with_context(subject: Mapping, basis: Basis, ctx=None) -> Iterable[Finding]:
    """判定入口（``ctx`` 仅供测试注入；生产通路读随包目录）。"""
    _require_basis_version(basis)
    subject = _validate_subject(subject)
    ctx = ctx or _load_context()
    try:
        case = pipeline.build_case(subject["profile"])
    except FeeError as exc:
        raise ValueError("企业档案不可用：%s" % exc)

    try:
        calc = pipeline.compute_calc(ctx, case)
    except FeeError as exc:
        raise ValueError("计提不可用：%s" % exc)

    findings = [_rules_finding(ctx, basis)]
    version = calc.coordinate["version"]

    if not calc.gate.ok:
        findings.append(_gate_finding("calc", calc.gate, basis))
        findings.append(_summary_finding(findings, basis))
        return tuple(findings)

    if calc.inputs_required:
        raise ValueError("档案缺少依据选择所需属性，无法判定：%s（条款 %s）"
                         % (", ".join(calc.inputs_required),
                            (calc.basis or {}).get("clause", "")))

    findings.extend(_calc_findings(calc, version, basis))

    ledger = subject.get("ledger")
    if ledger is not None:
        try:
            items = pipeline.build_ledger(ledger)
            spending_result = pipeline.check_spending(ctx, case, items)
        except FeeError as exc:
            raise ValueError("支出核查不可用：%s" % exc)
        findings.extend(_spending_findings(spending_result, version, basis))

    progress_spec = subject.get("progress")
    if progress_spec is not None:
        used = progress_spec.get("used")
        if used in (None, ""):
            raise ValueError("progress.used 必填")
        accrued = progress_spec.get("accrued")
        if accrued in (None, ""):
            accrued = calc.result.amount
        threshold_id = str(progress_spec.get("threshold_id") or "default")
        try:
            progress_result = pipeline.progress_for(
                ctx, case, accrued=Decimal(str(accrued)),
                used=Decimal(str(used)), threshold_id=threshold_id)
        except (FeeError, ArithmeticError) as exc:
            raise ValueError("使用进度判定不可用：%s" % exc)
        findings.append(_progress_findings(progress_result, version, basis))

    compare = subject.get("compare")
    if compare:
        if isinstance(compare, Mapping):
            from_year = int(compare.get("from_year") or 2020)
            to_year = int(compare.get("to_year") or 2024)
        else:
            from_year, to_year = 2020, 2024
        try:
            diff_report = pipeline.diff_for(ctx, from_year, to_year)
        except FeeError as exc:
            raise ValueError("双版本对照不可用：%s" % exc)
        if diff_report is not None:
            findings.append(_diff_finding(diff_report, basis))

    findings.append(_summary_finding(findings, basis))
    return tuple(findings)


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_context(subject, basis, None)


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "evaluate_with_context"]