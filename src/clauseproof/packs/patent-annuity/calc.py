"""年费 / 滞纳金 / 费减 / 组合排期计算内核（迁自来源 ``calc.*``）。

纪律：档位端点与政策数值只来自规则包；金额只由 Decimal 产生；未核对不得进
计算路径（门控拒绝时 ``amount=None`` 并携带原因码，由器官入口映射）。
"""

import calendar
import hashlib
import json as _json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from . import rules as R
from .errors import OutOfRangeError, PatfeeError, RulesetError, UsageError
from .models import (AnnuityResult, FeeBasis, LateResult, PatentType,
                     PolicyCandidate, PortfolioEntry, PortfolioResult,
                     ReductionResult, Tier, parse_patent_type, quantize_amount)

ENTRY_PREFIX = "annuity."
RELATED_FEE_KEYS = ("check.fee.ruc", "check.fee.evaluation_report")
MONTH_BASIS_CALENDAR = "calendar_month"
MONTH_BASIS_THIRTY_DAY = "thirty_day"
KIND_SETTLED = "settled"
KIND_UNPAID = "unpaid"
KIND_NOT_DUE = "not_due"
KIND_FAILED = "failed"
REASON_BAD_FORMAT = "bad_format"


def entry_key_for(patent_type):
    return ENTRY_PREFIX + patent_type.value


def tiers_from_entry(entry):
    tiers = []
    for raw in entry.tiers():
        try:
            from_year = int(raw["from_year"])
            to_year = int(raw["to_year"])
            amount = raw["amount"]
        except (KeyError, TypeError, ValueError) as exc:
            raise RulesetError("条目 %s 的阶梯区段非法: %r (%s)"
                               % (entry.key, raw, exc))
        if amount is None:
            raise RulesetError("条目 %s 的阶梯区段缺少金额: %r" % (entry.key, raw))
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        tiers.append(Tier(from_year=from_year, to_year=to_year, amount=amount,
                          label=raw.get("label") or ""))
    if not tiers:
        raise RulesetError("条目 %s 没有阶梯区段" % entry.key)
    return tiers


def find_tier(tiers, year):
    for tier in tiers:
        if tier.contains(year):
            return tier
    covered = ", ".join("%d-%d" % (t.from_year, t.to_year) for t in tiers)
    raise OutOfRangeError("缴费年度 %d 超出该专利类型的阶梯覆盖范围（已覆盖: %s）"
                          % (year, covered))


def basis_from_entry(entry, clause_override=None):
    basis = entry.basis or {}
    return FeeBasis(entry.ruleset_id, entry.ruleset_version, entry.key,
                    basis.get("doc_no") or "",
                    clause_override or basis.get("clause") or "",
                    basis.get("url") or "", basis.get("retrieved") or "")


def compute_annuity(library, patent_type, year, preview=False, provided_inputs=()):
    key = entry_key_for(patent_type)
    decision = R.evaluate_keys(library, [key], R.SCOPE_CALC, preview=preview,
                               provided_inputs=provided_inputs)
    entry = library.entry(key)
    if entry is None:
        return AnnuityResult(patent_type, year, None, None, None,
                             reasons=("untracked_entry",),
                             steps=("未在规则包中找到条目 %s" % key,),
                             coordinate=library.coordinate())
    if not decision.allowed:
        reasons = list(decision.reasons)
        if decision.required_inputs:
            reasons.append("input_required")
        steps = ["门控拒绝（scope=%s）：%s"
                 % (decision.scope, ", ".join(decision.reasons))]
        return AnnuityResult(patent_type, year, None, None,
                             basis_from_entry(entry),
                             reasons=tuple(dict.fromkeys(reasons)),
                             steps=tuple(steps), coordinate=library.coordinate())
    tiers = tiers_from_entry(entry)
    try:
        tier = find_tier(tiers, year)
    except OutOfRangeError as exc:
        return AnnuityResult(patent_type, year, None, None,
                             basis_from_entry(entry),
                             reasons=(exc.reason_code,),
                             steps=("超出阶梯覆盖范围：%s" % exc.message,),
                             coordinate=library.coordinate())
    amount = quantize_amount(tier.amount)
    warnings = []
    if decision.permitted_unverified:
        warnings.append("预览口径：条目 %s 尚未核对（status=pending），"
                        "金额不得作为缴费依据"
                        % ", ".join(decision.permitted_unverified))
    steps = ("专利类型=%s" % patent_type.value,
             "缴费年度=第 %d 年" % year,
             "命中区间=%s（第 %d-%d 年）"
             % (tier.label or "第 %d-%d 年" % (tier.from_year, tier.to_year),
                tier.from_year, tier.to_year),
             "区间年费=%s" % tier.amount, "结果=%s" % amount)
    return AnnuityResult(patent_type, year, amount, tier,
                         basis_from_entry(entry,
                                          clause_override=(tier.label or entry.basis.get("clause") or "")),
                         warnings=tuple(warnings), steps=steps,
                         coordinate=library.coordinate())


@dataclass(frozen=True)
class LateRequest:
    patent_type: PatentType
    year: int
    due_on: date
    paid_on: date
    preview: bool = False


def add_calendar_months(d, months):
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def overdue_months_between(due_on, paid_on, month_basis):
    steps = []
    if paid_on <= due_on:
        return 0, ["未逾期（paid_on <= due_on），月数=0"]
    if month_basis == MONTH_BASIS_THIRTY_DAY:
        days = (paid_on - due_on).days
        months = days // 30
        steps.append("口径=thirty_day：逾期 %d 天 ÷ 30 = %d 月（零头不计）"
                     % (days, months))
        return months, steps
    if month_basis == MONTH_BASIS_CALENDAR:
        months = 0
        probe = due_on
        while add_calendar_months(due_on, months + 1) <= paid_on:
            months += 1
            probe = add_calendar_months(due_on, months)
        steps.append("口径=calendar_month：自 %s 整自然月推进至 %s，共 %d 个整月"
                     "（零头不计）" % (due_on.isoformat(), probe.isoformat(), months))
        return months, steps
    raise PatfeeError("规则包 late.month_basis 值不识别: %r" % (month_basis,),
                      reason_code="ruleset_error")


def _required_scalar(library, key):
    entry = library.entry(key)
    if entry is None:
        raise RulesetError("规则包缺条目: %s" % key)
    value = entry.decimal()
    if value is None:
        raise RulesetError("条目 %s 值未入库（missing_value）" % key)
    return value


def compute_late(library, request, annuity=None):
    annuity_key = "annuity." + request.patent_type.value
    late_keys = ("late.monthly_rate", "late.grace_months", "late.month_basis")
    decision = R.evaluate_keys(library, list(late_keys) + [annuity_key],
                               R.SCOPE_LATE, preview=request.preview)
    annuity_gate = R.evaluate_keys(library, [annuity_key], R.SCOPE_CALC)
    reasons = list(decision.reasons)
    if not annuity_gate.allowed:
        reasons.extend(annuity_gate.reasons)
    warnings = []
    steps = []
    basis_entry = library.entry(annuity_key)
    basis = basis_from_entry(basis_entry) if basis_entry is not None else None

    def uncomputed(extra=()):
        return LateResult(
            request.patent_type, request.year, request.due_on.isoformat(),
            request.paid_on.isoformat(), None,
            _basis_text(library, ""), None, None, None, None, None, False,
            annuity_key, basis, reasons=tuple(dict.fromkeys(reasons)) or ("gated_pending",),
            warnings=tuple(warnings), steps=tuple(extra), coordinate=library.coordinate())

    steps.append("逾期区间: %s ~ %s"
                 % (request.due_on.isoformat(), request.paid_on.isoformat()))
    if not decision.allowed or not annuity_gate.allowed:
        if decision.required_inputs:
            steps.append("缺少必须显式提供的外部输入: %s"
                         % ", ".join(decision.required_inputs))
        return uncomputed(tuple(steps))
    if annuity is not None and annuity.computed:
        full = annuity.amount
        annuity_entry_key = annuity.basis.entry_key if annuity.basis else annuity_key
        steps.append("年费全额（沿用年费计算结果）: %s 元" % full)
    else:
        annuity_result = compute_annuity(library, request.patent_type, request.year,
                                        preview=request.preview)
        if not annuity_result.computed:
            reasons.extend(annuity_result.reasons)
            steps.append("年费全额未判定: %s" % "; ".join(annuity_result.reasons))
            return uncomputed(tuple(steps))
        full = annuity_result.amount
        annuity_entry_key = (annuity_result.basis.entry_key
                             if annuity_result.basis else annuity_key)
        steps.append("年费全额: %s 元（第 %d 年）" % (full, request.year))
    rate = _required_scalar(library, "late.monthly_rate")
    grace = int(_required_scalar(library, "late.grace_months"))
    month_basis = _basis_text(library, "")
    steps.append("滞纳金费率=%s/月（规则包 late.monthly_rate）" % rate)
    steps.append("补缴上限=%d 个月（规则包 late.grace_months）" % grace)
    steps.append("月数口径=%s（规则包 late.month_basis）" % month_basis)
    months, month_steps = overdue_months_between(request.due_on, request.paid_on,
                                                 month_basis)
    steps.extend(month_steps)
    surcharge = quantize_amount(full * rate * Decimal(months))
    exceeds_cap = months > grace
    payable = quantize_amount(full + surcharge)
    if exceeds_cap:
        reasons.append("late_exceeds_cap")
        warnings.append(
            "逾期 %d 个月已超过规则包补缴上限 %d 个月：专利权自应当缴纳年费期满之日起终止"
            "（进入失效流程口径，须另行办理恢复权利）；本金额为风险测算，不构成法律判定"
            % (months, grace))
    steps.append("滞纳金=%s × %s × %d = %s 元" % (full, rate, months, surcharge))
    steps.append("应缴合计（年费+滞纳金）=%s 元" % payable)
    related = _related_fees(library)
    for fee in related:
        if fee[2] is not None:
            steps.append("关联费用 %s: %s 元（按费率表条目，另行缴纳）"
                         % (fee[1], fee[2]))
    return LateResult(
        request.patent_type, request.year, request.due_on.isoformat(),
        request.paid_on.isoformat(), months, month_basis, grace, full, rate,
        surcharge, payable, exceeds_cap, annuity_entry_key, basis,
        related_fees=tuple(related), reasons=tuple(dict.fromkeys(reasons)),
        warnings=tuple(warnings), steps=tuple(steps), coordinate=library.coordinate())


def _basis_text(library, default):
    entry = library.entry("late.month_basis")
    if entry is not None and entry.value is not None:
        return str(entry.value).strip()
    return default


def _related_fees(library):
    labels = {"check.fee.ruc": "恢复权利请求费",
              "check.fee.evaluation_report": "专利权评价报告请求费"}
    out = []
    for key in RELATED_FEE_KEYS:
        entry = library.entry(key)
        if entry is None:
            continue
        out.append((key, labels.get(key, entry.label), entry.decimal()))
    return out


THRESHOLD_KEYS = (
    "reduction.threshold.individual_monthly_income",
    "reduction.threshold.individual_annual_income",
    "reduction.threshold.entity_taxable_income",
)
RATE_KEYS = ("reduction.rate.sole", "reduction.rate.combined")
POLICY_KEYS = THRESHOLD_KEYS + RATE_KEYS + (
    "reduction.threshold.effective_from",
    "reduction.open_license_discount",
    "reduction.no_double_benefit",
)
POLICY_FEE_REDUCTION = "费减"
POLICY_OPEN_LICENSE = "开放许可年费减免"


@dataclass(frozen=True)
class ReductionRequest:
    patent_type: PatentType
    year: int
    as_of_year: int
    applicants: tuple
    open_license: bool = False
    preview: bool = False


def parse_applicants(payload):
    if not isinstance(payload, (list, tuple)) or not payload:
        raise UsageError("applicants 必须是非空数组")
    out = []
    for idx, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise UsageError("applicants[%d] 必须是对象" % idx)
        kind = str(raw.get("kind") or "").strip()
        if kind not in ("individual", "entity"):
            raise UsageError("applicants[%d].kind 不识别: %r（应为 individual/entity）"
                             % (idx, kind))
        item = {"kind": kind, "name": str(raw.get("name") or "")}
        if kind == "individual":
            item["monthly_avg_income"] = _optional_amount(raw, "monthly_avg_income", idx)
            item["annual_income"] = _optional_amount(raw, "annual_income", idx)
            if item["monthly_avg_income"] is None and item["annual_income"] is None:
                raise UsageError("applicants[%d] 个人主体须提供 monthly_avg_income 或 "
                                 "annual_income" % idx)
        else:
            item["taxable_income"] = _optional_amount(raw, "taxable_income", idx)
        out.append(item)
    return tuple(out)


def _optional_amount(raw, field, idx):
    value = raw.get(field)
    if value in (None, ""):
        return None
    if isinstance(value, float):
        raise UsageError("applicants[%d].%s 不接受浮点数（会引入 1 分尾差）: %r"
                         % (idx, field, value))
    try:
        return Decimal(str(value).strip())
    except Exception:
        raise UsageError("applicants[%d].%s 不是合法金额: %r" % (idx, field, value))


def _required_text(library, key):
    entry = library.entry(key)
    if entry is None or entry.value is None:
        raise RulesetError("规则包缺条目或值未入库: %s" % key)
    return str(entry.value).strip()


def thresholds_for_year(library, as_of_year):
    anchor_text = _required_text(library, "reduction.threshold.effective_from")
    try:
        anchor_year = int(anchor_text[:4])
    except (TypeError, ValueError):
        raise RulesetError("条目 reduction.threshold.effective_from 值非法: %r"
                           % (anchor_text,))
    historical = as_of_year < anchor_year
    suffix = ".prev" if historical else ""
    keys = {
        "individual_monthly_income":
            "reduction.threshold.individual_monthly_income" + suffix,
        "individual_annual_income":
            "reduction.threshold.individual_annual_income" + suffix,
        "entity_taxable_income":
            "reduction.threshold.entity_taxable_income" + suffix,
    }
    return {k: _required_scalar(library, key) for k, key in keys.items()}, historical


def applicant_eligible(applicant, thresholds):
    kind = applicant["kind"]
    if kind == "individual":
        ok = False
        monthly = applicant.get("monthly_avg_income")
        annual = applicant.get("annual_income")
        if monthly is not None and monthly < thresholds["individual_monthly_income"]:
            ok = True
        if annual is not None and annual < thresholds["individual_annual_income"]:
            ok = True
        return ok
    if kind == "entity":
        taxable = applicant.get("taxable_income")
        return taxable is not None and taxable < thresholds["entity_taxable_income"]
    raise UsageError("主体类型不识别: %r" % (kind,))


def _basis_for(library, key):
    entry = library.entry(key)
    if entry is None:
        raise RulesetError("规则包缺条目: %s" % key)
    return basis_from_entry(entry)


def compute_reduction(library, request, annuity_amount=None):
    annuity_key = "annuity." + request.patent_type.value
    decision = R.evaluate_keys(library, list(POLICY_KEYS), R.SCOPE_REDUCTION,
                               preview=request.preview)
    annuity_gate = R.evaluate_keys(library, [annuity_key], R.SCOPE_CALC)
    reasons = list(decision.reasons)
    if not annuity_gate.allowed:
        reasons.extend(annuity_gate.reasons)
    steps = ["主体构成: %d 人（%s）" % (
        len(request.applicants),
        "共同主体" if len(request.applicants) >= 2 else "单主体"),
        "适用年度: %d（阈值按 316 号锚点前后取版本）" % request.as_of_year]

    def uncomputed(extra):
        return ReductionResult(
            request.patent_type, request.year, request.as_of_year,
            len(request.applicants), len(request.applicants) >= 2, None, {},
            None, None, (), None, _no_double_benefit_text(library), False, None,
            reasons=tuple(dict.fromkeys(reasons)) or ("gated_pending",),
            steps=tuple(extra), coordinate=library.coordinate())

    steps.append("门控: reduction scope %s" % ("放行" if decision.allowed else "拒绝"))
    if not decision.allowed or not annuity_gate.allowed:
        return uncomputed(tuple(steps))
    thresholds, historical = thresholds_for_year(library, request.as_of_year)
    steps.append("阈值（%s 口径）: 个人月均<%s 或 年收入<%s；单位应纳税所得额<%s"
                 % ("历史" if historical else "现行",
                    thresholds["individual_monthly_income"],
                    thresholds["individual_annual_income"],
                    thresholds["entity_taxable_income"]))
    eligible = True
    for idx, applicant in enumerate(request.applicants):
        ok = applicant_eligible(applicant, thresholds)
        steps.append("主体[%d] %s: %s" % (
            idx, applicant.get("name") or applicant["kind"],
            "合格" if ok else "不合格（须严格低于阈值，恰好等于不合格）"))
        if not ok:
            eligible = False
    combined = len(request.applicants) >= 2
    full = annuity_amount
    if full is None:
        annuity_result = compute_annuity(library, request.patent_type, request.year,
                                        preview=request.preview)
        if not annuity_result.computed:
            reasons.extend(annuity_result.reasons)
            return uncomputed(tuple(steps))
        full = annuity_result.amount
    steps.append("年费全额: %s 元（第 %d 年）" % (full, request.year))
    candidates = []
    rate_sole = _required_scalar(library, "reduction.rate.sole")
    rate_combined = _required_scalar(library, "reduction.rate.combined")
    reduction_rate = rate_combined if combined else rate_sole
    if eligible:
        candidates.append(PolicyCandidate(
            POLICY_FEE_REDUCTION, reduction_rate,
            quantize_amount(full * (Decimal(1) - reduction_rate))))
    open_license_discount = _required_scalar(library, "reduction.open_license_discount")
    if request.open_license:
        candidates.append(PolicyCandidate(
            POLICY_OPEN_LICENSE, open_license_discount,
            quantize_amount(full * (Decimal(1) - open_license_discount))))
    chosen = None
    payable = None
    if candidates:
        chosen = min(candidates, key=lambda c: c.amount)
        payable = chosen.amount
        steps.append("候选政策: %s" % "; ".join(
            "%s(费率%s→实缴%s)" % (c.policy, c.rate, c.amount) for c in candidates))
        steps.append("选中: %s（实缴 %s 元；不叠加）" % (chosen.policy, chosen.amount))
    else:
        steps.append("无可用减免政策 → 按全额缴纳")
    return ReductionResult(
        request.patent_type, request.year, request.as_of_year,
        len(request.applicants), combined, eligible, thresholds, full,
        reduction_rate if eligible else None, tuple(candidates), chosen,
        _no_double_benefit_text(library), len(candidates) > 1, payable,
        reasons=tuple(dict.fromkeys(reasons)), steps=tuple(steps),
        coordinate=library.coordinate())


def _no_double_benefit_text(library):
    entry = library.entry("reduction.no_double_benefit")
    if entry is None or entry.value is None:
        return ""
    return str(entry.value).strip()


@dataclass(frozen=True)
class PortfolioRequest:
    sources: tuple
    today: date
    window_months: int = 3
    preview: bool = False


def _entry_id(source, payload):
    no = str(payload.get("patent_no") or "")
    year = payload.get("year")
    if no:
        return "%s#y%s" % (no, year if year not in (None, "") else "?")
    return source


def build_portfolio_entry(source, payload, today, library=None):
    if not isinstance(payload, dict):
        return PortfolioEntry(source, source, KIND_FAILED, reason=REASON_BAD_FORMAT)
    entry_id = _entry_id(source, payload)
    patent_no = str(payload.get("patent_no") or "")
    if not patent_no:
        return PortfolioEntry(source, entry_id, KIND_FAILED,
                              reason=REASON_BAD_FORMAT)
    type_raw = payload.get("patent_type")
    if type_raw in (None, ""):
        return PortfolioEntry(source, entry_id, KIND_FAILED, patent_no=patent_no,
                              reason=REASON_BAD_FORMAT)
    try:
        patent_type = parse_patent_type(str(type_raw))
    except ValueError:
        return PortfolioEntry(source, entry_id, KIND_FAILED, patent_no=patent_no,
                              reason=REASON_BAD_FORMAT)
    try:
        year = int(payload.get("year"))
    except (TypeError, ValueError):
        return PortfolioEntry(source, entry_id, KIND_FAILED, patent_no=patent_no,
                              patent_type=patent_type.value,
                              reason=REASON_BAD_FORMAT)
    if year < 1:
        return PortfolioEntry(source, entry_id, KIND_FAILED, patent_no=patent_no,
                              patent_type=patent_type.value,
                              reason=REASON_BAD_FORMAT)
    due_raw = payload.get("due_on") or ""
    try:
        due_on = date.fromisoformat(str(due_raw))
    except ValueError:
        return PortfolioEntry(source, entry_id, KIND_FAILED, patent_no=patent_no,
                              patent_type=patent_type.value, year=year,
                              reason=REASON_BAD_FORMAT)
    paid_raw = str(payload.get("paid_on") or "")
    paid_on = None
    if paid_raw:
        try:
            paid_on = date.fromisoformat(paid_raw)
        except ValueError:
            return PortfolioEntry(source, entry_id, KIND_FAILED,
                                  patent_no=patent_no,
                                  patent_type=patent_type.value, year=year,
                                  due_on=due_on.isoformat(),
                                  reason=REASON_BAD_FORMAT)
    amount = None
    warnings = []
    if library is not None:
        annuity_result = compute_annuity(library, patent_type, year)
        if annuity_result.computed and annuity_result.amount is not None:
            amount = annuity_result.amount
        else:
            warnings.append("年费金额未判定: %s" % ", ".join(annuity_result.reasons))
    days_until_due = (due_on - today).days
    if paid_on is not None:
        kind = KIND_SETTLED
    elif days_until_due < 0:
        kind = KIND_UNPAID
    else:
        kind = KIND_NOT_DUE
    return PortfolioEntry(source, entry_id, kind, patent_no, patent_type.value,
                          year, due_on.isoformat(),
                          paid_on.isoformat() if paid_on is not None else "",
                          days_until_due, amount)


def scan_portfolio(request, library=None):
    entries = []
    failed = []
    for source, payload in request.sources:
        if payload is None:
            entry = PortfolioEntry(source, source, KIND_FAILED,
                                   reason=REASON_BAD_FORMAT)
        else:
            try:
                entry = build_portfolio_entry(source, payload, request.today, library)
            except Exception:
                entry = PortfolioEntry(source, source, KIND_FAILED,
                                       reason=REASON_BAD_FORMAT)
        entries.append(entry)
        if entry.kind == KIND_FAILED:
            failed.append(entry)
    live = [e for e in entries if e.kind != KIND_FAILED]
    settled = tuple(sorted(e.id for e in live if e.kind == KIND_SETTLED))
    unpaid = tuple(sorted(e.id for e in live if e.kind == KIND_UNPAID))
    not_due = tuple(sorted(e.id for e in live if e.kind == KIND_NOT_DUE))
    upper = request.window_months * 31
    due_soon = tuple(sorted(
        (e for e in live if e.kind == KIND_NOT_DUE
         and 0 <= (e.days_until_due or 0) <= upper),
        key=lambda e: (e.days_until_due or 0, e.id)))
    return PortfolioResult(request.today.isoformat(), request.window_months,
                           tuple(sorted(entries, key=lambda e: e.id)),
                           tuple(sorted(failed, key=lambda e: e.id)),
                           settled, unpaid, not_due, due_soon)


def content_fingerprint(payload):
    relevant = {"patent_no": payload.get("patent_no"),
                "year": payload.get("year"),
                "due_on": payload.get("due_on")}
    blob = _json.dumps(relevant, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


__all__ = ["LateRequest", "ReductionRequest", "PortfolioRequest", "parse_applicants",
           "compute_annuity", "compute_late", "compute_reduction", "scan_portfolio",
           "add_calendar_months", "overdue_months_between", "find_tier",
           "tiers_from_entry", "thresholds_for_year", "applicant_eligible",
           "content_fingerprint", "build_portfolio_entry", "entry_key_for",
           "ENTRY_PREFIX", "RELATED_FEE_KEYS"]