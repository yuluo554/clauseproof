"""规则包数据模型（迁自来源 ``rules.model``；仅标准库 + dataclass）。

四态判定与门槛判定的**业务语义一律来自规则包数据**（本模块只承载词汇表，
不含任何条款/门槛内容）：``auto_mapping`` 的取值→状态映射、``effect`` 的
义务分栏，均由规则包声明，引擎按声明求值（来源 NFR-5：引擎零门槛字面量）。
"""

from dataclasses import dataclass, field
from typing import List, Optional

STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"

# 检查项核查方式
METHOD_AUTO = "auto"
METHOD_MANUAL = "manual"

# 单项判定状态
STATE_COMPLIANT = "compliant"
STATE_PARTIAL = "partial"
STATE_NONCOMPLIANT = "noncompliant"
STATE_NOT_APPLICABLE = "not_applicable"
STATE_UNKNOWN = "unknown"

# 汇总状态
SUMMARY_COMPLIANT = "compliant"
SUMMARY_PARTIAL = "partial"
SUMMARY_NONCOMPLIANT = "noncompliant"
SUMMARY_NOT_ASSESSED = "not_assessed"

# 适用项集合（进分母的状态；不适用/未观测不进分母）
APPLICABLE_STATES = (STATE_COMPLIANT, STATE_PARTIAL, STATE_NONCOMPLIANT)

# 单项全部合法状态
ALL_STATES = APPLICABLE_STATES + (STATE_NOT_APPLICABLE, STATE_UNKNOWN)

# 门槛义务类型（effect）
EFFECT_PERIODIC_OBLIGATION = "periodic_obligation"
EFFECT_STANDING_OBLIGATION = "standing_obligation"
EFFECT_CONDITIONAL_INSTITUTION = "conditional_institution"
EFFECTS = (
    EFFECT_PERIODIC_OBLIGATION,
    EFFECT_STANDING_OBLIGATION,
    EFFECT_CONDITIONAL_INSTITUTION,
)

# auto_mapping 匹配词表（结构性词，非政策字面量）
MATCH_EQUALS = "equals"
MATCH_ONE_OF = "one_of"
MATCH_EMPTY = "empty"
MATCH_NONEMPTY = "nonempty"


@dataclass(frozen=True)
class Source:
    """条目出处：``channel`` 与 ``checked_at`` 必填，``url`` 可空。

    标准全文公开页需登录，故 url 允许为空；但"已核对"必须可追溯到渠道与核对日。
    """

    channel: str = ""
    url: str = ""
    checked_at: str = ""

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            channel=data.get("channel", ""),
            url=data.get("url", ""),
            checked_at=data.get("checked_at", ""),
        )

    def is_attributed(self):
        return bool(self.channel and self.checked_at)


@dataclass(frozen=True)
class Clause:
    """条目挂的条款坐标（依据文件 + 条号 + 要点）。"""

    basis: str
    article: str
    point: str = ""

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            basis=data.get("basis", ""),
            article=data.get("article", ""),
            point=data.get("point", ""),
        )

    def label(self):
        return "%s %s" % (self.basis, self.article)


@dataclass(frozen=True)
class BasisDoc:
    """依据文件本身（名称 / 施行日 / 核对状态 / 出处）。"""

    code: str
    title: str
    effective_date: Optional[str] = None
    status: str = STATUS_PENDING
    source: Source = field(default_factory=Source)

    @classmethod
    def from_dict(cls, data):
        return cls(
            code=data.get("code", ""),
            title=data.get("title", ""),
            effective_date=data.get("effective_date"),
            status=data.get("status", STATUS_PENDING),
            source=Source.from_dict(data.get("source")),
        )


@dataclass(frozen=True)
class AutoMapping:
    """auto 项的「取值 → 四态」映射（按序取首个命中，末条 default 兜底）。

    规则表为空时引擎退化为来源旧口径（非空 → ``compliant`` / 否则
    ``noncompliant``），以兼容未细化的规则包（示例包）。
    """

    rules: List[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data):
        if not data:
            return cls(rules=[])
        if isinstance(data, list):
            return cls(rules=list(data))
        return cls(rules=list(data.get("rules", [])))

    def is_empty(self):
        return not self.rules

    def match(self, value):
        for rule in self.rules:
            if _match_rule(rule.get("match", {}), value):
                return rule.get("state")
        return None

    def to_dict(self):
        return {"rules": [dict(rule) for rule in self.rules]}


def _is_empty_value(value):
    return value is None or value is False or (
        isinstance(value, str) and not value.strip()
    )


def _match_rule(match, value):
    if match.get("default"):
        return True
    if MATCH_EMPTY in match:
        if bool(match[MATCH_EMPTY]) != _is_empty_value(value):
            return False
    if MATCH_NONEMPTY in match:
        if bool(match[MATCH_NONEMPTY]) == _is_empty_value(value):
            return False
    if MATCH_EQUALS in match and value != match[MATCH_EQUALS]:
        return False
    if MATCH_ONE_OF in match and value not in match[MATCH_ONE_OF]:
        return False
    return True


@dataclass(frozen=True)
class Threshold:
    """一条审计义务门槛（参数 × 运算符 × 阈值 → 结论 + 义务类型）。"""

    id: str
    param: str
    op: str
    value: int
    conclusion: str
    frequency: str
    clause: Clause
    status: str
    severity: int = 0
    effect: str = EFFECT_STANDING_OBLIGATION
    source: Source = field(default_factory=Source)

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data["id"],
            param=data["param"],
            op=data["op"],
            value=data["value"],
            conclusion=data["conclusion"],
            frequency=data.get("frequency", ""),
            clause=Clause.from_dict(data.get("clause")),
            status=data.get("status", STATUS_PENDING),
            severity=data.get("severity", 0),
            effect=data.get("effect", EFFECT_STANDING_OBLIGATION),
            source=Source.from_dict(data.get("source")),
        )

    def is_conditional(self):
        """条件触发：保护部门"可以要求"，非处理者的无条件义务。"""
        return self.effect == EFFECT_CONDITIONAL_INSTITUTION


@dataclass(frozen=True)
class CheckItem:
    """一条审计检查项（27 项审查要点骨架中的一项）。"""

    id: str
    category: str
    title: str
    clause: Clause
    method: str
    criteria: str = ""
    auto_field: Optional[str] = None
    auto_mapping: AutoMapping = field(default_factory=AutoMapping)
    evidence_required: bool = True
    only_if: Optional[dict] = None
    status: str = STATUS_PENDING
    source: Source = field(default_factory=Source)

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data["id"],
            category=data.get("category", ""),
            title=data.get("title", ""),
            clause=Clause.from_dict(data.get("clause")),
            method=data.get("method", METHOD_MANUAL),
            criteria=data.get("criteria", ""),
            auto_field=data.get("auto_field"),
            auto_mapping=AutoMapping.from_dict(data.get("auto_mapping")),
            evidence_required=data.get("evidence_required", True),
            only_if=data.get("only_if"),
            status=data.get("status", STATUS_PENDING),
            source=Source.from_dict(data.get("source")),
        )


@dataclass(frozen=True)
class Ruleset:
    """一份规则包：依据文件 × 版本（门槛 + 检查单）。"""

    schema_version: str
    ruleset_id: str
    version: str
    generated_at: str
    basis: List[BasisDoc]
    thresholds: List[Threshold]
    checklist: List[CheckItem]
    path: Optional[str] = None

    @classmethod
    def from_dict(cls, data, path=None):
        return cls(
            schema_version=data.get("schema_version", ""),
            ruleset_id=data.get("ruleset_id", ""),
            version=data.get("version", ""),
            generated_at=data.get("generated_at", ""),
            basis=[BasisDoc.from_dict(item) for item in data.get("basis", [])],
            thresholds=[Threshold.from_dict(item) for item in data.get("thresholds", [])],
            checklist=[CheckItem.from_dict(item) for item in data.get("checklist", [])],
            path=str(path) if path else None,
        )

    def pending_entries(self):
        """列出 ``status != verified`` 的条目（门槛 + 检查项 + 依据文件）。"""
        out = []
        for basis in self.basis:
            if basis.status != STATUS_VERIFIED:
                out.append("basis:%s" % basis.code)
        for threshold in self.thresholds:
            if threshold.status != STATUS_VERIFIED:
                out.append("threshold:%s" % threshold.id)
        for item in self.checklist:
            if item.status != STATUS_VERIFIED:
                out.append("checklist:%s" % item.id)
        return out

    def unattributed_entries(self):
        """列出 ``status=verified`` 但缺出处的条目（"已核对"必须可追溯）。"""
        out = []
        for basis in self.basis:
            if basis.status == STATUS_VERIFIED and not basis.source.is_attributed():
                out.append("basis:%s" % basis.code)
        for threshold in self.thresholds:
            if threshold.status == STATUS_VERIFIED and not threshold.source.is_attributed():
                out.append("threshold:%s" % threshold.id)
        for item in self.checklist:
            if item.status == STATUS_VERIFIED and not item.source.is_attributed():
                out.append("checklist:%s" % item.id)
        return out


__all__ = [
    "STATUS_VERIFIED", "STATUS_PENDING",
    "METHOD_AUTO", "METHOD_MANUAL",
    "STATE_COMPLIANT", "STATE_PARTIAL", "STATE_NONCOMPLIANT",
    "STATE_NOT_APPLICABLE", "STATE_UNKNOWN",
    "SUMMARY_COMPLIANT", "SUMMARY_PARTIAL", "SUMMARY_NONCOMPLIANT",
    "SUMMARY_NOT_ASSESSED",
    "APPLICABLE_STATES", "ALL_STATES",
    "EFFECT_PERIODIC_OBLIGATION", "EFFECT_STANDING_OBLIGATION",
    "EFFECT_CONDITIONAL_INSTITUTION", "EFFECTS",
    "MATCH_EQUALS", "MATCH_ONE_OF", "MATCH_EMPTY", "MATCH_NONEMPTY",
    "Source", "Clause", "BasisDoc", "AutoMapping", "Threshold", "CheckItem",
    "Ruleset",
]