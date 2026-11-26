"""限值矩阵判定内核（**零 I/O / 零时钟 / 零环境变量 / 零限值数值字面量**）。

迁移的是来源产品的「三维限值矩阵」判定面（规则包校验与 status 门控 →
applies_if 三值逻辑 → 单位归一与比较 → 参数 × 限值四态判定 → 跨标准统一结论），
只保留「规则包 dict + 参数表 → 判定」这一段：

- **四态**：``compliant`` / ``non_compliant`` / ``not_applicable`` / ``not_provided``；
  硬约束是「未提供参数绝不判为符合」——一条规则都不适用时整体记
  ``not_assessed``，绝不输出 ``compliant``；
- **status 门控**：``status != verified`` 的条目**零参与核查路径**，只进
  ``excluded`` 集合并显式列出；``pending`` 条目 ``value`` 必须为 null
  （待核对不许预填数值）；``clause_status=pending`` 时 ``clause`` 必须为 null
  （绝不编造条款号）；
- **applies_if 三值逻辑**：白名单小语言（param/op/value、all、any、not，不用
  eval）；引用参数未提供或不可解析 → unknown → ``not_provided(condition_unknown)``
  （「不知道是否适用」≠「不适用」）；
- **单位归一**：换算系数表（数学常量）+ 单位别名表（数据侧来源）；可显式无损
  换算（kg↔g、km↔m、%↔‰）→ 换算后判定并降级 warning；不可换算一律
  ``not_provided(unit_incompatible)``，绝不臆测；全链路 ``Decimal``（禁 float，
  边界扫描要检出 1 个最小计量单位的差异）；
- **同目标去重**：同一 ``(param, clause, applies_if)`` 建两遍才是双份结论来源
  （同一参数配不同 applies_if 是正常形态）。

限值数值只来自规则包（随包冻结 JSON + 漂移门）；本模块只出现数学定义域端点
（``0`` / ``1`` / ``2``）与换算系数（非领域限值）。规则包装载收**内存 dict**
（文件读取留输入层，`SKELETON-SPEC` §2）。
"""

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 四态 / 原因码（机读判据；测试断言它，不匹配中文散文）
# ---------------------------------------------------------------------------
COMPLIANT = "compliant"
NON_COMPLIANT = "non_compliant"
NOT_APPLICABLE = "not_applicable"
NOT_PROVIDED = "not_provided"
NOT_ASSESSED = "not_assessed"

ALL_STATES = (COMPLIANT, NON_COMPLIANT, NOT_APPLICABLE, NOT_PROVIDED)

REASON_MISSING = "missing"
REASON_NULL_VALUE = "null_value"
REASON_UNPARSABLE = "unparsable"
REASON_UNIT_UNKNOWN = "unit_unknown"
REASON_UNIT_INCOMPATIBLE = "unit_incompatible"
REASON_MAPPING_UNCERTAIN = "mapping_uncertain"
REASON_CONDITION_UNKNOWN = "condition_unknown"
REASON_NO_RULE_FOR_PARAM = "no_rule_for_param"

ALL_REASONS = (
    REASON_MISSING, REASON_NULL_VALUE, REASON_UNPARSABLE, REASON_UNIT_UNKNOWN,
    REASON_UNIT_INCOMPATIBLE, REASON_MAPPING_UNCERTAIN, REASON_CONDITION_UNKNOWN,
    REASON_NO_RULE_FOR_PARAM,
)

SEVERITY_NORMAL = "normal"
SEVERITY_WARNING = "warning"

#: 整体结论的"最弱优先"聚合序
OVERALL_PRECEDENCE = (NON_COMPLIANT, NOT_PROVIDED, NOT_ASSESSED, COMPLIANT)

#: 三维（作用域）展示与聚合的固定顺序：整车 → 电池 → 充电器
DIMENSION_ORDER = ("vehicle", "battery", "charger")

STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"
CLAUSE_VERIFIED = "verified"
CLAUSE_PENDING = "pending"

SCOPE_VEHICLE = "vehicle"
SCOPE_BATTERY = "battery"
SCOPE_CHARGER = "charger"
ALLOWED_SCOPES = (SCOPE_VEHICLE, SCOPE_BATTERY, SCOPE_CHARGER)

STANDARD_STATUSES = ("current", "superseded", "abolished")
ALLOWED_SOURCE_KINDS = ("standard_meta", "gov_qna", "standard_text", "to_verify")

ALLOWED_OPS = ("<=", ">=", "<", ">", "==", "!=", "in", "not_in", "range")

RULES_MANIFEST = "manifest.json"

#: 规则包分册 → 作用域（与 manifest 登记一致；装配顺序按 DIMENSION_ORDER）
RULESET_FILES: Tuple[Tuple[str, str, str], ...] = (
    ("gb17761-2024.json", "vehicle", "GB17761-2024"),
    ("gb17761-2018.json", "vehicle", "GB17761-2018"),
    ("gb43854-2024.json", "battery", "GB43854-2024"),
    ("gb42296-2022.json", "charger", "GB42296-2022"),
)

#: 单位换算表：``目标单位 -> {源单位: 乘数}``。只登记**显式无损**的十进换算；
#: 换算系数是数学常量（非领域限值），单位别名表来自规则包映射节。
UNIT_FACTORS: Dict[str, Dict[str, str]] = {
    "kg": {"kg": "1", "g": "0.001", "t": "1000"},
    "g": {"g": "1", "kg": "1000", "mg": "0.001"},
    "km/h": {"km/h": "1", "m/s": "3.6", "km/s": "3600"},
    "m/s": {"m/s": "1", "km/h": "0.2777777777777777777777777778"},
    "km": {"km": "1", "m": "0.001"},
    "m": {"m": "1", "km": "1000", "mm": "0.001"},
    "%": {"%": "1", "‰": "0.1"},
    "‰": {"‰": "1", "%": "10"},
    "V": {"V": "1", "mV": "0.001"},
    "W": {"W": "1", "kW": "1000"},
    "Ah": {"Ah": "1"},
    "": {"": "1"},
}

#: 视为"无量纲"的单位标记（枚举、布尔、文本参数）
DIMENSIONLESS_UNITS = frozenset({"", "none", "text", "bool"})

#: 各单位的"最小计量单位"（边界枚举用）；未登记者按 0.1 处理
UNIT_EPSILON: Dict[str, str] = {
    "km/h": "0.1", "m/s": "0.1", "kg": "0.1", "g": "0.1", "%": "0.1",
    "‰": "0.1", "km": "0.1", "m": "0.1", "V": "0.1", "W": "1", "mV": "1",
    "kW": "0.1",
}


class MatrixError(ValueError):
    """输入不可用（规则包/档案结构非法）；内核映射退出码 2。"""


class RulesetError(MatrixError):
    """规则包不可用（schema 非法 / 缺失 / 校验失败）。"""


class VersionError(MatrixError):
    """版本锚定不可用（窗口缺失 / 日期格式非法）。"""


# ---------------------------------------------------------------------------
# 基础值解析
# ---------------------------------------------------------------------------
def decode_decimal(value: Any) -> Optional[Decimal]:
    """标量 → ``Decimal``；不可解析返回 ``None``。bool 不接受（静默当数字会掩盖错误）。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None


def _coerce(value: Any) -> Any:
    """数值优先，退化为字符串（枚举比较用）。

    布尔先归一到 ``"true"``/``"false"`` 字符串：档案是 JSON，布尔项写成字面
    ``true``，而规则包统一用字符串承载值；不归一会让"已达标"被误判为不符合。
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    number = decode_decimal(value)
    if number is not None:
        return number
    if isinstance(value, str):
        return value
    return str(value)


def compare(observed: Any, op: str, limit: Any) -> bool:
    """按 ``op`` 比较观测值与限值（``op`` 已在 schema 层白名单校验）。"""
    if op in ("in", "not_in"):
        pool = limit if isinstance(limit, (list, tuple)) else [limit]
        member = observed in pool
        return member if op == "in" else not member
    if op == "range":
        low, high = limit[0], limit[1]
        return _coerce(low) <= _coerce(observed) <= _coerce(high)
    left = _coerce(observed)
    right = _coerce(limit)
    if op == "<=":
        return left <= right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == ">":
        return left > right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    raise ValueError("未知比较运算符: %r" % (op,))


def epsilon_for(unit: str) -> Decimal:
    """取该单位的最小计量单位（边界枚举用）。"""
    return Decimal(UNIT_EPSILON.get((unit or "").strip(), "0.1"))


def resolve_unit(token: str, aliases: Optional[Mapping[str, str]] = None) -> str:
    """把单位书写变体归一到规范单位；未登记的保持原样（仍"不可换算"）。"""
    text = (token or "").strip()
    if text in DIMENSIONLESS_UNITS:
        return text
    if text in UNIT_FACTORS:
        return text
    table = aliases if aliases is not None else {}
    return table.get(text, text)


def normalize_unit(value: Any, source_unit: str, target_unit: str,
                   aliases: Optional[Mapping[str, str]] = None) -> Tuple[Optional[Decimal], bool]:
    """把 ``value``（``source_unit``）换算到 ``target_unit``。

    返回 ``(数值, 是否降级)``；无法换算抛 :class:`UnitError`。
    """
    target = resolve_unit(target_unit, aliases)
    source = resolve_unit(source_unit, aliases)
    if target in DIMENSIONLESS_UNITS and source in DIMENSIONLESS_UNITS:
        return None, False
    if not source:
        raise UnitError("unit_unknown", "档案未提供单位，无法与限值比较")
    if source == target:
        number = decode_decimal(value)
        if number is None:
            raise UnitError("unparsable", "值不可解析为数值")
        return number, False
    table = UNIT_FACTORS.get(target)
    if not table or source not in table:
        raise UnitError(
            "unit_incompatible",
            "单位 %r 无法换算到 %r（未登记换算）" % (source, target),
        )
    number = decode_decimal(value)
    if number is None:
        raise UnitError("unparsable", "值不可解析为数值")
    return number * Decimal(table[source]), True


class UnitError(Exception):
    """单位不可用（缺失或不可换算）。``reason`` 供调用方转成原因码。"""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# 规则包校验与门控（内存 dict 通路）
# ---------------------------------------------------------------------------
def _require(mapping: Mapping, key: str, where: str) -> Any:
    if key not in mapping:
        raise RulesetError("%s 缺少必填字段: %s" % (where, key))
    return mapping[key]


def _check_date(text: Any, where: str) -> str:
    if not isinstance(text, str) or len(text) != 10 or text[4] != "-" or text[7] != "-":
        raise RulesetError("%s 日期格式应为 YYYY-MM-DD，实际: %r" % (where, text))
    return text


def validate_applies_if(expr: Any, where: str) -> Optional[Dict[str, Any]]:
    """校验 ``applies_if`` 文法（白名单小语言，不用 eval）。"""
    if expr is None:
        return None
    if not isinstance(expr, dict):
        raise RulesetError("%s 的 applies_if 必须是对象或 null" % where)
    keys = set(expr)
    if keys == {"param", "op", "value"}:
        if not isinstance(expr["param"], str) or not expr["param"]:
            raise RulesetError("%s 的 applies_if.param 必须是非空字符串" % where)
        if expr["op"] not in ALLOWED_OPS:
            raise RulesetError("%s 的 applies_if.op 越白名单: %r" % (where, expr["op"]))
        return dict(expr)
    if keys == {"all"} or keys == {"any"}:
        key = "all" if "all" in keys else "any"
        items = expr[key]
        if not isinstance(items, list) or not items:
            raise RulesetError("%s 的 applies_if.%s 必须是非空数组" % (where, key))
        return {key: [validate_applies_if(item, where) for item in items]}
    if keys == {"not"}:
        return {"not": validate_applies_if(expr["not"], where)}
    raise RulesetError(
        "%s 的 applies_if 结构非法（只允许 param/op/value、all、any、not）: %r"
        % (where, sorted(keys))
    )


def _parse_rule(raw: Mapping, standard_code: str, where: str) -> Dict[str, Any]:
    """单条规则 schema 校验 → 规范化 dict（含 status / clause 纪律）。"""
    rule_id = _require(raw, "id", where)
    if not isinstance(rule_id, str) or not rule_id:
        raise RulesetError("%s 的 id 必须是非空字符串" % where)
    op = _require(raw, "op", where)
    if op not in ALLOWED_OPS:
        raise RulesetError("%s 的 op 越白名单: %r" % (where, op))
    status = _require(raw, "status", where)
    if status not in (STATUS_VERIFIED, STATUS_PENDING):
        raise RulesetError("%s 的 status 非法: %r" % (where, status))
    clause_status = raw.get("clause_status", CLAUSE_PENDING)
    if clause_status not in (CLAUSE_VERIFIED, CLAUSE_PENDING):
        raise RulesetError("%s 的 clause_status 非法: %r" % (where, clause_status))
    clause = raw.get("clause")
    if clause_status == CLAUSE_VERIFIED:
        if not clause or not str(clause).strip():
            raise RulesetError(
                "%s 声明 clause_status=verified 但 clause 为空（不编造条款号纪律）" % where)
    elif clause:
        raise RulesetError(
            "%s 的 clause_status=pending 时 clause 必须为 null（不得预填未核对条款号）" % where)

    value = raw.get("value")
    if status == STATUS_VERIFIED:
        if value is None:
            raise RulesetError(
                "%s 声明 status=verified 但 value 为 null（未核对不得生效）" % where)
        if op in ("in", "not_in"):
            if not isinstance(value, list) or not value:
                raise RulesetError("%s 的 in/not_in 需要非空数组 value" % where)
        elif op == "range":
            if not isinstance(value, list) or len(value) != 2:
                raise RulesetError("%s 的 range 需要 [lo, hi] 两元素 value" % where)
            if decode_decimal(value[0]) is None or decode_decimal(value[1]) is None:
                raise RulesetError("%s 的 range 边界不可解析为数值" % where)
        elif decode_decimal(value) is None and not isinstance(value, str):
            raise RulesetError(
                "%s 的 value 不可解析为数值或字符串: %r" % (where, value))
    else:
        if value is not None:
            raise RulesetError(
                "%s 声明 status=pending 但 value 非 null（待核对不得预填数值）" % where)

    source = _require(raw, "source", where)
    if not isinstance(source, dict):
        raise RulesetError("%s 的 source 必须是对象" % where)
    kind = source.get("kind")
    if kind not in ALLOWED_SOURCE_KINDS:
        raise RulesetError("%s 的 source.kind 非法: %r" % (where, kind))
    if kind != "to_verify" and not source.get("url"):
        raise RulesetError("%s 的 source.kind=%s 必须提供 url" % (where, kind))
    if not source.get("retrieved_on"):
        raise RulesetError("%s 的 source.retrieved_on 必填" % where)

    param = _require(raw, "param", where)
    if not isinstance(param, str) or not param:
        raise RulesetError("%s 的 param 必须是非空字符串" % where)
    unit = raw.get("unit", "")
    if not isinstance(unit, str):
        raise RulesetError("%s 的 unit 必须是字符串" % where)

    return {
        "id": rule_id,
        "param": param,
        "op": op,
        "value": value,
        "unit": unit,
        "clause": clause,
        "clause_status": clause_status,
        "source": dict(source),
        "status": status,
        "applies_if": validate_applies_if(raw.get("applies_if"), where),
        "applies_if_raw": raw.get("applies_if"),
        "clause_excerpt": raw.get("clause_excerpt", "") or "",
        "notes": raw.get("notes", "") or "",
        "verified_on": raw.get("verified_on", "") or "",
        "standard_code": standard_code,
    }


def validate_ruleset(raw: Any, file_name: str) -> None:
    """校验分册顶层结构（schema 入口把规则本身也验到）。"""
    if not isinstance(raw, dict):
        raise RulesetError("%s 顶层必须是对象" % file_name)
    _require(raw, "schema_version", file_name)
    standard = _require(raw, "standard", file_name)
    if not isinstance(standard, dict):
        raise RulesetError("%s.standard 必须是对象" % file_name)
    for key in ("code", "title", "published", "effective", "status"):
        _require(standard, key, "%s.standard" % file_name)
    _check_date(standard["published"], "%s.standard.published" % file_name)
    _check_date(standard["effective"], "%s.standard.effective" % file_name)
    if standard["status"] not in STANDARD_STATUSES:
        raise RulesetError("%s.standard.status 非法: %r" % (file_name, standard["status"]))
    scope = _require(raw, "scope", file_name)
    if scope not in ALLOWED_SCOPES:
        raise RulesetError("%s.scope 非法: %r" % (file_name, scope))
    rules_raw = _require(raw, "rules", file_name)
    if not isinstance(rules_raw, list):
        raise RulesetError("%s.rules 必须是数组" % file_name)
    if not rules_raw:
        raise RulesetError("%s.rules 为空（分册至少要有一条登记条目）" % file_name)
    standard_code = standard["code"]
    for index, item in enumerate(rules_raw):
        where = "%s.rules[%d]" % (file_name, index)
        if not isinstance(item, dict):
            raise RulesetError("%s 必须是对象" % where)
        _parse_rule(item, standard_code, where)


def build_ruleset(raw: Any, file_name: str) -> Dict[str, Any]:
    """校验 + 门控 → 规则集视图（``rules`` = 生效规则；``excluded`` = 门控排除）。"""
    validate_ruleset(raw, file_name)
    standard_code = raw["standard"]["code"]
    effective: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    seen_ids = set()
    seen_keys = set()
    for index, item in enumerate(raw["rules"]):
        where = "%s.rules[%d]" % (file_name, index)
        rule = _parse_rule(item, standard_code, where)
        if rule["id"] in seen_ids:
            raise RulesetError("%s 的 id 重复: %s" % (where, rule["id"]))
        seen_ids.add(rule["id"])
        # 同目标去重：同一 (参数, 条款, 适用条件) 才算重复
        dedup_key = (
            rule["param"],
            rule["clause"] or "",
            json_dumps(rule["applies_if_raw"]),
        )
        if dedup_key in seen_keys:
            raise RulesetError(
                "%s 的 (param, clause, applies_if) 重复: %r（同目标去重纪律）"
                % (where, dedup_key))
        seen_keys.add(dedup_key)
        if rule["status"] == STATUS_VERIFIED:
            effective.append(rule)
        else:
            excluded.append({
                "rule_id": rule["id"],
                "param": rule["param"],
                "status": rule["status"],
                "reason": "not_verified",
            })
    return {
        "file_name": file_name,
        "standard": dict(raw["standard"]),
        "scope": raw["scope"],
        "rules": effective,
        "excluded": excluded,
    }


def json_dumps(value: Any) -> str:
    import json
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def load_manifest(raw: Any) -> Dict[str, Any]:
    """manifest 校验（内存 dict 通路；sha256 核对留输入层）。"""
    if not isinstance(raw, dict):
        raise RulesetError("manifest.json 顶层必须是对象")
    for key in ("schema_version", "generated_by", "rulesets", "thresholds"):
        if key not in raw:
            raise RulesetError("manifest.json 缺少必填字段: %s" % key)
    if not isinstance(raw["rulesets"], list) or not raw["rulesets"]:
        raise RulesetError("manifest.json rulesets 必须是非空数组")
    for entry in raw["rulesets"]:
        for key in ("file", "standard", "scope", "version_key", "effective_from"):
            if key not in entry:
                raise RulesetError("manifest rulesets 条目缺少字段: %s" % key)
        if entry["scope"] not in ALLOWED_SCOPES:
            raise RulesetError("manifest rulesets 条目 scope 非法: %r" % entry["scope"])
    return raw


def eval_applies_if(expr: Optional[Mapping], params: Mapping) -> Optional[bool]:
    """三值逻辑求值：``True`` / ``False`` / ``None``（unknown）。

    引用参数未提供或不可解析 → ``None``；调用方据此判 ``not_provided``。
    """
    if expr is None:
        return True
    if "param" in expr:
        provided = params.get(expr["param"])
        if not isinstance(provided, dict):
            return None
        number = decode_decimal(provided.get("value"))
        target = expr["value"]
        if number is None:
            raw_value = provided.get("value")
            if isinstance(raw_value, str) and expr["op"] in ("==", "!="):
                hit = raw_value == target
                return hit if expr["op"] == "==" else not hit
            return None
        try:
            return bool(compare(number, expr["op"], target))
        except (ValueError, TypeError):
            return None
    if "all" in expr:
        results = [eval_applies_if(item, params) for item in expr["all"]]
        if any(item is False for item in results):
            return False
        if any(item is None for item in results):
            return None
        return True
    if "any" in expr:
        results = [eval_applies_if(item, params) for item in expr["any"]]
        if any(item is True for item in results):
            return True
        if any(item is None for item in results):
            return None
        return False
    if "not" in expr:
        inner = eval_applies_if(expr["not"], params)
        return None if inner is None else not inner
    return None


# ---------------------------------------------------------------------------
# 参数 × 限值判定矩阵（四态）
# ---------------------------------------------------------------------------
def _observed_text(value: Any) -> Optional[str]:
    """把观测值转成可输出文本；``None`` 表示"未提供"。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def check_param(rule: Mapping, params: Mapping,
                unit_aliases: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """对单条规则判定一个车型档案参数（四态短路序）。

    ``unit_aliases`` 缺省时用随包单位别名表（mapping.unit_alias_index）。
    """
    if unit_aliases is None:
        from .mapping import unit_alias_index as _default_index
        unit_aliases = _default_index()
    base = {
        "rule_id": rule["id"],
        "param": rule["param"],
        "standard": rule["standard_code"],
        "clause": rule["clause"],
        "clause_status": rule["clause_status"],
        "op": rule["op"],
        "limit": rule["value"],
        "unit": rule["unit"],
    }

    condition = eval_applies_if(rule.get("applies_if"), params)
    if condition is False:
        return dict(base, observed=None, state=NOT_APPLICABLE, reason=None,
                    severity=SEVERITY_NORMAL, notes="")
    if condition is None:
        return dict(base, observed=None, state=NOT_PROVIDED,
                    reason=REASON_CONDITION_UNKNOWN, severity=SEVERITY_NORMAL, notes="")

    provided = params.get(rule["param"])
    if not isinstance(provided, dict):
        return dict(base, observed=None, state=NOT_PROVIDED, reason=REASON_MISSING,
                    severity=SEVERITY_NORMAL, notes="")
    if provided.get("reason") == REASON_MAPPING_UNCERTAIN:
        # 字段映射层的"歧义列名"标记：显式未提供，绝不猜值
        return dict(base, observed=None, state=NOT_PROVIDED,
                    reason=REASON_MAPPING_UNCERTAIN, severity=SEVERITY_NORMAL, notes="")
    raw_value = provided.get("value")
    if raw_value is None:
        return dict(base, observed=None, state=NOT_PROVIDED, reason=REASON_NULL_VALUE,
                    severity=SEVERITY_NORMAL, notes="")

    unit_target = rule["unit"] or ""
    if unit_target.strip() == "" or unit_target.lower() in ("none", "text", "bool"):
        # 无量纲/枚举通路：直接比较原值
        try:
            ok = compare(raw_value, rule["op"], rule["value"])
        except (ValueError, TypeError):
            return dict(base, observed=_observed_text(raw_value), state=NOT_PROVIDED,
                        reason=REASON_UNPARSABLE, severity=SEVERITY_NORMAL, notes="")
        return dict(base, observed=_observed_text(raw_value),
                    state=COMPLIANT if ok else NON_COMPLIANT,
                    reason=None, severity=SEVERITY_NORMAL, notes="")

    try:
        number, downgraded = normalize_unit(raw_value, provided.get("unit", ""),
                                            unit_target, unit_aliases)
    except UnitError as error:
        reason = (
            REASON_UNIT_UNKNOWN if error.reason == "unit_unknown"
            else REASON_UNIT_INCOMPATIBLE if error.reason == "unit_incompatible"
            else REASON_UNPARSABLE
        )
        return dict(base, observed=_observed_text(raw_value), state=NOT_PROVIDED,
                    reason=reason, severity=SEVERITY_NORMAL, notes=str(error))

    ok = compare(number, rule["op"], rule["value"])
    return dict(base, observed=str(number),
                state=COMPLIANT if ok else NON_COMPLIANT,
                reason=None,
                severity=SEVERITY_WARNING if downgraded else SEVERITY_NORMAL,
                notes="单位已由 %s 换算为 %s" % (provided.get("unit", ""), unit_target)
                if downgraded else "")


def check_params(rules: Sequence[Mapping], params: Mapping,
                 unit_aliases: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """对一组规则判定同一档案的全部参数。"""
    return [check_param(rule, params, unit_aliases) for rule in rules]


def dimension_overall(findings: Sequence[Mapping]) -> str:
    """维度整体结论：按"最弱优先"聚合；``not_applicable`` 不作结论参与。"""
    states = {item["state"] for item in findings}
    if NON_COMPLIANT in states:
        return NON_COMPLIANT
    if NOT_PROVIDED in states:
        return NOT_PROVIDED
    relevant = states - {NOT_APPLICABLE}
    if not relevant:
        return NOT_ASSESSED
    if relevant <= {COMPLIANT}:
        return COMPLIANT
    return NOT_ASSESSED


def check_profile(subject: Mapping, ruleset_docs: Mapping[str, Any],
                  unit_aliases: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """三维装配：整车（按版本锚定）→ 电池 → 充电器 → 统一结论。

    ``ruleset_docs``：``{文件名: 规则集 dict}``（随包冻结资产，输入层已读取）。
    """
    validate_subject(subject)
    profile_id = subject.get("profile_id")
    version_key = subject.get("version_key") or anchor_version(subject)
    params = subject.get("params") or {}

    dimensions: List[Dict[str, Any]] = []
    participating: List[str] = []
    for file_name, _scope, expected_key in RULESET_FILES:
        if _scope == SCOPE_VEHICLE:
            # 整车维度按锚定版本取分册（显式 --version-of 语义经 version_key 字段）
            if version_key != expected_key:
                continue
        doc = ruleset_docs.get(file_name)
        if doc is None:
            raise RulesetError("规则包缺少分册: %s" % file_name)
        ruleset = build_ruleset(doc, file_name)
        if _scope != SCOPE_VEHICLE:
            # 电池/充电器是独立标准、各自成维度；本器官恒取现行分册
            pass
        findings = check_params(ruleset["rules"], params, unit_aliases)
        overall = dimension_overall(findings)
        participates = ruleset["scope"] == SCOPE_VEHICLE or len(ruleset["rules"]) > 0
        # 零生效规则的维度不参与统一结论聚合（否则会把整体结论无谓拉成"未评估"）
        if ruleset["scope"] == SCOPE_VEHICLE:
            participates = True
        else:
            participates = bool(ruleset["rules"])
        dimensions.append({
            "scope": ruleset["scope"],
            "standard": ruleset["standard"]["code"],
            "ruleset_file": file_name,
            "version_key": ruleset["standard"]["code"],
            "effective_rule_count": len(ruleset["rules"]),
            "excluded_rules": ruleset["excluded"],
            "findings": findings,
            "counts": _counts(findings),
            "overall": overall,
            "participates": participates,
        })
        if participates:
            participating.append(overall)

    overall = NOT_ASSESSED
    for candidate in OVERALL_PRECEDENCE:
        if candidate in participating:
            overall = candidate
            break
    return {
        "profile_id": profile_id,
        "version_key": version_key,
        "dimensions": dimensions,
        "counts": _counts(
            [f for d in dimensions for f in d["findings"]]),
        "overall": overall,
        "excluded_rules": [e for d in dimensions for e in d["excluded_rules"]],
    }


def _counts(findings: Sequence[Mapping]) -> Dict[str, int]:
    tally = {state: 0 for state in ALL_STATES}
    for item in findings:
        tally[item["state"]] = tally.get(item["state"], 0) + 1
    return tally


def anchor_version(subject: Mapping, version_anchors: Optional[Sequence[Mapping]] = None
                   ) -> str:
    """版本锚定：``model_design_date`` 优先、``market_date`` 次之；无日期不猜。

    锚点窗口来自 manifest ``version_anchors``（随包快照）。
    """
    anchors = DEFAULT_VERSION_ANCHORS if version_anchors is None else version_anchors
    design_date = subject.get("model_design_date")
    market_date = subject.get("market_date")
    if design_date:
        basis_value = design_date
    elif market_date:
        basis_value = market_date
    else:
        raise VersionError("档案未提供 model_design_date 或 market_date，无法锚定版本")
    point = _date_key(basis_value)
    for window in anchors:
        start = window.get("applies_from")
        until = window.get("applies_until")
        if start and point < _date_key(start):
            continue
        if until and point >= _date_key(until):
            continue
        return str(window["version_key"])
    raise VersionError("日期 %s 未命中任何版本窗口" % basis_value)


def _date_key(text: str) -> Tuple[int, int, int]:
    if not isinstance(text, str):
        raise VersionError("日期必须是字符串: %r" % (text,))
    parts = text.split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise VersionError("日期格式应为 YYYY-MM-DD: %r" % (text,))
    return int(parts[0]), int(parts[1]), int(parts[2])


#: manifest ``version_anchors`` 快照（与 data/manifest.json 逐条一致；漂移门核对）
DEFAULT_VERSION_ANCHORS: Tuple[Dict[str, Any], ...] = (
    {"standard_family": "GB17761", "version_key": "GB17761-2024",
     "applies_from": "2025-09-01",
     "note": "新生产车辆适用（实施日 2025-09-01）"},
    {"standard_family": "GB17761", "version_key": "GB17761-2018",
     "applies_until": "2025-09-01",
     "note": "历史车型对照；生产过渡期至 2025-08-31、销售过渡期至 2025-11-30"},
)


# ---------------------------------------------------------------------------
# 批量扫描与跨轮对账（来源 reconcile + benchmark.cases.observed_nonpass 判定面）
# ---------------------------------------------------------------------------
#: 参数级"非通过"口径的单一实现源：``non_compliant`` ∪ ``not_provided``。
NONPASS_STATES = (NON_COMPLIANT, NOT_PROVIDED)


def observed_nonpass(findings: Sequence[Mapping]) -> List[Tuple[str, str]]:
    """本次核查的"非通过"集合 = ``(param, state)`` 升序（单一实现源）。

    「没看到」不算「缺失」，但「未提供」是「没检查完」，必须能与「符合」区分开。
    """
    out = [(f["param"], f["state"]) for f in findings if f["state"] in NONPASS_STATES]
    return sorted(out)


def reconcile_rounds(baseline: Sequence[Mapping], current: Sequence[Mapping]):
    """对账两轮核查结果 → 三集合（新增越限 / 已整改 / 持续越限）。

    ``baseline`` / ``current`` 元素为 :func:`check_profile` 的结果 dict；
    配对主键 = ``profile_id``（稳定身份键）。纪律：

    - 已整改 / 持续越限只在**两轮都出现**的档案间配对（上轮的档案本轮没被
      扫描 ≠ 已整改）；
    - 仅本轮出现的档案，其非通过项全部算「新增越限」；
    - 上轮非通过、本轮该参数不再非通过算「已整改」（改值判合规或补齐缺失）。
    """
    def _nonpass_by_profile(results):
        out = {}
        for result in results:
            merged = [f for d in result["dimensions"] for f in d["findings"]]
            out[result["profile_id"]] = observed_nonpass(merged)
        return out

    before = _nonpass_by_profile(baseline)
    after = _nonpass_by_profile(current)
    new_violations: List[Tuple[str, str, str]] = []
    resolved: List[Tuple[str, str, str]] = []
    persistent: List[Tuple[str, str, str]] = []

    for profile_id in sorted(set(before) & set(after)):
        prev = dict(before[profile_id])
        curr = dict(after[profile_id])
        for param in sorted(set(prev) | set(curr)):
            was = prev.get(param)
            now = curr.get(param)
            if was is not None and now is None:
                resolved.append((profile_id, param, was))
            elif was is None and now is not None:
                new_violations.append((profile_id, param, now))
            else:
                persistent.append((profile_id, param, now))
    for profile_id in sorted(set(after) - set(before)):
        for param, state in after[profile_id]:
            new_violations.append((profile_id, param, state))
    return {
        "key_basis": "profile_id",
        "new_violations": new_violations,
        "resolved": resolved,
        "persistent": persistent,
        "counts": {"new_violation": len(new_violations), "resolved": len(resolved),
                   "persistent": len(persistent)},
    }


def scan_profiles(subjects: Sequence[Mapping], ruleset_docs: Mapping[str, Any],
                  unit_aliases: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """批量核查多份档案（顺序按 ``profile_id`` 排序，输出确定）。"""
    results = [check_profile(sub, ruleset_docs, unit_aliases) for sub in subjects]
    results.sort(key=lambda r: r["profile_id"])
    return results


def version_diff_params(old_doc: Mapping, new_doc: Mapping) -> List[Dict[str, Any]]:
    """两版规则包 diff → 逐参数差异表（从规则包本身 diff 生成，不手写）。

    差异类型：``added`` / ``removed`` / ``tightened`` / ``relaxed`` /
    ``value_changed`` / ``operator_changed`` / ``unchanged``；方向判定只对
    同向阈值运算符（``<=`` 降 / ``>=`` 升 / ``in`` 收缩 / ``not_in`` 扩张）有意义。
    """
    old_rules = {r["id"]: r for r in build_ruleset(old_doc, "old.json")["rules"]}
    new_rules = {r["id"]: r for r in build_ruleset(new_doc, "new.json")["rules"]}
    out: List[Dict[str, Any]] = []
    for rule_id in sorted(set(old_rules) | set(new_rules)):
        old = old_rules.get(rule_id)
        new = new_rules.get(rule_id)
        if old is None:
            out.append({"param": new["param"], "rule_id": rule_id, "kind": "added"})
            continue
        if new is None:
            out.append({"param": old["param"], "rule_id": rule_id, "kind": "removed"})
            continue
        op_changed = old["op"] != new["op"]
        value_changed = old["value"] != new["value"]
        if not op_changed and not value_changed:
            out.append({"param": old["param"], "rule_id": rule_id, "kind": "unchanged"})
            continue
        if op_changed:
            kind = "operator_changed" if not value_changed else "value_changed"
            out.append({"param": old["param"], "rule_id": rule_id, "kind": kind,
                        "old_op": old["op"], "new_op": new["op"],
                        "old_value": old["value"], "new_value": new["value"]})
            continue
        kind = _threshold_direction(old, new)
        out.append({"param": old["param"], "rule_id": rule_id, "kind": kind,
                    "old_value": old["value"], "new_value": new["value"]})
    return out


_THRESHOLD_OPS = ("<=", "<", ">", ">=")


def _threshold_direction(old: Mapping, new: Mapping) -> str:
    """同向阈值比较 → tightened / relaxed；不适用方向语义 → value_changed。"""
    if old["op"] not in _THRESHOLD_OPS or new["op"] != old["op"]:
        return "value_changed"
    old_value = decode_decimal(old["value"])
    new_value = decode_decimal(new["value"])
    if old_value is None or new_value is None:
        return "value_changed"
    if old["op"] in ("<=", "<"):
        return "tightened" if new_value < old_value else (
            "relaxed" if new_value > old_value else "value_changed")
    return "tightened" if new_value > old_value else (
        "relaxed" if new_value < old_value else "value_changed")


def validate_subject(subject: Mapping) -> None:
    """subject 结构校验（非法抛 :class:`MatrixError`，内核映射 2）。"""
    if not isinstance(subject, Mapping):
        raise MatrixError("输入必须是 JSON 对象，得到 %s" % type(subject).__name__)
    if not subject.get("profile_id") or not isinstance(subject.get("profile_id"), str):
        raise MatrixError("档案缺少 profile_id（string）")
    params = subject.get("params")
    if not isinstance(params, dict):
        raise MatrixError("档案缺少 params 对象")
    for name, entry in params.items():
        if isinstance(entry, dict):
            if "value" not in entry and "reason" not in entry:
                raise MatrixError("params[%r] 缺少 value（或映射不确定标记）" % name)
            if "unit" in entry and not isinstance(entry["unit"], str):
                raise MatrixError("params[%r].unit 必须是字符串" % name)
