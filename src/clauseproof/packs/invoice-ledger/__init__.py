"""器官 ``invoice-ledger``：电子发票台账判定（八规则 × 三级语义 × 条款锚点）。

一句话：**给一批已解析的发票参数卡 + 时间基准，判重复报销（精确/联合键/模糊）、
连号拆分、票面算术、大写金额与时间逻辑异常，逐条挂法规条款锚点。**

来源判定面的八规则（R-DUP-01/02/03、R-SEQ-01、R-ARITH-01/02、R-TIME-01/02）
逐条迁移；**发票文件解析（XML/PDF/OFD）、批次扫描、SQLite 台账、GUI/Excel 导出
都是输入/交付层，不迁**（器官零文件 IO、零环境变量、零时钟）。

判定账本口径（SKELETON-SPEC §3–§5）：

============================  ==========================================
来源级别                       本器官 verdict
============================  ==========================================
``error``（确认异常）           ``fail``（锚点：法规条款；阻断 → 退出码 1）
``suspicious``（疑似）          ``not_applicable``（疑似≠确认；保留级别证据）
``review``（待人工确认）         ``not_applicable``（预警不阻断）
规则未命中（整族无记录）         ``pass``（锚点：该族法规条款）
规则因缺字段未检查              ``not_applicable``（显式列出跳过卡数）
============================  ==========================================

**与 ``expense-ledger`` 的边界**：本器官判「发票票面与台账内号码/金额/时间逻辑」
（数电票号码、价税合计、大写金额、批次报销基准日）；``expense-ledger`` 判
「账单流水与真实支出的行级对账」（商户归一化、跨平台去重、订阅识别）。
两者 slug / 规则代码 / 测试零复用。

依据只从条文库取：``basis.anchor(clause_id)``。条文库版本 = 三份法规知识库核对
日期 ``2026-10-06``；版本不符 → ``ContractError``（退出码 3）。规则族是弱关联
（``series`` / ``time.future`` / ``time.stale``）时 evidence 显式带工程口径说明，
不冒充直接禁止条款。
"""

from typing import Iterable, List, Mapping, Tuple

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
from . import registry as rules

SLUG = rules.SLUG
VERSION = rules.VERSION
SUMMARY = rules.SUMMARY

#: 输入必填字段（cards = 发票参数卡数组；anchors = 时间基准，器官不读时钟）
INPUT_FIELDS = ("cards", "anchors")

_RULE_PREFIX = "invoice"


def _require_basis_version(basis: Basis) -> None:
    if basis.version != rules.PARAMS_VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据知识库核对日期 %s，条文库实为 %s"
            % (rules.PARAMS_VERSION, basis.version)
        )


def _rule_id(family: str, numbers: Tuple[str, ...], suffix: str = "") -> str:
    rule_id = "%s.%s" % (_RULE_PREFIX, family)
    if numbers:
        rule_id += ":" + "|".join(numbers)
    if suffix:
        rule_id += ":" + suffix
    return rule_id


def _hit_evidence(hit: engine.Hit) -> dict:
    evidence = dict(hit.evidence)
    evidence.update({
        "level": hit.level,
        "source_rule": rules.RULE_CODES[hit.family],
        "rule": hit.family,
        "heuristic": hit.family in rules.HEURISTIC_FAMILIES,
    })
    if hit.family in rules.HEURISTIC_FAMILIES:
        evidence["heuristic_note"] = rules.HEURISTIC_NOTE
    return evidence


def _hit_finding(hit: engine.Hit, basis: Basis) -> Finding:
    verdict = FAIL if hit.level == "error" else NOT_APPLICABLE
    return Finding(
        rule_id=_rule_id(hit.family, hit.numbers, hit.suffix),
        verdict=verdict,
        message=hit.message,
        anchor=basis.anchor(rules.RULE_CLAUSES[hit.family]),
        evidence=_hit_evidence(hit),
    )


def _summary_finding(family: str, stats: Mapping[str, int], basis: Basis) -> Finding:
    code = rules.RULE_CODES[family]
    if stats.get("skipped"):
        verdict = NOT_APPLICABLE
        message = ("未检查：%d 张卡缺本规则所需字段（不硬判；规则代码 %s）"
                   % (stats["skipped"], code))
    else:
        verdict = PASS
        message = "未命中：本规则三级（error/suspicious/review）均无记录（规则代码 %s）" % code
    evidence = {
        "level": "none" if not stats.get("skipped") else "skipped",
        "source_rule": code,
        "rule": family,
        "hits": stats.get("hits", 0),
        "skipped": stats.get("skipped", 0),
        "heuristic": family in rules.HEURISTIC_FAMILIES,
    }
    if family in rules.HEURISTIC_FAMILIES:
        evidence["heuristic_note"] = rules.HEURISTIC_NOTE
    return Finding(
        rule_id=_rule_id(family, ()),
        verdict=verdict,
        message=message,
        anchor=basis.anchor(rules.RULE_CLAUSES[family]),
        evidence=evidence,
    )


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。

    输入不合法（卡缺主键、cards 为空、anchors 非法、参数非法）→ ``ValueError``
    → 退出码 2；条文库版本不符 → ``ContractError`` → 退出码 3。
    """
    _require_basis_version(basis)
    context = engine.build_context(subject)
    hits, stats = engine.run(context)

    findings: List[Finding] = [_hit_finding(hit, basis) for hit in hits]
    for family in engine.RULE_ORDER:
        if stats[family]["hits"]:
            continue  # 有命中的规则不再出「未命中」汇总，避免自相矛盾
        findings.append(_summary_finding(family, stats[family], basis))
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