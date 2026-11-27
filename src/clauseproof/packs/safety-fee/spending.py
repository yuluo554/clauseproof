"""支出范围核查 + 使用进度（迁自来源 ``spending``）。

四态语义（不虚高）：``符合`` / ``部分符合`` / ``不符合`` / ``不适用``；
**无可适用条目 → ``未评估``**（"没查出问题" ≠ "没检查过"）。
``不适用`` 只保留给"原文明确写了例外情形"的项，绝不用于"缺材料/用户没做"。
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Sequence, Tuple

from .errors import NotCovered
from .tiered import quantize_money

STATE_COMPLIANT = "符合"
STATE_PARTIAL = "部分符合"
STATE_NONCOMPLIANT = "不符合"
STATE_NOT_APPLICABLE = "不适用"
STATE_NOT_ASSESSED = "未评估"

IN_SCOPE_INDUSTRIES = (
    "coal", "noncoal_mine", "oil_gas", "construction", "hazardous_chemicals",
    "transport", "metallurgy", "machinery", "fireworks", "civil_explosives",
    "weapons", "power",
)

NON_PASS_STATES = frozenset({STATE_NONCOMPLIANT, STATE_NOT_ASSESSED})


@dataclass(frozen=True)
class LedgerItem:
    item_key: str
    subject: str
    summary: str
    amount: Decimal


@dataclass(frozen=True)
class CheckFinding:
    item_key: str
    subject: str
    summary: str
    amount: Decimal
    state: str
    clause: str
    entry_id: str
    reason: str

    def as_dict(self) -> dict:
        return {
            "item_key": self.item_key,
            "subject": self.subject,
            "summary": self.summary,
            "amount": str(self.amount),
            "state": self.state,
            "clause": self.clause,
            "entry_id": self.entry_id,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CheckReport:
    industry_id: str
    findings: Tuple[CheckFinding, ...]
    redlines: Tuple[CheckFinding, ...]

    def counts(self) -> Dict[str, int]:
        out = {}
        for finding in self.findings:
            out[finding.state] = out.get(finding.state, 0) + 1
        return out

    def as_dict(self) -> dict:
        return {
            "industry_id": self.industry_id,
            "counts": self.counts(),
            "findings": [finding.as_dict() for finding in self.findings],
            "redlines": [finding.as_dict() for finding in self.redlines],
        }


def _match(entry: dict, item: LedgerItem) -> bool:
    keywords = entry.get("match_keywords") or []
    if not keywords:
        return False
    haystack = "%s %s" % (item.subject, item.summary)
    return any(str(keyword) in haystack for keyword in keywords)


def check_ledger(spending: dict, industry_id: str,
                 items: Sequence[LedgerItem]) -> CheckReport:
    if industry_id not in IN_SCOPE_INDUSTRIES:
        raise NotCovered("行业 %s 的支出范围核查属首期未覆盖（首期：%s），不臆造结论"
                         % (industry_id, "、".join(IN_SCOPE_INDUSTRIES)))
    entries = [entry for entry in spending.get("entries", [])
               if entry.get("industry_id") in (industry_id, "*")]

    findings: List[CheckFinding] = []
    for item in items:
        allowed = [entry for entry in entries
                   if entry.get("category") == "允许" and _match(entry, item)]
        forbidden = [entry for entry in entries
                     if entry.get("category") == "禁止" and _match(entry, item)]
        if forbidden:
            entry = forbidden[0]
            findings.append(CheckFinding(
                item_key=item.item_key, subject=item.subject, summary=item.summary,
                amount=item.amount, state=STATE_NONCOMPLIANT,
                clause=str(entry.get("clause", "")),
                entry_id=str(entry.get("entry_id", "")),
                reason="命中禁止性条目（红线）"))
        elif allowed:
            entry = allowed[0]
            findings.append(CheckFinding(
                item_key=item.item_key, subject=item.subject, summary=item.summary,
                amount=item.amount, state=STATE_COMPLIANT,
                clause=str(entry.get("clause", "")),
                entry_id=str(entry.get("entry_id", "")),
                reason="命中允许条目"))
        else:
            findings.append(CheckFinding(
                item_key=item.item_key, subject=item.subject, summary=item.summary,
                amount=item.amount, state=STATE_NOT_ASSESSED, clause="", entry_id="",
                reason="无可适用条目（**未评估**，非'符合'）"))

    redlines = tuple(finding for finding in findings
                     if finding.state == STATE_NONCOMPLIANT)
    return CheckReport(industry_id=industry_id, findings=tuple(findings),
                       redlines=redlines)


# ---------------------------------------------------------------------------
# 使用进度与披露
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ProgressResult:
    year: int
    accrued: Decimal
    used: Decimal
    ratio: Decimal
    threshold: Decimal
    applicable: bool
    disclosure_required: bool
    clause: str
    points: Tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "year": self.year,
            "accrued": str(self.accrued),
            "used": str(self.used),
            "ratio": str(self.ratio),
            "threshold": str(self.threshold),
            "applicable": self.applicable,
            "disclosure_required": self.disclosure_required,
            "clause": self.clause,
            "points": list(self.points),
        }


def compute_progress(progress_rules: dict, *, year: int, accrued: Decimal,
                     used: Decimal, threshold_id: str = "default") -> ProgressResult:
    node = None
    for candidate in progress_rules.get("thresholds", []):
        if candidate.get("threshold_id") == threshold_id:
            node = candidate
            break
    if node is None:
        from .errors import SchemaError
        raise SchemaError("progress.json 未登记门槛：%r" % threshold_id)

    threshold = Decimal(str(node["threshold"]))
    clause = str(node.get("clause", ""))
    points = tuple(node.get("disclosure_points", []))
    accrued = Decimal(accrued)
    used = Decimal(used)
    if accrued == 0:
        return ProgressResult(year=year, accrued=accrued, used=used, ratio=Decimal(0),
                              threshold=threshold, applicable=False,
                              disclosure_required=False, clause=clause, points=points)
    ratio = quantize_money(used / accrued)
    return ProgressResult(year=year, accrued=accrued, used=used, ratio=ratio,
                          threshold=threshold, applicable=True,
                          disclosure_required=ratio < threshold, clause=clause,
                          points=points)


__all__ = ["STATE_COMPLIANT", "STATE_PARTIAL", "STATE_NONCOMPLIANT",
           "STATE_NOT_APPLICABLE", "STATE_NOT_ASSESSED", "IN_SCOPE_INDUSTRIES",
           "NON_PASS_STATES", "LedgerItem", "CheckFinding", "CheckReport",
           "check_ledger", "ProgressResult", "compute_progress"]