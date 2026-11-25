"""器官 ``petfood-label``：宠物食品标签合规判定。

规模：判定面来自 target-map ① 行的旧仓（45 条规则 = 5 宣称支撑 /
8 标签标示 / 32 理化指标；五态判定；干物质基准换算；适用域画像）。

本器官只做一件事：**给一份结构化标签档案，逐条判它合不合规，每条结论挂条款锚点**。
它不打印、不读文件、不读环境变量、不读时钟，也不带自己的参数解析器——入口只有
``clauseproof check petfood-label --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

================  ==========================================================
来源五态           本器官 verdict
================  ==========================================================
``compliant``      ``pass``（必带锚点）
``noncompliant``   ``fail``（必带锚点；阻断 → 退出码 1）
``not_provided``   ``not_applicable`` + message「未判定（not_provided）：…」
``skipped``        ``not_applicable`` +「未判定（skipped）：未宣称 → 不适用」
``unknown``        ``not_applicable`` +「未判定（<原因码>）：…」
================  ==========================================================

另有两类**登记行**（`not_applicable`、无锚点、永不阻断）：

- ``ruleset.pending``：2 条待核对（牛磺酸限值未核对）条目不进判定路径；
- ``dimension.<维度>``：该维度**有生效规则但本档案无一条适用** → 未评估
  （绝不输出合规）。
"""

from typing import Iterable, Mapping, Sequence, Tuple

from clauseproof.core.basis import Basis
from clauseproof.core.ledger import (
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Finding,
)
from clauseproof.core.registry import Pack, register

from .engine import (
    DIMENSIONS,
    VERDICT_COMPLIANT,
    VERDICT_NONCOMPLIANT,
    Card,
    RawFinding,
    dimension_assessed,
    judge_dimension,
)
from .registry import PENDING_RULE_IDS, RULES, RULESET_VERSION

SLUG = "petfood-label"
VERSION = "0.2.0"
SUMMARY = "宠物食品标签合规判定（GB/T 31216/31217 理化指标 + 公告20号标签与宣称支撑）"

#: 输入必填字段（档案可空，但必须给出 category 用于适用域画像）
INPUT_FIELDS: Tuple[str, ...] = ("category",)

PENDING_RULE_ID = "ruleset.pending"

DIMENSION_LABEL = {
    "label": "标签标示",
    "nutrition": "理化指标",
    "claim": "宣称支撑",
}


def _require_basis_version(basis: Basis) -> None:
    if basis.version != RULESET_VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据规则包 %s 核对，条文库实为 %s"
            % (RULESET_VERSION, basis.version)
        )


def _message(raw: RawFinding) -> str:
    if raw.verdict in (VERDICT_COMPLIANT, VERDICT_NONCOMPLIANT):
        return raw.note or ("符合要求" if raw.verdict == VERDICT_COMPLIANT else "不符合要求")
    return "未判定（%s）：观测=%s；要求=%s" % (raw.verdict, raw.observed, raw.expected)


def _to_finding(raw: RawFinding, basis: Basis) -> Finding:
    anchor = basis.anchor(raw.rule.clause_id)
    evidence = {
        "dimension": raw.rule.dimension,
        "kind": raw.rule.kind,
        "target": raw.rule.target,
        "effect": raw.rule.effect,
        "source_verdict": raw.verdict,
        "observed": raw.observed,
        "expected": raw.expected,
    }
    if raw.rule.kind == "threshold":
        evidence["basis"] = raw.rule.basis
        evidence["op"] = raw.rule.op
        evidence["limit"] = raw.rule.value
    if raw.verdict == VERDICT_COMPLIANT:
        verdict = PASS
    elif raw.verdict == VERDICT_NONCOMPLIANT:
        verdict = FAIL
    else:
        verdict = NOT_APPLICABLE
    return Finding(
        rule_id=raw.rule.rule_id,
        verdict=verdict,
        message=_message(raw),
        anchor=anchor,
        evidence=evidence,
    )


def _pending_finding() -> Finding:
    return Finding(
        rule_id=PENDING_RULE_ID,
        verdict=NOT_APPLICABLE,
        message="%d 条待核对（status=pending）条目未进入判定路径：%s"
                % (len(PENDING_RULE_IDS), "、".join(PENDING_RULE_IDS)),
        anchor=None,
        evidence={"pending_rules": len(PENDING_RULE_IDS),
                  "rule_ids": list(PENDING_RULE_IDS)},
    )


def _dimension_finding(dimension: str) -> Finding:
    return Finding(
        rule_id="dimension.%s" % dimension,
        verdict=NOT_APPLICABLE,
        message="%s维度未评估：本档案没有一条适用的生效规则（不输出合规）"
                % DIMENSION_LABEL.get(dimension, dimension),
        anchor=None,
        evidence={"dimension": dimension, "assessed": False},
    )


def judge(card: Card, rules: Sequence = RULES) -> Tuple[RawFinding, ...]:
    """判定用的纯函数入口（测试与 ``evaluate`` 共用同一条路径）。"""
    findings = []
    for dimension in DIMENSIONS:
        findings.extend(judge_dimension(rules, dimension, card))
    return tuple(findings)


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    card = Card.from_subject(subject)
    _require_basis_version(basis)
    records = [_to_finding(raw, basis) for raw in judge(card)]
    for dimension in DIMENSIONS:
        if not dimension_assessed(RULES, dimension, card):
            records.append(_dimension_finding(dimension))
    if PENDING_RULE_IDS:
        records.append(_pending_finding())
    return tuple(records)


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "judge"]