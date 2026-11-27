"""器官 ``ghg-ledger`` 无损判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在「判定结果」上。
来源仓判定层（D1 + D18 机械选 11 文件 / 实跑 151 passed / AST 函数 145）逐文件
处置见 ``docs/ghg-ledger.md`` §6；本文件承载三维坐标与 status 门控、混算拦截、
边界识别与双标尺差异、逐源核算与单位链、因子优先级、质量校核四类、配额试算
四方法学与账本映射。

本文件同时是**漂移门**：随包 manifest 登记的逐册 sha256 与文件实值一致。
"""

import ast
import copy
import importlib
import json
import os
import sys
from decimal import Decimal

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

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
from clauseproof import cli as cp_cli  # noqa: E402

PACK_MOD = importlib.import_module("clauseproof.packs.ghg-ledger")
ENGINE = importlib.import_module("clauseproof.packs.ghg-ledger.engine")
RULES = importlib.import_module("clauseproof.packs.ghg-ledger.rules")
CALC = importlib.import_module("clauseproof.packs.ghg-ledger.calc")
QUOTA = importlib.import_module("clauseproof.packs.ghg-ledger.quota")
REGISTRY = importlib.import_module("clauseproof.packs.ghg-ledger.registry")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "ghg-ledger")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "ghg-ledger")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
CALC_SAMPLE = os.path.join(SAMPLES, "profile-power-2024.json")
GATE_SAMPLE = os.path.join(SAMPLES, "profile-power-2026.json")
MIXED_SAMPLE = os.path.join(SAMPLES, "profile-mixed.json")


def basis():
    return Basis.from_json(BASIS_PATH)


def subject(path=CALC_SAMPLE):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def findings(sub=None):
    return tuple(PACK_MOD.evaluate(subject() if sub is None else sub, basis()))


def report(sub, name="case.json"):
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject=name, findings=findings(sub))


def index():
    return REGISTRY.index()


def units():
    return REGISTRY.unit_table()


def coord(key):
    standard, year, industry = key.split("/")
    return ENGINE.Coordinate(standard, year, industry)


def calc_payload(_key="gbt32150-2025/2024/power", **overrides):
    payload = {
        "coordinate": {"standard": "gbt32150-2025", "year": 2024, "industry": "power"},
        "facility": {"name": "示例电厂"},
        "sources": [
            {"source_id": "stationary_combustion",
             "activity": {"value": "1000", "unit": "t"}},
        ],
    }
    payload.update(overrides)
    return payload


def compute(payload=None, _key="gbt32150-2025/2024/power"):
    c = coord(_key)
    return CALC.compute(payload if payload is not None else calc_payload(), c,
                        index().effective_ruleset(c, scope=RULES.SCOPE_CALC), units())


# ==========================================================================
# 一、器官契约与装配
# ==========================================================================
def test_pack_is_registered_under_slug():
    pack = get(SLUG)
    assert isinstance(pack, Pack)
    assert pack.slug == SLUG
    assert pack.version == PACK_MOD.VERSION


def test_pack_version():
    assert PACK_MOD.VERSION == "0.1.0"


def test_pack_input_fields():
    assert PACK_MOD.INPUT_FIELDS == ("profile",)


def test_slug_in_builtin_modules_sorted():
    packs_ns = importlib.import_module("clauseproof.packs")
    assert SLUG in packs_ns.BUILTIN_MODULES
    assert list(packs_ns.BUILTIN_MODULES) == sorted(packs_ns.BUILTIN_MODULES)


def test_pack_appears_in_all_packs():
    assert SLUG in [pack.slug for pack in all_packs()]


def test_basis_has_ten_clauses():
    payload = json.load(open(BASIS_PATH, encoding="utf-8"))
    assert len(payload["clauses"]) == 10
    assert payload["version"] == REGISTRY.PARAMS_VERSION


def test_clauses_cover_every_spec():
    payload = json.load(open(BASIS_PATH, encoding="utf-8"))
    got = {c["clause_id"] for c in payload["clauses"]}
    assert got == {cid for cid, _p in REGISTRY.clause_specs()}


def test_missing_anchor_raises_basis_missing(tmp_path):
    path = tmp_path / "clauses.json"
    path.write_text(json.dumps({"version": REGISTRY.PARAMS_VERSION, "clauses": []}),
                    encoding="utf-8")
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate(subject(), Basis.from_json(str(path)))


def test_manifest_coordinate_count():
    assert len(index().coordinates()) == 40


def test_manifest_axes():
    assert set(index().standards) == {"gbt32150-2015", "gbt32150-2025"}
    assert set(index().industries) == {"power", "steel", "cement", "aluminum"}
    assert index().years == [2022, 2023, 2024, 2025, 2026]


def test_manifest_registered_sha256_matches_files():
    manifest = REGISTRY.manifest()
    for entry in manifest["coordinates"]:
        path = os.path.join(DATA_DIR, entry["file"])
        import hashlib
        with open(path, "rb") as handle:
            actual = hashlib.sha256(handle.read()).hexdigest()
        assert actual == entry["sha256"], entry["file"]


def test_pack_filenames_match_manifest():
    assert len(REGISTRY.pack_filenames()) == 40


# ==========================================================================
# 二、Decimal 口径与表达式树
# ==========================================================================
def test_as_decimal_rejects_float():
    with pytest.raises(ENGINE.CalcError):
        ENGINE.as_decimal(1.5)


def test_as_decimal_rejects_bool():
    with pytest.raises(ENGINE.CalcError):
        ENGINE.as_decimal(True)


def test_as_decimal_parses_strings_and_ints():
    assert ENGINE.as_decimal("1.50") == Decimal("1.50")
    assert ENGINE.as_decimal(3) == Decimal(3)


def test_quantize_half_up():
    assert ENGINE.quantize("2.5", 0) == Decimal("3")
    assert ENGINE.quantize("3.5", 0) == Decimal("4")


def test_to_text_strips_trailing_zeros():
    assert ENGINE.to_text(Decimal("352752.74600")) == "352752.746"
    assert ENGINE.to_text(Decimal("47033700")) == "47033700"


def test_scale_for():
    assert ENGINE.scale_for(3) == Decimal("0.001")


def test_expr_validate_rejects_inline_const_value():
    with pytest.raises(ENGINE.RulesetValidationError):
        ENGINE.validate({"op": "const", "value": "1.0"})


def test_expr_validate_rejects_unknown_op():
    with pytest.raises(ENGINE.RulesetValidationError):
        ENGINE.validate({"op": "pow", "args": []})


def test_expr_validate_rejects_binary_arity():
    with pytest.raises(ENGINE.RulesetValidationError):
        ENGINE.validate({"op": "div", "args": [{"op": "var", "ref": "a"}]})


def test_expr_validate_accepts_valid_tree():
    expr = {"op": "mul", "args": [
        {"op": "var", "ref": "activity_data"},
        {"op": "var", "ref": "emission_factor"},
        {"op": "var", "ref": "oxidation_rate"},
    ]}
    assert ENGINE.validate(expr) is True


def test_expr_evaluate_mul():
    expr = {"op": "mul", "args": [{"op": "var", "ref": "a"},
                                  {"op": "var", "ref": "b"}]}
    assert ENGINE.evaluate(expr, {"a": "6", "b": "7"}) == Decimal(42)


def test_expr_evaluate_div_by_zero_raises():
    expr = {"op": "div", "args": [{"op": "var", "ref": "a"},
                                  {"op": "var", "ref": "b"}]}
    with pytest.raises(ENGINE.CalcError):
        ENGINE.evaluate(expr, {"a": "1", "b": "0"})


def test_expr_evaluate_missing_ref_raises():
    with pytest.raises(ENGINE.CalcError):
        ENGINE.evaluate({"op": "var", "ref": "nope"}, {})


def test_expr_evaluate_null_ref_raises():
    with pytest.raises(ENGINE.CalcError):
        ENGINE.evaluate({"op": "var", "ref": "a"}, {"a": None})


def test_collect_refs_by_op_splits():
    expr = {"op": "mul", "args": [
        {"op": "var", "ref": "activity_data"},
        {"op": "const", "ref": "oxidation_rate"},
    ]}
    out = ENGINE.collect_refs_by_op(expr)
    assert out == {"var": ["activity_data"], "const": ["oxidation_rate"]}


def test_all_forty_packs_expressions_validate():
    """规则自洽扫描（来源 bench 规则自洽率 100%）：40 坐标包公式全部通过文法校验。"""
    for c in index().coordinates():
        pack = index().pack(c)
        ENGINE.validate(pack["engine"]["formula"]["expr"])


def test_all_forty_packs_coordinate_declared():
    for c in index().coordinates():
        pack = index().pack(c)
        declared = pack["coordinate"]
        assert (declared["standard"], declared["year"], declared["industry"]) == \
            (c.standard, c.year, c.industry)


def test_coordinate_key_and_equality():
    a = ENGINE.Coordinate("gbt32150-2025", 2024, "power")
    b = ENGINE.parse_coordinate("gbt32150-2025/2024/power") \
        if hasattr(ENGINE, "parse_coordinate") else a
    assert a.key == "gbt32150-2025/2024/power"
    assert a == ENGINE.Coordinate("gbt32150-2025", "2024", "power")


def test_coordinate_bad_year_raises():
    with pytest.raises(ENGINE.CoordinateError):
        ENGINE.Coordinate("gbt32150-2025", "not-a-year", "power")


def test_coordinate_empty_industry_raises():
    with pytest.raises(ENGINE.CoordinateError):
        ENGINE.Coordinate("gbt32150-2025", 2024, "")


def test_parse_coordinate_from_dict_and_string():
    assert RULES.parse_coordinate({"standard": "gbt32150-2025", "year": 2024,
                                   "industry": "power"}).key == \
        "gbt32150-2025/2024/power"
    assert RULES.parse_coordinate("gbt32150-2025/2024/power").key == \
        "gbt32150-2025/2024/power"


def test_parse_coordinate_unknown_rejected():
    with pytest.raises(ENGINE.CoordinateError):
        RULES.parse_coordinate("gbt32150-2025/1999/power", index=index())


# ==========================================================================
# 三、单位换算
# ==========================================================================
def test_units_known_and_dimension():
    table = units()
    assert table.known("t") and table.known("kWh")
    assert table.dimension_of("t") == "mass"
    assert table.dimension_of("kWh") == "electricity"


def test_units_convert_same_dimension():
    assert units().convert("1000", "kg", "t") == Decimal(1)


def test_units_convert_cross_dimension_rejected():
    with pytest.raises(ENGINE.UnitError):
        units().convert("1", "t", "MWh")


def test_units_unknown_rejected():
    with pytest.raises(ENGINE.UnitError):
        units().dimension_of("斤")


def test_units_base_factors_are_one():
    for dimension, spec in units().dimensions().items():
        assert units().scale(spec["base"]) == Decimal(1), dimension


def test_split_compound_unit():
    assert ENGINE.split_compound_unit("tCO2e_per_t") == ("tCO2e", "t")
    assert ENGINE.split_compound_unit("tCO2e") == ("tCO2e", None)


def test_unit_chain_records_activity_conversion():
    chain = CALC.UnitChain(units())
    value, base = chain.activity_to_base("1000000", "kg")
    assert base == "t" and value == Decimal(1000)
    assert chain.trace()[0]["target"] == "activity"


def test_unit_chain_factor_conversion_recorded():
    chain = CALC.UnitChain(units())
    value, emission_unit = chain.factor_to_base("3.02", "tCO2e_per_t", "t")
    assert emission_unit == "tCO2e"
    assert value == Decimal("3.02")


def test_unit_chain_emission_to_tco2e():
    chain = CALC.UnitChain(units())
    assert chain.emission_to_unit("1000", "kgCO2e") == Decimal(1)


def test_unit_table_rejects_double_dimension():
    bad = {"dimensions": {"a": {"base": "u1", "units": {
        "u1": 1, "u2": 100}}, "b": {"base": "u3", "units": {"u3": 1, "u2": 1}}}}
    with pytest.raises(ENGINE.UnitError):
        ENGINE.UnitTable(bad)


def test_unit_table_rejects_base_factor_not_one():
    bad = {"dimensions": {"a": {"base": "u1", "units": {"u1": 2}}}}
    with pytest.raises(ENGINE.UnitError):
        ENGINE.UnitTable(bad)


# ==========================================================================
# 四、status 门控（分作用域）
# ==========================================================================
def test_gate_entry_effective_rules():
    assert RULES._entry_is_effective({"status": "verified", "value": 1}) is True
    assert RULES._entry_is_effective({"status": "verified", "value": None}) is False
    assert RULES._entry_is_effective({"status": "pending", "value": None}) is False
    assert RULES._entry_is_effective({"status": "input_required"}) is True


def test_gate_report_calc_effective_for_2024_power():
    report = index().gate_report(coord("gbt32150-2025/2024/power"),
                                 scope=RULES.SCOPE_CALC)
    assert report["effective"] is True
    assert report["pending_count"] == 0


def test_gate_blocks_2026_power_oxidation():
    with pytest.raises(ENGINE.RulesetNotEffective) as exc_info:
        index().effective_ruleset(coord("gbt32150-2025/2026/power"),
                                  scope=RULES.SCOPE_CALC)
    assert "oxidation_rate" in str(exc_info.value)


def test_gate_report_lists_pending_entry():
    report = index().gate_report(coord("gbt32150-2025/2026/power"),
                                 scope=RULES.SCOPE_CALC)
    assert report["effective"] is False
    assert any("oxidation_rate" in p["entry"] for p in report["pending"])


def test_gate_scope_isolation_quota_vs_calc():
    """作用域隔离：quota 路径的 pending 不牵连 calc 路径（各查各的块）。"""
    c = coord("gbt32150-2025/2025/power")
    calc_gate = index().gate_report(c, scope=RULES.SCOPE_CALC)
    quota_gate = index().gate_report(c, scope=RULES.SCOPE_QUOTA)
    assert calc_gate["effective"] is True
    assert isinstance(quota_gate["effective"], bool)


def test_gate_unknown_coordinate_raises():
    with pytest.raises(ENGINE.CoordinateError):
        index().effective_ruleset(coord("gbt32150-2025/1999/power"))


def test_pack_schema_checked():
    manifest = REGISTRY.manifest()
    packs = REGISTRY.packs()
    for entry in manifest["coordinates"][:3]:
        key = "%s/%s/%s" % (entry["standard"], entry["year"], entry["industry"])
        assert packs[key]["schema"] == RULES.SCHEMA_RULESET


def test_scoped_entries_only_scope_blocks():
    pack = index().pack(coord("gbt32150-2025/2024/power"))
    calc_paths = {p.split(".")[0] for p, _n in RULES._scoped_entries(
        pack, RULES.SCOPE_CALC)}
    assert calc_paths <= set(RULES.SCOPE_BLOCKS[RULES.SCOPE_CALC])


# ==========================================================================
# 五、混算拦截与坐标解析
# ==========================================================================
def test_mixed_coordinates_rejected():
    with pytest.raises(ENGINE.MixedCoordinateError):
        RULES.detect_mixed_coordinates(subject(MIXED_SAMPLE)["profile"])


def test_single_coordinate_ok():
    coords = RULES.detect_mixed_coordinates(subject()["profile"])
    assert len(coords) == 1


def test_payload_without_coordinate_raises():
    with pytest.raises(ENGINE.CoordinateError):
        RULES.parse_payload_coordinate({"sources": []}, index=index())


def test_coordinate_string_detected_once():
    found = RULES.detect_mixed_coordinates({"note": "gbt32150-2025/2024/power"})
    assert len(found) == 1


# ==========================================================================
# 六、边界识别与双标尺差异
# ==========================================================================
def test_boundary_power_2024_sources():
    c = coord("gbt32150-2025/2024/power")
    report = RULES.identify_boundary(calc_payload(), c,
                                     index().pack(c))
    assert report["required_count"] == 1
    assert report["included"] == ["stationary_combustion"]
    assert "purchased_electricity" in report["excluded"]


def test_boundary_missing_required_source():
    payload = calc_payload()
    payload["sources"] = []
    c = coord("gbt32150-2025/2024/power")
    report = RULES.identify_boundary(payload, c, index().pack(c))
    assert report["missing_inputs"] == ["stationary_combustion"]


def test_boundary_unknown_source_rejected():
    payload = calc_payload()
    payload["sources"].append({"source_id": "mystery_source",
                               "activity": {"value": "1", "unit": "t"}})
    c = coord("gbt32150-2025/2024/power")
    with pytest.raises(ENGINE.BoundaryError):
        RULES.identify_boundary(payload, c, index().pack(c))


def test_boundary_duplicate_source_rejected():
    payload = calc_payload()
    payload["sources"].append({"source_id": "stationary_combustion",
                               "activity": {"value": "1", "unit": "t"}})
    c = coord("gbt32150-2025/2024/power")
    with pytest.raises(ENGINE.BoundaryError):
        RULES.identify_boundary(payload, c, index().pack(c))


def test_boundary_optional_source_included_only_with_input():
    c = coord("gbt32150-2025/2024/power")
    payload = calc_payload()
    payload["sources"].append({"source_id": "purchased_electricity",
                               "activity": {"value": "1000", "unit": "MWh"}})
    report = RULES.identify_boundary(payload, c, index().pack(c))
    assert "purchased_electricity" not in report["included"]  # required=False，缺 include_optional
    report2 = RULES.identify_boundary(payload, c, index().pack(c),
                                      include_optional=True)
    assert "purchased_electricity" in report2["included"]


def test_boundary_diff_gbt2015_to_2025_power():
    old = coord("gbt32150-2015/2024/power")
    new = coord("gbt32150-2025/2024/power")
    diff = RULES.diff_boundary(old, new, index())
    assert diff["added"] == []
    assert diff["removed"] == []
    assert diff["adjusted_count"] == 3
    assert diff["unchanged_count"] == 1


def test_boundary_diff_same_standard_rejected():
    with pytest.raises(ENGINE.CoordinateError):
        RULES.diff_boundary(coord("gbt32150-2025/2024/power"),
                            coord("gbt32150-2025/2025/power"), index())


def test_boundary_diff_fresh_computation():
    """双标尺差异现算现出（同输入两次一致，不落盘）。"""
    old = coord("gbt32150-2015/2024/power")
    new = coord("gbt32150-2025/2024/power")
    a = RULES.diff_boundary(old, new, index())
    b = RULES.diff_boundary(old, new, index())
    assert a == b


# ==========================================================================
# 七、逐源核算与因子优先级
# ==========================================================================
def test_compute_power_2024_matches_truth():
    """真值对账：活动数据 117977 t × 因子 3.020215 × 氧化率 0.99 = 352752.746。"""
    result = compute(subject(CALC_SAMPLE)["profile"])
    assert result["total"] == "352752.746"
    line = result["lines"][0]
    assert line["factor"]["value"] == "3.020215"
    assert line["oxidation_rate"] == "0.99"
    assert line["emission"] == "352752.746"


def test_compute_has_unit_chain():
    result = compute()
    assert result["lines"][0]["unit_chain"] is not None


def test_compute_factor_priority_measured_wins():
    payload = calc_payload()
    payload["sources"][0]["factor"] = {"value": "3.1", "unit": "tCO2e_per_t",
                                       "source": "measured"}
    result = compute(payload)
    assert result["lines"][0]["factor"]["source"] == "measured"
    assert result["lines"][0]["factor"]["value"] == "3.1"


def test_compute_illegal_declared_source_rejected():
    payload = calc_payload()
    payload["sources"][0]["factor"] = {"value": "3.1", "unit": "tCO2e_per_t",
                                       "source": "guess"}
    with pytest.raises(ENGINE.FactorUnavailable):
        compute(payload)


def test_compute_self_declared_industry_default_must_match_ruleset():
    payload = calc_payload()
    payload["sources"][0]["factor"] = {"value": "9.9", "unit": "tCO2e_per_t",
                                       "source": "industry_default"}
    with pytest.raises(ENGINE.FactorUnavailable):
        compute(payload)


def test_compute_missing_required_source_raises():
    payload = calc_payload()
    payload["sources"] = []
    with pytest.raises(ENGINE.BoundaryError):
        compute(payload)


def test_compute_no_factor_three_layers_unavailable():
    """空规则包（缺 factors 块）→ FactorUnavailable（不得静默取 0/1）。"""
    c = coord("gbt32150-2025/2024/power")
    pack = copy.deepcopy(index().pack(c))
    pack["factors"] = {}
    with pytest.raises(ENGINE.FactorUnavailable):
        CALC.compute(calc_payload(), c, pack, units())


def test_compute_activity_kg_converts_to_t():
    payload = calc_payload()
    payload["sources"][0]["activity"] = {"value": "1000000", "unit": "kg"}
    result = compute(payload)
    assert result["lines"][0]["activity_base"]["unit"] == "t"
    assert result["lines"][0]["activity_base"]["value"] == "1000"


def test_compute_emission_text_three_places():
    result = compute()
    assert len(result["total"].split(".")[-1]) <= 3


def test_compute_non_combustion_source_oxidation_one():
    """非燃烧类源（工艺排放）：氧化率恒等 1（系数只对燃烧类适用）。"""
    c = coord("gbt32150-2025/2024/steel")
    profile = _steel_profile()
    result = CALC.compute(profile, c,
                          index().effective_ruleset(c, scope=RULES.SCOPE_CALC), units())
    by_id = {line["source_id"]: line for line in result["lines"]}
    assert by_id["stationary_combustion"]["oxidation_rate"] == "0.99"
    assert by_id["process_emission"]["oxidation_rate"] == "1"


def test_compute_deterministic():
    a = compute()
    b = compute()
    assert a == b


# ==========================================================================
# 八、数据质量校核（四类）
# ==========================================================================
def _steel_profile():
    """来源真值库 steel-2024 档案（只读转写样例；燃烧 + 工艺 + 碳产品三源）。"""
    return copy.deepcopy(subject(os.path.join(SAMPLES, "profile-steel-2024.json"))["profile"])


def _steel_baseline():
    return copy.deepcopy(subject(os.path.join(SAMPLES, "profile-steel-2023.json"))["profile"])


def _checks(profile, baseline=None):
    c = coord("gbt32150-2025/2024/steel")
    calc = CALC.compute(profile, c,
                        index().effective_ruleset(c, scope=RULES.SCOPE_CALC), units())
    pack = index().effective_ruleset(c, scope=RULES.SCOPE_CHECK)
    baseline_calc = None
    if baseline is not None:
        baseline_calc = CALC.compute(
            baseline, c, index().effective_ruleset(c, scope=RULES.SCOPE_CALC), units())
    return CALC.run_checks(profile, calc, c, pack, units=units(),
                           baseline=baseline_calc)


def test_quality_clean_profile_zero_issues():
    report = _checks(_steel_profile())
    assert report["issue_count"] == 0


def test_quality_unit_unknown_flagged():
    profile = _steel_profile()
    profile["sources"].append({"source_id": "purchased_electricity",
                               "activity": {"value": "100", "unit": "斤"}})
    report = _checks(profile)
    assert any(i["type"] == CALC.TYPE_UNIT and i["level"] == CALC.LEVEL_ERROR
               for i in report["issues"])


def test_quality_magnitude_single_source_skipped():
    """单源档案占比恒为 1，无筛查信息量 → 不报量级异常。"""
    report = _checks(_steel_profile())
    assert all(i["type"] != CALC.TYPE_MAGNITUDE for i in report["issues"])


def test_quality_yoy_skipped_without_baseline():
    report = _checks(_steel_profile())
    assert any(s["type"] == CALC.TYPE_YOY for s in report["rules_skipped"])


def test_quality_yoy_flagged_with_baseline():
    baseline = _steel_profile()
    for item in baseline["sources"]:
        if item["source_id"] == "stationary_combustion":
            item["activity"]["value"] = "13936"  # 1/10 → 变化率 90% 远超阈值
    report = _checks(_steel_profile(), baseline=baseline)
    assert any(i["type"] == CALC.TYPE_YOY for i in report["issues"])


def test_quality_intensity_out_of_range_flagged():
    profile = _steel_profile()
    profile["output"]["value"] = "1"
    report = _checks(profile)
    assert any(i["type"] == CALC.TYPE_INTENSITY for i in report["issues"])


def test_quality_intensity_no_output_skipped():
    profile = _steel_profile()
    del profile["output"]
    report = _checks(profile)
    assert any(s["type"] == CALC.TYPE_INTENSITY for s in report["rules_skipped"])


def test_quality_issue_ordering_by_level():
    profile = _steel_profile()
    profile["output"]["value"] = "1"  # info 级比强度
    profile["sources"].append({"source_id": "purchased_electricity",
                               "activity": {"value": "100", "unit": "斤"}})  # error 级
    report = _checks(profile)
    levels = [i["level"] for i in report["issues"]]
    order = {CALC.LEVEL_ERROR: 0, CALC.LEVEL_WARNING: 1, CALC.LEVEL_INFO: 2}
    assert levels == sorted(levels, key=lambda l: order.get(l, 9))


def test_quality_counts_match_issues():
    profile = _steel_profile()
    profile["output"]["value"] = "1"
    report = _checks(profile)
    assert sum(report["counts"].values()) == report["issue_count"]


def test_quality_requires_calc_result():
    with pytest.raises(ENGINE.QualityError):
        CALC.run_checks(_steel_profile(), None,
                        coord("gbt32150-2025/2024/steel"),
                        index().pack(coord("gbt32150-2025/2024/steel")))


# ==========================================================================
# 九、配额试算（四方法学）
# ==========================================================================
def _quota_pack(key="gbt32150-2025/2025/power", scope=RULES.SCOPE_QUOTA):
    c = coord(key)
    return c, index().effective_ruleset(c, scope=scope)


def test_quota_benchmark_method_truth():
    """真值对账（power-2025）：产量 395794 × 基准值（规则包 verified）× 0.97 = 303373.726。"""
    c, pack = _quota_pack()
    profile = subject(os.path.join(SAMPLES, "profile-power-2025.json"))["profile"]
    actual = CALC.compute(profile, c,
                          index().effective_ruleset(c, scope=RULES.SCOPE_CALC),
                          units())["total_raw"]
    report = QUOTA.compute_quota(pack, c, actual,
                                 params={"output": profile["output"]["value"],
                                         "correction_factor": "0.97"})
    assert report["method"] == QUOTA.METHOD_BENCHMARK
    assert report["allocated"] == "303373.726"
    assert report["gap"] == "6528.241"
    assert report["status"] == QUOTA.STATUS_OK


def test_quota_benchmark_requires_output():
    c, pack = _quota_pack()
    with pytest.raises(ENGINE.QuotaUnavailable):
        QUOTA.compute_quota(pack, c, "1", params={"correction_factor": "1"})


def test_quota_benchmark_input_required_not_silent_zero():
    """benchmark_value 为 input_required 且未提供 → 显式报错（不得静默取 0）。"""
    c = coord("gbt32150-2025/2024/power")
    pack = index().effective_ruleset(c, scope=RULES.SCOPE_QUOTA)
    with pytest.raises(ENGINE.QuotaUnavailable):
        QUOTA.compute_quota(pack, c, "352752.746", params={"output": "1000"})


def test_quota_benchmark_with_supplied_benchmark():
    c = coord("gbt32150-2025/2024/power")
    pack = index().effective_ruleset(c, scope=RULES.SCOPE_QUOTA)
    report = QUOTA.compute_quota(pack, c, "352752.746",
                                 params={"output": "100",
                                         "benchmark_value": "100",
                                         "correction_factor": "1"})
    assert report["allocated"] == "10000"


def test_quota_method_none_is_not_applicable():
    c = coord("gbt32150-2025/2025/power")
    pack = copy.deepcopy(index().pack(c))
    pack["quota"]["method"] = QUOTA.METHOD_NONE
    report = QUOTA.compute_quota(pack, c, "100")
    assert report["status"] == QUOTA.STATUS_NOT_APPLICABLE
    assert report["allocated"] is None
    assert report["gap"] is None


def test_quota_intensity_coefficient_derived_alpha():
    """真值对账（steel-2024，BP=2.1 外部提供）：α 由偏离度推出，A = E×(1+α)。"""
    c = coord("gbt32150-2025/2024/steel")
    pack = index().effective_ruleset(c, scope=RULES.SCOPE_QUOTA)
    profile = _steel_profile()
    actual = CALC.compute(profile, c,
                          index().effective_ruleset(c, scope=RULES.SCOPE_CALC),
                          units())["total_raw"]
    report = QUOTA.compute_quota(pack, c, actual,
                                 params={"benchmark_value": "2.1",
                                         "output": profile["output"]["value"]})
    assert report["method"] == QUOTA.METHOD_INTENSITY_COEFFICIENT
    assert report["parameters"]["correction_factor"]["source"] == "derived"
    assert report["allocated_raw"] == "334672.8904362887160894180968"


def test_quota_intensity_explicit_alpha_skips_derivation():
    c = coord("gbt32150-2025/2024/steel")
    pack = index().effective_ruleset(c, scope=RULES.SCOPE_QUOTA)
    report = QUOTA.compute_quota(pack, c, "100",
                                 params={"correction_factor": "0.05"})
    assert report["allocated"] == "105"
    assert report["parameters"]["correction_factor"]["source"] == "caller"


def test_quota_alpha_cap_clamped():
    """偏离度越上限 → +封顶；越下限 → −封顶（分段常数为规则包值）。"""
    pack = index().pack(coord("gbt32150-2025/2024/steel"))
    derivation = pack["quota"]["derivation"]
    band = ENGINE.as_decimal(derivation["band"]["value"])
    cap = ENGINE.as_decimal(derivation["cap"]["value"])
    high, _x = QUOTA._derive_alpha(pack, ENGINE.as_decimal("100"),
                                   ENGINE.as_decimal("1"))
    assert high == cap
    low, _x = QUOTA._derive_alpha(pack, ENGINE.as_decimal("100"),
                                  ENGINE.as_decimal("1000"))
    assert low == -cap
    assert band > 0


def test_quota_historical_intensity():
    c = coord("gbt32150-2025/2024/steel")
    pack = copy.deepcopy(index().pack(c))
    pack["quota"]["method"] = QUOTA.METHOD_HISTORICAL_INTENSITY
    pack["quota"]["allowed_methods"] = list(pack["quota"].get("allowed_methods") or [])
    if QUOTA.METHOD_HISTORICAL_INTENSITY not in pack["quota"]["allowed_methods"]:
        pack["quota"]["allowed_methods"].append(QUOTA.METHOD_HISTORICAL_INTENSITY)
    report = QUOTA.compute_quota(pack, c, "100",
                                 params={"output": "50",
                                         "historical_intensity": "3"})
    assert report["allocated"] == "150"
    assert report["gap"] == "50"


def test_quota_historical_requires_intensity():
    c = coord("gbt32150-2025/2024/steel")
    pack = copy.deepcopy(index().pack(c))
    pack["quota"]["method"] = QUOTA.METHOD_HISTORICAL_INTENSITY
    pack["quota"]["allowed_methods"] = [QUOTA.METHOD_HISTORICAL_INTENSITY]
    with pytest.raises(ENGINE.QuotaUnavailable):
        QUOTA.compute_quota(pack, c, "100", params={"output": "50"})


def test_quota_method_not_allowed_rejected():
    c = coord("gbt32150-2025/2024/steel")
    pack = index().pack(c)
    with pytest.raises(ENGINE.InputError):
        QUOTA.compute_quota(pack, c, "100", params={"method": "made_up"})


def test_quota_disclaimer_forced():
    c, pack = _quota_pack()
    report = QUOTA.compute_quota(pack, c, "1", params={"output": "1",
                                                       "correction_factor": "1"})
    assert report["disclaimer_required"] is True
    assert report["disclaimer"]


def test_quota_scalar_rejects_bool_and_garbage():
    with pytest.raises(ENGINE.QuotaUnavailable):
        QUOTA._scalar(True, "x")
    with pytest.raises(ENGINE.QuotaUnavailable):
        QUOTA._scalar("abc", "x")


def test_quota_inputs_from_profile_prefers_top_output():
    profile = {"output": {"value": "10", "unit": "t"},
               "quota_inputs": {"historical_intensity": "2"}}
    inputs = QUOTA.quota_inputs_from_profile(profile)
    assert inputs["output"] == Decimal(10)
    assert inputs["historical_intensity"] == Decimal(2)


def test_quota_gap_ratio_zero_actual():
    c, pack = _quota_pack()
    report = QUOTA.compute_quota(pack, c, "0", params={"output": "1",
                                                       "correction_factor": "1"})
    assert report["gap_ratio"] is None


# ==========================================================================
# 十、账本映射与退出码契约
# ==========================================================================
def test_calc_sample_exit_ok():
    """判据 2：旧 `ghg calc` rc 0 / 新 check rc 0（同 total 352752.746）。"""
    assert report(subject(CALC_SAMPLE), "profile-power-2024.json").exit_code() == EXIT_OK


def test_gate_blocked_profile_exit_blocked():
    """判据 2：旧 `ghg calc`（2026 发电缺氧化率）rc 1 / 新 rc 1（门控 fail）。"""
    assert report(subject(GATE_SAMPLE), "profile-power-2026.json").exit_code() == EXIT_BLOCKED


def test_gate_finding_lists_pending_entry():
    found = findings(subject(GATE_SAMPLE))
    gate = [f for f in found if f.rule_id.startswith("ghg.gate:")]
    assert gate
    assert gate[0].evidence["scope"] == "calc"
    assert any("oxidation_rate" in p["entry"] for p in gate[0].evidence["pending"])


def test_mixed_coordinates_raise_input_error():
    """判据 2：旧 `ghg calc` mixed rc 2 / 新抛（CLI rc 2）。"""
    with pytest.raises(ENGINE.MixedCoordinateError):
        findings(subject(MIXED_SAMPLE))


def test_included_source_pass_record():
    found = findings(subject(CALC_SAMPLE))
    hits = [f for f in found if f.rule_id == "ghg.source:stationary_combustion"]
    assert hits and hits[0].verdict == PASS


def test_excluded_sources_na_records():
    found = findings(subject(CALC_SAMPLE))
    na = [f for f in found if f.rule_id.startswith("ghg.source:")]
    assert len([f for f in na if f.verdict == NOT_APPLICABLE]) == 3


def test_calc_line_record_carries_provenance():
    found = findings(subject(CALC_SAMPLE))
    line = [f for f in found if f.rule_id == "ghg.line:stationary_combustion"][0]
    assert line.verdict == PASS
    assert line.evidence["provenance"]["coordinate"] == "gbt32150-2025/2024/power"
    assert line.evidence["emission"] == "352752.746"


def test_boundary_diff_record():
    found = findings(subject(CALC_SAMPLE))
    diff = [f for f in found if f.rule_id == "ghg.boundary_diff"]
    assert len(diff) == 1
    assert diff[0].evidence["added"] == []
    assert len(diff[0].evidence["adjusted"]) >= 1


def test_result_summary_record():
    found = findings(subject(CALC_SAMPLE))
    summary = [f for f in found if f.rule_id == "ghg.result"]
    assert len(summary) == 1
    assert summary[0].evidence["coordinate"] == "gbt32150-2025/2024/power"
    assert summary[0].evidence["total"] == "352752.746"


def test_all_findings_carry_anchors():
    found = findings(subject(CALC_SAMPLE))
    for finding in found:
        assert finding.anchor is not None


def test_findings_ids_unique():
    found = findings(subject(CALC_SAMPLE))
    ids = [f.id for f in found]
    assert len(ids) == len(set(ids))


def test_scopes_check_only():
    sub = subject(CALC_SAMPLE)
    sub["scopes"] = ["check"]
    found = tuple(PACK_MOD.evaluate(sub, basis()))
    assert any(f.rule_id.startswith("ghg.quality_skipped:") for f in found)
    assert not any(f.rule_id.startswith("ghg.line:") for f in found)


def test_scopes_quota_only_raises_input():
    sub = subject(CALC_SAMPLE)
    sub["scopes"] = ["quota"]
    with pytest.raises(ENGINE.QuotaUnavailable):
        PACK_MOD.evaluate(sub, basis())


def test_scope_unknown_rejected():
    sub = subject(CALC_SAMPLE)
    sub["scopes"] = ["report"]
    with pytest.raises(ENGINE.GhgError):
        PACK_MOD.evaluate(sub, basis())


def test_quality_error_becomes_fail_record():
    profile = json.load(open(CALC_SAMPLE, encoding="utf-8"))["profile"]
    profile = copy.deepcopy(profile)
    profile["sources"].append({"source_id": "purchased_electricity",
                               "activity": {"value": "100", "unit": "斤"}})
    sub = {"profile": profile, "scopes": ["check"]}
    found = tuple(PACK_MOD.evaluate(sub, basis()))
    fails = [f for f in found if f.rule_id.startswith("ghg.quality:")]
    assert fails and all(f.verdict == FAIL for f in fails)


def test_validate_subject_rejects_missing_profile():
    with pytest.raises(ENGINE.GhgError):
        PACK_MOD.validate_subject({"baseline": {}})


def test_validate_subject_rejects_bad_sources():
    with pytest.raises(ENGINE.GhgError):
        PACK_MOD.validate_subject({"profile": {"sources": [{"activity": {}}]}})


def test_cli_missing_basis_returns_contract_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input", CALC_SAMPLE])
    assert code == EXIT_CONTRACT
    assert "ContractError" in capsys.readouterr().err


def test_cli_wrong_basis_version_returns_contract_code(tmp_path, capsys):
    path = tmp_path / "clauses.json"
    path.write_text(json.dumps({"version": "1999-01-01", "clauses": []}),
                    encoding="utf-8")
    code = cp_cli.main(["check", SLUG, "--input", CALC_SAMPLE,
                        "--basis", str(path)])
    assert code == EXIT_CONTRACT


def test_cli_missing_file_returns_input_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input", "no-such-file.json",
                        "--basis", BASIS_PATH])
    assert code == EXIT_INPUT


def test_cli_mixed_coordinates_returns_input_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input", MIXED_SAMPLE,
                        "--basis", BASIS_PATH])
    assert code == EXIT_INPUT


def test_cli_clean_calc_json_flag(capsys):
    code = cp_cli.main(["check", SLUG, "--input", CALC_SAMPLE,
                        "--basis", BASIS_PATH, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert payload["organ"] == SLUG
    assert payload["summary"]["blocking"] == 0


def test_json_output_deterministic():
    import io
    from contextlib import redirect_stdout

    buffer1, buffer2 = io.StringIO(), io.StringIO()
    argv = ["check", SLUG, "--input", CALC_SAMPLE, "--basis", BASIS_PATH, "--json"]
    with redirect_stdout(buffer1):
        cp_cli.main(argv)
    with redirect_stdout(buffer2):
        cp_cli.main(argv)
    assert buffer1.getvalue() == buffer2.getvalue()


def test_rule_codes_are_machine_readable():
    found = findings(subject(CALC_SAMPLE))
    prefixes = ("ghg.gate:", "ghg.source:", "ghg.line:", "ghg.boundary_diff",
                "ghg.quality", "ghg.quota", "ghg.result")
    for finding in found:
        assert finding.rule_id.startswith(prefixes), finding.rule_id


def test_engine_modules_have_no_io_or_clock():
    banned = ("os.environ", "datetime.now", "time.time", "date.today", "utcnow",
              "input(", "print(", "open(")
    for name in ("engine.py", "rules.py", "calc.py", "quota.py"):
        with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for token in banned:
                    assert token not in node.value, (name, token)


def test_engine_modules_import_graph():
    allowed = {"decimal", "typing"}
    for name in ("engine.py", "rules.py", "calc.py", "quota.py"):
        with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in allowed, (name, alias.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert (node.module or "").split(".")[0] in allowed, (name, node.module)


def test_no_policy_numbers_in_engine_sources():
    """零政策数值字面量：引擎源码不得出现规则包政策数值（抽查真值 token）。"""
    forbidden = {"352752.74600445000", "3.020215", "8400", "0.99"}
    for name in ("engine.py", "rules.py", "calc.py", "quota.py"):
        with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in forbidden, (name, node.value)


def test_manifest_bench_targets_present():
    targets = index().bench_targets()
    assert targets
    assert all(isinstance(v, (int, float, Decimal)) for v in targets.values())


def test_collect_numeric_tokens_non_empty():
    tokens = RULES.collect_numeric_tokens(index())
    assert tokens
    assert all(isinstance(t, str) and t for t in tokens)


# ==========================================================================
# 十一、真值库逐用例对账（来源 data/truth/expected.json 12 用例）
# ==========================================================================
def test_truth_calc_effective_is_38_of_40():
    """核算路径 38/40 坐标可通过（2026 发电碳氧化率待官方因子库 —— 诚实留白）。"""
    ok = [c.key for c in index().coordinates()
          if index().gate_report(c, scope=RULES.SCOPE_CALC)["effective"]]
    blocked = sorted(set(c.key for c in index().coordinates()) - set(ok))
    assert len(ok) == 38
    assert blocked == ["gbt32150-2015/2026/power", "gbt32150-2025/2026/power"]


def test_truth_quota_and_check_paths_40_of_40():
    quota_ok = sum(1 for c in index().coordinates()
                   if index().gate_report(c, scope=RULES.SCOPE_QUOTA)["effective"])
    check_ok = sum(1 for c in index().coordinates()
                   if index().gate_report(c, scope=RULES.SCOPE_CHECK)["effective"])
    assert quota_ok == 40
    assert check_ok == 40


def test_truth_missing_required_source_case():
    """truth: missing_required_source → 缺应核算源活动数据（退出码 2）。"""
    profile = _steel_profile()
    profile["sources"] = [s for s in profile["sources"]
                          if s["source_id"] != "process_emission"]
    c = coord("gbt32150-2025/2024/steel")
    with pytest.raises(ENGINE.BoundaryError) as exc_info:
        CALC.compute(profile, c, index().effective_ruleset(c, scope=RULES.SCOPE_CALC),
                     units())
    assert "process_emission" in str(exc_info.value)


def test_truth_bad_format_null_activity_case():
    """truth: bad_format_missing_activity_value → activity.value 为 null 按缺输入处理。"""
    profile = _steel_profile()
    for item in profile["sources"]:
        if item["source_id"] == "stationary_combustion":
            item["activity"]["value"] = None
    c = coord("gbt32150-2025/2024/steel")
    with pytest.raises(ENGINE.BoundaryError):
        CALC.compute(profile, c, index().effective_ruleset(c, scope=RULES.SCOPE_CALC),
                     units())


def test_truth_quality_magnitude_outlier_warning_level():
    """truth: magnitude_outlier（燃烧源放大 200 倍）→ Q-MAG-01 warning 级。"""
    profile = _steel_profile()
    for item in profile["sources"]:
        if item["source_id"] == "stationary_combustion":
            item["activity"]["value"] = str(int(item["activity"]["value"]) * 200)
    report = _checks(profile)
    hits = [i for i in report["issues"] if i["type"] == CALC.TYPE_MAGNITUDE]
    assert hits
    assert hits[0]["rule_id"] == "Q-MAG-01"
    assert hits[0]["level"] == CALC.LEVEL_WARNING


def test_truth_quality_intensity_info_level():
    """truth: intensity_out_of_range（产量压到 1/10）→ Q-INT-01 info 级。"""
    profile = _steel_profile()
    profile["output"]["value"] = str(int(profile["output"]["value"]) // 10)
    report = _checks(profile)
    hits = [i for i in report["issues"] if i["type"] == CALC.TYPE_INTENSITY]
    assert hits
    assert hits[0]["rule_id"] == "Q-INT-01"
    assert hits[0]["level"] == CALC.LEVEL_INFO


def test_truth_quality_bad_unit_error_level():
    """truth: quality_bad_unit（未纳入核算的选填源录入未知单位）→ Q-UNIT-01 error 级。"""
    profile = _steel_profile()
    profile["sources"].append({"source_id": "purchased_electricity",
                               "activity": {"value": "100", "unit": "斤"}})
    report = _checks(profile)
    hits = [i for i in report["issues"] if i["type"] == CALC.TYPE_UNIT]
    assert hits
    assert hits[0]["rule_id"] == "Q-UNIT-01"
    assert hits[0]["level"] == CALC.LEVEL_ERROR


def test_truth_yoy_real_baseline_flagged():
    """truth: steel-2024 vs steel-2023 基线 → 燃烧源活动数据近翻倍，yoy 命中。"""
    report = _checks(_steel_profile(), baseline=_steel_baseline())
    assert any(i["type"] == CALC.TYPE_YOY for i in report["issues"])


def test_truth_yoy_clean_when_baseline_identical():
    """truth 干净对照口径：上年度与本年活动数据同量级 → yoy 零命中。"""
    report = _checks(_steel_profile(), baseline=_steel_profile())
    assert all(i["type"] != CALC.TYPE_YOY for i in report["issues"])


def test_truth_quota_benchmark_gap_ratio():
    c, pack = _quota_pack()
    profile = subject(os.path.join(SAMPLES, "profile-power-2025.json"))["profile"]
    actual = CALC.compute(profile, c,
                          index().effective_ruleset(c, scope=RULES.SCOPE_CALC),
                          units())["total_raw"]
    report = QUOTA.compute_quota(pack, c, actual,
                                 params={"output": profile["output"]["value"],
                                         "correction_factor": "0.97"})
    assert report["gap_ratio"].startswith("0.022")


def test_truth_quota_missing_benchmark_uses_input_required():
    """truth: quota_missing_benchmark → 2024 发电基准值为 input_required，未提供即报错。"""
    c = coord("gbt32150-2025/2024/power")
    pack = index().effective_ruleset(c, scope=RULES.SCOPE_QUOTA)
    entry = pack["quota"]["params"]["benchmark_value"]
    assert entry["status"] == RULES.STATUS_INPUT_REQUIRED
    with pytest.raises(ENGINE.QuotaUnavailable):
        QUOTA.compute_quota(pack, c, "1", params={"output": "1"})


def test_truth_quota_case_actual_emission():
    """truth: quota_benchmark 的 actual 与核算路径合计一致（296845.486 呈现口径）。"""
    c = coord("gbt32150-2025/2025/power")
    profile = subject(os.path.join(SAMPLES, "profile-power-2025.json"))["profile"]
    result = CALC.compute(profile, c,
                          index().effective_ruleset(c, scope=RULES.SCOPE_CALC), units())
    assert result["total"] == "296845.486"


# ==========================================================================
# 十二、补充判定面（因子分派 / 边界 reason / 校核约束 / 报告头口径）
# ==========================================================================
def test_factor_default_by_category_dispatch():
    """行业缺省因子按类别分派：无覆盖 → default_factor（provenance 不含 by_category）。"""
    pack = index().pack(coord("gbt32150-2025/2024/power"))
    entry, label = CALC._default_factor_entry(pack, "combustion")
    assert entry is not None
    assert label.startswith("industry_default")
    entry2, label2 = CALC._default_factor_entry(pack, "no_such_category")
    assert label2 == "industry_default"


def test_factor_declared_official_db_accepted():
    pack = index().pack(coord("gbt32150-2025/2024/power"))
    source = {"source_id": "stationary_combustion",
              "factor": {"value": "3.0", "unit": "tCO2e_per_t",
                         "source": "official_db"}}
    value, unit, label, prov = CALC._select_factor(source, pack, "combustion")
    assert label == "official_db"
    assert value == Decimal(3)


def test_factor_priority_respected():
    """规则包 priority 次序（实测 > 官方库 > 行业缺省）；非优先来源被拒。"""
    pack = copy.deepcopy(index().pack(coord("gbt32150-2025/2024/power")))
    pack["factors"]["priority"] = ["measured"]
    source = {"source_id": "stationary_combustion",
              "factor": {"value": "3.0", "unit": "tCO2e_per_t",
                         "source": "official_db"}}
    with pytest.raises(ENGINE.FactorUnavailable):
        CALC._select_factor(source, pack, "combustion")


def test_boundary_reason_carries_clause():
    c = coord("gbt32150-2025/2024/power")
    report = RULES.identify_boundary(calc_payload(), c, index().pack(c))
    included = [s for s in report["sources"] if s["included"]][0]
    assert "依据" in included["reason"]


def test_boundary_delta_invalid_declared():
    c_old = coord("gbt32150-2015/2024/power")
    c_new = coord("gbt32150-2025/2024/power")
    packs = dict(REGISTRY.packs())
    packs[c_new.key] = copy.deepcopy(packs[c_new.key])
    for src in packs[c_new.key]["boundary"]["sources"]:
        src["delta_vs_2015"] = "weird"
    broken = RULES.RulesIndex(REGISTRY.manifest(), packs)
    with pytest.raises(ENGINE.BoundaryError):
        RULES.diff_boundary(c_old, c_new, broken)


def test_quality_does_not_mutate_profile():
    profile = _steel_profile()
    before = json.dumps(profile, sort_keys=True)
    _checks(profile)
    assert json.dumps(profile, sort_keys=True) == before


def test_quality_does_not_mutate_calc():
    c = coord("gbt32150-2025/2024/steel")
    profile = _steel_profile()
    calc = CALC.compute(profile, c,
                        index().effective_ruleset(c, scope=RULES.SCOPE_CALC), units())
    before = json.dumps(calc, sort_keys=True)
    pack = index().effective_ruleset(c, scope=RULES.SCOPE_CHECK)
    CALC.run_checks(profile, calc, c, pack, units=units())
    assert json.dumps(calc, sort_keys=True) == before


def test_quality_skipped_records_reason():
    report = _checks(_steel_profile())
    for skip in report["rules_skipped"]:
        assert skip["reason"]
        assert skip["rule_ids"]


def test_quota_input_required_cites_note():
    c = coord("gbt32150-2025/2024/power")
    pack = index().pack(c)
    entry = QUOTA._entry_of(pack, "quota.params.benchmark_value")
    with pytest.raises(ENGINE.QuotaUnavailable) as exc_info:
        QUOTA._resolve(entry, "benchmark", None)
    assert "外部提供" in str(exc_info.value)


def test_quota_alpha_in_band_is_linear():
    pack = index().pack(coord("gbt32150-2025/2024/steel"))
    derivation = pack["quota"]["derivation"]
    slope = ENGINE.as_decimal(derivation["slope"]["value"])
    band = ENGINE.as_decimal(derivation["band"]["value"])
    bp = ENGINE.as_decimal(100)
    intensity = bp * (ENGINE.as_decimal(1) - band / 2)
    alpha, x = QUOTA._derive_alpha(pack, bp, intensity)
    assert alpha == slope * x
    assert -band < x < band


def test_result_message_present_in_human_output():
    lines = report(subject(CALC_SAMPLE)).as_lines()
    assert any("ghg.result" in line for line in lines)