"""器官 ``safety-fee`` 判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源判定面（分段计算 / 单位换算 / 年度锚定 / status 门控 / 四类计提机制 /
依据选择 / 支出四态 / 使用进度 / 双版本对照）逐条搬，断言落在「金额 + 机制 + 条款 +
四态 + 阻断」上。来源判定层（D1 + D18 机械选 18 文件 / 实跑 140 passed / AST 139）
逐文件处置见 ``docs/safety-fee.md`` §6。

来源仓只读；合成规则/档案一律**内存注入**。真值库 122 例 + 7 误报对照逐例对账
（金额由来源生成器独立计算路径产出，双重记账）。
"""

import importlib
import json
import os
import shutil
import sys
from decimal import Decimal

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from clauseproof import cli as cp_cli  # noqa: E402
from clauseproof.core.basis import Basis  # noqa: E402
from clauseproof.core.ledger import (  # noqa: E402
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Report,
)

PACK_MOD = importlib.import_module("clauseproof.packs.safety-fee")
TIERED = importlib.import_module("clauseproof.packs.safety-fee.tiered")
UNITS = importlib.import_module("clauseproof.packs.safety-fee.units")
MANIFEST = importlib.import_module("clauseproof.packs.safety-fee.manifest")
GATE = importlib.import_module("clauseproof.packs.safety-fee.gate")
ACCRUAL = importlib.import_module("clauseproof.packs.safety-fee.accrual")
SPENDING = importlib.import_module("clauseproof.packs.safety-fee.spending")
DIFF = importlib.import_module("clauseproof.packs.safety-fee.diff")
PIPELINE = importlib.import_module("clauseproof.packs.safety-fee.pipeline")
REG = importlib.import_module("clauseproof.packs.safety-fee.registry")
ERRORS = importlib.import_module("clauseproof.packs.safety-fee.errors")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "safety-fee")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "safety-fee")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
COAL_SAMPLE = os.path.join(SAMPLES, "profile-coal.json")
LEDGER_SAMPLE = os.path.join(SAMPLES, "profile-coal-ledger.json")
PROGRESS_SAMPLE = os.path.join(SAMPLES, "profile-coal-progress.json")
COMPARE_SAMPLE = os.path.join(SAMPLES, "profile-compare.json")
TRUTH_PATH = os.path.join(DATA_DIR, "truth-cases.json")

BASIS = Basis.from_json(BASIS_PATH)
with open(TRUTH_PATH, "r", encoding="utf-8") as _handle:
    TRUTH = json.load(_handle)
CASES = TRUTH["cases"]
NEGATIVES = TRUTH["negatives"]

CTX = PIPELINE.context()
REFS = {ref.ruleset_id: ref for ref in CTX.manifest.refs}
REF_2022 = REFS["财资-2022-136"]
REF_2012 = REFS["财企-2012-16"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _case(**overrides):
    payload = {
        "enterprise_id": "90000000SYN0000001A",
        "enterprise_name": "示例煤炭（合成）有限公司",
        "industry_id": "coal",
        "year": 2024,
        "basis_kind": "output",
        "basis_value": "120000",
        "basis_unit": "ton",
        "variant_id": "coal_high_gas",
    }
    payload.update(overrides)
    return PIPELINE.build_case(payload)


def _records(subject, basis=None):
    findings = PACK_MOD.evaluate_with_context(subject, basis or BASIS, CTX)
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject="test.json", findings=tuple(findings))


def _sample(path):
    return load_json(path)


def _find(records, rule_id):
    for record in records:
        if record.rule_id == rule_id:
            return record
    raise AssertionError("未找到账本行：%s" % rule_id)


def _ruleset(version="2022"):
    return CTX.ruleset(REF_2022 if version == "2022" else REF_2012)


def _spec(lower, upper, rate, clause="第一条"):
    return TIERED.TierSpec(lower=Decimal(str(lower)),
                           upper=None if upper is None else Decimal(str(upper)),
                           rate=None if rate is None else Decimal(str(rate)),
                           clause=clause, status="verified")


# --------------------------------------------------------------------------
# §一 超额累退分段
# --------------------------------------------------------------------------
def test_tier_base_below_first():
    spec = _spec(0, 1000, "0.05")
    assert TIERED.tier_base(Decimal("0"), spec) == 0


def test_tier_base_in_first():
    spec = _spec(0, 1000, "0.05")
    assert TIERED.tier_base(Decimal("600"), spec) == Decimal("600")


def test_tier_base_at_upper():
    spec = _spec(0, 1000, "0.05")
    assert TIERED.tier_base(Decimal("1000"), spec) == Decimal("1000")


def test_tier_base_second_tier():
    spec = _spec(1000, 5000, "0.03")
    assert TIERED.tier_base(Decimal("2000"), spec) == Decimal("1000")


def test_tier_base_open_upper():
    spec = _spec(5000, None, "0.01")
    assert TIERED.tier_base(Decimal("8000"), spec) == Decimal("3000")


def test_tier_base_zero_value_returns_zero():
    spec = _spec(1000, 5000, "0.03")
    assert TIERED.tier_base(Decimal("0"), spec) == 0


def test_compute_tiered_zero_empty():
    assert TIERED.compute_tiered(Decimal("0"), (_spec(0, 100, "0.05"),)) == ()


def test_compute_tiered_negative_empty():
    assert TIERED.compute_tiered(Decimal("-1"), (_spec(0, 100, "0.05"),)) == ()


def test_compute_tiered_single():
    lines = TIERED.compute_tiered(Decimal("100"), (_spec(0, None, "0.05"),))
    assert lines[0].amount == Decimal("5.00")


def test_compute_tiered_two_segments_sum():
    lines = TIERED.compute_tiered(Decimal("300"), (_spec(0, 100, "0.10"),
                                                     _spec(100, None, "0.05")))
    assert TIERED.tiered_total(lines) == Decimal("20.00")


def test_compute_tiered_boundary_belongs_next():
    lines = TIERED.compute_tiered(Decimal("100"), (_spec(0, 100, "0.10"),
                                                    _spec(100, None, "0.05")))
    assert lines[0].amount == Decimal("10.00")
    assert lines[1].amount == Decimal("0.00")


def test_compute_tiered_quantizes_each_segment():
    lines = TIERED.compute_tiered(Decimal("333"), (_spec(0, 100, "0.033"),
                                                    _spec(100, None, "0.033")))
    assert lines[0].amount == Decimal("3.30")
    assert lines[1].amount == Decimal("7.69")


def test_compute_tiered_zero_segment_still_listed():
    lines = TIERED.compute_tiered(Decimal("10"), (_spec(0, 100, "0.10"),
                                                   _spec(100, None, "0.05")))
    assert len(lines) == 2
    assert lines[1].base_in_tier == 0


def test_tiered_total_empty():
    assert TIERED.tiered_total(()) == 0


def test_tiers_from_rules_sorted():
    specs = TIERED.tiers_from_rules([{"lower": "1000", "rate": "0.01"},
                                     {"lower": "0", "rate": "0.05"}])
    assert [spec.lower for spec in specs] == [Decimal("0"), Decimal("1000")]


def test_tiers_from_rules_missing_rate():
    specs = TIERED.tiers_from_rules([{"lower": "0", "rate": None}])
    assert specs[0].rate is None


def test_tiers_from_rules_clause():
    specs = TIERED.tiers_from_rules([{"lower": "0", "rate": "0.05",
                                       "clause": "第七条"}])
    assert specs[0].clause == "第七条"


def test_tier_line_as_dict():
    lines = TIERED.compute_tiered(Decimal("100"), (_spec(0, None, "0.05"),))
    payload = lines[0].as_dict()
    assert payload["rate"] == "0.05"
    assert payload["upper"] is None
    assert payload["amount"] == "5.00"


def test_quantize_half_up():
    assert TIERED.quantize_money(Decimal("0.005")) == Decimal("0.01")


def test_quantize_two_decimals():
    assert TIERED.quantize_money(Decimal("1.234")) == Decimal("1.23")


def test_tier_line_index():
    lines = TIERED.compute_tiered(Decimal("200"), (_spec(0, 100, "0.01"),
                                                   _spec(100, None, "0.01")))
    assert [line.index for line in lines] == [1, 2]


def test_tier_base_fractional():
    spec = _spec(0, 1, "0.5")
    assert TIERED.tier_base(Decimal("0.25"), spec) == Decimal("0.25")


# --------------------------------------------------------------------------
# §二 单位换算
# --------------------------------------------------------------------------
def _units():
    return CTX.units


def test_units_cny_identity():
    assert _units().to_base(Decimal("10"), "CNY") == (Decimal("10"), None)


def test_units_cny10k():
    value, warning = _units().to_base(Decimal("2"), "CNY10k")
    assert value == Decimal("20000")
    assert "定义性换算" in warning


def test_units_cny100m():
    value, _ = _units().to_base(Decimal("1"), "CNY100m")
    assert value == Decimal("100000000")


def test_units_ton_identity():
    assert _units().to_base(Decimal("5"), "ton") == (Decimal("5"), None)


def test_units_unknown():
    with pytest.raises(ERRORS.SchemaError):
        _units().factor("GBP")


def test_units_missing_required():
    with pytest.raises(ERRORS.SchemaError):
        UNITS.UnitConverter({"CNY": Decimal(1)})


def test_build_units_bad_shape():
    with pytest.raises(ERRORS.SchemaError):
        UNITS.build_units({"factors": []})


def test_units_factors_copy():
    factors = _units().factors
    factors["CNY"] = Decimal("9")
    assert _units().factor("CNY") == Decimal("1")


# --------------------------------------------------------------------------
# §三 manifest / 年度锚定 / 指纹
# --------------------------------------------------------------------------
def test_resolve_2020_2012():
    assert CTX.manifest.resolve_year(2020).ruleset_id == "财企-2012-16"


def test_resolve_2022_2012():
    assert CTX.manifest.resolve_year(2022).ruleset_id == "财企-2012-16"


def test_resolve_2023_2022():
    assert CTX.manifest.resolve_year(2023).ruleset_id == "财资-2022-136"


def test_resolve_2024_2022():
    assert CTX.manifest.resolve_year(2024).ruleset_id == "财资-2022-136"


def test_resolve_1900_raises():
    with pytest.raises(ERRORS.NoRulesetForYear):
        CTX.manifest.resolve_year(1900)


def test_resolve_ambiguous():
    payload = {
        "schema_version": 1,
        "rulesets": [
            {"dir": "a", "ruleset_id": "财资-2022-136", "doc_no": "A",
             "effective_from": "2022-01-01", "effective_to": None, "files": {}},
            {"dir": "b", "ruleset_id": "财企-2012-16", "doc_no": "B",
             "effective_from": "2022-01-01", "effective_to": None, "files": {}},
        ],
    }
    app = MANIFEST.build_manifest(DATA_DIR, payload)
    with pytest.raises(ERRORS.AmbiguousRuleset):
        app.resolve_year(2024)


def test_version_of():
    assert MANIFEST.version_of("财资-2022-136") == "2022"
    assert MANIFEST.version_of("财企-2012-16") == "2012"


def test_version_of_bad():
    with pytest.raises(ERRORS.SchemaError):
        MANIFEST.version_of("no-year-here")


def test_flat_name():
    assert MANIFEST.flat_name("ruleset", "2022") == "ruleset-2022.json"


def test_manifest_refs_count():
    assert len(CTX.manifest.refs) == 2


def test_ref_covers():
    assert REF_2012.covers(__import__("datetime").date(2020, 1, 1))
    assert not REF_2022.covers(__import__("datetime").date(2020, 1, 1))


def test_ref_as_dict():
    payload = REF_2012.as_dict()
    assert payload["version"] == "2012"
    assert payload["effective_to"] == "2022-11-20"


def test_manifest_next_review():
    assert CTX.manifest.next_review == "2027-10-14"
    assert CTX.manifest.review_interval == "annual"


def test_manifest_integrity_ok():
    CTX.manifest.verify_integrity()


def test_manifest_integrity_tamper(tmp_path):
    target = tmp_path / "data"
    shutil.copytree(DATA_DIR, target)
    path = target / "ruleset-2022.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    payload = load_json(str(target / "rules-manifest.json"))
    built = MANIFEST.build_manifest(str(target), payload)
    with pytest.raises(ERRORS.IntegrityError):
        built.verify_integrity()


def test_manifest_integrity_missing(tmp_path):
    target = tmp_path / "data"
    shutil.copytree(DATA_DIR, target)
    (target / "ruleset-2012.json").unlink()
    payload = load_json(str(target / "rules-manifest.json"))
    built = MANIFEST.build_manifest(str(target), payload)
    with pytest.raises(ERRORS.IntegrityError):
        built.verify_integrity()


def test_build_manifest_bad_schema():
    with pytest.raises(ERRORS.SchemaError):
        MANIFEST.build_manifest(DATA_DIR, {"schema_version": 99, "rulesets": []})


def test_parse_day_bad():
    payload = {"schema_version": 1, "rulesets": [
        {"dir": "a", "ruleset_id": "财资-2022-136", "doc_no": "A",
         "effective_from": "2022/01/01", "files": {}}]}
    with pytest.raises(ERRORS.SchemaError):
        MANIFEST.build_manifest(DATA_DIR, payload)


# --------------------------------------------------------------------------
# §四 status 门控
# --------------------------------------------------------------------------
def _pending_ruleset():
    return {"industries": [
        {"industry_id": "coal", "status": "verified", "clause": "第七条",
         "implementation": "in_scope"},
        {"industry_id": "machinery", "status": "pending", "clause": "第二十七条",
         "implementation": "in_scope"},
    ]}


def test_gate_calc_industry_scoped():
    result = GATE.check_scope(_pending_ruleset(), "calc", industry_id="coal")
    assert result.ok is True


def test_gate_calc_other_industry_blocked():
    result = GATE.check_scope(_pending_ruleset(), "calc", industry_id="machinery")
    assert result.ok is False
    assert result.blockers[0].clause == "第二十七条"


def test_gate_calc_no_scope_blocks_any_pending():
    result = GATE.check_scope(_pending_ruleset(), "calc")
    assert result.ok is False


def test_gate_calc_deferred_skipped():
    ruleset = {"industries": [
        {"industry_id": "future", "status": "pending", "implementation": "deferred",
         "clause": "第三十条"}]}
    assert GATE.check_scope(ruleset, "calc").ok is True


def test_gate_input_required_not_blocking():
    ruleset = {"industries": [
        {"industry_id": "coal", "status": "input_required", "clause": "第七条"}]}
    assert GATE.check_scope(ruleset, "calc").ok is True


def test_gate_collect_nested():
    payload = {"a": [{"status": "pending", "clause": "第一条"}]}
    blockers = GATE.collect_blockers(payload, "calc", "root")
    assert blockers[0].path == "root.a[0]"


def test_gate_collect_status_dict_stops():
    payload = {"status": "pending", "clause": "第一条", "inner": {"status": "pending"}}
    blockers = GATE.collect_blockers(payload, "calc", "root")
    assert len(blockers) == 1


def test_gate_unknown_scope():
    with pytest.raises(ERRORS.ConfigError):
        GATE.check_scope({}, "magic")


def test_gate_check_requires_spending():
    with pytest.raises(ERRORS.ConfigError):
        GATE.check_scope({}, "check")


def test_gate_progress_requires_progress():
    with pytest.raises(ERRORS.ConfigError):
        GATE.check_scope({}, "progress")


def test_gate_check_ok_for_shipped_2022():
    ruleset = _ruleset("2022")
    result = GATE.check_scope(ruleset, "check",
                              spending=CTX.spending(REF_2022))
    assert result.ok is True


def test_gate_progress_ok_for_shipped_2022():
    ruleset = _ruleset("2022")
    result = GATE.check_scope(ruleset, "progress",
                              progress=CTX.progress(REF_2022))
    assert result.ok is True


def test_gate_progress_blocked_for_2012_pending():
    ruleset = _ruleset("2012")
    result = GATE.check_scope(ruleset, "progress",
                              progress=CTX.progress(REF_2012))
    assert result.ok is False
    assert result.blockers[0].clause == "第十四条"


def test_gate_scope_result_as_dict():
    result = GATE.check_scope(_pending_ruleset(), "calc", industry_id="machinery")
    payload = result.as_dict()
    assert payload["ok"] is False
    assert payload["blockers"][0]["status"] == "pending"


# --------------------------------------------------------------------------
# §五 计提机制
# --------------------------------------------------------------------------
def test_coal_high_gas_amount():
    report = PIPELINE.compute_calc(CTX, _case(), REF_2022)
    assert report.result.amount == Decimal("3600000.00")


def test_coal_other_underground():
    report = PIPELINE.compute_calc(CTX, _case(variant_id="coal_other_underground"), REF_2022)
    assert report.result.amount == Decimal("1800000.00")


def test_coal_outburst():
    report = PIPELINE.compute_calc(CTX, _case(variant_id="coal_outburst_rockburst"), REF_2022)
    assert report.result.amount == Decimal("6000000.00")


def test_coal_variant_required():
    profile = dict(enterprise_id="E", enterprise_name="N", industry_id="coal",
                   year=2024, basis_kind="output", basis_value="1", basis_unit="ton")
    with pytest.raises(ERRORS.MissingInput):
        ACCRUAL.compute(_ruleset("2022"), ACCRUAL.AccrualRequest(
            industry_id="coal", basis_kind="output", basis_value=Decimal("1"),
            basis_unit="ton", year=2024))


def test_coal_unknown_variant():
    with pytest.raises(ERRORS.SchemaError):
        ACCRUAL.compute(_ruleset("2022"), ACCRUAL.AccrualRequest(
            industry_id="coal", basis_kind="output", basis_value=Decimal("1"),
            basis_unit="ton", year=2024, variant_id="nope"))


def test_tiered_hazardous_amount():
    case = _case(enterprise_id="E2", industry_id="hazardous_chemicals",
                 basis_kind="revenue", basis_value="50000000", basis_unit="CNY",
                 variant_id=None)
    report = PIPELINE.compute_calc(CTX, case, REF_2022)
    assert report.result.amount == Decimal("1350000.00")
    assert report.result.mechanism == "by_revenue_tiered"


def test_tiered_lines_exposed():
    case = _case(enterprise_id="E2", industry_id="hazardous_chemicals",
                 basis_kind="revenue", basis_value="50000000", basis_unit="CNY",
                 variant_id=None)
    report = PIPELINE.compute_calc(CTX, case, REF_2022)
    assert len(report.result.tiers) >= 2


def test_transport_revenue_rate():
    case = _case(enterprise_id="E3", industry_id="transport",
                 basis_kind="revenue", basis_value="1000000", basis_unit="CNY",
                 variant_id="general_freight")
    report = PIPELINE.compute_calc(CTX, case, REF_2022)
    assert report.result.amount == Decimal("10000.00")


def test_construction_project_cost():
    case = _case(enterprise_id="E4", industry_id="construction",
                 basis_kind="project_cost", basis_value="1000000", basis_unit="CNY",
                 variant_id="mine_engineering")
    report = PIPELINE.compute_calc(CTX, case, REF_2022)
    assert report.result.mechanism == "by_project_cost"
    assert report.result.amount == Decimal("35000.00")


def test_basis_kind_mismatch():
    with pytest.raises(ERRORS.SchemaError):
        ACCRUAL.compute(_ruleset("2022"), ACCRUAL.AccrualRequest(
            industry_id="coal", basis_kind="revenue", basis_value=Decimal("1"),
            basis_unit="CNY", year=2024, variant_id="coal_high_gas"))


def test_unknown_industry():
    with pytest.raises(ERRORS.SchemaError):
        ACCRUAL.compute(_ruleset("2022"), ACCRUAL.AccrualRequest(
            industry_id="space", basis_kind="revenue", basis_value=Decimal("1"),
            basis_unit="CNY", year=2024))


def test_deferred_industry():
    ruleset = {"industries": [{"industry_id": "future", "implementation": "deferred",
                               "industry_name": "未来行业"}]}
    with pytest.raises(ERRORS.NotCovered):
        ACCRUAL.compute(ruleset, ACCRUAL.AccrualRequest(
            industry_id="future", basis_kind="revenue", basis_value=Decimal("1"),
            basis_unit="CNY", year=2024))


def test_result_formula_contains_amount():
    report = PIPELINE.compute_calc(CTX, _case(), REF_2022)
    assert "3600000.00" in report.result.formula


def test_result_provenance_present():
    report = PIPELINE.compute_calc(CTX, _case(), REF_2022)
    assert report.result.provenance


def test_result_as_dict():
    report = PIPELINE.compute_calc(CTX, _case(), REF_2022)
    payload = report.result.as_dict()
    assert payload["mechanism"] == "by_output"
    assert payload["amount"] == "3600000.00"


def test_rate_missing_value():
    ruleset = {"industries": [{"industry_id": "x", "status": "verified",
                               "mechanism": "by_revenue_rate",
                               "clause": "第一条"}]}
    with pytest.raises(ERRORS.SchemaError):
        ACCRUAL.compute(ruleset, ACCRUAL.AccrualRequest(
            industry_id="x", basis_kind="revenue", basis_value=Decimal("1"),
            basis_unit="CNY", year=2024))


def test_output_zero_basis():
    report = PIPELINE.compute_calc(CTX, _case(basis_value="0"), REF_2022)
    assert report.result.amount == Decimal("0.00")


def test_variant_overrides_mechanism():
    ruleset = {"industries": [{
        "industry_id": "mix", "industry_name": "混合", "mechanism": "by_output",
        "clause": "第一条", "status": "verified",
        "variants": [{"variant_id": "v1", "variant_name": "比例变体",
                      "mechanism": "by_project_cost", "rate": "0.02",
                      "clause": "第一条", "status": "verified"}]}]}
    result = ACCRUAL.compute(ruleset, ACCRUAL.AccrualRequest(
        industry_id="mix", basis_kind="project_cost", basis_value=Decimal("100"),
        basis_unit="CNY", year=2024, variant_id="v1"))
    assert result.amount == Decimal("2.00")


def test_two_tier_amount_matches_manual():
    case = _case(enterprise_id="E5", industry_id="fireworks",
                 basis_kind="revenue", basis_value="10000000", basis_unit="CNY",
                 variant_id=None, year=2024)
    report = PIPELINE.compute_calc(CTX, case, REF_2022)
    manual = sum(line.amount for line in report.result.tiers)
    assert report.result.amount == manual


# --------------------------------------------------------------------------
# §六 依据选择
# --------------------------------------------------------------------------
def test_mine_variant_highest():
    industry = {"industry_id": "coal", "clause": "第七条", "variants": [
        {"variant_id": "a", "severity": 4, "conditions": {"hazards": ["gas_outburst"]},
         "clause": "第七条"},
        {"variant_id": "b", "severity": 1, "conditions": {"mine_type": "other_underground"},
         "clause": "第七条"},
    ]}
    decision = ACCRUAL.choose_mine_variant(industry, mine_type="other_underground",
                                           hazards=["gas_outburst"])
    assert decision.chosen_variant == "a"
    assert decision.excluded


def test_mine_variant_inputs_required():
    industry = {"industry_id": "coal", "clause": "第七条",
                "variants": [{"variant_id": "a", "severity": 1,
                              "conditions": {"mine_type": "x"}}]}
    decision = ACCRUAL.choose_mine_variant(industry)
    assert decision.inputs_required == ("mine_type",)


def test_mine_variant_no_match():
    industry = {"industry_id": "coal", "variants": [
        {"variant_id": "a", "severity": 1, "conditions": {"mine_type": "x"}}]}
    with pytest.raises(ERRORS.MissingInput):
        ACCRUAL.choose_mine_variant(industry, mine_type="z")


def test_mine_variant_no_variants():
    decision = ACCRUAL.choose_mine_variant({"industry_id": "x", "clause": "第一条"})
    assert decision.kind == "none"


def test_multi_business_separate():
    decision = ACCRUAL.resolve_multi_business(_ruleset("2022"), [
        {"industry_id": "coal", "revenue": "100", "separate_accounting": True},
        {"industry_id": "machinery", "revenue": "200", "separate_accounting": True},
    ])
    assert decision.chosen_industry is None
    assert len(decision.notes) == 2


def test_multi_business_not_separate():
    decision = ACCRUAL.resolve_multi_business(_ruleset("2022"), [
        {"industry_id": "coal", "revenue": "100", "separate_accounting": False},
        {"industry_id": "machinery", "revenue": "200", "separate_accounting": False},
    ])
    assert decision.chosen_industry == "machinery"


def test_multi_business_empty():
    decision = ACCRUAL.resolve_multi_business(_ruleset("2022"), [])
    assert decision.kind == "none"


def test_net_basis_not_contractor():
    decision = ACCRUAL.resolve_net_basis(_ruleset("2022"), revenue=Decimal("100"),
                                         purchased_cost=Decimal("90"))
    assert decision.kind == "none"


def test_net_basis_inputs_required():
    decision = ACCRUAL.resolve_net_basis(_ruleset("2022"), revenue=None,
                                         purchased_cost=None, is_contractor=True)
    assert decision.inputs_required == ("revenue", "purchased_cost")


def test_net_basis_above_threshold():
    decision = ACCRUAL.resolve_net_basis(_ruleset("2022"), revenue=Decimal("100"),
                                         purchased_cost=Decimal("90"),
                                         is_contractor=True)
    assert decision.basis_value == "10"


def test_net_basis_below_threshold():
    decision = ACCRUAL.resolve_net_basis(_ruleset("2022"), revenue=Decimal("100"),
                                         purchased_cost=Decimal("80"),
                                         is_contractor=True)
    assert decision.basis_value is None


def test_net_basis_zero_revenue():
    decision = ACCRUAL.resolve_net_basis(_ruleset("2022"), revenue=Decimal("0"),
                                         purchased_cost=Decimal("0"),
                                         is_contractor=True)
    assert decision.basis_value is None


def test_decide_basis_multi_priority():
    case = _case(businesses=[{"industry_id": "coal", "revenue": "10",
                              "separate_accounting": False},
                             {"industry_id": "machinery", "revenue": "20",
                              "separate_accounting": False}])
    decision = ACCRUAL.decide_basis(_ruleset("2022"), case)
    assert decision.kind == "multi_business"


def test_decide_basis_net():
    case = _case(is_contractor=True, revenue="100", purchased_cost="90")
    decision = ACCRUAL.decide_basis(_ruleset("2022"), case)
    assert decision.kind == "net_basis"
    assert decision.basis_value == "10"


def test_decide_basis_mine():
    profile = dict(enterprise_id="E", enterprise_name="N", industry_id="coal",
                   year=2024, basis_kind="output", basis_value="120000",
                   basis_unit="ton", mine_type="high_gas")
    decision = ACCRUAL.decide_basis(_ruleset("2022"), PIPELINE.build_case(profile))
    assert decision.chosen_variant == "coal_high_gas"


def test_decide_basis_none():
    decision = ACCRUAL.decide_basis(_ruleset("2022"), _case())
    assert decision.kind in ("mine_variant", "none")


def test_basis_decision_as_dict():
    decision = ACCRUAL.choose_mine_variant(
        {"industry_id": "coal", "clause": "第七条", "variants": [
            {"variant_id": "a", "severity": 2, "conditions": {"mine_type": "x"},
             "clause": "第七条"}]}, mine_type="x")
    payload = decision.as_dict()
    assert payload["chosen_variant"] == "a"
    assert isinstance(payload["excluded"], list)


def test_multi_business_ranking_tie():
    decision = ACCRUAL.resolve_multi_business(_ruleset("2022"), [
        {"industry_id": "b", "revenue": "10", "separate_accounting": False},
        {"industry_id": "a", "revenue": "10", "separate_accounting": False},
    ])
    assert decision.chosen_industry == "a"


# --------------------------------------------------------------------------
# §七 支出四态
# --------------------------------------------------------------------------
def _items():
    return PIPELINE.build_ledger(_sample(LEDGER_SAMPLE)["ledger"])


def test_check_allowed():
    report = SPENDING.check_ledger(CTX.spending(REF_2022), "coal", _items())
    assert report.findings[0].state == SPENDING.STATE_COMPLIANT


def test_check_forbidden_redline():
    report = SPENDING.check_ledger(CTX.spending(REF_2022), "coal", _items())
    assert report.redlines[0].item_key == "EXP-003"
    assert report.redlines[0].clause == "第四条"


def test_check_not_assessed():
    items = [SPENDING.LedgerItem(item_key="X", subject="差旅费",
                                 summary="员工差旅报销", amount=Decimal("1.00"))]
    report = SPENDING.check_ledger(CTX.spending(REF_2022), "coal", items)
    assert report.findings[0].state == SPENDING.STATE_NOT_ASSESSED


def test_check_counts():
    report = SPENDING.check_ledger(CTX.spending(REF_2022), "coal", _items())
    assert report.counts() == {SPENDING.STATE_COMPLIANT: 3, SPENDING.STATE_NONCOMPLIANT: 1}


def test_check_unknown_industry():
    with pytest.raises(ERRORS.NotCovered):
        SPENDING.check_ledger(CTX.spending(REF_2022), "space", _items())


def test_check_star_entries():
    spending = {"entries": [{"entry_id": "STAR", "industry_id": "*",
                             "category": "允许", "match_keywords": ["报销"],
                             "clause": "第一条"}]}
    items = [SPENDING.LedgerItem(item_key="X", subject="差旅",
                                 summary="报销", amount=Decimal("1"))]
    report = SPENDING.check_ledger(spending, "coal", items)
    assert report.findings[0].state == SPENDING.STATE_COMPLIANT


def test_check_keyword_subject():
    spending = {"entries": [{"entry_id": "S", "industry_id": "coal",
                             "category": "允许", "match_keywords": ["培训"],
                             "clause": "第一条"}]}
    items = [SPENDING.LedgerItem(item_key="X", subject="培训",
                                 summary="—", amount=Decimal("1"))]
    assert SPENDING.check_ledger(spending, "coal", items).findings[0].entry_id == "S"


def test_check_keyword_summary():
    spending = {"entries": [{"entry_id": "S", "industry_id": "coal",
                             "category": "允许", "match_keywords": ["培训"],
                             "clause": "第一条"}]}
    items = [SPENDING.LedgerItem(item_key="X", subject="—",
                                 summary="开展培训", amount=Decimal("1"))]
    assert SPENDING.check_ledger(spending, "coal", items).findings[0].entry_id == "S"


def test_check_forbidden_wins_over_allowed():
    spending = {"entries": [
        {"entry_id": "A", "industry_id": "coal", "category": "允许",
         "match_keywords": ["费用"], "clause": "第一条"},
        {"entry_id": "F", "industry_id": "coal", "category": "禁止",
         "match_keywords": ["费用"], "clause": "第二条"},
    ]}
    items = [SPENDING.LedgerItem(item_key="X", subject="费用",
                                 summary="—", amount=Decimal("1"))]
    assert SPENDING.check_ledger(spending, "coal", items).findings[0].state == \
        SPENDING.STATE_NONCOMPLIANT


def test_check_report_as_dict():
    report = SPENDING.check_ledger(CTX.spending(REF_2022), "coal", _items())
    payload = report.as_dict()
    assert payload["industry_id"] == "coal"
    assert len(payload["findings"]) == 4


def test_state_constants_distinct():
    states = {SPENDING.STATE_COMPLIANT, SPENDING.STATE_PARTIAL,
              SPENDING.STATE_NONCOMPLIANT, SPENDING.STATE_NOT_APPLICABLE,
              SPENDING.STATE_NOT_ASSESSED}
    assert len(states) == 5


def test_non_pass_states():
    assert SPENDING.NON_PASS_STATES == frozenset(
        {SPENDING.STATE_NONCOMPLIANT, SPENDING.STATE_NOT_ASSESSED})


def test_in_scope_industries_count():
    assert len(SPENDING.IN_SCOPE_INDUSTRIES) == 12


def test_check_empty_ledger():
    report = SPENDING.check_ledger(CTX.spending(REF_2022), "coal", [])
    assert report.findings == () and report.redlines == ()


def test_check_allowed_clause():
    report = SPENDING.check_ledger(CTX.spending(REF_2022), "coal", _items())
    allowed = [f for f in report.findings if f.state == SPENDING.STATE_COMPLIANT][0]
    assert allowed.clause == "第八条"


# --------------------------------------------------------------------------
# §八 使用进度
# --------------------------------------------------------------------------
def test_progress_below():
    result = SPENDING.compute_progress(CTX.progress(REF_2022), year=2024,
                                       accrued=Decimal("100000"), used=Decimal("40000"))
    assert result.disclosure_required is True
    assert result.ratio == Decimal("0.40")


def test_progress_equal_threshold():
    result = SPENDING.compute_progress(CTX.progress(REF_2022), year=2024,
                                       accrued=Decimal("100"), used=Decimal("60"))
    assert result.disclosure_required is False


def test_progress_above():
    result = SPENDING.compute_progress(CTX.progress(REF_2022), year=2024,
                                       accrued=Decimal("100"), used=Decimal("80"))
    assert result.disclosure_required is False


def test_progress_zero_accrued():
    result = SPENDING.compute_progress(CTX.progress(REF_2022), year=2024,
                                       accrued=Decimal("0"), used=Decimal("0"))
    assert result.applicable is False
    assert result.disclosure_required is False


def test_progress_missing_threshold():
    with pytest.raises(ERRORS.SchemaError):
        SPENDING.compute_progress(CTX.progress(REF_2022), year=2024,
                                  accrued=Decimal("1"), used=Decimal("1"),
                                  threshold_id="nope")


def test_progress_points():
    result = SPENDING.compute_progress(CTX.progress(REF_2022), year=2024,
                                       accrued=Decimal("100"), used=Decimal("40"))
    assert result.points


def test_progress_ratio_quantized():
    result = SPENDING.compute_progress(CTX.progress(REF_2022), year=2024,
                                       accrued=Decimal("3"), used=Decimal("1"))
    assert result.ratio == Decimal("0.33")


def test_progress_result_as_dict():
    result = SPENDING.compute_progress(CTX.progress(REF_2022), year=2024,
                                       accrued=Decimal("100"), used=Decimal("40"))
    payload = result.as_dict()
    assert payload["disclosure_required"] is True
    assert payload["threshold"] == "0.6"


def test_progress_clause_from_rules():
    result = SPENDING.compute_progress(CTX.progress(REF_2022), year=2024,
                                       accrued=Decimal("100"), used=Decimal("40"))
    assert result.clause == "第五十一条"


def test_progress_threshold_value():
    result = SPENDING.compute_progress(CTX.progress(REF_2022), year=2024,
                                       accrued=Decimal("100"), used=Decimal("40"))
    assert result.threshold == Decimal("0.6")


# --------------------------------------------------------------------------
# §九 双版本对照
# --------------------------------------------------------------------------
def _diff():
    return DIFF.compare(_ruleset("2012"), _ruleset("2022"))


def test_diff_counts():
    counts = _diff().counts()
    assert sum(counts.values()) == len(_diff().items)


def test_diff_added():
    assert any(item.kind == "added" for item in _diff().items)


def test_diff_removed():
    assert any(item.kind == "removed" for item in _diff().items)


def test_diff_value_changed():
    assert any(item.kind == "value_changed" for item in _diff().items)


def test_diff_rate_changed():
    assert any(item.kind == "rate_changed" for item in _diff().items)


def test_diff_compared_industries():
    assert "coal" in _diff().compared_industries


def test_diff_as_dict():
    payload = _diff().as_dict()
    assert payload["old_doc_no"].startswith("财企")
    assert payload["new_doc_no"].startswith("财资")


def test_diff_same_ruleset_no_items():
    report = DIFF.compare(_ruleset("2022"), _ruleset("2022"))
    assert report.items == ()
    assert report.compared_industries


def test_diff_item_as_dict():
    item = _diff().items[0]
    payload = item.as_dict()
    assert set(payload) >= {"industry_id", "variant_id", "kind", "old_clause", "new_clause"}


def test_diff_segments_compared():
    # 超额累退节点的费率序列按 | 连接，避免两版费率差异被静默漏掉
    assert any(item.kind == "rate_changed" and "|" in (item.old_value or "")
               for item in _diff().items)


# --------------------------------------------------------------------------
# §十 编排（build_case / ledger / 年度锚定）
# --------------------------------------------------------------------------
def test_build_case_ok():
    case = _case()
    assert case.industry_id == "coal"
    assert case.basis_value == Decimal("120000")


def test_build_case_missing():
    with pytest.raises(ERRORS.MissingInput):
        PIPELINE.build_case({"enterprise_id": "E"})


def test_build_case_unknown_key():
    with pytest.raises(ERRORS.MissingInput):
        _case(extra_field="x")


def test_build_case_bad_year():
    with pytest.raises(ERRORS.MissingInput):
        _case(year="not-a-year")


def test_build_case_year_out_of_range():
    with pytest.raises(ERRORS.MissingInput):
        _case(year=1800)


def test_build_case_bad_value():
    with pytest.raises(ERRORS.MissingInput):
        _case(basis_value="abc")


def test_build_case_variant_none():
    payload = load_json(os.path.join(SAMPLES, "profile-hazardous.json"))["profile"]
    assert PIPELINE.build_case(payload).variant_id is None


def test_compute_calc_coal():
    report = PIPELINE.compute_calc(CTX, _case(), REF_2022)
    assert report.result.amount == Decimal("3600000.00")
    assert report.gate.ok


def test_compute_calc_2012_by_year():
    case = _case(year=2020, industry_id="fireworks", basis_kind="revenue",
                 basis_value="3000000", basis_unit="CNY", variant_id=None)
    report = PIPELINE.compute_calc(CTX, case)
    assert report.coordinate["version"] == "2012"


def test_compute_calc_inputs_required():
    profile = dict(enterprise_id="E", enterprise_name="N", industry_id="coal",
                   year=2024, basis_kind="output", basis_value="1", basis_unit="ton")
    report = PIPELINE.compute_calc(CTX, PIPELINE.build_case(profile), REF_2022)
    assert report.inputs_required == ("mine_type",)


def test_compute_calc_unit_warning():
    report = PIPELINE.compute_calc(CTX, _case(basis_value="12", basis_unit="CNY10k",
                                              variant_id="coal_high_gas"), REF_2022)
    assert report.result.amount == Decimal("3600000.00")
    assert any("定义性换算" in warning for warning in report.warnings)


def test_build_ledger_ok():
    items = _items()
    assert len(items) == 4
    assert items[0].amount == Decimal("120000.00")


def test_build_ledger_missing():
    with pytest.raises(ERRORS.MissingInput):
        PIPELINE.build_ledger([{"item_key": "X"}])


def test_build_ledger_bad_amount():
    with pytest.raises(ERRORS.MissingInput):
        PIPELINE.build_ledger([{"item_key": "X", "subject": "a", "summary": "b",
                                "amount": "abc"}])


def test_build_ledger_not_list():
    with pytest.raises(ERRORS.MissingInput):
        PIPELINE.build_ledger({"item_key": "X"})


def test_check_spending_ok():
    result = PIPELINE.check_spending(CTX, _case(), _items())
    assert result["gate_blocked"] is False
    assert result["report"].redlines


def test_progress_for_ok():
    result = PIPELINE.progress_for(CTX, _case(), accrued=Decimal("100000"),
                                   used=Decimal("40000"))
    assert result["gate_blocked"] is False
    assert result["report"].disclosure_required is True


def test_progress_for_2012_gate_blocked():
    case = _case(year=2020, industry_id="fireworks", basis_kind="revenue",
                 basis_value="3000000", basis_unit="CNY", variant_id=None)
    result = PIPELINE.progress_for(CTX, case, accrued=Decimal("100"),
                                   used=Decimal("40"))
    assert result["gate_blocked"] is True


def test_diff_for_none_same_version():
    assert PIPELINE.diff_for(CTX, 2024, 2025) is None


def test_diff_for_returns_report():
    report = PIPELINE.diff_for(CTX, 2020, 2024)
    assert report is not None and report.items


def test_context_cache():
    assert PIPELINE.context() is CTX


# --------------------------------------------------------------------------
# §十一 账本 / 输入契约 / CLI
# --------------------------------------------------------------------------
def test_coal_record_count():
    report = _records(_sample(COAL_SAMPLE))
    assert len(report.findings) == 3


def test_coal_no_fail():
    assert _records(_sample(COAL_SAMPLE)).exit_code() == 0


def test_ledger_record_count():
    report = _records(_sample(LEDGER_SAMPLE))
    assert len(report.findings) == 7


def test_ledger_exit_one():
    assert _records(_sample(LEDGER_SAMPLE)).exit_code() == 1


def test_ledger_spending_fail():
    report = _records(_sample(LEDGER_SAMPLE))
    record = _find(report.findings, "fee.spending:EXP-003")
    assert record.verdict == FAIL
    assert record.anchor.clause_id == "fee:2022:spending:SP-COAL-01" or \
        record.anchor.clause_id.startswith("fee:2022:spending:")


def test_spending_not_assessed_is_na():
    subject = _sample(COAL_SAMPLE)
    subject["ledger"] = [{"item_key": "X", "subject": "差旅费",
                          "summary": "员工差旅报销", "amount": "1.00"}]
    record = _find(_records(subject).findings, PACK_MOD.RULE_SPENDING + ":X")
    assert record.verdict == NOT_APPLICABLE
    assert record.anchor is None


def test_progress_record_count():
    report = _records(_sample(PROGRESS_SAMPLE))
    assert len(report.findings) == 4


def test_progress_exit_zero():
    assert _records(_sample(PROGRESS_SAMPLE)).exit_code() == 0


def test_progress_disclosure_message():
    record = _find(_records(_sample(PROGRESS_SAMPLE)).findings, PACK_MOD.RULE_PROGRESS)
    assert "须" in record.message and record.evidence["disclosure_required"] is True


def test_compare_record_count():
    report = _records(_sample(COMPARE_SAMPLE))
    assert len(report.findings) == 4


def test_compare_diff_record():
    record = _find(_records(_sample(COMPARE_SAMPLE)).findings, PACK_MOD.RULE_DIFF)
    assert record.verdict == PASS
    assert record.evidence["items"]


def test_compare_exit_zero():
    assert _records(_sample(COMPARE_SAMPLE)).exit_code() == 0


def test_2012_progress_gate_fail():
    subject = _sample(COAL_SAMPLE)
    subject["profile"]["year"] = 2020
    subject["profile"]["industry_id"] = "fireworks"
    subject["profile"]["basis_kind"] = "revenue"
    subject["profile"]["basis_value"] = "3000000"
    subject["profile"]["basis_unit"] = "CNY"
    subject["profile"].pop("variant_id", None)
    subject["progress"] = {"accrued": "100000", "used": "40000"}
    report = _records(subject)
    record = _find(report.findings, PACK_MOD.RULE_GATE + ":progress")
    assert record.verdict == FAIL
    assert report.exit_code() == 1


def test_rules_finding_anchor():
    record = _find(_records(_sample(COAL_SAMPLE)).findings, PACK_MOD.RULE_RULES)
    assert record.anchor.clause_id == PACK_MOD.CLAUSE_RULES
    assert record.evidence["next_review"] == "2027-10-14"


def test_accrual_finding_anchor():
    record = _find(_records(_sample(COAL_SAMPLE)).findings, PACK_MOD.RULE_ACCRUAL)
    assert record.anchor.clause_id == "fee:2022:variant:coal:coal_high_gas"


def test_summary_pass():
    record = _find(_records(_sample(COAL_SAMPLE)).findings, PACK_MOD.RULE_SUMMARY)
    assert record.verdict == PASS


def test_summary_fail():
    record = _find(_records(_sample(LEDGER_SAMPLE)).findings, PACK_MOD.RULE_SUMMARY)
    assert record.verdict == FAIL


def test_every_non_na_record_has_anchor():
    report = _records(_sample(LEDGER_SAMPLE))
    for record in report.findings:
        if record.verdict != NOT_APPLICABLE:
            assert record.anchor is not None


def test_subject_requires_case_id():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"profile": _sample(COAL_SAMPLE)["profile"]}, BASIS)


def test_subject_requires_profile():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c"}, BASIS)


def test_subject_unknown_key():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "profile": {}, "extra": 1}, BASIS)


def test_subject_ledger_type():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c",
                           "profile": _sample(COAL_SAMPLE)["profile"],
                           "ledger": {}}, BASIS)


def test_subject_progress_type():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c",
                           "profile": _sample(COAL_SAMPLE)["profile"],
                           "progress": []}, BASIS)


def test_subject_compare_type():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c",
                           "profile": _sample(COAL_SAMPLE)["profile"],
                           u"compare": "yes"}, BASIS)


def test_subject_progress_used_required():
    subject = _sample(COAL_SAMPLE)
    subject["progress"] = {"accrued": "1"}
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(subject, BASIS)


def test_subject_inputs_required_rc2():
    subject = {"case_id": "c", "profile": {"enterprise_id": "E",
                                           "enterprise_name": "N",
                                           "industry_id": "coal", "year": 2024,
                                           "basis_kind": "output",
                                           "basis_value": "1", "basis_unit": "ton"}}
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(subject, BASIS)


def test_basis_version_mismatch():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(_sample(COAL_SAMPLE), Basis.empty("1999-01-01"))


def test_basis_missing_clause():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(_sample(COAL_SAMPLE), Basis(REG.VERSION))


def test_cli_list_contains_slug(capsys):
    assert cp_cli.main(["list"]) == 0
    assert SLUG in capsys.readouterr().out


def test_cli_coal_rc0():
    assert cp_cli.main(["check", SLUG, "--input", COAL_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_ledger_rc1():
    assert cp_cli.main(["check", SLUG, "--input", LEDGER_SAMPLE,
                        "--basis", BASIS_PATH]) == 1


def test_cli_progress_rc0():
    assert cp_cli.main(["check", SLUG, "--input", PROGRESS_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_missing_basis_rc3():
    assert cp_cli.main(["check", SLUG, "--input", COAL_SAMPLE]) == 3


def test_cli_missing_input_rc2():
    assert cp_cli.main(["check", SLUG, "--input", os.path.join(SAMPLES, "nope.json"),
                        "--basis", BASIS_PATH]) == 2


def test_cli_json(capsys):
    assert cp_cli.main(["check", SLUG, "--input", COAL_SAMPLE,
                        "--basis", BASIS_PATH, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG
    assert payload["summary"]["verdicts"]["fail"] == 0


# --------------------------------------------------------------------------
# §十二 随包数据完整性
# --------------------------------------------------------------------------
def _manifest():
    return load_json(os.path.join(DATA_DIR, "manifest.json"))


def test_data_manifest_file_set():
    assert set(_manifest()["files"]) == set(REG.DATA_FILES)


def test_data_manifest_sha256():
    import hashlib
    for name, record in _manifest()["files"].items():
        raw = open(os.path.join(DATA_DIR, name), "rb").read()
        assert record["bytes"] == len(raw)
        assert record["sha256"] == hashlib.sha256(raw).hexdigest()


def test_data_manifest_counts():
    manifest = _manifest()
    assert manifest["clause_count"] == len(Basis.from_json(BASIS_PATH)) == 167
    assert manifest["truth_cases"] == 122
    assert manifest["truth_negatives"] == 7


def test_data_manifest_version():
    assert _manifest()["version"] == REG.VERSION


def test_data_files_lf_only():
    for name in REG.DATA_FILES + ("manifest.json",):
        raw = open(os.path.join(DATA_DIR, name), "rb").read()
        assert b"\r\n" not in raw


def test_data_clauses_all_versioned():
    data = load_json(BASIS_PATH)
    assert data["version"] == REG.VERSION
    for entry in data["clauses"]:
        assert entry["version"] == REG.VERSION


def test_data_every_industry_has_clause():
    for version in ("2012", "2022"):
        ruleset = _ruleset(version)
        for industry in ruleset.get("industries", []):
            assert BASIS.clause("fee:%s:industry:%s"
                                % (version, industry["industry_id"])) is not None


def test_data_every_variant_has_clause():
    for version in ("2012", "2022"):
        ruleset = _ruleset(version)
        for industry in ruleset.get("industries", []):
            for variant in industry.get("variants") or []:
                assert BASIS.clause("fee:%s:variant:%s:%s"
                                    % (version, industry["industry_id"],
                                       variant["variant_id"])) is not None


def test_data_every_spending_entry_has_clause():
    for version in ("2012", "2022"):
        ref = REF_2022 if version == "2022" else REF_2012
        spending = CTX.spending(ref)
        for entry in spending["entries"]:
            assert BASIS.clause("fee:%s:spending:%s"
                                % (version, entry["entry_id"])) is not None


def test_data_every_progress_threshold_has_clause():
    for version in ("2012", "2022"):
        ref = REF_2022 if version == "2022" else REF_2012
        progress = CTX.progress(ref)
        for threshold in progress["thresholds"]:
            assert BASIS.clause("fee:%s:progress:%s"
                                % (version, threshold.get("threshold_id", "default"))
                                ) is not None


def test_data_pending_clause_marked():
    clause = BASIS.clause("fee:2012:progress:default")
    assert clause.text.startswith("【待核对】")


def test_data_contracts_registered():
    expected = {PACK_MOD.CLAUSE_VERSION, PACK_MOD.CLAUSE_RULES,
                PACK_MOD.CLAUSE_GATE, PACK_MOD.CLAUSE_ACCRUAL,
                PACK_MOD.CLAUSE_BASIS, PACK_MOD.CLAUSE_TIERED,
                PACK_MOD.CLAUSE_UNITS, PACK_MOD.CLAUSE_SPENDING,
                PACK_MOD.CLAUSE_NOT_ASSESSED, PACK_MOD.CLAUSE_PROGRESS,
                PACK_MOD.CLAUSE_DIFF, PACK_MOD.CLAUSE_INPUT,
                PACK_MOD.CLAUSE_SUMMARY}
    assert all(BASIS.clause(clause_id) is not None for clause_id in expected)


def test_data_doc_clauses_registered():
    knowledge = load_json(os.path.join(DATA_DIR, "clauses.json"))
    doc_clauses = [entry["clause_id"] for entry in knowledge["clauses"]
                   if entry["clause_id"].startswith("fee:doc:")]
    assert len(doc_clauses) == 8


# --------------------------------------------------------------------------
# §十三 真值库对账（122 例 + 7 误报对照；来源 bench 口径）
# --------------------------------------------------------------------------
@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_truth_case_amount_and_mechanism(case):
    report = PIPELINE.compute_calc(CTX, PIPELINE.build_case(case["enterprise"]),
                                   REFS[case["ruleset_id"]])
    expected = case["expect"]
    assert report.gate.ok
    assert report.result is not None
    assert str(report.result.amount) == str(expected["amount"])
    assert report.result.mechanism == expected["mechanism"]
    also = expected.get("also_expect") or {}
    if "clause" in also:
        assert report.result.clause == also["clause"]


@pytest.mark.parametrize("negative", NEGATIVES,
                         ids=[item["negative_id"] for item in NEGATIVES])
def test_truth_negative(negative):
    report = PIPELINE.compute_calc(CTX, PIPELINE.build_case(negative["enterprise"]),
                                   REFS[negative["ruleset_id"]])
    warnings = list(report.warnings)
    if negative["expect"].get("zero_hit"):
        assert warnings == []
    elif negative["expect"].get("downgrade_warning"):
        assert any("定义性换算" in warning for warning in warnings)


def test_truth_case_counts():
    assert TRUTH["case_count"] == len(CASES) == 122
    assert TRUTH["negative_count"] == len(NEGATIVES) == 7


def test_truth_rulesets_covered():
    assert {case["ruleset_id"] for case in CASES} == {"财企-2012-16", "财资-2022-136"}


def test_truth_amounts_are_two_decimals():
    for case in CASES:
        assert str(case["expect"]["amount"]).count(".") == 1


def test_truth_notes_present():
    assert all(case.get("note") for case in CASES)