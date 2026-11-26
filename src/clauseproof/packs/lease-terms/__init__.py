"""器官 ``lease-terms``：租赁合同条款判定（五态 + 法条锚点 + 义务分栏）。

规模：判定面来自 target-map ① 行的旧仓（京/沪两套地方规则包 + 全国层民法典，
共 21 条规则；五态判定、适用域三态、义务分栏、加载侧锚点门）。

本器官只做一件事：**给一张合同卡片，逐条判「约定值 vs 法条限值」，并说明依据是哪一条
哪一款的原文**。它不打印、不读文件、不读环境变量、不读时钟，也不带自己的参数解析器
——入口只有 ``clauseproof check lease-terms --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

================ ==========================================================
来源五态          本器官 verdict
================ ==========================================================
``compliant``     ``pass``（锚点：该规则的条款引文）
``noncompliant``  ``fail``（**必带锚点**；阻断 → 退出码 1）
``skipped``        ``not_applicable``（原文明确了适用情形限制，锚点照挂）
``unknown``        ``not_applicable``（拒判/未观测，锚点照挂，message 写明原因）
``not_assessed``   不逐条产生；整体口径由「全 skipped」自然落到 NA
================ ==========================================================

另有两类不参与义务判定的记录，同样入账：

- ``scope=quota``（监管裁量/提示性条款）→ ``not_applicable``，message 写明「仅作提示」；
- 门控拦下的规则（``status`` 非 verified / 缺锚点）→ ``not_applicable`` 且**无锚点**
  （无锚点可引正是它被拦下的原因），message 写明拦截理由。

依据只从条文库取：``basis.anchor(clause_id)``。条文库缺所需条款 → ``BasisMissing``
冒到 CLI（退出码 3）；条文库版本与规则包坐标不符 → ``ContractError``（退出码 3）。
"""

from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

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
from .registry import CLAUSES_VERSION, SOURCES

SLUG = "lease-terms"
VERSION = "0.1.1"
SUMMARY = "租赁合同条款判定（京/沪 + 民法典 21 条规则；五态 + 法条原文锚点 + 义务分栏）"

#: 输入必填字段
INPUT_FIELDS: Tuple[str, ...] = ("city",)

#: 来源状态 → 本器官结论
_VERDICTS = {
    engine.STATUS_COMPLIANT: PASS,
    engine.STATUS_NONCOMPLIANT: FAIL,
    engine.STATUS_SKIPPED: NOT_APPLICABLE,
    engine.STATUS_UNKNOWN: NOT_APPLICABLE,
    engine.STATUS_NOT_ASSESSED: NOT_APPLICABLE,
}


def _require_basis_version(basis: Basis) -> None:
    if basis.version != CLAUSES_VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据规则包坐标 %s 核对，条文库实为 %s"
            % (CLAUSES_VERSION, basis.version)
        )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _anchor(basis: Basis, clause_id: Optional[str]) -> Any:
    if not clause_id:
        return None
    return basis.anchor(clause_id)


def _evidence(finding: Mapping, source: Mapping) -> Dict[str, Any]:
    return {
        "status": finding["status"],
        "check_type": finding["check_type"],
        "effect": finding["effect"],
        "severity": finding["severity"],
        "scope": finding["scope"],
        "param": finding.get("param"),
        "observed": _jsonable(finding.get("observed")),
        "limit": _jsonable(finding.get("limit")),
        "op": finding.get("op"),
        "unit": finding.get("unit"),
        "clause": finding.get("clause"),
        "source_id": finding.get("source_id"),
        "source_title": source.get("title"),
        "doc_no": source.get("doc_no"),
    }


def _to_finding(finding: Mapping, basis: Basis) -> Finding:
    source = SOURCES.get(finding.get("source_id") or "", {})
    verdict = _VERDICTS.get(finding["status"], NOT_APPLICABLE)
    title = finding.get("title") or finding["rule_id"]
    return Finding(
        rule_id=finding["rule_id"],
        verdict=verdict,
        message="%s — %s" % (title, finding.get("reason") or ""),
        anchor=_anchor(basis, finding.get("clause_id")),
        evidence=_evidence(finding, source),
    )


def _disabled_finding(entry: Mapping) -> Finding:
    """被门控拦下的规则：无锚点可引（这正是它被拦下的原因）。"""
    return Finding(
        rule_id=entry["rule_id"],
        verdict=NOT_APPLICABLE,
        message="规则未启用（%s）— %s" % (entry.get("reason"), entry.get("title")),
        anchor=None,
        evidence={"status": entry.get("status"), "scope": "gate",
                  "disabled": True, "reason": entry.get("reason")},
    )


def evaluate_with_rules(subject: Mapping, basis: Basis,
                        rules: Optional[Sequence[Mapping]] = None) -> Iterable[Finding]:
    """判定用入口（测试可注入规则表；``evaluate`` 用随包规则包走同一路径）。"""
    _require_basis_version(basis)
    engine.validate_card(subject)

    city = subject["city"]
    gated = engine.effective_rules(city, "calc", rules)
    judged = engine.judge_card(subject, gated["kept"])

    findings: List[Finding] = [_to_finding(item, basis) for item in judged]
    findings.extend(_to_finding(item, basis)
                    for item in engine.reference_findings(gated["reference"]))
    findings.extend(_disabled_finding(entry) for entry in gated["disabled"])
    return tuple(findings)


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_rules(subject, basis, None)


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "evaluate_with_rules"]