"""判定内核（迁自来源 ``engine.thresholds`` / ``engine.checklist``）。

两条硬语义（来源 FR-1.2 / FR-2.5）：

1. **义务分栏**：命中的门槛按 ``effect`` 分「无条件义务」与「条件触发」两栏，
   结论不混同；``triggered`` 仅表示命中任一门槛。
2. **不误报合规**：不适用（门控不满足）记 ``not_applicable``，未观测记
   ``unknown``，两者都不进分母；一条适用项都没被评 → 汇总 ``not_assessed``，
   **绝不输出 compliant**。

与来源的一处口径差（如实登记，见 docs §5）：来源对「参数值类型不可比」静默
``continue``（该门槛既不触发也不留痕）；本器官改为**显式登记**
``type_mismatch``，不静默丢弃输入。
"""

from .model import (ALL_STATES, APPLICABLE_STATES, EFFECT_CONDITIONAL_INSTITUTION,
                    EFFECT_PERIODIC_OBLIGATION, EFFECT_STANDING_OBLIGATION,
                    METHOD_AUTO, STATE_COMPLIANT, STATE_NONCOMPLIANT,
                    STATE_NOT_APPLICABLE, STATE_PARTIAL, STATE_UNKNOWN,
                    SUMMARY_COMPLIANT, SUMMARY_NONCOMPLIANT,
                    SUMMARY_NOT_ASSESSED, SUMMARY_PARTIAL)
from .rules import OPS

# 门槛判定结果（单项）
OUTCOME_HIT = "hit"
OUTCOME_MISS = "miss"
OUTCOME_NO_INPUT = "no_input"
OUTCOME_TYPE_MISMATCH = "type_mismatch"

OUTCOME_LABELS = {
    OUTCOME_HIT: "命中",
    OUTCOME_MISS: "未触发",
    OUTCOME_NO_INPUT: "输入未提供参数，未判定",
    OUTCOME_TYPE_MISMATCH: "输入类型不可比，未判定",
}

EFFECT_LABELS = {
    EFFECT_PERIODIC_OBLIGATION: "无条件义务（周期性）",
    EFFECT_STANDING_OBLIGATION: "无条件义务（持续性）",
    EFFECT_CONDITIONAL_INSTITUTION: "条件触发（保护部门可以要求）",
}

# 问题分级（工具内部严重度序，非政策数值）
RISK_HIGH = "high"
RISK_MEDIUM = "medium"
_STATE_TO_RISK = {
    STATE_NONCOMPLIANT: RISK_HIGH,
    STATE_PARTIAL: RISK_MEDIUM,
}

_AUTO_NOTES = {
    STATE_COMPLIANT: "自动核查通过",
    STATE_PARTIAL: "自动核查部分符合",
    STATE_NONCOMPLIANT: "自动核查未通过",
    STATE_NOT_APPLICABLE: "自动核查判定为不适用",
    STATE_UNKNOWN: "自动核查未能判定",
}


class ThresholdOutcome:
    """一条门槛的判定留痕（含未触发与未判定的原因）。"""

    __slots__ = ("threshold", "outcome", "actual")

    def __init__(self, threshold, outcome, actual=None):
        self.threshold = threshold
        self.outcome = outcome
        self.actual = actual

    @property
    def hit(self):
        return self.outcome == OUTCOME_HIT

    def as_dict(self):
        return {
            "threshold_id": self.threshold.id,
            "param": self.threshold.param,
            "op": self.threshold.op,
            "value": self.threshold.value,
            "actual": self.actual,
            "outcome": self.outcome,
            "conclusion": self.threshold.conclusion,
            "effect": self.threshold.effect,
            "frequency": self.threshold.frequency,
            "severity": self.threshold.severity,
            "clause": {
                "basis": self.threshold.clause.basis,
                "article": self.threshold.clause.article,
                "point": self.threshold.clause.point,
            },
        }


class ThresholdResult:
    """门槛判定汇总（命中集合按 severity 降序、同级按义务类型序）。"""

    def __init__(self, outcomes, matched):
        self.outcomes = list(outcomes)
        self.matched = list(matched)

    @property
    def triggered(self):
        return any(threshold.severity > 0 for threshold in self.matched)

    @property
    def obligations(self):
        return [threshold for threshold in self.matched if not threshold.is_conditional()]

    @property
    def conditional_triggers(self):
        return [threshold for threshold in self.matched if threshold.is_conditional()]

    @property
    def frequency(self):
        for threshold in self.obligations:
            if threshold.frequency:
                return threshold.frequency
        return ""

    @property
    def conclusions(self):
        out, seen = [], set()
        for threshold in self.matched:
            if threshold.conclusion not in seen:
                seen.add(threshold.conclusion)
                out.append(threshold.conclusion)
        return out

    def as_dict(self):
        return {
            "triggered": self.triggered,
            "conclusions": list(self.conclusions),
            "frequency": self.frequency,
            "obligations": [threshold.conclusion for threshold in self.obligations],
            "conditional_triggers": [threshold.conclusion
                                     for threshold in self.conditional_triggers],
            "outcomes": [entry.as_dict() for entry in self.outcomes],
        }


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _effect_rank(threshold):
    if threshold.effect == EFFECT_PERIODIC_OBLIGATION:
        return 0
    if threshold.effect == EFFECT_STANDING_OBLIGATION:
        return 1
    if threshold.effect == EFFECT_CONDITIONAL_INSTITUTION:
        return 2
    return 3


def evaluate_thresholds(ruleset, input_card):
    """按规则包逐条门槛判定；命中按 severity 降序、同级按义务类型序归并。"""
    outcomes = []
    for threshold in ruleset.thresholds:
        if threshold.param not in input_card:
            outcomes.append(ThresholdOutcome(threshold, OUTCOME_NO_INPUT))
            continue
        actual = input_card[threshold.param]
        if not _is_number(actual):
            outcomes.append(ThresholdOutcome(threshold, OUTCOME_TYPE_MISMATCH, actual))
            continue
        op = OPS.get(threshold.op)
        try:
            hit = bool(op(actual, threshold.value))
        except TypeError:
            outcomes.append(ThresholdOutcome(threshold, OUTCOME_TYPE_MISMATCH, actual))
            continue
        outcomes.append(ThresholdOutcome(
            threshold, OUTCOME_HIT if hit else OUTCOME_MISS, actual))

    matched = [entry.threshold for entry in outcomes if entry.hit]
    matched.sort(key=lambda threshold: (-threshold.severity, _effect_rank(threshold)))
    return ThresholdResult(outcomes, matched)


class ItemResult:
    """一条检查项的判定结果。"""

    __slots__ = ("item", "state", "note")

    def __init__(self, item, state, note=""):
        self.item = item
        self.state = state
        self.note = note

    @property
    def risk(self):
        return _STATE_TO_RISK.get(self.state)

    def as_dict(self):
        return {
            "item_id": self.item.id,
            "category": self.item.category,
            "title": self.item.title,
            "method": self.item.method,
            "state": self.state,
            "note": self.note,
            "risk": self.risk,
            "evidence_required": self.item.evidence_required,
            "clause": {
                "basis": self.item.clause.basis,
                "article": self.item.clause.article,
                "point": self.item.clause.point,
            },
        }


def _gated_out(item, input_card):
    """only_if 门控：任一条件不满足即不适用。"""
    gate = item.only_if
    if not gate:
        return False
    for key, allowed in gate.items():
        if input_card.get(key) not in allowed:
            return True
    return False


def _is_present(value):
    """非空判定：``True`` 或非空白字符串视为"有"（来源旧口径的兜底映射）。"""
    return value is True or (isinstance(value, str) and bool(value.strip()))


def _map_auto(item, value):
    mapping = item.auto_mapping
    if mapping is not None and not mapping.is_empty():
        state = mapping.match(value)
        if state in ALL_STATES:
            return state
    return STATE_COMPLIANT if _is_present(value) else STATE_NONCOMPLIANT


def evaluate_item(item, input_card, manual_results):
    """单检查项判定（auto 按规则包映射 / manual 按人工录入，缺项记 unknown）。"""
    if _gated_out(item, input_card):
        return ItemResult(item, STATE_NOT_APPLICABLE, "门控不满足，不适用")

    if item.method == METHOD_AUTO:
        field = item.auto_field
        if field is None or field not in input_card:
            return ItemResult(item, STATE_UNKNOWN, "自动核查字段缺失，未观测")
        state = _map_auto(item, input_card[field])
        return ItemResult(item, state, _AUTO_NOTES.get(state, "自动核查"))

    record = manual_results.get(item.id)
    if record is None:
        return ItemResult(item, STATE_UNKNOWN, "未录入，待人工确认")
    state = record.get("state", STATE_UNKNOWN)
    if state not in ALL_STATES:
        state = STATE_UNKNOWN
    return ItemResult(item, state, record.get("note", ""))


def summarize(results):
    """汇总：适用项为空 → ``not_assessed``（绝不输出 compliant）。"""
    applicable = [result for result in results if result.state in APPLICABLE_STATES]
    if not applicable:
        return SUMMARY_NOT_ASSESSED
    if any(result.state == STATE_NONCOMPLIANT for result in applicable):
        return SUMMARY_NONCOMPLIANT
    if any(result.state == STATE_PARTIAL for result in applicable):
        return SUMMARY_PARTIAL
    return SUMMARY_COMPLIANT


def counts(results):
    """各状态计数 + 问题分级计数（确定性键序）。"""
    tally = {state: 0 for state in (
        STATE_COMPLIANT, STATE_PARTIAL, STATE_NONCOMPLIANT,
        STATE_NOT_APPLICABLE, STATE_UNKNOWN)}
    for result in results:
        tally[result.state] = tally.get(result.state, 0) + 1
    tally["total"] = len(results)
    tally["applicable"] = sum(tally[state] for state in APPLICABLE_STATES)
    tally["risk_high"] = sum(1 for result in results if result.risk == RISK_HIGH)
    tally["risk_medium"] = sum(1 for result in results if result.risk == RISK_MEDIUM)
    return tally


__all__ = [
    "OUTCOME_HIT", "OUTCOME_MISS", "OUTCOME_NO_INPUT", "OUTCOME_TYPE_MISMATCH",
    "OUTCOME_LABELS", "EFFECT_LABELS", "RISK_HIGH", "RISK_MEDIUM",
    "ThresholdOutcome", "ThresholdResult", "evaluate_thresholds",
    "ItemResult", "evaluate_item", "summarize", "counts",
]