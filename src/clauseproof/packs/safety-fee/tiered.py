"""超额累退分段计算（迁自来源 ``tiered``，边界口径不变）。

**边界归属**：段区间 ``[lower, upper)``（下含上不含），恰好等于分段点归**下一段**；
**逐段量化到分后求和**（不是"总额乘单一费率"）——这正是本器官存在的理由。
金额全链路 ``Decimal``，``ROUND_HALF_UP``。
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence, Tuple

Q2 = Decimal("0.01")


def quantize_money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Q2, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class TierSpec:
    lower: Decimal
    upper: Optional[Decimal]
    rate: Optional[Decimal]
    clause: str = ""
    status: str = "pending"


@dataclass(frozen=True)
class TierLine:
    index: int
    lower: Decimal
    upper: Optional[Decimal]
    base_in_tier: Decimal
    rate: Optional[Decimal]
    amount: Decimal
    clause: str

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "lower": str(self.lower),
            "upper": None if self.upper is None else str(self.upper),
            "base_in_tier": str(self.base_in_tier),
            "rate": None if self.rate is None else str(self.rate),
            "amount": str(self.amount),
            "clause": self.clause,
        }


def tier_base(value: Decimal, spec: TierSpec) -> Decimal:
    """段内依据量（``[lower, upper)``）。"""
    remaining = Decimal(value) - spec.lower
    if remaining <= 0:
        return Decimal(0)
    if spec.upper is None:
        return remaining
    return min(remaining, spec.upper - spec.lower)


def compute_tiered(value: Decimal, tiers: Sequence[TierSpec]) -> Tuple[TierLine, ...]:
    """逐段计算；``value <= 0`` 返回空明细；零段仍输出（保留完整结构）。"""
    value = Decimal(value)
    if value <= 0:
        return ()
    lines = []
    for index, spec in enumerate(tiers, start=1):
        base = tier_base(value, spec)
        rate = spec.rate if spec.rate is not None else Decimal(0)
        amount = quantize_money(base * rate)
        lines.append(TierLine(index=index, lower=spec.lower, upper=spec.upper,
                              base_in_tier=base, rate=spec.rate, amount=amount,
                              clause=spec.clause))
    return tuple(lines)


def tiered_total(lines: Sequence[TierLine]) -> Decimal:
    total = Decimal(0)
    for line in lines:
        total += line.amount
    return total


def tiers_from_rules(segments: Sequence[dict]) -> Tuple[TierSpec, ...]:
    def _dec(raw):
        if raw is None:
            return None
        return Decimal(str(raw))

    specs = []
    for segment in segments:
        specs.append(TierSpec(
            lower=_dec(segment.get("lower")) or Decimal(0),
            upper=_dec(segment.get("upper")),
            rate=_dec(segment.get("rate")),
            clause=str(segment.get("clause", "")),
            status=str(segment.get("status", "pending")),
        ))
    specs.sort(key=lambda spec: spec.lower)
    return tuple(specs)


__all__ = ["Q2", "quantize_money", "TierSpec", "TierLine", "tier_base",
           "compute_tiered", "tiered_total", "tiers_from_rules"]