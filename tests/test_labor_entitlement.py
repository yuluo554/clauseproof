"""器官 ``labor-entitlement`` 判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源四引擎（经济补偿/赔偿金、加班费、年休假、二倍工资）+ 参数门控 +
条款依据逐条搬，断言落在「计算结果 + 金额 + 口径 + 依据」上。来源判定层
（D1 + D18 机械选 10 文件 / 实跑 156 passed / AST 140）逐文件处置见
``docs/labor-entitlement.md`` §6。

来源仓只读；参数包为随包冻结资产，合成参数包一律在 ``tmp_path`` 内存/临时树注入。
"""

import importlib
import json
import os
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_FLOOR

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from clauseproof import cli as cp_cli  # noqa: E402
from clauseproof.core.basis import Basis, BasisMissing  # noqa: E402
from clauseproof.core.ledger import (  # noqa: E402
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Report,
)

PACK_MOD = importlib.import_module("clauseproof.packs.labor-entitlement")
ENGINE = importlib.import_module("clauseproof.packs.labor-entitlement.engine")
SEV = importlib.import_module("clauseproof.packs.labor-entitlement.engine.severance")
OT = importlib.import_module("clauseproof.packs.labor-entitlement.engine.overtime")
AL = importlib.import_module("clauseproof.packs.labor-entitlement.engine.annual_leave")
DW = importlib.import_module("clauseproof.packs.labor-entitlement.engine.double_wage")
PARAMS = importlib.import_module("clauseproof.packs.labor-entitlement.params")
GATE = importlib.import_module("clauseproof.packs.labor-entitlement.gate")
LAW = importlib.import_module("clauseproof.packs.labor-entitlement.law")
MODEL = importlib.import_module("clauseproof.packs.labor-entitlement.model")
PIPE = importlib.import_module("clauseproof.packs.labor-entitlement.pipeline")
DU = importlib.import_module("clauseproof.packs.labor-entitlement.decimalutil")
ERRS = importlib.import_module("clauseproof.packs.labor-entitlement.errors")
REG = importlib.import_module("clauseproof.packs.labor-entitlement.registry")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "labor-entitlement")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "labor-entitlement")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
README_SAMPLE = os.path.join(SAMPLES, "case-readme.json")
PENDING_SAMPLE = os.path.join(SAMPLES, "case-pending.json")

InputError = ERRS.InputError
ParamCoordinateError = ERRS.ParamCoordinateError
ParamSchemaError = ERRS.ParamSchemaError
GateError = ERRS.GateError
LawBasisError = ERRS.LawBasisError
ComputationError = ERRS.ComputationError


# --------------------------------------------------------------------------
# 夹具
# --------------------------------------------------------------------------
def basis():
    return Basis.from_json(BASIS_PATH)


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def data_dir():
    return DATA_DIR


@pytest.fixture(scope="module")
def ruleset(data_dir):
    return GATE.effective_ruleset(
        PARAMS.load_ruleset("110000", 2025, data_dir=data_dir),
        PARAMS.load_constants(data_dir=data_dir),
        data_dir=data_dir,
    )


@pytest.fixture(scope="module")
def library(data_dir):
    return LAW.load_library(data_dir)


def _facts(ruleset, hire="2024-06-28", terminate="2025-06-28", wages=("12000.00",),
           **overrides):
    payload = {
        "region_code": ruleset.region_code,
        "year": ruleset.year,
        "hire_date": hire,
        "terminate_date": terminate,
        "monthly_wages": [str(value) for value in wages],
        "contract_signed": True,
    }
    payload.update(overrides)
    return MODEL.EmploymentFacts.from_dict(payload)


def _term(ground, notified=None):
    return MODEL.TerminationFacts.from_dict(
        {"ground": ground, "notified_30d_in_advance": notified})


def _overtime_facts(ruleset, **overrides):
    payload = {
        "region_code": ruleset.region_code,
        "year": ruleset.year,
        "hire_date": "2020-03-01",
        "terminate_date": "2025-06-30",
        "monthly_wages": ["12000.00"] * 12,
        "contract_signed": True,
        "cumulative_service_years": "6",
        "annual_leave_taken_days": "0",
        "overtime": [],
    }
    payload.update(overrides)
    return MODEL.EmploymentFacts.from_dict(payload)


def evaluate(subject):
    return tuple(PACK_MOD.evaluate(subject, basis()))


def report(findings):
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject="test", findings=findings)


def by_rule(findings, rule_id):
    return [item for item in findings if item.rule_id == rule_id]


# ==========================================================================
# §一 条文库与随包数据（12）
# ==========================================================================
def test_basis_version_is_data_review_date():
    assert basis().version == REG.VERSION == "2026-10-13"


def test_basis_has_twenty_two_clauses():
    assert len(basis()) == 22


def test_basis_covers_all_law_clause_ids():
    library = LAW.load_library(DATA_DIR)
    for clause_id in library.ids():
        assert basis().clause(clause_id) is not None, clause_id


def test_basis_has_contract_clauses():
    ids = basis().clause_ids()
    for clause_id in ("contract.caliber", "contract.data", "contract.gate",
                      "contract.module", "contract.params"):
        assert clause_id in ids


def test_basis_clause_versions_match_library():
    library = basis()
    for clause_id in library.clause_ids():
        assert library.clause(clause_id).version == library.version


def test_basis_paths_and_text_non_empty():
    library = basis()
    for clause_id in library.clause_ids():
        assert library.clause(clause_id).path.strip()
        assert library.clause(clause_id).text.strip()


def test_basis_law_citation_preserved():
    clause = basis().clause("LCL-47")
    assert clause.path == "中华人民共和国劳动合同法 / 第四十七条"
    assert "经济补偿" in clause.text


def test_manifest_clause_count_matches_library():
    manifest = load_json(os.path.join(DATA_DIR, "manifest.json"))
    assert manifest["clause_count"] == len(basis())
    assert manifest["version"] == REG.VERSION


def test_manifest_sha256_matches_files():
    import hashlib

    manifest = load_json(os.path.join(DATA_DIR, "manifest.json"))
    assert set(manifest["files"]) == set(REG.DATA_FILES)
    for name, record in manifest["files"].items():
        path = os.path.join(DATA_DIR, name)
        assert os.path.getsize(path) == record["bytes"], name
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        assert digest == record["sha256"], name


def test_registry_data_files_cover_directory():
    on_disk = sorted(name for name in os.listdir(DATA_DIR)
                     if name.endswith(".json") and name != "manifest.json")
    assert on_disk == sorted(REG.DATA_FILES)


def test_all_eight_rulesets_present():
    files = PARAMS.list_ruleset_files(DATA_DIR)
    assert len(files) == 8


def test_verified_coordinates_are_the_four_reviewed_ones(data_dir):
    verified = set()
    for path in PARAMS.list_ruleset_files(data_dir):
        match = PARAMS.RULES_FILENAME_RE.match(os.path.basename(path))
        ruleset = PARAMS.load_ruleset(match.group("region"), match.group("year"),
                                      data_dir=data_dir)
        if ruleset.status == "verified":
            verified.add(ruleset.coordinate)
    assert verified == {("110000", 2025), ("110000", 2026),
                        ("310000", 2025), ("310000", 2026)}


# ==========================================================================
# §二 输入模型与 Decimal（16）
# ==========================================================================
BASE = {
    "region_code": "310000",
    "year": 2026,
    "hire_date": "2020-03-01",
    "terminate_date": "2026-06-30",
    "monthly_wages": ["12000.00"] * 12,
    "work_system": "standard",
}


def test_employment_parses_and_decimals():
    facts = MODEL.EmploymentFacts.from_dict(BASE)
    assert facts.hire_date.year == 2020
    assert isinstance(facts.monthly_wages[0], Decimal)


def test_missing_region_code_raises():
    payload = dict(BASE)
    payload.pop("region_code")
    with pytest.raises(InputError):
        MODEL.EmploymentFacts.from_dict(payload)


def test_missing_year_raises():
    payload = dict(BASE)
    payload.pop("year")
    with pytest.raises(InputError):
        MODEL.EmploymentFacts.from_dict(payload)


def test_reversed_dates_raise():
    payload = dict(BASE)
    payload["terminate_date"] = "2019-01-01"
    with pytest.raises(InputError) as exc:
        MODEL.EmploymentFacts.from_dict(payload)
    assert "倒置" in str(exc.value)


def test_negative_wage_raises():
    payload = dict(BASE)
    payload["monthly_wages"] = ["-1"]
    with pytest.raises(InputError):
        MODEL.EmploymentFacts.from_dict(payload)


def test_bad_work_system_raises():
    payload = dict(BASE)
    payload["work_system"] = "flexible"
    with pytest.raises(InputError):
        MODEL.EmploymentFacts.from_dict(payload)


def test_bad_date_format_raises():
    payload = dict(BASE)
    payload["hire_date"] = "2020/3/1 00:00"
    with pytest.raises(InputError):
        MODEL.EmploymentFacts.from_dict(payload)


def test_termination_ground_enum():
    assert MODEL.TerminationFacts.from_dict(
        {"ground": "mutual_agreement"}).ground == "mutual_agreement"
    with pytest.raises(InputError):
        MODEL.TerminationFacts.from_dict({"ground": "fire_him"})


def test_case_input_requires_employment():
    with pytest.raises(InputError):
        MODEL.CaseInput.from_dict({"termination": {"ground": "mutual_agreement"}})


def test_overtime_entries_parse():
    payload = dict(BASE)
    payload["overtime"] = [
        {"date": "2026-05-01", "hours": "8"},
        {"date": "2026-05-10", "hours": "3", "kind": "rest_day"},
    ]
    facts = MODEL.EmploymentFacts.from_dict(payload)
    assert len(facts.overtime) == 2
    assert facts.overtime[0].kind == "auto"
    assert facts.overtime[1].hours == Decimal("3")


def test_overtime_negative_hours_raise():
    payload = dict(BASE)
    payload["overtime"] = [{"date": "2026-05-01", "hours": "-1"}]
    with pytest.raises(InputError):
        MODEL.EmploymentFacts.from_dict(payload)


def test_float_goes_through_str_not_binary():
    value = DU.to_decimal(0.1)
    assert value == Decimal("0.1")
    assert str(value) == "0.1"


def test_bool_is_not_a_number():
    with pytest.raises(TypeError):
        DU.to_decimal(True)


def test_money_quantize_half_up():
    assert DU.money_str(Decimal("1.005")) == "1.01"
    assert DU.money_str(Decimal("1.004")) == "1.00"
    assert DU.money_str(Decimal("2.675")) == "2.68"


def test_json_load_uses_decimal(tmp_path):
    path = tmp_path / "x.json"
    path.write_text('{"a": 0.1, "b": 12345.678}', encoding="utf-8")
    payload = DU.load_json_decimal(str(path))
    assert isinstance(payload["a"], Decimal)
    assert payload["a"] == Decimal("0.1")


def test_empty_string_is_not_a_number():
    with pytest.raises(ValueError):
        DU.to_decimal("  ")


# ==========================================================================
# §三 参数库（16）
# ==========================================================================
def test_load_ruleset_exact_coordinate(data_dir):
    ruleset = PARAMS.load_ruleset("310000", 2026, data_dir=data_dir)
    assert ruleset.coordinate == ("310000", 2026)


def test_unknown_coordinate_raises(data_dir):
    with pytest.raises(ParamCoordinateError):
        PARAMS.load_ruleset("999999", 2026, data_dir=data_dir)


def test_unknown_year_raises(data_dir):
    with pytest.raises(ParamCoordinateError):
        PARAMS.load_ruleset("310000", 2019, data_dir=data_dir)


def test_no_fuzzy_fallback(data_dir):
    with pytest.raises(ParamCoordinateError):
        PARAMS.load_ruleset("31000", 2026, data_dir=data_dir)


def test_list_ruleset_files_sorted(data_dir):
    names = [os.path.basename(item) for item in PARAMS.list_ruleset_files(data_dir)]
    assert names == sorted(names)


def test_validate_rejects_filename_coordinate_mismatch(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    payload = {
        "schema_version": 1, "region_code": "310000", "region_name": "上海市",
        "year": 2026, "status": "pending",
        "params": {
            "social_avg_wage_monthly": {"value": "0.00", "status": "pending"},
            "min_wage_monthly": {"value": "0.00", "status": "pending"},
            "holiday_calendar": {"days": [], "status": "pending"},
        },
    }
    (root / "ruleset-110000-2026.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ParamSchemaError) as exc:
        PARAMS.load_ruleset("110000", 2026, data_dir=str(root))
    assert "不一致" in str(exc.value)


def test_validate_rejects_verified_without_source(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    payload = {
        "schema_version": 1, "region_code": "310000", "region_name": "上海市",
        "year": 2026, "status": "verified",
        "params": {
            "social_avg_wage_monthly": {"value": "0.00", "status": "verified"},
            "min_wage_monthly": {"value": "0.00", "status": "pending"},
            "holiday_calendar": {"days": [], "status": "pending"},
        },
    }
    (root / "ruleset-310000-2026.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ParamSchemaError) as exc:
        PARAMS.load_ruleset("310000", 2026, data_dir=str(root))
    assert "来源" in str(exc.value)


def test_validate_rejects_bad_status(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    payload = {
        "schema_version": 1, "region_code": "310000", "region_name": "上海市",
        "year": 2026,
        "params": {
            "social_avg_wage_monthly": {"value": "0.00", "status": "whatever"},
            "min_wage_monthly": {"value": "0.00", "status": "pending"},
            "holiday_calendar": {"days": [], "status": "pending"},
        },
    }
    (root / "ruleset-310000-2026.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ParamSchemaError) as exc:
        PARAMS.load_ruleset("310000", 2026, data_dir=str(root))
    assert "status" in str(exc.value)


def test_all_repo_rulesets_pass_schema(data_dir):
    for path in PARAMS.list_ruleset_files(data_dir):
        match = PARAMS.RULES_FILENAME_RE.match(os.path.basename(path))
        ruleset = PARAMS.load_ruleset(match.group("region"), match.group("year"),
                                      data_dir=data_dir)
        assert ruleset.region_code == match.group("region")
        assert ruleset.year == int(match.group("year"))


def test_constants_entries_are_flat_and_complete(data_dir):
    paths = set(PARAMS.load_constants(data_dir).entries())
    for required in (
        "severance.cap_multiple_of_social_avg",
        "severance.cap_years",
        "severance.rounding.full_year_threshold_months",
        "severance.avg_wage_months",
        "overtime.rates.workday_extension",
        "overtime.rates.rest_day_no_compensatory",
        "overtime.rates.statutory_holiday",
        "annual_leave.monthly_pay_days",
        "annual_leave.unused_multiple",
        "annual_leave.already_paid_portion",
        "annual_leave.days_per_year",
        "annual_leave.entitlement_tiers[0]",
        "annual_leave.entitlement_tiers[2]",
        "double_wage.start_after_months",
        "double_wage.max_months",
    ):
        assert required in paths, required


def test_constants_verified_requires_basis_and_channel(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    payload = {"schema_version": 1,
               "constants": {"severance": {"cap_years": {"value": 12,
                                                         "status": "verified"}}}}
    (root / "constants.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ParamSchemaError) as exc:
        PARAMS.load_constants(data_dir=str(root))
    assert "basis" in str(exc.value)


def test_regions_require_caliber(data_dir):
    regions = PARAMS.load_regions(data_dir)
    assert regions.codes()
    for item in regions.regions:
        assert item.get("avg_wage_caliber")


def test_regions_get_unknown_raises(data_dir):
    with pytest.raises(ParamCoordinateError):
        PARAMS.load_regions(data_dir).get("000000")


def test_summarize_shape(data_dir):
    summary = PARAMS.summarize(data_dir)
    assert summary["rulesets"]
    assert summary["constants_status"] in ("pending", "verified")
    assert summary["regions"]


def test_missing_data_dir_raises():
    with pytest.raises(FileNotFoundError):
        PARAMS.load_ruleset("310000", 2026, data_dir="Z:/no-such-dir")


# ==========================================================================
# §四 门控（10）
# ==========================================================================
def test_pending_ruleset_is_blocked(data_dir):
    ruleset = PARAMS.load_ruleset("440000", 2026, data_dir=data_dir)
    with pytest.raises(GateError) as exc:
        GATE.effective_ruleset(ruleset, data_dir=data_dir)
    assert "未核对" in str(exc.value)


def test_verified_ruleset_passes_gate(data_dir):
    ruleset = PARAMS.load_ruleset("110000", 2025, data_dir=data_dir)
    assert ruleset.status == "verified"
    effective = GATE.effective_ruleset(ruleset, data_dir=data_dir)
    assert effective.coordinate == ("110000", 2025)
    assert effective.social_avg_wage_monthly() > 0
    assert effective.min_wage_monthly() > 0
    assert effective.holiday_days()


def test_pending_list_covers_ruleset_only(data_dir):
    ruleset = PARAMS.load_ruleset("440000", 2026, data_dir=data_dir)
    constants = PARAMS.load_constants(data_dir)
    pending = GATE.pending_entries(ruleset, constants)
    assert any(item.startswith("ruleset.") for item in pending)
    assert not any(item.startswith("constants.") for item in pending)


def test_allow_pending_preview_reads_values(data_dir):
    ruleset = PARAMS.load_ruleset("310000", 2026, data_dir=data_dir)
    effective = GATE.effective_ruleset(ruleset, allow_pending=True, data_dir=data_dir)
    assert effective.allow_pending is True
    assert effective.severance_cap_years() is not None


def test_gate_passes_when_all_verified(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    ruleset_payload = {
        "schema_version": 1, "region_code": "310000", "region_name": "上海市",
        "year": 2026, "status": "verified",
        "params": {
            "social_avg_wage_monthly": {
                "value": "10000.00", "status": "verified",
                "source": {"publisher": "P", "published_year": 2026,
                           "url": "u", "retrieved_at": "d"}},
            "min_wage_monthly": {
                "value": "2000.00", "status": "verified",
                "source": {"publisher": "P", "published_year": 2026,
                           "url": "u", "retrieved_at": "d"}},
            "holiday_calendar": {
                "days": [], "adjusted_workdays": [], "status": "verified",
                "source": {"publisher": "P", "published_year": 2025,
                           "url": "u", "retrieved_at": "d"}},
        },
    }
    (root / "ruleset-310000-2026.json").write_text(
        json.dumps(ruleset_payload, ensure_ascii=False), encoding="utf-8")
    constants_payload = {
        "schema_version": 1,
        "constants": {
            "severance": {
                "cap_multiple_of_social_avg": {"value": 3, "basis": ["LCL-47"],
                                                "status": "verified",
                                                "source": {"channel": "npc"}},
                "cap_years": {"value": 12, "basis": ["LCL-47"], "status": "verified",
                              "source": {"channel": "npc"}},
                "rounding": {
                    "full_year_threshold_months": {"value": 6, "basis": ["LCL-47"],
                                                    "status": "verified",
                                                    "source": {"channel": "npc"}},
                    "round_up_to_year": {"value": 1, "basis": ["LCL-47"],
                                         "status": "verified",
                                         "source": {"channel": "npc"}},
                    "round_down_to_half_month": {"value": 0.5, "basis": ["LCL-47"],
                                                 "status": "verified",
                                                 "source": {"channel": "npc"}},
                },
                "avg_wage_months": {"value": 12, "basis": ["LCL-47"],
                                    "status": "verified",
                                    "source": {"channel": "npc"}},
            },
            "overtime": {"rates": {
                "workday_extension": {"value": 1.5, "basis": ["LL-44"],
                                      "status": "verified",
                                      "source": {"channel": "npc"}},
                "rest_day_no_compensatory": {"value": 2.0, "basis": ["LL-44"],
                                             "status": "verified",
                                             "source": {"channel": "npc"}},
                "statutory_holiday": {"value": 3.0, "basis": ["LL-44"],
                                      "status": "verified",
                                      "source": {"channel": "npc"}},
            }},
            "annual_leave": {
                "monthly_pay_days": {"value": "21.75", "basis": ["MOHRSS-ORDER-1-ART11"],
                                     "status": "verified",
                                     "source": {"channel": "gov"}},
                "entitlement_tiers": [
                    {"min_service_years": 1, "max_service_years_exclusive": 10,
                     "days": 5, "basis": ["ALR-3"], "status": "verified",
                     "source": {"channel": "gov"}},
                    {"min_service_years": 10, "max_service_years_exclusive": 20,
                     "days": 10, "basis": ["ALR-3"], "status": "verified",
                     "source": {"channel": "gov"}},
                    {"min_service_years": 20, "max_service_years_exclusive": None,
                     "days": 15, "basis": ["ALR-3"], "status": "verified",
                     "source": {"channel": "gov"}},
                ],
                "unused_multiple": {"value": 3.0, "basis": ["ALR-5"],
                                    "status": "verified",
                                    "source": {"channel": "gov"}},
                "already_paid_portion": {"value": 1.0,
                                         "basis": ["MOHRSS-ORDER-1-ART10"],
                                         "status": "verified",
                                         "source": {"channel": "gov"}},
                "days_per_year": {"value": 365, "basis": ["MOHRSS-ORDER-1-ART12"],
                                  "status": "verified",
                                  "source": {"channel": "gov"}},
            },
            "double_wage": {
                "start_after_months": {"value": 1, "basis": ["LCL-82"],
                                       "status": "verified",
                                       "source": {"channel": "npc"}},
                "max_months": {"value": 11, "basis": ["LCL-82"], "status": "verified",
                               "source": {"channel": "npc"}},
            },
        },
    }
    (root / "constants.json").write_text(
        json.dumps(constants_payload, ensure_ascii=False), encoding="utf-8")
    ruleset = PARAMS.load_ruleset("310000", 2026, data_dir=str(root))
    effective = GATE.effective_ruleset(ruleset, data_dir=str(root))
    assert effective.severance_cap_years() == 12
    assert effective.min_wage_monthly() == PARAMS.to_decimal("2000.00")
    assert len(effective.entitlement_tiers()) == 3


def test_engine_takes_effective_ruleset_only(ruleset):
    facts = _facts(ruleset)
    with pytest.raises((AttributeError, TypeError)):
        SEV.compute(facts, _term("mutual_agreement"), {"min_wage_monthly": 1})


def test_gate_error_is_input_error_at_organ_boundary():
    with pytest.raises(ValueError):
        evaluate(load_json(PENDING_SAMPLE))


def test_preview_pending_returns_na_findings():
    subject = load_json(PENDING_SAMPLE)
    subject["preview"] = True
    findings = evaluate(subject)
    assert len(findings) == 4
    assert all(item.verdict == NOT_APPLICABLE for item in findings)


def test_preview_verified_does_not_relax_gate():
    subject = load_json(README_SAMPLE)
    subject["preview"] = True
    findings = evaluate(subject)
    assert all(item.verdict == PASS for item in findings)
    assert all(item.evidence["module"] for item in findings)


def test_pending_entries_are_sorted(data_dir):
    ruleset = PARAMS.load_ruleset("440000", 2026, data_dir=data_dir)
    pending = GATE.pending_entries(ruleset)
    assert pending == sorted(pending)


# ==========================================================================
# §五 条款库（8）
# ==========================================================================
def test_load_library(data_dir):
    library = LAW.load_library(data_dir)
    assert library.ids()
    assert library.has("LCL-47")


def test_clause_citation_and_points(data_dir):
    clause = LAW.load_library(data_dir).get("LCL-47")
    assert clause.law == "中华人民共和国劳动合同法"
    assert clause.article == "第四十七条"
    assert clause.points
    assert clause.citation == "《中华人民共和国劳动合同法》第四十七条"


def test_resolve_unknown_id_raises(data_dir):
    with pytest.raises(LawBasisError):
        LAW.load_library(data_dir).resolve(["NOPE-1"])


def test_engine_referenced_clause_ids_exist(data_dir):
    library = LAW.load_library(data_dir)
    referenced = set()
    for ids in SEV.FORMULA_CLAUSE_IDS.values():
        referenced.update(ids)
    assert not sorted(item for item in referenced if not library.has(item))


def test_validate_rejects_verified_without_channel(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    payload = {"schema_version": 1, "clauses": [
        {"id": "X-1", "law": "某法", "article": "第一条", "points": ["要点"],
         "status": "verified"}]}
    (root / "law-clauses.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ParamSchemaError) as exc:
        LAW.load_library(data_dir=str(root))
    assert "channel" in str(exc.value)


def test_validate_rejects_missing_points(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    payload = {"schema_version": 1, "clauses": [
        {"id": "X-1", "law": "某法", "article": "第一条", "status": "pending"}]}
    (root / "law-clauses.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ParamSchemaError) as exc:
        LAW.load_library(data_dir=str(root))
    assert "points" in str(exc.value)


def test_clause_points_are_short(data_dir):
    for clause in LAW.load_library(data_dir).clauses():
        for point in clause.points:
            assert len(point) <= 200, clause.id


def test_library_has_no_pending_clauses(data_dir):
    assert LAW.load_library(data_dir).pending_ids() == []


# ==========================================================================
# §六 经济补偿/赔偿金（24）
# ==========================================================================
NINE_CASES = (
    ("mutual_agreement", None, "N"),
    ("employee_fault_dismissal", None, "none"),
    ("employer_unilateral_no_fault", True, "N"),
    ("employer_unilateral_no_fault", False, "N+1"),
    ("economic_layoff", None, "N"),
    ("illegal_termination", None, "2N"),
    ("contract_expiry_employer_no_renewal", None, "N"),
    ("employee_resignation_art38", None, "N"),
    ("employee_resignation_voluntary", None, "none"),
)


@pytest.mark.parametrize("ground,notified,expected", NINE_CASES)
def test_determine_formula_nine_cases(ground, notified, expected):
    decision = SEV.determine_formula(_term(ground, notified))
    assert decision["formula"] == expected
    assert decision["basis"] == SEV.FORMULA_CLAUSE_IDS[expected]


def test_confusable_boundaries():
    assert SEV.determine_formula(_term("employer_unilateral_no_fault", False))[
        "formula"] == "N+1"
    assert SEV.determine_formula(_term("employee_fault_dismissal"))[
        "formula"] == "none"
    assert SEV.determine_formula(_term("employee_resignation_art38"))[
        "formula"] == "N"


def test_determine_formula_rejects_unknown_ground():
    with pytest.raises(InputError):
        SEV.determine_formula(_term("no_such_ground"))


def test_all_grounds_have_a_formula():
    for ground in MODEL.TERMINATION_GROUNDS:
        assert ground in SEV.FORMULA_BY_GROUND


@pytest.mark.parametrize("months,expected_years",
                         ((5, "0.5"), (6, "1.0"), (11, "1.0"), (12, "1.0")))
def test_service_years_rounding(ruleset, months, expected_years):
    terminate = date(2025, 6, 28)
    hire = SEV._add_months(terminate, -months)
    assert SEV.service_years_for_compensation(hire, terminate, ruleset) == \
        Decimal(expected_years)


def test_service_years_remainder_threshold(ruleset):
    terminate = date(2025, 6, 28)
    anchor = SEV._add_months(terminate, -12)
    assert SEV.service_years_for_compensation(anchor, terminate, ruleset) == \
        Decimal("1.0")
    assert SEV.service_years_for_compensation(
        date(anchor.year, anchor.month, anchor.day - 14), terminate,
        ruleset) == Decimal("1.0")
    assert SEV.service_years_for_compensation(
        date(anchor.year, anchor.month, anchor.day - 15), terminate,
        ruleset) == Decimal("1.5")


def test_service_years_rejects_inverted_range(ruleset):
    with pytest.raises(ComputationError):
        SEV.service_years_for_compensation(date(2025, 6, 28), date(2024, 1, 1),
                                           ruleset)


def test_cap_switch_point_is_strict_greater(ruleset):
    cap_base = ruleset.social_avg_wage_monthly() * ruleset.severance_cap_multiple()
    cent = Decimal("0.01")
    at = SEV.compute(_facts(ruleset, wages=[cap_base] * 12),
                     _term("mutual_agreement"), ruleset)
    assert at["cap_applied"] is False
    assert at["monthly_wage_avg"] == at["cap_base"]
    plus = SEV.compute(_facts(ruleset, wages=[cap_base + cent] * 12),
                       _term("mutual_agreement"), ruleset)
    assert plus["cap_applied"] is True
    minus = SEV.compute(_facts(ruleset, wages=[cap_base - cent] * 12),
                        _term("mutual_agreement"), ruleset)
    assert minus["cap_applied"] is False


@pytest.mark.parametrize("months,service_years",
                         ((137, "11.5"), (144, "12"), (146, "12.5"), (156, "13")))
def test_cap_twelve_year_limit(ruleset, months, service_years):
    cap_base = ruleset.social_avg_wage_monthly() * ruleset.severance_cap_multiple()
    terminate = date(2025, 6, 28)
    hire = SEV._add_months(terminate, -months)
    capped = SEV.compute(
        _facts(ruleset, hire=hire.isoformat(), terminate=terminate.isoformat(),
               wages=[cap_base + Decimal("0.01")] * 12),
        _term("mutual_agreement"), ruleset)
    assert capped["service_years"] == Decimal(service_years)
    assert capped["years_used"] == min(Decimal(service_years),
                                       ruleset.severance_cap_years())
    uncapped = SEV.compute(
        _facts(ruleset, hire=hire.isoformat(), terminate=terminate.isoformat(),
               wages=[ruleset.min_wage_monthly()] * 12),
        _term("mutual_agreement"), ruleset)
    assert uncapped["cap_applied"] is False
    assert uncapped["years_used"] == Decimal(service_years)


def test_cap_uses_param_driven_base(ruleset):
    cap_base = ruleset.social_avg_wage_monthly() * ruleset.severance_cap_multiple()
    out = SEV.compute(_facts(ruleset, wages=[cap_base + Decimal("1")] * 12),
                      _term("mutual_agreement"), ruleset)
    assert out["cap_base"] == cap_base.quantize(Decimal("0.01"))


def test_min_wage_floor_applied(ruleset):
    floor = ruleset.min_wage_monthly()
    out = SEV.compute(_facts(ruleset, wages=[floor - Decimal("1")] * 12),
                      _term("mutual_agreement"), ruleset)
    assert out["min_wage_applied"] is True
    assert out["basis_wage"] == floor.quantize(Decimal("0.01"))
    assert out["amount"] == (floor * out["years_used"]).quantize(Decimal("0.01"))


def test_min_wage_floor_not_applied_above_floor(ruleset):
    floor = ruleset.min_wage_monthly()
    out = SEV.compute(_facts(ruleset, wages=[floor + Decimal("1")] * 12),
                      _term("mutual_agreement"), ruleset)
    assert out["min_wage_applied"] is False


def test_basis_ids_are_formula_specific_and_resolvable(data_dir):
    library = LAW.load_library(data_dir)
    for ids in SEV.FORMULA_CLAUSE_IDS.values():
        for clause_id in ids:
            assert library.has(clause_id)


def test_compute_attaches_basis_for_each_formula(ruleset):
    grounds = {
        "N": _term("mutual_agreement"),
        "N+1": _term("employer_unilateral_no_fault", False),
        "2N": _term("illegal_termination"),
        "none": _term("employee_resignation_voluntary"),
    }
    expected = {"N": ["LCL-46", "LCL-47"], "N+1": ["LCL-40", "LCL-47"],
                "2N": ["LCL-48", "LCL-87"], "none": []}
    facts = _facts(ruleset, wages=["12000.00"] * 12)
    for formula, term in grounds.items():
        out = SEV.compute(facts, term, ruleset)
        assert out["formula"] == formula
        assert out["basis"] == expected[formula]


def test_n_plus_1_adds_last_month_wage_not_capped_base(ruleset):
    cap_base = ruleset.social_avg_wage_monthly() * ruleset.severance_cap_multiple()
    wages = [cap_base + Decimal("1")] * 11 + [cap_base + Decimal("500")]
    out = SEV.compute(_facts(ruleset, wages=wages),
                      _term("employer_unilateral_no_fault", False), ruleset)
    assert out["formula"] == "N+1"
    assert out["cap_applied"] is True
    assert out["last_month_wage"] == (cap_base + Decimal("500")).quantize(
        Decimal("0.01"))
    n_part = Decimal(out["basis_wage"]) * out["years_used"]
    assert out["amount"] == (n_part + Decimal(out["last_month_wage"])).quantize(
        Decimal("0.01"))


def test_none_formula_yields_zero(ruleset):
    facts = _facts(ruleset, wages=["12000.00"] * 12)
    for ground in ("employee_fault_dismissal", "employee_resignation_voluntary"):
        out = SEV.compute(facts, _term(ground), ruleset)
        assert out["formula"] == "none"
        assert out["amount"] == Decimal("0.00")
        assert out["basis"] == []


def test_compute_two_n_uses_compensation_multiple(ruleset):
    facts = _facts(ruleset, wages=["12000.00"] * 12)
    out = SEV.compute(facts, _term("illegal_termination"), ruleset)
    base = Decimal(out["monthly_wage_avg"])
    want = (base * out["years_used"] * ruleset.compensation_multiple()).quantize(
        Decimal("0.01"))
    assert out["amount"] == want


def test_compute_requires_termination(ruleset):
    with pytest.raises(InputError):
        SEV.compute(_facts(ruleset), None, ruleset)


def test_compute_requires_terminate_date(ruleset):
    with pytest.raises(InputError):
        SEV.compute(_facts(ruleset, terminate=None), _term("mutual_agreement"),
                    ruleset)


def test_compute_requires_wages(ruleset):
    with pytest.raises(InputError):
        SEV.compute(_facts(ruleset, wages=[]), _term("mutual_agreement"), ruleset)


def test_compute_averages_at_most_avg_wage_months(ruleset):
    window = int(ruleset.avg_wage_months())
    out = SEV.compute(
        _facts(ruleset, hire="2020-06-28",
               wages=[Decimal("1000.00")] * 6 + [Decimal("20000.00")] * window),
        _term("mutual_agreement"), ruleset)
    assert out["monthly_wage_avg"] == Decimal("20000.00")


def test_case_input_end_to_end(ruleset):
    case = MODEL.CaseInput.from_dict({
        "employment": {
            "region_code": ruleset.region_code,
            "year": ruleset.year,
            "hire_date": "2020-03-01",
            "terminate_date": "2025-06-30",
            "monthly_wages": ["12000.00"] * 12,
        },
        "termination": {"ground": "mutual_agreement",
                        "notified_30d_in_advance": True},
    })
    out = SEV.compute(case.employment, case.termination, ruleset)
    assert out["formula"] == "N"
    assert Decimal(out["amount"]) > 0
    assert out["steps"]


# ==========================================================================
# §七 加班费（12）
# ==========================================================================
def test_overtime_day_type_rate_mapping_matches_calendar(ruleset):
    holidays = ruleset.holiday_days()
    rest = ruleset.rest_days()
    adjusted = ruleset.adjusted_workdays()
    entries = [
        {"date": holidays[0], "hours": "2"},
        {"date": rest[0], "hours": "2"},
        {"date": adjusted[0], "hours": "2"},
        {"date": "2025-01-02", "hours": "2"},
    ]
    output = OT.compute(_overtime_facts(ruleset, overtime=entries), ruleset)
    by_date = {item["date"]: item for item in output["entries"]}
    assert by_date[holidays[0]]["day_type"] == "statutory_holiday"
    assert by_date[holidays[0]]["rate"] == ruleset.overtime_rate(
        "statutory_holiday")
    for day in (rest[0], adjusted[0]):
        assert by_date[day]["rate"] == ruleset.overtime_rate(
            "rest_day_no_compensatory")
    assert by_date["2025-01-02"]["day_type"] == "workday"
    assert by_date["2025-01-02"]["rate"] == ruleset.overtime_rate(
        "workday_extension")


def test_overtime_rest_day_and_adjusted_workday_share_rate(ruleset):
    rest = ruleset.rest_days()
    adjusted = ruleset.adjusted_workdays()
    output = OT.compute(
        _overtime_facts(ruleset, overtime=[
            {"date": rest[0], "hours": "1"},
            {"date": adjusted[0], "hours": "1"}]),
        ruleset)
    rates = {item["day_type"]: item["rate"] for item in output["entries"]}
    assert rates["rest_day"] == rates["adjusted_workday"]


def test_overtime_hourly_base_from_monthly_wage_and_min_wage_floor(ruleset):
    base = ruleset.min_wage_monthly() - Decimal("1")
    low = OT.compute(_overtime_facts(
        ruleset, monthly_wages=[str(base)] * 12,
        overtime=[{"date": "2025-01-02", "hours": "1"}]), ruleset)
    assert low["min_wage_applied"] is True
    expected = ruleset.min_wage_monthly() / ruleset.monthly_pay_days() \
        / ruleset.overtime_standard_daily_hours()
    assert low["hourly_base"] == expected


def test_overtime_explicit_kind_overrides_calendar(ruleset):
    output = OT.compute(_overtime_facts(
        ruleset, overtime=[{"date": "2025-01-02", "hours": "1",
                            "kind": "statutory_holiday"}]), ruleset)
    item = output["entries"][0]
    assert item["day_type_source"] == "explicit"
    assert item["rate"] == ruleset.overtime_rate("statutory_holiday")


def test_overtime_basis_ids_resolvable(ruleset, library):
    output = OT.compute(_overtime_facts(
        ruleset, overtime=[{"date": "2025-01-02", "hours": "1"}]), ruleset)
    assert output["basis"] == ["LL-44", "LL-36"]
    assert all(library.has(item) for item in output["basis"])


def test_overtime_empty_entries_yields_zero(ruleset):
    output = OT.compute(_overtime_facts(ruleset, overtime=[]), ruleset)
    assert output["total"] == Decimal("0.00")
    assert output["entries"] == []


def test_overtime_requires_wages(ruleset):
    with pytest.raises(InputError):
        OT.compute(_overtime_facts(ruleset, monthly_wages=[]), ruleset)


def test_overtime_entry_amount_is_hourly_times_hours_times_rate(ruleset):
    output = OT.compute(_overtime_facts(
        ruleset, overtime=[{"date": "2025-01-02", "hours": "3"}]), ruleset)
    item = output["entries"][0]
    assert item["entry_amount"] == (
        output["hourly_base"] * Decimal("3") * item["rate"]).quantize(
            Decimal("0.01"))


def test_overtime_work_system_is_recorded(ruleset):
    output = OT.compute(_overtime_facts(
        ruleset, work_system="comprehensive",
        overtime=[{"date": "2025-01-02", "hours": "1"}]), ruleset)
    assert output["work_system"] == "comprehensive"


def test_overtime_negative_hours_rejected_at_model():
    with pytest.raises(InputError):
        MODEL.EmploymentFacts.from_dict({
            "region_code": "110000", "year": 2025, "hire_date": "2024-01-01",
            "monthly_wages": ["12000.00"],
            "overtime": [{"date": "2025-01-02", "hours": "-1"}]})


def test_overtime_bad_kind_rejected_at_model():
    with pytest.raises(InputError):
        MODEL.EmploymentFacts.from_dict({
            "region_code": "110000", "year": 2025, "hire_date": "2024-01-01",
            "monthly_wages": ["12000.00"],
            "overtime": [{"date": "2025-01-02", "hours": "1", "kind": "holiday"}]})


def test_overtime_unknown_date_is_workday(ruleset):
    output = OT.compute(_overtime_facts(
        ruleset, overtime=[{"date": "2025-01-02", "hours": "1"}]), ruleset)
    assert output["entries"][0]["day_type"] == "workday"


# ==========================================================================
# §八 年休假（11）
# ==========================================================================
def test_annual_leave_tier_selection_at_boundaries(ruleset):
    tiers = {tier["min_service_years"]: tier["days"]
             for tier in ruleset.entitlement_tiers()}
    for service in (Decimal("1"), Decimal("10"), Decimal("20")):
        output = AL.compute(_overtime_facts(
            ruleset, cumulative_service_years=str(service)), ruleset)
        assert output["entitlement_days"] == tiers[service]


def test_annual_leave_proration_and_floor_rounding(ruleset):
    output = AL.compute(_overtime_facts(
        ruleset, terminate_date="2025-03-01", cumulative_service_years="6",
        annual_leave_taken_days="0"), ruleset)
    elapsed = (date(2025, 3, 1) - date(2025, 1, 1)).days + 1
    expected = Decimal(elapsed) / ruleset.days_per_year() * output[
        "entitlement_days"]
    assert output["prorated_days"] == expected
    assert output["unused_days"] == expected.to_integral_value(
        rounding=ROUND_FLOOR)


def test_annual_leave_floor_applies_after_deducting_taken_days(ruleset):
    output = AL.compute(_overtime_facts(
        ruleset, terminate_date="2025-03-01", cumulative_service_years="6",
        annual_leave_taken_days="1"), ruleset)
    raw = output["prorated_days"] - Decimal("1")
    want = max(Decimal("0"), raw.to_integral_value(rounding=ROUND_FLOOR))
    assert output["unused_days"] == want


def test_annual_leave_unused_days_never_negative(ruleset):
    output = AL.compute(_overtime_facts(
        ruleset, terminate_date="2025-01-02", annual_leave_taken_days="10"),
        ruleset)
    assert output["unused_days"] == Decimal("0")
    assert output["additional_due"] == Decimal("0.00")


def test_annual_leave_additional_due_is_unused_minus_already_paid(ruleset):
    output = AL.compute(_overtime_facts(
        ruleset, terminate_date="2025-12-31", cumulative_service_years="6",
        annual_leave_taken_days="0"), ruleset)
    want = output["daily_wage"] * output["unused_days"] * (
        ruleset.unused_multiple() - ruleset.already_paid_portion())
    assert output["additional_due"] == want.quantize(Decimal("0.01"))


def test_annual_leave_requires_terminate_date(ruleset):
    with pytest.raises(InputError):
        AL.compute(_overtime_facts(ruleset, terminate_date=None), ruleset)


def test_annual_leave_basis_ids_resolvable(ruleset, library):
    output = AL.compute(_overtime_facts(ruleset), ruleset)
    assert all(library.has(item) for item in output["basis"])
    for expected in ("ALR-3", "ALR-5", "MOHRSS-ORDER-1-ART10",
                     "MOHRSS-ORDER-1-ART11", "MOHRSS-ORDER-1-ART12"):
        assert expected in output["basis"]


def test_annual_leave_requires_wages(ruleset):
    with pytest.raises(InputError):
        AL.compute(_overtime_facts(ruleset, monthly_wages=[]), ruleset)


def test_annual_leave_zero_entitlement_below_one_year(ruleset):
    output = AL.compute(_overtime_facts(
        ruleset, cumulative_service_years="0.5"), ruleset)
    assert output["entitlement_days"] == Decimal("0")


def test_annual_leave_prorated_keeps_full_precision(ruleset):
    output = AL.compute(_overtime_facts(
        ruleset, terminate_date="2025-03-01", cumulative_service_years="6"),
        ruleset)
    assert output["prorated_days"] == output["prorated_days"]
    assert output["prorated_days"] > Decimal("0")


def test_annual_leave_payable_uses_unused_multiple(ruleset):
    output = AL.compute(_overtime_facts(
        ruleset, terminate_date="2025-12-31", cumulative_service_years="6"),
        ruleset)
    want = output["daily_wage"] * output["unused_days"] * \
        ruleset.unused_multiple()
    assert output["payable_total"] == want.quantize(Decimal("0.01"))


# ==========================================================================
# §九 二倍工资（10）
# ==========================================================================
def test_double_wage_signed_contract_yields_zero(ruleset):
    output = DW.compute(_overtime_facts(ruleset, contract_signed=True), ruleset)
    assert output["signed"] is True
    assert output["months"] == 0
    assert output["total_difference"] == Decimal("0.00")


def test_double_wage_starts_day_after_full_month(ruleset):
    start_after = int(ruleset.double_wage_start_after_months())
    for hire in ("2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31"):
        output = DW.compute(_overtime_facts(
            ruleset, hire_date=hire, terminate_date="2025-06-28",
            contract_signed=False), ruleset)
        hire_date = date.fromisoformat(hire)
        total = hire_date.month - 1 + start_after
        year = hire_date.year + total // 12
        month = total % 12 + 1
        days_in_target = (date(year + (month // 12), month % 12 + 1, 1)
                          - date(year, month, 1)).days
        anniversary = date(year, month, min(hire_date.day, days_in_target))
        assert output["start_date"] == (anniversary + timedelta(days=1)).isoformat()


def test_double_wage_capped_at_max_months(ruleset):
    output = DW.compute(_overtime_facts(
        ruleset, hire_date="2020-03-01", terminate_date="2025-06-30",
        contract_signed=False), ruleset)
    assert Decimal(output["months"]) == ruleset.double_wage_max_months()


def test_double_wage_terminate_before_start_yields_zero(ruleset):
    output = DW.compute(_overtime_facts(
        ruleset, hire_date="2025-06-01", terminate_date="2025-06-15",
        contract_signed=False), ruleset)
    assert output["months"] == 0
    assert output["total_difference"] == Decimal("0.00")


def test_double_wage_total_is_base_times_months_times_multiple(ruleset):
    output = DW.compute(_overtime_facts(
        ruleset, hire_date="2024-07-28", terminate_date="2025-06-28",
        contract_signed=False), ruleset)
    want = Decimal(output["monthly_wage"]) * Decimal(output["months"]) \
        * ruleset.double_wage_difference_multiple()
    assert output["total_difference"] == want.quantize(Decimal("0.01"))


def test_double_wage_basis_ids_resolvable(ruleset, library):
    output = DW.compute(_overtime_facts(ruleset, contract_signed=False), ruleset)
    assert output["basis"] == ["LCL-82"]
    assert library.has("LCL-82")


def test_double_wage_requires_wages_when_unsigned(ruleset):
    with pytest.raises(InputError):
        DW.compute(_overtime_facts(ruleset, monthly_wages=[],
                                   contract_signed=False), ruleset)


def test_double_wage_monthly_detail_matches_months(ruleset):
    output = DW.compute(_overtime_facts(
        ruleset, hire_date="2024-07-28", terminate_date="2025-06-28",
        contract_signed=False), ruleset)
    assert len(output["monthly_detail"]) == output["months"]


def test_double_wage_detail_rows_are_quantized(ruleset):
    output = DW.compute(_overtime_facts(
        ruleset, hire_date="2024-07-28", terminate_date="2025-06-28",
        contract_signed=False), ruleset)
    for row in output["monthly_detail"]:
        assert str(row["difference"]) == str(row["due"])


def test_double_wage_end_capped_at_hard_end(ruleset):
    output = DW.compute(_overtime_facts(
        ruleset, hire_date="2024-07-28", terminate_date="2026-12-31",
        contract_signed=False), ruleset)
    assert output["end_date"] == "2025-07-28"


# ==========================================================================
# §十 编排与端到端（16）
# ==========================================================================
def test_pipeline_modules_contract():
    assert PIPE.MODULES == ("severance", "overtime", "annual_leave", "double_wage")


def test_pipeline_defaults_to_all_modules():
    case = PIPE.build_case(load_json(README_SAMPLE))
    request = PIPE.build_request(case)
    assert request.modules == PIPE.MODULES
    assert request.preview is False


def test_pipeline_is_deterministic():
    subject = load_json(README_SAMPLE)
    first = PIPE.compute_full_calc(PIPE.build_request(PIPE.build_case(subject)))
    second = PIPE.compute_full_calc(PIPE.build_request(PIPE.build_case(subject)))
    assert first.modules == second.modules


def test_pipeline_amounts_match_source_readme():
    result = PIPE.compute_full_calc(
        PIPE.build_request(PIPE.build_case(load_json(README_SAMPLE))))
    assert result.modules["severance"]["amount"] == Decimal("79029.17")
    assert result.modules["overtime"]["amount"] == Decimal("2096.26")
    assert result.modules["annual_leave"]["amount"] == Decimal("0.00")
    assert result.modules["double_wage"]["amount"] == Decimal("0.00")


def test_pipeline_only_severance_selection():
    subject = load_json(README_SAMPLE)
    subject["modules"] = ["severance"]
    findings = evaluate(subject)
    assert [item.rule_id for item in findings] == ["labor.severance"]


def test_pipeline_missing_termination_skips_severance():
    subject = load_json(README_SAMPLE)
    subject.pop("termination")
    findings = evaluate(subject)
    severance = by_rule(findings, "labor.severance")
    assert severance[0].verdict == NOT_APPLICABLE
    assert severance[0].evidence["skipped"] is True


def test_organ_readme_sample_four_pass():
    findings = evaluate(load_json(README_SAMPLE))
    assert len(findings) == 4
    assert all(item.verdict == PASS for item in findings)
    assert report(findings).exit_code() == 0


def test_organ_readme_amounts_in_evidence():
    findings = evaluate(load_json(README_SAMPLE))
    evidence = {item.rule_id: item.evidence for item in findings}
    assert evidence["labor.severance"]["amount"] == "79029.17"
    assert evidence["labor.overtime"]["amount"] == "2096.26"


def test_organ_severance_anchor_is_formula_clause():
    findings = evaluate(load_json(README_SAMPLE))
    severance = by_rule(findings, "labor.severance")[0]
    assert severance.anchor.clause_id == "LCL-47"


def test_organ_other_module_anchors():
    findings = evaluate(load_json(README_SAMPLE))
    assert by_rule(findings, "labor.overtime")[0].anchor.clause_id == "LL-44"
    assert by_rule(findings, "labor.annual_leave")[0].anchor.clause_id == "ALR-3"
    assert by_rule(findings, "labor.double_wage")[0].anchor.clause_id == "LCL-82"


def test_organ_findings_carry_steps():
    findings = evaluate(load_json(README_SAMPLE))
    assert all(item.evidence["steps"] for item in findings)


def test_organ_findings_carry_basis_ids():
    findings = evaluate(load_json(README_SAMPLE))
    assert "LCL-46" in by_rule(findings, "labor.severance")[0].evidence["basis_ids"]


def test_organ_pending_sample_raises_value_error():
    with pytest.raises(ValueError) as exc:
        evaluate(load_json(PENDING_SAMPLE))
    assert "门控" in str(exc.value)


def test_organ_unknown_module_rejected():
    subject = load_json(README_SAMPLE)
    subject["modules"] = ["severance", "bonus"]
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_unknown_top_level_key_rejected():
    subject = load_json(README_SAMPLE)
    subject["future_field"] = 1
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_missing_employment_rejected():
    with pytest.raises(ValueError):
        evaluate({"termination": {"ground": "mutual_agreement"}})


def test_organ_wrong_basis_version_raises_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(load_json(README_SAMPLE), Basis.empty("0"))


def test_organ_missing_clause_raises_basis_missing():
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate(load_json(README_SAMPLE),
                          Basis(version=REG.VERSION, clauses=[]))


# ==========================================================================
# §十一 CLI 契约（5）
# ==========================================================================
def test_cli_readme_returns_ok():
    assert cp_cli.main(["check", SLUG, "--input", README_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_pending_returns_input():
    assert cp_cli.main(["check", SLUG, "--input", PENDING_SAMPLE,
                        "--basis", BASIS_PATH]) == 2


def test_cli_missing_basis_returns_contract():
    assert cp_cli.main(["check", SLUG, "--input", README_SAMPLE]) == 3


def test_cli_bad_input_returns_input(tmp_path):
    subject = load_json(README_SAMPLE)
    subject.pop("employment")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(subject, ensure_ascii=False), encoding="utf-8")
    assert cp_cli.main(["check", SLUG, "--input", str(path),
                        "--basis", BASIS_PATH]) == 2


def test_cli_preview_pending_returns_ok(tmp_path):
    subject = load_json(PENDING_SAMPLE)
    subject["preview"] = True
    path = tmp_path / "preview.json"
    path.write_text(json.dumps(subject, ensure_ascii=False), encoding="utf-8")
    assert cp_cli.main(["check", SLUG, "--input", str(path),
                        "--basis", BASIS_PATH]) == 0


# ==========================================================================
# §十二 口径锚点与数据契约（5）
# ==========================================================================
def test_severance_n_plus_1_anchor_is_lcl40():
    subject = load_json(README_SAMPLE)
    subject["modules"] = ["severance"]
    subject["termination"] = {"ground": "employer_unilateral_no_fault",
                              "notified_30d_in_advance": False}
    findings = evaluate(subject)
    assert findings[0].anchor.clause_id == "LCL-40"
    assert findings[0].evidence["formula"] == "N+1"


def test_severance_two_n_anchor_is_lcl87():
    subject = load_json(README_SAMPLE)
    subject["modules"] = ["severance"]
    subject["termination"] = {"ground": "illegal_termination"}
    findings = evaluate(subject)
    assert findings[0].anchor.clause_id == "LCL-87"
    assert findings[0].evidence["formula"] == "2N"


def test_severance_none_anchor_is_caliber_contract():
    subject = load_json(README_SAMPLE)
    subject["modules"] = ["severance"]
    subject["termination"] = {"ground": "employee_fault_dismissal"}
    findings = evaluate(subject)
    assert findings[0].anchor.clause_id == "contract.caliber"
    assert findings[0].evidence["amount"] == "0.00"


def test_basis_covers_every_module_clause():
    library = basis()
    for clause_id in ("LCL-47", "LL-44", "ALR-3", "LCL-82", "contract.caliber",
                      "contract.gate", "contract.module"):
        assert library.anchor(clause_id).path


def test_data_source_clause_mentions_byte_identical():
    text = basis().clause("contract.data").text
    assert "逐字节" in text
    assert "sha256" in text