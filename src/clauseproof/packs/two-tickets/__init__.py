"""器官 ``two-tickets``：电力两票（工作票 / 操作票）核查。

一句话：**给一张已解析的票面参数卡，按 7 票种 × 7 类 check_type 逐条判定，
输出三级结论（合规 / 不合规 / 待人工确认），每条结论挂规范条款与复核锚；
依据待核对的规则不下确定性「不合规」（降级待人工确认）。**

来源判定面（票种类目门控 / 7 类 check_type / 依据闸 / 三级结论 / 问题分级 /
复核锚）逐条迁移；**票面文本解析、OCR、LLM 兜底、docx 报告、Web 面板、
批量目录审核、内置基准与数据生成器都是输入或交付面，不迁**（器官零文件 IO——
规则库由装配面 :mod:`pipeline` 读入，判定内核只收内存对象；零环境变量、零时钟）。

判定账本口径（SKELETON-SPEC §3–§5）：

===============================  ==============================================
来源结论                         本器官 verdict
===============================  ==============================================
``合规``                          ``pass``（锚点：该规则条款）
``不合规``                        ``fail``（锚点：该规则条款；风险进 evidence；阻断 → 1）
``待人工确认``                     ``not_applicable``（非结论；含依据待核对降级）
规则库坐标（每次运行一条）          ``pass``（锚点：规则库契约）
依据待核对汇总（30 条）            ``not_applicable``（锚点：依据闸契约）
汇总（检出不合规 / 全合规 / 全待人工）  ``fail`` / ``pass`` / ``not_applicable``
===============================  ==============================================

依据只从条文库取：``basis.anchor(clause_id)``。条文库版本 = 规则库核对日期
``2026-10-02``。版本不符 / 条款缺失 → ``ContractError``（退出码 3）。
规则库不可用（缺字段 / 依据无出处 / 未知 check_type / 非法票种）→ 退出码 2。
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
from .errors import TicketError
from .model import VERDICT_COMPLIANT, VERDICT_MANUAL, VERDICT_VIOLATION

SLUG = registry.SLUG
VERSION = registry.VERSION
SUMMARY = registry.SUMMARY

#: 输入必填字段
INPUT_FIELDS = ("case_id",)

RULE_RULES = "ticket.rules"
RULE_PENDING = "ticket.pending"
RULE_RULE = "ticket.rule"
RULE_SUMMARY = "ticket.summary"

CLAUSE_VERSION = "contract.version"
CLAUSE_RULES = "contract.rules"
CLAUSE_GATE = "contract.gate"
CLAUSE_TICKET_TYPE = "contract.ticket_type"
CLAUSE_CHECK_TYPE = "contract.check_type"
CLAUSE_VERDICT = "contract.verdict"
CLAUSE_REVIEW = "contract.review"
CLAUSE_EVIDENCE = "contract.evidence"
CLAUSE_SUMMARY = "contract.summary"
CLAUSE_MANUAL = "contract.manual"

_ALLOWED_KEYS = {"case_id", "ticket", "note"}

_VERDICTS = {
    VERDICT_COMPLIANT: PASS,
    VERDICT_VIOLATION: FAIL,
    VERDICT_MANUAL: NOT_APPLICABLE,
}


def _require_basis_version(basis: Basis) -> None:
    if basis.version != VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据规则库核对日期 %s，条文库实为 %s"
            % (VERSION, basis.version)
        )


def _anchor(basis: Basis, clause_id: str):
    if basis.clause(clause_id) is None:
        raise ContractError("条文库缺少本器官的必要条款：%s" % clause_id)
    return basis.anchor(clause_id)


def _validate_subject(subject: Mapping) -> Mapping:
    if not isinstance(subject, Mapping):
        raise ValueError("输入必须是 JSON 对象")
    unknown = sorted(set(subject) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError("输入含未知字段：%s" % ", ".join(unknown))
    if not str(subject.get("case_id") or "").strip():
        raise ValueError("输入缺少 case_id（一次判定运行的稳定标识）")
    if not isinstance(subject.get("ticket"), Mapping):
        raise ValueError("输入缺少 ticket（已解析的票面参数卡对象）")
    return subject


def _load_library():
    try:
        return pipeline.load_library()
    except TicketError as exc:
        raise ValueError("规则库不可用：%s" % exc)


def _rules_finding(library, basis: Basis) -> Finding:
    coordinate = library.coordinate()
    counts = library.status_counts
    return Finding(
        rule_id=RULE_RULES,
        verdict=PASS,
        message=("规则库 %d 条（已核对 %d / 待核对 %d）；7 票种 × 7 类 check_type；"
                 "无出处的规则不得落库"
                 % (coordinate["rules"], counts.get("已核对", 0),
                    counts.get("待核对", 0))),
        anchor=_anchor(basis, CLAUSE_RULES),
        evidence=coordinate,
    )


def _pending_finding(library, basis: Basis) -> Finding:
    pending = library.pending_rules
    by_standard = {}
    for rule in pending:
        standard = rule["basis"]["standard"]
        by_standard[standard] = by_standard.get(standard, 0) + 1
    return Finding(
        rule_id=RULE_PENDING,
        verdict=NOT_APPLICABLE,
        message=("依据待核对 %d 条（占 %d%%）：其「不合规」结论一律降级为"
                 "「待人工确认」；可确定性判定的仅 %d 条规则——条款 pending 如实登记，"
                 "不把待核对写成已核对"
                 % (len(pending), round(100 * len(pending) / len(library.rules)),
                    len(library.rules) - len(pending))),
        anchor=_anchor(basis, CLAUSE_GATE),
        evidence={
            "pending": len(pending),
            "total": len(library.rules),
            "by_standard": dict(sorted(by_standard.items())),
            "rule_ids": [rule["id"] for rule in pending],
        },
    )


def _conclusion_message(conclusion) -> str:
    basis = conclusion.basis or {}
    status = basis.get("status", "")
    due = basis.get("review_due", "")
    detail = "；".join(conclusion.evidence[:3])
    if conclusion.verdict == VERDICT_COMPLIANT:
        return "%s：%s" % (conclusion.name, detail)
    if conclusion.verdict == VERDICT_VIOLATION:
        risk = "风险 %s；" % conclusion.risk if conclusion.risk else ""
        return "%s：%s%s" % (conclusion.name, risk, detail)
    prefix = ""
    if conclusion.downgraded:
        prefix = ("依据待核对（%s %s%s），「不合规」降级为待人工确认："
                  % (basis.get("standard", ""), basis.get("clause", ""),
                     "，复核到期 %s" % due if due else ""))
    return "%s%s：%s" % (prefix, conclusion.name, detail)


def _rule_findings(conclusions, basis: Basis):
    findings = []
    seen = {}
    for conclusion in conclusions:
        seen[conclusion.rule_id] = seen.get(conclusion.rule_id, 0) + 1
        suffix = "" if seen[conclusion.rule_id] == 1 else "#%d" % seen[conclusion.rule_id]
        verdict = _VERDICTS.get(conclusion.verdict, NOT_APPLICABLE)
        evidence = conclusion.as_dict()
        evidence["basis_status"] = (conclusion.basis or {}).get("status", "")
        evidence["review_due"] = (conclusion.basis or {}).get("review_due", "")
        findings.append(Finding(
            rule_id="%s:%s%s" % (RULE_RULE, conclusion.rule_id, suffix),
            verdict=verdict,
            message="%s %s :: %s" % (conclusion.rule_id, conclusion.check_type,
                                     _conclusion_message(conclusion)),
            anchor=_anchor(basis, "ticket:rule:%s" % conclusion.rule_id),
            evidence=evidence,
        ))
    return findings


def _summary_finding(tally, basis: Basis) -> Finding:
    message = ("三级结论：合规 %d / 不合规 %d / 待人工确认 %d（共 %d 条；"
               "待核对降级 %d 条）"
               % (tally["compliant"], tally["violation"], tally["manual"],
                  tally["total"], tally["downgraded"]))
    if tally["violation"]:
        message += "；检出不合规，风险分布 %s" % (
            "、".join("%s=%d" % (key, value) for key, value in tally["risk"].items())
            or "未分级")
        return Finding(
            rule_id=RULE_SUMMARY, verdict=FAIL, message=message,
            anchor=_anchor(basis, CLAUSE_SUMMARY), evidence=dict(tally),
        )
    if tally["compliant"]:
        return Finding(
            rule_id=RULE_SUMMARY, verdict=PASS,
            message=message + "；无不合规结论",
            anchor=_anchor(basis, CLAUSE_SUMMARY), evidence=dict(tally),
        )
    return Finding(
        rule_id=RULE_SUMMARY, verdict=NOT_APPLICABLE,
        message=message + "；全部为待人工确认，无确定性结论",
        anchor=_anchor(basis, CLAUSE_MANUAL), evidence=dict(tally),
    )


def evaluate_with_library(subject: Mapping, basis: Basis, library=None) -> Iterable[Finding]:
    """判定入口（``library`` 仅供测试注入；生产通路读随包目录）。"""
    _require_basis_version(basis)
    subject = _validate_subject(subject)
    if library is None:
        library = _load_library()
    try:
        card = pipeline.build_card(subject["ticket"])
    except TicketError as exc:
        raise ValueError("票面参数卡不可用：%s" % exc)
    conclusions = engine.run_checks(card, library.rules)
    tally = engine.summarize(conclusions)

    findings = [_rules_finding(library, basis)]
    if library.pending_rules:
        findings.append(_pending_finding(library, basis))
    findings.extend(_rule_findings(conclusions, basis))
    findings.append(_summary_finding(tally, basis))
    return tuple(findings)


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_library(subject, basis, None)


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "evaluate_with_library"]