"""租赁条款判定内核（**零 I/O / 零时钟 / 零环境变量 / 零政策字面量**）。

迁移的是来源产品的判定面：规则包门控（含全国层叠加）+ 五态判定 + 义务分栏。
只保留「卡片事实 → 逐条判定」这一段：

- **五态**：``compliant`` / ``noncompliant`` / ``skipped`` / ``unknown`` / ``not_assessed``；
- **适用域三态**：``applies`` / ``not_applies`` / ``indeterminate``——主体未知判
  ``unknown``（**不是** ``skipped``），绝不替用户断言「这条不适用」；
- **无条件义务缺失 = noncompliant**，绝不记 ``skipped``；
- **门控**：``status != verified`` 或**缺锚点**（条款号 / 法条原文 / 来源）的规则
  不得进入判定路径，逐条记入未启用清单；
- **义务分栏**：``scope=quota``（监管裁量/提示性条款）不作为相对人义务判定。

政策数值**只能来自** :mod:`registry`（规则包快照）；本模块只出现运算符与派发表。

本模块不读合同文件：``judge_card`` 收**已抽取的卡片**（字段取值 + 条款列表 +
合同原文）。条款切分与要素抽取属输入层，见 ``docs/lease-terms.md`` §5。
"""

from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import registry

# ------------------------------------------------------------------ 判定五态
STATUS_COMPLIANT = "compliant"
STATUS_NONCOMPLIANT = "noncompliant"
STATUS_SKIPPED = "skipped"
STATUS_UNKNOWN = "unknown"
STATUS_NOT_ASSESSED = "not_assessed"
ALL_STATUSES = (STATUS_COMPLIANT, STATUS_NONCOMPLIANT, STATUS_SKIPPED, STATUS_UNKNOWN,
                STATUS_NOT_ASSESSED)

# ------------------------------------------------------------------ 适用域三态
APPLIES = "applies"
NOT_APPLIES = "not_applies"
INDETERMINATE = "indeterminate"

# ------------------------------------------------------------------ 作用域
SCOPES = ("calc", "check", "quota")
PARTIES = ("enterprise", "individual", "unknown")
LEASE_KINDS = ("ordinary", "affordable")

#: 条件触发栏的事由
REFERENCE_REASON = "该条为监管裁量/提示性条款，不构成相对人的无条件义务，仅作提示"

_OPERATORS = {
    "<=": lambda left, right: left <= right,
    "<": lambda left, right: left < right,
    ">=": lambda left, right: left >= right,
    ">": lambda left, right: left > right,
    "==": lambda left, right: left == right,
}


class CardError(ValueError):
    """卡片/输入不合法。内核映射退出码 2。"""


class RulesetError(ValueError):
    """规则包不可用（城市未登记 / 门控拦截 / 缺锚点）。"""


# ------------------------------------------------------------------ 卡片
def validate_card(card: Any) -> Mapping:
    """卡片结构校验（不合法抛 :class:`CardError`）。"""
    if not isinstance(card, Mapping):
        raise CardError("卡片必须是 JSON 对象，得到 %s" % type(card).__name__)
    city = card.get("city")
    if city not in registry.CITY_RULESETS:
        raise CardError("未登记的城市: %r（可选：%s）"
                        % (city, "、".join(registry.CITY_RULESETS)))
    party = card.get("party", "unknown")
    if party not in PARTIES:
        raise CardError("未知合同主体: %r（可选：%s）" % (party, "、".join(PARTIES)))
    lease_kind = card.get("lease_kind", "ordinary")
    if lease_kind not in LEASE_KINDS:
        raise CardError("未知租赁类型: %r（可选：%s）"
                        % (lease_kind, "、".join(LEASE_KINDS)))
    fields = card.get("fields", {})
    if not isinstance(fields, Mapping):
        raise CardError("fields 必须是对象（要素名 → 取值）")
    text = card.get("contract_text")
    if text is not None and not isinstance(text, str):
        raise CardError("contract_text 必须是字符串")
    clauses = card.get("clauses", [])
    if not isinstance(clauses, (list, tuple)):
        raise CardError("clauses 必须是数组")
    for clause in clauses:
        if not isinstance(clause, Mapping) or not clause.get("number"):
            raise CardError("clauses 的每一条都必须有 number")
    return card


def field_value(card: Mapping, name: Optional[str]) -> Any:
    """取卡片要素值（缺省 → ``None`` = 未观测；``None`` 显式值同样视为未观测）。"""
    if not name:
        return None
    return card.get("fields", {}).get(name)


def is_observed(card: Mapping, name: Optional[str]) -> bool:
    return field_value(card, name) is not None


# ------------------------------------------------------------------ 门控
def _has_anchor(rule: Mapping) -> Tuple[bool, Tuple[str, ...]]:
    """锚点门：条款号 / 条款 id / 来源缺一即不得进判定路径。"""
    missing = []
    if not rule.get("clause"):
        missing.append("条款号")
    if not rule.get("clause_id"):
        missing.append("条文锚点")
    if not rule.get("source_id"):
        missing.append("来源")
    return (not missing), tuple(missing)


def gate_rules(rules: Sequence[Mapping], scope: str = "calc") -> Dict[str, Any]:
    """门控：返回 ``{"kept", "reference", "disabled"}``。

    作用域语义：``calc`` → 取 ``scope ∈ {calc, check}`` 的已核对条目；``check`` /
    ``quota`` → 只取同名作用域。``quota`` 条目在 ``calc`` 下**不作为义务**，
    但进 ``reference``（条件触发栏）——「没查」与「查了没问题」必须可区分。
    """
    if scope not in SCOPES:
        raise RulesetError("未知作用域: %s（可选：%s）" % (scope, "/".join(SCOPES)))
    wanted = {"calc", "check"} if scope == "calc" else {scope}

    kept, reference, disabled = [], [], []
    for rule in rules:
        anchored, missing = _has_anchor(rule)
        if rule.get("status") != "verified":
            if rule.get("scope") in wanted or rule.get("scope") == "quota":
                disabled.append({"rule_id": rule["rule_id"], "title": rule["title"],
                                 "status": rule.get("status"),
                                 "reason": "数值核对状态非 verified，不参与判定"})
            continue
        if not anchored:
            if rule.get("scope") in wanted or rule.get("scope") == "quota":
                disabled.append({"rule_id": rule["rule_id"], "title": rule["title"],
                                 "status": rule.get("status"),
                                 "reason": "缺锚点（%s），不参与判定" % "、".join(missing)})
            continue
        if rule.get("scope") == "quota":
            if scope == "quota":
                # 口径差：来源仓在 quota 作用域下实际返回空集（分支先 continue）；
                # 本器官保留 quota 条目，供「只查裁量条款」的用途。
                kept.append(rule)
            elif scope == "calc":
                reference.append(rule)
            continue
        if rule.get("scope") in wanted:
            kept.append(rule)
    return {"kept": kept, "reference": reference, "disabled": disabled}


def effective_rules(city: str, scope: str = "calc",
                    rules: Optional[Sequence[Mapping]] = None) -> Dict[str, Any]:
    """按城市叠加全国层后门控（器官的主入口之一）。"""
    if city not in registry.CITY_RULESETS:
        raise RulesetError("未登记的城市: %r" % (city,))
    merged = list(registry.rules_for_overlay(city)) if rules is None else list(rules)
    return gate_rules(merged, scope)


# ------------------------------------------------------------------ 适用域
def applicability(rule: Mapping, card: Mapping) -> str:
    """``applies_if`` 三态判定。

    **关键区分**（防「把没做记成不用做」的反向陷阱）：

    - 已知主体不满足适用条件 → ``not_applies``（原文明确写了适用情形限制）→ ``skipped``；
    - 主体**未知**、无法确定是否适用 → ``indeterminate`` → ``unknown``（不是 ``skipped``）。

    若把 ``indeterminate`` 记成 ``skipped``，等于替用户断言「这条不适用」——合规结论虚高。
    """
    condition = rule.get("applies_if") or {}
    party = condition.get("party")
    if party and "any" not in party:
        if card.get("party", "unknown") == "unknown":
            return INDETERMINATE
        if card.get("party") not in party:
            return NOT_APPLIES
    kinds = condition.get("lease_kind")
    if kinds and "any" not in kinds:
        if card.get("lease_kind", "ordinary") not in kinds:
            return NOT_APPLIES
    return APPLIES


def _reason_indeterminate(rule: Mapping) -> str:
    party = (rule.get("applies_if") or {}).get("party") or []
    return ("无法确定合同主体（合同未载明出租人为%s），本规则是否适用存疑，"
            "需人工确认主体性质后重新判定" % "/".join(party))


def _reason_skipped(rule: Mapping, card: Mapping) -> str:
    condition = rule.get("applies_if") or {}
    bits = []
    if condition.get("party") and "any" not in condition["party"]:
        bits.append("适用主体限于 %s（本合同主体判定为 %s）"
                    % ("/".join(condition["party"]), card.get("party", "unknown")))
    if condition.get("lease_kind") and "any" not in condition["lease_kind"]:
        bits.append("适用房屋类型限于 %s（本合同为 %s）"
                    % ("/".join(condition["lease_kind"]), card.get("lease_kind", "ordinary")))
    return "；".join(bits) or "适用条件不满足"


# ------------------------------------------------------------------ 逐条判定
def _as_decimal(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except (ArithmeticError, ValueError):
            return value
    return value


def limit_words(op: Optional[str]) -> Tuple[str, str]:
    """按运算符给出「合规/违规」两侧的方向措辞（把义务方向说反是硬伤）。"""
    if op in (">=", ">"):
        return "不低于规则下限", "低于规则下限"
    return "未超过规则上限", "超过规则上限"


def _base(rule: Mapping, status: str, reason: str, **extra: Any) -> Dict[str, Any]:
    finding = {
        "rule_id": rule["rule_id"],
        "title": rule["title"],
        "status": status,
        "check_type": rule["check_type"],
        "effect": rule["effect"],
        "severity": rule["severity"],
        "scope": rule["scope"],
        "reason": reason,
        "param": rule.get("param"),
        "observed": None,
        "limit": None,
        "op": rule.get("op"),
        "unit": rule.get("unit"),
        "clause": rule.get("clause"),
        "clause_id": rule.get("clause_id"),
        "source_id": rule.get("source_id"),
    }
    finding.update(extra)
    return finding


def check_numeric(rule: Mapping, card: Mapping) -> Dict[str, Any]:
    """数值阈值判定（上限/下限由 ``op`` 决定，方向措辞不混用）。"""
    if rule.get("op") is None or rule.get("value") is None:
        return _base(rule, STATUS_UNKNOWN, "该条无明确数值阈值，无法作数值判定")
    if not is_observed(card, rule.get("param")):
        return _base(rule, STATUS_UNKNOWN,
                     "合同未载明或无法抽取「%s」，无法判定" % (rule.get("param") or rule["title"]),
                     limit=rule.get("value"))
    observed = _as_decimal(field_value(card, rule.get("param")))
    limit = _as_decimal(rule.get("value"))
    if not isinstance(observed, Decimal) or not isinstance(limit, Decimal):
        # 卡片给的是非数值（如「一个月」）→ 拒判，不猜换算（旧仓此处会抛 TypeError）
        return _base(rule, STATUS_UNKNOWN,
                     "约定值不是数值（%r），无法作数值判定" % (field_value(card, rule.get("param")),),
                     limit=rule.get("value"))
    compare = _OPERATORS.get(rule.get("op"))
    if compare is None:
        return _base(rule, STATUS_UNKNOWN, "未知运算符 %s，无法判定" % rule.get("op"))
    ok = compare(observed, limit)
    status = STATUS_COMPLIANT if ok else STATUS_NONCOMPLIANT
    ok_words, bad_words = limit_words(rule.get("op"))
    reason = "约定 %s%s，%s %s%s" % (observed, rule.get("unit") or "",
                                    ok_words if ok else bad_words,
                                    limit, rule.get("unit") or "")
    return _base(rule, status, reason, observed=field_value(card, rule.get("param")),
                 limit=rule.get("value"))


def check_deadline(rule: Mapping, card: Mapping) -> Dict[str, Any]:
    """期限/程序性判定：有数值阈值走数值判定，无阈值的看「是否已约定」。"""
    if rule.get("op") is None or rule.get("value") is None:
        if is_observed(card, rule.get("param")):
            declared = field_value(card, rule.get("param"))
            if declared is True:
                return _base(rule, STATUS_COMPLIANT, "合同已约定该项期限")
            if declared is False:
                return _base(rule, STATUS_UNKNOWN,
                             "合同未约定该项，依本条法定补充规则处理（非法定违反，仅提示）")
        return _base(rule, STATUS_UNKNOWN, "该条为程序性补充规则，无数值阈值，无法作数值判定")
    return check_numeric(rule, card)


def looks_like_lease_contract(card: Mapping) -> bool:
    """文本是否可识别为租赁合同。

    必要性：对**非合同文本**判「缺失法定要素 = noncompliant」是**假 noncompliant**
    ——比 unknown 更糟（冤枉用户，且把「这不是合同」说成「你的合同不合格」）。
    """
    text = card.get("contract_text") or ""
    if not text:
        return False
    has_keyword = any(keyword in text for keyword in ("租赁", "出租", "承租", "租金", "押金"))
    return has_keyword and bool(card.get("clauses"))


def check_elements(rule: Mapping, card: Mapping) -> Dict[str, Any]:
    """定性检查：按要素别名表逐项匹配合同原文（别名表防「措辞不同被判缺失」）。"""
    text = card.get("contract_text") or ""
    elements = rule.get("elements") or ()
    if not elements:
        return _base(rule, STATUS_UNKNOWN, "规则未登记要素清单，无法判定")
    if not text:
        return _base(rule, STATUS_UNKNOWN, "无合同文本，无法判定要素完整性")
    if not looks_like_lease_contract(card):
        return _base(rule, STATUS_UNKNOWN,
                     "输入文本不构成可识别的租赁合同，无法评估要素完整性（未观测，非缺失）")

    missing = []
    for name, aliases in elements:
        candidates = (name,) + tuple(aliases)
        if not any(candidate and candidate in text for candidate in candidates):
            missing.append(name)
    if not missing:
        return _base(rule, STATUS_COMPLIANT, "法定要素全部载明（%d 项）" % len(elements))
    return _base(rule, STATUS_NONCOMPLIANT,
                 "缺失法定要素 %d 项：%s（建议补充）" % (len(missing), "、".join(missing)))


def check_prohibition(rule: Mapping, card: Mapping) -> Dict[str, Any]:
    """禁止性/提示性条款：不作为本合同判定，归条件触发栏。"""
    return _base(rule, STATUS_SKIPPED, "该条为监管裁量/提示性条款，不针对本合同判定")


_DISPATCH = {
    "numeric_limit": check_numeric,
    "deadline_obligation": check_deadline,
    "element_completeness": check_elements,
    "text_prohibition": check_prohibition,
}


def judge_rule(rule: Mapping, card: Mapping) -> Dict[str, Any]:
    """单条规则的判定（含适用域门）。"""
    state = applicability(rule, card)
    if state == NOT_APPLIES:
        return _base(rule, STATUS_SKIPPED, _reason_skipped(rule, card))
    if state == INDETERMINATE:
        return _base(rule, STATUS_UNKNOWN, _reason_indeterminate(rule))
    handler = _DISPATCH.get(rule.get("check_type"))
    if handler is None:
        return _base(rule, STATUS_UNKNOWN, "未知判定类型 %s，无法判定" % rule.get("check_type"))
    return handler(rule, card)


def judge_card(card: Mapping, rules: Sequence[Mapping]) -> List[Dict[str, Any]]:
    """逐条判定（同一规则包版本 + 同一输入 = 同一输出）。"""
    return [judge_rule(rule, card) for rule in rules]


def reference_findings(rules: Sequence[Mapping]) -> List[Dict[str, Any]]:
    """条件触发栏（``scope=quota``）：不是义务，但必须显式呈现。"""
    out = []
    for rule in rules:
        finding = _base(rule, "reference", REFERENCE_REASON)
        out.append(finding)
    return out


def overall_status(findings: Sequence[Mapping]) -> str:
    """整体等级（保守口径）。

    - 无任何有效判定（全 ``skipped``）→ ``not_assessed``（绝不输出 ``compliant``）；
    - 有 ``noncompliant`` → ``noncompliant``；
    - 有 ``unknown`` → ``not_assessed``（结论不完整，**不声称合规**）；
    - 否则 ``compliant``。
    """
    effective = [finding for finding in findings
                 if finding.get("status") != STATUS_SKIPPED]
    if not effective:
        return STATUS_NOT_ASSESSED
    if any(finding["status"] == STATUS_NONCOMPLIANT for finding in effective):
        return STATUS_NONCOMPLIANT
    if any(finding["status"] in (STATUS_UNKNOWN, STATUS_NOT_ASSESSED) for finding in effective):
        return STATUS_NOT_ASSESSED
    return STATUS_COMPLIANT


def status_counts(findings: Sequence[Mapping]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for finding in findings:
        out[finding["status"]] = out.get(finding["status"], 0) + 1
    return out


def summary_text(findings: Sequence[Mapping]) -> str:
    counts = status_counts(findings)
    assessed = sum(value for key, value in counts.items() if key != STATUS_SKIPPED)
    parts = ["已判定 %d 项" % assessed]
    if counts.get(STATUS_UNKNOWN):
        parts.append("其中未能判定 %d 项（需人工确认或补充合同信息）" % counts[STATUS_UNKNOWN])
    if counts.get(STATUS_SKIPPED):
        parts.append("不适用 %d 项" % counts[STATUS_SKIPPED])
    return "%s（%s）" % (overall_status(findings), "，".join(parts))


__all__ = [
    "STATUS_COMPLIANT", "STATUS_NONCOMPLIANT", "STATUS_SKIPPED", "STATUS_UNKNOWN",
    "STATUS_NOT_ASSESSED", "ALL_STATUSES", "APPLIES", "NOT_APPLIES", "INDETERMINATE",
    "SCOPES", "PARTIES", "LEASE_KINDS", "REFERENCE_REASON",
    "CardError", "RulesetError", "validate_card", "field_value", "is_observed",
    "gate_rules", "effective_rules", "applicability", "limit_words", "check_numeric",
    "check_deadline", "looks_like_lease_contract", "check_elements", "check_prohibition",
    "judge_rule", "judge_card", "reference_findings", "overall_status", "status_counts",
    "summary_text",
]