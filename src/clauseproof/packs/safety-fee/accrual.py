"""计提引擎 + 依据选择判定（迁自来源 ``accrual``）。

四类计提机制：``by_output``（产量 × 单价）/ ``by_revenue_tiered``（营业收入超额累退）/
``by_revenue_rate``（营业收入单一比例）/ ``by_project_cost``（工程造价比例）。
标准值与适用条件**全部读规则包**；金额全链路 ``Decimal``，精确到分。

依据选择（第五十二/五十三条 + 矿井从高提取）：档案属性缺失即 ``inputs_required``
（运行时必索，退出码 2），**绝不静默取 0/1**；判定留痕进结果。
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Optional, Sequence, Tuple

from .errors import MissingInput, NotCovered, SchemaError
from .tiered import compute_tiered, quantize_money, tiered_total, tiers_from_rules

MECHANISMS = ("by_output", "by_revenue_tiered", "by_revenue_rate", "by_project_cost")
BASIS_KINDS = {
    "by_output": "output",
    "by_revenue_tiered": "revenue",
    "by_revenue_rate": "revenue",
    "by_project_cost": "project_cost",
}


@dataclass(frozen=True)
class AccrualRequest:
    industry_id: str
    basis_kind: str
    basis_value: Decimal
    basis_unit: str
    year: int
    variant_id: Optional[str] = None
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AccrualResult:
    amount: Decimal
    mechanism: str
    formula: str
    clause: str
    industry_name: str
    variant_name: Optional[str]
    tiers: Tuple = ()
    warnings: Tuple[str, ...] = ()
    provenance: Tuple[dict, ...] = ()
    basis: Optional[dict] = None

    def as_dict(self) -> dict:
        return {
            "amount": str(self.amount),
            "mechanism": self.mechanism,
            "formula": self.formula,
            "clause": self.clause,
            "industry_name": self.industry_name,
            "variant_name": self.variant_name,
            "tiers": [line.as_dict() for line in self.tiers],
            "warnings": list(self.warnings),
            "provenance": list(self.provenance),
            "basis": self.basis,
        }


def _find_industry(ruleset: dict, industry_id: str) -> dict:
    for item in ruleset.get("industries", []):
        if item.get("industry_id") == industry_id:
            return item
    raise SchemaError("规则包未登记行业：%r" % industry_id)


def _find_variant(industry: dict, variant_id: Optional[str]) -> Optional[dict]:
    variants = industry.get("variants") or []
    if not variants:
        return None
    if variant_id is None:
        if len(variants) == 1:
            return variants[0]
        raise MissingInput("行业 %s 有多个变体，须显式指定 variant_id（可选：%s）"
                           % (industry.get("industry_id"),
                              ", ".join(str(v.get("variant_id")) for v in variants)))
    for variant in variants:
        if variant.get("variant_id") == variant_id:
            return variant
    raise SchemaError("行业 %s 无此变体：%r" % (industry.get("industry_id"), variant_id))


def _require_value(node: dict, key: str, where: str):
    value = node.get(key)
    if value is None:
        raise SchemaError("%s 的 %r 未落值（status=%s）——门控应已拦截；未核对的值绝不参与计算"
                          % (where, key, node.get("status", "pending")))
    return value


def _prov_of(node: dict, industry: dict) -> list:
    prov = node.get("provenance") or industry.get("provenance") or []
    if isinstance(prov, dict):
        return [prov]
    return list(prov)


def compute(ruleset: dict, request: AccrualRequest) -> AccrualResult:
    industry = _find_industry(ruleset, request.industry_id)
    if industry.get("implementation") == "deferred":
        raise NotCovered("行业 %s（%s）属首期未覆盖范围，暂不输出结论"
                         % (industry.get("industry_id"),
                            industry.get("industry_name", "")))

    variant = _find_variant(industry, request.variant_id)
    node = variant or industry
    mechanism = node.get("mechanism") or industry.get("mechanism")
    if mechanism not in MECHANISMS:
        raise SchemaError("未知计提机制：%r（支持 %s）"
                          % (mechanism, ", ".join(MECHANISMS)))
    expected_kind = BASIS_KINDS[mechanism]
    if request.basis_kind != expected_kind:
        raise SchemaError("行业 %s 的计提机制为 %s，依据类型应为 %r，收到 %r"
                          % (request.industry_id, mechanism, expected_kind,
                             request.basis_kind))

    warnings = list(request.warnings)
    clause = str(node.get("clause") or industry.get("clause", ""))

    if mechanism == "by_output":
        unit_value = Decimal(str(_require_value(node, "value", "industry/variant")))
        amount = quantize_money(unit_value * Decimal(request.basis_value))
        formula = "%s（%s） × %s = %s 元" % (node.get("unit", ""), unit_value,
                                            request.basis_value, amount)
        return AccrualResult(amount=amount, mechanism=mechanism, formula=formula,
                             clause=clause, industry_name=industry.get("industry_name", ""),
                             variant_name=(node.get("variant_name") if variant else None),
                             warnings=tuple(warnings),
                             provenance=tuple(_prov_of(node, industry)))

    if mechanism == "by_revenue_tiered":
        segments = node.get("segments")
        if not segments:
            raise SchemaError("超额累退行业 %s 缺少 segments" % request.industry_id)
        specs = tiers_from_rules(segments)
        lines = compute_tiered(Decimal(request.basis_value), specs)
        amount = tiered_total(lines)
        parts = ["%s×%s" % (line.base_in_tier, line.rate)
                 for line in lines if line.base_in_tier > 0]
        formula = "超额累退逐段：%s = %s 元" % (" + ".join(parts), amount)
        return AccrualResult(amount=amount, mechanism=mechanism, formula=formula,
                             clause=clause, industry_name=industry.get("industry_name", ""),
                             variant_name=(node.get("variant_name") if variant else None),
                             tiers=lines, warnings=tuple(warnings),
                             provenance=tuple(_prov_of(node, industry)))

    rate = Decimal(str(_require_value(node, "rate", "industry/variant")))
    amount = quantize_money(rate * Decimal(request.basis_value))
    if mechanism == "by_revenue_rate":
        formula = "营业收入 %s 元 × 费率 %s = %s 元" % (request.basis_value, rate, amount)
    else:
        formula = "工程造价 %s 元 × 费率 %s = %s 元" % (request.basis_value, rate, amount)
    return AccrualResult(amount=amount, mechanism=mechanism, formula=formula,
                         clause=clause, industry_name=industry.get("industry_name", ""),
                         variant_name=(node.get("variant_name") if variant else None),
                         warnings=tuple(warnings),
                         provenance=tuple(_prov_of(node, industry)))


# ---------------------------------------------------------------------------
# 依据选择判定
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BasisDecision:
    kind: str
    clause: str = ""
    chosen_variant: Optional[str] = None
    chosen_industry: Optional[str] = None
    excluded: Tuple[Tuple[str, str], ...] = ()
    inputs_required: Tuple[str, ...] = ()
    basis_value: Optional[str] = None
    notes: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "clause": self.clause,
            "chosen_variant": self.chosen_variant,
            "chosen_industry": self.chosen_industry,
            "excluded": [{"item": item, "reason": reason}
                         for item, reason in self.excluded],
            "inputs_required": list(self.inputs_required),
            "basis_value": self.basis_value,
            "notes": list(self.notes),
        }


def choose_mine_variant(industry: dict, *, mine_type=None, hazards=()) -> BasisDecision:
    """矿井变体选择：多种灾害并存**从高提取**（severity 最大者）。"""
    variants = industry.get("variants") or []
    if not variants:
        return BasisDecision(kind="none", clause=str(industry.get("clause", "")))
    if mine_type is None and not hazards:
        return BasisDecision(kind="mine_variant",
                             clause=str(industry.get("clause", "")),
                             inputs_required=("mine_type",))
    matched = []
    for variant in variants:
        conditions = variant.get("conditions") or {}
        if "mine_type" in conditions and conditions["mine_type"] == mine_type:
            matched.append(variant)
        for hazard in hazards:
            if hazard in (conditions.get("hazards") or []):
                matched.append(variant)
    if not matched:
        raise MissingInput("行业 %s 未匹配到任何矿井变体（mine_type=%r, hazards=%r）"
                           % (industry.get("industry_id"), mine_type, list(hazards)))
    matched.sort(key=lambda v: (-int(v.get("severity", 0)), str(v.get("variant_id"))))
    chosen = matched[0]
    excluded = tuple((str(v.get("variant_id")), "severity 低于选定变体（从高提取）")
                     for v in matched[1:])
    return BasisDecision(kind="mine_variant",
                         clause=str(chosen.get("clause") or industry.get("clause", "")),
                         chosen_variant=str(chosen.get("variant_id")),
                         excluded=excluded,
                         notes=("多种灾害并存矿井从高提取",))


def resolve_multi_business(ruleset: dict, businesses: Sequence[dict]) -> BasisDecision:
    rule = (ruleset.get("basis_rules") or {}).get("multi_business") or {}
    clause = str(rule.get("clause", "第五十二条"))
    if not businesses:
        return BasisDecision(kind="none", clause=clause)
    can_separate = all(bool(b.get("separate_accounting")) for b in businesses)
    if can_separate:
        notes = tuple("分别核算：%s 营收 %s" % (b.get("industry_id"), b.get("revenue"))
                      for b in businesses)
        return BasisDecision(kind="multi_business", clause=clause, notes=notes)
    ranked = sorted(businesses,
                    key=lambda b: (-Decimal(str(b.get("revenue", 0))),
                                   str(b.get("industry_id"))))
    chosen = ranked[0]
    excluded = tuple((str(b.get("industry_id")),
                      "营业收入占比低于选定业务（不能分别核算）")
                     for b in ranked[1:])
    return BasisDecision(kind="multi_business", clause=clause,
                         chosen_industry=str(chosen.get("industry_id")),
                         excluded=excluded,
                         notes=("不能分别核算：按营业收入占比最高业务对合计营业收入计提",))


def resolve_net_basis(ruleset: dict, *, revenue, purchased_cost,
                      is_contractor: bool = False) -> BasisDecision:
    rule = (ruleset.get("basis_rules") or {}).get("net_basis") or {}
    clause = str(rule.get("clause", "第五十三条"))
    if not is_contractor:
        return BasisDecision(kind="none", clause=clause)
    if revenue is None or purchased_cost is None:
        return BasisDecision(kind="net_basis", clause=clause,
                             inputs_required=("revenue", "purchased_cost"))
    threshold = Decimal(str(rule.get("threshold", "0")))
    ratio = (purchased_cost / revenue) if revenue else Decimal(0)
    if ratio > threshold:
        net = revenue - purchased_cost
        return BasisDecision(
            kind="net_basis", clause=clause, basis_value=str(net),
            notes=("外购成本占营业收入 %s%%（> 规则包阈值 %s%%）→ 按净额计提"
                   % ((ratio * 100).quantize(Decimal("0.01")),
                      (threshold * 100).quantize(Decimal("0.01"))),))
    return BasisDecision(
        kind="net_basis", clause=clause,
        notes=("外购成本占营业收入 %s%%（未高于阈值 %s%%）→ 不适用净额口径"
               % ((ratio * 100).quantize(Decimal("0.01")),
                  (threshold * 100).quantize(Decimal("0.01"))),))


def decide_basis(ruleset: dict, case) -> BasisDecision:
    """优先级：跨行业（第五十二条）→ 净额口径（第五十三条）→ 矿井变体从高提取。"""
    raw = getattr(case, "raw", {}) or {}

    businesses = raw.get("businesses") or []
    if businesses:
        multi = resolve_multi_business(ruleset, businesses)
        if multi.chosen_industry:
            return multi
        if multi.kind != "none":
            return multi

    revenue = raw.get("revenue")
    if raw.get("is_contractor") or raw.get("purchased_cost") is not None:
        net = resolve_net_basis(
            ruleset,
            revenue=None if revenue is None else Decimal(str(revenue)),
            purchased_cost=(None if raw.get("purchased_cost") is None
                            else Decimal(str(raw["purchased_cost"]))),
            is_contractor=bool(raw.get("is_contractor")),
        )
        if net.inputs_required or net.basis_value is not None:
            return net

    industry = _find_industry(ruleset, case.industry_id)
    variants = industry.get("variants") or []
    if variants and any(v.get("conditions") for v in variants):
        if not case.variant_id:
            return choose_mine_variant(industry, mine_type=raw.get("mine_type"),
                                       hazards=raw.get("hazards") or ())
    return BasisDecision(kind="none", clause=str(industry.get("clause", "")))


__all__ = ["MECHANISMS", "BASIS_KINDS", "AccrualRequest", "AccrualResult",
           "compute", "BasisDecision", "choose_mine_variant",
           "resolve_multi_business", "resolve_net_basis", "decide_basis"]