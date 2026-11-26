"""器官 ``ebike-limits``：电动自行车三维限值判定（整车/电池/充电器 × GB 强制标准）。

规模：判定面来自 target-map ① 行的旧仓（规则包 schema 校验与 status 门控、
applies_if 三值逻辑、单位归一与 Decimal 比较、参数 × 限值四态判定矩阵、
跨标准统一结论聚合、版本锚定、字段映射）。

本器官只做一件事：**给一份车型参数卡 + 随包规则包，判关键参数符不符合
GB 17761—2024 / GB 43854—2024 / GB 42296—2022 的强制限值，逐条挂标准条款号，
并给跨标准统一结论**。它不打印、不读环境变量、不读时钟，也不带自己的参数
解析器——入口只有
``clauseproof check ebike-limits --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

====================================  ==========================================
来源结论                               本器官 verdict
====================================  =====================================
``non_compliant``（不符合）              ``fail``（必带锚点：标准条款；阻断 → 退出码 1）
``compliant``（符合）                   ``pass``（锚点：标准条款）
``not_provided``（未提供/不可判定）       ``not_applicable``（"没查到"≠"没问题"，必带锚点）
``not_applicable``（条件不适用）          ``not_applicable``
门控排除条目（pending）                  ``not_applicable``（显式列出，不参与判定）
统一结论（聚合）                         ``pass``（汇总记录；随 fail 决定退出码）
====================================  ==========================================

依据只从条文库取：``basis.anchor(clause_id)``。条款锚点在 ``evidence`` 里携带
**标准号 + 条款号 + 条款核对状态**（来源逐条核对纪律：verified 必有条款号、
pending 必为 null——绝不编造条款号）。**本器官的条文库条目是数据契约**
（四态语义、status 门控、版本锚定窗口），标准条款号进 ``evidence``，不冒充
条文库内容。

条文库缺所需条款 → ``BasisMissing`` 冒到 CLI（退出码 3）；条文库版本与规则包
快照不符 → ``ContractError``（退出码 3）。

**文件读取只在装配面**：随包冻结规则包（与来源仓逐字节同 sha256）由本包
``registry.ruleset_docs()`` 读入一次（与 ``Basis.from_json`` 同形态的装配），
判定内核 :mod:`engine` 只收内存 dict（零文件 IO、零时钟、零环境变量）。
"""

from typing import Any, Dict, Iterable, List, Mapping

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

SLUG = "ebike-limits"
VERSION = "0.1.0"
SUMMARY = ("电动自行车三维限值判定（整车/电池/充电器 × GB 17761-2024 等三册强制标准；"
           "四态判定 + status 门控 + 条款锚点）")

#: 输入必填字段
INPUT_FIELDS = ("profile_id", "params")

#: 规则单号（一条结论 = 规则 + 锚点）
RULE_FINDING = "ebike.finding"
RULE_EXCLUDED = "ebike.excluded"
RULE_DIMENSION = "ebike.dimension"
RULE_RESULT = "ebike.result"

#: 四态 → verdict 映射（SKELETON-SPEC §3 判定账本）
_STATE_VERDICT = {
    engine.COMPLIANT: PASS,
    engine.NON_COMPLIANT: FAIL,
    engine.NOT_APPLICABLE: NOT_APPLICABLE,
    engine.NOT_PROVIDED: NOT_APPLICABLE,
}


def _require_basis_version(basis: Basis) -> None:
    if basis.version != rules.PARAMS_VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据规则包快照 %s 核对，条文库实为 %s"
            % (rules.PARAMS_VERSION, basis.version)
        )


def _state_anchor(basis: Basis, finding: Mapping) -> Any:
    """结论锚点：四态契约条目（标准条款号在 evidence，不冒充条文库内容）。"""
    return basis.anchor(rules.CLAUSE_FOUR_STATES)


def _finding_record(finding: Mapping, basis: Basis) -> Finding:
    verdict = _STATE_VERDICT[finding["state"]]
    message_bits = ["%s（%s）" % (finding["param"], finding["standard"])]
    if finding["clause"]:
        message_bits.append("条款 %s" % finding["clause"])
    if finding["state"] == engine.NON_COMPLIANT:
        message_bits.append("观测 %s %s %s 限值 %s %s"
                            % (finding["observed"], finding["unit"],
                               finding["op"], finding["limit"], finding["unit"]))
    elif finding["state"] == engine.NOT_PROVIDED:
        message_bits.append("未判定（%s）" % finding.get("reason"))
    elif finding["state"] == engine.NOT_APPLICABLE:
        message_bits.append("不适用")
    else:
        message_bits.append("观测 %s %s（限值 %s %s）"
                            % (finding["observed"], finding["unit"],
                               finding["limit"], finding["unit"]))
    if finding.get("notes"):
        message_bits.append(finding["notes"])
    return Finding(
        rule_id="%s:%s" % (RULE_FINDING, finding["rule_id"]),
        verdict=verdict,
        message="%s %s" % (finding["state"], "；".join(message_bits)),
        anchor=_state_anchor(basis, finding),
        evidence={
            "state": finding["state"],
            "param": finding["param"],
            "standard": finding["standard"],
            "clause": finding["clause"],
            "clause_status": finding["clause_status"],
            "op": finding["op"],
            "limit": finding["limit"],
            "unit": finding["unit"],
            "observed": finding["observed"],
            "reason": finding.get("reason"),
            "severity": finding.get("severity"),
        },
    )


def _findings(result: Mapping, basis: Basis) -> List[Finding]:
    findings: List[Finding] = []

    for dimension in result["dimensions"]:
        # ① 门控排除条目：pending 零参与核查（显式列出，绝不"悄悄当作已核对"）
        for excluded in dimension["excluded_rules"]:
            findings.append(Finding(
                rule_id="%s:%s" % (RULE_EXCLUDED, excluded["rule_id"]),
                verdict=NOT_APPLICABLE,
                message="%s：条目 %s 状态 %s，零参与核查路径（不参与判定）"
                        % (dimension["standard"], excluded["param"], excluded["status"]),
                anchor=basis.anchor(rules.CLAUSE_STATUS_GATE),
                evidence={"standard": dimension["standard"],
                          "rule_id": excluded["rule_id"],
                          "param": excluded["param"],
                          "status": excluded["status"]},
            ))
        # ② 参数 × 限值四态结论
        for finding in dimension["findings"]:
            findings.append(_finding_record(finding, basis))

    # ③ 统一结论（聚合）：non_compliant > not_provided > not_assessed > compliant
    counts = result["counts"]
    findings.append(Finding(
        rule_id=RULE_RESULT,
        verdict=PASS,
        message=("三维核查完成：%s——不符合 %d / 未提供 %d / 不适用 %d / 符合 %d；"
                 "门控排除 %d 条（pending 不参与判定）")
                % (result["overall"], counts[engine.NON_COMPLIANT],
                   counts[engine.NOT_PROVIDED], counts[engine.NOT_APPLICABLE],
                   counts[engine.COMPLIANT], len(result["excluded_rules"])),
        anchor=basis.anchor(rules.CLAUSE_NOT_PROVIDED),
        evidence={
            "profile_id": result["profile_id"],
            "version_key": result["version_key"],
            "overall": result["overall"],
            "counts": dict(counts),
            "excluded": len(result["excluded_rules"]),
            "dimensions": [
                {"scope": d["scope"], "standard": d["standard"],
                 "overall": d["overall"],
                 "effective_rule_count": d["effective_rule_count"]}
                for d in result["dimensions"]
            ],
        },
    ))
    return findings


# ------------------------------------------------------------------ 器官入口
def evaluate_with_docs(subject: Mapping, basis: Basis,
                       ruleset_docs: Mapping[str, Any]) -> Iterable[Finding]:
    """判定用入口（测试可注入规则包；``evaluate`` 用随包规则包走同一路径）。"""
    _require_basis_version(basis)
    result = engine.check_profile(subject, ruleset_docs, rules.unit_alias_index())
    return tuple(_findings(result, basis))


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_rules(subject, basis)


def evaluate_with_rules(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """默认装配：随包冻结规则包（与来源仓逐字节同 sha256）。"""
    return evaluate_with_docs(subject, basis, rules.ruleset_docs())


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "evaluate_with_docs",
           "evaluate_with_rules"]
