"""宠物食品标签判定内核（**零 I/O / 零时钟 / 零环境变量 / 零限值字面量**）。

逐条移植 target-map ① 行来源产品的判定语义（``pflc/engine`` +
``pflc/model`` 的五态），只保留"输入 → 判定"这一段：

- ``presence``：标示项是否提供。**无条件义务缺失 = 不符合**（"没做绝不记成不用做"）；
  条件触发项缺失 → ``unknown``（待人工确认，不冤枉）；
- ``threshold``：保证值 vs 限值（全程 ``Decimal``）。保证值缺失 → ``not_provided``
  （不是不符合）；限值为**干物质基准**时先换算（``干基 = 标示值 / (1 - 水分%/100)``），
  水分缺失/越界 → ``unknown(basis_undetermined)``，**绝不拿未换算的值直接比**；
- ``claim_support``：只查"宣称存在 → 适用条件要求的信息支撑是否齐备"，不做语义硬判；
  未宣称 → ``skipped``（前提不成立，不是违规）；
- **适用性**：``applies_if`` 未命中的规则不参与；有生效规则但无适用项 →
  该维度"未评估"（绝不输出合规）。

限值只存在于 :mod:`registry`（规则包）；本模块不得出现限值字面量。
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

# ------------------------------------------------------------------ 判定方式
KIND_PRESENCE = "presence"
KIND_THRESHOLD = "threshold"
KIND_CLAIM_SUPPORT = "claim_support"
KINDS = (KIND_PRESENCE, KIND_THRESHOLD, KIND_CLAIM_SUPPORT)

OPERATORS = (">=", "<=", ">", "<", "==")
_OPERATOR_FUNCS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}

# ------------------------------------------------------------------ 效果 / 基准
EFFECT_OBLIGATION = "obligation"
EFFECT_CONDITIONAL = "conditional"
EFFECTS = (EFFECT_OBLIGATION, EFFECT_CONDITIONAL)

BASIS_AS_FED = "as_fed"
BASIS_DRY_MATTER = "dry_matter"
BASES = (BASIS_AS_FED, BASIS_DRY_MATTER)

# ------------------------------------------------------------------ 五态
VERDICT_COMPLIANT = "compliant"
VERDICT_NONCOMPLIANT = "noncompliant"
VERDICT_NOT_PROVIDED = "not_provided"
VERDICT_SKIPPED = "skipped"
VERDICT_UNKNOWN = "unknown"
VERDICTS = (VERDICT_COMPLIANT, VERDICT_NONCOMPLIANT,
            VERDICT_NOT_PROVIDED, VERDICT_SKIPPED, VERDICT_UNKNOWN)

# ------------------------------------------------------------------ 核对状态
STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"

#: 水分字段（干物质换算的唯一依据）
FIELD_MOISTURE = "水分"

#: 标签档案可提供的非保证值字段
LABEL_FIELDS = ("product_name", "category", "life_stage", "ingredients",
                "additives", "net_content", "producer", "product_dates")

REASON_NOT_FOUND = "not_found"
REASON_BASIS_UNDETERMINED = "basis_undetermined"

DIM_LABEL = "label"
DIM_NUTRITION = "nutrition"
DIM_CLAIM = "claim"
DIMENSIONS = (DIM_LABEL, DIM_NUTRITION, DIM_CLAIM)

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)


class PackError(ValueError):
    """输入不合法（标签档案结构缺陷）。内核映射退出码 2。"""


class RuleError(ValueError):
    """规则自相矛盾（缺 op/value、运算符不支持）。"""


# ------------------------------------------------------------------ 规则
@dataclass(frozen=True)
class Rule:
    """单条判定规则（字段名与来源规则包 JSON 一一对应）。"""

    rule_id: str
    dimension: str
    kind: str
    target: str
    effect: str
    op: Optional[str]
    value: Optional[str]
    unit: Optional[str]
    basis: str
    applies_if: Mapping[str, Tuple[str, ...]]
    required_support: Tuple[str, ...]
    status: str
    clause_id: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError("规则 %s 的 kind 非法：%r" % (self.rule_id, self.kind))
        if self.dimension not in DIMENSIONS:
            raise ValueError("规则 %s 的 dimension 非法：%r" % (self.rule_id, self.dimension))
        if self.effect not in EFFECTS:
            raise ValueError("规则 %s 的 effect 非法：%r" % (self.rule_id, self.effect))
        if self.basis not in BASES:
            raise ValueError("规则 %s 的 basis 非法：%r" % (self.rule_id, self.basis))
        if self.kind == KIND_THRESHOLD and self.is_effective:
            if self.op not in OPERATORS:
                raise ValueError("规则 %s 的运算符非法：%r" % (self.rule_id, self.op))
            if self.value is None:
                raise ValueError("规则 %s 缺限值" % self.rule_id)
        for key in self.applies_if:
            if key not in ("category", "life_stage"):
                raise ValueError("规则 %s 的 applies_if 键非法：%r" % (self.rule_id, key))

    @property
    def is_effective(self) -> bool:
        return self.status == STATUS_VERIFIED

    @property
    def limit(self) -> Optional[Decimal]:
        if self.value is None:
            return None
        try:
            return Decimal(self.value)
        except InvalidOperation:
            raise RuleError("规则 %s 的限值无法解析：%r" % (self.rule_id, self.value))

    def applies_to(self, category: Optional[str], life_stage: Optional[str]) -> bool:
        """``applies_if`` 适用性：未提供的输入不满足任何条件分支（宁可不判）。"""
        observed = {"category": category, "life_stage": life_stage}
        for key, allowed in self.applies_if.items():
            value = observed.get(key)
            if value is None:
                return False
            if value not in allowed:
                return False
        return True

    def compare(self, observed: Decimal) -> bool:
        if self.op is None or self.value is None:
            raise RuleError("规则 %s 缺 op/value，无法比较" % self.rule_id)
        func = _OPERATOR_FUNCS.get(self.op)
        if func is None:
            raise RuleError("规则 %s 的运算符 %r 不受支持" % (self.rule_id, self.op))
        return bool(func(observed, self.limit))


# ------------------------------------------------------------------ 档案
@dataclass
class Card:
    """标签档案（判定输入）。构造即校验——畸形输入挡在判定路径之外。"""

    category: Optional[str] = None
    life_stage: Optional[str] = None
    fields: Optional[Dict[str, str]] = None
    guaranteed: Optional[Dict[str, Tuple[Decimal, Optional[str]]]] = None
    claims: Tuple[str, ...] = ()

    def provided(self, name: str) -> bool:
        if name in ("category", "life_stage"):
            return bool(getattr(self, name))
        return name in (self.fields or {}) and bool((self.fields or {})[name])

    def field(self, name: str) -> Optional[str]:
        if name in ("category", "life_stage"):
            return getattr(self, name)
        return (self.fields or {}).get(name)

    def guaranteed_value(self, name: str) -> Optional[Decimal]:
        entry = (self.guaranteed or {}).get(name)
        return entry[0] if entry else None

    def guaranteed_unit(self, name: str) -> Optional[str]:
        entry = (self.guaranteed or {}).get(name)
        return entry[1] if entry else None

    @classmethod
    def from_subject(cls, data: Mapping) -> "Card":
        if not isinstance(data, Mapping):
            raise PackError("标签档案必须是 JSON 对象，得到 %s" % type(data).__name__)

        category = data.get("category")
        if category is not None and (not isinstance(category, str) or not category.strip()):
            raise PackError("category 必须是非空字符串或 null")
        life_stage = data.get("life_stage")
        if life_stage is not None and (not isinstance(life_stage, str) or not life_stage.strip()):
            raise PackError("life_stage 必须是非空字符串或 null")

        raw_fields = data.get("fields", {})
        if raw_fields is None:
            raw_fields = {}
        if not isinstance(raw_fields, Mapping):
            raise PackError("fields 必须是对象（字段名 → 值）")
        fields = {}
        for key, value in raw_fields.items():
            if key not in LABEL_FIELDS:
                raise PackError("fields 含未知字段：%r（合法：%s）"
                                % (key, "、".join(LABEL_FIELDS)))
            if not isinstance(value, str) or not value.strip():
                raise PackError("fields[%s] 必须是非空字符串" % key)
            fields[key] = value

        raw_guaranteed = data.get("guaranteed", {})
        if raw_guaranteed is None:
            raw_guaranteed = {}
        if not isinstance(raw_guaranteed, Mapping):
            raise PackError("guaranteed 必须是对象（指标 → {value, unit}）")
        guaranteed = {}
        for key, entry in raw_guaranteed.items():
            if isinstance(entry, Mapping):
                value = entry.get("value")
                unit = entry.get("unit")
            else:
                value, unit = entry, None
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise PackError("guaranteed[%s].value 必须是数值或数值字符串" % key)
            try:
                number = Decimal(str(value))
            except InvalidOperation:
                raise PackError("guaranteed[%s].value 无法解析为数值：%r" % (key, value))
            if unit is not None and not isinstance(unit, str):
                raise PackError("guaranteed[%s].unit 必须是字符串" % key)
            guaranteed[key] = (number, unit)

        raw_claims = data.get("claims", [])
        if raw_claims is None:
            raw_claims = []
        if not isinstance(raw_claims, list) or any(
                not isinstance(item, str) or not item.strip() for item in raw_claims):
            raise PackError("claims 必须是非空字符串数组")

        return cls(category=category, life_stage=life_stage, fields=fields,
                   guaranteed=guaranteed, claims=tuple(raw_claims))


# ------------------------------------------------------------------ 判定结果
@dataclass(frozen=True)
class RawFinding:
    """内部判定（尚未挂条款锚点）。"""

    rule: Rule
    verdict: str
    note: str
    observed: str
    expected: str


def support_present(card: Card, name: str) -> bool:
    return card.provided(name)


def to_dry_matter(observed: Decimal, card: Card) -> Optional[Decimal]:
    """把"按标示状态"的观测值换算到干物质基准（水分缺失/越界 → ``None``）。"""
    moisture = card.guaranteed_value(FIELD_MOISTURE)
    if moisture is None:
        return None
    if not (_ZERO < moisture < _HUNDRED):
        return None
    return observed / ((_HUNDRED - moisture) / _HUNDRED)


def judge_rule(rule: Rule, card: Card) -> RawFinding:
    """按 ``rule.kind`` 判定一条规则（五态，逐条对齐来源语义）。"""
    if rule.kind == KIND_PRESENCE:
        return _judge_presence(rule, card)
    if rule.kind == KIND_THRESHOLD:
        return _judge_threshold(rule, card)
    if rule.kind == KIND_CLAIM_SUPPORT:
        return _judge_claim_support(rule, card)
    raise RuleError("规则 %s 的 kind=%r 无判定实现" % (rule.rule_id, rule.kind))


def _judge_presence(rule: Rule, card: Card) -> RawFinding:
    if rule.target not in LABEL_FIELDS and rule.target not in ("category", "life_stage"):
        return RawFinding(rule, VERDICT_UNKNOWN,
                          "规则目标不在标签档案字段集内：%r" % rule.target, "-", "已标示")
    if card.provided(rule.target):
        return RawFinding(rule, VERDICT_COMPLIANT, "", card.field(rule.target), "已标示")
    if rule.effect == EFFECT_CONDITIONAL:
        return RawFinding(rule, VERDICT_UNKNOWN, REASON_NOT_FOUND, "未提供(%s)" % REASON_NOT_FOUND,
                          "条件触发，需人工确认")
    return RawFinding(rule, VERDICT_NONCOMPLIANT, REASON_NOT_FOUND,
                      "未提供(%s)" % REASON_NOT_FOUND, "应当标示")


def _judge_threshold(rule: Rule, card: Card) -> RawFinding:
    observed = card.guaranteed_value(rule.target)
    expected = "%s %s" % (rule.op, rule.value)
    if rule.unit:
        expected = "%s %s" % (expected, rule.unit)
    if observed is None:
        return RawFinding(rule, VERDICT_NOT_PROVIDED, REASON_NOT_FOUND, "未提供", expected)

    compare_value = observed
    note = ""
    if rule.basis == BASIS_DRY_MATTER:
        converted = to_dry_matter(observed, card)
        if converted is None:
            return RawFinding(rule, VERDICT_UNKNOWN, REASON_BASIS_UNDETERMINED,
                              str(observed), expected)
        compare_value = converted
        moisture = card.guaranteed_value(FIELD_MOISTURE)
        note = "标示值 %s 换算为干基 %s（水分 %s%%）" % (observed, converted, moisture)

    ok = rule.compare(compare_value)
    return RawFinding(rule, VERDICT_COMPLIANT if ok else VERDICT_NONCOMPLIANT,
                      note, str(observed), expected)


def _judge_claim_support(rule: Rule, card: Card) -> RawFinding:
    if rule.target not in card.claims:
        return RawFinding(rule, VERDICT_SKIPPED, "", "未宣称", "未宣称时不适用")
    missing = [name for name in rule.required_support if not support_present(card, name)]
    expected = "需齐备：" + "、".join(rule.required_support)
    if missing:
        return RawFinding(rule, VERDICT_NONCOMPLIANT, "缺少：" + "、".join(missing),
                          "已宣称但支撑信息不齐备", expected)
    return RawFinding(rule, VERDICT_COMPLIANT, "", "已宣称且支撑信息齐备", expected)


def judge_dimension(rules: Sequence[Rule], dimension: str,
                    card: Card) -> Tuple[RawFinding, ...]:
    """对一个维度跑全部生效规则（``applies_if`` 未命中的不参与）。"""
    effective = [rule for rule in rules
                 if rule.is_effective and rule.dimension == dimension]
    applicable = [rule for rule in effective
                  if rule.applies_to(card.category, card.life_stage)]
    return tuple(judge_rule(rule, card) for rule in applicable)


def dimension_assessed(rules: Sequence[Rule], dimension: str, card: Card) -> bool:
    """该维度是否有**任一条适用**的生效规则（否则"未评估"）。"""
    effective = [rule for rule in rules
                 if rule.is_effective and rule.dimension == dimension]
    return any(rule.applies_to(card.category, card.life_stage) for rule in effective)


__all__ = [
    "KIND_PRESENCE", "KIND_THRESHOLD", "KIND_CLAIM_SUPPORT", "KINDS", "OPERATORS",
    "EFFECT_OBLIGATION", "EFFECT_CONDITIONAL", "EFFECTS",
    "BASIS_AS_FED", "BASIS_DRY_MATTER", "BASES",
    "VERDICT_COMPLIANT", "VERDICT_NONCOMPLIANT", "VERDICT_NOT_PROVIDED",
    "VERDICT_SKIPPED", "VERDICT_UNKNOWN", "VERDICTS",
    "STATUS_VERIFIED", "STATUS_PENDING",
    "FIELD_MOISTURE", "LABEL_FIELDS", "REASON_NOT_FOUND", "REASON_BASIS_UNDETERMINED",
    "DIM_LABEL", "DIM_NUTRITION", "DIM_CLAIM", "DIMENSIONS",
    "PackError", "RuleError", "Rule", "Card", "RawFinding",
    "support_present", "to_dry_matter", "judge_rule", "judge_dimension",
    "dimension_assessed",
]