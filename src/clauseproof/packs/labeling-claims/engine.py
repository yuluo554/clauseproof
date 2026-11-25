"""AI 生成合成内容标识判定内核（**零 I/O / 零时钟 / 零环境变量**）。

本模块是来源产品 ``labelcheck`` 判定语义的**逐条移植**，只保留"输入 → 判定"
这一段；规则库/映射表的承载在 :mod:`rulebook`，条款依据的承载在条文库
（``Basis``），本模块一律不碰。

移植纪律（与来源产品 plan/04 §一.3 同源）：

- ``presence`` 缺值判 ``fail``；其余 check_type 缺值判 ``unknown``（**不臆测合规**）；
- ``present=true`` 但缺 ``position`` → ``unknown``（位置约束无法核验）；
- 适用场景未命中 → ``skipped``（**不是 fail**：把"不适用"判成违规是冤枉用户）；
- 作用域未被观测 → 该 scope 全部 ``unknown``（解析通路看不到渲染后的画面文字）；
- ``unique`` 以**整块隐式标识**为上下文（同一要素被多键提供 = 重复保留）。
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------- 枚举（既定口径）
CARRIERS = ("text", "image", "audio", "video")
SOURCES = ("synthetic", "manual", "parsed")
SCENARIO_AUTHORED = "authored"
SCENARIO_EXPORTED = "exported"
SCENARIO_PROPAGATED = "propagated"
SCENARIOS = (SCENARIO_AUTHORED, SCENARIO_EXPORTED, SCENARIO_PROPAGATED)
OBSERVED_EXPLICIT = "explicit"
OBSERVED_IMPLICIT = "implicit"
OBSERVED_KEYS = (OBSERVED_EXPLICIT, OBSERVED_IMPLICIT)

SCOPE_EXPLICIT = "explicit"
SCOPE_IMPLICIT = "implicit"
SCOPES = (SCOPE_EXPLICIT, SCOPE_IMPLICIT)

#: 判定状态（内部态；向外映射见 ``pack.__init__`` 的 verdict 映射表）
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_UNKNOWN = "unknown"
STATUS_SKIPPED = "skipped"
STATUSES = (STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN, STATUS_SKIPPED)

#: 核对状态：**只有 verified 能进判定路径**（来源产品 NFR-4）
STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"

CHECK_TYPES = ("presence", "position", "enum", "pattern", "type", "range", "unique")
SEVERITIES = ("critical", "major", "minor")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CheckError(ValueError):
    """输入不合法（标识卡结构缺陷）。内核映射退出码 2。"""


# ---------------------------------------------------------------- 规则条目
@dataclass(frozen=True)
class Rule:
    """一条冻结核查规则（字段名与来源产品规则库 JSON 一一对应）。"""

    rule_id: str
    scope: str
    carrier: Tuple[str, ...]
    target: str
    check_type: str
    params: Mapping[str, Any]
    severity: str
    scenarios: Tuple[str, ...]
    clause_id: str
    status: str

    def __post_init__(self) -> None:
        if self.scope not in SCOPES:
            raise ValueError("规则 %s 的 scope 非法：%r" % (self.rule_id, self.scope))
        if self.check_type not in CHECK_TYPES:
            raise ValueError("规则 %s 的 check_type 非法：%r" % (self.rule_id, self.check_type))
        if self.severity not in SEVERITIES:
            raise ValueError("规则 %s 的 severity 非法：%r" % (self.rule_id, self.severity))
        for scenario in self.scenarios:
            if scenario not in SCENARIOS:
                raise ValueError("规则 %s 的场景非法：%r" % (self.rule_id, scenario))
        if self.check_type == "unique" and self.scope != SCOPE_IMPLICIT:
            raise ValueError("规则 %s：unique 只能用于 implicit scope" % self.rule_id)

    @property
    def is_effective(self) -> bool:
        """是否已核对通过（可进判定路径）。"""
        return self.status == STATUS_VERIFIED

    def applies_to_carrier(self, carrier: str) -> bool:
        """载体门控：空列表 = 全部载体适用。"""
        return not self.carrier or carrier in self.carrier

    def applies_to_scenario(self, scenario: str) -> bool:
        """场景门控：空列表 = 全部场景适用。"""
        return not self.scenarios or scenario in self.scenarios


@dataclass(frozen=True)
class FieldMapping:
    """一个国标字段的映射定义（``aliases`` 声明序敏感）。"""

    national_field: str
    aliases: Tuple[str, ...] = ()

    @property
    def keys(self) -> Tuple[str, ...]:
        return (self.national_field,) + tuple(self.aliases)


@dataclass(frozen=True)
class Resolution:
    """一个国标字段的归一结果。"""

    national_field: str
    value: Any = None
    matched_key: Optional[str] = None
    alternatives: Tuple[str, ...] = ()

    @property
    def found(self) -> bool:
        return self.matched_key is not None

    @property
    def all_matched_keys(self) -> Tuple[str, ...]:
        if self.matched_key is None:
            return ()
        return (self.matched_key,) + tuple(self.alternatives)


# ---------------------------------------------------------------- 标识卡
@dataclass
class Card:
    """标识卡（判定输入）。构造即校验——畸形输入挡在判定路径之外。"""

    card_id: str
    carrier: str
    content_sha256: str
    explicit: List[Dict[str, Any]] = field(default_factory=list)
    implicit: Dict[str, Any] = field(default_factory=dict)
    source: str = "manual"
    notes: str = ""
    scenario: str = SCENARIO_AUTHORED
    observed: Dict[str, bool] = field(
        default_factory=lambda: {OBSERVED_EXPLICIT: True, OBSERVED_IMPLICIT: True})
    implicit_duplicate_keys: Tuple[str, ...] = ()

    @classmethod
    def from_subject(cls, data: Mapping) -> "Card":
        """从判定输入构造并校验；不合法抛 :class:`CheckError`（退出码 2）。"""
        if not isinstance(data, Mapping):
            raise CheckError("标识卡必须是 JSON 对象，得到 %s" % type(data).__name__)

        card_id = data.get("card_id")
        if not isinstance(card_id, str) or not card_id.strip():
            raise CheckError("标识卡缺少合法 card_id（须为非空字符串）")

        carrier = data.get("carrier")
        if carrier not in CARRIERS:
            raise CheckError(
                "标识卡 %s 的 carrier 非法：%r（须为 %s 之一）"
                % (card_id, carrier, "/".join(CARRIERS))
            )

        content_sha256 = data.get("content_sha256")
        if not isinstance(content_sha256, str) or not _SHA256_RE.match(content_sha256):
            raise CheckError(
                "标识卡 %s 的 content_sha256 缺失或不合法（须为 64 位小写 hex）" % card_id
            )

        source = data.get("source", "manual")
        if source not in SOURCES:
            raise CheckError(
                "标识卡 %s 的 source 非法：%r（须为 %s 之一）"
                % (card_id, source, "/".join(SOURCES))
            )

        scenario = data.get("scenario", SCENARIO_AUTHORED)
        if scenario not in SCENARIOS:
            raise CheckError(
                "标识卡 %s 的 scenario 非法：%r（须为 %s 之一）"
                % (card_id, scenario, "/".join(SCENARIOS))
            )

        observed = _normalize_observed(card_id, data.get("observed"))

        explicit = data.get("explicit", [])
        if not isinstance(explicit, list):
            raise CheckError("标识卡 %s 的 explicit 必须是数组" % card_id)
        for index, item in enumerate(explicit):
            if not isinstance(item, dict):
                raise CheckError("标识卡 %s 的 explicit[%d] 必须是对象" % (card_id, index))
            if not isinstance(item.get("element"), str) or not item["element"]:
                raise CheckError("标识卡 %s 的 explicit[%d] 缺少合法 element" % (card_id, index))

        implicit = data.get("implicit", {})
        if not isinstance(implicit, dict):
            raise CheckError("标识卡 %s 的 implicit 必须是对象" % card_id)

        duplicate_keys = data.get("implicit_duplicate_keys", [])
        if duplicate_keys is None:
            duplicate_keys = []
        if not isinstance(duplicate_keys, list) or any(
                not isinstance(key, str) or not key for key in duplicate_keys):
            raise CheckError(
                "标识卡 %s 的 implicit_duplicate_keys 必须是非空字符串数组" % card_id)

        notes = data.get("notes", "")
        if notes is None:
            notes = ""
        if not isinstance(notes, str):
            raise CheckError("标识卡 %s 的 notes 必须是字符串" % card_id)

        return cls(
            card_id=card_id,
            carrier=carrier,
            content_sha256=content_sha256,
            explicit=[dict(item) for item in explicit],
            implicit=dict(implicit),
            source=source,
            notes=notes,
            scenario=scenario,
            observed=observed,
            implicit_duplicate_keys=tuple(duplicate_keys),
        )

    def observes(self, scope: str) -> bool:
        return bool(self.observed.get(scope, True))

    def find_explicit(self, element_id: str) -> Optional[Dict[str, Any]]:
        for item in self.explicit:
            if item.get("element") == element_id:
                return item
        return None


def _normalize_observed(card_id: str, observed: Optional[Mapping]) -> Dict[str, bool]:
    result = {OBSERVED_EXPLICIT: True, OBSERVED_IMPLICIT: True}
    if observed is None:
        return result
    if not isinstance(observed, Mapping):
        raise CheckError("标识卡 %s 的 observed 必须是对象（scope → bool）" % card_id)
    for key in observed:
        if key not in OBSERVED_KEYS:
            raise CheckError(
                "标识卡 %s 的 observed 含未知 scope：%r（须为 %s）"
                % (card_id, key, "/".join(OBSERVED_KEYS)))
    for key, value in observed.items():
        if not isinstance(value, bool):
            raise CheckError("标识卡 %s 的 observed[%s] 必须是布尔值" % (card_id, key))
        result[key] = value
    return result


# ---------------------------------------------------------------- 判定结果
@dataclass(frozen=True)
class RawFinding:
    """内部判定（尚未挂条款锚点）。对外映射由 pack 完成。"""

    rule: Rule
    status: str
    code: str
    message: str
    evidence: Mapping[str, Any]
    scenario: str


# ---------------------------------------------------------------- 归一
def resolve_fields(implicit: Mapping[str, Any],
                   fields: Sequence[FieldMapping]) -> Dict[str, Resolution]:
    """把卡片 ``implicit`` 归一为国标字段（键序 = 映射表声明序，确定性）。"""
    results = {}
    for mapping in fields:
        matched_key = None
        alternatives = []
        for key in mapping.keys:
            if key in implicit:
                if matched_key is None:
                    matched_key = key
                else:
                    alternatives.append(key)
        value = implicit.get(matched_key) if matched_key is not None else None
        results[mapping.national_field] = Resolution(
            national_field=mapping.national_field,
            value=value,
            matched_key=matched_key,
            alternatives=tuple(alternatives),
        )
    return results


# ---------------------------------------------------------------- check_type
def evaluate_check(rule: Rule, observed: Any) -> Tuple[str, str, str, Dict[str, Any]]:
    """按 ``rule.check_type`` 判定观测值，返回 ``(status, code, message, evidence)``。

    ``unique`` 需要整块上下文，必须由 :func:`check_implicit` 直接判定——这里显式拒绝，
    避免调用方误用（与来源产品同一纪律）。
    """
    check_type = rule.check_type
    params = rule.params

    if check_type == "unique":
        raise ValueError(
            "check_type=unique 需整块上下文，须由 check_implicit 判定（规则 %s）"
            % rule.rule_id)

    if check_type == "presence":
        if observed is None or observed == "":
            return (STATUS_FAIL,
                    "element_absent" if rule.scope == SCOPE_EXPLICIT else "field_absent",
                    "必需项缺失", {"observed": None})
        return (STATUS_PASS, "", "存在且非空", {"observed": observed})

    if observed is None:
        code = ("element_absent_cannot_verify" if rule.scope == SCOPE_EXPLICIT
                else "field_absent_cannot_verify")
        return (STATUS_UNKNOWN, code, "缺值，无法核验该项约束", {"observed": None})

    if check_type == "position":
        allowed = list(params.get("allowed", []))
        if observed in allowed:
            return (STATUS_PASS, "", "位置在允许集内",
                    {"observed": observed, "expected": allowed})
        return (STATUS_FAIL, "position_not_allowed", "位置不在允许集内",
                {"observed": observed, "expected": allowed})

    if check_type == "enum":
        allowed = list(params.get("allowed", []))
        if observed in allowed:
            return (STATUS_PASS, "", "取值在枚举内",
                    {"observed": observed, "expected": allowed})
        return (STATUS_FAIL, "value_not_allowed", "取值不在枚举内",
                {"observed": observed, "expected": allowed})

    if check_type == "pattern":
        pattern = params.get("regex", "")
        text = observed if isinstance(observed, str) else str(observed)
        try:
            matched = re.fullmatch(pattern, text) is not None
        except re.error as exc:
            raise ValueError("规则 %s 的 regex 非法：%s（%s）" % (rule.rule_id, pattern, exc))
        if matched:
            return (STATUS_PASS, "", "格式匹配", {"observed": text, "expected": pattern})
        return (STATUS_FAIL, "format_mismatch", "格式不匹配",
                {"observed": text, "expected": pattern})

    if check_type == "type":
        expect = params.get("expect", "string")
        if _type_matches(observed, expect):
            return (STATUS_PASS, "", "类型匹配",
                    {"observed": type(observed).__name__, "expected": expect})
        return (STATUS_FAIL, "type_mismatch", "类型不匹配",
                {"observed": type(observed).__name__, "expected": expect})

    if check_type == "range":
        return _evaluate_range(rule, observed)

    raise ValueError("未知 check_type：%r（规则 %s）" % (check_type, rule.rule_id))


def _type_matches(value: Any, expect: str) -> bool:
    if expect == "string":
        return isinstance(value, str)
    if expect == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if expect == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expect == "bool":
        return isinstance(value, bool)
    if expect == "list":
        return isinstance(value, list)
    if expect == "object":
        return isinstance(value, dict)
    raise ValueError("未知 type 期望：%r" % expect)


def _evaluate_range(rule: Rule, observed: Any) -> Tuple[str, str, str, Dict[str, Any]]:
    params = rule.params
    try:
        value = float(observed)
    except (TypeError, ValueError):
        return (STATUS_FAIL, "type_mismatch", "取值范围检查要求数值", {"observed": observed})
    low = params.get("min", None)
    high = params.get("max", None)
    ok = True
    if low is not None and value < low:
        ok = False
    if high is not None and value > high:
        ok = False
    expected = {"min": low, "max": high}
    if ok:
        return (STATUS_PASS, "", "取值在范围内", {"observed": value, "expected": expected})
    return (STATUS_FAIL, "value_out_of_range", "取值超出范围",
            {"observed": value, "expected": expected})


# ---------------------------------------------------------------- 规则筛选
def rules_for(rules: Sequence[Rule], scope: str, carrier: str,
              scenario: str) -> Tuple[List[Rule], List[Rule]]:
    """取 ``scope × 载体`` 下的生效规则，按场景分为 ``(适用, 不适用)``。"""
    applicable, skipped = [], []
    for rule in rules:
        if not rule.is_effective or rule.scope != scope:
            continue
        if not rule.applies_to_carrier(carrier):
            continue
        if rule.applies_to_scenario(scenario):
            applicable.append(rule)
        else:
            skipped.append(rule)
    return applicable, skipped


# ---------------------------------------------------------------- 显式标识
def check_explicit(card: Card, rules: Sequence[Rule]) -> List[RawFinding]:
    """逐条核验显式要素（返回顺序 = 规则表声明序）。"""
    applicable, skipped = rules_for(rules, SCOPE_EXPLICIT, card.carrier, card.scenario)

    findings = []
    for rule in skipped:
        findings.append(RawFinding(
            rule, STATUS_SKIPPED, "scenario_not_applicable",
            "场景不适用（本条仅适用于 %s）：%s"
            % ("/".join(rule.scenarios), card.scenario),
            {"scenario": card.scenario, "applies_to": list(rule.scenarios)},
            card.scenario,
        ))

    observed = card.observes(OBSERVED_EXPLICIT)
    for rule in applicable:
        if not observed:
            findings.append(RawFinding(
                rule, STATUS_UNKNOWN, "explicit_not_observed",
                "显式标识作用域未被观测（解析通路无法读取渲染后的文字/语音），不臆测合规性",
                {"observed": False}, card.scenario))
            continue

        element = card.find_explicit(rule.target)
        if element is None:
            if rule.check_type == "presence":
                findings.append(RawFinding(
                    rule, STATUS_FAIL, "element_absent",
                    "显式标识要素缺失：%s" % rule.target,
                    {"observed": None}, card.scenario))
            else:
                findings.append(RawFinding(
                    rule, STATUS_UNKNOWN, "element_absent_cannot_verify",
                    "显式要素缺失，无法核验其%s约束" % rule.check_type,
                    {"observed": None}, card.scenario))
            continue

        present = element.get("present")
        if present is False:
            findings.append(RawFinding(
                rule, STATUS_FAIL, "element_not_present",
                "显式标识要素声明为不存在：%s" % rule.target,
                {"observed": False}, card.scenario))
            continue
        if present is not True:
            findings.append(RawFinding(
                rule, STATUS_UNKNOWN, "element_presence_unknown",
                "显式要素未声明 present，无法判定是否具备标识：%s" % rule.target,
                {"observed": present}, card.scenario))
            continue

        if rule.check_type == "presence":
            findings.append(RawFinding(
                rule, STATUS_PASS, "", "显式标识要素存在",
                {"observed": True}, card.scenario))
        elif rule.check_type == "position":
            observed_position = element.get("position")
            if observed_position is None:
                findings.append(RawFinding(
                    rule, STATUS_UNKNOWN, "position_unknown",
                    "要素存在但未记录位置，无法核验位置约束：%s" % rule.target,
                    {"observed": None, "expected": list(rule.params.get("allowed", []))},
                    card.scenario))
            else:
                status, code, message, evidence = evaluate_check(rule, observed_position)
                findings.append(RawFinding(
                    rule, status, code, message, evidence, card.scenario))
        else:
            observed_value = element.get("value")
            status, code, message, evidence = evaluate_check(rule, observed_value)
            findings.append(RawFinding(rule, status, code, message, evidence, card.scenario))

    return findings


# ---------------------------------------------------------------- 隐式标识
def check_implicit(card: Card, rules: Sequence[Rule],
                   fields: Sequence[FieldMapping]) -> List[RawFinding]:
    """逐条核验隐式字段（映射归一 + check_type 分派 + unique 上下文判定）。"""
    resolutions = resolve_fields(card.implicit, fields)
    applicable, skipped = rules_for(rules, SCOPE_IMPLICIT, card.carrier, card.scenario)

    findings = []
    for rule in skipped:
        findings.append(RawFinding(
            rule, STATUS_SKIPPED, "scenario_not_applicable",
            "场景不适用（本条仅适用于 %s）：%s"
            % ("/".join(rule.scenarios), card.scenario),
            {"scenario": card.scenario, "applies_to": list(rule.scenarios)},
            card.scenario,
        ))

    observed = card.observes(OBSERVED_IMPLICIT)
    for rule in applicable:
        if not observed:
            findings.append(RawFinding(
                rule, STATUS_UNKNOWN, "implicit_not_observed",
                "隐式标识作用域未被观测（无元数据来源），不臆测合规性",
                {"observed": False}, card.scenario))
            continue

        if rule.check_type == "unique":
            findings.append(_check_unique(rule, resolutions, card))
            continue

        resolution = resolutions.get(rule.target)
        if resolution is None:
            findings.append(RawFinding(
                rule, STATUS_UNKNOWN, "field_not_in_mapping",
                "规则引用的国标字段不在映射表中：%s" % rule.target,
                {"observed": None}, card.scenario))
            continue

        evidence = {"observed_key": resolution.matched_key}
        if resolution.alternatives:
            evidence["alternatives"] = list(resolution.alternatives)

        if not resolution.found:
            if rule.check_type == "presence":
                findings.append(RawFinding(
                    rule, STATUS_FAIL, "field_absent",
                    "隐式标识字段缺失：%s" % rule.target, evidence, card.scenario))
            else:
                findings.append(RawFinding(
                    rule, STATUS_UNKNOWN, "field_absent_cannot_verify",
                    "隐式字段缺失，无法核验其%s约束：%s" % (rule.check_type, rule.target),
                    evidence, card.scenario))
            continue

        status, code, message, extra = evaluate_check(rule, resolution.value)
        evidence.update(extra)
        findings.append(RawFinding(rule, status, code, message, evidence, card.scenario))

    return findings


def _check_unique(rule: Rule, resolutions: Mapping[str, Resolution],
                  card: Card) -> RawFinding:
    """判定"文件元数据隐式标识是否被重复保留"（GB 45438-2025 §6.1 c)）。"""
    duplicated = []
    for national_field, resolution in resolutions.items():
        keys = resolution.all_matched_keys
        repeated = [key for key in card.implicit_duplicate_keys if key in keys]
        if len(keys) + len(repeated) > 1:
            duplicated.append({
                "national_field": national_field,
                "keys": list(keys),
                "repeated_keys": repeated,
            })

    observed_keys = []
    for resolution in resolutions.values():
        observed_keys.extend(resolution.all_matched_keys)
    evidence = {"observed_keys": observed_keys, "duplicated": duplicated}

    if not observed_keys:
        return RawFinding(
            rule, STATUS_UNKNOWN, "field_absent_cannot_verify",
            "未观测到任何隐式标识要素，无法核验唯一性约束", evidence, card.scenario)
    if not duplicated:
        return RawFinding(
            rule, STATUS_PASS, "", "文件元数据隐式标识仅保留一份", evidence, card.scenario)
    return RawFinding(
        rule, STATUS_FAIL, "duplicate_implicit_label",
        "文件元数据隐式标识被重复保留（%d 个要素存在多份）：同一标识应仅保留一份"
        % len(duplicated),
        evidence, card.scenario)


__all__ = [
    "CARRIERS", "SOURCES", "SCENARIOS", "OBSERVED_KEYS", "SCOPES", "STATUSES",
    "SCOPE_EXPLICIT", "SCOPE_IMPLICIT",
    "SCENARIO_AUTHORED", "SCENARIO_EXPORTED", "SCENARIO_PROPAGATED",
    "OBSERVED_EXPLICIT", "OBSERVED_IMPLICIT",
    "STATUS_PASS", "STATUS_FAIL", "STATUS_UNKNOWN", "STATUS_SKIPPED",
    "STATUS_VERIFIED", "STATUS_PENDING", "CHECK_TYPES", "SEVERITIES",
    "CheckError", "Rule", "FieldMapping", "Resolution", "Card", "RawFinding",
    "resolve_fields", "evaluate_check", "rules_for", "check_explicit", "check_implicit",
]