"""领域模型（迁自来源 ``domain.models`` 的判定子集）。

金额一律 ``Decimal``：构造时显式拒收 ``float``（1 分差异必须可检出）。
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

MONEY_QUANTUM = Decimal("0.01")


def quantize_amount(value):
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


class PatentType(str, Enum):
    INVENTION = "invention"
    UTILITY_MODEL = "utility_model"
    DESIGN = "design"
    DESIGN_INTL = "design_intl"


PATENT_TYPE_LABELS = {
    PatentType.INVENTION: "发明专利",
    PatentType.UTILITY_MODEL: "实用新型专利",
    PatentType.DESIGN: "外观设计专利",
    PatentType.DESIGN_INTL: "外观设计国际注册",
}


def parse_patent_type(raw):
    text = (raw or "").strip()
    for member in PatentType:
        if text == member.value or text == PATENT_TYPE_LABELS[member]:
            return member
    aliases = {
        "发明": PatentType.INVENTION,
        "实用新型": PatentType.UTILITY_MODEL,
        "外观设计": PatentType.DESIGN,
        "外观设计国际注册": PatentType.DESIGN_INTL,
        "invention_patent": PatentType.INVENTION,
        "utility": PatentType.UTILITY_MODEL,
        "design_patent": PatentType.DESIGN,
    }
    if text in aliases:
        return aliases[text]
    raise ValueError("专利类型不识别: %r" % (raw,))


def _reject_float(value, where):
    if isinstance(value, float):
        raise TypeError("%s 金额必须是 Decimal，收到 float：%r" % (where, value))


@dataclass(frozen=True)
class FeeBasis:
    ruleset_id: str
    ruleset_version: str
    entry_key: str
    doc_no: str
    clause: str
    url: str
    retrieved: str

    def coordinate(self):
        return "%s@%s#%s" % (self.ruleset_id, self.ruleset_version, self.entry_key)

    def as_dict(self):
        return {
            "ruleset_id": self.ruleset_id, "ruleset_version": self.ruleset_version,
            "entry_key": self.entry_key, "doc_no": self.doc_no,
            "clause": self.clause, "url": self.url, "retrieved": self.retrieved,
            "coordinate": self.coordinate(),
        }


@dataclass(frozen=True)
class Tier:
    from_year: int
    to_year: int
    amount: Decimal
    label: str = ""

    def __post_init__(self):
        _reject_float(self.amount, "Tier.amount")
        if self.from_year > self.to_year:
            raise ValueError("阶梯区间非法: %d-%d" % (self.from_year, self.to_year))

    def contains(self, year):
        return self.from_year <= year <= self.to_year

    def as_dict(self):
        return {"from_year": self.from_year, "to_year": self.to_year,
                "amount": str(self.amount), "label": self.label}


@dataclass(frozen=True)
class AnnuityResult:
    patent_type: PatentType
    year: int
    amount: object
    tier: object
    basis: object
    reasons: tuple = ()
    warnings: tuple = ()
    steps: tuple = ()
    coordinate: dict = field(default_factory=dict)

    def __post_init__(self):
        _reject_float(self.amount, "AnnuityResult.amount")

    @property
    def computed(self):
        return self.amount is not None


@dataclass(frozen=True)
class LateResult:
    patent_type: PatentType
    year: int
    due_on: str
    paid_on: str
    overdue_months: object
    month_basis: str
    grace_months: object
    full_annuity: object
    monthly_rate: object
    surcharge: object
    payable: object
    exceeds_cap: bool
    annuity_entry_key: str
    basis: object
    related_fees: tuple = ()
    reasons: tuple = ()
    warnings: tuple = ()
    steps: tuple = ()
    coordinate: dict = field(default_factory=dict)

    def __post_init__(self):
        for name in ("full_annuity", "surcharge", "payable"):
            _reject_float(getattr(self, name), "LateResult." + name)

    @property
    def computed(self):
        return self.surcharge is not None


@dataclass(frozen=True)
class PolicyCandidate:
    policy: str
    rate: Decimal
    amount: Decimal

    def as_dict(self):
        return {"policy": self.policy, "rate": str(self.rate),
                "amount": str(self.amount)}


@dataclass(frozen=True)
class ReductionResult:
    patent_type: PatentType
    year: int
    as_of_year: int
    applicant_count: int
    combined: bool
    eligible: object
    thresholds: dict
    full_annuity: object
    reduction_rate: object
    candidates: tuple
    chosen: object
    no_double_benefit: str
    no_double_benefit_applied: bool
    payable: object
    reasons: tuple = ()
    steps: tuple = ()
    coordinate: dict = field(default_factory=dict)

    @property
    def computed(self):
        return self.payable is not None


@dataclass(frozen=True)
class PortfolioEntry:
    source: str
    id: str
    kind: str
    patent_no: str = ""
    patent_type: str = ""
    year: object = None
    due_on: str = ""
    paid_on: str = ""
    days_until_due: object = None
    amount: object = None
    reason: str = ""

    def __post_init__(self):
        _reject_float(self.amount, "PortfolioEntry.amount")

    def as_dict(self):
        return {"source": self.source, "id": self.id, "kind": self.kind,
                "patent_no": self.patent_no, "patent_type": self.patent_type,
                "year": self.year, "due_on": self.due_on, "paid_on": self.paid_on,
                "days_until_due": self.days_until_due,
                "amount": None if self.amount is None else str(self.amount),
                "reason": self.reason}


@dataclass(frozen=True)
class PortfolioResult:
    today: str
    window_months: int
    entries: tuple = ()
    failed: tuple = ()
    settled: tuple = ()
    unpaid: tuple = ()
    not_due: tuple = ()
    due_soon: tuple = ()

    @property
    def detected(self):
        return bool(self.unpaid or self.due_soon or self.failed)

    def as_dict(self):
        return {"today": self.today, "window_months": self.window_months,
                "entries": [e.as_dict() for e in self.entries],
                "failed": [e.as_dict() for e in self.failed],
                "settled": list(self.settled), "unpaid": list(self.unpaid),
                "not_due": list(self.not_due),
                "due_soon": [e.as_dict() for e in self.due_soon]}


__all__ = ["MONEY_QUANTUM", "quantize_amount", "PatentType", "PATENT_TYPE_LABELS",
           "parse_patent_type", "FeeBasis", "Tier", "AnnuityResult", "LateResult",
           "PolicyCandidate", "ReductionResult", "PortfolioEntry", "PortfolioResult"]