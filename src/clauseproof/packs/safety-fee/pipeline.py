"""装配与编排（迁自来源 ``engine.pipeline`` 的判定链）。

- **装配边界**：manifest / units / 规则集 / 支出范围 / 进度门槛在这里读入并校验
  （逐文件 sha256），判定内核只收内存对象；
- **输入解释唯一实现**：``build_case`` 校验企业档案（缺字段即退出码 2）；
- 编排：计提（门控 → 依据选择 → 计算）/ 支出核查 / 使用进度 / 双版本对照。

批量扫描、报告导出、GUI、真值基准 runner 属交付/工具面，不迁。
"""

import os
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import List, Optional

from . import accrual, diff, registry, spending
from . import manifest as mf
from . import units as units_mod
from .errors import FeeError, MissingInput, SchemaError
from .gate import GateResult, check_scope
from .tiered import quantize_money

_CACHE = {}
_PROFILE_KEYS = {
    "enterprise_id", "enterprise_name", "industry_id", "year", "basis_kind",
    "basis_value", "basis_unit", "variant_id", "mine_type", "hazards",
    "businesses", "revenue", "purchased_cost", "is_contractor", "note",
}


@dataclass
class Case:
    enterprise_id: str
    enterprise_name: str
    industry_id: str
    year: int
    basis_kind: str
    basis_value: Decimal
    basis_unit: str
    variant_id: Optional[str] = None
    raw: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "enterprise_id": self.enterprise_id,
            "enterprise_name": self.enterprise_name,
            "industry_id": self.industry_id,
            "year": self.year,
            "basis_kind": self.basis_kind,
            "basis_value": str(self.basis_value),
            "basis_unit": self.basis_unit,
            "variant_id": self.variant_id,
        }


@dataclass
class CalcReport:
    coordinate: dict
    case: Case
    result: Optional[accrual.AccrualResult]
    gate: GateResult
    warnings: tuple
    basis: Optional[dict] = None
    inputs_required: tuple = ()

    def as_dict(self) -> dict:
        return {
            "coordinate": dict(self.coordinate),
            "case": self.case.as_dict(),
            "result": self.result.as_dict() if self.result else None,
            "gate": self.gate.as_dict(),
            "warnings": list(self.warnings),
            "basis": self.basis,
            "inputs_required": list(self.inputs_required),
        }


class Context:
    """一份随包数据目录的装配缓存。"""

    def __init__(self, root: str):
        self.root = root
        payload = mf.load_json(os.path.join(root, mf.MANIFEST_FILE))
        self.manifest = mf.build_manifest(root, payload)
        self.manifest.verify_integrity()
        self.units = units_mod.build_units(
            mf.load_json(os.path.join(root, mf.UNITS_FILE)))
        self._rulesets = {}
        self._spending = {}
        self._progress = {}

    def ruleset(self, ref: mf.RulesetRef) -> dict:
        if ref.version not in self._rulesets:
            self._rulesets[ref.version] = mf.load_json(
                os.path.join(self.root, mf.flat_name("ruleset", ref.version)))
        return self._rulesets[ref.version]

    def spending(self, ref: mf.RulesetRef) -> dict:
        if ref.version not in self._spending:
            self._spending[ref.version] = mf.load_json(
                os.path.join(self.root, mf.flat_name("spending", ref.version)))
        return self._spending[ref.version]

    def progress(self, ref: mf.RulesetRef) -> dict:
        if ref.version not in self._progress:
            self._progress[ref.version] = mf.load_json(
                os.path.join(self.root, mf.flat_name("progress", ref.version)))
        return self._progress[ref.version]

    def coordinate(self, ref: mf.RulesetRef) -> dict:
        return dict(ref.as_dict(), next_review=self.manifest.next_review,
                    review_interval=self.manifest.review_interval)


def context(data_dir=None) -> Context:
    root = data_dir or registry.data_dir()
    if root not in _CACHE:
        _CACHE[root] = Context(root)
    return _CACHE[root]


def reset_cache() -> None:
    _CACHE.clear()


def build_case(payload: dict) -> Case:
    if not hasattr(payload, "get"):
        raise MissingInput("企业档案必须是 JSON 对象")
    unknown = sorted(set(payload) - _PROFILE_KEYS)
    if unknown:
        raise MissingInput("企业档案含未知字段：%s" % ", ".join(unknown))
    required = ("enterprise_id", "enterprise_name", "industry_id", "year",
                "basis_kind", "basis_value", "basis_unit")
    missing = [key for key in required if payload.get(key) in (None, "")]
    if missing:
        raise MissingInput("企业档案缺少必填字段：%s" % ", ".join(missing))
    try:
        year = int(payload["year"])
        basis_value = Decimal(str(payload["basis_value"]))
    except (TypeError, ValueError, ArithmeticError):
        raise MissingInput("year / basis_value 不可解析")
    if year < 1900 or year > 2200:
        raise MissingInput("year 超出合理范围：%r" % payload["year"])
    return Case(
        enterprise_id=str(payload["enterprise_id"]),
        enterprise_name=str(payload["enterprise_name"]),
        industry_id=str(payload["industry_id"]),
        year=year,
        basis_kind=str(payload["basis_kind"]),
        basis_value=basis_value,
        basis_unit=str(payload["basis_unit"]),
        variant_id=(str(payload["variant_id"]) if payload.get("variant_id") else None),
        raw=dict(payload),
    )


def compute_calc(ctx: Context, case: Case, ref: Optional[mf.RulesetRef] = None) -> CalcReport:
    """计提：门控 → 依据选择 → 计算。

    ``ref`` 缺省按**年度锚定**（对外入口的唯一口径）；真值库用例按 ``ruleset_id``
    直算（来源 bench 口径）时由测试显式传入 ref——“锚定年度即锚定版本”不被削弱。
    """
    ref = ref or ctx.manifest.resolve_year(case.year)
    ruleset = ctx.ruleset(ref)
    gate = check_scope(ruleset, "calc", industry_id=case.industry_id)
    coordinate = ctx.coordinate(ref)

    warnings = []
    basis_value, unit_warning = ctx.units.to_base(case.basis_value, case.basis_unit)
    if unit_warning:
        warnings.append(unit_warning)

    if not gate.ok:
        return CalcReport(coordinate=coordinate, case=case, result=None, gate=gate,
                          warnings=tuple(warnings))

    decision = accrual.decide_basis(ruleset, case)
    if decision.inputs_required:
        return CalcReport(coordinate=coordinate, case=case, result=None, gate=gate,
                          warnings=tuple(warnings), basis=decision.as_dict(),
                          inputs_required=decision.inputs_required)

    variant_id = case.variant_id or decision.chosen_variant
    if decision.basis_value is not None:
        basis_value = Decimal(decision.basis_value)
        warnings.append("依据选择：第五十三条净额口径生效——依据量取净额 %s 元"
                        % decision.basis_value)

    request = accrual.AccrualRequest(
        industry_id=case.industry_id,
        basis_kind=case.basis_kind,
        basis_value=basis_value,
        basis_unit="CNY" if case.basis_kind != "output" else case.basis_unit,
        year=case.year,
        variant_id=variant_id,
        warnings=tuple(warnings),
    )
    result = accrual.compute(ruleset, request)
    merged = tuple(dict.fromkeys(warnings + list(result.warnings)))
    basis_payload = decision.as_dict() if decision.kind != "none" else None
    if basis_payload is not None and result.basis is None:
        result = replace(result, basis=basis_payload)
    return CalcReport(coordinate=coordinate, case=case, result=result, gate=gate,
                      warnings=merged, basis=basis_payload)


def build_ledger(raw_items) -> List[spending.LedgerItem]:
    if not isinstance(raw_items, list):
        raise MissingInput("ledger 必须是数组")
    items = []
    for index, raw in enumerate(raw_items):
        if not hasattr(raw, "get"):
            raise MissingInput("ledger[%d] 必须是对象" % index)
        missing = [key for key in ("item_key", "subject", "summary", "amount")
                   if raw.get(key) in (None, "")]
        if missing:
            raise MissingInput("ledger[%d] 缺字段：%s" % (index, ", ".join(missing)))
        try:
            amount = quantize_money(Decimal(str(raw["amount"])))
        except (ArithmeticError, ValueError):
            raise MissingInput("ledger[%d].amount 不可解析" % index)
        items.append(spending.LedgerItem(
            item_key=str(raw["item_key"]), subject=str(raw["subject"]),
            summary=str(raw["summary"]), amount=amount))
    return items


def check_spending(ctx: Context, case: Case, items) -> dict:
    ref = ctx.manifest.resolve_year(case.year)
    ruleset = ctx.ruleset(ref)
    rules = ctx.spending(ref)
    gate = check_scope(ruleset, "check", spending=rules)
    coordinate = ctx.coordinate(ref)
    if not gate.ok:
        return {"gate_blocked": True, "gate": gate, "coordinate": coordinate}
    report = spending.check_ledger(rules, case.industry_id, items)
    return {"gate_blocked": False, "gate": gate, "coordinate": coordinate,
            "report": report}


def progress_for(ctx: Context, case: Case, *, accrued: Decimal, used: Decimal,
                 threshold_id: str = "default") -> dict:
    ref = ctx.manifest.resolve_year(case.year)
    ruleset = ctx.ruleset(ref)
    rules = ctx.progress(ref)
    gate = check_scope(ruleset, "progress", progress=rules)
    coordinate = ctx.coordinate(ref)
    if not gate.ok:
        return {"gate_blocked": True, "gate": gate, "coordinate": coordinate}
    result = spending.compute_progress(rules, year=case.year, accrued=accrued,
                                       used=used, threshold_id=threshold_id)
    return {"gate_blocked": False, "gate": gate, "coordinate": coordinate,
            "report": result}


def diff_for(ctx: Context, from_year: int, to_year: int):
    old_ref = ctx.manifest.resolve_year(int(from_year))
    new_ref = ctx.manifest.resolve_year(int(to_year))
    if old_ref.ruleset_id == new_ref.ruleset_id:
        return None
    return diff.compare(ctx.ruleset(old_ref), ctx.ruleset(new_ref))


__all__ = ["Case", "CalcReport", "Context", "context", "reset_cache",
           "build_case", "compute_calc", "build_ledger", "check_spending",
           "progress_for", "diff_for", "FeeError", "SchemaError"]