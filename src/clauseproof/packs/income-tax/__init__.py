"""器官 ``income-tax``：个人所得税联动判定（累计预扣 × 年度汇算 × 年终奖择优 × 七项扣除）。

规模：判定面来自 target-map ① 行的旧仓（八个年度规则包 + status 门控 + 累计预扣
逐月状态机 + 年度汇算 + 社保联动 + 七项专项附加校验/计算 + 年终奖单独计税/择优/
临界区间机制性推导）。

本器官只做一件事：**给一份工资薪金年度档案 + 随包年度规则包，判该年度应预扣多少、
年终奖单独计税与并入哪一方案更省、申报的扣除项是否成立**。它不打印、不读环境变量、
不读时钟，也不带自己的参数解析器——入口只有
``clauseproof check income-tax --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

====================================  ==========================================
来源结论                               本器官 verdict
====================================  =====================================
status 门控拦截（待核对条目）           ``fail``（必带锚点：status 门控契约；阻断 → 1）
社保公积金个人部分合计                  ``pass``（锚点：社保参数属用户输入契约）
逐月累计预扣（每期一条）                 ``pass``（锚点：减除费用条款；级次/税率在 evidence）
专项附加扣除逐项成立                    ``pass``（锚点：该项标准条款）
年度汇算应退/应补                       ``pass``（锚点：减除费用条款）
年终奖单独计税                          ``pass``（锚点：按月换算税率表附件）
单独计税政策在有效期内 / 已到期          ``pass`` / ``not_applicable``（锚点：政策条款）
双方案择优                              ``pass``（锚点：择优/优惠衔接政策条款）
临界区间（未落入 / 落入预警）            ``not_applicable``（预警 ≠ 判定，不阻断）
缺月补足                                ``not_applicable``（锚点：缺月补足契约）
计算完成（汇总）                        ``pass``（锚点：账本口径契约）
====================================  ==========================================

**输入不可用**（无该年度规则包/年度非法/字段不认识/数值非法/月数为空或超限/
社保参数缺成对上下限/扣除申报违规整单拒绝/奖金非正/已预扣为负）→ 抛 ``ValueError``
→ 退出码 2（与来源仓「用法与输入错误 = 2」逐条对齐；**扣除申报违规**在来源仓
同样是 2，本器官不改判据迁就代码）。

条文库缺所需条款 → ``BasisMissing`` 冒到 CLI（本产品内核映射退出码 2）；
条文库版本与规则包快照不符 → ``ContractError``（退出码 3）。
"""

from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from clauseproof.core.basis import Basis
from clauseproof.core.ledger import (
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Finding,
)
from clauseproof.core.registry import Pack, register

from . import bonus as B
from . import deductions as D
from . import pipeline as P
from . import registry as reg
from . import rules as R
from .monthly import MONTHS_PER_YEAR, MonthInput

SLUG = "income-tax"
VERSION = "0.1.0"
SUMMARY = ("个人所得税联动判定（累计预扣 × 年度汇算 × 年终奖择优 × 七项专项附加扣除；"
           "八个年度规则包随包冻结）")

INPUT_FIELDS = ("year",)

RULE_GATE = "tax.gate"
RULE_MONTHS_PADDED = "tax.months.padded"
RULE_SOCIAL = "tax.social"
RULE_CLAIM = "tax.claim"
RULE_MONTH = "tax.month"
RULE_SETTLEMENT = "tax.settlement"
RULE_BONUS = "tax.bonus"
RULE_BONUS_POLICY = "tax.bonus.policy"
RULE_BONUS_COMPARE = "tax.bonus.compare"
RULE_BONUS_TRAP = "tax.bonus.trap"
RULE_RESULT = "tax.result"

_TOP_FIELDS = (
    "year",
    "months",
    "uniform_month",
    "month_count",
    "social",
    "special_additional_claims",
    "bonus_income",
    "settlement",
)
_MONTH_FIELDS = (
    "gross",
    "tax_free",
    "special_deduction",
    "special_additional_deduction",
    "other_deduction",
)
_SETTLEMENT_FIELDS = (
    "annual_gross",
    "annual_special_deduction",
    "annual_special_additional_deduction",
    "annual_other_deduction",
    "withheld_total",
)
_CLAIM_FIELDS = (
    "item",
    "children",
    "share_ratio",
    "kind",
    "months",
    "tier",
    "only_child",
    "monthly_amount",
    "other_shared_amounts",
    "self_paid_total",
    "note",
)
_CLAIM_DECIMAL_FIELDS = ("children", "share_ratio", "monthly_amount", "self_paid_total")


# ---------------------------------------------------------------------------
# 装配面：subject 结构校验与解析（非法一律 ValueError → 退出码 2）
# ---------------------------------------------------------------------------
def _check_unknown_keys(node: Mapping, allowed, where: str) -> None:
    unknown = sorted(set(node) - set(allowed))
    if unknown:
        raise ValueError(f"{where}: 不认识的字段 {unknown}（允许：{sorted(allowed)}）")


def _decimal(node: Mapping, key: str, where: str) -> Decimal:
    try:
        return R.to_decimal(node[key], f"{where}.{key}")
    except KeyError:
        raise ValueError(f"{where}: 缺少必填字段 {key}")
    except R.RulesetSchemaError as exc:
        raise ValueError(str(exc))


def _optional_decimal(node: Mapping, key: str, where: str) -> Optional[Decimal]:
    if key not in node:
        return None
    try:
        return R.to_decimal(node[key], f"{where}.{key}")
    except R.RulesetSchemaError as exc:
        raise ValueError(str(exc))


def _parse_month_object(node: Any, where: str) -> MonthInput:
    if not isinstance(node, Mapping):
        raise ValueError(f"{where}: 月度输入必须是对象")
    _check_unknown_keys(node, _MONTH_FIELDS, where)
    kwargs = {}
    for key in _MONTH_FIELDS:
        value = _optional_decimal(node, key, where)
        kwargs[key] = value if value is not None else Decimal(0)
    return MonthInput(**kwargs)


def _parse_months(raw: Mapping) -> Tuple[List[MonthInput], int]:
    """月度输入：``months`` 显式列表 或 ``uniform_month`` + ``month_count``。

    返回 ``(月份列表, 实提供月数)``。缺月按 0 补足到 12 个月（输入层口径；累计预扣
    补 0 不改变税额），调用方另行出账一条 ``not_applicable`` 说明未提供月份。
    """
    has_months = "months" in raw
    has_uniform = "uniform_month" in raw or "month_count" in raw
    if has_months and has_uniform:
        raise ValueError("输入：months 与 uniform_month/month_count 只能二选一")

    months: List[MonthInput] = []
    if has_months:
        nodes = raw["months"]
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("输入：months 必须为非空数组")
        if len(nodes) > MONTHS_PER_YEAR:
            raise ValueError(f"输入：months 最多 {MONTHS_PER_YEAR} 个月，收到 {len(nodes)} 个")
        months = [_parse_month_object(node, f"months[{i}]") for i, node in enumerate(nodes)]
    elif has_uniform:
        uniform = _parse_month_object(raw.get("uniform_month", {}) or {}, "uniform_month")
        count = raw.get("month_count")
        if not isinstance(count, int) or isinstance(count, bool):
            raise ValueError(f"输入：month_count 必须为 1-{MONTHS_PER_YEAR} 的整数")
        if not 1 <= count <= MONTHS_PER_YEAR:
            raise ValueError(f"输入：month_count 必须为 1-{MONTHS_PER_YEAR} 的整数")
        months = [uniform] * count
    else:
        raise ValueError("输入：缺少月度输入（months 列表，或 uniform_month+month_count）")

    provided = len(months)
    for _ in range(provided, MONTHS_PER_YEAR):
        months.append(MonthInput(note="未提供，按 0 处理"))
    return months, provided


def _parse_social(raw: Mapping):
    if raw.get("social") is None:
        return None
    node = raw["social"]
    where = "social"
    if not isinstance(node, Mapping):
        raise ValueError(f"{where}: 必须为对象")
    _check_unknown_keys(node, ("base_input", "base_lower", "base_upper", "rates"), where)
    base_input = _decimal(node, "base_input", where)
    base_lower = _optional_decimal(node, "base_lower", where)
    base_upper = _optional_decimal(node, "base_upper", where)
    if (base_lower is None) != (base_upper is None):
        raise ValueError(f"{where}: base_lower 与 base_upper 必须成对提供（夹取区间）")
    if base_lower is None:
        raise ValueError(f"{where}: 缺少 base_lower/base_upper（缴费基数上下限，用户输入）")
    rates = node.get("rates")
    if not isinstance(rates, Mapping) or not rates:
        raise ValueError(f"{where}.rates: 必须为非空对象（{{险种名: 个人费率}}）")
    parsed_rates = {}
    for label, value in rates.items():
        parsed_rates[str(label)] = R.to_decimal(value, f"{where}.rates.{label}")
    return (base_input, parsed_rates, base_lower, base_upper)


def _parse_settlement(raw: Mapping) -> Dict[str, Decimal]:
    if raw.get("settlement") is None:
        return {}
    node = raw["settlement"]
    if not isinstance(node, Mapping):
        raise ValueError("settlement: 必须为对象")
    _check_unknown_keys(node, _SETTLEMENT_FIELDS, "settlement")
    overrides = {}
    for key in _SETTLEMENT_FIELDS:
        value = _optional_decimal(node, key, "settlement")
        if value is not None:
            overrides[key] = value
    return overrides


def _parse_claims(raw: Mapping) -> List[D.Claim]:
    """专项附加扣除申报清单（七项；字段按项目取用，非法组合由引擎校验拒绝）。"""
    if raw.get("special_additional_claims") is None:
        return []
    nodes = raw["special_additional_claims"]
    if not isinstance(nodes, list):
        raise ValueError("special_additional_claims: 必须为数组")
    claims: List[D.Claim] = []
    for i, node in enumerate(nodes):
        where = f"special_additional_claims[{i}]"
        if not isinstance(node, Mapping):
            raise ValueError(f"{where}: 必须为对象")
        _check_unknown_keys(node, _CLAIM_FIELDS, where)
        item = node.get("item")
        if not isinstance(item, str) or not item:
            raise ValueError(f"{where}: 缺少 item（扣除项目键，如 child_education）")
        kwargs: Dict[str, Any] = {"item": item}
        for key in _CLAIM_DECIMAL_FIELDS:
            value = _optional_decimal(node, key, where)
            if value is not None:
                kwargs[key] = value
        kind = node.get("kind")
        if kind is not None:
            if not isinstance(kind, str):
                raise ValueError(f"{where}.kind: 必须为字符串（academic/vocational）")
            kwargs["kind"] = kind
        months = node.get("months")
        if months is not None:
            if not isinstance(months, int) or isinstance(months, bool) or not (
                1 <= months <= MONTHS_PER_YEAR
            ):
                raise ValueError(f"{where}.months: 必须为 1-{MONTHS_PER_YEAR} 的整数")
            kwargs["months"] = months
        tier = node.get("tier")
        if tier is not None:
            if not isinstance(tier, int) or isinstance(tier, bool) or tier < 0:
                raise ValueError(f"{where}.tier: 必须为非负整数（住房租金城市档下标）")
            kwargs["tier"] = tier
        only_child = node.get("only_child")
        if only_child is not None:
            if not isinstance(only_child, bool):
                raise ValueError(f"{where}.only_child: 必须为布尔值")
            kwargs["only_child"] = only_child
        others = node.get("other_shared_amounts")
        if others is not None:
            if not isinstance(others, list):
                raise ValueError(f"{where}.other_shared_amounts: 必须为数组")
            parsed = []
            for j, value in enumerate(others):
                parsed.append(R.to_decimal(value, f"{where}.other_shared_amounts[{j}]"))
            kwargs["other_shared_amounts"] = tuple(parsed)
        note = node.get("note")
        if note is not None:
            if not isinstance(note, str):
                raise ValueError(f"{where}.note: 必须为字符串")
            kwargs["note"] = note
        claims.append(D.Claim(**kwargs))
    return claims


def validate_subject(subject: Mapping) -> None:
    """subject 结构校验（非法抛 ``ValueError``，内核映射 2）。"""
    if not isinstance(subject, Mapping):
        raise ValueError("输入必须是 JSON 对象，得到 %s" % type(subject).__name__)
    _check_unknown_keys(subject, _TOP_FIELDS, "输入")
    year = subject.get("year")
    if not isinstance(year, int) or isinstance(year, bool):
        raise ValueError("输入：year 必须为整数（纳税年度）")


def parse_subject(subject: Mapping) -> Tuple[int, P.CalcRequest, int]:
    """subject → (year, CalcRequest, 实提供的月数)。

    ``预算``：只做结构/取值校验，不查规则包是否存在（由 ``evaluate`` 决定）。
    """
    validate_subject(subject)
    year = int(subject["year"])
    months, provided = _parse_months(subject)
    bonus_income = None
    if subject.get("bonus_income") is not None:
        bonus_income = _decimal(subject, "bonus_income", "输入")
    request = P.CalcRequest(
        months=tuple(months),
        social_params=_parse_social(subject),
        claims=tuple(_parse_claims(subject)),
        bonus_income=bonus_income,
        settlement_overrides=_parse_settlement(subject),
    )
    return year, request, provided


# ---------------------------------------------------------------------------
# 出账：判定账本（一行一结论 + 条文锚点）
# ---------------------------------------------------------------------------
def _require_basis_version(basis: Basis) -> None:
    if basis.version != reg.PARAMS_VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据规则包快照 %s 核对，条文库实为 %s"
            % (reg.PARAMS_VERSION, basis.version))


def _dec(value) -> str:
    """证据里的数值一律字符串化（Decimal 不进 JSON）。"""
    if isinstance(value, Decimal):
        return str(value)
    return "" if value is None else str(value)


def _amount(value: Optional[Decimal]) -> str:
    return "-" if value is None else f"{value:.2f}"


def _rate(value: Optional[Decimal]) -> str:
    return "-" if value is None else f"{value * 100:.2f}%"


def _anchor_ref(basis: Basis, ref: Any):
    return basis.anchor(reg.ref_clause_id(ref))


def _standard_ref(ruleset: R.Ruleset) -> Any:
    return ruleset.data["withholding"]["monthly_standard_deduction"]["ref"]


def _monthly_table_ref(ruleset: R.Ruleset) -> Any:
    return ruleset.data["rate_tables"]["monthly_converted"][0]["ref"]


def _bonus_policy_ref(ruleset: R.Ruleset) -> Any:
    return ruleset.data["bonus"]["separate_tax_policy"]["ref"]


def _gate_findings(ruleset: R.Ruleset, basis: Basis) -> List[Finding]:
    report = R.status_report(ruleset)
    if report.all_effective:
        return []
    return [
        Finding(
            rule_id="%s:%s" % (RULE_GATE, path),
            verdict=FAIL,
            message="规则包 %d 年度门控拦截：%d 项待核对（%s）"
                    % (ruleset.year, report.pending, path),
            anchor=basis.anchor(reg.CLAUSE_GATE),
            evidence={"year": ruleset.year, "pending_count": report.pending,
                      "pending_paths": list(report.pending_paths)},
        )
        for path in report.pending_paths
    ]


def _social_finding(result, basis: Basis) -> Finding:
    items = "、".join("%s %s" % (item.label, _amount(item.personal_amount))
                     for item in result.items)
    message = "社保公积金个人部分合计 %s 元/月（缴费基数 %s，用户输入区间 [%s, %s]；%s）" % (
        _amount(result.total), _amount(result.clamped_base),
        _amount(result.base_lower), _amount(result.base_upper), items)
    if result.clamp_note:
        message += "；" + result.clamp_note
    return Finding(
        rule_id=RULE_SOCIAL,
        verdict=PASS,
        message=message,
        anchor=basis.anchor(reg.CLAUSE_SOCIAL),
        evidence={
            "base_input": _dec(result.base_input),
            "clamped_base": _dec(result.clamped_base),
            "base_lower": _dec(result.base_lower),
            "base_upper": _dec(result.base_upper),
            "items": [{"label": item.label, "rate": _dec(item.rate),
                       "base": _dec(item.base),
                       "personal_amount": _dec(item.personal_amount)}
                      for item in result.items],
            "total": _dec(result.total),
            "clamp_note": result.clamp_note,
        },
    )


def _claim_finding(claim, basis: Basis) -> Finding:
    stage_label = "预扣+汇算" if claim.stage == D.STAGE_BOTH else "仅汇算"
    message = "%s（%s）：%s → 年额 %s 元" % (
        D.ITEM_LABELS.get(claim.item, claim.item), stage_label,
        claim.detail, _amount(claim.annual_amount))
    if claim.note:
        message += "；" + claim.note
    return Finding(
        rule_id="%s:%s" % (RULE_CLAIM, claim.item if not claim.kind
                           else "%s:%s" % (claim.item, claim.kind)),
        verdict=PASS,
        message=message,
        anchor=_anchor_ref(basis, claim.standard_ref),
        evidence={
            "item": claim.item, "kind": claim.kind, "stage": claim.stage,
            "monthly_amount": _dec(claim.monthly_amount),
            "months_claimed": claim.months_claimed,
            "annual_amount": _dec(claim.annual_amount),
            "detail": claim.detail,
            "standard_ref": dict(claim.standard_ref),
        },
    )


def _month_finding(month, standard_ref: Any, basis: Basis) -> Finding:
    message = (
        "第 %d 月：累计收入 %s − 累计减除 %s − 累计专项 %s − 累计专项附加 %s − 累计其他 %s "
        "= 累计应纳税所得额 %s"
    ) % (
        month.month_no,
        _amount(month.cumulative_income),
        _amount(month.cumulative_standard_deduction),
        _amount(month.cumulative_special_deduction),
        _amount(month.cumulative_special_additional_deduction),
        _amount(month.cumulative_other_deduction),
        _amount(month.cumulative_taxable),
    )
    if month.bracket_index is None:
        message += "；累计应纳税所得额 ≤ 0 → 累计应预扣 0.00；本期应预扣 0.00"
    else:
        message += "；第 %d 级 %s（速算 %s）→ 累计应预扣 %s；本期应预扣 %s" % (
            month.bracket_index + 1, _rate(month.rate), _amount(month.quick_deduction),
            _amount(month.cumulative_tax), _amount(month.withholding))
    if month.note:
        message += "（注：%s）" % month.note
    return Finding(
        rule_id="%s:%02d" % (RULE_MONTH, month.month_no),
        verdict=PASS,
        message=message,
        anchor=_anchor_ref(basis, standard_ref),
        evidence={
            "month_no": month.month_no,
            "gross": _dec(month.inp.gross),
            "tax_free": _dec(month.inp.tax_free),
            "special_deduction": _dec(month.inp.special_deduction),
            "special_additional_deduction": _dec(month.inp.special_additional_deduction),
            "other_deduction": _dec(month.inp.other_deduction),
            "cumulative_income": _dec(month.cumulative_income),
            "cumulative_tax_free": _dec(month.cumulative_tax_free),
            "cumulative_standard_deduction": _dec(month.cumulative_standard_deduction),
            "cumulative_special_deduction": _dec(month.cumulative_special_deduction),
            "cumulative_special_additional_deduction": _dec(
                month.cumulative_special_additional_deduction),
            "cumulative_other_deduction": _dec(month.cumulative_other_deduction),
            "cumulative_taxable": _dec(month.cumulative_taxable),
            "bracket_index": month.bracket_index,
            "rate": _dec(month.rate),
            "quick_deduction": _dec(month.quick_deduction),
            "cumulative_tax": _dec(month.cumulative_tax),
            "withheld_before": _dec(month.withheld_before),
            "withholding": _dec(month.withholding),
            "note": month.note,
        },
    )


def _settlement_finding(report, basis: Basis) -> Finding:
    if report.bracket_index is None:
        message = "年度汇算：应纳税所得额 %s ≤ 0 → 年应纳税额 0.00；已预扣 %s → 应退税额 %s" % (
            _amount(report.cumulative_taxable_income),
            _amount(report.withheld_total), _amount(report.refund_or_owe))
    else:
        message = (
            "年度汇算：减除费用 %s，应纳税所得额 %s → 第 %d 级 %s（速算 %s）→ "
            "年应纳税额 %s；已预扣 %s → 应退税额 %s"
        ) % (
            _amount(report.annual_standard_deduction),
            _amount(report.cumulative_taxable_income),
            report.bracket_index + 1, _rate(report.rate), _amount(report.quick_deduction),
            _amount(report.annual_tax), _amount(report.withheld_total),
            _amount(report.refund_or_owe))
    if report.note:
        message += "；" + report.note
    return Finding(
        rule_id=RULE_SETTLEMENT,
        verdict=PASS,
        message=message,
        anchor=_anchor_ref(basis, report.standard_deduction_ref),
        evidence={
            "annual_standard_deduction": _dec(report.annual_standard_deduction),
            "cumulative_taxable_income": _dec(report.cumulative_taxable_income),
            "bracket_index": report.bracket_index,
            "rate": _dec(report.rate),
            "quick_deduction": _dec(report.quick_deduction),
            "annual_tax": _dec(report.annual_tax),
            "withheld_total": _dec(report.withheld_total),
            "refund_or_owe": _dec(report.refund_or_owe),
            "note": report.note,
        },
    )


def _bonus_findings(result, comparison, intervals, active,
                    monthly_ref: Any, policy_ref: Any, basis: Basis) -> List[Finding]:
    findings: List[Finding] = []
    findings.append(Finding(
        rule_id=RULE_BONUS,
        verdict=PASS,
        message="全年一次性奖金 %s ÷ %s = %s（商数定档，税基全额）→ 第 %d 级 %s（速算 %s）"
                "→ 应纳税额 %s；税后 %s"
                % (_amount(result.bonus_amount), _dec(result.divisor), _dec(result.quotient),
                   (result.bracket_index or 0) + 1, _rate(result.rate),
                   _amount(result.quick_deduction), _amount(result.tax),
                   _amount(result.after_tax)),
        anchor=_anchor_ref(basis, monthly_ref),
        evidence={
            "bonus_amount": _dec(result.bonus_amount),
            "divisor": _dec(result.divisor),
            "quotient": _dec(result.quotient),
            "bracket_index": result.bracket_index,
            "rate": _dec(result.rate),
            "quick_deduction": _dec(result.quick_deduction),
            "tax": _dec(result.tax),
            "after_tax": _dec(result.after_tax),
            "policy_valid": result.policy_valid,
            "policy_note": result.policy_note,
        },
    ))
    findings.append(Finding(
        rule_id=RULE_BONUS_POLICY,
        verdict=PASS if result.policy_valid else NOT_APPLICABLE,
        message=(result.policy_note or "单独计税政策有效期未登记")
                + ("" if result.policy_valid
                   else "：该纳税年度方案 A 不可选，只能并入综合所得"),
        anchor=_anchor_ref(basis, policy_ref),
        evidence={"policy_valid": result.policy_valid, "policy_note": result.policy_note},
    ))
    difference = comparison.tax_difference
    if not comparison.scheme_separate.available:
        tail = "推荐方案 B（方案 A 在该年度不可选）"
    elif comparison.tie:
        tail = "差额不超过申报精度 → 两案等同，可任选"
    elif comparison.recommended == B.SCHEME_SEPARATE:
        tail = "推荐方案 A：单独计税全年少缴 %s" % _amount(-difference)
    else:
        tail = "推荐方案 B：并入综合所得全年少缴 %s" % _amount(difference)
    findings.append(Finding(
        rule_id=RULE_BONUS_COMPARE,
        verdict=PASS,
        message="方案 A 全年总税负 %s / 方案 B %s；差额（A−B）%s → %s"
                % (_amount(comparison.scheme_separate.annual_total_tax),
                   _amount(comparison.scheme_combined.annual_total_tax),
                   _amount(difference), tail),
        anchor=_anchor_ref(basis, policy_ref),
        evidence={
            "recommended": comparison.recommended,
            "tax_difference": _dec(difference),
            "tie": comparison.tie,
            "scheme_separate": {
                "available": comparison.scheme_separate.available,
                "annual_total_tax": _dec(comparison.scheme_separate.annual_total_tax),
                "bracket_index": comparison.scheme_separate.bracket_index,
                "rate": _dec(comparison.scheme_separate.rate),
                "note": comparison.scheme_separate.note,
            },
            "scheme_combined": {
                "available": comparison.scheme_combined.available,
                "annual_total_tax": _dec(comparison.scheme_combined.annual_total_tax),
                "taxable_income": _dec(comparison.scheme_combined.taxable_income),
                "bracket_index": comparison.scheme_combined.bracket_index,
                "rate": _dec(comparison.scheme_combined.rate),
                "note": comparison.scheme_combined.note,
            },
            "note": comparison.note,
        },
    ))
    if active is None:
        trap_message = ("奖金未落入任何临界区间（%d 个区间由按月换算表逐边界推导；"
                        "「多发一元、到手变少」风险不适用）" % len(intervals))
    else:
        trap_message = ("[!!] 奖金落入临界区间 (%s, %s)：区间内税后奖金低于左端锚点处"
                        "（税率表级距机制客观呈现，非避税建议）"
                        % (_amount(active.lower), _amount(active.upper)))
    findings.append(Finding(
        rule_id=RULE_BONUS_TRAP,
        verdict=NOT_APPLICABLE,
        message=trap_message,
        anchor=_anchor_ref(basis, monthly_ref),
        evidence={
            "in_trap": active is not None,
            "intervals": [{"lower": _dec(iv.lower), "upper": _dec(iv.upper),
                           "left_bracket_index": iv.left_bracket_index,
                           "right_bracket_index": iv.right_bracket_index}
                          for iv in intervals],
            "active": None if active is None else {
                "lower": _dec(active.lower), "upper": _dec(active.upper),
                "left_rate": _dec(active.left_rate), "right_rate": _dec(active.right_rate),
                "note": active.note,
            },
        },
    ))
    return findings


def _result_finding(ruleset, request, result, basis: Basis) -> Finding:
    monthly = result.monthly_report
    settlement = result.settlement_report
    claims = result.deductions_report
    bonus = result.bonus_report
    evidence = {
        "year": ruleset.year,
        "months": len(monthly.months),
        "withheld_total": _dec(monthly.withheld_total),
        "claims": 0 if claims is None else len(claims.claims),
        "claims_monthly_total": None if claims is None else _dec(claims.monthly_total),
        "claims_annual_total": None if claims is None else _dec(claims.annual_total),
        "settlement_only_annual_total": None if claims is None
        else _dec(claims.settlement_only_annual_total),
        "refund_or_owe": _dec(settlement.refund_or_owe),
        "annual_tax": _dec(settlement.annual_tax),
        "bonus_tax": None if bonus is None else _dec(bonus.tax),
        "bonus_recommended": None if result.bonus_comparison is None
        else result.bonus_comparison.recommended,
    }
    message = "计算完成（%d 纳税年度）：逐月 %d 期，已预扣 %s；汇算应纳税额 %s（应退/应补 %s）" % (
        ruleset.year, len(monthly.months), _amount(monthly.withheld_total),
        _amount(settlement.annual_tax), _amount(settlement.refund_or_owe))
    if claims is not None:
        message += "；申报 %d 项（月合计 %s / 年合计 %s）" % (
            len(claims.claims), _amount(claims.monthly_total), _amount(claims.annual_total))
    if bonus is not None and result.bonus_comparison is not None:
        if result.bonus_comparison.tie:
            pick = "并列"
        elif result.bonus_comparison.recommended == B.SCHEME_SEPARATE:
            pick = result.bonus_comparison.scheme_separate.label
        else:
            pick = result.bonus_comparison.scheme_combined.label
        message += "；年终奖单独计税 %s，推荐 %s" % (_amount(bonus.tax), pick)
    return Finding(
        rule_id=RULE_RESULT,
        verdict=PASS,
        message=message,
        anchor=basis.anchor(reg.CLAUSE_LEDGER),
        evidence=evidence,
    )


def _findings(ruleset: R.Ruleset, request: P.CalcRequest, basis: Basis,
              provided_months: int) -> List[Finding]:
    gate = _gate_findings(ruleset, basis)
    if gate:
        blocked = Finding(
            rule_id=RULE_RESULT,
            verdict=NOT_APPLICABLE,
            message="门控拦截：规则包存在待核对条目，未出账（不得按已核对计算）",
            anchor=basis.anchor(reg.CLAUSE_GATE),
            evidence={"year": ruleset.year, "reason": "status_gate"},
        )
        return gate + [blocked]

    result = P.compute_full_calc(ruleset, request)
    findings: List[Finding] = []

    if result.social_report is not None:
        findings.append(_social_finding(result.social_report, basis))

    if result.deductions_report is not None:
        for claim in result.deductions_report.claims:
            findings.append(_claim_finding(claim, basis))

    for month in result.monthly_report.months:
        findings.append(_month_finding(month, _standard_ref(ruleset), basis))

    findings.append(_settlement_finding(result.settlement_report, basis))

    if result.bonus_report is not None:
        findings.extend(_bonus_findings(
            result.bonus_report, result.bonus_comparison,
            list(result.trap_intervals), result.active_trap,
            _monthly_table_ref(ruleset), _bonus_policy_ref(ruleset), basis))

    if provided_months < MONTHS_PER_YEAR:
        findings.append(Finding(
            rule_id=RULE_MONTHS_PADDED,
            verdict=NOT_APPLICABLE,
            message="第 %d–%d 月未提供，按 0 处理并逐月出账（累计口径下补 0 不改变税额）"
                    % (provided_months + 1, MONTHS_PER_YEAR),
            anchor=basis.anchor(reg.CLAUSE_MONTHS),
            evidence={"provided": provided_months, "padded_to": MONTHS_PER_YEAR},
        ))

    findings.append(_result_finding(ruleset, request, result, basis))
    return findings


def evaluate_with_rulesets(subject: Mapping, basis: Basis,
                           raw_packs: Mapping) -> Iterable[Finding]:
    """判定入口（测试可注入合成规则包；``evaluate`` 用随包规则包走同一路径）。"""
    _require_basis_version(basis)
    year, request, provided = parse_subject(subject)
    if year not in raw_packs:
        raise R.RulesetNotFoundError(year, sorted(raw_packs))
    ruleset = R.build_ruleset(raw_packs[year], expected_year=year)
    return tuple(_findings(ruleset, request, basis, provided))


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    _require_basis_version(basis)
    year, request, provided = parse_subject(subject)
    ruleset = reg.ruleset(year)
    return tuple(_findings(ruleset, request, basis, provided))


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "evaluate_with_rulesets",
           "validate_subject", "parse_subject"]