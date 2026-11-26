"""政策条目入库判定内核（**零 I/O / 零时钟 / 零环境变量 / 零网络**）。

迁移的是来源产品的判定面：统一 schema 校验、发布日期真实性、文号三态、部门归一、
快照双键新增/重复判定、规范序。只保留「已抓到的条目 → 判定」这一段：

- **必填缺失 ≠ 补编**：缺任一必填字段 → 该条不得落库、不得进日报；
- **日期两步校验**：先看 `YYYY.MM.DD` 形态，再用真实日历校验组合（`2026.13.45` 必须被挡）；
- **文号三态**：`parsed` / `partial` / `unparsed`，未解析字段显式标哨兵 `未解析`，**不编造年份**；
- **部门归一**：空白类字符拆分 + 前缀匹配 + **最长优先**；未命中原样保留（不猜）；
- **双键去重**：`id` 相同 → 重复；否则 `pcode` 相同且非空 → 重复；命中键可回溯；
- **规范序**：`pubtimeStr` 倒序、同级 `id` 升序，**产物无时间戳**。

字段/文号/别名等口径数值**只能来自** :mod:`registry`；本模块不读数据文件。

本模块不读抓取产物：``judge_intake`` 收**已解析的条目清单**（上次快照 + 本次条目）。
抓取（HTTP）、产物格式分派、写盘属输入层，见 ``docs/policy-intake.md`` §5。
"""

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import registry


class ItemError(ValueError):
    """条目/输入形态不合法。内核映射退出码 2。"""


DATE_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")
WHITESPACE_RE = re.compile(r"\s+")
DECREE_RE = re.compile(r"^(?P<agency>[^\u7b2c]+)\u7b2c(?P<body>[^\u53f7]*)\u53f7")

#: 分类
CLASS_NEW = "new"
CLASS_DUPLICATE = "duplicate"


# ------------------------------------------------------------------ 条目
def normalize_item(raw: Any) -> Dict[str, Any]:
    """把一条原始条目归一到十字段（多余字段保留在 ``_extra`` 供字段门判定）。"""
    if not isinstance(raw, Mapping):
        raise ItemError("条目必须是 JSON 对象，得到 %s" % type(raw).__name__)
    item = {}
    for name in registry.SCHEMA_FIELDS:
        value = raw.get(name, "")
        item[name] = "" if value is None else value
    item["_extra"] = sorted(set(raw) - set(registry.SCHEMA_FIELDS))
    return item


def required_missing(item: Mapping) -> Tuple[str, ...]:
    """返回缺失的必填字段名（空 = 通过）。**空白字符串同样算缺失**。"""
    missing = []
    for name in registry.REQUIRED_FIELDS:
        value = item.get(name, "")
        if not str(value or "").strip():
            missing.append(name)
    return tuple(missing)


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _days_in_month(year: int, month: int) -> int:
    if month == 2 and _is_leap(year):
        return 29
    return _DAYS[month - 1]


def date_valid(text: Any) -> bool:
    """`pubtimeStr` 形态 + 组合真实性校验。

    两步：① 分隔符形态由正则把关（`2026-10-08` 这类不得放过）；② 用真实日历校验
    组合（"月日各自合法但组合不存在"的 `2026.13.45` / `2026.02.30` 必须被挡下）。
    """
    value = str(text or "")
    if not DATE_RE.match(value):
        return False
    year, month, day = int(value[0:4]), int(value[5:7]), int(value[8:10])
    if not 1 <= month <= 12:
        return False
    if not 1 <= day <= _days_in_month(year, month):
        return False
    return True


def _all_keys(item: Mapping) -> set:
    """原始键 = 十字段 + ``_extra``（归一化时把白名单外的键收进 ``_extra``）。"""
    return set(item) | set(item.get("_extra") or ())


def forbidden_fields(item: Mapping) -> Tuple[str, ...]:
    """快照/条目里出现的禁字段（不做全文归档）。"""
    return tuple(sorted(_all_keys(item) & set(registry.FORBIDDEN_SNAPSHOT_FIELDS)))


def extra_fields(item: Mapping) -> Tuple[str, ...]:
    """字段白名单之外的字段（**允许清单不是黑名单**；禁字段另计，不重复报）。"""
    extra = set(item.get("_extra") or ())
    if not extra:
        extra = set(item) - set(registry.SCHEMA_FIELDS) - {"_extra"}
    return tuple(sorted(extra - set(registry.FORBIDDEN_SNAPSHOT_FIELDS)))


def field_violations(items: Sequence[Mapping]) -> List[Dict[str, Any]]:
    """逐条收集字段门违规（禁字段 / 白名单外字段）。"""
    out = []
    for index, item in enumerate(items):
        forbidden = forbidden_fields(item)
        if forbidden:
            out.append({"index": index, "item_id": item.get("id"),
                        "kind": "forbidden", "fields": list(forbidden)})
        extra = extra_fields(item)
        if extra:
            out.append({"index": index, "item_id": item.get("id"),
                        "kind": "extra", "fields": list(extra)})
    return out


# ------------------------------------------------------------------ 文号三态
def _find_bracket_pair(text: str) -> Tuple[Optional[int], Optional[int]]:
    for left, right in registry.BRACKET_PAIRS:
        pos = text.find(left)
        if pos >= 0:
            end = text.find(right, pos + 1)
            if end > pos:
                return pos, end
    return None, None


def _digits(text: str) -> str:
    digits = "".join(char for char in text if char.isdigit())
    return digits if digits else registry.UNPARSED


def _serial_from_tail(tail: str) -> str:
    before_hao = tail.split("\u53f7", 1)[0]
    return _digits(before_hao)


def _with_status(fields: Mapping[str, str]) -> Dict[str, str]:
    known = [value for value in fields.values() if value != registry.UNPARSED]
    if len(known) == 3:
        status = registry.STATUS_PARSED
    elif known:
        status = registry.STATUS_PARTIAL
    else:
        status = registry.STATUS_UNPARSED
    out = dict(fields)
    out["status"] = status
    return out


def _unparsed_all() -> Dict[str, str]:
    return {"agency_code": registry.UNPARSED, "year": registry.UNPARSED,
            "serial": registry.UNPARSED, "status": registry.STATUS_UNPARSED}


def _is_year(text: str) -> bool:
    return len(text) == 4 and text.isdigit()


def parse_pcode(pcode: Any) -> Dict[str, str]:
    """文号原文 → ``{agency_code, year, serial, status}``（三态）。

    - 括号形态：代字 = 左括号前全部非空字符；年份 = 括号内四位数字；序号 = 右括号后
      到「号」前的数字串（容忍序号与「号」之间空白）；
    - 「第…号」形态：代字 = 「第」前字符；年份 = **未解析**（可靠来源缺失，不编造）；
    - 其它：整条 ``unparsed``。
    """
    text = str(pcode or "").strip()
    if not text:
        return _unparsed_all()

    open_at, close_at = _find_bracket_pair(text)
    if open_at is not None:
        agency = text[:open_at].strip()
        inner = text[open_at + 1:close_at].strip()
        return _with_status({
            "agency_code": agency if agency else registry.UNPARSED,
            "year": inner if _is_year(inner) else registry.UNPARSED,
            "serial": _serial_from_tail(text[close_at + 1:]),
        })

    match = DECREE_RE.match(text)
    if match:
        agency = match.group("agency").strip()
        return _with_status({
            "agency_code": agency if agency else registry.UNPARSED,
            "year": registry.UNPARSED,
            "serial": _digits(match.group("body")),
        })
    return _unparsed_all()


# ------------------------------------------------------------------ 部门归一
def sorted_alias_keys(aliases: Mapping[str, str]) -> List[str]:
    """别名键按「长度倒序、字典序」排（最长优先，同长稳定）。"""
    return sorted(aliases, key=lambda key: (-len(key), key))


def parse_orgs(puborg: Any, aliases: Mapping[str, str]) -> List[Dict[str, Any]]:
    """`puborg` → 逐 token 的 ``{raw, canonical, alias_missing}``。

    拆分按空白类字符（含 U+2002 / U+00A0 一类）；匹配 = 前缀 + 最长优先；
    未命中：``canonical`` 原样保留、``alias_missing=True``（**不猜**）。
    """
    text = str(puborg or "").strip()
    if not text:
        return []
    keys = sorted_alias_keys(aliases)
    out = []
    for token in WHITESPACE_RE.split(text):
        if not token:
            continue
        matched = None
        for key in keys:
            if token.startswith(key):
                matched = key
                break
        if matched is None:
            out.append({"raw": token, "canonical": token, "alias_missing": True})
        else:
            out.append({"raw": token, "canonical": aliases[matched],
                        "alias_missing": False})
    return out


# ------------------------------------------------------------------ 规范序与去重
def canonical_order(items: Sequence[Mapping]) -> List[Mapping]:
    """``(pubtimeStr 倒序, id 升序)``；两步稳定排序，不读时钟、不做日期数值转换。"""
    ordered = sorted(items, key=lambda item: str(item.get("id", "")))
    ordered.sort(key=lambda item: str(item.get("pubtimeStr", "")), reverse=True)
    return ordered


def is_canonical_order(items: Sequence[Mapping]) -> bool:
    """观测判据：给定序列是否已是规范序。"""
    return list(canonical_order(items)) == list(items)


def detect_new(previous_items: Sequence[Mapping],
               current_items: Sequence[Mapping]) -> Dict[str, Any]:
    """双键判定：``id`` 相同 → 重复；否则 ``pcode`` 相同且非空 → 重复；否则新增。

    返回 ``{new_ids, dup_ids, matched_by}``；``matched_by`` 覆盖每一条重复
    （命中键供回溯：该按 pcode 命中的却按 id 算，是缺陷，必须能点名）。
    """
    previous_ids = set(str(item.get("id", "")) for item in previous_items)
    previous_pcodes = set(str(item.get("pcode", "")) for item in previous_items
                          if str(item.get("pcode", "")))
    new_ids, dup_ids, matched_by = [], [], {}
    for item in current_items:
        item_id = str(item.get("id", ""))
        pcode = str(item.get("pcode", ""))
        if item_id in previous_ids:
            dup_ids.append(item_id)
            matched_by[item_id] = "id"
            continue
        if pcode and pcode in previous_pcodes:
            dup_ids.append(item_id)
            matched_by[item_id] = "pcode"
            continue
        new_ids.append(item_id)
    new_ids.sort()
    dup_ids.sort()
    return {"new_ids": new_ids, "dup_ids": dup_ids, "matched_by": matched_by}


# ------------------------------------------------------------------ 输入与判定
def load_items(raw: Any, where: str) -> List[Dict[str, Any]]:
    """把 ``{"items": [...]}`` 或裸数组归一到条目清单。"""
    if isinstance(raw, Mapping):
        items = raw.get("items")
    else:
        items = raw
    if not isinstance(items, (list, tuple)):
        raise ItemError("%s 缺少 items 数组" % where)
    return [normalize_item(item) for item in items]


def validate_subject(subject: Any) -> Mapping:
    """输入结构校验。``previous`` 缺省或 ``null`` = 首跑。"""
    if not isinstance(subject, Mapping):
        raise ItemError("输入必须是 JSON 对象，得到 %s" % type(subject).__name__)
    if "current" not in subject:
        raise ItemError("缺少 current（本次条目）")
    previous = subject.get("previous")
    if previous is not None and not isinstance(previous, (Mapping, list, tuple)):
        raise ItemError("previous 必须是对象（含 items）或 null")
    if previous is not None and isinstance(previous, Mapping) \
            and previous.get("items") is None:
        raise ItemError("previous.items 缺失")
    return subject


def judge_intake(subject: Mapping,
                 aliases: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """对一批条目做入库判定（纯函数）。"""
    validate_subject(subject)
    alias_table = dict(registry.ORG_ALIASES if aliases is None else aliases)

    current = load_items(subject["current"], "current")
    previous_raw = subject.get("previous")
    first_run = previous_raw is None
    previous = [] if first_run else load_items(previous_raw, "previous")

    violations = field_violations(current)

    classified = detect_new(previous, current)
    records = []
    for index, item in enumerate(current):
        pcode = parse_pcode(item.get("pcode"))
        orgs = parse_orgs(item.get("puborg"), alias_table)
        item_id = str(item.get("id", ""))
        if item_id in classified["matched_by"]:
            category = CLASS_DUPLICATE
            matched_by = classified["matched_by"][item_id]
        else:
            category = CLASS_NEW
            matched_by = None
        records.append({
            "index": index,
            "item_id": item_id,
            "pcode": item.get("pcode", ""),
            "puborg": item.get("puborg", ""),
            "missing": list(required_missing(item)),
            "date_valid": date_valid(item.get("pubtimeStr")),
            "forbidden": list(forbidden_fields(item)),
            "extra": list(extra_fields(item)),
            "pcode_parse": pcode,
            "orgs": orgs,
            "category": category,
            "matched_by": matched_by,
        })

    order_source = current if first_run else previous + current
    return {
        "first_run": first_run,
        "previous_count": len(previous),
        "current_count": len(current),
        "new_ids": classified["new_ids"],
        "dup_ids": classified["dup_ids"],
        "matched_by": classified["matched_by"],
        "field_violations": violations,
        "records": records,
        "order_observed": is_canonical_order(order_source),
    }


def pcode_counts(records: Sequence[Mapping]) -> Dict[str, int]:
    counts = {status: 0 for status in registry.PCODE_STATUSES}
    for record in records:
        counts[record["pcode_parse"]["status"]] += 1
    return counts


def alias_missing_tokens(records: Sequence[Mapping]) -> List[str]:
    tokens = []
    for record in records:
        for org in record["orgs"]:
            if org["alias_missing"] and org["raw"] not in tokens:
                tokens.append(org["raw"])
    return sorted(tokens)


__all__ = [
    "ItemError", "DATE_RE", "WHITESPACE_RE", "DECREE_RE", "CLASS_NEW", "CLASS_DUPLICATE",
    "normalize_item", "required_missing", "date_valid", "forbidden_fields", "extra_fields",
    "field_violations", "parse_pcode", "sorted_alias_keys", "parse_orgs", "canonical_order",
    "is_canonical_order", "detect_new", "load_items", "validate_subject", "judge_intake",
    "pcode_counts", "alias_missing_tokens",
]