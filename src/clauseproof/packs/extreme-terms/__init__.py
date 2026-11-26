"""器官 ``extreme-terms``：广告文案极限用语判定（确定性词表扫描 + 法条锚点）。

规模：判定面来自 target-map ① 行的旧仓（133 条词表、四步词条门控、前缀树扫描、
左→右长词优先非重叠、命中位置与上下文）。

本器官只做一件事：**给一段广告文案，判命中哪些绝对化/违禁用语，并把每条命中挂到
法条原文锚点上**。它不打印、不读文件、不读环境变量、不读时钟、不调 LLM，也不带自己的
参数解析器——入口只有 ``clauseproof check extreme-terms --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

====================  ======================================================
来源结论               本器官 verdict
====================  ======================================================
命中词条               ``fail``（**必带锚点**：该词条的法条条款；阻断 → 退出码 1）
零命中                 ``pass``（锚点：词表契约；一条汇总记录，防「空账本 = 没跑」）
词条未生效（门控拦截）  ``not_applicable``（**无锚点**——无锚点可引正是被拦下的原因）
====================  ======================================================

依据只从条文库取：``basis.anchor(clause_id)``。词条的法条原文逐字随包（``data/clauses.json``，
来自来源仓冻结的法条文本）；``basis=literal`` 的词条**必须**在条款原文里逐字出现，
加载侧再核一次。

条文库缺所需条款 → 该词条不生效并进未启用清单（**不冒到 CLI**：一条挂不上锚点的词不应该
让整次扫描失败）；条文库版本与词表坐标不符 → ``ContractError``（退出码 3）。
"""

from typing import Any, Dict, Iterable, List, Mapping, Tuple

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
from .registry import CLAUSE_WORDLIST, VERSION

SLUG = "extreme-terms"
ORG_VERSION = "0.0.1"
SUMMARY = "广告文案极限用语判定（133 条词表 + 前缀树扫描 + 法条原文锚点；词表为非官方整理快照）"

#: 输入必填字段
INPUT_FIELDS: Tuple[str, ...] = ("text",)

RULE_TERM = "term"
RULE_INACTIVE = "term.inactive"
RULE_RESULT = "scan.result"


def _require_basis_version(basis: Basis) -> None:
    if basis.version != VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据词表坐标 %s 核对，条文库实为 %s"
            % (VERSION, basis.version)
        )


def _clause_by_term(active: List[Mapping]) -> Dict[Tuple[str, str], str]:
    mapping = {}
    for entry in active:
        mapping[(entry["word"], entry["category"])] = entry["clause_id"]
    return mapping


def _hit_findings(result: Mapping, basis: Basis) -> List[Finding]:
    clauses = _clause_by_term(result["active"])
    findings = []
    for hit in result["hits"]:
        clause_id = clauses[(hit["word"], hit["category"])]
        findings.append(Finding(
            rule_id="%s:%s:%s:L%dC%d" % (RULE_TERM, hit["category"], hit["word"],
                                         hit["line"], hit["col"]),
            verdict=FAIL,
            message="命中极限/违禁用语「%s」（类别 %s，风险 %s；上下文：%s）——%s"
                    % (hit["word"], hit["category"], hit["risk"], hit["context"],
                       hit["suggestion"]),
            anchor=basis.anchor(clause_id),
            evidence={
                "word": hit["word"],
                "category": hit["category"],
                "risk": hit["risk"],
                "line": hit["line"],
                "col": hit["col"],
                "context": hit["context"],
                "suggestion": hit["suggestion"],
            },
        ))
    return findings


def _inactive_findings(result: Mapping) -> List[Finding]:
    findings = []
    for entry in result["inactive"]:
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_INACTIVE, entry["word"]),
            verdict=NOT_APPLICABLE,
            message="词条「%s」未生效（%s）——不进扫描路径，也不静默放宽" % (entry["word"],
                                                                          entry["reason"]),
            anchor=None,
            evidence={"word": entry["word"], "reason": entry["reason"], "status": "inactive"},
        ))
    return findings


def _result_finding(result: Mapping, basis: Basis) -> Finding:
    hits = result["hits"]
    risks = {}
    for hit in hits:
        risks[hit["risk"]] = risks.get(hit["risk"], 0) + 1
    return Finding(
        rule_id=RULE_RESULT,
        verdict=FAIL if hits else PASS,
        message=("命中 %d 条（生效词条 %d 条；风险分布 %s）"
                 % (len(hits), len(result["active"]),
                    "、".join("%s=%d" % (key, risks[key]) for key in sorted(risks)))
                 if hits else
                 "未命中（生效词条 %d 条；未生效 %d 条）"
                 % (len(result["active"]), len(result["inactive"]))),
        anchor=basis.anchor(CLAUSE_WORDLIST),
        evidence={
            "hits": len(hits),
            "active": len(result["active"]),
            "inactive": len(result["inactive"]),
            "risk_counts": risks,
        },
    )


def evaluate_with_words(subject: Mapping, basis: Basis,
                        words: Any = None) -> Iterable[Finding]:
    """判定用入口（测试可注入词条；``evaluate`` 用随包词表走同一路径）。"""
    _require_basis_version(basis)
    result = engine.run_scan(subject, words, basis)
    findings: List[Finding] = []
    findings.extend(_hit_findings(result, basis))
    findings.extend(_inactive_findings(result))
    findings.append(_result_finding(result, basis))
    return tuple(findings)


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_words(subject, basis, None)


PACK = register(
    Pack(
        slug=SLUG,
        version=ORG_VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "ORG_VERSION", "PACK", "evaluate", "evaluate_with_words"]