"""器官 ``patent-annuity``：专利年费与费减判定（国家知识产权局现行费率表 × 费减政策）。

一句话：**给专利类型 + 缴费年度 + 时间事实/主体收入，算年费阶梯金额、滞纳金、
费减资格与减免额、组合排期；逐项挂政策条款坐标；未核对条目拒绝进入计算路径。**

来源判定面（年费阶梯 / 滞纳金 / 费减资格与多政策择一 / 组合排期）逐条迁移；
**GUI / 报告导出 / 批量文件读取 / 基准 runner / 真值库都是交付或工具面，不迁**
（器官零文件 IO——规则包由装配面 :mod:`registry` 读入，判定内核只收内存对象；
零环境变量、零时钟——组合排期的 ``today`` 由输入显式提供）。

判定账本口径（SKELETON-SPEC §3–§5）：

============================  ==========================================
来源结论                       本器官 verdict
============================  ==========================================
年费/滞纳金/费减计算完成         ``pass``（锚点：费率/政策条目；金额与过程入 evidence）
组合排期条目已缴清/未到期        ``pass``（锚点：该专利类型年费条目）
组合排期已到期未缴              ``fail``（锚点：该专利类型年费条目；阻断 → 1）
门控拒绝/未判定/坏格式           ``not_applicable``（非结论，不冒充金额）
============================  ==========================================

**与既有器官的边界**：本器官判「专利年费与费减」，依据国家知识产权局费率表与
财税〔2016〕78 号 / 公告 316 / 594；与 ``income-tax``（个税）、``labor-entitlement``
（劳动给付）、``invoice-ledger``（发票）零复用。

依据只从条文库取：``basis.anchor(clause_id)``；条文库版本 = 规则包核对日期
``2026-10-14``。版本不符 → ``ContractError``（退出码 3）；条款缺失 →
``BasisMissing``（本产品内核映射退出码 2）。
"""

from typing import Iterable, Mapping

from clauseproof.core.basis import Basis
from clauseproof.core.ledger import (
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Finding,
)
from clauseproof.core.registry import Pack, register

from . import calc
from . import registry as pack_data
from . import rules as R
from .errors import PatfeeError, RulesetError, UsageError
from .models import PatentType, parse_patent_type

SLUG = pack_data.SLUG
VERSION = pack_data.VERSION
SUMMARY = pack_data.SUMMARY

#: 输入必填字段（case_id = 一次判定运行的稳定标识）
INPUT_FIELDS = ("case_id",)

RULE_ANNUITY = "patent.annuity"
RULE_LATE = "patent.late"
RULE_REDUCTION = "patent.reduction"
RULE_PORTFOLIO = "patent.portfolio"

CLAUSE_GATE = "contract.gate"
CLAUSE_LEDGER = "contract.ledger"
CLAUSE_PREVIEW = "contract.preview"

_ALLOWED_KEYS = {"case_id", "patent", "late", "reduction", "portfolio", "note",
                 "preview"}
_INPUT_ERRORS = (PatfeeError, RulesetError, UsageError, ValueError, KeyError)


def _require_basis_version(basis: Basis) -> None:
    if basis.version != pack_data.VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据规则包核对日期 %s，条文库实为 %s"
            % (pack_data.VERSION, basis.version))


def _validate_subject(subject: Mapping):
    if not isinstance(subject, Mapping):
        raise ValueError("输入必须是 JSON 对象")
    unknown = sorted(set(subject) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError("输入含未知字段：%s" % ", ".join(unknown))
    if not str(subject.get("case_id") or "").strip():
        raise ValueError("输入缺少 case_id（一次判定运行的稳定标识）")
    if not any(key in subject for key in ("patent", "late", "reduction", "portfolio")):
        raise ValueError("输入至少需要 patent / late / reduction / portfolio 之一")
    return subject


def _ask(mapping, key, label):
    if not isinstance(mapping, Mapping):
        raise ValueError("%s 必须是对象" % label)
    if key not in mapping:
        raise ValueError("%s 缺少 %s" % (label, key))
    return mapping[key]


def _patent_type(mapping, label):
    try:
        return parse_patent_type(str(_ask(mapping, "patent_type", label)))
    except ValueError as exc:
        raise ValueError("%s：%s" % (label, exc))


def _year(mapping, label):
    try:
        year = int(_ask(mapping, "year", label))
    except (TypeError, ValueError):
        raise ValueError("%s.year 必须是整数" % label)
    if year < 1:
        raise ValueError("%s.year 必须 ≥ 1" % label)
    return year


def _annuity_findings(subject, library, basis, preview):
    spec = subject.get("patent")
    if spec is None:
        return []
    patent_type = _patent_type(spec, "patent")
    year = _year(spec, "patent")
    result = calc.compute_annuity(library, patent_type, year, preview=preview)
    if not result.computed:
        return [Finding(
            rule_id="%s:%s:%d" % (RULE_ANNUITY, patent_type.value, year),
            verdict=NOT_APPLICABLE,
            message="年费未判定（%s）" % "、".join(result.reasons),
            anchor=basis.anchor(CLAUSE_GATE),
            evidence={"patent_type": patent_type.value, "year": year,
                      "reasons": list(result.reasons),
                      "coordinate": result.coordinate},
        )]
    return [Finding(
        rule_id="%s:%s:%d" % (RULE_ANNUITY, patent_type.value, year),
        verdict=PASS,
        message="年费：%s 第 %d 年应缴 %s 元（区间 %d-%d 年）"
                % (patent_type.value, year, result.amount,
                   result.tier.from_year, result.tier.to_year),
        anchor=basis.anchor(result.basis.entry_key),
        evidence={"amount": str(result.amount), "tier": result.tier.as_dict(),
                  "basis": result.basis.as_dict(),
                  "warnings": list(result.warnings),
                  "steps": list(result.steps),
                  "coordinate": result.coordinate},
    )]


def _late_findings(subject, library, basis, preview):
    spec = subject.get("late")
    if spec is None:
        return []
    patent_type = _patent_type(spec, "late")
    year = _year(spec, "late")
    try:
        due_on = __import__("datetime").date.fromisoformat(
            str(_ask(spec, "due_on", "late")))
        paid_on = __import__("datetime").date.fromisoformat(
            str(_ask(spec, "paid_on", "late")))
    except ValueError:
        raise ValueError("late.due_on / paid_on 必须是 ISO 日期（YYYY-MM-DD）")
    request = calc.LateRequest(patent_type, year, due_on, paid_on, preview=preview)
    result = calc.compute_late(library, request)
    rule_id = "%s:%s:%d" % (RULE_LATE, patent_type.value, year)
    if not result.computed:
        return [Finding(
            rule_id=rule_id, verdict=NOT_APPLICABLE,
            message="滞纳金未判定（%s）" % "、".join(result.reasons),
            anchor=basis.anchor(CLAUSE_GATE),
            evidence={"reasons": list(result.reasons),
                      "coordinate": result.coordinate})]
    return [Finding(
        rule_id=rule_id, verdict=PASS,
        message="滞纳金：逾期 %d 个月，滞纳金 %s 元，应缴合计 %s 元%s"
                % (result.overdue_months, result.surcharge, result.payable,
                   "（超补缴上限，风险提示）" if result.exceeds_cap else ""),
        anchor=basis.anchor("late.monthly_rate"),
        evidence={"overdue_months": result.overdue_months,
                  "surcharge": str(result.surcharge),
                  "payable": str(result.payable),
                  "exceeds_cap": result.exceeds_cap,
                  "warnings": list(result.warnings),
                  "steps": list(result.steps),
                  "coordinate": result.coordinate},
    )]


def _reduction_findings(subject, library, basis, preview):
    spec = subject.get("reduction")
    if spec is None:
        return []
    patent_type = _patent_type(spec, "reduction")
    year = _year(spec, "reduction")
    try:
        as_of_year = int(_ask(spec, "as_of_year", "reduction"))
    except (TypeError, ValueError):
        raise ValueError("reduction.as_of_year 必须是整数")
    applicants = calc.parse_applicants(_ask(spec, "applicants", "reduction"))
    request = calc.ReductionRequest(
        patent_type, year, as_of_year, applicants,
        bool(spec.get("open_license", False)), preview=preview)
    result = calc.compute_reduction(library, request)
    rule_id = "%s:%s:%d" % (RULE_REDUCTION, patent_type.value, year)
    if not result.computed:
        return [Finding(
            rule_id=rule_id, verdict=NOT_APPLICABLE,
            message="费减未判定（%s）" % "、".join(result.reasons),
            anchor=basis.anchor(CLAUSE_GATE),
            evidence={"reasons": list(result.reasons),
                      "coordinate": result.coordinate})]
    anchor_id = "reduction.rate.combined" if result.combined \
        else "reduction.rate.sole"
    return [Finding(
        rule_id=rule_id, verdict=PASS,
        message="费减：%s，%d 名主体，实缴 %s 元%s"
                % ("合格" if result.eligible else "不合格（按全额缴纳）",
                   result.applicant_count, result.payable,
                   ("；选中 %s" % result.chosen.policy) if result.chosen else ""),
        anchor=basis.anchor(anchor_id),
        evidence={"eligible": result.eligible,
                  "combined": result.combined,
                  "thresholds": {k: str(v) for k, v in result.thresholds.items()},
                  "full_annuity": str(result.full_annuity),
                  "reduction_rate": None if result.reduction_rate is None
                  else str(result.reduction_rate),
                  "candidates": [c.as_dict() for c in result.candidates],
                  "chosen": None if result.chosen is None else result.chosen.as_dict(),
                  "no_double_benefit": result.no_double_benefit,
                  "payable": str(result.payable),
                  "steps": list(result.steps),
                  "coordinate": result.coordinate},
    )]


def _portfolio_findings(subject, library, basis, preview):
    spec = subject.get("portfolio")
    if spec is None:
        return []
    if not isinstance(spec, Mapping):
        raise ValueError("portfolio 必须是对象")
    unknown = sorted(set(spec) - {"today", "window_months", "items", "entries"})
    if unknown:
        raise ValueError("portfolio 含未知字段：%s" % ", ".join(unknown))
    try:
        today = __import__("datetime").date.fromisoformat(
            str(_ask(spec, "today", "portfolio")))
    except ValueError:
        raise ValueError("portfolio.today 必须是 ISO 日期（YYYY-MM-DD）")
    window = int(spec.get("window_months", 3))
    if window < 0:
        raise ValueError("portfolio.window_months 须为非负整数")
    raw_items = spec.get("items", spec.get("entries"))
    if not isinstance(raw_items, list):
        raise ValueError("portfolio.items 必须是数组")
    sources = []
    for idx, item in enumerate(raw_items):
        name = ""
        if isinstance(item, Mapping):
            name = str(item.get("patent_no") or "")
        sources.append((name or "item[%d]" % idx, item))
    request = calc.PortfolioRequest(tuple(sources), today, window, preview=preview)
    result = calc.scan_portfolio(request, library)
    findings = []
    due_ids = {e.id for e in result.due_soon}
    for entry in result.entries:
        anchor_id = CLAUSE_LEDGER
        if entry.patent_type:
            anchor_id = "annuity." + entry.patent_type
        if basis.clause(anchor_id) is None:
            anchor_id = CLAUSE_LEDGER
        if entry.kind == calc.KIND_UNPAID:
            verdict = FAIL
        elif entry.kind == calc.KIND_FAILED:
            verdict = NOT_APPLICABLE
        elif entry.id in due_ids:
            verdict = NOT_APPLICABLE
        else:
            verdict = PASS
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_PORTFOLIO, entry.id),
            verdict=verdict,
            message="组合排期 %s：%s%s"
                    % (entry.id, entry.kind,
                       "（窗口内到期）" if entry.id in due_ids else ""),
            anchor=basis.anchor(anchor_id),
            evidence=entry.as_dict(),
        ))
    findings.append(Finding(
        rule_id="%s:summary" % RULE_PORTFOLIO,
        verdict=PASS,
        message="组合排期：%d 件（已缴清 %d / 未缴 %d / 未到期 %d / 失败 %d）"
                % (len(result.entries), len(result.settled), len(result.unpaid),
                   len(result.not_due), len(result.failed)),
        anchor=basis.anchor(CLAUSE_LEDGER),
        evidence={"counts": {"settled": len(result.settled),
                             "unpaid": len(result.unpaid),
                             "not_due": len(result.not_due),
                             "failed": len(result.failed),
                             "due_soon": len(result.due_soon)}},
    ))
    return findings


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    _require_basis_version(basis)
    _validate_subject(subject)
    preview = bool(subject.get("preview", False))
    try:
        library = R.load_library(pack_data.DATA_DIR)
        findings = []
        findings.extend(_annuity_findings(subject, library, basis, preview))
        findings.extend(_late_findings(subject, library, basis, preview))
        findings.extend(_reduction_findings(subject, library, basis, preview))
        findings.extend(_portfolio_findings(subject, library, basis, preview))
    except _INPUT_ERRORS as exc:
        raise ValueError(str(exc))
    return tuple(findings)


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate"]