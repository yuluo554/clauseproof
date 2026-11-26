"""支出账本判定内核（**零 I/O / 零时钟 / 零环境变量 / 零业务数值字面量**）。

迁移的是来源产品的「多平台账单对账」判定面（归一化 → 跨平台去重 → 语义识别
→ 订阅识别），只保留「已解码文本行 → 判定」这一段：

- **行三态**：``ok`` / ``invalid`` / ``unknown``——invalid 行绝不入库（宁可少一行，
  不可错位入库）；unknown 行入库且显式列出（"未知"是可用的行）；
- **归一化动作序列写死**：去空白 → 全半角（映射表驱动）→ 后缀剥离（白名单、
  剥离后非空才生效）→ 别名表（variants 过同一管线后建索引）；未命中原样保留；
- **跨平台去重**：金额 Decimal 精确相等 + ``|Δt| ≤ W`` 闭区间 + 归一对手方相等；
  同方向内链式相邻聚类（A-B 近、B-C 近、A-C 远仍同簇）；簇内 ≥2 平台判重复
  （非代表笔排除出净额），单平台候选**显式不合并**；代表笔 = 时间最早 →
  平台优先级（规则包）→ 来源行号；
- **语义识别**：关键词子串匹配（区分大小写）+ 收支方向组合；规则按 priority
  升序评估、同优先级按 id 升序；命中多条取首个但**全部命中都记录**；
  "未知"是一等结论，绝不 fallthrough 为"消费"；
- **订阅识别**：只对语义=消费的支出行判定；同商户（金额子分组）链式聚类 →
  连续 min_repeats 期落在周期容差带（允许漏一期）作种子 → 逐期续链；
  涨价续链（金额变化 ≥ 阈值、间隔落单期带内）合并两段；涨价只记录**观测到的**
  变动，不做预测；未锚定链终态进干扰行清单。

业务数值（去重窗口 / 最小重复数 / 容差天数 / 涨价阈值 / 周期表 / 平台次序 /
表头定位参数）**只能来自** :mod:`registry`（规则包快照）；本模块只出现结构
性端点（``0`` / ``1`` / ``2`` 等），不出现任何口径数值。

本模块不做文件 IO、不探测编码、不解 XLSX 容器：``ingest`` 收**已解码的文本行**
（编码判定是输入层的事，属 `SKELETON-SPEC` §2 禁止的器官 I/O 面——
见 ``docs/expense-ledger.md`` §5）。
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import re

_WHITESPACE_RUN = re.compile(r"\s+")

# ---------------------------------------------------------------------------
# 行三态 / 问题码（机读判据；测试断言它，不匹配中文散文）
# ---------------------------------------------------------------------------
STATUS_OK = "ok"
STATUS_INVALID = "invalid"
STATUS_UNKNOWN = "unknown"

CODE_AMOUNT_MISSING = "amount_missing"
CODE_AMOUNT_NOT_NUMERIC = "amount_not_numeric"
CODE_AMOUNT_AMBIGUOUS = "amount_ambiguous"
CODE_TIME_UNPARSEABLE = "time_unparseable"
CODE_COLUMN_COUNT = "column_count_mismatch"
CODE_UNMAPPED_DIRECTION = "unmapped_direction"
CODE_HEADER_NOT_FOUND = "header_not_found"
CODE_REQUIRED_COLUMN_MISSING = "required_column_missing"
CODE_UNKNOWN_COLUMN = "unknown_column"
CODE_EMPTY_FILE = "empty_file"
CODE_UNKNOWN_PLATFORM = "unknown_platform"
CODE_UNSUPPORTED_FORMAT = "unsupported_format"
CODE_ENCODING_UNDETERMINED = "encoding_undetermined"
CODE_BAD_INPUT = "input_bad"

# 归一化动作 id（顺序即语义）
RULE_WHITESPACE = "whitespace_collapse"
RULE_FULLWIDTH = "fullwidth_norm"
RULE_SUFFIX = "suffix_strip"
RULE_ALIAS = "alias_table"

# 平台语义值（来源 IR 口径）
DIR_EXPENSE = "expense"
DIR_INCOME = "income"
DIR_NEUTRAL = "neutral"

# 收支类型列取值白名单（微信/支付宝形态）
DIRECTION_EXPENSE = "支出"
DIRECTION_INCOME = "收入"
DIRECTION_NEUTRAL = "不计收支"

# 去重结论（来源 IR 口径）
VERDICT_CROSS = "duplicate_cross_platform"
VERDICT_SAME = "candidate_same_platform"

# 语义未知（一等结论）
LABEL_UNKNOWN = "未知"

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_THOUSANDS_SEP = ","

#: 规范字段名（IR 语义字段的唯一拼法，与列别名表 canonical 同源）
F_TIME = "交易时间"
F_AMOUNT = "金额"
F_DIRECTION = "收支类型"
F_COUNTERPARTY = "对手方"
F_DESCRIPTION = "商品说明"

REQUIRED_IR_FIELDS = (F_TIME, F_AMOUNT, F_COUNTERPARTY)

# 银行表头的固定列名（收支分列形态）
BANK_EXPENSE_COL = "支出金额"
BANK_INCOME_COL = "收入金额"
BANK_TIME_COL = "交易时间"  # 时分秒列（表头名与微信同、语义不同）
BANK_DATE_COL = "交易日期"

DAY_SECONDS = 86400


class LedgerError(ValueError):
    """输入不可用（字段缺失 / 结构非法）；内核映射退出码 2。"""


class InputBad(LedgerError):
    """subject 结构非法。"""


# ---------------------------------------------------------------------------
# 输入校验
# ---------------------------------------------------------------------------
def validate_subject(subject: Mapping) -> None:
    """subject 结构校验（非法抛 :class:`InputBad`，内核映射 2）。"""
    if not isinstance(subject, Mapping):
        raise InputBad("输入必须是 JSON 对象，得到 %s" % type(subject).__name__)
    files = subject.get("files")
    if not isinstance(files, Mapping) or not files:
        raise InputBad("缺少 files（文件名 → 已解码文本行的对象）")
    for name, doc in files.items():
        if not isinstance(doc, Mapping):
            raise InputBad("files[%r] 必须是对象" % name)
        if doc.get("encoding") == "xlsx":
            table = doc.get("table")
            if not isinstance(table, (list, tuple)):
                raise InputBad("files[%r].table 必须是二维数组（xlsx 通道）" % name)
            for row in table:
                if not isinstance(row, (list, tuple)):
                    raise InputBad("files[%r].table 行必须是数组" % name)
        else:
            lines = doc.get("lines")
            if not isinstance(lines, (list, tuple)):
                raise InputBad("files[%r].lines 必须是数组（已解码文本行）" % name)
            for line in lines:
                if not isinstance(line, str):
                    raise InputBad("files[%r].lines 行必须是字符串" % name)


# ---------------------------------------------------------------------------
# 编码通道无关的文本行 → 单元格（输入层已解码；本层只切列）
# ---------------------------------------------------------------------------
def _split_row(line: str) -> List[str]:
    return line.split("\t")


# ---------------------------------------------------------------------------
# 表头定位 / 列映射
# ---------------------------------------------------------------------------
def locate_header(lines: Sequence[str], platform: str, header_k: int,
                  max_scan_lines: int) -> Tuple[int, List[str]]:
    """前 max_scan_lines 行内定位表头行（锚定列命中数 ≥ header_k）。

    失败抛 :class:`LedgerError`（附尝试过的候选行）。
    """
    anchors = set(registry_header_anchors(platform))
    tried = []
    for idx, line in enumerate(lines[:max_scan_lines]):
        fields = [f.strip() for f in _split_row(line)]
        hit = sum(1 for f in fields if f in anchors)
        if hit >= header_k:
            return idx, fields
        if hit > 0:
            tried.append("第%d行（命中%d列）" % (idx + 1, hit))
    raise LedgerError(
        "表头定位失败（平台 %s，K=%d，扫描上限 %d 行；候选：%s）"
        % (platform, header_k, max_scan_lines, "；".join(tried) or "无")
    )


def _norm_cell(text: str) -> str:
    """列名匹配前的轻量归一：去首尾及内部全部空白。"""
    return "".join(text.split())


def build_column_map(header_fields: Sequence[str], platform: str,
                     column_aliases: Sequence[Mapping]) -> Tuple[Dict[str, int], List[str]]:
    """表头字段 → 规范字段。

    精确层 → 别名层（``column_aliases`` 条目 ``{canonical, variants[], platforms[]}``）；
    未登记列 → unknown 列表（入 issues，不拒行）；同名规范字段取首个命中列。
    """
    canonical_by_column = registry_canonical_columns()
    registered = set(registry_expected_columns(platform))
    alias_lookup: Dict[str, str] = {}
    for entry in column_aliases:
        platforms = entry.get("platforms") or []
        if platforms and platform not in platforms:
            continue
        for variant in entry.get("variants", []):
            alias_lookup.setdefault(_norm_cell(variant), entry["canonical"])

    field_map: Dict[str, int] = {}
    unknown: List[str] = []
    for idx, raw in enumerate(header_fields):
        name = raw.strip()
        if not name:
            continue
        canonical = canonical_by_column.get(name) or alias_lookup.get(_norm_cell(name))
        if canonical is not None:
            field_map.setdefault(canonical, idx)
        elif name not in registered:
            unknown.append(name)
    return field_map, unknown


def require_fields(field_map: Mapping[str, int], source_name: str) -> None:
    """必填字段缺失 → LedgerError（文件级失败，不猜测）。"""
    missing = [f for f in REQUIRED_IR_FIELDS if f not in field_map]
    if missing:
        raise LedgerError("%s：必填列缺失（%s）" % (source_name, "、".join(missing)))


# ---------------------------------------------------------------------------
# 金额 / 时间解析（固定格式严格解析；任何不可解析 → invalid，不猜测）
# ---------------------------------------------------------------------------
def parse_amount_cell(text: Optional[str]) -> Optional[Decimal]:
    """金额单元格 → Decimal（正数）或 None（空/非数值）。

    去千分位与货币符号（半角 ``¥`` 与全角 ``￥`` 都在列——GBK 通道编码不了
    半角形）后必须整体合法。
    """
    text = (text or "").strip()
    if not text:
        return None
    cleaned = text
    for ch in _CURRENCY_CHARS:
        cleaned = cleaned.replace(ch, "")
    cleaned = cleaned.replace(_THOUSANDS_SEP, "").strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return abs(value)


def parse_time(text: Optional[str]) -> Optional[str]:
    """固定格式严格解析；返回规范化字符串或 None（空/不可解析）。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        moment = datetime.strptime(text, _TIME_FORMAT)
    except ValueError:
        return None
    return moment.strftime(_TIME_FORMAT)


def direction_from_text(text: Optional[str]) -> Optional[str]:
    """收支类型列取值 → IR direction；未登记取值返回 None（unknown 行）。"""
    text = (text or "").strip()
    if text == DIRECTION_EXPENSE:
        return DIR_EXPENSE
    if text == DIRECTION_INCOME:
        return DIR_INCOME
    if text == DIRECTION_NEUTRAL:
        return DIR_NEUTRAL
    return None


_CURRENCY_CHARS = "¥￥$"


def _to_plain(value: Decimal) -> str:
    """Decimal → 定点字符串（无科学计数法）。"""
    return format(value, "f")


def _cell(fields: Sequence[str], idx: Optional[int]) -> str:
    if idx is None or idx >= len(fields):
        return ""
    return fields[idx].strip()


def _zip_raw(header_fields: Sequence[str], fields: Sequence[str]) -> Dict[str, Any]:
    """原始行字段（表头名 → 原值）；多余字段记 ``_extra:N``（列数不匹配可审计）。"""
    out: Dict[str, Any] = {}
    for idx, name in enumerate(header_fields):
        out[name] = fields[idx] if idx < len(fields) else None
    for i in range(len(header_fields), len(fields)):
        out["_extra:%d" % i] = fields[i]
    return out


def _index_of(header_fields: Sequence[str], name: str) -> Optional[int]:
    for idx, cell in enumerate(header_fields):
        if cell.strip() == name:
            return idx
    return None


def _parse_direction_column_row(fields, header_fields, field_map):
    """微信/支付宝行：单金额列 + 收支类型列。"""
    raw_fields = _zip_raw(header_fields, fields)
    if len(fields) != len(header_fields):
        return {"status": STATUS_INVALID, "code": CODE_COLUMN_COUNT,
                "detail": "字段数 %d ≠ 表头列数 %d" % (len(fields), len(header_fields)),
                "raw_fields": raw_fields}

    time_text = parse_time(_cell(fields, field_map.get(F_TIME)))
    if time_text is None:
        return {"status": STATUS_INVALID, "code": CODE_TIME_UNPARSEABLE,
                "detail": "时间不可解析（须为 YYYY-MM-DD HH:MM:SS）",
                "raw_fields": raw_fields}

    direction_text = _cell(fields, field_map.get(F_DIRECTION))
    direction = direction_from_text(direction_text)
    if direction is None:
        # 未登记收支取值 → unknown 行（入库 + issues 显式列出）
        return {"status": STATUS_UNKNOWN, "code": CODE_UNMAPPED_DIRECTION,
                "detail": "未登记的收/支取值：%s" % direction_text,
                "time": time_text,
                "amount": _num_or_none(parse_amount_cell(_cell(fields, field_map.get(F_AMOUNT)))),
                "counterparty": _cell(fields, field_map.get(F_COUNTERPARTY)),
                "description": _cell(fields, field_map.get(F_DESCRIPTION)),
                "raw_fields": raw_fields}

    amount_cell = _cell(fields, field_map.get(F_AMOUNT))
    amount = parse_amount_cell(amount_cell)
    if amount is None:
        # 空单元格与"非数值内容"是两个问题码
        code = CODE_AMOUNT_MISSING if not amount_cell.strip() else CODE_AMOUNT_NOT_NUMERIC
        return {"status": STATUS_INVALID, "code": code,
                "detail": "金额为空" if code == CODE_AMOUNT_MISSING
                else "金额非数值：%s" % amount_cell,
                "raw_fields": raw_fields}
    return {"status": STATUS_OK, "time": time_text, "amount": _to_plain(amount),
            "direction": direction,
            "counterparty": _cell(fields, field_map.get(F_COUNTERPARTY)),
            "description": _cell(fields, field_map.get(F_DESCRIPTION)),
            "raw_fields": raw_fields}


def _parse_bank_row(fields, header_fields, field_map):
    """银行行：收支分列（支出金额/收入金额）+ 日期与时分秒分列。"""
    raw_fields = _zip_raw(header_fields, fields)
    if len(fields) != len(header_fields):
        return {"status": STATUS_INVALID, "code": CODE_COLUMN_COUNT,
                "detail": "字段数 %d ≠ 表头列数 %d" % (len(fields), len(header_fields)),
                "raw_fields": raw_fields}

    date_idx = field_map.get(F_TIME)
    hms_idx = _index_of(header_fields, BANK_TIME_COL)
    time_text = parse_time("%s %s" % (_cell(fields, date_idx), _cell(fields, hms_idx)))
    if time_text is None:
        return {"status": STATUS_INVALID, "code": CODE_TIME_UNPARSEABLE,
                "detail": "时间不可解析（日期+时分秒拼接后须为 YYYY-MM-DD HH:MM:SS）",
                "raw_fields": raw_fields}

    expense_cell = _cell(fields, _index_of(header_fields, BANK_EXPENSE_COL))
    income_cell = _cell(fields, _index_of(header_fields, BANK_INCOME_COL))
    expense = parse_amount_cell(expense_cell)
    income = parse_amount_cell(income_cell)
    if expense is not None and income is not None:
        return {"status": STATUS_INVALID, "code": CODE_AMOUNT_AMBIGUOUS,
                "detail": "支出金额与收入金额同时非空",
                "raw_fields": raw_fields}
    direction = None
    amount = None
    if expense is not None:
        direction, amount = DIR_EXPENSE, expense
    elif income is not None:
        direction, amount = DIR_INCOME, income
    else:
        non_empty = expense_cell.strip() or income_cell.strip()
        if non_empty:
            return {"status": STATUS_INVALID, "code": CODE_AMOUNT_NOT_NUMERIC,
                    "detail": "金额非数值：%s" % non_empty,
                    "raw_fields": raw_fields}
        return {"status": STATUS_INVALID, "code": CODE_AMOUNT_MISSING,
                "detail": "支出金额与收入金额均为空",
                "raw_fields": raw_fields}
    return {"status": STATUS_OK, "time": time_text, "amount": _to_plain(amount),
            "direction": direction,
            "counterparty": _cell(fields, field_map.get(F_COUNTERPARTY)),
            "description": _cell(fields, field_map.get(F_DESCRIPTION)),
            "raw_fields": raw_fields}


def _num_or_none(value):
    return None if value is None else _to_plain(value)


# ---------------------------------------------------------------------------
# 归一化（模块②）
# ---------------------------------------------------------------------------
class AliasIndex:
    """冻结别名表的归一化索引（构建一次、纯查询）。

    variants 先过同一归一管线再建索引——保证"表中写法"与"流水写法"
    在同一口径下比较。
    """

    MAX_ALIAS_ENTRIES = 4096

    def __init__(self, aliases_doc: Mapping) -> None:
        suffix_list = aliases_doc.get("suffix_strip", [])
        fullwidth_list = aliases_doc.get("fullwidth_map", [])
        alias_entries = aliases_doc.get("aliases", [])
        if len(alias_entries) > self.MAX_ALIAS_ENTRIES:
            raise InputBad("别名表条目数超上限 %d（疑似配置错误）" % self.MAX_ALIAS_ENTRIES)
        self._suffixes = tuple(sorted((s for s in suffix_list if s), key=len, reverse=True))
        self._fullwidth: Dict[str, str] = {}
        for entry in fullwidth_list:
            full, half = entry.get("full"), entry.get("half")
            if not full or half is None:
                raise InputBad("fullwidth_map 条目缺少 full/half 字段")
            self._fullwidth[full] = half
        self._index: Dict[str, str] = {}
        for entry in alias_entries:
            canonical = entry["canonical"]
            for variant in entry["variants"]:
                norm = self.normalize(variant)[0]
                self._index[norm] = canonical

    def normalize(self, original: str) -> Tuple[str, List[Dict[str, str]]]:
        """原名 → (归一名, actions)；动作序列写死，逐条依据。"""
        actions: List[Dict[str, str]] = []
        value = original

        # 1. 去空白（首尾 + 内部全部移除）
        collapsed = _WHITESPACE_RUN.sub("", value)
        if collapsed != value:
            actions.append({"rule": RULE_WHITESPACE, "detail": "去除空白字符"})
            value = collapsed

        # 2. 全半角统一（映射表驱动）
        if value and any(ch in self._fullwidth for ch in value):
            mapped = "".join(self._fullwidth.get(ch, ch) for ch in value)
            if mapped != value:
                actions.append({"rule": RULE_FULLWIDTH, "detail": "全角转半角"})
                value = mapped

        # 3. 后缀剥离（白名单、最长优先；剥离后非空才生效）
        for suffix in self._suffixes:
            if value.endswith(suffix) and len(value) > len(suffix):
                stripped = value[: -len(suffix)].strip()
                if stripped:
                    actions.append({"rule": RULE_SUFFIX,
                                    "detail": "剥离后缀 %r" % suffix})
                    value = stripped
                    break

        # 4. 别名表命中（variants 归一后索引 → canonical）
        if value in self._index:
            canonical = self._index[value]
            if canonical != value:
                actions.append({"rule": RULE_ALIAS, "detail": "别名归并 → %r" % canonical})
                value = canonical
        return value, actions


# ---------------------------------------------------------------------------
# 去重（模块③）
# ---------------------------------------------------------------------------
def _parse_dt(value: str) -> datetime:
    return datetime.strptime(value, _TIME_FORMAT)


def _cents(amount_text: str) -> int:
    return int((Decimal(amount_text) * 100).to_integral_value())


def _sort_key(record: Mapping, platform_rank: Mapping[str, int]):
    """固定排序：时间 → 平台优先级 → 来源行号。"""
    return (
        _parse_dt(record["time"]),
        platform_rank.get(record["source_platform"], len(platform_rank)),
        record["source_row"],
        record["id"],
    )


def _cluster_direction(records: List[Mapping], window_seconds: int) -> List[List[Mapping]]:
    """单方向内的链式相邻聚类 → 候选簇列表（每簇为排序后的 record 列表）。

    链式相邻：与前一条 Δt ≤ W 就续链（闭区间，恰好 W 命中）。
    """
    clusters: List[List[Mapping]] = []
    current: List[Mapping] = []
    prev_time = None
    for record in records:
        t = _parse_dt(record["time"])
        if current and (t - prev_time).total_seconds() <= window_seconds:
            current.append(record)
        else:
            if current:
                clusters.append(current)
            current = [record]
        prev_time = t
    if current:
        clusters.append(current)
    return clusters


def dedup_ledger(ledger: Mapping, window_seconds: int,
                 platform_priority: Sequence[str]) -> Mapping:
    """归一化后 IR → 追加去重段的视图（原始不可变，只增标记不改写）。

    跨平台前提：三元组命中只记候选簇；簇内 ≥2 平台判重复（非代表笔排除出
    净额）；单平台候选显式不合并，成员照常计入净额。
    """
    if window_seconds < 0:
        raise InputBad("时间窗口不能为负：%r" % window_seconds)
    platform_rank = {name: i for i, name in enumerate(platform_priority)}

    by_key: Dict[Tuple, List[Mapping]] = {}
    order: List[Tuple] = []
    for record in ledger.get("records", []):
        # 方向 None（unknown 行）不参与聚类——语义上"方向未知"无法断言同方向
        direction = record.get("direction")
        amount = record.get("amount")
        if not direction or amount is None:
            continue
        key = (direction, record.get("normalized_counterparty") or "", amount)
        if key not in by_key:
            by_key[key] = []
            order.append(key)
        by_key[key].append(record)

    records = [dict(r) for r in ledger.get("records", [])]
    by_id = {r["id"]: r for r in records}

    clusters: List[Dict[str, Any]] = []
    for key in order:
        direction, counterparty, amount = key
        group = by_key[key]
        group.sort(key=lambda r: _sort_key(r, platform_rank))
        for members in _cluster_direction(group, window_seconds):
            if len(members) < 2:
                continue  # 单条不成簇
            platforms = sorted({m["source_platform"] for m in members})
            verdict = VERDICT_CROSS if len(platforms) >= 2 else VERDICT_SAME
            representative = min(members, key=lambda r: _sort_key(r, platform_rank))
            span = (_parse_dt(members[-1]["time"]) - _parse_dt(members[0]["time"])
                    ).total_seconds()
            cluster = {
                "cluster_id": "D%03d" % (len(clusters) + 1),
                "verdict": verdict,
                "direction": direction,
                "counterparty": counterparty,
                "amount": amount,
                "platforms": platforms,
                "members": [m["id"] for m in members],
                "representative": representative["id"],
                "time_span_seconds": span,
                "note": "" if verdict == VERDICT_CROSS
                        else "同平台候选：不合并，待人工复核（绝不静默合并）",
            }
            clusters.append(cluster)
            for m in members:
                entry = by_id[m["id"]]
                entry["dedup_verdict"] = verdict
                entry["dedup_cluster"] = cluster["cluster_id"]
                entry["is_duplicate"] = (
                    verdict == VERDICT_CROSS and m["id"] != representative["id"]
                )
                entry["is_representative"] = m["id"] == representative["id"]

    excluded = sorted(r["id"] for r in records if r.get("is_duplicate"))

    def _net(direction: str) -> int:
        total = 0
        for r in records:
            if r.get("is_duplicate"):
                continue
            if r.get("direction") == direction and r.get("amount"):
                total += _cents(r["amount"])
        return total

    out = dict(ledger)
    out["records"] = records
    out["dedup"] = {
        "params": {"window_seconds": window_seconds,
                   "platform_priority": list(platform_priority)},
        "clusters": clusters,
        "net_summary": {"excluded_duplicate_ids": excluded,
                        "net_expense_cents": _net(DIR_EXPENSE),
                        "net_income_cents": _net(DIR_INCOME)},
    }
    return out


# ---------------------------------------------------------------------------
# 语义识别（模块④）
# ---------------------------------------------------------------------------
def load_keyword_rules(keywords_doc: Mapping) -> List[Mapping]:
    """关键词表 → 评估序列（priority 升序、同优先级 id 升序；确定性）。"""
    rules: List[Mapping] = []
    for entry in keywords_doc.get("rules", []):
        if not entry.get("keywords"):
            raise InputBad("关键词规则 %s 的 keywords 为空（配置错误）" % entry.get("id"))
        rules.append(entry)
    rules.sort(key=lambda r: (r["priority"], r["id"]))
    return rules


def _direction_ok(condition, direction) -> bool:
    if condition == "any":
        return True
    return direction == condition


def classify_record(record: Mapping, rules: Sequence[Mapping]) -> Dict[str, Any]:
    """单条记录 → 判定 dict（"未知"是一等结论，绝不 fallthrough 为"消费"）。"""
    direction = record.get("direction")
    scope_text = "%s\n%s" % (
        record.get("normalized_counterparty") or record.get("counterparty") or "",
        record.get("description") or "")

    hits: List[Dict[str, Any]] = []
    for rule in rules:
        if not _direction_ok(rule["direction_condition"], direction):
            continue
        for keyword in rule["keywords"]:
            if keyword in scope_text:
                hits.append({
                    "rule_id": rule["id"],
                    "label": rule["label"],
                    "keyword": keyword,
                    "priority": rule["priority"],
                })
                break  # 同一规则内命中任一关键词即可（首个，确定性）

    if hits:
        chosen = hits[0]  # 评估序首个 = 优先级最高
        condition = "?"
        for rule in rules:
            if rule["id"] == chosen["rule_id"]:
                condition = rule["direction_condition"]
                break
        return {
            "label": chosen["label"],
            "rule_id": chosen["rule_id"],
            "matched_keywords": [h["keyword"] for h in hits],
            "all_hits": hits,
            "basis": {
                "rule": "keyword+direction",
                "detail": "命中规则 %s（priority=%d，方向条件=%s）"
                          % (chosen["rule_id"], chosen["priority"], condition),
            },
        }
    detail = ("方向未知，且无规则命中" if direction not in (DIR_EXPENSE, DIR_INCOME, DIR_NEUTRAL)
              else "无规则命中（不得 fallthrough 为消费）")
    return {
        "label": LABEL_UNKNOWN,
        "rule_id": None,
        "matched_keywords": [],
        "all_hits": [],
        "basis": {"rule": "no_match", "detail": detail},
    }


def classify_ledger(ledger: Mapping, keywords_doc: Mapping) -> Mapping:
    """IR（归一化后）→ 追加语义标签段的视图（原始不可变，只增不改）。"""
    rules = load_keyword_rules(keywords_doc)
    records = []
    distribution: Dict[str, int] = {}
    unknown_rows: List[Dict[str, Any]] = []
    for record in ledger.get("records", []):
        new_record = dict(record)
        verdict = classify_record(record, rules)
        new_record["semantic_label"] = verdict["label"]
        new_record["semantic_basis"] = verdict
        records.append(new_record)
        distribution[verdict["label"]] = distribution.get(verdict["label"], 0) + 1
        if verdict["label"] == LABEL_UNKNOWN:
            unknown_rows.append({
                "id": record["id"],
                "direction": record.get("direction"),
                "counterparty": record.get("normalized_counterparty")
                or record.get("counterparty"),
                "description": record.get("description"),
                "amount": record.get("amount"),
                "reason": verdict["basis"]["detail"],
            })

    out = dict(ledger)
    out["records"] = records
    out["classify"] = {
        "distribution": dict(sorted(distribution.items())),
        "unknown_rows": unknown_rows,
        "note": "『未知』是一等结论：主口径不把未知混入消费，也不假装未知不存在",
    }
    return out


# ---------------------------------------------------------------------------
# 订阅识别（模块⑤）
# ---------------------------------------------------------------------------
def _days_floor(seconds: float) -> int:
    """间隔秒数 → 天数（向下取整；不足一天按 0 天计，避免边界误判）。"""
    return int(seconds // DAY_SECONDS)


def _percent_change(old_amount: str, new_amount: str) -> Optional[Decimal]:
    old = Decimal(old_amount)
    new = Decimal(new_amount)
    if old == 0:
        return None
    return abs(new - old) / old * Decimal(100)


def _price_change_hit(old_amount: str, new_amount: str, min_percent) -> bool:
    pct = _percent_change(old_amount, new_amount)
    if pct is None:
        return False
    return pct >= Decimal(str(min_percent))


def _period_bands(period_table, default_tolerance_days: int):
    """周期表 → [(period_id, interval_days, tolerance_days)]。

    周期条目未单独给 tolerance_days 时回落到规则包默认容差。
    """
    bands = []
    for period in period_table:
        tolerance = period.get("tolerance_days", default_tolerance_days)
        bands.append((period["id"], int(period["interval_days"]), int(tolerance)))
    return bands


def _match_period(days: int, bands) -> Optional[Dict[str, int]]:
    """间隔天数命中任一周期容差带 → 该 period 条目；否则 None。"""
    for period_id, interval, tolerance in bands:
        if abs(days - interval) <= tolerance:
            return {"period_id": period_id, "interval_days": interval,
                    "gap_days": days}
    return None


def _chain_gap_limit_days(bands) -> int:
    """链式相邻聚类的续链上限：允许漏一期（2×最长周期 + 容差）。"""
    longest = max(interval + tolerance for _, interval, tolerance in bands)
    return 2 * longest


def _chain_groups(records: List[Mapping], bands) -> List[List[Mapping]]:
    """同商户同金额组内链式相邻聚类（日距 ≤ 漏一期上限即续链）。"""
    limit = _chain_gap_limit_days(bands)
    chains: List[List[Mapping]] = []
    current: List[Mapping] = []
    prev_time = None
    for record in records:
        t = _parse_dt(record["time"])
        if current and (_days_floor((t - prev_time).total_seconds()) <= limit):
            current.append(record)
        else:
            if current:
                chains.append(current)
            current = [record]
        prev_time = t
    if current:
        chains.append(current)
    return chains


def _pair_in_band(days: int, bands):
    """相邻对间隔落单期容差带 → (hit, None)；否则漏期带 → (None, bridge_hit)。"""
    hit = _match_period(days, bands)
    if hit is not None:
        return hit, None
    for period_id, interval, tolerance in bands:
        if abs(days - 2 * interval) <= tolerance:
            return None, {"period_id": period_id, "interval_days": interval,
                          "gap_days": days}
    return None, None


def _anchor_seed(chain: Sequence[Mapping], min_repeats: int, bands):
    """链内首个「连续 min_repeats 期相邻间隔都落带内（允许漏一期）」的窗格。"""
    count = len(chain)
    for start in range(0, count - min_repeats + 1):
        window = chain[start:start + min_repeats]
        first_hit = None
        seed_gaps: List[Dict[str, Any]] = []
        ok = True
        for prev, cur in zip(window, window[1:]):
            days = _days_floor(
                (_parse_dt(cur["time"]) - _parse_dt(prev["time"])).total_seconds()
            )
            hit, bridged = _pair_in_band(days, bands)
            if hit is None and bridged is None:
                ok = False
                break
            if first_hit is None:
                first_hit = hit or bridged
            if bridged is not None:
                seed_gaps.append({
                    "after_entry": prev["id"],
                    "resumed_entry": cur["id"],
                    "missed_intervals": 1,
                    "gap_days": bridged["gap_days"],
                    "period_id": bridged["period_id"],
                })
        if ok:
            return start, start + min_repeats - 1, first_hit, seed_gaps
    return None


def _follow_chain(chain: Sequence[Mapping], seed_start: int, seed_end: int,
                  bands, seed_gaps):
    """种子锚点起逐期续链 → 成员下标序列 + gaps（0 基下标）。"""
    members = list(range(seed_start, seed_end + 1))
    gaps = list(seed_gaps)
    index = seed_end
    while True:
        advanced = False
        base = _parse_dt(chain[index]["time"])
        for j in range(index + 1, len(chain)):
            days = _days_floor((_parse_dt(chain[j]["time"]) - base).total_seconds())
            hit, bridged = _pair_in_band(days, bands)
            if hit is None and bridged is None:
                continue
            members.append(j)
            if bridged is not None:
                gaps.append({
                    "after_entry": chain[index]["id"],
                    "resumed_entry": chain[j]["id"],
                    "missed_intervals": 1,
                    "gap_days": bridged["gap_days"],
                    "period_id": bridged["period_id"],
                })
            index = j
            advanced = True
            break
        if not advanced:
            break
    return members, gaps


def _price_changes(chain: Sequence[Mapping], members: Sequence[int],
                   min_percent, bands) -> List[Dict[str, Any]]:
    """相邻期对中观测到的金额变动（间隔落单期带内才算期对；≥阈值记变动）。"""
    changes: List[Dict[str, Any]] = []
    for prev_idx, cur_idx in zip(members, members[1:]):
        prev = chain[prev_idx]
        cur = chain[cur_idx]
        if prev["amount"] == cur["amount"]:
            continue
        days = _days_floor(
            (_parse_dt(cur["time"]) - _parse_dt(prev["time"])).total_seconds()
        )
        # 只有单期间隔才算"相邻期对"——漏期补链对（≈2×interval）不是期对
        if _match_period(days, bands) is None:
            continue
        if _price_change_hit(prev["amount"], cur["amount"], min_percent):
            changes.append({
                "entry": cur["id"],
                "from_amount": prev["amount"],
                "to_amount": cur["amount"],
                "from_time": prev["time"],
                "to_time": cur["time"],
                "change_percent": str(_percent_change(prev["amount"], cur["amount"])),
            })
    return changes


def _merge_price_chains(chains_data, min_repeats: int, min_percent, bands):
    """涨价续链：A 链尾笔与 B 链首笔同商户、金额变化 ≥ 阈值、间隔落单期带内。

    B 允许是未锚定链（涨价后的新金额链天然只有 1-2 笔）：只能被锚定链收编。
    """
    changed = True
    while changed:
        changed = False
        for i in range(len(chains_data)):
            if changed:
                break
            a = chains_data[i]
            if not a["members"]:
                continue
            tail = a["chain"][a["members"][-1]]
            for j in range(len(chains_data)):
                if j == i:
                    continue
                b = chains_data[j]
                if not b["chain"]:
                    continue
                head = b["chain"][0]
                if head["amount"] == tail["amount"]:
                    continue
                days = _days_floor(
                    (_parse_dt(head["time"]) - _parse_dt(tail["time"])).total_seconds()
                )
                if _match_period(days, bands) is None:
                    continue
                if not _price_change_hit(tail["amount"], head["amount"], min_percent):
                    continue
                seen_ids = set()
                union: List[Mapping] = []
                for record in sorted(a["chain"] + b["chain"],
                                     key=lambda r: (_parse_dt(r["time"]), r["id"])):
                    if record["id"] in seen_ids:
                        continue
                    seen_ids.add(record["id"])
                    union.append(record)
                seed = _anchor_seed(union, min_repeats, bands)
                prior_gaps = a["gaps"] + b["gaps"]
                if seed is not None:
                    s, e, seed_hit, sg = seed
                    members, gaps = _follow_chain(union, s, e, bands, sg)
                    have = {g["resumed_entry"] for g in prior_gaps}
                    gaps = prior_gaps + [g for g in gaps
                                         if g["resumed_entry"] not in have]
                    period_hit = seed_hit
                else:
                    # 锚定退化（并集跨漏期窗过宽）：保留全部并集成员，周期沿用前段
                    members = list(range(len(union)))
                    gaps = prior_gaps
                    period_hit = a["period_hit"]
                chains_data[i] = {
                    "chain": union,
                    "members": members,
                    "gaps": gaps,
                    "period_hit": period_hit,
                    "gapped_head": False,
                }
                del chains_data[j]
                changed = True
                break
    return chains_data


def detect_subscriptions(ledger: Mapping, min_repeats: int,
                         price_change_min_percent, period_table,
                         default_tolerance_days: int):
    """classified ledger → 订阅清单 + 干扰行清单（纯函数，不改输入）。"""
    bands = _period_bands(period_table, default_tolerance_days)

    candidates: List[Mapping] = []
    for record in ledger.get("records", []):
        if record.get("semantic_label") != "消费":
            continue
        if record.get("direction") != DIR_EXPENSE:
            continue
        amount = record.get("amount")
        if not amount:
            continue
        try:
            Decimal(amount)
        except (InvalidOperation, ValueError):
            continue
        candidates.append(record)

    by_merchant: Dict[str, List[Mapping]] = {}
    for record in candidates:
        merchant = (record.get("normalized_counterparty")
                    or record.get("counterparty") or "")
        by_merchant.setdefault(merchant, []).append(record)

    subscriptions: List[Dict[str, Any]] = []
    distractor_ids: List[str] = []
    for merchant in sorted(by_merchant):
        group = sorted(by_merchant[merchant],
                       key=lambda r: (_parse_dt(r["time"]), r["id"]))
        merchant_chains = _chain_groups(group, bands)

        chains_data: List[Dict[str, Any]] = []
        for chain in merchant_chains:
            for amount in sorted({r["amount"] for r in chain}):
                sub_chain = [r for r in chain if r["amount"] == amount]
                seed = _anchor_seed(sub_chain, min_repeats, bands)
                if seed is None:
                    # 未锚定子链保留进池：可能被锚定链尾的涨价合并收编
                    chains_data.append({
                        "chain": sub_chain, "members": [], "gaps": [],
                        "period_hit": None, "gapped_head": False,
                    })
                    continue
                seed_start, seed_end, first_hit, seed_gaps = seed
                members, gaps = _follow_chain(sub_chain, seed_start, seed_end,
                                              bands, seed_gaps)
                chains_data.append({
                    "chain": sub_chain,
                    "members": members,
                    "gaps": gaps,
                    "period_hit": first_hit,
                    "gapped_head": False,
                })

        chains_data = _merge_price_chains(chains_data, min_repeats,
                                          price_change_min_percent, bands)

        for item in chains_data:
            if not item["members"]:
                distractor_ids.extend(r["id"] for r in item["chain"])
                continue
            chain = item["chain"]
            members = item["members"]
            changes = _price_changes(chain, members,
                                     price_change_min_percent, bands)
            entries = [chain[i]["id"] for i in members]
            subscriptions.append({
                "merchant": merchant,
                "amounts": sorted({chain[i]["amount"] for i in members}),
                "period_id": item["period_hit"]["period_id"],
                "repeats": len(members),
                "entries": entries,
                "gaps": item["gaps"],
                "price_changes": changes,
                "first_time": chain[members[0]]["time"],
                "last_time": chain[members[-1]]["time"],
            })

    subscriptions.sort(key=lambda s: (s["merchant"], s["first_time"]))
    for i, sub in enumerate(subscriptions, start=1):
        sub["subscription_id"] = "SUB%03d" % i

    subscribed = {entry for sub in subscriptions for entry in sub["entries"]}
    distractors = []
    for record in candidates:
        if record["id"] not in subscribed:
            distractors.append({
                "id": record["id"],
                "merchant": (record.get("normalized_counterparty")
                             or record.get("counterparty") or ""),
                "amount": record["amount"],
                "time": record["time"],
            })
    distractors.sort(key=lambda d: d["id"])
    return subscriptions, distractors


def detect_subscription_ledger(ledger: Mapping, min_repeats: int,
                               price_change_min_percent, period_table,
                               default_tolerance_days: int) -> Mapping:
    """IR（classify 后）→ 追加订阅段的视图（原始不可变，只增不改）。"""
    subscriptions, distractors = detect_subscriptions(
        ledger,
        min_repeats=min_repeats,
        price_change_min_percent=price_change_min_percent,
        period_table=period_table,
        default_tolerance_days=default_tolerance_days,
    )
    records = [dict(r) for r in ledger.get("records", [])]
    by_id = {r["id"]: r for r in records}
    for sub in subscriptions:
        for entry in sub["entries"]:
            by_id[entry]["subscription_id"] = sub["subscription_id"]

    out = dict(ledger)
    out["records"] = records
    out["subscription"] = {
        "params": {"min_repeats": min_repeats,
                   "price_change_min_percent": price_change_min_percent,
                   "period_table": period_table,
                   "default_tolerance_days": default_tolerance_days},
        "subscriptions": subscriptions,
        "distractors": distractors,
        "note": "只对语义=消费的支出行判定；涨价只记录观测到的变动，不做预测",
    }
    return out


# ---------------------------------------------------------------------------
# 全链编排（表头定位 → 行三态 → 归一化 → 去重 → 语义 → 订阅）
# ---------------------------------------------------------------------------
def run_ledger(subject: Mapping, params: Mapping, aliases_doc: Mapping,
               keywords_doc: Mapping) -> Mapping:
    """subject（已解码文件行）→ 全链 IR 判定结果（含各段视图）。"""
    validate_subject(subject)
    column_aliases = aliases_doc.get("column_aliases", [])
    header_k = params.get("header_locate_k")
    max_scan = params.get("header_locate_max_scan_lines")

    meta_sources: List[Dict[str, Any]] = []
    all_records: List[Dict[str, Any]] = []
    all_issues: List[Dict[str, Any]] = []
    all_file_issues: List[Dict[str, Any]] = []

    for name in sorted(subject["files"]):
        doc = subject["files"][name]
        encoding = doc.get("encoding")
        if encoding not in ("wechat", "alipay", "bank") and encoding not in (
                "csv", "tsv", "xlsx", "utf-8", "utf-8-sig", "utf-16", "gb18030",
                "gbk", "gb2312"):
            all_file_issues.append({"file": name, "code": CODE_UNKNOWN_PLATFORM,
                                    "detail": "文件名需以 wechat-/alipay-/bank- 前缀开头"})
            continue
        platform = None
        lowered = name.lower()
        for candidate in ("wechat", "alipay", "bank"):
            if lowered.startswith(candidate + "-") or lowered.startswith(candidate + "_"):
                platform = candidate
                break
        if platform is None:
            all_file_issues.append({"file": name, "code": CODE_UNKNOWN_PLATFORM,
                                    "detail": "无法识别平台（文件名需以 wechat-/alipay-/bank- 前缀开头）"})
            continue

        if doc.get("encoding") == "xlsx":
            rows = doc.get("table") or []
            lines = ["\t".join("" if cell is None else str(cell) for cell in row)
                     for row in rows]
        else:
            lines = list(doc.get("lines") or [])
            while lines and lines[-1] == "":
                lines.pop()

        if not lines:
            all_file_issues.append({"file": name, "code": CODE_EMPTY_FILE,
                                    "detail": "空文件（无任何内容）"})
            continue

        try:
            header_idx, header_fields = locate_header(lines, platform, header_k, max_scan)
        except LedgerError as exc:
            all_file_issues.append({"file": name, "code": CODE_HEADER_NOT_FOUND,
                                    "detail": str(exc)})
            continue
        field_map, unknown_columns = build_column_map(header_fields, platform, column_aliases)
        try:
            require_fields(field_map, name)
        except LedgerError as exc:
            all_file_issues.append({"file": name, "code": CODE_REQUIRED_COLUMN_MISSING,
                                    "detail": str(exc)})
            continue

        for column_name in unknown_columns:
            all_issues.append({
                "source_file": name,
                "row_id": None,
                "kind": "unknown",
                "code": CODE_UNKNOWN_COLUMN,
                "column": column_name,
                "detail": "未登记列名：%s（该列不入规范字段，原值保留在 raw_fields）" % column_name,
            })

        parser = _parse_bank_row if platform == "bank" else _parse_direction_column_row
        rows_ok = rows_invalid = rows_unknown = 0
        for offset, line in enumerate(lines[header_idx + 1:], start=header_idx + 2):
            lineno = offset  # 物理行号（1-based，含表头与广告行）
            if line == "":
                continue
            fields = _split_row(line)
            parsed = parser(fields, header_fields, field_map)
            row_id = "%s#%d" % (name, lineno)
            if parsed["status"] == STATUS_INVALID:
                rows_invalid += 1
                all_issues.append({
                    "source_file": name,
                    "row_id": row_id,
                    "kind": "invalid",
                    "code": parsed["code"],
                    "detail": parsed["detail"],
                })
                continue
            if parsed["status"] == STATUS_UNKNOWN:
                rows_unknown += 1
                all_issues.append({
                    "source_file": name,
                    "row_id": row_id,
                    "kind": "unknown",
                    "code": parsed["code"],
                    "detail": parsed["detail"],
                })
            else:
                rows_ok += 1
            all_records.append({
                "id": row_id,
                "source_platform": platform,
                "source_file": name,
                "source_row": lineno,
                "time": parsed.get("time"),
                "amount": parsed.get("amount"),
                "direction": parsed.get("direction"),
                "counterparty": parsed.get("counterparty"),
                "description": parsed.get("description"),
                "raw_fields": parsed.get("raw_fields"),
                "row_status": parsed["status"],
            })

        meta_sources.append({
            "file": name,
            "platform": platform,
            "encoding": doc.get("encoding"),
            "header_skipped_lines": header_idx,
            "rows_total": rows_ok + rows_invalid + rows_unknown,
            "rows_ok": rows_ok,
            "rows_invalid": rows_invalid,
            "rows_unknown": rows_unknown,
        })

    # 排序确定性：records 按 (source_file, source_row)；issues 按 (file, row, code)
    all_records.sort(key=lambda r: (r["source_file"], r["source_row"]))
    all_issues.sort(key=lambda i: (i["source_file"], str(i["row_id"]), i["code"],
                                   i.get("column") or "", i["detail"]))

    ledger: Dict[str, Any] = {
        "schema_version": 1,
        "meta": {"sources": meta_sources},
        "records": all_records,
        "issues": all_issues,
        "file_issues": all_file_issues,
    }

    ledger = normalize_ledger(ledger, aliases_doc)
    ledger = dedup_ledger(
        ledger,
        window_seconds=params.get("dedup_window_seconds"),
        platform_priority=params.get("platform_priority"),
    )
    ledger = classify_ledger(ledger, keywords_doc)
    ledger = detect_subscription_ledger(
        ledger,
        min_repeats=params.get("subscription_min_repeats"),
        price_change_min_percent=params.get("price_change_min_percent"),
        period_table=params.get("period_table"),
        default_tolerance_days=params.get("subscription_interval_tolerance_days"),
    )
    ledger["net"] = {
        "net_expense_cents": ledger["dedup"]["net_summary"]["net_expense_cents"],
        "net_income_cents": ledger["dedup"]["net_summary"]["net_income_cents"],
        "excluded_duplicate_ids": ledger["dedup"]["net_summary"]["excluded_duplicate_ids"],
        "unknown_amount_cents": sum(
            _cents(row["amount"]) for row in ledger["classify"]["unknown_rows"]
            if row.get("amount")
        ),
    }
    return ledger


def normalize_ledger(ledger: Mapping, aliases_doc: Mapping) -> Mapping:
    """IR ledger → 追加归一化段的视图（原始不可变：只增不改）。"""
    index = AliasIndex(aliases_doc)
    records = []
    journal: Dict[str, Dict[str, Any]] = {}
    journal_order: List[str] = []
    for record in ledger.get("records", []):
        new_record = dict(record)
        original = record.get("counterparty") or ""
        if original:
            normalized, actions = index.normalize(original)
        else:
            normalized, actions = original, []
        new_record["normalized_counterparty"] = normalized
        new_record["normalize_actions"] = actions
        records.append(new_record)
        if original and original not in journal:
            journal[original] = {
                "original": original,
                "normalized": normalized,
                "actions": actions,
                "changed": bool(actions),
            }
            journal_order.append(original)

    out = dict(ledger)
    out["records"] = records
    out["normalize"] = {
        "order": journal_order,
        "entries": [journal[name] for name in journal_order],
    }
    return out


def registry_header_anchors(platform: str) -> Sequence[str]:
    from . import registry
    return registry.HEADER_ANCHORS[platform]


def registry_expected_columns(platform: str) -> Sequence[str]:
    from . import registry
    return registry.EXPECTED_COLUMNS[platform]


def registry_canonical_columns() -> Mapping[str, str]:
    from . import registry
    return registry.CANONICAL_BY_COLUMN
