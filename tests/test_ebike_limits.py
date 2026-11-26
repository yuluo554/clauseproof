"""器官 ``ebike-limits`` 无损判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在「判定结果」上。
来源仓判定层（D1 + D18 机械选 7 文件 / 实跑 185 passed / AST 函数 175）逐文件处置见
``docs/ebike-limits.md`` §6；本文件承载规则包 schema 校验、status 门控、
applies_if 三值逻辑、单位归一与 Decimal 比较、四态判定矩阵、版本锚定、
字段映射、跨标准统一结论与账本映射。

本文件同时是**漂移门**：随包规则包四册与 manifest 的 sha256 登记必须一致、
mapping 字面量与来源资产转写逐条一致。
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
    Finding,
    Report,
)
from clauseproof.core.registry import Pack, all_packs, get  # noqa: E402
from clauseproof import cli as cp_cli  # noqa: E402

PACK_MOD = importlib.import_module("clauseproof.packs.ebike-limits")
ENGINE = importlib.import_module("clauseproof.packs.ebike-limits.engine")
REGISTRY = importlib.import_module("clauseproof.packs.ebike-limits.registry")
MAPPING = importlib.import_module("clauseproof.packs.ebike-limits.mapping")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "ebike-limits")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "ebike-limits")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
README_PATH = os.path.join(SAMPLES, "profile-readme.json")
VIOLATION_PATH = os.path.join(SAMPLES, "profile-violation.json")


def basis():
    return Basis.from_json(BASIS_PATH)


def subject(path=README_PATH):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def findings(sub=None):
    return tuple(PACK_MOD.evaluate(subject() if sub is None else sub, basis()))


def rules(found):
    return [finding.rule_id for finding in found]


def one(found, rule_id):
    hits = [finding for finding in found if finding.rule_id == rule_id]
    assert len(hits) == 1, (rule_id, rules(found))
    return hits[0]


def report(sub, name="case.json"):
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject=name, findings=findings(sub))


def docs_copy():
    return REGISTRY.ruleset_docs()


def _ruleset_by_file(docs, file_name):
    return ENGINE.build_ruleset(docs[file_name], file_name)


def _find_rule(ruleset, rule_id):
    for rule in ruleset["rules"]:
        if rule["id"] == rule_id:
            return rule
    raise AssertionError(rule_id)


def _param(profile, name, value, unit):
    out = copy.deepcopy(profile)
    out["params"][name] = {"value": value, "unit": unit} if unit else {"value": value}
    return out


def _bad_ruleset(**overrides):
    """最小合法规则包（供 schema 校验负例）。"""
    doc = {
        "schema_version": "1.0",
        "standard": {"code": "GB X-0000", "title": "测试标准", "published": "2024-01-01",
                     "effective": "2024-02-01", "status": "current"},
        "scope": "vehicle",
        "rules": [{
            "id": "X-1", "param": "p", "op": "<=", "value": "1", "unit": "kg",
            "clause": "1.1", "clause_status": "verified",
            "source": {"kind": "standard_text", "url": "https://example.gov/a",
                       "retrieved_on": "2026-10-14"},
            "status": "verified", "verified_on": "2026-10-14",
        }],
    }
    doc.update(overrides)
    if "standard" in overrides and isinstance(overrides["standard"], dict):
        doc["standard"] = dict(doc["standard"], **overrides["standard"])
    return doc


# ==========================================================================
# 一、器官契约与装配
# ==========================================================================
def test_pack_is_registered_under_slug():
    pack = get(SLUG)
    assert isinstance(pack, Pack)
    assert pack.slug == SLUG
    assert pack.version == PACK_MOD.VERSION


def test_pack_version_tracks_snapshot_version():
    assert PACK_MOD.VERSION == "0.1.0"


def test_pack_input_fields():
    assert PACK_MOD.INPUT_FIELDS == ("profile_id", "params")


def test_slug_in_builtin_modules_sorted():
    packs_ns = importlib.import_module("clauseproof.packs")
    assert SLUG in packs_ns.BUILTIN_MODULES
    assert list(packs_ns.BUILTIN_MODULES) == sorted(packs_ns.BUILTIN_MODULES)


def test_pack_appears_in_all_packs():
    assert SLUG in [pack.slug for pack in all_packs()]


def test_clauses_json_exists():
    assert os.path.isfile(BASIS_PATH)


def test_clauses_version_matches_snapshot():
    payload = json.load(open(BASIS_PATH, encoding="utf-8"))
    assert payload["version"] == REGISTRY.PARAMS_VERSION


def test_clauses_cover_every_spec():
    payload = json.load(open(BASIS_PATH, encoding="utf-8"))
    got = {c["clause_id"] for c in payload["clauses"]}
    assert got == {clause_id for clause_id, _path in REGISTRY.clause_specs()}


def test_clauses_have_expected_count():
    payload = json.load(open(BASIS_PATH, encoding="utf-8"))
    assert len(payload["clauses"]) == 8


def test_clauses_paths_match_specs():
    payload = json.load(open(BASIS_PATH, encoding="utf-8"))
    specs = dict(REGISTRY.clause_specs())
    for clause in payload["clauses"]:
        assert clause["path"] == specs[clause["clause_id"]]


def test_missing_anchor_raises_basis_missing(tmp_path):
    path = tmp_path / "clauses.json"
    path.write_text(json.dumps({"version": REGISTRY.PARAMS_VERSION, "clauses": []}),
                    encoding="utf-8")
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate(subject(), Basis.from_json(str(path)))


# ==========================================================================
# 二、漂移门（随包规则包 ↔ manifest 登记 sha256 ↔ 来源资产）
# ==========================================================================
def _sha256_of(name):
    import hashlib
    with open(os.path.join(DATA_DIR, name), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def test_manifest_registered_sha256_matches_files():
    manifest = REGISTRY.manifest()
    for entry in manifest["rulesets"]:
        assert entry["sha256"] == _sha256_of(entry["file"]), entry["file"]


def test_manifest_entries_match_engine_files():
    manifest = REGISTRY.manifest()
    registered = {e["file"]: (e["scope"], e["version_key"]) for e in manifest["rulesets"]}
    for file_name, scope, key in ENGINE.RULESET_FILES:
        assert registered[file_name] == (scope, key), file_name


def test_ruleset_files_are_four():
    assert len(ENGINE.RULESET_FILES) == 4


def test_2018_ruleset_is_abolished_with_pending_clauses():
    """废止标准：数值经官方问答引述核对（verified），条款号如实 pending（无全文可核）。"""
    doc = REGISTRY.ruleset_doc("gb17761-2018.json")
    assert doc["standard"]["status"] == "abolished"
    for rule in doc["rules"]:
        assert rule["status"] == "verified"
        assert rule["clause_status"] == "pending"
        assert rule["clause"] is None


def test_pending_rules_never_prefill_value():
    for file_name, _scope, _key in ENGINE.RULESET_FILES:
        doc = REGISTRY.ruleset_doc(file_name)
        for rule in doc["rules"]:
            if rule["status"] != "verified":
                assert rule["value"] is None, rule["id"]


def test_verified_rules_carry_clauses():
    for file_name, _scope, _key in ENGINE.RULESET_FILES:
        doc = REGISTRY.ruleset_doc(file_name)
        for rule in doc["rules"]:
            if rule["clause_status"] == "verified":
                assert rule["clause"], rule["id"]
            else:
                assert rule["clause"] is None, rule["id"]


def test_version_anchors_match_engine_default():
    manifest = REGISTRY.manifest()
    anchors = manifest["version_anchors"]
    for window in anchors:
        assert window in [dict(w) for w in ENGINE.DEFAULT_VERSION_ANCHORS]


def test_mapping_variants_cover_every_effective_param():
    """映射表覆盖全部生效规则参数（来源 test_mapping_covers_every_rule_package_param）。"""
    table = MAPPING.ParamMapping()
    for file_name, _scope, _key in ENGINE.RULESET_FILES:
        ruleset = _ruleset_by_file(docs_copy(), file_name)
        for rule in ruleset["rules"]:
            assert table.variants.get(rule["param"]) == rule["param"] or \
                rule["param"] in {p for p, _u, _v, _a in MAPPING.MAPPING_ENTRIES}, rule["id"]


def test_mapping_unit_alias_table_covers_factor_units():
    """单位别名表覆盖引擎换算表的规范单位（来源 test_unit_alias_table_covers_factor_units）。"""
    index = MAPPING.unit_alias_index()
    for canonical in ENGINE.UNIT_FACTORS:
        if canonical == "":
            continue
        assert canonical in index, canonical


# ==========================================================================
# 三、规则包 schema 校验
# ==========================================================================
def test_valid_minimal_ruleset_passes():
    ruleset = ENGINE.build_ruleset(_bad_ruleset(), "t.json")
    assert len(ruleset["rules"]) == 1
    assert ruleset["excluded"] == []


def test_bad_op_rejected():
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(rules=[dict(_bad_ruleset()["rules"][0], op="~")]),
                             "t.json")


def test_pending_with_value_rejected():
    rule = dict(_bad_ruleset()["rules"][0], status="pending")
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(rules=[rule]), "t.json")


def test_verified_with_null_value_rejected():
    rule = dict(_bad_ruleset()["rules"][0], value=None)
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(rules=[rule]), "t.json")


def test_pending_clause_must_be_null():
    rule = dict(_bad_ruleset()["rules"][0], clause_status="pending")
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(rules=[rule]), "t.json")


def test_verified_clause_must_be_present():
    rule = dict(_bad_ruleset()["rules"][0], clause=None)
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(rules=[rule]), "t.json")


def test_duplicate_id_rejected():
    rule = _bad_ruleset()["rules"][0]
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(rules=[rule, rule]), "t.json")


def test_same_target_duplicate_rejected():
    rule = _bad_ruleset()["rules"][0]
    second = dict(rule, id="X-2")
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(rules=[rule, second]), "t.json")


def test_same_param_different_applies_if_allowed():
    rule = _bad_ruleset()["rules"][0]
    second = dict(rule, id="X-2", clause="1.2",
                  applies_if={"param": "battery_type", "op": "==", "value": "lead_acid"},
                  applies_if_raw={"param": "battery_type", "op": "==", "value": "lead_acid"})
    ruleset = ENGINE.build_ruleset(_bad_ruleset(rules=[rule, second]), "t.json")
    assert len(ruleset["rules"]) == 2


def test_bad_source_kind_rejected():
    rule = dict(_bad_ruleset()["rules"][0],
                source={"kind": "blog", "url": "https://x", "retrieved_on": "2026-10-14"})
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(rules=[rule]), "t.json")


def test_source_without_url_rejected():
    rule = dict(_bad_ruleset()["rules"][0],
                source={"kind": "standard_text", "retrieved_on": "2026-10-14"})
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(rules=[rule]), "t.json")


def test_bad_date_rejected():
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(
            _bad_ruleset(standard={"published": "2024/01/01"}), "t.json")


def test_bad_scope_rejected():
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(scope="frame"), "t.json")


def test_empty_rules_rejected():
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(rules=[]), "t.json")


def test_applies_if_unknown_key_rejected():
    rule = dict(_bad_ruleset()["rules"][0],
                applies_if={"when": "x"}, applies_if_raw={"when": "x"})
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(rules=[rule]), "t.json")


def test_applies_if_bad_op_rejected():
    rule = dict(_bad_ruleset()["rules"][0],
                applies_if={"param": "p", "op": "≈", "value": "1"},
                applies_if_raw={"param": "p", "op": "≈", "value": "1"})
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.build_ruleset(_bad_ruleset(rules=[rule]), "t.json")


def test_manifest_structure_enforced():
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.load_manifest({"schema_version": "1.0"})


def test_manifest_scope_whitelist():
    manifest = REGISTRY.manifest()
    for entry in manifest["rulesets"]:
        assert entry["scope"] in ("vehicle", "battery", "charger")


# ==========================================================================
# 四、status 门控
# ==========================================================================
def test_pending_rule_goes_to_excluded():
    rule = dict(_bad_ruleset()["rules"][0], status="pending", value=None)
    ruleset = ENGINE.build_ruleset(_bad_ruleset(rules=[rule]), "t.json")
    assert ruleset["rules"] == []
    assert len(ruleset["excluded"]) == 1
    assert ruleset["excluded"][0]["reason"] == "not_verified"


def test_real_pack_excludes_pending_only():
    for file_name, _scope, _key in ENGINE.RULESET_FILES:
        ruleset = _ruleset_by_file(docs_copy(), file_name)
        total = len(ruleset["rules"]) + len(ruleset["excluded"])
        doc = REGISTRY.ruleset_doc(file_name)
        assert total == len(doc["rules"]), file_name


def test_battery_pack_is_fully_pending():
    ruleset = _ruleset_by_file(docs_copy(), "gb43854-2024.json")
    assert ruleset["rules"] == []
    assert len(ruleset["excluded"]) == 2


def test_charger_pack_has_one_effective_rule():
    ruleset = _ruleset_by_file(docs_copy(), "gb42296-2022.json")
    assert len(ruleset["rules"]) == 1
    assert len(ruleset["excluded"]) == 2


# ==========================================================================
# 五、applies_if 三值逻辑
# ==========================================================================
def test_applies_if_none_is_true():
    assert ENGINE.eval_applies_if(None, {}) is True


def test_applies_if_param_missing_is_unknown():
    expr = {"param": "battery_type", "op": "==", "value": "lead_acid"}
    assert ENGINE.eval_applies_if(expr, {}) is None


def test_applies_if_param_hit():
    expr = {"param": "battery_type", "op": "==", "value": "lead_acid"}
    assert ENGINE.eval_applies_if(expr, {"battery_type": {"value": "lead_acid"}}) is True
    assert ENGINE.eval_applies_if(expr, {"battery_type": {"value": "lithium"}}) is False


def test_applies_if_unknown_string_value_falls_to_text_compare():
    expr = {"param": "battery_type", "op": "==", "value": "lead_acid"}
    assert ENGINE.eval_applies_if(expr, {"battery_type": {"value": "abc"}}) is False


def test_applies_if_not_logic():
    expr = {"not": {"param": "battery_type", "op": "==", "value": "lead_acid"}}
    assert ENGINE.eval_applies_if(expr, {"battery_type": {"value": "lithium"}}) is True
    assert ENGINE.eval_applies_if(expr, {"battery_type": {"value": "lead_acid"}}) is False
    assert ENGINE.eval_applies_if(expr, {}) is None


def test_applies_if_all_any_logic():
    all_expr = {"all": [
        {"param": "battery_type", "op": "==", "value": "lead_acid"},
        {"param": "nominal_voltage", "op": "<=", "value": "48"},
    ]}
    params = {"battery_type": {"value": "lead_acid"},
              "nominal_voltage": {"value": "60"}}
    assert ENGINE.eval_applies_if(all_expr, params) is False
    params2 = {"battery_type": {"value": "lead_acid"},
               "nominal_voltage": {"value": "48"}}
    assert ENGINE.eval_applies_if(all_expr, params2) is True
    any_expr = {"any": [
        {"param": "battery_type", "op": "==", "value": "lead_acid"},
        {"param": "nominal_voltage", "op": "<=", "value": "48"},
    ]}
    assert ENGINE.eval_applies_if(any_expr, params) is True


# ==========================================================================
# 六、单位归一与比较
# ==========================================================================
def test_decode_decimal_rejects_bool_and_garbage():
    assert ENGINE.decode_decimal(True) is None
    assert ENGINE.decode_decimal("abc") is None
    assert ENGINE.decode_decimal("") is None
    assert ENGINE.decode_decimal("63") == Decimal("63")


def test_compare_numeric_and_enum_paths():
    assert ENGINE.compare("30", "<=", "25") is False
    assert ENGINE.compare("25", "<=", "25") is True
    assert ENGINE.compare(True, "==", "true") is True
    assert ENGINE.compare("lead_acid", "==", "lead_acid") is True


def test_normalize_unit_same_unit_no_downgrade():
    number, downgraded = ENGINE.normalize_unit("70", "kg", "kg")
    assert number == Decimal("70")
    assert downgraded is False


def test_normalize_unit_gram_to_kilogram_downgrades():
    number, downgraded = ENGINE.normalize_unit("70000", "g", "kg")
    assert number == Decimal("70")
    assert downgraded is True


def test_normalize_unit_incompatible_raises():
    with pytest.raises(ENGINE.UnitError) as exc_info:
        ENGINE.normalize_unit("70", "斤", "kg")
    assert exc_info.value.reason == "unit_incompatible"


def test_normalize_unit_missing_unit_raises():
    with pytest.raises(ENGINE.UnitError) as exc_info:
        ENGINE.normalize_unit("70", "", "kg")
    assert exc_info.value.reason == "unit_unknown"


def test_resolve_unit_alias_chinese():
    index = MAPPING.unit_alias_index()
    assert ENGINE.resolve_unit("公斤", index) == "kg"
    assert ENGINE.resolve_unit("公里/小时", index) == "km/h"
    assert ENGINE.resolve_unit("％", index) == "%"


def test_resolve_unit_unknown_kept_as_is():
    assert ENGINE.resolve_unit("里") == "里"


def test_epsilon_for_registered_units():
    assert ENGINE.epsilon_for("km/h") == Decimal("0.1")
    assert ENGINE.epsilon_for("W") == Decimal("1")
    assert ENGINE.epsilon_for("尺") == Decimal("0.1")


def test_boundary_one_epsilon_detectable():
    """边界扫描：检出 1 个最小计量单位的差异（Decimal 全链路）。"""
    assert ENGINE.compare("25.1", "<=", "25") is False
    assert ENGINE.compare("25.0", "<=", "25") is True


# ==========================================================================
# 七、四态判定矩阵
# ==========================================================================
def test_check_param_compliant():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    rule = _find_rule(ruleset, "GB17761-2024-max_design_speed")
    out = ENGINE.check_param(rule, {"max_design_speed": {"value": "25", "unit": "km/h"}})
    assert out["state"] == "compliant"
    assert out["observed"] == "25"


def test_check_param_non_compliant():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    rule = _find_rule(ruleset, "GB17761-2024-max_design_speed")
    out = ENGINE.check_param(rule, {"max_design_speed": {"value": "30", "unit": "km/h"}})
    assert out["state"] == "non_compliant"


def test_check_param_missing_is_not_provided():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    rule = _find_rule(ruleset, "GB17761-2024-plastic_mass_ratio")
    out = ENGINE.check_param(rule, {})
    assert out["state"] == "not_provided"
    assert out["reason"] == "missing"


def test_check_param_null_value():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    rule = _find_rule(ruleset, "GB17761-2024-plastic_mass_ratio")
    out = ENGINE.check_param(rule, {"plastic_mass_ratio": {"value": None, "unit": "%"}})
    assert out["state"] == "not_provided"
    assert out["reason"] == "null_value"


def test_check_param_unit_incompatible():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    rule = _find_rule(ruleset, "GB17761-2024-vehicle_mass-lead-acid")
    out = ENGINE.check_param(rule, {"vehicle_mass": {"value": "70", "unit": "斤"},
                                    "battery_type": {"value": "lead_acid"}})
    assert out["state"] == "not_provided"
    assert out["reason"] == "unit_incompatible"


def test_check_param_unit_downgrade_warning():
    """g→kg 可无损换算：判定降级 warning（70000 g = 70 kg > 63 kg → 不符合）。"""
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    rule = _find_rule(ruleset, "GB17761-2024-vehicle_mass-lead-acid")
    out = ENGINE.check_param(rule, {"vehicle_mass": {"value": "60000", "unit": "g"},
                                    "battery_type": {"value": "lead_acid"}})
    assert out["state"] == "compliant"
    assert out["severity"] == "warning"
    assert "换算" in out["notes"]


def test_check_param_unparsable():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    rule = _find_rule(ruleset, "GB17761-2024-vehicle_mass-lead-acid")
    out = ENGINE.check_param(rule, {"vehicle_mass": {"value": "abc", "unit": "kg"},
                                    "battery_type": {"value": "lead_acid"}})
    assert out["state"] == "not_provided"
    assert out["reason"] == "unparsable"


def test_check_param_mapping_uncertain_marker():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    rule = _find_rule(ruleset, "GB17761-2024-max_design_speed")
    out = ENGINE.check_param(rule, {"max_design_speed": {"value": None,
                                                         "reason": "mapping_uncertain"}})
    assert out["state"] == "not_provided"
    assert out["reason"] == "mapping_uncertain"


def test_check_param_condition_unknown():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    rule = _find_rule(ruleset, "GB17761-2024-vehicle_mass-lead-acid")
    out = ENGINE.check_param(rule, {"vehicle_mass": {"value": "70", "unit": "kg"}})
    assert out["state"] == "not_provided"
    assert out["reason"] == "condition_unknown"


def test_check_param_not_applicable_branch():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    rule = _find_rule(ruleset, "GB17761-2024-vehicle_mass-other")
    out = ENGINE.check_param(rule, {"battery_type": {"value": "lead_acid"},
                                    "vehicle_mass": {"value": "70", "unit": "kg"}})
    assert out["state"] == "not_applicable"


def test_check_param_dimensionless_enum_path():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    rule = _find_rule(ruleset, "GB17761-2024-anti_tamper-battery")
    out = ENGINE.check_param(rule, {"anti_tamper_battery_pack": {"value": True}})
    assert out["state"] == "compliant"
    assert out["observed"] == "true"


def test_check_param_dimensionless_enum_violation():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    rule = _find_rule(ruleset, "GB17761-2024-anti_tamper-battery")
    out = ENGINE.check_param(rule, {"anti_tamper_battery_pack": {"value": False}})
    assert out["state"] == "non_compliant"


def test_check_params_all_vehicle_rules():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2024.json")
    profile = subject()
    findings = ENGINE.check_params(ruleset["rules"], profile["params"])
    assert len(findings) == len(ruleset["rules"])


def test_dimension_overall_precedence():
    def _f(state):
        return {"state": state}
    assert ENGINE.dimension_overall([_f("compliant"), _f("non_compliant")]) == "non_compliant"
    assert ENGINE.dimension_overall([_f("compliant"), _f("not_provided")]) == "not_provided"
    assert ENGINE.dimension_overall([_f("compliant")]) == "compliant"
    assert ENGINE.dimension_overall([_f("not_applicable")]) == "not_assessed"


# ==========================================================================
# 八、版本锚定
# ==========================================================================
def test_anchor_version_2024_window():
    assert ENGINE.anchor_version({"model_design_date": "2025-10-01"}) == "GB17761-2024"
    assert ENGINE.anchor_version({"model_design_date": "2025-09-01"}) == "GB17761-2024"


def test_anchor_version_2018_window():
    assert ENGINE.anchor_version({"model_design_date": "2024-06-01"}) == "GB17761-2018"
    assert ENGINE.anchor_version({"market_date": "2020-01-01"}) == "GB17761-2018"


def test_anchor_version_design_date_wins():
    assert ENGINE.anchor_version({"model_design_date": "2026-01-01",
                                  "market_date": "2020-01-01"}) == "GB17761-2024"


def test_anchor_version_no_date_raises():
    with pytest.raises(ENGINE.VersionError):
        ENGINE.anchor_version({})


def test_anchor_version_bad_date_raises():
    with pytest.raises(ENGINE.VersionError):
        ENGINE.anchor_version({"model_design_date": "2025/10/01"})


def test_anchor_version_windows_are_exhaustive():
    """窗口并集覆盖任意日期（2018 窗口无下界 → 不存在"窗口外"日期）。"""
    assert ENGINE.anchor_version({"model_design_date": "2010-01-01"}) == "GB17761-2018"
    assert ENGINE.anchor_version({"model_design_date": "2099-01-01"}) == "GB17761-2024"


def test_subject_explicit_version_key_wins():
    sub = subject()
    sub["version_key"] = "GB17761-2018"
    result = ENGINE.check_profile(sub, docs_copy())
    assert result["version_key"] == "GB17761-2018"
    vehicle = next(d for d in result["dimensions"] if d["scope"] == "vehicle")
    assert vehicle["standard"] == "GB 17761-2018"


# ==========================================================================
# 九、字段映射
# ==========================================================================
def test_mapping_resolve_exact_variant():
    table = MAPPING.ParamMapping()
    verdict, param = table.resolve("最高车速")
    assert verdict == "mapped" and param == "max_design_speed"


def test_mapping_resolve_ambiguous_variant():
    table = MAPPING.ParamMapping()
    verdict, param = table.resolve("车速")
    assert verdict == "uncertain" and param is None


def test_mapping_resolve_unmapped():
    table = MAPPING.ParamMapping()
    verdict, param = table.resolve("轮距")
    assert verdict == "unmapped"


def test_mapping_conflicting_variant_rejected():
    entries = (("a", "kg", ("列",), ()), ("b", "kg", ("列",), ()))
    with pytest.raises(MAPPING.MappingError):
        MAPPING.ParamMapping(entries)


def test_normalize_params_maps_and_fills_units():
    """精确命中补规范单位；歧义列名（无精确命中时）对候选参数注入 uncertain 标记。"""
    columns = {"最高车速": {"value": "25"}, "整车重量": {"value": "70"}}
    out = MAPPING.normalize_params(columns)
    assert out["max_design_speed"]["value"] == "25"
    assert out["max_design_speed"]["unit"] == "km/h"
    assert out["vehicle_mass"]["value"] == "70"
    assert out["vehicle_mass"]["unit"] == "kg"


def test_normalize_params_uncertain_marker_standalone():
    """歧义列名单独出现：候选参数注入 mapping_uncertain 标记（绝不猜值）。"""
    out = MAPPING.normalize_params({"车速": {"value": "30", "unit": "km/h"}})
    assert out["max_design_speed"]["value"] is None
    assert out["max_design_speed"]["reason"] == "mapping_uncertain"
    assert out["max_design_speed"]["unit"] == "km/h"


def test_normalize_params_drops_unmapped():
    out = MAPPING.normalize_params({"轮距": {"value": "1.2", "unit": "m"}})
    assert out == {}


def test_normalize_params_scalar_entry():
    out = MAPPING.normalize_params({"最高车速": "25"})
    assert out["max_design_speed"]["value"] == "25"


def test_mapping_param_count_is_fourteen():
    table = MAPPING.ParamMapping()
    assert table.param_count == 14


# ==========================================================================
# 十、三维装配与统一结论
# ==========================================================================
def test_check_profile_readme_matches_old_counts():
    """判据 2 对账：readme 样例四态计数与旧 CLI 输出逐值一致。"""
    result = ENGINE.check_profile(subject(), docs_copy())
    assert result["counts"] == {"compliant": 5, "non_compliant": 0,
                                "not_applicable": 1, "not_provided": 5}
    assert result["overall"] == "not_provided"


def test_check_profile_violation_matches_old_counts():
    """判据 2 对账：越限样例四态计数与旧 CLI 输出逐值一致。"""
    result = ENGINE.check_profile(subject(VIOLATION_PATH), docs_copy())
    assert result["counts"] == {"compliant": 4, "non_compliant": 6,
                                "not_applicable": 1, "not_provided": 0}
    assert result["overall"] == "non_compliant"


def test_check_profile_dimensions_in_fixed_order():
    result = ENGINE.check_profile(subject(), docs_copy())
    assert [d["scope"] for d in result["dimensions"]] == ["vehicle", "battery", "charger"]


def test_battery_dimension_not_participating():
    result = ENGINE.check_profile(subject(), docs_copy())
    battery = next(d for d in result["dimensions"] if d["scope"] == "battery")
    assert battery["effective_rule_count"] == 0
    assert battery["participates"] is False


def test_vehicle_dimension_participates():
    result = ENGINE.check_profile(subject(), docs_copy())
    vehicle = next(d for d in result["dimensions"] if d["scope"] == "vehicle")
    assert vehicle["effective_rule_count"] == 10
    assert vehicle["participates"] is True


def test_excluded_rules_union():
    result = ENGINE.check_profile(subject(), docs_copy())
    assert len(result["excluded_rules"]) == 4


def test_profile_deterministic():
    first = ENGINE.check_profile(subject(), docs_copy())
    second = ENGINE.check_profile(subject(), docs_copy())
    assert first == second


def test_missing_ruleset_doc_raises():
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.check_profile(subject(), {})


def test_bad_subject_rejected():
    with pytest.raises(ENGINE.MatrixError):
        ENGINE.check_profile({"params": {}}, docs_copy())


def test_bad_params_rejected():
    with pytest.raises(ENGINE.MatrixError):
        ENGINE.check_profile({"profile_id": "X", "params": []}, docs_copy())


def test_bad_param_unit_type_rejected():
    with pytest.raises(ENGINE.MatrixError):
        ENGINE.check_profile({"profile_id": "X", "params": {"p": {"value": "1", "unit": 3}}},
                             docs_copy())


# ==========================================================================
# 十一、账本映射与退出码契约
# ==========================================================================
def test_readme_exit_code_is_ok():
    """判据 2：README 示例（合规样例）→ 旧 check rc 0 / 新 check rc 0。"""
    assert report(subject(README_PATH), "profile-readme.json").exit_code() == EXIT_OK


def test_violation_exit_code_is_blocked():
    """判据 2：越限样例 → 旧 check rc 1 / 新 check rc 1（同 6 条 non_compliant）。"""
    assert report(subject(VIOLATION_PATH), "profile-violation.json").exit_code() == EXIT_BLOCKED


def test_violation_blocking_is_six():
    found = findings(subject(VIOLATION_PATH))
    blocking = [f for f in found if f.verdict == FAIL]
    assert len(blocking) == 6
    assert all("non_compliant" in f.message for f in blocking)


def test_violation_hit_rules_match_old():
    """越限 6 条与旧 CLI 输出逐条同 rule_id（含充电器册跨标准条款 5.5.4）。"""
    found = findings(subject(VIOLATION_PATH))
    hit = sorted(f.rule_id for f in found if f.verdict == FAIL)
    assert hit == sorted([
        "ebike.finding:GB17761-2024-max_design_speed",
        "ebike.finding:GB17761-2024-vehicle_mass-lead-acid",
        "ebike.finding:GB17761-2024-plastic_mass_ratio",
        "ebike.finding:GB17761-2024-nominal_voltage",
        "ebike.finding:GB17761-2024-motor_rated_power",
        "ebike.finding:GB42296-2022-charger-no-load-output-voltage",
    ])


def test_findings_carry_clause_evidence():
    found = findings(subject(VIOLATION_PATH))
    speed = one(found, "ebike.finding:GB17761-2024-max_design_speed")
    assert speed.evidence["clause"] == "6.1.1.1"
    assert speed.evidence["clause_status"] == "verified"
    assert speed.evidence["standard"] == "GB 17761-2024"


def test_excluded_findings_are_na_with_gate_anchor():
    found = findings(subject(README_PATH))
    excluded = [f for f in found if f.rule_id.startswith("ebike.excluded:")]
    assert len(excluded) == 4
    for finding in excluded:
        assert finding.verdict == NOT_APPLICABLE
        assert finding.anchor.clause_id == REGISTRY.CLAUSE_STATUS_GATE


def test_not_provided_findings_are_na():
    found = findings(subject(README_PATH))
    not_provided = [f for f in found if f.evidence.get("state") == "not_provided"]
    assert not_provided
    for finding in not_provided:
        assert finding.verdict == NOT_APPLICABLE


def test_result_summary_present():
    found = findings(subject(README_PATH))
    summary = one(found, "ebike.result")
    assert summary.evidence["overall"] == "not_provided"
    assert summary.evidence["version_key"] == "GB17761-2024"
    assert len(summary.evidence["dimensions"]) == 3


def test_all_findings_carry_anchors():
    found = findings(subject(README_PATH))
    for finding in found:
        assert finding.anchor is not None


def test_findings_ids_unique():
    found = findings(subject(README_PATH))
    ids = [f.id for f in found]
    assert len(ids) == len(set(ids))


def test_cli_missing_basis_returns_contract_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input", README_PATH])
    assert code == EXIT_CONTRACT
    assert "ContractError" in capsys.readouterr().err


def test_cli_wrong_basis_version_returns_contract_code(tmp_path, capsys):
    path = tmp_path / "clauses.json"
    path.write_text(json.dumps({"version": "1999-01-01", "clauses": []}), encoding="utf-8")
    code = cp_cli.main(["check", SLUG, "--input", README_PATH, "--basis", str(path)])
    assert code == EXIT_CONTRACT
    assert "ContractError" in capsys.readouterr().err


def test_cli_missing_file_returns_input_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input", "no-such-file.json",
                        "--basis", BASIS_PATH])
    assert code == EXIT_INPUT


def test_cli_missing_required_field_returns_input_code(tmp_path, capsys):
    path = tmp_path / "subject.json"
    path.write_text(json.dumps({"params": {}}), encoding="utf-8")
    code = cp_cli.main(["check", SLUG, "--input", str(path), "--basis", BASIS_PATH])
    assert code == EXIT_INPUT


def test_cli_clean_case_json_flag(capsys):
    code = cp_cli.main(["check", SLUG, "--input", README_PATH,
                        "--basis", BASIS_PATH, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert payload["organ"] == SLUG
    assert payload["summary"]["blocking"] == 0


def test_json_output_deterministic():
    import io
    from contextlib import redirect_stdout

    buffer1, buffer2 = io.StringIO(), io.StringIO()
    argv = ["check", SLUG, "--input", README_PATH, "--basis", BASIS_PATH, "--json"]
    with redirect_stdout(buffer1):
        cp_cli.main(argv)
    with redirect_stdout(buffer2):
        cp_cli.main(argv)
    assert buffer1.getvalue() == buffer2.getvalue()


def test_rule_codes_are_machine_readable():
    found = findings(subject(README_PATH))
    prefixes = ("ebike.finding:", "ebike.excluded:", "ebike.result")
    for finding in found:
        assert finding.rule_id.startswith(prefixes), finding.rule_id


def test_organ_engine_module_has_no_io_or_clock():
    banned = ("os.environ", "datetime.now", "time.time", "date.today", "utcnow",
              "input(", "print(", "open(")
    for name in ("engine.py", "mapping.py"):
        with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for token in banned:
                    assert token not in node.value, (name, token)


def test_engine_imports_are_stdlib_only():
    allowed = {"decimal", "typing", "json"}
    with open(os.path.join(PACK_DIR, "engine.py"), "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in allowed | {"clauseproof"}, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            assert (node.module or "").split(".")[0] in allowed | {"clauseproof"}


def test_no_limit_values_in_engine_source():
    """零限值字面量门（限值只许来自规则包；换算系数是数学常量）。"""
    forbidden = {"'63'", '"63"', "'55'", '"55"', "'5.5'", '"5.5"', "'48'", '"48"',
                 "'42.4'", '"42.4"', "'400'", '"400"', "'25'", '"25"'}
    with open(os.path.join(PACK_DIR, "engine.py"), "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in forbidden, node.value


# ==========================================================================
# 十二、限值矩阵逐参数判定（2024 册 10 条规则 × 三态×边界）
# ==========================================================================
def _vehicle_ruleset():
    return _ruleset_by_file(docs_copy(), "gb17761-2024.json")


def _chk(rule_id, params):
    ruleset = _vehicle_ruleset()
    rule = _find_rule(ruleset, rule_id)
    return ENGINE.check_param(rule, params)


# --- max_design_speed（车速 <= 25 km/h） ---
def test_speed_below_limit_compliant():
    assert _chk("GB17761-2024-max_design_speed",
                {"max_design_speed": {"value": "24.9", "unit": "km/h"}})["state"] == "compliant"


def test_speed_at_limit_compliant():
    assert _chk("GB17761-2024-max_design_speed",
                {"max_design_speed": {"value": "25", "unit": "km/h"}})["state"] == "compliant"


def test_speed_above_limit_non_compliant():
    assert _chk("GB17761-2024-max_design_speed",
                {"max_design_speed": {"value": "25.1", "unit": "km/h"}})["state"] == "non_compliant"


def test_speed_mps_unit_converts():
    out = _chk("GB17761-2024-max_design_speed",
               {"max_design_speed": {"value": "7.1", "unit": "m/s"}})
    assert out["state"] == "non_compliant"
    assert out["severity"] == "warning"


def test_speed_kmh_alias_compliant():
    out = _chk("GB17761-2024-max_design_speed",
               {"max_design_speed": {"value": "25", "unit": "公里/小时"}})
    assert out["state"] == "compliant"


# --- vehicle_mass（铅酸 63 kg / 其他 55 kg） ---
def test_mass_lead_acid_at_limit():
    out = _chk("GB17761-2024-vehicle_mass-lead-acid",
               {"vehicle_mass": {"value": "63", "unit": "kg"},
                "battery_type": {"value": "lead_acid"}})
    assert out["state"] == "compliant"


def test_mass_lead_acid_over_limit():
    out = _chk("GB17761-2024-vehicle_mass-lead-acid",
               {"vehicle_mass": {"value": "63.1", "unit": "kg"},
                "battery_type": {"value": "lead_acid"}})
    assert out["state"] == "non_compliant"


def test_mass_other_battery_at_limit():
    out = _chk("GB17761-2024-vehicle_mass-other",
               {"vehicle_mass": {"value": "55", "unit": "kg"},
                "battery_type": {"value": "lithium"}})
    assert out["state"] == "compliant"


def test_mass_other_battery_over_limit():
    out = _chk("GB17761-2024-vehicle_mass-other",
               {"vehicle_mass": {"value": "55.1", "unit": "kg"},
                "battery_type": {"value": "lithium"}})
    assert out["state"] == "non_compliant"


def test_mass_other_battery_na_for_lead_acid():
    out = _chk("GB17761-2024-vehicle_mass-other",
               {"vehicle_mass": {"value": "60", "unit": "kg"},
                "battery_type": {"value": "lead_acid"}})
    assert out["state"] == "not_applicable"


def test_mass_lead_acid_na_for_other():
    out = _chk("GB17761-2024-vehicle_mass-lead-acid",
               {"vehicle_mass": {"value": "60", "unit": "kg"},
                "battery_type": {"value": "lithium"}})
    assert out["state"] == "not_applicable"


def test_mass_battery_type_null_condition_unknown():
    out = _chk("GB17761-2024-vehicle_mass-lead-acid",
               {"vehicle_mass": {"value": "60", "unit": "kg"},
                "battery_type": {"value": None}})
    assert out["state"] == "not_provided"
    assert out["reason"] == "condition_unknown"


def test_mass_ton_unit_converts():
    out = _chk("GB17761-2024-vehicle_mass-lead-acid",
               {"vehicle_mass": {"value": "0.05", "unit": "t"},
                "battery_type": {"value": "lead_acid"}})
    assert out["state"] == "compliant"
    assert out["severity"] == "warning"


# --- plastic_mass_ratio（塑料占比 <= 5.5 %） ---
def test_plastic_at_limit_compliant():
    out = _chk("GB17761-2024-plastic_mass_ratio",
               {"plastic_mass_ratio": {"value": "5.5", "unit": "%"}})
    assert out["state"] == "compliant"


def test_plastic_over_limit_non_compliant():
    out = _chk("GB17761-2024-plastic_mass_ratio",
               {"plastic_mass_ratio": {"value": "5.6", "unit": "%"}})
    assert out["state"] == "non_compliant"


def test_plastic_permille_unit_converts():
    out = _chk("GB17761-2024-plastic_mass_ratio",
               {"plastic_mass_ratio": {"value": "50", "unit": "‰"}})
    assert out["state"] == "compliant"
    assert out["severity"] == "warning"


def test_plastic_missing_not_provided():
    out = _chk("GB17761-2024-plastic_mass_ratio", {})
    assert out["state"] == "not_provided"
    assert out["reason"] == "missing"


# --- nominal_voltage（标称电压 <= 48 V） ---
def test_voltage_at_limit_compliant():
    out = _chk("GB17761-2024-nominal_voltage",
               {"nominal_voltage": {"value": "48", "unit": "V"}})
    assert out["state"] == "compliant"


def test_voltage_over_limit_non_compliant():
    out = _chk("GB17761-2024-nominal_voltage",
               {"nominal_voltage": {"value": "60", "unit": "V"}})
    assert out["state"] == "non_compliant"


def test_voltage_mv_unit_converts():
    out = _chk("GB17761-2024-nominal_voltage",
               {"nominal_voltage": {"value": "48000", "unit": "mV"}})
    assert out["state"] == "compliant"
    assert out["severity"] == "warning"


def test_voltage_chinese_alias():
    out = _chk("GB17761-2024-nominal_voltage",
               {"nominal_voltage": {"value": "48", "unit": "伏特"}})
    assert out["state"] == "compliant"


# --- motor_rated_power（电机功率 <= 400 W） ---
def test_power_at_limit_compliant():
    out = _chk("GB17761-2024-motor_rated_power",
               {"motor_rated_power": {"value": "400", "unit": "W"}})
    assert out["state"] == "compliant"


def test_power_over_limit_non_compliant():
    out = _chk("GB17761-2024-motor_rated_power",
               {"motor_rated_power": {"value": "401", "unit": "W"}})
    assert out["state"] == "non_compliant"


def test_power_kw_unit_converts():
    out = _chk("GB17761-2024-motor_rated_power",
               {"motor_rated_power": {"value": "0.4", "unit": "kW"}})
    assert out["state"] == "compliant"
    assert out["severity"] == "warning"


def test_power_watt_alias():
    out = _chk("GB17761-2024-motor_rated_power",
               {"motor_rated_power": {"value": "400", "unit": "瓦特"}})
    assert out["state"] == "compliant"


# --- 防篡改三项（== true） ---
def test_anti_tamper_all_true_compliant():
    for rule_id, param in (
            ("GB17761-2024-anti_tamper-battery", "anti_tamper_battery_pack"),
            ("GB17761-2024-anti_tamper-controller", "anti_tamper_controller"),
            ("GB17761-2024-anti_tamper-speed_limiter", "anti_tamper_speed_limiter")):
        out = _chk(rule_id, {param: {"value": True}})
        assert out["state"] == "compliant", rule_id


def test_anti_tamper_false_non_compliant():
    for rule_id, param in (
            ("GB17761-2024-anti_tamper-battery", "anti_tamper_battery_pack"),
            ("GB17761-2024-anti_tamper-controller", "anti_tamper_controller"),
            ("GB17761-2024-anti_tamper-speed_limiter", "anti_tamper_speed_limiter")):
        out = _chk(rule_id, {param: {"value": False}})
        assert out["state"] == "non_compliant", rule_id


def test_anti_tamper_missing_not_provided():
    for rule_id, param in (
            ("GB17761-2024-anti_tamper-battery", "anti_tamper_battery_pack"),
            ("GB17761-2024-anti_tamper-controller", "anti_tamper_controller"),
            ("GB17761-2024-anti_tamper-speed_limiter", "anti_tamper_speed_limiter")):
        out = _chk(rule_id, {})
        assert out["state"] == "not_provided", rule_id
        assert out["reason"] == "missing"


def test_over_speed_cutoff_true_compliant():
    out = _chk("GB17761-2024-over_speed_power_cutoff",
               {"over_speed_power_cutoff": {"value": True}})
    assert out["state"] == "compliant"


def test_over_speed_cutoff_false_non_compliant():
    out = _chk("GB17761-2024-over_speed_power_cutoff",
               {"over_speed_power_cutoff": {"value": False}})
    assert out["state"] == "non_compliant"


def test_over_speed_cutoff_string_true_compliant():
    """规则包统一字符串承载：字符串 "true" 与布尔 True 同判。"""
    out = _chk("GB17761-2024-over_speed_power_cutoff",
               {"over_speed_power_cutoff": {"value": "true"}})
    assert out["state"] == "compliant"


# --- 充电器册（GB 42296-2022 空载输出电压 <= 42.4 V） ---
def _charger_ruleset():
    return _ruleset_by_file(docs_copy(), "gb42296-2022.json")


def _chk_charger(rule_id, params):
    rule = _find_rule(_charger_ruleset(), rule_id)
    return ENGINE.check_param(rule, params)


def test_charger_voltage_at_limit_compliant():
    out = _chk_charger("GB42296-2022-charger-no-load-output-voltage",
                       {"charger_no_load_output_voltage": {"value": "42.4", "unit": "V"}})
    assert out["state"] == "compliant"


def test_charger_voltage_over_limit_non_compliant():
    out = _chk_charger("GB42296-2022-charger-no-load-output-voltage",
                       {"charger_no_load_output_voltage": {"value": "42.5", "unit": "V"}})
    assert out["state"] == "non_compliant"


def test_charger_voltage_missing_not_provided():
    out = _chk_charger("GB42296-2022-charger-no-load-output-voltage", {})
    assert out["state"] == "not_provided"
    assert out["reason"] == "missing"


def test_charger_clause_is_verified_554():
    ruleset = _charger_ruleset()
    rule = _find_rule(ruleset, "GB42296-2022-charger-no-load-output-voltage")
    assert rule["clause"] == "5.5.4"
    assert rule["clause_status"] == "verified"


# --- 2018 册（历史车型对照） ---
def test_2018_mass_limit_55():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2018.json")
    rule = _find_rule(ruleset, "GB17761-2018-vehicle_mass")
    out = ENGINE.check_param(rule, {"vehicle_mass": {"value": "56", "unit": "kg"}})
    assert out["state"] == "non_compliant"


def test_2018_mass_limit_compliant():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2018.json")
    rule = _find_rule(ruleset, "GB17761-2018-vehicle_mass")
    out = ENGINE.check_param(rule, {"vehicle_mass": {"value": "55", "unit": "kg"}})
    assert out["state"] == "compliant"


def test_2018_speed_limit():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2018.json")
    rule = _find_rule(ruleset, "GB17761-2018-max_design_speed")
    assert ENGINE.check_param(rule, {"max_design_speed": {"value": "20", "unit": "km/h"}}
                             )["state"] == "compliant"
    assert ENGINE.check_param(rule, {"max_design_speed": {"value": "26", "unit": "km/h"}}
                             )["state"] == "non_compliant"


def test_2018_clauses_carry_pending_status():
    ruleset = _ruleset_by_file(docs_copy(), "gb17761-2018.json")
    for rule in ruleset["rules"]:
        assert rule["clause"] is None
        assert rule["clause_status"] == "pending"


# ==========================================================================
# 十三、跨标准装配逐维度（三维计数与统一结论）
# ==========================================================================
def test_vehicle_dimension_counts_readme():
    result = ENGINE.check_profile(subject(), docs_copy())
    vehicle = next(d for d in result["dimensions"] if d["scope"] == "vehicle")
    assert vehicle["counts"] == {"compliant": 5, "non_compliant": 0,
                                 "not_applicable": 1, "not_provided": 4}


def test_charger_dimension_counts_readme():
    result = ENGINE.check_profile(subject(), docs_copy())
    charger = next(d for d in result["dimensions"] if d["scope"] == "charger")
    assert charger["counts"] == {"compliant": 0, "non_compliant": 0,
                                 "not_applicable": 0, "not_provided": 1}


def test_battery_dimension_zero_effective():
    result = ENGINE.check_profile(subject(), docs_copy())
    battery = next(d for d in result["dimensions"] if d["scope"] == "battery")
    assert battery["effective_rule_count"] == 0
    assert battery["findings"] == []
    assert battery["participates"] is False


def test_overall_not_provided_when_no_violation():
    result = ENGINE.check_profile(subject(), docs_copy())
    assert result["overall"] == "not_provided"


def test_overall_compliant_when_full_profile():
    sub = _param(_param(_param(subject(), "vehicle_mass", "55", "kg"),
                        "plastic_mass_ratio", "5.0", "%"),
                 "nominal_voltage", "48", "V")
    sub = _param(sub, "motor_rated_power", "350", "W")
    sub = _param(sub, "charger_no_load_output_voltage", "42.0", "V")
    result = ENGINE.check_profile(sub, docs_copy())
    assert result["overall"] == "compliant"
    assert result["counts"]["non_compliant"] == 0
    assert result["counts"]["not_provided"] == 0


def test_overall_non_compliant_wins():
    sub = _param(subject(), "max_design_speed", "30", "km/h")
    result = ENGINE.check_profile(sub, docs_copy())
    assert result["overall"] == "non_compliant"


def test_version_2018_profile_checks_2018_ruleset():
    sub = dict(subject(), version_key="GB17761-2018")
    result = ENGINE.check_profile(sub, docs_copy())
    vehicle = next(d for d in result["dimensions"] if d["scope"] == "vehicle")
    assert vehicle["standard"] == "GB 17761-2018"
    assert vehicle["effective_rule_count"] == 2


def test_excluded_rules_carry_rule_ids():
    result = ENGINE.check_profile(subject(), docs_copy())
    excluded_ids = {e["rule_id"] for e in result["excluded_rules"]}
    assert "GB43854-2024-battery-type" in excluded_ids
    assert "GB42296-2022-charger-protection" in excluded_ids


def test_dimension_standards_are_three():
    result = ENGINE.check_profile(subject(), docs_copy())
    standards = [d["standard"] for d in result["dimensions"]]
    assert standards == ["GB 17761-2024", "GB 43854-2024", "GB 42296-2022"]


def test_profile_with_columns_mapping_path():
    """列名参数表经 mapping 归一后判定：精确命中先收编，歧义列名不再覆盖。"""
    sub = {"profile_id": "SYN-EB-COL", "model_design_date": "2025-10-01",
           "params": {"最高车速": {"value": "25", "unit": "km/h"},
                      "车速": {"value": "26", "unit": "km/h"}}}
    normalized = MAPPING.normalize_params(sub["params"])
    sub2 = {"profile_id": "SYN-EB-COL", "model_design_date": "2025-10-01",
            "params": normalized}
    result = ENGINE.check_profile(sub2, docs_copy())
    speed = next(f for f in result["dimensions"][0]["findings"]
                 if f["param"] == "max_design_speed")
    assert speed["state"] == "compliant"
    assert speed["observed"] == "25"


def test_mapping_uncertain_does_not_block():
    """mapping_uncertain 是 NA 不阻断（"没判定"≠"判出违规"）。"""
    sub = {"profile_id": "X", "model_design_date": "2025-10-01",
           "params": {"车速": {"value": "99", "unit": "km/h"}}}
    normalized = MAPPING.normalize_params(sub["params"])
    sub2 = {"profile_id": "X", "model_design_date": "2025-10-01",
            "params": normalized}
    result = ENGINE.check_profile(sub2, docs_copy())
    assert result["overall"] == "not_provided"
    assert result["counts"]["non_compliant"] == 0


# ==========================================================================
# 十四、批量扫描 / 跨轮对账 / 版本差异（来源 M3/M4 判定面）
# ==========================================================================
def _violation_subject():
    return subject(VIOLATION_PATH)


def test_observed_nonpass_violation_profile():
    result = ENGINE.check_profile(_violation_subject(), docs_copy())
    merged = [f for d in result["dimensions"] for f in d["findings"]]
    nonpass = ENGINE.observed_nonpass(merged)
    assert all(state in ("non_compliant", "not_provided")
               for _p, state in nonpass)
    assert ("max_design_speed", "non_compliant") in nonpass
    assert ("charger_no_load_output_voltage", "non_compliant") in nonpass
    assert nonpass == sorted(nonpass)


def test_observed_nonpass_excludes_compliant_and_na():
    result = ENGINE.check_profile(subject(), docs_copy())
    merged = [f for d in result["dimensions"] for f in d["findings"]]
    nonpass = ENGINE.observed_nonpass(merged)
    assert ("max_design_speed", "compliant") not in nonpass
    assert ("vehicle_mass", "not_applicable") not in nonpass


def test_reconcile_same_profile_persistent():
    """同一档案两轮：非通过项全部持续越限。"""
    first = ENGINE.check_profile(_violation_subject(), docs_copy())
    second = ENGINE.check_profile(_violation_subject(), docs_copy())
    out = ENGINE.reconcile_rounds([first], [second])
    assert out["counts"]["persistent"] == len(out["persistent"])
    assert out["counts"]["new_violation"] == 0
    assert out["counts"]["resolved"] == 0
    assert out["persistent"][0][0] == "SYN-EB-VIOLATION"


def test_reconcile_resolved_after_fix():
    """改值判合规 → 已整改（整改动作既包括改值也包括补齐缺失；配对主键 profile_id）。"""
    fixed = _param(_violation_subject(), "max_design_speed", "25", "km/h")
    fixed = _param(fixed, "vehicle_mass", "55", "kg")
    fixed = _param(fixed, "plastic_mass_ratio", "5.0", "%")
    fixed = _param(fixed, "nominal_voltage", "48", "V")
    fixed = _param(fixed, "motor_rated_power", "350", "W")
    fixed = _param(fixed, "charger_no_load_output_voltage", "42.0", "V")
    first = ENGINE.check_profile(_violation_subject(), docs_copy())
    second = ENGINE.check_profile(fixed, docs_copy())
    assert first["profile_id"] == second["profile_id"] == "SYN-EB-VIOLATION"
    out = ENGINE.reconcile_rounds([first], [second])
    assert out["counts"]["resolved"] == 6
    assert out["counts"]["persistent"] == 0
    resolved_params = {p for _pid, p, _s in out["resolved"]}
    assert "max_design_speed" in resolved_params
    assert "charger_no_load_output_voltage" in resolved_params


def test_reconcile_new_violation_appears():
    """上轮合规、本轮越限 → 新增越限。"""
    clean = _param(subject(), "max_design_speed", "25", "km/h")
    worse = _param(subject(), "max_design_speed", "30", "km/h")
    first = ENGINE.check_profile(clean, docs_copy())
    second = ENGINE.check_profile(worse, docs_copy())
    out = ENGINE.reconcile_rounds([first], [second])
    assert out["counts"]["new_violation"] == 1
    assert out["new_violations"][0] == ("SYN-EB-001", "max_design_speed", "non_compliant")


def test_reconcile_profile_disappeared_not_resolved():
    """上轮档案本轮没被扫描 ≠ 已整改（绝不计入整改成效）。"""
    first = ENGINE.check_profile(_violation_subject(), docs_copy())
    other = dict(subject(), profile_id="SYN-EB-OTHER")
    second = ENGINE.check_profile(other, docs_copy())
    out = ENGINE.reconcile_rounds([first], [second])
    assert out["counts"]["resolved"] == 0
    assert out["counts"]["new_violation"] == len(
        ENGINE.observed_nonpass([f for d in second["dimensions"] for f in d["findings"]]))


def test_reconcile_not_provided_state_transition():
    """两轮都非通过但状态变化（越限→未提供）仍算持续越限（含状态变化）。"""
    broken = dict(subject(), profile_id="SYN-EB-001")
    broken["params"] = {"max_design_speed": {"value": "30", "unit": "km/h"}}
    missing = dict(subject(), profile_id="SYN-EB-001")
    missing["params"] = {}
    first = ENGINE.check_profile(broken, docs_copy())
    second = ENGINE.check_profile(missing, docs_copy())
    out = ENGINE.reconcile_rounds([first], [second])
    assert out["counts"]["persistent"] >= 1
    assert out["counts"]["resolved"] == 0


def test_scan_profiles_sorted_and_counted():
    subs = [subject(VIOLATION_PATH), subject(README_PATH)]
    results = ENGINE.scan_profiles(subs, docs_copy())
    assert [r["profile_id"] for r in results] == ["SYN-EB-001", "SYN-EB-VIOLATION"]
    assert results[0]["overall"] == "not_provided"
    assert results[1]["overall"] == "non_compliant"


def test_version_diff_identical_is_unchanged():
    doc = REGISTRY.ruleset_doc("gb17761-2024.json")
    diffs = ENGINE.version_diff_params(doc, copy.deepcopy(doc))
    assert diffs and all(d["kind"] == "unchanged" for d in diffs)


def test_version_diff_tightened_and_relaxed():
    doc = REGISTRY.ruleset_doc("gb17761-2024.json")
    new = copy.deepcopy(doc)
    for rule in new["rules"]:
        if rule["id"] == "GB17761-2024-max_design_speed":
            rule["value"] = "22"
        if rule["id"] == "GB17761-2024-motor_rated_power":
            rule["value"] = "450"
    diffs = ENGINE.version_diff_params(doc, new)
    by_rule = {d["rule_id"]: d for d in diffs}
    assert by_rule["GB17761-2024-max_design_speed"]["kind"] == "tightened"
    assert by_rule["GB17761-2024-motor_rated_power"]["kind"] == "relaxed"


def test_version_diff_added_and_removed():
    doc = REGISTRY.ruleset_doc("gb17761-2024.json")
    new = copy.deepcopy(doc)
    new["rules"] = [r for r in new["rules"]
                    if r["id"] != "GB17761-2024-plastic_mass_ratio"]
    new["rules"].append({
        "id": "GB17761-2024-frame_material", "param": "frame_material",
        "op": "in", "value": ["steel", "aluminum"], "unit": "",
        "clause": "6.2.1", "clause_status": "verified",
        "source": doc["rules"][0]["source"], "status": "verified",
        "verified_on": "2026-10-14",
    })
    diffs = ENGINE.version_diff_params(doc, new)
    by_rule = {d["rule_id"]: d for d in diffs}
    assert by_rule["GB17761-2024-plastic_mass_ratio"]["kind"] == "removed"
    assert by_rule["GB17761-2024-frame_material"]["kind"] == "added"


def test_version_diff_operator_changed():
    doc = REGISTRY.ruleset_doc("gb17761-2024.json")
    new = copy.deepcopy(doc)
    for rule in new["rules"]:
        if rule["id"] == "GB17761-2024-max_design_speed":
            rule["op"] = "<"
    diffs = ENGINE.version_diff_params(doc, new)
    by_rule = {d["rule_id"]: d for d in diffs}
    assert by_rule["GB17761-2024-max_design_speed"]["kind"] == "operator_changed"
    assert by_rule["GB17761-2024-max_design_speed"]["old_op"] == "<="
    assert by_rule["GB17761-2024-max_design_speed"]["new_op"] == "<"


def test_version_diff_in_list_shrink_is_tightened():
    doc = REGISTRY.ruleset_doc("gb17761-2024.json")
    new = copy.deepcopy(doc)
    for rule in new["rules"]:
        if rule["id"] == "GB17761-2024-max_design_speed":
            rule["op"] = "in"
            rule["value"] = ["20", "22", "24", "25"]
    diffs = ENGINE.version_diff_params(doc, new)
    by_rule = {d["rule_id"]: d for d in diffs}
    # op 变化走 operator/value_changed，不硬套方向（跨运算符不比方向）
    assert by_rule["GB17761-2024-max_design_speed"]["kind"] == "value_changed"


def test_2018_vs_2024_diff_detects_relaxation():
    """2018 → 2024：整车质量 55→63（铅酸分支）属放宽方向的历史演变。"""
    old = REGISTRY.ruleset_doc("gb17761-2018.json")
    new = REGISTRY.ruleset_doc("gb17761-2024.json")
    diffs = ENGINE.version_diff_params(old, new)
    kinds = {d["kind"] for d in diffs}
    assert "added" in kinds  # 2024 新增多条分支规则
    assert "removed" in kinds  # 2018 的无条件规则不再出现
    mass = [d for d in diffs if d["rule_id"] == "GB17761-2018-vehicle_mass"]
    assert mass and mass[0]["kind"] == "removed"


def test_reconcile_key_basis_is_profile_id():
    """配对主键 = profile_id（稳定身份键），在结果里显式声明。"""
    first = ENGINE.check_profile(_violation_subject(), docs_copy())
    out = ENGINE.reconcile_rounds([first], [first])
    assert out["key_basis"] == "profile_id"


def test_version_diff_value_changed_no_direction():
    """``==`` 目标改变：方向语义不适用 → 如实记 value_changed（不硬套收紧/放宽）。"""
    doc = REGISTRY.ruleset_doc("gb17761-2024.json")
    new = copy.deepcopy(doc)
    for rule in new["rules"]:
        if rule["id"] == "GB17761-2024-max_design_speed":
            rule["op"] = "=="
            rule["value"] = "24"
    diffs = ENGINE.version_diff_params(doc, new)
    by_rule = {d["rule_id"]: d for d in diffs}
    assert by_rule["GB17761-2024-max_design_speed"]["kind"] == "value_changed"
