"""器官 ``bid-conformity``：招投标符合性校核（资格 / 星号 / 算术 / 保证金 / 时间 / 否决 / 低价）。

规模：判定面来自 target-map ① 行的旧仓（21 条 `CHK-*` 规则、7 个 `rule_type`、
`only_if` 类目门控、否决联动、依据关联）。

本器官只做一件事：**给招标参数卡 + 投标参数卡，判投标响应在哪一条上不符合（或需人工确认），
并把每条结论挂到法规条号或招标文件条款 id 上**。它不打印、不读文件、不读环境变量、
不读时钟、不联网、不调 LLM——入口只有
``clauseproof check bid-conformity --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

====================  ======================================================
来源三级结论           本器官 verdict
====================  ======================================================
``不符合``             ``fail``（**必带锚点**；阻断 → 退出码 1）
``待人工确认``          ``not_applicable``（提请人工，锚点照挂）
（校核完成但无非符合结论） ``pass``（一条汇总记录，防「空账本 = 没跑」）
====================  ======================================================

依据只从条文库取：``basis.anchor(clause_id)``。法规引用（``《法规名》第X条``）映射到
**已核对**的条文块；招标文件自设条款（``Q*``/``S*``/``R*``）映射到「招标文件自设条款」契约条目
（条款原文在具体项目文件里，本产品条文库不含它）。

条文库缺所需条款 → 该条结论降级为 ``not_applicable``（无锚点，message 写明「依据不可解析」）；
条文库版本与知识库坐标不符 → ``ContractError``（退出码 3）。
"""

import re
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from clauseproof.core.basis import Basis
from clauseproof.core.ledger import (
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Finding,
)
from clauseproof.core.registry import Pack, register

from . import engine
from .registry import (
    CLAUSE_RULE_PACK,
    CLAUSE_TENDER_CLAUSE,
    LAW_PREFIX,
    VERSION,
)
from .schema import STATUS_CONFORM, STATUS_MANUAL, STATUS_NONCONFORM, BidCard, TenderCard

SLUG = "bid-conformity"
ORG_VERSION = "0.6.0"
SUMMARY = "招投标符合性校核（21 条 CHK-*；资格/星号/算术/保证金/时间/否决/低价；依据=法规条号或招标条款）"

#: 输入必填字段
INPUT_FIELDS: Tuple[str, ...] = ("tender", "bid")

RULE_REVIEW = "review.result"

_BASIS_LAW_RE = re.compile(r"^《([^《》]+)》(第[0-9一二三四五六七八九十百]+条)$")
_BASIS_CLAUSE_RE = re.compile(r"^[QSR][0-9]+$")

_VERDICTS = {
    STATUS_NONCONFORM: FAIL,
    STATUS_MANUAL: NOT_APPLICABLE,
    STATUS_CONFORM: PASS,
}


def _require_basis_version(basis: Basis) -> None:
    if basis.version != VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据知识库坐标 %s 核对，条文库实为 %s"
            % (VERSION, basis.version)
        )


def validate_subject(subject: Any) -> Mapping:
    """输入结构校验：``{"tender": {...}, "bid": {...}, "doc_text": str?}``。"""
    if not isinstance(subject, Mapping):
        raise ValueError("输入必须是 JSON 对象，得到 %s" % type(subject).__name__)
    for key in ("tender", "bid"):
        if not isinstance(subject.get(key), Mapping):
            raise ValueError("缺少 %s（参数卡对象）" % key)
    text = subject.get("doc_text")
    if text is not None and not isinstance(text, str):
        raise ValueError("doc_text 必须是字符串")
    return subject


def _anchor(basis: Basis, entries: List[str]) -> Any:
    """依据解析：优先法规条文块（可逐字核验），其次招标文件自设条款契约。"""
    for entry in entries:
        match = _BASIS_LAW_RE.match(entry)
        if not match:
            continue
        law, article = match.group(1), match.group(2)
        prefix = LAW_PREFIX.get(law)
        if not prefix:
            continue
        clause_id = "%s:%s" % (prefix, article)
        if basis.clause(clause_id) is not None:
            return basis.anchor(clause_id)
    for entry in entries:
        if _BASIS_CLAUSE_RE.match(entry) and basis.clause(CLAUSE_TENDER_CLAUSE) is not None:
            return basis.anchor(CLAUSE_TENDER_CLAUSE)
    return None


def _evidence_payload(finding: Any) -> List[Dict[str, Any]]:
    out = []
    for item in finding.evidence or []:
        out.append({"section": item.section, "quote": item.quote, "line": item.line})
    return out


def _to_findings(raw: List[Any], basis: Basis) -> Tuple[List[Finding], int]:
    findings = []
    sequence = {}
    blocked = 0
    for finding in raw:
        check_id = finding.check_id or "CHK-UNKNOWN"
        sequence[check_id] = sequence.get(check_id, 0) + 1
        rule_id = "%s#%d" % (check_id, sequence[check_id])
        verdict = _VERDICTS.get(finding.status, NOT_APPLICABLE)
        anchor = _anchor(basis, list(finding.basis or []))
        message = finding.message or ""
        if verdict == FAIL and anchor is None:
            verdict = NOT_APPLICABLE
            message = "%s（依据不可解析：%s；降级为待人工确认）" % (
                message, "、".join(finding.basis or []) or "无")
        elif verdict == FAIL:
            blocked += 1
        findings.append(Finding(
            rule_id=rule_id,
            verdict=verdict,
            message=message,
            anchor=anchor,
            evidence={
                "check_id": finding.check_id,
                "status": finding.status,
                "risk_level": finding.risk_level,
                "basis": list(finding.basis or []),
                "evidence": _evidence_payload(finding),
            },
        ))
    return findings, blocked


def _summary_finding(raw: List[Any], blocked: int, basis: Basis) -> Finding:
    manual = sum(1 for item in raw if item.status == STATUS_MANUAL)
    conform = sum(1 for item in raw if item.status == STATUS_CONFORM)
    return Finding(
        rule_id=RULE_REVIEW,
        verdict=FAIL if blocked else PASS,
        message=("校核完成：非符合结论 %d 条（不符合 %d / 待人工确认 %d）"
                 % (len(raw), blocked, manual) if raw
                 else "校核完成：未发现非符合结论"),
        anchor=basis.anchor(CLAUSE_RULE_PACK),
        evidence={"findings": len(raw), "blocking": blocked, "manual": manual,
                  "conform": conform},
    )


def evaluate_with_rules(subject: Mapping, basis: Basis,
                        rules: Optional[List[Dict[str, Any]]] = None) -> Iterable[Finding]:
    """判定用入口（测试可注入规则包；``evaluate`` 用随包规则包走同一路径）。"""
    _require_basis_version(basis)
    validate_subject(subject)

    tender = TenderCard.from_dict(dict(subject["tender"]))
    bid = BidCard.from_dict(dict(subject["bid"]))
    doc_text = subject.get("doc_text")

    raw = list(engine.run_tender_checks(tender, doc_text, rules))
    raw.extend(engine.run_checks(tender, bid, doc_text, rules))

    findings, blocked = _to_findings(raw, basis)
    findings.append(_summary_finding(raw, blocked, basis))
    return tuple(findings)


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_rules(subject, basis, None)


PACK = register(
    Pack(
        slug=SLUG,
        version=ORG_VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "ORG_VERSION", "PACK", "evaluate", "evaluate_with_rules",
           "validate_subject"]