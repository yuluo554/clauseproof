"""器官 ``patent-annuity`` 判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源判定面（年费阶梯 / 滞纳金 / 费减资格与多政策择一 / 组合排期 /
规则加载与 status 门控）逐条搬，断言落在「金额 + 口径 + 依据」上。来源判定层
（D1 + D18 机械选 8 文件 / 实跑 124 passed / AST 110）逐文件处置见
``docs/patent-annuity.md`` §6。

来源仓只读；合成规则库一律内存注入，不写真实标准内容。
"""

import importlib
import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from clauseproof import cli as cp_cli  # noqa: E402
from clauseproof.core.basis import Basis, BasisMissing  # noqa: E402
from clauseproof.core.ledger import (  # noqa: E402
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Report,
)

PACK_MOD = importlib.import_module("clauseproof.packs.patent-annuity")
MODELS = importlib.import_module("clauseproof.packs.patent-annuity.models")
RULES = importlib.import_module("clauseproof.packs.patent-annuity.rules")
CALC = importlib.import_module("clauseproof.packs.patent-annuity.calc")
REG = importlib.import_module("clauseproof.packs.patent-annuity.registry")
ERRS = importlib.import_module("clauseproof.packs.patent-annuity.errors")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "patent-annuity")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "patent-annuity")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
ANNUITY_SAMPLE = os.path.join(SAMPLES, "annuity.json")
LATE_SAMPLE = os.path.join(SAMPLES, "late.json")
REDUCTION_SAMPLE = os.path.join(SAMPLES, "reduction.json")
PORTFOLIO_SAMPLE = os.path.join(SAMPLES, "portfolio.json")
FULL_SAMPLE = os.path.join(SAMPLES, "case-full.json")

PatentType = MODELS.PatentType
IT = PatentType.INVENTION
UM = PatentType.UTILITY_MODEL
DS = PatentType.DESIGN

RulesetError = ERRS.RulesetError
OutOfRangeError = ERRS.OutOfRangeError
UsageError = ERRS.UsageError


def lib():
    return RULES.load_library(DATA_DIR)


def basis():
    return Basis.from_json(BASIS_PATH)


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def evaluate(subject):
    return tuple(PACK_MOD.evaluate(subject, basis()))


def report(findings):
    return Report(product="clauseproof", organ=SLUG,
                  organ_version=PACK_MOD.VERSION, subject="test",
                  findings=findings)


def tiny_library(status="verified"):
    raw_rs = {
        "schema": "patfee.ruleset/v1",
        "id": "probe",
        "version": "v1",
        "title": "probe",
        "doc_no": "probe",
        "entries": [
            {"key": "annuity.invention", "label": "probe", "kind": "ladder",
             "status": status, "scopes": ["calc"],
             "ladder": [{"from_year": 1, "to_year": 3, "amount": 900, "label": "1-3"},
                        {"from_year": 4, "to_year": 6, "amount": 1200, "label": "4-6"}],
             "basis": {"doc_no": "d", "clause": "c", "url": "http://x",
                       "retrieved": "2026-10-14"}},
            {"key": "late.monthly_rate", "label": "rate", "kind": "scalar",
             "status": status, "scopes": ["late"], "value": "0.05",
             "basis": {"doc_no": "d", "clause": "c", "url": "http://x",
                       "retrieved": "2026-10-14"}},
            {"key": "late.grace_months", "label": "grace", "kind": "scalar",
             "status": status, "scopes": ["late"], "value": 6,
             "basis": {"doc_no": "d", "clause": "c", "url": "http://x",
                       "retrieved": "2026-10-14"}},
            {"key": "late.month_basis", "label": "basis", "kind": "scalar",
             "status": status, "scopes": ["late"], "value": "calendar_month",
             "basis": {"doc_no": "d", "clause": "c", "url": "http://x",
                       "retrieved": "2026-10-14"}},
        ],
    }
    manifest = {"schema": "patfee.rules.manifest/v1", "rulesets": [],
                "scopes": ["calc", "late"], "benchmarks": {}}
    return RULES.RuleLibrary(manifest, [RULES.Ruleset(raw_rs)], Path("."))


# ==========================================================================
# §一 模型与类型（12）
# ==========================================================================
def test_patent_type_parse_enum_value():
    assert MODELS.parse_patent_type("invention") == IT


def test_patent_type_parse_chinese_label():
    assert MODELS.parse_patent_type("实用新型专利") == UM


def test_patent_type_parse_alias():
    assert MODELS.parse_patent_type("外观设计") == DS


def test_patent_type_parse_unknown_raises():
    with pytest.raises(ValueError):
        MODELS.parse_patent_type("pct")


def test_patent_type_labels_cover_all():
    for member in PatentType:
        assert member in MODELS.PATENT_TYPE_LABELS


def test_tier_contains_is_double_closed():
    tier = MODELS.Tier(1, 3, Decimal("900"))
    assert tier.contains(1) and tier.contains(3)
    assert not tier.contains(4)


def test_tier_rejects_inverted_span():
    with pytest.raises(ValueError):
        MODELS.Tier(4, 3, Decimal("900"))


def test_tier_rejects_float_amount():
    with pytest.raises(TypeError):
        MODELS.Tier(1, 3, 900.0)


def test_quantize_amount_half_up():
    assert str(MODELS.quantize_amount(Decimal("1200.005"))) == "1200.01"


def test_fee_basis_coordinate():
    b = MODELS.FeeBasis("fee_schedule", "v2024", "annuity.invention", "doc",
                        "clause", "url", "2026-10-14")
    assert b.coordinate() == "fee_schedule@v2024#annuity.invention"


def test_annuity_result_rejects_float():
    with pytest.raises(TypeError):
        MODELS.AnnuityResult(IT, 5, 1.0, None, None)


def test_late_result_rejects_float():
    with pytest.raises(TypeError):
        MODELS.LateResult(IT, 5, "d", "p", 1, "calendar_month", 6,
                          Decimal("1"), Decimal("1"), 1.0, None, False,
                          "k", None)


# ==========================================================================
# §二 规则加载（14）
# ==========================================================================
def test_library_has_four_rulesets():
    assert len(lib().rulesets) == 4


def test_library_ids():
    assert sorted(lib().rulesets) == ["fee_schedule", "reduction_316",
                                      "reduction_594", "reduction_78"]


def test_library_entry_count_32():
    total = sum(len(rs.entries) for rs in lib().rulesets.values())
    assert total == 32


def test_library_all_entries_verified():
    assert lib().status_counts()["verified"] == 32


def test_library_entry_lookup():
    assert lib().entry("annuity.invention").verified
    assert lib().entry("nope") is None


def test_library_entries_with_prefix():
    keys = [e.key for e in lib().entries_with_prefix("annuity.")]
    assert sorted(keys) == ["annuity.design", "annuity.invention",
                            "annuity.utility_model"]


def test_library_ruleset_unknown_raises():
    with pytest.raises(RulesetError):
        lib().ruleset("nope")


def test_library_benchmark_threshold():
    cfg = lib().benchmark_threshold("b1_ladder")
    assert cfg["min_pass_rate"] == "1.0"


def test_library_benchmark_missing_raises():
    with pytest.raises(RulesetError):
        lib().benchmark_threshold("b9")


def test_library_coordinate_shape():
    coordinate = lib().coordinate()
    assert coordinate["manifest_schema"] == "patfee.rules.manifest/v1"
    assert len(coordinate["rulesets"]) == 4


def test_entry_decimal_value():
    assert lib().entry("late.monthly_rate").decimal() == Decimal("0.05")


def test_entry_decimal_none_for_unknown_entry():
    assert lib().entry("late.missing_never") is None


def test_ruleset_status_counts():
    counts = lib().ruleset("fee_schedule").status_counts()
    assert counts["verified"] == 16


def test_load_library_missing_manifest(tmp_path):
    with pytest.raises(FileNotFoundError):
        RULES.load_library(str(tmp_path))


# ==========================================================================
# §三 status 门控（12）
# ==========================================================================
def test_gate_verified_allows():
    decision = RULES.evaluate_keys(lib(), ["annuity.invention"], RULES.SCOPE_CALC)
    assert decision.allowed


def test_gate_pending_blocks():
    probe = tiny_library("pending")
    decision = RULES.evaluate_keys(probe, ["annuity.invention"], RULES.SCOPE_CALC)
    assert not decision.allowed
    assert "gated_pending" in decision.reasons


def test_gate_pending_preview_permits_but_marks():
    probe = tiny_library("pending")
    decision = RULES.evaluate_keys(probe, ["annuity.invention"],
                                   RULES.SCOPE_CALC, preview=True)
    assert decision.allowed
    assert decision.permitted_unverified == ["annuity.invention"]


def test_gate_scope_isolation():
    probe = tiny_library("pending")
    decision = RULES.evaluate_keys(probe, ["annuity.invention"], RULES.SCOPE_LATE)
    assert decision.allowed


def test_gate_input_required_blocks_without_input():
    probe = tiny_library("input_required")
    decision = RULES.evaluate_keys(probe, ["annuity.invention"], RULES.SCOPE_CALC)
    assert not decision.allowed
    assert decision.required_inputs == ["annuity.invention"]


def test_gate_input_required_satisfied():
    probe = tiny_library("input_required")
    decision = RULES.evaluate_keys(probe, ["annuity.invention"], RULES.SCOPE_CALC,
                                   provided_inputs=["annuity.invention"])
    assert decision.allowed


def test_gate_untracked_entry():
    decision = RULES.evaluate_keys(lib(), ["nope"], RULES.SCOPE_CALC)
    assert not decision.allowed
    assert "untracked_entry" in decision.reasons


def test_gate_statuses_recorded():
    decision = RULES.evaluate_keys(lib(), ["annuity.invention"], RULES.SCOPE_CALC)
    assert decision.statuses["annuity.invention"] == "verified"


def test_gate_decision_scope():
    decision = RULES.evaluate_keys(lib(), ["late.monthly_rate"], RULES.SCOPE_LATE)
    assert decision.scope == "late"


def test_gate_missing_value_blocks():
    raw = {"schema": "patfee.ruleset/v1", "id": "p", "version": "v1",
           "title": "p", "doc_no": "p",
           "entries": [{"key": "annuity.invention", "kind": "scalar",
                        "status": "verified", "scopes": ["calc"], "value": None,
                        "basis": {"doc_no": "d", "clause": "c", "url": "u",
                                  "retrieved": "r"}}]}
    manifest = {"schema": "patfee.rules.manifest/v1", "rulesets": [],
                "scopes": ["calc"], "benchmarks": {}}
    probe = RULES.RuleLibrary(manifest, [RULES.Ruleset(raw)], Path("."))
    decision = RULES.evaluate_keys(probe, ["annuity.invention"], RULES.SCOPE_CALC)
    assert "missing_value" in decision.reasons


def test_gate_rejects_bad_entry_status():
    raw = {"schema": "patfee.ruleset/v1", "id": "p", "version": "v1",
           "title": "p", "doc_no": "p",
           "entries": [{"key": "k", "status": "unknown", "scopes": ["calc"],
                        "value": 1}]}
    with pytest.raises(RulesetError):
        RULES.Ruleset(raw)


def test_production_all_verified_passes():
    decision = RULES.evaluate_keys(lib(), ["annuity.invention"], RULES.SCOPE_CALC)
    assert decision.allowed and not decision.required_inputs


# ==========================================================================
# §四 年费阶梯（18）
# ==========================================================================
def test_find_tier_boundaries_inclusive():
    tiers = [MODELS.Tier(1, 3, Decimal("900")), MODELS.Tier(4, 6, Decimal("1200"))]
    assert CALC.find_tier(tiers, 3).amount == Decimal("900")
    assert CALC.find_tier(tiers, 4).amount == Decimal("1200")


def test_find_tier_out_of_range():
    tiers = [MODELS.Tier(1, 3, Decimal("900"))]
    with pytest.raises(OutOfRangeError):
        CALC.find_tier(tiers, 4)


def test_annuity_invention_year1():
    result = CALC.compute_annuity(lib(), IT, 1)
    assert result.amount == Decimal("900.00")


def test_annuity_invention_year4():
    assert CALC.compute_annuity(lib(), IT, 4).amount == Decimal("1200.00")


def test_annuity_invention_year9():
    assert CALC.compute_annuity(lib(), IT, 9).amount == Decimal("2000.00")


def test_annuity_invention_year10():
    assert CALC.compute_annuity(lib(), IT, 10).amount == Decimal("4000.00")


def test_annuity_invention_year16():
    assert CALC.compute_annuity(lib(), IT, 16).amount == Decimal("8000.00")


def test_annuity_utility_year1():
    assert CALC.compute_annuity(lib(), UM, 1).amount == Decimal("600.00")


def test_annuity_utility_year6():
    assert CALC.compute_annuity(lib(), UM, 6).amount == Decimal("1200.00")


def test_annuity_design_year11():
    assert CALC.compute_annuity(lib(), DS, 11).amount == Decimal("3000.00")


def test_annuity_design_international_missing_entry():
    result = CALC.compute_annuity(lib(), PatentType.DESIGN_INTL, 1)
    assert result.amount is None
    assert "untracked_entry" in result.reasons


def test_annuity_out_of_range_30():
    result = CALC.compute_annuity(lib(), IT, 30, preview=True)
    assert result.amount is None
    assert "out_of_range" in result.reasons


def test_annuity_tier_label_and_span():
    result = CALC.compute_annuity(lib(), IT, 5)
    assert (result.tier.from_year, result.tier.to_year) == (4, 6)


def test_annuity_basis_entry_key():
    result = CALC.compute_annuity(lib(), IT, 5)
    assert result.basis.entry_key == "annuity.invention"


def test_annuity_preview_verified_has_no_warning():
    result = CALC.compute_annuity(lib(), IT, 5, preview=True)
    assert result.amount == Decimal("1200.00")
    assert result.warnings == ()


def test_annuity_pending_blocks():
    result = CALC.compute_annuity(tiny_library("pending"), IT, 5)
    assert result.amount is None
    assert "gated_pending" in result.reasons
    assert result.basis is not None


def test_annuity_pending_preview_computes_with_warning():
    result = CALC.compute_annuity(tiny_library("pending"), IT, 5, preview=True)
    assert result.amount == Decimal("1200.00")
    assert result.warnings


def test_annuity_steps_recorded():
    result = CALC.compute_annuity(lib(), IT, 5)
    assert result.steps and any("命中区间" in step for step in result.steps)


# ==========================================================================
# §五 滞纳金（18）
# ==========================================================================
def test_add_calendar_months_clamps():
    assert str(CALC.add_calendar_months(date(2026, 1, 31), 1)) == "2026-02-28"
    assert str(CALC.add_calendar_months(date(2024, 1, 31), 1)) == "2024-02-29"


def test_overdue_months_calendar():
    months, _ = CALC.overdue_months_between(date(2019, 5, 4), date(2019, 7, 4),
                                            "calendar_month")
    assert months == 2


def test_overdue_months_partial_not_counted():
    months, _ = CALC.overdue_months_between(date(2019, 5, 4), date(2019, 6, 3),
                                            "calendar_month")
    assert months == 0


def test_overdue_months_thirty_day():
    months, _ = CALC.overdue_months_between(date(2026, 1, 1), date(2026, 3, 2),
                                            "thirty_day")
    assert months == 2


def test_overdue_months_unknown_basis_raises():
    with pytest.raises(Exception, match="month_basis"):
        CALC.overdue_months_between(date(2026, 1, 1), date(2026, 2, 1), "fortnight")


def test_late_one_month():
    result = CALC.compute_late(lib(), CALC.LateRequest(IT, 5, date(2020, 5, 4),
                                                       date(2020, 6, 4)))
    assert result.overdue_months == 1
    assert result.surcharge == Decimal("60.00")


def test_late_two_months():
    result = CALC.compute_late(lib(), CALC.LateRequest(IT, 5, date(2020, 5, 4),
                                                       date(2020, 7, 4)))
    assert result.surcharge == Decimal("120.00")
    assert result.payable == Decimal("1320.00")


def test_late_at_cap_not_exceeded():
    result = CALC.compute_late(lib(), CALC.LateRequest(IT, 5, date(2020, 1, 4),
                                                       date(2020, 7, 4)))
    assert result.overdue_months == 6
    assert result.exceeds_cap is False
    assert result.reasons == ()


def test_late_over_cap_still_computes():
    result = CALC.compute_late(lib(), CALC.LateRequest(IT, 5, date(2020, 1, 4),
                                                       date(2020, 8, 4)))
    assert result.overdue_months == 7
    assert result.exceeds_cap is True
    assert "late_exceeds_cap" in result.reasons
    assert result.computed
    assert any("风险测算" in w for w in result.warnings)


def test_late_not_overdue_is_zero():
    result = CALC.compute_late(lib(), CALC.LateRequest(IT, 5, date(2026, 5, 4),
                                                       date(2026, 5, 4)))
    assert result.overdue_months == 0
    assert result.surcharge == Decimal("0.00")


def test_late_month_basis_from_rules():
    result = CALC.compute_late(lib(), CALC.LateRequest(IT, 5, date(2020, 5, 4),
                                                       date(2020, 7, 4)))
    assert result.month_basis == "calendar_month"


def test_late_rate_from_rules():
    result = CALC.compute_late(lib(), CALC.LateRequest(IT, 5, date(2020, 5, 4),
                                                       date(2020, 7, 4)))
    assert result.monthly_rate == Decimal("0.05")


def test_late_grace_from_rules():
    result = CALC.compute_late(lib(), CALC.LateRequest(IT, 5, date(2020, 5, 4),
                                                       date(2020, 7, 4)))
    assert result.grace_months == 6


def test_late_related_fees_listed():
    result = CALC.compute_late(lib(), CALC.LateRequest(IT, 5, date(2020, 1, 4),
                                                       date(2020, 8, 4)))
    keys = {fee[0] for fee in result.related_fees}
    assert "check.fee.ruc" in keys
    assert "check.fee.evaluation_report" in keys


def test_late_payable_excludes_related_fees():
    result = CALC.compute_late(lib(), CALC.LateRequest(IT, 5, date(2020, 1, 4),
                                                       date(2020, 8, 4)))
    assert result.payable == result.full_annuity + result.surcharge


def test_late_reuses_passed_annuity():
    annuity = CALC.compute_annuity(lib(), IT, 5)
    result = CALC.compute_late(lib(), CALC.LateRequest(IT, 5, date(2020, 5, 4),
                                                       date(2020, 7, 4)), annuity)
    assert result.full_annuity == annuity.amount


def test_late_pending_blocks():
    result = CALC.compute_late(tiny_library("pending"),
                               CALC.LateRequest(IT, 5, date(2020, 5, 4),
                                                date(2020, 7, 4)))
    assert result.computed is False


def test_late_steps_recorded():
    result = CALC.compute_late(lib(), CALC.LateRequest(IT, 5, date(2020, 5, 4),
                                                       date(2020, 7, 4)))
    assert any("滞纳金=" in step for step in result.steps)


# ==========================================================================
# §六 费减（20）
# ==========================================================================
def _applicant_individual(monthly=None, annual=None, name="A"):
    item = {"kind": "individual", "name": name}
    if monthly is not None:
        item["monthly_avg_income"] = monthly
    if annual is not None:
        item["annual_income"] = annual
    return item


def test_parse_applicants_rejects_empty():
    with pytest.raises(UsageError):
        CALC.parse_applicants([])


def test_parse_applicants_rejects_bad_kind():
    with pytest.raises(UsageError):
        CALC.parse_applicants([{"kind": "company"}])


def test_parse_applicants_individual_requires_income():
    with pytest.raises(UsageError):
        CALC.parse_applicants([{"kind": "individual"}])


def test_parse_applicants_accepts_monthly_only():
    parsed = CALC.parse_applicants([_applicant_individual("4999")])
    assert parsed[0]["monthly_avg_income"] == Decimal("4999")


def test_parse_applicants_rejects_float():
    with pytest.raises(UsageError):
        CALC.parse_applicants([_applicant_individual(4999.0)])


def test_thresholds_current():
    thresholds, historical = CALC.thresholds_for_year(lib(), 2026)
    assert historical is False
    assert thresholds["individual_monthly_income"] == Decimal("5000")


def test_thresholds_historical():
    thresholds, historical = CALC.thresholds_for_year(lib(), 2018)
    assert historical is True
    assert thresholds["individual_monthly_income"] == Decimal("3500")


def test_applicant_eligible_strict_less():
    thresholds, _ = CALC.thresholds_for_year(lib(), 2026)
    under = CALC.parse_applicants([_applicant_individual("4999.99")])[0]
    exact = CALC.parse_applicants([_applicant_individual("5000")])[0]
    assert CALC.applicant_eligible(under, thresholds) is True
    assert CALC.applicant_eligible(exact, thresholds) is False


def test_applicant_eligible_annual_path():
    thresholds, _ = CALC.thresholds_for_year(lib(), 2026)
    applicant = CALC.parse_applicants(
        [_applicant_individual(None, "59999.99")])[0]
    assert CALC.applicant_eligible(applicant, thresholds) is True


def test_applicant_eligible_entity():
    thresholds, _ = CALC.thresholds_for_year(lib(), 2026)
    assert CALC.applicant_eligible({"kind": "entity", "taxable_income": Decimal("1")},
                                   thresholds) is True
    assert CALC.applicant_eligible({"kind": "entity", "taxable_income": Decimal("1000000")},
                                   thresholds) is False


def test_reduction_sole_rate():
    request = CALC.ReductionRequest(
        IT, 5, 2026,
        CALC.parse_applicants([_applicant_individual("4999.99")]))
    result = CALC.compute_reduction(lib(), request)
    assert result.eligible is True
    assert result.reduction_rate == Decimal("0.85")
    assert result.payable == Decimal("180.00")


def test_reduction_combined_rate():
    request = CALC.ReductionRequest(
        IT, 5, 2026,
        CALC.parse_applicants([_applicant_individual("4999", name="A"),
                               _applicant_individual("4999", name="B")]))
    result = CALC.compute_reduction(lib(), request)
    assert result.combined is True
    assert result.reduction_rate == Decimal("0.70")
    assert result.payable == Decimal("360.00")


def test_reduction_one_ineligible_makes_all_ineligible():
    request = CALC.ReductionRequest(
        IT, 5, 2026,
        CALC.parse_applicants([_applicant_individual("4999", name="A"),
                               _applicant_individual("5000", name="B")]))
    result = CALC.compute_reduction(lib(), request)
    assert result.eligible is False
    assert result.payable is None


def test_reduction_ineligible_no_candidate():
    request = CALC.ReductionRequest(
        IT, 5, 2026, CALC.parse_applicants([_applicant_individual("8000")]))
    result = CALC.compute_reduction(lib(), request)
    assert result.eligible is False
    assert result.candidates == ()


def test_reduction_open_license_candidate():
    request = CALC.ReductionRequest(
        IT, 5, 2026, CALC.parse_applicants([_applicant_individual("4999")]),
        open_license=True)
    result = CALC.compute_reduction(lib(), request)
    assert len(result.candidates) == 2
    assert result.chosen.policy == "费减"
    assert result.no_double_benefit_applied is True


def test_reduction_open_license_only_candidate():
    request = CALC.ReductionRequest(
        IT, 5, 2026, CALC.parse_applicants([_applicant_individual("8000")]),
        open_license=True)
    result = CALC.compute_reduction(lib(), request)
    assert len(result.candidates) == 1
    assert result.payable == Decimal("1020.00")


def test_reduction_no_double_benefit_text():
    result = CALC.compute_reduction(
        lib(), CALC.ReductionRequest(
            IT, 5, 2026, CALC.parse_applicants([_applicant_individual("4999")]),
            open_license=True))
    assert result.no_double_benefit


def test_reduction_historical_threshold():
    request = CALC.ReductionRequest(
        IT, 5, 2018, CALC.parse_applicants([_applicant_individual("3600")]))
    result = CALC.compute_reduction(lib(), request)
    assert result.eligible is False  # 3600 > 3500 历史阈值


def test_reduction_full_annuity():
    result = CALC.compute_reduction(
        lib(), CALC.ReductionRequest(
            IT, 5, 2026, CALC.parse_applicants([_applicant_individual("4999")])))
    assert result.full_annuity == Decimal("1200.00")
    assert result.thresholds["entity_taxable_income"] == Decimal("1000000")


def test_reduction_steps_recorded():
    result = CALC.compute_reduction(
        lib(), CALC.ReductionRequest(
            IT, 5, 2026, CALC.parse_applicants([_applicant_individual("4999")])))
    assert any("选中" in step for step in result.steps)


# ==========================================================================
# §七 组合排期（16）
# ==========================================================================
def _portfolio(*items, today="2026-10-14", window=3):
    sources = tuple((item.get("patent_no") or "item%d" % idx, item)
                    for idx, item in enumerate(items))
    return CALC.PortfolioRequest(sources, date.fromisoformat(today), window)


def test_portfolio_settled():
    result = CALC.scan_portfolio(_portfolio(
        {"patent_no": "P1", "patent_type": "invention", "year": 5,
         "due_on": "2026-12-01", "paid_on": "2026-11-01"}))
    assert result.settled == ("P1#y5",)


def test_portfolio_unpaid():
    result = CALC.scan_portfolio(_portfolio(
        {"patent_no": "P1", "patent_type": "invention", "year": 5,
         "due_on": "2026-01-01", "paid_on": ""}))
    assert result.unpaid == ("P1#y5",)


def test_portfolio_not_due():
    result = CALC.scan_portfolio(_portfolio(
        {"patent_no": "P1", "patent_type": "invention", "year": 5,
         "due_on": "2027-12-01"}))
    assert result.not_due == ("P1#y5",)


def test_portfolio_due_soon_window():
    result = CALC.scan_portfolio(_portfolio(
        {"patent_no": "P1", "patent_type": "invention", "year": 5,
         "due_on": "2026-11-01"}))
    assert [e.id for e in result.due_soon] == ["P1#y5"]


def test_portfolio_due_soon_outside_window():
    result = CALC.scan_portfolio(_portfolio(
        {"patent_no": "P1", "patent_type": "invention", "year": 5,
         "due_on": "2027-12-01"}))
    assert result.due_soon == ()


def test_portfolio_bad_format_isolated():
    result = CALC.scan_portfolio(_portfolio({"patent_no": "P1"}))
    assert len(result.failed) == 1
    assert result.failed[0].reason == "bad_format"


def test_portfolio_missing_patent_no_failed():
    result = CALC.scan_portfolio(_portfolio({"patent_type": "invention",
                                             "year": 5, "due_on": "2026-01-01"}))
    assert len(result.failed) == 1


def test_portfolio_bad_type_failed():
    result = CALC.scan_portfolio(_portfolio({"patent_no": "P1",
                                             "patent_type": "pct", "year": 5,
                                             "due_on": "2026-01-01"}))
    assert len(result.failed) == 1


def test_portfolio_bad_due_date_failed():
    result = CALC.scan_portfolio(_portfolio({"patent_no": "P1",
                                             "patent_type": "invention",
                                             "year": 5, "due_on": "2026/01/01"}))
    assert len(result.failed) == 1


def test_portfolio_amount_from_rules():
    result = CALC.scan_portfolio(_portfolio(
        {"patent_no": "P1", "patent_type": "invention", "year": 5,
         "due_on": "2027-12-01"}), lib())
    assert result.entries[0].amount == Decimal("1200.00")


def test_portfolio_detected_true_for_unpaid():
    result = CALC.scan_portfolio(_portfolio(
        {"patent_no": "P1", "patent_type": "invention", "year": 5,
         "due_on": "2026-01-01"}))
    assert result.detected is True


def test_portfolio_detected_false_when_all_settled():
    result = CALC.scan_portfolio(_portfolio(
        {"patent_no": "P1", "patent_type": "invention", "year": 5,
         "due_on": "2026-12-01", "paid_on": "2026-11-01"}))
    assert result.detected is False


def test_portfolio_entries_sorted_by_id():
    result = CALC.scan_portfolio(_portfolio(
        {"patent_no": "P2", "patent_type": "invention", "year": 5,
         "due_on": "2027-01-01"},
        {"patent_no": "P1", "patent_type": "invention", "year": 5,
         "due_on": "2027-01-01"}))
    assert [e.id for e in result.entries] == ["P1#y5", "P2#y5"]


def test_portfolio_fingerprint_stable():
    payload = {"patent_no": "P1", "year": 5, "due_on": "2026-01-01",
               "paid_on": ""}
    assert CALC.content_fingerprint(payload) == CALC.content_fingerprint(payload)


def test_portfolio_fingerprint_changes_with_due_date():
    a = {"patent_no": "P1", "year": 5, "due_on": "2026-01-01"}
    b = {"patent_no": "P1", "year": 5, "due_on": "2026-02-01"}
    assert CALC.content_fingerprint(a) != CALC.content_fingerprint(b)


def test_portfolio_result_as_dict_shape():
    result = CALC.scan_portfolio(_portfolio(
        {"patent_no": "P1", "patent_type": "invention", "year": 5,
         "due_on": "2026-01-01"}))
    payload = result.as_dict()
    assert payload["unpaid"] == ["P1#y5"]


# ==========================================================================
# §八 器官端到端（18）
# ==========================================================================
def test_organ_annuity_pass():
    findings = evaluate(load_json(ANNUITY_SAMPLE))
    assert len(findings) == 1
    assert findings[0].verdict == PASS
    assert findings[0].anchor.clause_id == "annuity.invention"
    assert findings[0].evidence["amount"] == "1200.00"


def test_organ_late_pass():
    findings = evaluate(load_json(LATE_SAMPLE))
    assert findings[0].verdict == PASS
    assert findings[0].evidence["surcharge"] == "120.00"
    assert findings[0].evidence["payable"] == "1320.00"


def test_organ_reduction_pass():
    findings = evaluate(load_json(REDUCTION_SAMPLE))
    assert findings[0].verdict == PASS
    assert findings[0].evidence["payable"] == "180.00"
    assert findings[0].evidence["eligible"] is True


def test_organ_portfolio_has_failures():
    findings = evaluate(load_json(PORTFOLIO_SAMPLE))
    counts = report(findings).summary()["verdicts"]
    assert counts[FAIL] == 2
    assert counts[NOT_APPLICABLE] == 3
    assert counts[PASS] == 3


def test_organ_portfolio_rc_blocked():
    assert report(evaluate(load_json(PORTFOLIO_SAMPLE))).exit_code() == 1


def test_organ_full_sample_counts():
    findings = evaluate(load_json(FULL_SAMPLE))
    assert len(findings) == 11
    assert report(findings).blocking()


def test_organ_requires_case_id():
    subject = load_json(ANNUITY_SAMPLE)
    subject.pop("case_id")
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_requires_one_section():
    with pytest.raises(ValueError):
        evaluate({"case_id": "x"})


def test_organ_rejects_unknown_field():
    subject = load_json(ANNUITY_SAMPLE)
    subject["future"] = 1
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_rejects_bad_patent_type():
    subject = load_json(ANNUITY_SAMPLE)
    subject["patent"]["patent_type"] = "pct"
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_rejects_bad_year():
    subject = load_json(ANNUITY_SAMPLE)
    subject["patent"]["year"] = 0
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_rejects_bad_late_date():
    subject = load_json(LATE_SAMPLE)
    subject["late"]["due_on"] = "2020/05/04"
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_rejects_bad_applicants():
    subject = load_json(REDUCTION_SAMPLE)
    subject["reduction"]["applicants"] = []
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_rejects_bad_portfolio_items():
    subject = load_json(PORTFOLIO_SAMPLE)
    subject["portfolio"]["items"] = "nope"
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_wrong_basis_version():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(load_json(ANNUITY_SAMPLE), Basis.empty("0"))


def test_organ_missing_clause():
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate(load_json(ANNUITY_SAMPLE),
                          Basis(version=REG.VERSION, clauses=[]))


def test_organ_deterministic():
    subject = load_json(FULL_SAMPLE)
    first = [f.as_dict() for f in evaluate(subject)]
    second = [f.as_dict() for f in evaluate(subject)]
    assert first == second


def test_organ_late_exceeds_cap_warning():
    subject = load_json(LATE_SAMPLE)
    subject["late"]["due_on"] = "2020-01-04"
    subject["late"]["paid_on"] = "2020-08-04"
    findings = evaluate(subject)
    assert findings[0].evidence["exceeds_cap"] is True
    assert findings[0].evidence["warnings"]


# ==========================================================================
# §九 CLI（6）
# ==========================================================================
def test_cli_annuity_ok():
    assert cp_cli.main(["check", SLUG, "--input", ANNUITY_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_late_ok():
    assert cp_cli.main(["check", SLUG, "--input", LATE_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_reduction_ok():
    assert cp_cli.main(["check", SLUG, "--input", REDUCTION_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_portfolio_blocked():
    assert cp_cli.main(["check", SLUG, "--input", PORTFOLIO_SAMPLE,
                        "--basis", BASIS_PATH]) == 1


def test_cli_missing_basis():
    assert cp_cli.main(["check", SLUG, "--input", ANNUITY_SAMPLE]) == 3


def test_cli_bad_input(tmp_path):
    subject = load_json(ANNUITY_SAMPLE)
    subject.pop("case_id")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(subject, ensure_ascii=False), encoding="utf-8")
    assert cp_cli.main(["check", SLUG, "--input", str(path),
                        "--basis", BASIS_PATH]) == 2


# ==========================================================================
# §十 数据纪律（8）
# ==========================================================================
def test_pack_registered():
    from clauseproof.packs import BUILTIN_MODULES
    assert SLUG in BUILTIN_MODULES


def test_basis_has_41_clauses():
    assert len(basis()) == 41


def test_basis_contains_all_rule_entries():
    library = basis()
    for entry in lib().entries_with_prefix(""):
        assert library.clause(entry.key) is not None, entry.key


def test_basis_has_contract_clauses():
    ids = basis().clause_ids()
    for clause_id in ("contract.ledger", "contract.gate", "contract.preview",
                      "contract.data"):
        assert clause_id in ids


def test_manifest_sha256_matches():
    import hashlib

    manifest = load_json(os.path.join(DATA_DIR, "manifest.json"))
    assert set(manifest["files"]) == set(REG.DATA_FILES)
    for name, record in manifest["files"].items():
        path = os.path.join(DATA_DIR, name)
        assert os.path.getsize(path) == record["bytes"]
        assert hashlib.sha256(open(path, "rb").read()).hexdigest() == \
            record["sha256"]


def test_ruleset_sha256_matches_manifest():
    import hashlib

    manifest = load_json(os.path.join(DATA_DIR, "rules-manifest.json"))
    by_id = {meta["id"]: meta for meta in manifest["rulesets"]}
    for rid, rs in lib().rulesets.items():
        assert rid in by_id
        assert len(rs.expected_sha256 or "") == 64
        path = os.path.join(DATA_DIR, by_id[rid]["file"])
        assert hashlib.sha256(open(path, "rb").read()).hexdigest() == \
            rs.expected_sha256


def test_all_rule_entries_have_basis():
    for entry in lib().entries_with_prefix(""):
        assert entry.basis.get("doc_no")
        assert entry.basis.get("clause")


def test_production_zero_pending():
    assert lib().status_counts()["pending"] == 0