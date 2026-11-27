"""器官 ``food-label``：预包装食品标签双标尺判定（GB 7718-2011 现行 / 2025 过渡期）。

规模：判定面来自 target-map ① 行的旧仓（双标尺规则引擎 47 条：21 + 26；
11 种检查类型；数值复算 NRV%/能量/声称阈值/到期日；三级判定；
依据待核对标记；双标尺差异对照）。

本器官只做一件事：**给一张已解析的标签参数卡，分别按 GB 7718-2011（现行）
与 GB 7718-2025（过渡期）判合规，输出「现行合规 / 新规不合规」对照，每条
结论挂标准条款出处与标签原文证据**。它不打印、不读环境变量、不读时钟，
也不带自己的参数解析器——入口只有
``clauseproof check food-label --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

==============================  ==========================================
来源结论                         本器官 verdict
==============================  ==========================================
``不合规``                        ``fail``（必带锚点；阻断 → 退出码 1）
``待人工确认``                    ``not_applicable``（"没判定"≠"判出违规"，必带锚点）
``合规``                          ``pass``（锚点：对应契约条目）
双标尺差异（dual_diff）            ``pass``（汇总记录，携带新增/消除不合规项）
审查完成（stats 汇总）             ``pass``（汇总记录）
==============================  ==========================================

依据只从条文库取：``basis.anchor(clause_id)``。条款锚点按 ``check_type`` 映射
到数值口径条目或数据契约条目；**标准条款号**（GB 7718 条款）逐条进
``evidence``（source 的规则级 ``basis`` 原样携带，不冒充条文库内容）。

条文库缺所需条款 → ``BasisMissing`` 冒到 CLI（退出码 3）；条文库版本与规则包
快照不符 → ``ContractError``（退出码 3）。

**解析层不进器官**：文本标签 → 参数卡（字段抽取、逐字证据、非规范日期归一）
留在输入层（`SKELETON-SPEC` §2：器官不得做文件 IO）；subject 收参数卡
（``card``）与可选纯文本（``text``，仅作门控平文本的补充）。
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

SLUG = "food-label"
VERSION = "0.1.0"
SUMMARY = ("预包装食品标签双标尺判定（GB 7718-2011 现行 / 2025 过渡期 47 条规则；"
           "11 种检查类型 + 数值复算 + 三级判定；人食品，非宠物食品）")

#: 输入必填字段
INPUT_FIELDS = ("card",)

#: 规则单号（一条结论 = 规则 + 锚点）
RULE_FINDING = "label.finding"
RULE_DUAL_DIFF = "label.dual_diff"
RULE_RESULT = "label.result"

#: 三级判定 → verdict 映射（SKELETON-SPEC §3 判定账本）
_LEVEL_VERDICT = {
    engine.LEVEL_PASS: PASS,
    engine.LEVEL_FAIL: FAIL,
    engine.LEVEL_MANUAL: NOT_APPLICABLE,
}


def _require_basis_version(basis: Basis) -> None:
    if basis.version != rules.PARAMS_VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据规则包快照 %s 核对，条文库实为 %s"
            % (rules.PARAMS_VERSION, basis.version)
        )


def _clause_of(ruleset_id: str, rule_id: str) -> str:
    check_type = rules.rule_check_type(ruleset_id, rule_id)
    return rules.CHECK_TYPE_CLAUSE.get(check_type, rules.CLAUSE_THREE_LEVELS)


def _findings(result: Mapping, basis: Basis) -> List[Finding]:
    findings: List[Finding] = []

    for ruleset_id in sorted(result["results"]):
        payload = result["results"][ruleset_id]
        # ① 逐条规则结论（三级 → pass / fail / not_applicable）
        for finding in payload["findings"]:
            clause_id = _clause_of(ruleset_id, finding["rule_id"])
            basis_payload = dict(finding.get("basis") or {})
            message = "%s [%s] %s" % (finding["level"], ruleset_id, finding["message"])
            if finding.get("flagged_pending_basis"):
                message += "（依据待核对）"
            findings.append(Finding(
                rule_id="%s:%s:%s" % (RULE_FINDING, ruleset_id, finding["rule_id"]),
                verdict=_LEVEL_VERDICT[finding["level"]],
                message=message,
                anchor=basis.anchor(clause_id),
                evidence={
                    "ruleset_id": ruleset_id,
                    "rule_id": finding["rule_id"],
                    "level": finding["level"],
                    "standard": basis_payload.get("standard"),
                    "clause": basis_payload.get("clause"),
                    "quote_ref": basis_payload.get("quote_ref"),
                    "basis_status": basis_payload.get("status"),
                    "flagged_pending_basis": bool(finding.get("flagged_pending_basis")),
                    "advice": finding.get("advice", ""),
                },
            ))

    # ② 双标尺差异对照（新增/消除的不合规项）
    diff = result["dual_diff"]
    findings.append(Finding(
        rule_id=RULE_DUAL_DIFF,
        verdict=PASS,
        message=("双标尺对照：%s → %s；新增不合规 %d 项（%s）；消除不合规 %d 项（%s）")
                % (diff["baseline"], diff["target"], len(diff["new_fails"]),
                   "、".join(diff["new_fails"]) or "无",
                   len(diff["resolved_fails"]),
                   "、".join(diff["resolved_fails"]) or "无"),
        anchor=basis.anchor(rules.CLAUSE_DUAL_RULESETS),
        evidence={
            "baseline": diff["baseline"],
            "target": diff["target"],
            "new_fails": list(diff["new_fails"]),
            "resolved_fails": list(diff["resolved_fails"]),
        },
    ))

    # ③ 审查完成（统计口径：pass+fail+manual == checked）
    stats_view = {rid: dict(payload["stats"]) for rid, payload in sorted(result["results"].items())}
    total_fails = sum(s["fail"] for s in stats_view.values())
    total_manual = sum(s["manual"] for s in stats_view.values())
    findings.append(Finding(
        rule_id=RULE_RESULT,
        verdict=PASS,
        message=("双标尺审查完成：不合规 %d 条 / 待人工确认 %d 条；%s")
                % (total_fails, total_manual,
                   "；".join("%s checked=%d skipped=%d not_run=%d"
                             % (rid, s["checked"], s["skipped"], s["not_run"])
                             for rid, s in stats_view.items())),
        anchor=basis.anchor(rules.CLAUSE_STATS),
        evidence={"stats": stats_view, "fail": total_fails, "manual": total_manual},
    ))
    return findings


# ------------------------------------------------------------------ 输入校验
def validate_subject(subject: Mapping) -> None:
    """subject 结构校验（非法抛 :class:`engine.LabelError`，内核映射 2）。"""
    if not isinstance(subject, Mapping):
        raise engine.LabelError("输入必须是 JSON 对象，得到 %s" % type(subject).__name__)
    card = subject.get("card")
    if not isinstance(card, Mapping):
        raise engine.LabelError("缺少 card（标签参数卡）")
    fields = card.get("fields")
    if fields is not None and not isinstance(fields, Mapping):
        raise engine.LabelError("card.fields 必须是对象")
    for name, entry in (fields or {}).items():
        if not isinstance(entry, Mapping):
            raise engine.LabelError("card.fields[%r] 必须是对象" % name)
        if "value" not in entry:
            raise engine.LabelError("card.fields[%r] 缺少 value" % name)
    table = card.get("nutrition_table")
    if table is not None:
        if not isinstance(table, (list, tuple)):
            raise engine.LabelError("card.nutrition_table 必须是数组")
        for row in table:
            if not isinstance(row, Mapping) or "name" not in row:
                raise engine.LabelError("card.nutrition_table 行必须是含 name 的对象")
    for key in ("ingredients", "claims", "unresolved"):
        value = card.get(key)
        if value is not None and not isinstance(value, (list, tuple)):
            raise engine.LabelError("card.%s 必须是数组" % key)
    if subject.get("rulesets") is not None:
        ids = subject["rulesets"]
        if not isinstance(ids, (list, tuple)) or not ids:
            raise engine.LabelError("rulesets 必须是非空数组（2011 / 2025）")
        for rid in ids:
            if rid not in engine.AVAILABLE_RULESETS:
                raise engine.LabelError("未知规则集 id：%r" % (rid,))


# ------------------------------------------------------------------ 器官入口
def evaluate_with_pack(subject: Mapping, basis: Basis,
                       ruleset_docs: Mapping[str, Any],
                       reference) -> Iterable[Finding]:
    """判定用入口（测试可注入规则包；``evaluate`` 用随包规则包走同一路径）。"""
    _require_basis_version(basis)
    validate_subject(subject)
    card = dict(subject["card"])
    if "text" in subject:
        card["text"] = subject["text"]
    ids = list(subject.get("rulesets") or engine.AVAILABLE_RULESETS)
    results = engine.run_dual(card, ruleset_docs, reference, ids)
    diff = engine.dual_diff(results, ids[0], ids[-1])
    return tuple(_findings({"results": results, "dual_diff": diff}, basis))


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_pack(subject, basis, rules.rulesets(),
                              rules.nutrient_reference())


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "evaluate_with_pack",
           "validate_subject"]