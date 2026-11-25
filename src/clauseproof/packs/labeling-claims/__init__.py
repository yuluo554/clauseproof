"""器官 ``labeling-claims``：AI 生成合成内容标识合规判定。

规模：判定面来自 target-map ① 行的旧仓（规则库 34 条 =
27 条生效 + 7 条待核对；字段映射 5 个国标字段；四载体 × 三场景 × 两作用域）。

本器官只做三件事：**校验输入 → 逐条判定 → 把结论挂到条款锚点上**。
它不打印、不读文件、不读环境变量、不读时钟，也不带自己的参数解析器——入口只有
``clauseproof check labeling-claims --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

============  ============================================================
来源状态      本器官 verdict
============  ============================================================
``pass``      ``pass``（必带锚点）
``fail``      ``fail``（必带锚点，阻断，退出码 1）
``unknown``   ``not_applicable`` + message「未判定（<code>）：…」（缺值不臆测）
``skipped``   ``not_applicable`` + message「未判定（scenario_not_applicable）：…」
``pending``   ``not_applicable`` 登记行 ``ruleset.pending``（不参与判定）
============  ============================================================

依据只从条文库取：``basis.anchor(rule.clause_id)``。条文库缺该条款 → ``BasisMissing``
冒到 CLI（退出码 3）；条文库版本与本规则表核对版本不符 → ``ContractError``（退出码 3，
即 SKELETON-SPEC §5「依据包版本缺失」）。
"""

from typing import Iterable, Mapping, Tuple

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
    STATUS_FAIL,
    STATUS_PASS,
    Card,
    RawFinding,
    check_explicit,
    check_implicit,
)
from .rulebook import BASIS_VERSION, FIELDS, PENDING_RULE_IDS, RULES

SLUG = "labeling-claims"
VERSION = "0.2.0"
SUMMARY = "AI 生成合成内容标识判定（GB 45438-2025 §5/§6 + 标识办法第四/六条）"

#: 输入必填字段（与来源产品 ``LabelCard.from_dict`` 的硬性要求一致：
#: ``explicit`` / ``implicit`` 缺省为空，不算缺字段）
INPUT_FIELDS: Tuple[str, ...] = ("card_id", "carrier", "content_sha256")

#: 本轮登记行：待核对条目一律不判定，但要让人看见"有多少条还没核对"
PENDING_RULE_ID = "ruleset.pending"


def _require_basis_version(basis: Basis) -> None:
    """条文库版本必须是本规则表核对过的版本（否则判定依据漂移）。"""
    if basis.version != BASIS_VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据 %s 核对，条文库实为 %s"
            % (BASIS_VERSION, basis.version)
        )


def _message(raw: RawFinding) -> str:
    """人读消息：pass/fail 沿用来源措辞，未判定项前缀缺失原因（§4.2）。"""
    if raw.status in (STATUS_PASS, STATUS_FAIL):
        return raw.message
    return "未判定（%s）：%s" % (raw.code or raw.status, raw.message)


def _to_finding(raw: RawFinding, basis: Basis) -> Finding:
    """内部判定 → 账本行（锚点在此唯一处取得）。"""
    anchor = basis.anchor(raw.rule.clause_id)
    evidence = {
        "scope": raw.rule.scope,
        "target": raw.rule.target,
        "code": raw.code,
        "severity": raw.rule.severity,
        "scenario": raw.scenario,
    }
    evidence.update(raw.evidence)
    if raw.status == STATUS_PASS:
        verdict = PASS
    elif raw.status == STATUS_FAIL:
        verdict = FAIL
    else:
        # unknown / skipped：缺值或缺场景，不猜结论 → 不适用
        verdict = NOT_APPLICABLE
    return Finding(
        rule_id=raw.rule.rule_id,
        verdict=verdict,
        message=_message(raw),
        anchor=anchor,
        evidence=evidence,
    )


def _pending_finding() -> Finding:
    """待核对条目的登记行（无锚点：这些条目**没有**可引用的已核条款）。"""
    return Finding(
        rule_id=PENDING_RULE_ID,
        verdict=NOT_APPLICABLE,
        message="%d 条待核对（status=pending）条目未进入判定路径：%s"
                % (len(PENDING_RULE_IDS), "、".join(PENDING_RULE_IDS)),
        anchor=None,
        evidence={"pending_rules": len(PENDING_RULE_IDS),
                  "rule_ids": list(PENDING_RULE_IDS)},
    )


def judge(card: Card, rules=RULES, fields=FIELDS) -> Tuple[RawFinding, ...]:
    """判定用的纯函数入口（测试与 ``evaluate`` 共用同一条路径）。"""
    findings = []
    findings.extend(check_explicit(card, rules))
    findings.extend(check_implicit(card, rules, fields))
    return tuple(findings)


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    card = Card.from_subject(subject)
    _require_basis_version(basis)
    records = [_to_finding(raw, basis) for raw in judge(card)]
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