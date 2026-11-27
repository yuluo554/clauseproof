"""器官 ``income-tax`` 无损判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在「判定结果」上。
来源仓判定层（D1 + D18 机械选 11 文件 / 实跑 107 passed / AST 函数 107）逐文件
处置见 ``docs/income-tax.md`` §6；本文件承载八个年度规则包与 status 门控、累计
预扣逐月状态机、年度汇算、社保联动、七项专项附加申报校验/分链、年终奖单独计税/
双方案择优/临界区间推导，以及账本映射 + 真值库对账 + 漂移门。

来源仓只读；合成规则包一律**内存注入**（``evaluate_with_rulesets``），不写盘。
"""

import ast
import copy
import importlib
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from clauseproof import cli as cp_cli  # noqa: E402
from clauseproof.core.basis import Basis, BasisMissing  # noqa: E402
from clauseproof.core.ledger import (  # noqa: E402
    EXIT_BLOCKED,
    EXIT_CONTRACT,
    EXIT_INPUT,
    EXIT_OK,
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Report,
)
from clauseproof.core.registry import Pack, all_packs, get  # noqa: E402

PACK_MOD = importlib.import_module("clauseproof.packs.income-tax")
M = importlib.import_module("clauseproof.packs.income-tax.monthly")
SO = importlib.import_module("clauseproof.packs.income-tax.social")
SE = importlib.import_module("clauseproof.packs.income-tax.settlement")
D = importlib.import_module("clauseproof.packs.income-tax.deductions")
B = importlib.import_module("clauseproof.packs.income-tax.bonus")
P = importlib.import_module("clauseproof.packs.income-tax.pipeline")
R = importlib.import_module("clauseproof.packs.income-tax.rules")
REG = importlib.import_module("clauseproof.packs.income-tax.registry")
MONEY = importlib.import_module("clauseproof.packs.income-tax.money")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "income-tax")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "income-tax")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
README_SAMPLE = os.path.join(SAMPLES, "readme-example.json")
REJECT_SAMPLE = os.path.join(SAMPLES, "claims-reject.json")
TRAP_SAMPLE = os.path.join(SAMPLES, "trap-2024.json")
ALL_YEARS = list(range(2019, 2027))


# --------------------------------------------------------------------------
# 公共夹具（装配面读随包冻结资产；判定面只收内存 dict）
# --------------------------------------------------------------------------
def basis():
    return Basis.from_json(BASIS_PATH)


def eff(year=2024):
    return R.effective_ruleset(REG.ruleset(year))


def subject(path=README_SAMPLE):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def findings(sub=None):
    return tuple(PACK_MOD.evaluate(subject() if sub is None else sub, basis()))


def report(sub=None, name="case.json"):
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject=name, findings=findings(sub))


def by_rule(fs, rule_id):
    return [f for f in fs if f.rule_id == rule_id]


def raw_copy(year):
    """原始规则包的可变副本（合成门控/政策到期路径用；不写盘）。"""
    return copy.deepcopy(REG.raw_packs()[year])


def synthetic(raw, year):
    """把 raw 内嵌 year 同步后构建 Ruleset（不写盘、不碰来源）。"""
    data = json.loads(json.dumps(raw, ensure_ascii=False, default=str))
    data["year"] = year
    return R.build_ruleset(data, expected_year=year)


def flip_one_node_pending(raw):
    """把一个数值条目翻回待核对（构造门控拦截的合成包）。"""

    def walk(node):
        if isinstance(node, dict):
            if node.get("status") == "已核对" and "value" in node:
                node["status"] = "待核对"
                return True
            for child in node.values():
                if walk(child):
                    return True
        elif isinstance(node, list):
            for child in node:
                if walk(child):
                    return True
        return False

    walk(raw)
    return raw


def violation_reason(year, *claims):
    with pytest.raises(D.DeductionViolationError) as excinfo:
        D.evaluate_claims(eff(year), list(claims))
    return str(excinfo.value)


def evaluate(year, *claims):
    return D.evaluate_claims(eff(year), list(claims))


def settle(year=2024, **kwargs):
    return SE.compute_annual_settlement(eff(year), SE.SettlementInput(**kwargs))


def bonus_of(amount, year=2024):
    return B.compute_bonus_separate_tax(eff(year), amount)


def salary_settlement(year=2024, annual_gross="60000.00"):
    return SE.compute_annual_settlement(
        eff(year), SE.SettlementInput(annual_gross=Decimal(annual_gross)))


def run_2019(months):
    return M.compute_monthly_withholding(eff(2019), months)


def claim_subject(year, *claims, **extra):
    sub = {"year": year, "uniform_month": {"gross": "20000.00"}, "month_count": 12}
    sub["special_additional_claims"] = list(claims)
    sub.update(extra)
    return sub


def _flatten(node, prefix=""):
    out = {}
    if isinstance(node, dict):
        for key, value in node.items():
            out.update(_flatten(value, prefix + "." + key if prefix else key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out.update(_flatten(value, "%s[%d]" % (prefix, i)))
    else:
        out[prefix] = Decimal(node)  # 两侧同构：真值字符串与实际 Decimal 同口径对账
    return out


def check_case(case_id, actual_nested):
    case = REG.truth_cases()[case_id]
    wanted = _flatten(case["expected"])
    wanted.update(_flatten(case.get("also_expect", {})))
    actual = _flatten(actual_nested)
    assert set(actual) == set(wanted), (
        f"{case_id}: 字段覆盖差异缺失={sorted(set(wanted) - set(actual))} "
        f"多余={sorted(set(actual) - set(wanted))}"
    )
    for key, want in wanted.items():
        assert actual[key] == want, f"{case_id}.{key}: 引擎={actual[key]} 真值={want}"


# ==========================================================================
# 一、器官契约与随包装配
# ==========================================================================
def test_pack_is_registered_under_slug():
    pack = get(SLUG)
    assert isinstance(pack, Pack)
    assert pack.slug == SLUG
    assert pack.version == PACK_MOD.VERSION


def test_pack_version():
    assert PACK_MOD.VERSION == "0.1.0"


def test_pack_input_fields():
    assert PACK_MOD.INPUT_FIELDS == ("year",)


def test_slug_in_builtin_modules_sorted():
    packs_ns = importlib.import_module("clauseproof.packs")
    assert SLUG in packs_ns.BUILTIN_MODULES
    assert list(packs_ns.BUILTIN_MODULES) == sorted(packs_ns.BUILTIN_MODULES)


def test_manifest_years_cover_full_range():
    assert list(REG.years()) == ALL_YEARS


def test_pack_filenames_match_manifest():
    names = sorted(os.listdir(DATA_DIR))
    for name in REG.pack_filenames():
        assert name in names


def test_all_rulesets_schema_valid():
    for year in ALL_YEARS:
        rs = REG.ruleset(year)
        assert rs.year == year
        assert len(rs.comprehensive_brackets) == 7
        assert len(rs.monthly_brackets) == 7


def test_ruleset_sha256_match_manifest():
    import hashlib
    for entry in REG.pack_entries():
        with open(os.path.join(DATA_DIR, entry["file"]), "rb") as handle:
            raw = handle.read()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        assert len(raw) == entry["bytes"]


def test_truth_sha256_match_manifest():
    import hashlib
    entry = REG.manifest()["truth"]
    with open(os.path.join(DATA_DIR, entry["file"]), "rb") as handle:
        raw = handle.read()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
    assert entry["cases"] == len(REG.truth()["cases"])


def test_clauses_version_matches_snapshot():
    assert basis().version == REG.PARAMS_VERSION
    assert REG.manifest()["version"] == REG.PARAMS_VERSION


def test_clause_ids_unique():
    ids = REG.clause_ids()
    assert len(ids) == len(set(ids))


def test_every_pack_ref_has_clause():
    have = set(REG.clause_ids())
    for year in ALL_YEARS:
        for key in REG.refs_used(year):
            assert key in have, (year, key)


def test_contract_clauses_registered():
    have = set(REG.clause_ids())
    for key in REG.CONTRACT_CLAUSES:
        assert key in have


def test_basis_loads_all_clauses():
    assert len(basis()) == REG.manifest()["clauses"]["count"]
    assert "contract:status-gate" in basis().clause_ids()


# ==========================================================================
# 二、规则包 schema / status 门控（来源 test_rules_loader 移植 + 内存注入）
# ==========================================================================
def test_structure_2026():
    rs = REG.ruleset(2026)
    assert rs.year == 2026
    first = rs.comprehensive_brackets[0]
    assert first.lower == Decimal(0)
    assert first.rate == Decimal("0.03")
    last = rs.comprehensive_brackets[-1]
    assert last.upper is None
    assert last.rate == Decimal("0.45")
    assert rs.monthly_standard_deduction == Decimal(5000)


def test_rate_tables_identical_across_years():
    base = REG.ruleset(2019)
    for year in ALL_YEARS[1:]:
        rs = REG.ruleset(year)
        assert base.comprehensive_brackets == rs.comprehensive_brackets, year
        assert base.monthly_brackets == rs.monthly_brackets, year


def test_years_range():
    assert REG.years() == tuple(range(2019, 2027))


def test_missing_year_lists_available():
    with pytest.raises(R.RulesetNotFoundError) as excinfo:
        REG.ruleset(1999)
    assert excinfo.value.available == ALL_YEARS


def test_all_years_all_verified():
    for year in ALL_YEARS:
        rs = REG.ruleset(year)
        report = R.status_report(rs)
        assert report.pending == 0, (year, report.pending_paths)
        assert report.verified > 0
        assert report.all_effective
        assert R.effective_ruleset(rs) is rs


def test_year_differences_match_policy_chain():
    r2019 = REG.ruleset(2019).data["special_deductions"]
    assert "infant_care" not in r2019
    assert r2019["child_education"]["monthly_per_child"]["value"] == 1000
    assert r2019["support_elderly"]["only_child_monthly"]["value"] == 2000
    assert REG.ruleset(2021).data["bonus"]["separate_tax_policy"]["valid_until"] == "2021-12-31"
    assert REG.ruleset(2021).data["bonus"]["separate_tax_policy"]["ref"]["source"] == "S164"
    r2022 = REG.ruleset(2022).data["special_deductions"]
    assert "infant_care" in r2022
    assert r2022["infant_care"]["monthly_per_child"]["value"] == 1000
    assert REG.ruleset(2022).data["bonus"]["separate_tax_policy"]["ref"]["source"] == "S42"
    assert REG.ruleset(2022).data["bonus"]["separate_tax_policy"]["valid_until"] == "2023-12-31"
    for year in (2023, 2026):
        sd = REG.ruleset(year).data["special_deductions"]
        assert sd["infant_care"]["monthly_per_child"]["value"] == 2000
        assert sd["child_education"]["monthly_per_child"]["value"] == 2000
        assert sd["support_elderly"]["only_child_monthly"]["value"] == 3000
        assert sd["support_elderly"]["shared_per_child_cap"]["value"] == 1500
        policy = REG.ruleset(year).data["bonus"]["separate_tax_policy"]
        assert policy["ref"]["source"] == "S30"
        assert policy["valid_until"] == "2027-12-31"


def test_status_report_2026_all_verified():
    report = R.status_report(REG.ruleset(2026))
    assert report.pending == 0
    assert report.pending_paths == ()
    assert report.all_effective


def test_effective_gating_blocks_synthetic_pending():
    raw = flip_one_node_pending(raw_copy(2026))
    rs = synthetic(raw, 2099)
    report = R.status_report(rs)
    assert report.pending == 1
    assert not report.all_effective
    with pytest.raises(R.RulesetNotEffective) as excinfo:
        R.effective_ruleset(rs)
    assert len(excinfo.value.pending_paths) == 1
    assert "待核对" in str(excinfo.value)


def test_gate_opens_when_all_verified():
    assert R.effective_ruleset(REG.ruleset(2026)) is REG.ruleset(2026)


def test_missing_status_defaults_to_pending():
    raw = raw_copy(2026)
    raw["withholding"]["monthly_standard_deduction"].pop("status")
    report = R.status_report(synthetic(raw, 2098))
    assert "withholding.monthly_standard_deduction" in report.pending_paths


def test_schema_missing_section():
    raw = raw_copy(2026)
    raw.pop("bonus")
    with pytest.raises(R.RulesetSchemaError) as excinfo:
        synthetic(raw, 2097)
    assert "bonus" in str(excinfo.value)


def test_schema_year_mismatch():
    raw = raw_copy(2026)
    raw["year"] = 2026  # 请求 2099 → 文件内 year 不一致
    with pytest.raises(R.RulesetSchemaError) as excinfo:
        R.build_ruleset(raw, expected_year=2099)
    assert "不一致" in str(excinfo.value)


def test_schema_mutex_flag_required():
    raw = raw_copy(2026)
    raw["special_deductions"]["housing_loan_vs_rent"] = "exclusive"
    with pytest.raises(R.RulesetSchemaError) as excinfo:
        synthetic(raw, 2096)
    assert "mutually_exclusive" in str(excinfo.value)


def test_schema_rate_table_must_be_contiguous():
    raw = raw_copy(2026)
    raw["rate_tables"]["comprehensive_annual"][3]["lower"] = 123456
    with pytest.raises(R.RulesetSchemaError) as excinfo:
        synthetic(raw, 2095)
    assert "不相接" in str(excinfo.value)


def test_schema_value_node_requires_ref():
    raw = raw_copy(2026)
    raw["special_deductions"]["continue_education"]["academic_monthly"].pop("ref")
    with pytest.raises(R.RulesetSchemaError) as excinfo:
        synthetic(raw, 2094)
    assert "ref" in str(excinfo.value)


def test_schema_invalid_status_rejected():
    raw = raw_copy(2026)
    raw["special_deductions"]["continue_education"]["academic_monthly"]["status"] = "大概吧"
    with pytest.raises(R.RulesetSchemaError) as excinfo:
        synthetic(raw, 2093)
    assert "status" in str(excinfo.value)


def test_all_sources_have_reviewed_at():
    for year in ALL_YEARS:
        for src in REG.ruleset(year).data["sources"]:
            assert "reviewed_at" in src, (year, src.get("id"))
            assert len(src["reviewed_at"]) == 10
            assert src["reviewed_at"][4] == "-" and src["reviewed_at"][7] == "-"


def test_all_rulesets_have_review_block():
    expected_basis = {**{y: 2019 for y in (2019, 2020, 2021)}, 2022: 2022}
    expected_basis.update({y: 2023 for y in (2023, 2024, 2025, 2026)})
    for year in ALL_YEARS:
        review = REG.ruleset(year).data["review"]
        assert isinstance(review, dict)
        for name in R.REVIEW_FIELDS:
            assert name in review, (year, name)
        assert review["basis_year"] == expected_basis[year]
        assert isinstance(review["carry_forward_years"], list)
        assert all(isinstance(y, int) and not isinstance(y, bool)
                   for y in review["carry_forward_years"])
    assert REG.ruleset(2026).data["review"]["carry_forward_years"] == [2024, 2025, 2026]
    assert REG.ruleset(2022).data["review"]["carry_forward_years"] == []


def test_review_dates_valid_and_ordered():
    from datetime import date
    for year in ALL_YEARS:
        review = REG.ruleset(year).data["review"]
        reviewed_at = date.fromisoformat(review["reviewed_at"])
        next_review = date.fromisoformat(review["next_review"])
        assert next_review > reviewed_at, year
        for src in REG.ruleset(year).data["sources"]:
            date.fromisoformat(src["reviewed_at"])


def test_schema_rejects_missing_reviewed_at():
    raw = raw_copy(2026)
    raw["sources"][0].pop("reviewed_at")
    with pytest.raises(R.RulesetSchemaError) as excinfo:
        synthetic(raw, 2092)
    assert "reviewed_at" in str(excinfo.value)


def test_schema_rejects_bad_next_review():
    raw = raw_copy(2026)
    raw["review"]["next_review"] = raw["review"]["reviewed_at"]
    with pytest.raises(R.RulesetSchemaError) as excinfo:
        synthetic(raw, 2091)
    assert "next_review" in str(excinfo.value)


def test_to_decimal_rejects_bool_and_junk():
    with pytest.raises(R.RulesetSchemaError):
        R.to_decimal(True, "x")
    with pytest.raises(R.RulesetSchemaError):
        R.to_decimal("abc", "x")
    assert R.to_decimal("1.20", "x") == Decimal("1.20")


def test_parse_iso_date_strict():
    assert R.parse_iso_date("2026-10-07", "x").isoformat() == "2026-10-07"
    with pytest.raises(R.RulesetSchemaError):
        R.parse_iso_date("2026-1-7", "x")


# ==========================================================================
# 三、累计预扣逐月引擎（来源 test_engine_monthly 8 条）
# ==========================================================================
def test_truth_case_three_months_uniform():
    report = run_2019([M.MonthInput(gross=Decimal("10000.00"),
                                    special_deduction=Decimal("2000.00"))] * 3)
    assert [m.cumulative_taxable for m in report.months] == [Decimal(3000), Decimal(6000), Decimal(9000)]
    assert [m.cumulative_standard_deduction for m in report.months] == [
        Decimal(5000), Decimal(10000), Decimal(15000)]
    assert [m.cumulative_tax for m in report.months] == [
        Decimal("90.00"), Decimal("180.00"), Decimal("270.00")]
    assert [m.withholding for m in report.months] == [Decimal("90.00")] * 3
    assert report.withheld_total == Decimal("270.00")
    assert all(m.bracket_index == 0 for m in report.months)


def test_bracket_jump_mid_year_progressive():
    report = run_2019([M.MonthInput(gross=Decimal("30000.00"),
                                    special_deduction=Decimal("2000.00"))] * 3)
    m1, m2, m3 = report.months
    assert m1.cumulative_taxable == Decimal(23000)
    assert m1.bracket_index == 0 and m1.withholding == Decimal("690.00")
    assert m2.cumulative_taxable == Decimal(46000)
    assert m2.bracket_index == 1
    assert m2.cumulative_tax == Decimal("2080.00")
    assert m2.withholding == Decimal("1390.00")
    assert m3.cumulative_taxable == Decimal(69000)
    assert m3.cumulative_tax == Decimal("4380.00")
    assert m3.withholding == Decimal("2300.00")


def test_nonpositive_cumulative_taxable_is_zero_tax():
    report = run_2019([M.MonthInput(gross=Decimal("0.00"))] * 3)
    for m in report.months:
        assert m.cumulative_taxable < 0
        assert m.bracket_index is None
        assert m.cumulative_tax == Decimal("0.00")
        assert m.withholding == Decimal("0.00")


def test_negative_withholding_clamped_no_refund():
    months = [M.MonthInput(gross=Decimal("100000.00"))] + [M.MonthInput(gross=Decimal("0.00"))] * 11
    report = run_2019(months)
    m1 = report.months[0]
    assert m1.bracket_index == 1
    assert m1.withholding == Decimal("6980.00")
    for later in report.months[1:]:
        assert later.withholding == Decimal("0.00")
        assert "暂不退税" in later.note
    assert report.months[-1].cumulative_tax == Decimal("1480.00")
    assert report.withheld_total == Decimal("6980.00")


def test_recovery_after_zero_months_pays_full_cumulative():
    report = run_2019([M.MonthInput(gross=Decimal("0.00")),
                       M.MonthInput(gross=Decimal("20000.00"))])
    assert report.months[0].withholding == Decimal("0.00")
    m2 = report.months[1]
    assert m2.cumulative_taxable == Decimal(10000)
    assert m2.withholding == Decimal("300.00")


def test_social_linkage_note_propagates():
    report = run_2019([M.MonthInput(
        gross=Decimal("10000"), special_deduction=Decimal("2250.00"),
        note="含社保公积金个人部分 2250.00 元/月（社保联动计算）")])
    assert "社保联动" in report.months[0].note


def test_month_count_bounds():
    with pytest.raises(ValueError):
        M.compute_monthly_withholding(eff(2026), [])
    with pytest.raises(ValueError):
        M.compute_monthly_withholding(eff(2026), [M.MonthInput()] * 13)


def test_find_bracket_inclusive_upper_official_semantics():
    brackets = eff(2026).comprehensive_brackets
    assert M.find_bracket(brackets, Decimal(36000))[0] == 0
    assert M.find_bracket(brackets, Decimal("36000.01"))[0] == 1
    assert M.find_bracket(brackets, Decimal(144000))[0] == 1
    assert M.find_bracket(brackets, Decimal("0.01"))[0] == 0
    with pytest.raises(ValueError):
        M.find_bracket(brackets, Decimal(0))


# ==========================================================================
# 四、年度汇算（来源 test_engine_settlement 5 条）
# ==========================================================================
def test_truth_case_settlement_2024():
    r = settle(
        annual_gross=Decimal("200000.00"),
        annual_special_deduction=Decimal("40000.00"),
        annual_special_additional_deduction=Decimal("60000.00"),
    )
    assert r.annual_standard_deduction == Decimal("60000.00")
    assert r.cumulative_taxable_income == Decimal("40000.00")
    assert r.bracket_index == 1 and r.rate == Decimal("0.10")
    assert r.annual_tax == Decimal("1480.00")


def test_refund_when_overwithheld():
    r = settle(annual_gross=Decimal("120000.00"), withheld_total=Decimal("864.00"))
    assert r.annual_tax == Decimal("3480.00")
    assert r.refund_or_owe == Decimal("-2616.00")


def test_owe_when_underwithheld_sign_convention():
    a = settle(annual_gross=Decimal("120000.00"), withheld_total=Decimal("3000.00"))
    assert a.refund_or_owe == Decimal("-480.00")
    b = settle(annual_gross=Decimal("120000.00"), withheld_total=Decimal("4000.00"))
    assert b.refund_or_owe == Decimal("520.00")


def test_nonpositive_taxable_full_refund():
    r = settle(annual_gross=Decimal("50000.00"), withheld_total=Decimal("150.00"))
    assert r.cumulative_taxable_income == Decimal("-10000.00")
    assert r.bracket_index is None
    assert r.annual_tax == Decimal("0.00")
    assert r.refund_or_owe == Decimal("150.00")
    assert "汇算退还" in r.note


def test_negative_withheld_rejected():
    with pytest.raises(ValueError):
        settle(annual_gross=Decimal("120000.00"), withheld_total=Decimal("-0.01"))


# ==========================================================================
# 五、社保联动（来源 test_engine_social 4 条）
# ==========================================================================
def test_within_range_base_sum_of_items():
    r = SO.compute_social_insurance(
        Decimal("10000.00"),
        {"养老": Decimal("0.08"), "医疗": Decimal("0.02"),
         "失业": Decimal("0.005"), "公积金": Decimal("0.12")},
        Decimal("4000.00"), Decimal("25000.00"),
    )
    assert r.clamped_base == Decimal("10000.00")
    assert r.clamp_note == ""
    assert [i.personal_amount for i in r.items] == [
        Decimal("800.00"), Decimal("200.00"), Decimal("50.00"), Decimal("1200.00")]
    assert r.total == Decimal("2250.00")
    assert "社保联动" in r.source_note


def test_base_clamped_to_lower_and_upper():
    rates = {"养老": Decimal("0.08")}
    low = SO.compute_social_insurance(Decimal("3000.00"), rates, Decimal("4000.00"), Decimal("25000.00"))
    assert low.clamped_base == Decimal("4000.00")
    assert low.total == Decimal("320.00")
    assert "夹取" in low.clamp_note
    high = SO.compute_social_insurance(Decimal("30000.00"), rates, Decimal("4000.00"), Decimal("25000.00"))
    assert high.clamped_base == Decimal("25000.00")
    assert high.total == Decimal("2000.00")
    assert "夹取" in high.clamp_note


def test_empty_and_negative_inputs_rejected():
    with pytest.raises(ValueError):
        SO.compute_social_insurance(Decimal("10000"), {}, Decimal("4000"), Decimal("25000"))
    with pytest.raises(ValueError):
        SO.compute_social_insurance(Decimal("10000"), {"养老": Decimal("-0.08")}, Decimal("4000"), Decimal("25000"))
    with pytest.raises(ValueError):
        SO.compute_social_insurance(Decimal("-1"), {"养老": Decimal("0.08")}, Decimal("4000"), Decimal("25000"))


def test_lower_above_upper_rejected():
    with pytest.raises(ValueError):
        SO.compute_social_insurance(Decimal("10000"), {"养老": Decimal("0.08")}, Decimal("25000"), Decimal("4000"))


# ==========================================================================
# 六、七项专项附加扣除（来源 test_engine_deductions 31 条）
# ==========================================================================
def test_child_education_standard_2024():
    claim = evaluate(2024, D.Claim(item="child_education")).claims[0]
    assert claim.monthly_amount == Decimal("2000.00")
    assert claim.annual_amount == Decimal("24000.00")
    assert claim.stage == D.STAGE_BOTH and claim.months_claimed == 12


def test_child_education_half_share_two_children():
    report = evaluate(2024, D.Claim(item="child_education", children=2,
                                    share_ratio=Decimal("0.5")))
    assert report.claims[0].monthly_amount == Decimal("2000.00")
    assert report.annual_total == Decimal("24000.00")


def test_child_education_2019_uses_old_standard():
    report = evaluate(2019, D.Claim(item="child_education"))
    assert report.claims[0].monthly_amount == Decimal("1000.00")
    assert report.annual_total == Decimal("12000.00")


def test_child_education_invalid_share_ratio_rejected():
    reason = violation_reason(2024, D.Claim(item="child_education", share_ratio=Decimal("0.3")))
    assert "分摊比例" in reason and "第六条" in reason


def test_child_education_fractional_children_rejected():
    reason = violation_reason(2024, D.Claim(item="child_education", children=Decimal("1.5")))
    assert "孩数" in reason


def test_infant_care_standards_by_year():
    assert evaluate(2022, D.Claim(item="infant_care")).claims[0].monthly_amount == Decimal("1000.00")
    assert evaluate(2024, D.Claim(item="infant_care")).claims[0].monthly_amount == Decimal("2000.00")


def test_infant_care_not_available_before_introduction_year():
    reason = violation_reason(2019, D.Claim(item="infant_care"))
    assert "无此扣除项" in reason


def test_continue_education_academic_monthly():
    r = evaluate(2024, D.Claim(item="continue_education", kind="academic", months=12))
    assert r.claims[0].monthly_amount == Decimal("400.00")
    assert r.claims[0].annual_amount == Decimal("4800.00")


def test_continue_education_months_within_single_year():
    reason = violation_reason(2024, D.Claim(item="continue_education", kind="academic", months=13))
    assert "申报月数" in reason


def test_continue_education_academic_max_months_cap():
    raw = raw_copy(2024)
    raw["special_deductions"]["continue_education"]["academic_max_months"]["value"] = 6
    rs = R.effective_ruleset(synthetic(raw, 2099))
    with pytest.raises(D.DeductionViolationError) as excinfo:
        D.evaluate_claims(rs, [D.Claim(item="continue_education", kind="academic", months=12)])
    assert "扣除期限" in str(excinfo.value) and "6" in str(excinfo.value)


def test_continue_education_vocational_annual_lump():
    claim = evaluate(2024, D.Claim(item="continue_education", kind="vocational")).claims[0]
    assert claim.monthly_amount == Decimal("0.00")
    assert claim.annual_amount == Decimal("3600.00")
    assert claim.stage == D.STAGE_SETTLEMENT_ONLY


def test_continue_education_kind_required():
    reason = violation_reason(2024, D.Claim(item="continue_education"))
    assert "academic" in reason and "vocational" in reason


def test_serious_illness_threshold_cap_and_stage():
    r = evaluate(2024, D.Claim(item="serious_illness", self_paid_total=Decimal("30000.00")))
    claim = r.claims[0]
    assert claim.stage == D.STAGE_SETTLEMENT_ONLY
    assert claim.monthly_amount == Decimal("0.00")
    assert claim.annual_amount == Decimal("15000.00")
    assert r.settlement_only_annual_total == Decimal("15000.00")
    assert r.monthly_total == Decimal("0.00")


def test_serious_illness_annual_cap():
    r = evaluate(2024, D.Claim(item="serious_illness", self_paid_total=Decimal("95000.00")))
    assert r.claims[0].annual_amount == Decimal("80000.00")


def test_serious_illness_below_threshold_zero():
    claim = evaluate(2024, D.Claim(item="serious_illness", self_paid_total=Decimal("10000.00"))).claims[0]
    assert claim.annual_amount == Decimal("0.00")
    assert "未超起付线" in claim.note


def test_serious_illness_negative_self_paid_rejected():
    reason = violation_reason(2024, D.Claim(item="serious_illness", self_paid_total=Decimal("-1.00")))
    assert "不能为负" in reason


def test_housing_loan_standard():
    claim = evaluate(2024, D.Claim(item="housing_loan", months=12)).claims[0]
    assert claim.monthly_amount == Decimal("1000.00")
    assert claim.annual_amount == Decimal("12000.00")


def test_housing_rent_tier_standards():
    for tier, expected in ((0, "1500.00"), (1, "1100.00"), (2, "800.00")):
        claim = evaluate(2024, D.Claim(item="housing_rent", tier=tier)).claims[0]
        assert claim.monthly_amount == Decimal(expected), tier
        assert "城市" in claim.detail


def test_housing_rent_invalid_tier_rejected():
    assert "城市档" in violation_reason(2024, D.Claim(item="housing_rent", tier=3))
    assert "城市档" in violation_reason(2024, D.Claim(item="housing_rent", tier=-1))


def test_housing_loan_and_rent_mutually_exclusive():
    reason = violation_reason(
        2024, D.Claim(item="housing_loan"), D.Claim(item="housing_rent", tier=0))
    assert "不得同时申报" in reason and "第二十条" in reason


def test_support_elderly_only_child_standard_by_year():
    assert evaluate(2024, D.Claim(item="support_elderly", only_child=True)).claims[0].monthly_amount == Decimal("3000.00")
    assert evaluate(2019, D.Claim(item="support_elderly", only_child=True)).claims[0].monthly_amount == Decimal("2000.00")


def test_support_elderly_shared_within_per_child_cap():
    r = evaluate(2024, D.Claim(item="support_elderly", only_child=False,
                               monthly_amount=Decimal("1500.00")))
    assert r.claims[0].monthly_amount == Decimal("1500.00")
    assert r.claims[0].annual_amount == Decimal("18000.00")


def test_support_elderly_shared_exceeds_per_child_cap():
    reason = violation_reason(2024, D.Claim(item="support_elderly", only_child=False,
                                            monthly_amount=Decimal("1500.01")))
    assert "每人上限" in reason


def test_support_elderly_shared_total_cap_across_siblings():
    reason = violation_reason(
        2024, D.Claim(item="support_elderly", only_child=False,
                      monthly_amount=Decimal("1500.00"),
                      other_shared_amounts=(Decimal("1500.00"), Decimal("500.00"))))
    assert "合计" in reason and "额度" in reason


def test_support_elderly_only_child_flag_required():
    assert "独生子女" in violation_reason(2024, D.Claim(item="support_elderly"))


def test_support_elderly_only_child_rejects_sibling_amounts():
    reason = violation_reason(2024, D.Claim(item="support_elderly", only_child=True,
                                            other_shared_amounts=(Decimal("1000.00"),)))
    assert "共赡养人" in reason


def test_duplicate_claim_rejected():
    reason = violation_reason(2024, D.Claim(item="child_education"), D.Claim(item="child_education"))
    assert "重复申报" in reason


def test_same_continue_education_kind_twice_rejected_but_two_kinds_ok():
    reason = violation_reason(
        2024, D.Claim(item="continue_education", kind="academic"),
        D.Claim(item="continue_education", kind="academic"))
    assert "重复申报" in reason
    report = evaluate(2024, D.Claim(item="continue_education", kind="academic"),
                      D.Claim(item="continue_education", kind="vocational"))
    assert len(report.claims) == 2


def test_unknown_item_rejected():
    assert "未知扣除项目" in violation_reason(2024, D.Claim(item="pet_care"))


def test_report_aggregates_split_chains():
    r = evaluate(
        2024,
        D.Claim(item="child_education"),
        D.Claim(item="support_elderly", only_child=True),
        D.Claim(item="serious_illness", self_paid_total=Decimal("30000.00")),
    )
    assert r.monthly_total == Decimal("5000.00")
    assert r.settlement_only_annual_total == Decimal("15000.00")
    assert r.annual_total == Decimal("75000.00")
    assert len(r.claims) == 3


def test_claims_gate_pending_ruleset():
    raw = flip_one_node_pending(raw_copy(2024))
    rs = synthetic(raw, 2099)
    with pytest.raises(R.RulesetNotEffective):
        D.evaluate_claims(rs, [D.Claim(item="child_education")])


# ==========================================================================
# 七、年终奖：单独计税 / 择优 / 临界区间（来源 test_engine_bonus 15 条）
# ==========================================================================
def test_truth_case_bonus_36000_first_bracket():
    r = bonus_of("36000.00")
    assert r.quotient == Decimal("3000.00")
    assert r.bracket_index == 0 and r.rate == Decimal("0.03") and r.quick_deduction == Decimal(0)
    assert r.tax == Decimal("1080.00")
    assert r.after_tax == Decimal("34920.00")
    assert r.policy_valid and "2027" in r.policy_note


def test_truth_case_bonus_36001_trap_jump():
    r = bonus_of("36001.00")
    assert r.quotient == Decimal("3000.08")
    assert r.bracket_index == 1 and r.rate == Decimal("0.10") and r.quick_deduction == Decimal(210)
    assert r.tax == Decimal("3390.10")
    assert r.after_tax == Decimal("32610.90")
    assert r.tax - bonus_of("36000.00").tax == Decimal("2310.10")


def test_quotient_rounding_half_up_two_digits():
    r = bonus_of("36000.004")
    assert r.quotient == Decimal("3000.00")
    assert r.tax == (r.bonus_amount * Decimal("0.03")).quantize(Decimal("0.01"))


def test_policy_expiry_flag():
    raw = raw_copy(2024)
    rs = R.effective_ruleset(synthetic(raw, 2099))
    r = B.compute_bonus_separate_tax(rs, "36000.00")
    assert not r.policy_valid
    assert "到期" in r.policy_note


def test_nonpositive_bonus_rejected():
    with pytest.raises(ValueError):
        bonus_of("0.00")
    with pytest.raises(ValueError):
        bonus_of("-1.00")


def test_compare_separate_recommended_when_bracket_jump():
    salary = salary_settlement(2024, "96000.00")
    cmp = B.compare_bonus_schemes(eff(2024), "36000.00", salary)
    assert cmp.scheme_separate.annual_total_tax == Decimal("2160.00")
    assert cmp.scheme_combined.annual_total_tax == Decimal("4680.00")
    assert cmp.scheme_combined.taxable_income == Decimal("72000.00")
    assert cmp.tax_difference == Decimal("-2520.00")
    assert not cmp.tie
    assert cmp.recommended == B.SCHEME_SEPARATE
    assert cmp.scheme_separate.available


def test_compare_combined_recommended_when_salary_below_deduction():
    salary = salary_settlement(2024, "30000.00")
    cmp = B.compare_bonus_schemes(eff(2024), "36000.00", salary)
    assert cmp.scheme_separate.annual_total_tax == Decimal("1080.00")
    assert cmp.scheme_combined.annual_total_tax == Decimal("180.00")
    assert cmp.scheme_combined.taxable_income == Decimal("6000.00")
    assert cmp.tax_difference == Decimal("900.00")
    assert cmp.recommended == B.SCHEME_COMBINED


def test_compare_tie_within_penny():
    salary = salary_settlement(2024, "60000.00")
    cmp = B.compare_bonus_schemes(eff(2024), "36000.00", salary)
    assert cmp.scheme_separate.annual_total_tax == Decimal("1080.00")
    assert cmp.scheme_combined.annual_total_tax == Decimal("1080.00")
    assert cmp.tax_difference == Decimal("0.00")
    assert cmp.tie
    assert cmp.recommended == "tie"


def test_compare_policy_expired_forces_combined():
    rs = R.effective_ruleset(synthetic(raw_copy(2024), 2099))
    salary = salary_settlement(2024, "96000.00")
    cmp = B.compare_bonus_schemes(rs, "36000.00", salary)
    assert not cmp.scheme_separate.available
    assert "到期" in cmp.scheme_separate.note
    assert cmp.recommended == B.SCHEME_COMBINED


def test_compare_nonpositive_bonus_rejected():
    with pytest.raises(ValueError):
        B.compare_bonus_schemes(eff(2024), "0.00", salary_settlement())


def test_compare_and_trap_derive_gate_pending_ruleset():
    rs = synthetic(flip_one_node_pending(raw_copy(2024)), 2099)
    salary = salary_settlement()
    with pytest.raises(R.RulesetNotEffective):
        B.compare_bonus_schemes(rs, "36000.00", salary)
    with pytest.raises(R.RulesetNotEffective):
        B.derive_bonus_trap_intervals(rs)


def test_trap_intervals_all_boundaries_2024():
    intervals = B.derive_bonus_trap_intervals(eff(2024))
    assert len(intervals) == 6
    assert [iv.lower for iv in intervals] == [
        Decimal("36000"), Decimal("144000"), Decimal("300000"),
        Decimal("420000"), Decimal("660000"), Decimal("960000")]
    assert [Bmoney(iv.upper) for iv in intervals] == [
        Decimal("38566.67"), Decimal("160500.00"), Decimal("318333.33"),
        Decimal("447500.00"), Decimal("706538.46"), Decimal("1120000.00")]
    first = intervals[0]
    assert first.left_bracket_index == 0 and first.right_bracket_index == 1
    assert first.left_rate == Decimal("0.03") and first.right_rate == Decimal("0.10")
    assert first.upper > first.lower


def Bmoney(value):
    """年终奖端点按申报精度落地（与来源 money() 同口径）。"""
    return MONEY.money(value)


def test_trap_intervals_identical_across_all_years():
    base = B.derive_bonus_trap_intervals(eff(2019))
    for year in ALL_YEARS[1:]:
        assert B.derive_bonus_trap_intervals(eff(year)) == base


def test_find_trap_interval_open_interval_semantics():
    intervals = B.derive_bonus_trap_intervals(eff(2024))
    assert B.find_trap_interval(intervals, "36001.00") is intervals[0]
    assert B.find_trap_interval(intervals, "36000.00") is None
    assert B.find_trap_interval(intervals, intervals[0].upper) is None
    assert B.find_trap_interval(intervals, "50000.00") is None


def test_trap_interval_brute_force_recovery_point():
    rs = eff(2024)
    iv = B.derive_bonus_trap_intervals(rs)[0]
    step = Decimal("0.01")
    anchor = B.compute_bonus_separate_tax(rs, iv.lower).after_tax
    b = iv.lower + step
    while B.compute_bonus_separate_tax(rs, b).bracket_index != iv.right_bracket_index:
        b += step
    switch = b
    recovery = None
    b = switch
    while recovery is None:
        if B.compute_bonus_separate_tax(rs, b).after_tax >= anchor:
            recovery = b
        b += step
    assert recovery == Bmoney(iv.upper)
    b = switch
    while b < recovery:
        assert B.compute_bonus_separate_tax(rs, b).after_tax < anchor, b
        b += step
    b = iv.lower + step
    while b < switch:
        assert B.compute_bonus_separate_tax(rs, b).after_tax >= anchor, b
        b += step


# ==========================================================================
# 八、真值库与对账（来源 test_truth 5 + test_truth_reconciliation 6）
# ==========================================================================
def test_truth_file_exists_and_schema_version():
    raw = REG.truth()
    assert raw["schema_version"] == 1


def test_at_least_three_cases_with_unique_ids():
    cases = REG.truth()["cases"]
    assert len(cases) >= 3
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    for case_id in ids:
        assert case_id == case_id.strip() and case_id


def test_each_case_structure():
    valid = {"bonus_separate", "withholding_cumulative", "annual_settlement"}
    for case in REG.truth()["cases"]:
        assert case["category"] in valid, case["id"]
        assert 2019 <= case["year"] <= 2026, case["id"]
        assert isinstance(case["title"], str) and case["title"]
        assert isinstance(case["input"], dict) and case["input"], case["id"]
        assert isinstance(case["expected"], dict) and case["expected"], case["id"]
        source = case["source"]
        assert source["refs"] and source["urls"], case["id"]
        for url in source["urls"]:
            assert url.startswith("https://") or url.startswith("http://"), case["id"]
        assert isinstance(source["note"], str) and source["note"], case["id"]


def test_amounts_are_decimal_strings():
    def walk(node, where):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{where}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{where}[{i}]")
        else:
            assert isinstance(node, str), f"{where}: 期望值必须为 Decimal 字符串，得到 {node!r}"
            try:
                Decimal(node)
            except InvalidOperation:
                pytest.fail(f"{where}: 非法 Decimal 字面值 {node!r}")

    for case in REG.truth()["cases"]:
        walk(case["expected"], f"{case['id']}.expected")
        walk(case.get("also_expect", {}), f"{case['id']}.also_expect")


def test_bonus_boundary_trap_pair():
    cases = REG.truth_cases()
    assert "bonus-36000-2024" in cases and "bonus-36001-2024" in cases
    t0 = Decimal(cases["bonus-36000-2024"]["expected"]["tax"])
    t1 = Decimal(cases["bonus-36001-2024"]["expected"]["tax"])
    assert t1 > t0
    extra = Decimal(cases["bonus-36001-2024"]["also_expect"]["extra_tax_vs_bonus_36000"])
    assert extra == t1 - t0


def test_case_bonus_36000():
    case = REG.truth_cases()["bonus-36000-2024"]
    result = B.compute_bonus_separate_tax(eff(case["year"]), case["input"]["bonus_income"])
    check_case(case["id"], {
        "divisor_quotient": result.quotient, "rate": result.rate,
        "quick_deduction": result.quick_deduction, "tax": result.tax,
        "after_tax": result.after_tax,
    })


def test_case_bonus_36001_with_cross_case_extra_tax():
    case = REG.truth_cases()["bonus-36001-2024"]
    base = B.compute_bonus_separate_tax(eff(case["year"]), "36000.00").tax
    result = B.compute_bonus_separate_tax(eff(case["year"]), case["input"]["bonus_income"])
    check_case(case["id"], {
        "divisor_quotient": result.quotient, "rate": result.rate,
        "quick_deduction": result.quick_deduction, "tax": result.tax,
        "after_tax": result.after_tax,
        "extra_tax_vs_bonus_36000": result.tax - base,
    })


def test_case_withholding_three_months():
    case = REG.truth_cases()["withholding-3months-2019"]
    inp = case["input"]
    months = [M.MonthInput(
        gross=Decimal(inp["monthly_gross"]),
        special_deduction=Decimal(inp["monthly_social_insurance"]),
        special_additional_deduction=Decimal(inp["monthly_special_additional"]),
        other_deduction=Decimal(inp["monthly_other_deductions"]),
    )] * int(inp["months"])
    r = M.compute_monthly_withholding(eff(case["year"]), months)
    check_case(case["id"], {
        "cumulative_taxable": [m.cumulative_taxable for m in r.months],
        "cumulative_tax": [m.cumulative_tax for m in r.months],
        "monthly_tax": [m.withholding for m in r.months],
        "cumulative_standard_deduction": [m.cumulative_standard_deduction for m in r.months],
    })


def test_case_settlement_2024():
    case = REG.truth_cases()["settlement-2024"]
    inp = case["input"]
    total = sum((Decimal(v) for v in inp["special_additional_detail"].values()), Decimal(0))
    r = SE.compute_annual_settlement(eff(case["year"]), SE.SettlementInput(
        annual_gross=Decimal(inp["annual_gross"]),
        annual_special_deduction=Decimal(inp["annual_social_insurance"]),
        annual_special_additional_deduction=total,
        annual_other_deduction=Decimal(inp["annual_other_deductions"]),
    ))
    check_case(case["id"], {
        "comprehensive_taxable_income": r.cumulative_taxable_income,
        "annual_tax": r.annual_tax,
        "standard_deduction_total": r.annual_standard_deduction,
        "special_additional_total": total,
    })


def test_all_four_cases_covered():
    assert set(REG.truth_cases()) == {
        "bonus-36000-2024", "bonus-36001-2024",
        "withholding-3months-2019", "settlement-2024"}


def test_engines_reject_pending_ruleset():
    rs = synthetic(flip_one_node_pending(raw_copy(2026)), 2099)
    with pytest.raises(R.RulesetNotEffective):
        M.compute_monthly_withholding(rs, [M.MonthInput(gross=Decimal("1.00"))])
    with pytest.raises(R.RulesetNotEffective):
        SE.compute_annual_settlement(rs, SE.SettlementInput(annual_gross=Decimal("1.00")))
    with pytest.raises(R.RulesetNotEffective):
        B.compute_bonus_separate_tax(rs, "1.00")


def test_truth_expected_not_mutated_by_engine():
    before = json.dumps(REG.truth(), ensure_ascii=False, default=str)
    bonus_of("36001.00")
    settle(annual_gross=Decimal("200000.00"))
    assert json.dumps(REG.truth(), ensure_ascii=False, default=str) == before


# ==========================================================================
# 九、零政策数值字面量门禁（来源 test_zero_policy_literals 移植）
# ==========================================================================
SCAN_NAMES = ("__init__.py", "money.py", "monthly.py", "social.py",
              "settlement.py", "deductions.py", "bonus.py", "pipeline.py")


def _numeric_tokens(node):
    if isinstance(node, bool):
        return
    if isinstance(node, dict):
        for value in node.values():
            yield from _numeric_tokens(value)
    elif isinstance(node, list):
        for value in node:
            yield from _numeric_tokens(value)
    elif isinstance(node, (int, float, str, Decimal)):
        text = str(node)
        try:
            value = Decimal(text)
        except InvalidOperation:
            return
        if value == value.to_integral_value():
            if abs(value) >= 100:
                yield str(int(value))
        elif abs(value) >= 1:
            yield format(value.normalize(), "f")
        if isinstance(node, str) and abs(value) < 1:
            yield text.strip()


def collect_forbidden_tokens():
    tokens = set()
    for year in ALL_YEARS:
        with open(os.path.join(DATA_DIR, "ruleset-%d.json" % year), "r", encoding="utf-8") as handle:
            raw = json.load(handle, parse_float=Decimal)
        tokens.update(_numeric_tokens(raw))
    return tokens


def test_collect_numeric_tokens_non_empty():
    tokens = collect_forbidden_tokens()
    for must in ("5000", "36000", "2520", "15000", "80000"):
        assert must in tokens


def test_scan_files_exist():
    assert len(SCAN_NAMES) == 8
    for name in SCAN_NAMES:
        assert os.path.isfile(os.path.join(PACK_DIR, name)), name
    # 装配面（rules / registry）与来源口径一致，不在扫描范围：它们承载 schema/快照版本
    assert os.path.isfile(os.path.join(PACK_DIR, "rules.py"))
    assert os.path.isfile(os.path.join(PACK_DIR, "registry.py"))


def test_engine_sources_free_of_policy_literals():
    tokens = collect_forbidden_tokens()
    offenders = []
    for name in SCAN_NAMES:
        with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
            source = handle.read()
        for token in tokens:
            pattern = re.compile(r"(?<![0-9.])" + re.escape(token) + r"(?![0-9])")
            if pattern.search(source):
                offenders.append(f"{name}: {token}")
    assert not offenders, f"判定层源码出现政策数值字面量：{offenders}"


# ==========================================================================
# 十、全链路编排（来源 pipeline 语义，新增端到端断言）
# ==========================================================================
def test_pipeline_full_readme_values():
    year, request, provided = PACK_MOD.parse_subject(subject())
    result = P.compute_full_calc(REG.ruleset(year), request)
    assert provided == 12
    assert result.social_report.total == Decimal("2250.00")
    assert [c.monthly_amount for c in result.deductions_report.claims] == [
        Decimal("1000.00"), Decimal("1000.00"), Decimal("2000.00")]
    assert [m.withholding for m in result.monthly_report.months][:5] == [
        Decimal("262.50"), Decimal("262.50"), Decimal("262.50"),
        Decimal("262.50"), Decimal("805.00")]
    assert result.monthly_report.withheld_total == Decimal("7980.00")
    assert result.settlement_report.annual_tax == Decimal("7980.00")
    assert result.settlement_report.refund_or_owe == Decimal("0.00")
    assert result.bonus_report.tax == Decimal("3390.10")
    assert result.bonus_comparison.recommended == B.SCHEME_SEPARATE
    assert result.active_trap.lower == Decimal("36000")


def test_pipeline_requires_months():
    with pytest.raises(ValueError):
        P.compute_full_calc(eff(), P.CalcRequest())


def test_pipeline_settlement_only_not_in_withholding():
    req = P.CalcRequest(
        months=(M.MonthInput(gross=Decimal("10000.00")),),
        claims=(D.Claim(item="serious_illness", self_paid_total=Decimal("30000.00")),),
    )
    result = P.compute_full_calc(eff(), req)
    assert result.monthly_report.months[0].inp.special_additional_deduction == Decimal("0.00")
    assert result.settlement_report.cumulative_taxable_income == (
        Decimal("10000.00") - Decimal("60000.00") - Decimal("15000.00"))


def test_pipeline_claims_injected_into_months():
    req = P.CalcRequest(
        months=(M.MonthInput(gross=Decimal("10000.00")), M.MonthInput(gross=Decimal("10000.00"))),
        claims=(D.Claim(item="child_education", months=2),),
    )
    result = P.compute_full_calc(eff(2024), req)
    assert [m.inp.special_additional_deduction for m in result.monthly_report.months] == [
        Decimal("2000.00"), Decimal("2000.00")]
    assert "专项附加扣除申报计入" in result.monthly_report.months[0].note


def test_pipeline_claims_beyond_months_are_capped():
    req = P.CalcRequest(
        months=(M.MonthInput(gross=Decimal("10000.00")),),
        claims=(D.Claim(item="child_education", months=12),),
    )
    result = P.compute_full_calc(eff(2024), req)
    assert result.monthly_report.months[0].inp.special_additional_deduction == Decimal("2000.00")


def test_pipeline_settlement_override_wins():
    req = P.CalcRequest(
        months=(M.MonthInput(gross=Decimal("10000.00")),),
        settlement_overrides={"annual_gross": Decimal("1.00")},
    )
    result = P.compute_full_calc(eff(), req)
    assert result.settlement_report.cumulative_taxable_income == Decimal("1.00") - Decimal("60000.00")


def test_pipeline_bonus_report_none_without_bonus():
    result = P.compute_full_calc(eff(), P.CalcRequest(
        months=(M.MonthInput(gross=Decimal("10000.00")),)))
    assert result.bonus_report is None
    assert result.trap_intervals is None


def test_pipeline_negative_withheld_override_rejected():
    req = P.CalcRequest(months=(M.MonthInput(gross=Decimal("10000.00")),),
                        settlement_overrides={"withheld_total": Decimal("-1.00")})
    with pytest.raises(ValueError):
        P.compute_full_calc(eff(), req)


def test_pipeline_deduction_violation_is_atomic():
    req = P.CalcRequest(
        months=(M.MonthInput(gross=Decimal("10000.00")),),
        claims=(D.Claim(item="housing_loan"), D.Claim(item="housing_rent", tier=0)),
    )
    with pytest.raises(D.DeductionViolationError):
        P.compute_full_calc(eff(), req)


# ==========================================================================
# 十一、器官账本 / CLI / 判据 2 对撞面
# ==========================================================================
def test_evaluate_readme_example_no_blocking():
    fs = findings()
    rep = report()
    assert rep.exit_code() == EXIT_OK
    assert rep.summary()["blocking"] == 0
    assert len([f for f in fs if f.rule_id.startswith("tax.month:")]) == 12
    assert by_rule(fs, "tax.settlement")[0].evidence["annual_tax"] == "7980.00"
    assert by_rule(fs, "tax.bonus")[0].evidence["tax"] == "3390.10"


def test_evaluate_readme_example_values_match_source_cli():
    fs = findings()
    social = by_rule(fs, "tax.social")[0]
    assert social.evidence["total"] == "2250.00"
    assert [i["personal_amount"] for i in social.evidence["items"]] == [
        "800.00", "200.00", "50.00", "1200.00"]
    last = by_rule(fs, "tax.month:12")[0]
    assert last.evidence["withholding"] == "875.00"
    assert last.evidence["cumulative_tax"] == "7980.00"
    compare = by_rule(fs, "tax.bonus.compare")[0]
    assert compare.evidence["tax_difference"] == "-210.00"
    assert compare.evidence["recommended"] == "separate"


def test_claim_violation_is_input_error():
    with pytest.raises(D.DeductionViolationError) as excinfo:
        findings(subject(REJECT_SAMPLE))
    assert "不得同时申报" in str(excinfo.value)
    assert "第二十条" in str(excinfo.value)


def test_negative_bonus_is_input_error():
    sub = {"year": 2024, "uniform_month": {"gross": "10000.00"},
           "month_count": 12, "bonus_income": "0.00"}
    with pytest.raises(ValueError):
        findings(sub)


def test_unknown_year_is_input_error():
    sub = {"year": 1999, "uniform_month": {"gross": "10000.00"}, "month_count": 12}
    with pytest.raises(R.RulesetNotFoundError):
        findings(sub)


def test_unknown_top_field_is_input_error():
    sub = subject()
    sub["surprise"] = 1
    with pytest.raises(ValueError):
        findings(sub)


def test_bad_month_amount_is_input_error():
    sub = {"year": 2024, "uniform_month": {"gross": "abc"}, "month_count": 12}
    with pytest.raises(ValueError):
        findings(sub)


def test_both_month_forms_rejected():
    sub = {"year": 2024, "months": [{"gross": "1.00"}],
           "uniform_month": {"gross": "1.00"}, "month_count": 1}
    with pytest.raises(ValueError):
        findings(sub)


def test_missing_basis_version_is_contract_error():
    sub = subject()
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(sub, Basis.empty())


def test_missing_clause_raises_basis_missing():
    sub = subject()
    thin = Basis.from_dict({"version": REG.PARAMS_VERSION, "clauses": []})
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate(sub, thin)


def test_gate_pending_produces_fail_and_exit_one():
    raw = flip_one_node_pending(raw_copy(2024))
    raw["year"] = 2099
    sub = {"year": 2099, "uniform_month": {"gross": "10000.00"}, "month_count": 12}
    fs = PACK_MOD.evaluate_with_rulesets(sub, basis(), {2099: raw})
    assert any(f.verdict == FAIL for f in fs)
    assert by_rule(fs, "tax.result")[0].verdict == NOT_APPLICABLE
    rep = Report(product="clauseproof", organ=SLUG,
                 organ_version=PACK_MOD.VERSION, subject="pending.json", findings=fs)
    assert rep.exit_code() == EXIT_BLOCKED


def test_basis_missing_clause_degrades_for_not_applicable():
    # na 允许无锚点的产品契约在这个器官仍然不绕过门控：所有 pass 必须有锚点
    fs = findings()
    assert all(f.anchor is not None for f in fs if f.verdict == PASS)


def test_report_is_deterministic():
    a = report().as_dict()
    b = report().as_dict()
    assert a == b


def test_evidence_json_serializable():
    json.dumps(report().as_dict(), ensure_ascii=False)


def test_month_padding_finding_is_explicit():
    sub = {"year": 2024, "months": [{"gross": "12000.00"}], "bonus_income": "36000.00"}
    fs = findings(sub)
    pad = by_rule(fs, "tax.months.padded")[0]
    assert pad.verdict == NOT_APPLICABLE
    assert pad.evidence["provided"] == 1
    assert len([f for f in fs if f.rule_id.startswith("tax.month:")]) == 12


def test_trap_sample_policy_year_2026():
    fs = findings(subject(TRAP_SAMPLE))
    policy = by_rule(fs, "tax.bonus.policy")[0]
    assert policy.verdict == PASS
    assert "2027" in policy.message
    trap = by_rule(fs, "tax.bonus.trap")[0]
    assert trap.verdict == NOT_APPLICABLE
    assert trap.evidence["in_trap"] is True


def test_policy_expired_ledger_is_not_applicable():
    raw = raw_copy(2024)
    raw["year"] = 2099
    sub = {"year": 2099, "uniform_month": {"gross": "10000.00"},
           "month_count": 12, "bonus_income": "36000.00"}
    fs = PACK_MOD.evaluate_with_rulesets(sub, basis(), {2099: raw})
    assert by_rule(fs, "tax.bonus.policy")[0].verdict == NOT_APPLICABLE
    assert by_rule(fs, "tax.bonus.compare")[0].evidence["recommended"] == B.SCHEME_COMBINED


def test_cli_readme_example_rc_zero(capsys):
    rc = cp_cli.main(["check", SLUG, "--input", README_SAMPLE, "--basis", BASIS_PATH])
    assert rc == EXIT_OK
    out = capsys.readouterr().out
    assert "合计 22 条，阻断 0 条" in out
    assert "3390.10" in out
    assert "7980.00" in out


def test_cli_claims_reject_rc_two(capsys):
    rc = cp_cli.main(["check", SLUG, "--input", REJECT_SAMPLE, "--basis", BASIS_PATH])
    assert rc == EXIT_INPUT
    assert "不得同时申报" in capsys.readouterr().err


def test_cli_missing_basis_rc_three(capsys):
    rc = cp_cli.main(["check", SLUG, "--input", README_SAMPLE])
    assert rc == EXIT_CONTRACT
    assert "版本不符" in capsys.readouterr().err


def test_cli_json_output_has_basis_anchor(capsys):
    rc = cp_cli.main(["check", SLUG, "--input", TRAP_SAMPLE, "--basis", BASIS_PATH, "--json"])
    assert rc == EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert data["organ"] == SLUG
    assert all(record["basis_ref"]["clause_id"] for record in data["records"]
               if record["verdict"] != NOT_APPLICABLE)
