"""判定内核（迁自来源 ``rules.run_checks``）。

两道门控，顺序与来源一致：

1. **票种类目门控**：``applies_to`` 不含本票种 → 该规则不参与（防跨票种误查）；
2. **依据闸**：``basis.status != 已核对`` → 该规则产出的「不合规」一律降级为
   「待人工确认」（窄闸：只降「不合规」；「合规」与既有「待人工确认」不动）。
   闸门在 ``check()`` **之后**执行——若写成「跳过规则不执行」，
   ``required_field`` 的缺失检测会整块消失（字段缺失本身就是判据）。
"""

from .checks import CHECKS
from .model import (VERDICT_COMPLIANT, VERDICT_MANUAL, VERDICT_VIOLATION,
                    Conclusion, TicketCard)


def run_checks(card: TicketCard, rules) -> list:
    """逐条规则判定，返回结论列表（规则顺序，确定性）。"""
    conclusions = []
    for rule in rules:
        if card.ticket_type not in rule.get("applies_to", []):
            continue
        check = CHECKS.get(rule["check_type"])
        if check is None:
            raise ValueError("未知 check_type：%s（规则 %s）"
                             % (rule["check_type"], rule["id"]))
        produced = check(rule, card)
        if (rule.get("basis") or {}).get("status") != "已核对":
            for conclusion in produced:
                if conclusion.verdict == VERDICT_VIOLATION:
                    conclusion.verdict = VERDICT_MANUAL
                    conclusion.downgraded = True
        conclusions.extend(produced)
    return conclusions


def summarize(conclusions):
    """三级结论计数 + 风险分布（不做「全合规」以外的猜测）。"""
    counts = {VERDICT_COMPLIANT: 0, VERDICT_VIOLATION: 0, VERDICT_MANUAL: 0}
    risks = {}
    downgraded = 0
    for conclusion in conclusions:
        counts[conclusion.verdict] = counts.get(conclusion.verdict, 0) + 1
        if conclusion.verdict == VERDICT_VIOLATION and conclusion.risk:
            risks[conclusion.risk] = risks.get(conclusion.risk, 0) + 1
        if conclusion.downgraded:
            downgraded += 1
    return {
        "total": len(conclusions),
        "compliant": counts[VERDICT_COMPLIANT],
        "violation": counts[VERDICT_VIOLATION],
        "manual": counts[VERDICT_MANUAL],
        "downgraded": downgraded,
        "risk": dict(sorted(risks.items())),
    }


__all__ = ["run_checks", "summarize"]