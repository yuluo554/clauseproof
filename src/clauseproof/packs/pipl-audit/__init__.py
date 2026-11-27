"""器官 ``pipl-audit``：个人信息保护合规审计判定。

一句话：**给一张已填好的审计参数卡（+ 人工录入结论），判是否触发审计义务、
逐项过 27 项审查要点的四态、汇总到「符合 / 部分符合 / 不符合 / 未评估」，
逐条挂办法与国标的条款锚点；未核对条目拒绝进入核查路径。**

来源判定面（门槛判定 + 义务三分分栏 / 检查单四态 / 汇总语义 / status 门控 /
规则包坐标）逐条迁移；**GUI / 报告导出 / 底稿与证据链 / 整改台账 CSV /
内置基准 / 真值库生成器都是交付或工具面，不迁**（器官零文件 IO——规则包由
装配面 :mod:`pipeline` 读入，判定内核只收内存对象；零环境变量、零时钟）。

判定账本口径（SKELETON-SPEC §3–§5）：

===============================  ==============================================
来源结论                         本器官 verdict
===============================  ==============================================
门槛命中（无条件义务 / 条件触发）    ``pass``（锚点：该门槛条款；结论不混同）
门槛未触发 / 参数未提供 / 类型不可比  ``not_applicable``（非结论，不冒充"不适用"）
检查项 ``compliant``               ``pass``（锚点：检查项条款）
检查项 ``partial`` / ``noncompliant``  ``fail``（锚点：检查项条款；阻断 → 退出码 1）
检查项 ``not_applicable`` / ``unknown``  ``not_applicable``（不进分母）
汇总 ``compliant``                 ``pass``（锚点：汇总契约）
汇总 ``partial`` / ``noncompliant``  ``fail``（阻断 → 退出码 1）
汇总 ``not_assessed``              ``fail``（阻断 —— 未评估不得冒充合规，来源 rc 同为 1）
===============================  ==============================================

依据只从条文库取：``basis.anchor(clause_id)``。条文库版本 = 来源规则包核对日期
``2026-10-13``。版本不符 / 条款缺失 → ``ContractError``（退出码 3）。
规则包不可用（status 门控拦截 / schema 不符）→ 退出码 2（与来源一致）。
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

from . import engine, pipeline, registry, rules
from .errors import AuditError
from .model import (SUMMARY_COMPLIANT, SUMMARY_NONCOMPLIANT,
                    SUMMARY_NOT_ASSESSED, SUMMARY_PARTIAL)

SLUG = registry.SLUG
VERSION = registry.VERSION
SUMMARY = registry.SUMMARY

#: 输入必填字段
INPUT_FIELDS = ("case_id",)

RULE_PACK = "audit.pack"
RULE_PACK_SYNTHETIC = "audit.pack.synthetic"
RULE_THRESHOLD = "audit.threshold"
RULE_THRESHOLD_RESULT = "audit.threshold.result"
RULE_ITEM = "audit.item"
RULE_SUMMARY = "audit.summary"

CLAUSE_VERSION = "contract.version"
CLAUSE_PACK = "contract.pack"
CLAUSE_GATE = "contract.gate"
CLAUSE_THRESHOLD = "contract.threshold"
CLAUSE_CHECKLIST = "contract.checklist"
CLAUSE_SUMMARY = "contract.summary"
CLAUSE_NOT_ASSESSED = "contract.not_assessed"
CLAUSE_RISK = "contract.risk"
CLAUSE_MANUAL = "contract.manual"
CLAUSE_INPUT = "contract.input"
CLAUSE_EVIDENCE = "contract.evidence"

_ALLOWED_KEYS = {"case_id", "ruleset", "input_card", "manual_results", "audit_scope"}

_SUMMARY_LABELS = {
    SUMMARY_COMPLIANT: "符合",
    SUMMARY_PARTIAL: "部分符合",
    SUMMARY_NONCOMPLIANT: "不符合",
    SUMMARY_NOT_ASSESSED: "未评估",
}

_SUMMARY_VERDICTS = {
    SUMMARY_COMPLIANT: PASS,
    SUMMARY_PARTIAL: FAIL,
    SUMMARY_NONCOMPLIANT: FAIL,
    SUMMARY_NOT_ASSESSED: FAIL,
}

_ITEM_VERDICTS = {
    "compliant": PASS,
    "partial": FAIL,
    "noncompliant": FAIL,
    "not_applicable": NOT_APPLICABLE,
    "unknown": NOT_APPLICABLE,
}


def _require_basis_version(basis: Basis) -> None:
    if basis.version != VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据知识库核对日期 %s，条文库实为 %s"
            % (VERSION, basis.version)
        )


def _anchor(basis: Basis, clause_id: str):
    """取锚点；条文库缺本器官必要条款 = 数据漂移（契约违约，退出码 3）。"""
    if basis.clause(clause_id) is None:
        raise ContractError("条文库缺少本器官的必要条款：%s" % clause_id)
    return basis.anchor(clause_id)


def _threshold_clause(kind: str, entry_id: str) -> str:
    return "pipl:%s:%s" % (kind, entry_id)


def _validate_subject(subject: Mapping) -> Mapping:
    if not isinstance(subject, Mapping):
        raise ValueError("输入必须是 JSON 对象")
    unknown = sorted(set(subject) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError("输入含未知字段：%s" % ", ".join(unknown))
    if not str(subject.get("case_id") or "").strip():
        raise ValueError("输入缺少 case_id（一次判定运行的稳定标识）")
    if not isinstance(subject.get("input_card"), Mapping):
        raise ValueError("输入缺少 input_card（已填好的审计参数卡对象）")
    for key in ("manual_results", "audit_scope"):
        value = subject.get(key)
        if value is not None and not isinstance(value, Mapping):
            raise ValueError("%s 必须是对象" % key)
    ruleset_id = subject.get("ruleset")
    if ruleset_id is not None and not isinstance(ruleset_id, str):
        raise ValueError("ruleset 必须是字符串（规则包 id）")
    return subject


def _select_pack(subject: Mapping, packs):
    ruleset_id = subject.get("ruleset") or registry.DEFAULT_RULESET
    pack = packs.get(ruleset_id)
    if pack is None:
        raise ValueError(
            "未知规则包：%s（随包可选：%s）"
            % (ruleset_id, ", ".join(sorted(packs)))
        )
    try:
        rules.effective(pack.ruleset)
    except AuditError as exc:
        raise ValueError("规则包不可用：%s" % exc)
    return pack


def _pack_finding(pack, basis: Basis) -> Finding:
    counts = pack.counts
    synthetic = "；合成示例包（门槛值为合成示例值，不得据以作出合规结论）" \
        if pack.synthetic else ""
    return Finding(
        rule_id=RULE_PACK,
        verdict=PASS,
        message=("规则包 %s 版本 %s：依据 %d 份 / 门槛 %d 条 / 检查项 %d 条"
                 "（全部 verified 且出处齐全）%s"
                 % (pack.ruleset_id, pack.version, counts["basis"],
                    counts["thresholds"], counts["checklist"], synthetic)),
        anchor=_anchor(basis, CLAUSE_PACK),
        evidence=dict(pack.coordinate(), **counts),
    )


def _synthetic_finding(pack) -> Finding:
    return Finding(
        rule_id=RULE_PACK_SYNTHETIC,
        verdict=NOT_APPLICABLE,
        message=("当前使用合成示例规则包 %s：门槛值为合成示例值、非法规门槛，"
                 "不得据以作出任何合规结论" % pack.ruleset_id),
        anchor=None,
        evidence={"ruleset_id": pack.ruleset_id, "synthetic": True},
    )


def _threshold_findings(result, basis: Basis):
    findings = []
    for outcome in result.outcomes:
        threshold = outcome.threshold
        anchor = _anchor(basis, _threshold_clause("th", threshold.id))
        effect_label = engine.EFFECT_LABELS.get(threshold.effect, threshold.effect)
        if outcome.hit:
            message = "命中门槛 %s（%s）：%s%s" % (
                threshold.id, effect_label, threshold.conclusion,
                "；频次：%s" % threshold.frequency if threshold.frequency else "",
            )
            verdict = PASS
        else:
            message = "%s（%s：%s %s %s）" % (
                engine.OUTCOME_LABELS[outcome.outcome], threshold.id,
                threshold.param, threshold.op, threshold.value,
            )
            verdict = NOT_APPLICABLE
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_THRESHOLD, threshold.id),
            verdict=verdict,
            message=message,
            anchor=anchor,
            evidence=dict(
                outcome.as_dict(),
                effect_label=effect_label,
                condition="%s %s %s" % (threshold.param, threshold.op, threshold.value),
            ),
        ))
    return findings


def _threshold_summary_finding(result, basis: Basis) -> Finding:
    obligations = result.obligations
    conditional = result.conditional_triggers
    frequency = result.frequency
    message = ("门槛结论：%s；无条件义务 %d 条%s；条件触发 %d 条（分栏呈现，结论不混同）"
               % ("触发" if result.triggered else "未触发",
                  len(obligations),
                  "（频次：%s）" % frequency if frequency else "",
                  len(conditional)))
    if result.conclusions:
        message += "；结论码：%s" % "、".join(result.conclusions)
    return Finding(
        rule_id=RULE_THRESHOLD_RESULT,
        verdict=PASS,
        message=message,
        anchor=_anchor(basis, CLAUSE_THRESHOLD),
        evidence=result.as_dict(),
    )


def _item_findings(result, basis: Basis):
    findings = []
    for item_result in result.item_results:
        item = item_result.item
        verdict = _ITEM_VERDICTS.get(item_result.state, NOT_APPLICABLE)
        suffix = "；问题分级 %s" % item_result.risk if item_result.risk else ""
        note = "（%s）" % item_result.note if item_result.note else ""
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_ITEM, item.id),
            verdict=verdict,
            message="%s【%s】%s：%s%s%s" % (
                item.id, item.category, item.title,
                _state_label(item_result.state), note, suffix,
            ),
            anchor=_anchor(basis, _threshold_clause("chk", item.id)),
            evidence=item_result.as_dict(),
        ))
    return findings


def _state_label(state):
    return {
        "compliant": "符合",
        "partial": "部分符合",
        "noncompliant": "不符合",
        "not_applicable": "不适用",
        "unknown": "未观测（待人工确认）",
    }.get(state, state)


def _summary_finding(result, basis: Basis) -> Finding:
    summary = result.summary
    verdict = _SUMMARY_VERDICTS.get(summary, FAIL)
    counts = result.counts
    if summary == SUMMARY_NOT_ASSESSED:
        clause_id = CLAUSE_NOT_ASSESSED
        message = ("未评估：无任何适用项被评（适用项 %d / 检查项 %d；"
                   "不适用 %d、未观测 %d）——未评估不得冒充合规"
                   % (counts["applicable"], counts["total"],
                      counts["not_applicable"], counts["unknown"]))
    else:
        clause_id = CLAUSE_SUMMARY
        message = ("汇总 %s：适用项 %d（符合 %d / 部分符合 %d / 不符合 %d）；"
                   "不适用 %d、未观测 %d"
                   % (_SUMMARY_LABELS.get(summary, summary), counts["applicable"],
                      counts["compliant"], counts["partial"], counts["noncompliant"],
                      counts["not_applicable"], counts["unknown"]))
    evidence = dict(counts)
    evidence["summary"] = summary
    evidence["risk"] = {"high": counts["risk_high"], "medium": counts["risk_medium"]}
    return Finding(
        rule_id=RULE_SUMMARY,
        verdict=verdict,
        message=message,
        anchor=_anchor(basis, clause_id),
        evidence=evidence,
    )


def evaluate_with_packs(subject: Mapping, basis: Basis, packs=None) -> Iterable[Finding]:
    """判定入口（``packs`` 仅供测试注入；生产通路读随包目录）。"""
    _require_basis_version(basis)
    subject = _validate_subject(subject)
    if packs is None:
        packs = pipeline.load_packs()
    pack = _select_pack(subject, packs)
    try:
        result = pipeline.compute_audit(
            pack,
            subject["input_card"],
            subject.get("manual_results") or {},
            subject.get("audit_scope") or {},
        )
    except AuditError as exc:
        raise ValueError("输入不可用：%s" % exc)
    findings = []
    if pack.synthetic:
        findings.append(_synthetic_finding(pack))
    findings.append(_pack_finding(pack, basis))
    findings.extend(_threshold_findings(result.threshold_result, basis))
    findings.append(_threshold_summary_finding(result.threshold_result, basis))
    findings.extend(_item_findings(result, basis))
    findings.append(_summary_finding(result, basis))
    return tuple(findings)


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_packs(subject, basis, None)


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "evaluate_with_packs"]