"""发票台账判定内核（迁自来源八规则；零文件 IO / 零时钟 / 零环境变量）。

规则族（注册顺序 = 执行顺序；DUP-03 门控依赖 DUP-01/02 已命中集）：

============================  ==========  ==========================================
器官规则族                     来源规则     语义
============================  ==========  ==========================================
``duplicate.exact``           R-DUP-01    同号多卡或号码已存在台账
``duplicate.joint``           R-DUP-02    号码+价税合计+开票日期相同、批次不同且非纯复制
``duplicate.fuzzy``           R-DUP-03    同销售方 ±N 天内价税合计相同的不同号票（门控互斥）
``series``                    R-SEQ-01    同销售方号码后缀连续 ≥N 张且日期跨度在窗口内
``arithmetic.total``          R-ARITH-01  明细聚合 + 金额+税额=价税合计（容差内）
``arithmetic.cn``             R-ARITH-02  大写金额与小写价税合计互核
``time.future``               R-TIME-01   开票日期晚于批次报销基准日
``time.stale``                R-TIME-02   开票日期早于基准月超过 N 期（仅追溯方向）
============================  ==========  ==========================================

级别语义（来源定稿）：``error`` = 确认异常（确定性算术/键冲突）；``suspicious`` =
疑似（模糊/簇类启发）；``review`` = 待人工确认（低置信度、跨期临界）。
判定账本映射见 ``__init__``：只有 ``error`` 落 ``fail``（阻断），疑似/待人工记
``not_applicable`` 并保留级别证据——「疑似≠确认」。

时间基准全部来自输入（``anchors.default`` / ``anchors.batches``），本模块不读时钟。
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .cn_amount import encode_amount
from .model import InvoiceCard

LEVELS = ("error", "suspicious", "review")

#: 规则族（注册顺序 = 执行顺序）
RULE_ORDER: Tuple[str, ...] = (
    "duplicate.exact",
    "duplicate.joint",
    "duplicate.fuzzy",
    "series",
    "arithmetic.total",
    "arithmetic.cn",
    "time.future",
    "time.stale",
)

#: 规则族 → 来源规则代码（evidence 留痕；判定账本 rule_id 用器官词汇）
RULE_CODES = {
    "duplicate.exact": "R-DUP-01",
    "duplicate.joint": "R-DUP-02",
    "duplicate.fuzzy": "R-DUP-03",
    "series": "R-SEQ-01",
    "arithmetic.total": "R-ARITH-01",
    "arithmetic.cn": "R-ARITH-02",
    "time.future": "R-TIME-01",
    "time.stale": "R-TIME-02",
}

#: 参数缺省（与来源一致；参数是**用户输入**，不是政策数值）
DEFAULT_PARAMS = {
    "arith_tolerance": "0.01",
    "dup_date_window_days": 1,
    "dup_amount_tol": "0.00",
    "seq_suffix_len": 8,
    "seq_min_len": 3,
    "seq_date_window_days": 7,
    "time_n_period": 3,
}

#: 纯复制件判定不参与比较的字段（解析层自由度 + 入库时填充项）
_NON_SEMANTIC_FIELDS = frozenset(
    ("batch_id", "confidence", "field_flags", "evidence")
)


@dataclass(frozen=True)
class Hit:
    """一条规则命中（判定账本前的内部形态）。"""

    family: str
    level: str
    numbers: Tuple[str, ...]
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    suffix: str = ""


@dataclass(frozen=True)
class RuleResult:
    """单规则执行结果：命中集 + 因缺字段跳过的卡数。"""

    hits: Tuple[Hit, ...] = ()
    skipped: int = 0


@dataclass(frozen=True)
class Context:
    """一次判定所需的全部输入（已校验，不再触碰外部）。"""

    cards: Tuple[InvoiceCard, ...]
    default_anchor: date
    batch_anchors: Mapping[str, date]
    existing_numbers: frozenset
    params: Mapping[str, Any]

    def anchor_of(self, card: InvoiceCard) -> date:
        return self.batch_anchors.get(card.batch_id, self.default_anchor)


# ------------------------------------------------------------------ 输入校验
def _as_int(name: str, value: Any, minimum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("参数 %s 必须是整数：%r" % (name, value)) from exc
    if isinstance(value, bool) or number < minimum:
        raise ValueError("参数 %s 须 ≥ %d：%r" % (name, minimum, value))
    return number


def _as_decimal(name: str, value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("参数 %s 必须是数值：%r" % (name, value)) from exc
    if not number.is_finite() or number < 0:
        raise ValueError("参数 %s 须为非负有限数值：%r" % (name, value))
    return number


def parse_params(raw: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """校验并归一化判定参数；未知键即输入不合法（防拼写漂移静默取默认）。"""
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ValueError("params 必须是 JSON 对象")
    unknown = sorted(set(raw) - set(DEFAULT_PARAMS))
    if unknown:
        raise ValueError("params 含未知参数：%s" % ", ".join(unknown))
    merged = dict(DEFAULT_PARAMS)
    merged.update(raw)
    return {
        "arith_tolerance": _as_decimal("arith_tolerance", merged["arith_tolerance"]),
        "dup_date_window_days": _as_int(
            "dup_date_window_days", merged["dup_date_window_days"], 0),
        "dup_amount_tol": _as_decimal("dup_amount_tol", merged["dup_amount_tol"]),
        "seq_suffix_len": _as_int("seq_suffix_len", merged["seq_suffix_len"], 1),
        "seq_min_len": _as_int("seq_min_len", merged["seq_min_len"], 1),
        "seq_date_window_days": _as_int(
            "seq_date_window_days", merged["seq_date_window_days"], 0),
        "time_n_period": _as_int("time_n_period", merged["time_n_period"], 0),
    }


def _parse_day(value: Any, label: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s 必须是 ISO 日期字符串（YYYY-MM-DD）" % label)
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("%s 不是合法日期：%r" % (label, value)) from exc


def parse_anchors(raw: Any) -> Tuple[date, Dict[str, date]]:
    """解析时间基准：``{"default": "YYYY-MM-DD", "batches": {...}}``。

    器官不读时钟，故 ``default`` 必填（来源的「导入时刻」兜底留输入层）。
    """
    if not isinstance(raw, Mapping):
        raise ValueError("anchors 必须是 JSON 对象")
    unknown = sorted(set(raw) - {"default", "batches"})
    if unknown:
        raise ValueError("anchors 含未知字段：%s" % ", ".join(unknown))
    if "default" not in raw:
        raise ValueError("anchors.default 必填（器官不读时钟）")
    default = _parse_day(raw["default"], "anchors.default")
    raw_batches = raw.get("batches") or {}
    if not isinstance(raw_batches, Mapping):
        raise ValueError("anchors.batches 必须是 JSON 对象")
    batches = {
        str(key): _parse_day(value, "anchors.batches.%s" % key)
        for key, value in raw_batches.items()
    }
    return default, batches


def parse_existing_numbers(raw: Any) -> frozenset:
    if raw is None:
        return frozenset()
    if not isinstance(raw, list):
        raise ValueError("existing_numbers 必须是字符串数组")
    numbers = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("existing_numbers 只接受非空字符串：%r" % (item,))
        numbers.append(item.strip())
    return frozenset(numbers)


def parse_cards(raw: Any) -> Tuple[InvoiceCard, ...]:
    if not isinstance(raw, list):
        raise ValueError("cards 必须是发票卡数组")
    if not raw:
        raise ValueError("cards 为空：无可判定对象（与来源「目录内无可解析文件」同义）")
    return tuple(InvoiceCard.from_dict(item) for item in raw)


def build_context(subject: Mapping[str, Any]) -> Context:
    """把所有输入校验集中在一处；任何不合规 → ``ValueError``（退出码 2）。"""
    if not isinstance(subject, Mapping):
        raise ValueError("输入必须是 JSON 对象")
    default_anchor, batch_anchors = parse_anchors(subject.get("anchors"))
    return Context(
        cards=parse_cards(subject.get("cards")),
        default_anchor=default_anchor,
        batch_anchors=batch_anchors,
        existing_numbers=parse_existing_numbers(subject.get("existing_numbers")),
        params=parse_params(subject.get("params")),
    )


# ------------------------------------------------------------------ 工具
def _to_decimal(text: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(text))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _as_date(text: Any) -> Optional[date]:
    if not isinstance(text, str) or not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _semantic_dict(card: InvoiceCard) -> Dict[str, Any]:
    payload = card.to_dict()
    return {key: value for key, value in payload.items()
            if key not in _NON_SEMANTIC_FIELDS}


def _hit_numbers(hits: Iterable[Hit], families: Tuple[str, ...]) -> frozenset:
    numbers = set()
    for hit in hits:
        if hit.family in families:
            numbers.update(hit.numbers)
    return frozenset(numbers)


# ------------------------------------------------------------------ 八规则
def check_duplicate_exact(ctx: Context) -> RuleResult:
    """R-DUP-01 精确重复：同号多卡（含被拒副本）或号码已存在台账。"""
    groups: Dict[str, List[InvoiceCard]] = {}
    for card in ctx.cards:
        groups.setdefault(card.invoice_number, []).append(card)
    hits = []
    for number in sorted(groups):
        members = groups[number]
        pre_existing = number in ctx.existing_numbers
        if len(members) < 2 and not pre_existing:
            continue
        hits.append(Hit(
            family="duplicate.exact",
            level="error",
            numbers=(number,),
            message="发票号码重复：%s出现 %d 次%s，疑似重复报销"
                    % ("台账已有记录且本次" if pre_existing else "本次导入中",
                       len(members),
                       "（台账既有号码）" if pre_existing else ""),
            evidence={
                "occurrences": len(members),
                "batches": sorted({m.batch_id for m in members}),
                "pre_existing_in_ledger": pre_existing,
            },
        ))
    return RuleResult(tuple(hits))


def check_duplicate_joint(ctx: Context) -> RuleResult:
    """R-DUP-02 联合键重复：同号+同价税合计+同开票日期、跨批次且非纯复制件。"""
    groups: Dict[str, List[InvoiceCard]] = {}
    for card in ctx.cards:
        groups.setdefault(card.invoice_number, []).append(card)
    hits = []
    for number in sorted(groups):
        members = groups[number]
        pairs = []
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                first, second = members[i], members[j]
                if first.batch_id == second.batch_id:
                    continue
                if not (first.total_with_tax == second.total_with_tax
                        and first.issue_date == second.issue_date):
                    continue
                if _semantic_dict(first) == _semantic_dict(second):
                    continue
                pairs.append({
                    "batches": sorted([first.batch_id, second.batch_id]),
                    "total_with_tax": first.total_with_tax,
                    "issue_date": first.issue_date,
                })
        if pairs:
            hits.append(Hit(
                family="duplicate.joint",
                level="error",
                numbers=(number,),
                message="联合键重复（号码+价税合计+开票日期相同、批次不同且内容有差异），"
                        "疑似跨批次再制票",
                evidence={"pairs": pairs},
            ))
    return RuleResult(tuple(hits))


def check_duplicate_fuzzy(ctx: Context, prior: Iterable[Hit]) -> RuleResult:
    """R-DUP-03 模糊重复：同销售方 ±N 日内金额相等的不同号票（门控互斥）。"""
    window_days = ctx.params["dup_date_window_days"]
    amount_tol = ctx.params["dup_amount_tol"]
    gated = _hit_numbers(prior, ("duplicate.exact", "duplicate.joint"))
    dated = []
    skipped = 0
    for card in ctx.cards:
        if not card.seller_tax_id or card.invoice_number in gated:
            if not card.seller_tax_id and card.invoice_number not in gated:
                skipped += 1
            continue
        day = _as_date(card.issue_date)
        total = _to_decimal(card.total_with_tax)
        if day is None or total is None:
            skipped += 1
            continue
        dated.append((card, day, total))
    hits = []
    for i in range(len(dated)):
        for j in range(i + 1, len(dated)):
            first_card, first_day, first_total = dated[i]
            second_card, second_day, second_total = dated[j]
            if first_card.invoice_number == second_card.invoice_number:
                continue
            if first_card.seller_tax_id != second_card.seller_tax_id:
                continue
            if abs((first_day - second_day).days) > window_days:
                continue
            if abs(first_total - second_total) > amount_tol:
                continue
            numbers = tuple(sorted([first_card.invoice_number,
                                    second_card.invoice_number]))
            hits.append(Hit(
                family="duplicate.fuzzy",
                level="suspicious",
                numbers=numbers,
                message="同销售方 %s 在 %d 天内出现价税合计相同的不同发票，疑似近似重复报销"
                        % (first_card.seller_name or first_card.seller_tax_id,
                           window_days),
                evidence={
                    "seller_tax_id": first_card.seller_tax_id,
                    "amount": first_card.total_with_tax,
                    "issue_dates": sorted([first_card.issue_date,
                                           second_card.issue_date]),
                    "batches": sorted([first_card.batch_id, second_card.batch_id]),
                },
            ))
    return RuleResult(tuple(hits), skipped)


def check_series(ctx: Context) -> RuleResult:
    """R-SEQ-01 连号拆分簇：同销售方号码后缀连续 ≥N 张且日期跨度在窗口内。"""
    suffix_len = ctx.params["seq_suffix_len"]
    min_len = ctx.params["seq_min_len"]
    window_days = ctx.params["seq_date_window_days"]
    groups: Dict[str, List[Tuple[int, str, date, InvoiceCard]]] = {}
    skipped = 0
    for card in ctx.cards:
        if not card.seller_tax_id or len(card.invoice_number) <= suffix_len:
            skipped += 1
            continue
        suffix_text = card.invoice_number[-suffix_len:]
        if not suffix_text.isdigit():
            skipped += 1
            continue
        day = _as_date(card.issue_date)
        if day is None:
            skipped += 1
            continue
        prefix = card.invoice_number[:-suffix_len]
        groups.setdefault(card.seller_tax_id, []).append(
            (int(suffix_text), prefix, day, card))
    hits = []
    for seller_tax_id, members in sorted(groups.items()):
        members.sort(key=lambda m: (m[0], m[2], m[3].invoice_number))
        run: List[Tuple[int, str, date, InvoiceCard]] = []
        stretches: List[List[Tuple[int, str, date, InvoiceCard]]] = []
        for member in members:
            if run and member[0] == run[-1][0] + 1:
                run.append(member)
            else:
                if len(run) >= 2:
                    stretches.append(run)
                run = [member]
        if len(run) >= 2:
            stretches.append(run)
        for stretch in stretches:
            if len(stretch) < min_len:
                continue
            prefixes = {m[1] for m in stretch}
            if len(prefixes) > 1:
                continue
            span = (max(m[2] for m in stretch) - min(m[2] for m in stretch)).days
            if span > window_days:
                continue
            numbers = tuple(sorted(m[3].invoice_number for m in stretch))
            hits.append(Hit(
                family="series",
                level="suspicious",
                numbers=numbers,
                message="同销售方 %s 的 %d 张发票号码连续（日期跨度 %d 天），疑似连号拆分报销"
                        % (stretch[0][3].seller_name or seller_tax_id,
                           len(stretch), span),
                evidence={
                    "seller_tax_id": seller_tax_id,
                    "count": len(stretch),
                    "date_span_days": span,
                    "batches": sorted({m[3].batch_id for m in stretch}),
                },
            ))
    return RuleResult(tuple(hits), skipped)


def check_arithmetic_total(ctx: Context) -> RuleResult:
    """R-ARITH-01 价税合计复核：明细聚合 + 金额+税额=价税合计（容差内）。"""
    tolerance = ctx.params["arith_tolerance"]
    hits = []
    skipped = 0
    for card in ctx.cards:
        if not (card.amount and card.tax_amount and card.total_with_tax):
            skipped += 1
            continue
        amount = _to_decimal(card.amount)
        tax = _to_decimal(card.tax_amount)
        total = _to_decimal(card.total_with_tax)
        if amount is None or tax is None or total is None:
            hits.append(Hit(
                family="arithmetic.total",
                level="review",
                numbers=(card.invoice_number,),
                message="金额字段无法解析为数值，待人工确认（不硬判）",
                evidence={
                    "check": "unparseable",
                    "amount": card.amount,
                    "tax_amount": card.tax_amount,
                    "total_with_tax": card.total_with_tax,
                },
                suffix="unparseable",
            ))
            continue
        if card.items:
            item_amounts = [_to_decimal(item.amount) for item in card.items]
            item_taxes = [_to_decimal(item.tax_amount) for item in card.items]
            if all(value is not None for value in item_amounts + item_taxes):
                sum_amount = sum(item_amounts, Decimal("0"))
                sum_tax = sum(item_taxes, Decimal("0"))
                if (abs(sum_amount - amount) > tolerance
                        or abs(sum_tax - tax) > tolerance):
                    hits.append(Hit(
                        family="arithmetic.total",
                        level="error",
                        numbers=(card.invoice_number,),
                        message="明细聚合不符：Σ明细金额/Σ明细税额 与合计金额/合计税额不一致",
                        evidence={
                            "check": "sum",
                            "items_amount_sum": str(sum_amount),
                            "items_tax_sum": str(sum_tax),
                            "amount": card.amount,
                            "tax_amount": card.tax_amount,
                        },
                        suffix="sum",
                    ))
        if abs((amount + tax) - total) > tolerance:
            hits.append(Hit(
                family="arithmetic.total",
                level="error",
                numbers=(card.invoice_number,),
                message="票面算术不符：金额 %s + 税额 %s ≠ 价税合计 %s"
                        % (card.amount, card.tax_amount, card.total_with_tax),
                evidence={
                    "check": "total",
                    "amount": card.amount,
                    "tax_amount": card.tax_amount,
                    "total_with_tax": card.total_with_tax,
                    "expect_total": str(amount + tax),
                },
                suffix="total",
            ))
    return RuleResult(tuple(hits), skipped)


def check_arithmetic_cn(ctx: Context) -> RuleResult:
    """R-ARITH-02 大写金额一致：大写与小写价税合计互核。"""
    hits = []
    skipped = 0
    for card in ctx.cards:
        if not (card.total_with_tax and card.total_with_tax_cn):
            skipped += 1
            continue
        try:
            expected_cn = encode_amount(card.total_with_tax)
        except ValueError:
            hits.append(Hit(
                family="arithmetic.cn",
                level="review",
                numbers=(card.invoice_number,),
                message="价税合计不可解析，大写金额无法自动复核，待人工确认（不硬判）",
                evidence={
                    "total_with_tax": card.total_with_tax,
                    "total_with_tax_cn": card.total_with_tax_cn,
                },
                suffix="unparseable",
            ))
            continue
        if card.total_with_tax_cn.strip() != expected_cn:
            hits.append(Hit(
                family="arithmetic.cn",
                level="error",
                numbers=(card.invoice_number,),
                message="大写金额与小写价税合计不符：大写 %s，按小写 %s 应为 %s"
                        % (card.total_with_tax_cn, card.total_with_tax, expected_cn),
                evidence={
                    "total_with_tax": card.total_with_tax,
                    "total_with_tax_cn": card.total_with_tax_cn,
                    "expect_cn": expected_cn,
                },
            ))
    return RuleResult(tuple(hits), skipped)


def check_time_future(ctx: Context) -> RuleResult:
    """R-TIME-01 开票晚于批次报销基准日。"""
    hits = []
    skipped = 0
    for card in ctx.cards:
        if not card.issue_date:
            skipped += 1
            continue
        issue = _as_date(card.issue_date)
        if issue is None:
            skipped += 1
            continue
        anchor = ctx.anchor_of(card)
        if issue <= anchor:
            continue
        hits.append(Hit(
            family="time.future",
            level="error",
            numbers=(card.invoice_number,),
            message="开票日期 %s 晚于批次 %s 报销基准日 %s，时间逻辑异常"
                    % (card.issue_date, card.batch_id or "-", anchor.isoformat()),
            evidence={
                "issue_date": card.issue_date,
                "anchor": anchor.isoformat(),
                "batch_id": card.batch_id,
                "delta_days": (issue - anchor).days,
            },
        ))
    return RuleResult(tuple(hits), skipped)


def check_time_stale(ctx: Context) -> RuleResult:
    """R-TIME-02 跨期异常：开票早于基准月超过 N 期（仅追溯方向）。"""
    n_period = ctx.params["time_n_period"]
    hits = []
    skipped = 0
    for card in ctx.cards:
        if not card.issue_date:
            skipped += 1
            continue
        issue = _as_date(card.issue_date)
        if issue is None:
            skipped += 1
            continue
        anchor = ctx.anchor_of(card)
        months_behind = (anchor.year * 12 + anchor.month) - (
            issue.year * 12 + issue.month)
        if months_behind <= n_period:
            continue
        hits.append(Hit(
            family="time.stale",
            level="review",
            numbers=(card.invoice_number,),
            message="开票日期 %s 距批次 %s 报销基准月 %04d-%02d 跨 %d 期（超过 %d 期），"
                    "跨期报销待人工确认"
                    % (card.issue_date, card.batch_id or "-",
                       anchor.year, anchor.month, months_behind, n_period),
            evidence={
                "issue_date": card.issue_date,
                "anchor": anchor.isoformat(),
                "batch_id": card.batch_id,
                "months_behind": months_behind,
                "n_period": n_period,
            },
        ))
    return RuleResult(tuple(hits), skipped)


# ------------------------------------------------------------------ 编排
def run(ctx: Context) -> Tuple[List[Hit], Dict[str, Dict[str, int]]]:
    """按注册顺序执行八规则；返回 (命中集, 每规则命中/跳过计数)。"""
    all_hits: List[Hit] = []
    stats: Dict[str, Dict[str, int]] = {}
    for family in RULE_ORDER:
        if family == "duplicate.fuzzy":
            result = check_duplicate_fuzzy(ctx, all_hits)
        else:
            result = _RUNNERS[family](ctx)
        seen = set()
        unique = []
        for hit in result.hits:
            key = (hit.family, hit.numbers, hit.suffix, hit.message)
            if key in seen:
                continue
            seen.add(key)
            if hit.level not in LEVELS:
                raise ValueError("非法判定级别：%r" % (hit.level,))
            unique.append(hit)
        stats[family] = {"hits": len(unique), "skipped": result.skipped}
        all_hits.extend(unique)
    return all_hits, stats


_RUNNERS = {
    "duplicate.exact": check_duplicate_exact,
    "duplicate.joint": check_duplicate_joint,
    "series": check_series,
    "arithmetic.total": check_arithmetic_total,
    "arithmetic.cn": check_arithmetic_cn,
    "time.future": check_time_future,
    "time.stale": check_time_stale,
}