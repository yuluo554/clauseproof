"""器官 ``occupational-surveillance`` 判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源判定面（监护矩阵 / 覆盖度四态 / 周期判定 / 版本锚定 / 版本对照 /
status 门控 / schema）逐条搬，断言落在「判定结果 + 依据 + 证据」上。来源判定层
（D1 + D18 机械选 9 文件 / 实跑 190 passed / AST 190）逐文件处置见
``docs/occupational-surveillance.md`` §6。

来源仓只读；合成规则集一律**内存注入**，绝不写入真实标准内容。
"""

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

from clauseproof import cli as cp_cli  # noqa: E402
from clauseproof.core.basis import Basis, BasisMissing  # noqa: E402
from clauseproof.core.ledger import (  # noqa: E402
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Report,
)

PACK_MOD = importlib.import_module("clauseproof.packs.occupational-surveillance")
MODEL = importlib.import_module("clauseproof.packs.occupational-surveillance.model")
MATRIX = importlib.import_module("clauseproof.packs.occupational-surveillance.engine.matrix")
COVERAGE = importlib.import_module("clauseproof.packs.occupational-surveillance.engine.coverage")
PERIOD = importlib.import_module("clauseproof.packs.occupational-surveillance.engine.period")
COMPARE = importlib.import_module("clauseproof.packs.occupational-surveillance.engine.compare")
PIPE = importlib.import_module("clauseproof.packs.occupational-surveillance.pipeline")
SCHEMA = importlib.import_module("clauseproof.packs.occupational-surveillance.rules.schema")
LOADER = importlib.import_module("clauseproof.packs.occupational-surveillance.rules.loader")
GATE = importlib.import_module("clauseproof.packs.occupational-surveillance.rules.gate")
VERSION = importlib.import_module("clauseproof.packs.occupational-surveillance.rules.version")
ERRS = importlib.import_module("clauseproof.packs.occupational-surveillance.errors")
REG = importlib.import_module("clauseproof.packs.occupational-surveillance.registry")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "occupational-surveillance")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "occupational-surveillance")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
POSITION_SAMPLE = os.path.join(SAMPLES, "position-benzene.json")
RECORD_SAMPLE = os.path.join(SAMPLES, "record-partial.json")
FULL_SAMPLE = os.path.join(SAMPLES, "case-full.json")
COMPARE_SAMPLE = os.path.join(SAMPLES, "compare-only.json")

InputError = ERRS.InputError
GateBlocked = ERRS.GateBlocked
MissingInputError = ERRS.MissingInputError
AmbiguousYearError = ERRS.AmbiguousYearError

SYN = "SYNTHETIC-"


# --------------------------------------------------------------------------
# 合成夹具（与来源 tests/helpers 同纪律：synthetic=true、出处带 SYNTHETIC-）
# --------------------------------------------------------------------------
def _src(clause):
    return {"doc": SYN + "TESTSPEC", "clause": clause, "url": "",
            "fetched": "2026-10-14"}


def _item(code, clause="9.9.9"):
    return {"item_code": code, "item_name": SYN + "项目 " + code,
            "status": "verified", "basis": SYN + "测试", "source": _src(clause)}


def make_factor(code="T_FACTOR", fid="5.9.0", months=12, required=("T_ITEM_1",),
                kind="always", threshold=None, comparator=">=", unit="mg/m3",
                factor_status="verified", exam_status="verified",
                period_status="verified"):
    elig = {"kind": kind, "threshold": threshold if kind == "threshold" else None,
            "unit": unit, "comparator": comparator if kind == "threshold" else "",
            "status": factor_status, "basis": SYN + "一律纳入监护",
            "source": _src(fid)}
    exam_required = [_item(c, fid) for c in required] if exam_status == "verified" else []
    exams = {
        key: {"required_items": list(exam_required), "supplementary_items": [],
              "optional_items": [], "status": exam_status,
              "basis": SYN + "测试", "source": _src(fid)}
        for key in ("pre_placement", "periodic", "post_placement", "emergency")
    }
    period_kind = "months" if period_status == "verified" else "pending"
    return {"factor_id": fid, "factor_code": code,
            "factor_name": SYN + "因素 " + code, "chapter": fid.split(".")[0],
            "category": "chemical", "eligibility": elig, "target_diseases": [],
            "exposed_population": "", "examinations": exams,
            "period": {"kind": period_kind,
                       "value": months if period_status == "verified" else None,
                       "status": period_status, "basis": SYN + "测试", "note": "",
                       "source": _src(fid)},
            "status": factor_status, "source": _src(fid)}


def make_ruleset(factors=None, ruleset_id="SYN-TEST", effective_from="2026-08-01",
                 optional_items_policy="any"):
    return {"schema_version": "1.0", "synthetic": True, "ruleset_id": ruleset_id,
            "basis": {"doc_code": SYN + "TESTSPEC", "doc_title": SYN + "合成测试规范",
                      "issuer": "", "doc_number": SYN + "TEST",
                      "published": "2026-01-01", "effective_from": effective_from,
                      "replaces": "", "url": "", "fetched": "2026-10-14"},
            "chapters": ["5"], "optional_items_policy": optional_items_policy,
            "alias_map": {"status": "pending", "source": _src("9"), "map": {}},
            "factors": list(factors or [make_factor()])}


def make_manifest(rulesets=None, cutover=None):
    entries = []
    for rid, filename, count in (rulesets or [("SYN-TEST", "ruleset.json", 1)]):
        entries.append({"ruleset_id": rid, "file": filename, "sha256": "",
                        "factor_count": count,
                        "status_counts": {"verified": 0, "pending": 0,
                                          "input_required": 0}})
    return {"schema_version": "1.0", "synthetic": True, "generated_by": "tests",
            "cutover": cutover or {"date": "2026-08-01", "before": "SYN-OLD",
                                   "after": "SYN-NEW"},
            "rulesets": entries,
            "benchmark_thresholds": {"matrix_accuracy_min": 1.0,
                                     "coverage_accuracy_min": 1.0,
                                     "compare_accuracy_min": 1.0,
                                     "false_positive_max": 0,
                                     "max_runtime_seconds": 30.0}}


def make_record(record_id="REC-1", employee_id="SYN-A-001", factor_code="T_FACTOR",
                exam_date="2026-09-15", exam_type="periodic",
                items=("T_ITEM_1",), last_exam_date=None,
                conclusion_code="normal", position_id="POS-1"):
    obj = {"record_id": record_id, "employee_id": employee_id,
           "employee_name": SYN + "人员 " + employee_id,
           "position_id": position_id, "factor_code": factor_code,
           "exam_date": exam_date, "exam_type": exam_type, "items": list(items),
           "conclusion_code": conclusion_code, "notified_suspected": False}
    if last_exam_date:
        obj["last_exam_date"] = last_exam_date
    return obj


def _plan(factors, codes, exam_date="2026-09-15", exposure=None):
    eff = GATE.effective_ruleset(LOADER.Ruleset(make_ruleset(factors)), "plan",
                                 required_factor_ids=codes)
    refs = [MODEL.FactorRef(code, exposure_value=exposure) for code in codes]
    profile = MODEL.PositionProfile(position_id="POS-1", exam_date=exam_date,
                                    factors=refs)
    return MATRIX.compute_plan(profile, eff)


def _check(factors, record_obj, last=None, alias_map=None):
    code = record_obj["factor_code"]
    eff = GATE.effective_ruleset(LOADER.Ruleset(make_ruleset(factors)), "check",
                                 required_factor_ids=[code])
    profile = MODEL.PositionProfile(position_id="POS-1",
                                    exam_date=record_obj["exam_date"],
                                    factors=[MODEL.FactorRef(code)])
    plan = MATRIX.compute_plan(profile, eff)
    record = MODEL.HealthRecord.from_dict(record_obj)
    return COVERAGE.check_record(record, plan, alias_map=alias_map,
                                 last_exam_date=last)


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


# ==========================================================================
# §一 条文库与随包数据（14）
# ==========================================================================
def test_basis_version_is_knowledge_date():
    assert basis().version == REG.VERSION == "2026-10-14"


def test_basis_has_103_clauses():
    assert len(basis()) == 103


def test_basis_contains_every_factor_clause():
    knowledge = load_json(os.path.join(DATA_DIR, "knowledge-clauses.json"))
    for entry in knowledge["clauses"]:
        assert basis().clause(entry["factor_id"]) is not None, entry["factor_id"]


def test_basis_has_contract_clauses():
    ids = basis().clause_ids()
    for clause_id in ("contract.version", "contract.gate", "contract.verdict",
                      "contract.period", "contract.compare", "contract.module"):
        assert clause_id in ids


def test_basis_clause_versions_match_library():
    library = basis()
    for clause_id in library.clause_ids():
        assert library.clause(clause_id).version == library.version


def test_basis_factor_path_contains_doc_and_section():
    clause = basis().clause("5.19")
    assert clause.path == "GBZ 188—2025 / 第 5.19 节"
    assert "苯" in clause.text


def test_basis_paths_non_empty():
    library = basis()
    for clause_id in library.clause_ids():
        assert library.clause(clause_id).path.strip()
        assert library.clause(clause_id).text.strip()


def test_manifest_clause_count_matches():
    manifest = load_json(os.path.join(DATA_DIR, "manifest.json"))
    assert manifest["clause_count"] == len(basis())


def test_manifest_sha256_matches_files():
    import hashlib

    manifest = load_json(os.path.join(DATA_DIR, "manifest.json"))
    assert set(manifest["files"]) == set(REG.DATA_FILES)
    for name, record in manifest["files"].items():
        path = os.path.join(DATA_DIR, name)
        assert os.path.getsize(path) == record["bytes"], name
        assert hashlib.sha256(open(path, "rb").read()).hexdigest() == \
            record["sha256"], name


def test_registry_data_files_cover_directory():
    on_disk = sorted(name for name in os.listdir(DATA_DIR)
                     if name.endswith(".json") and name != "manifest.json")
    assert on_disk == sorted(REG.DATA_FILES)


def test_ruleset_2025_sha256_matches_source_manifest():
    manifest = load_json(os.path.join(DATA_DIR, "rules-manifest.json"))
    entry = next(item for item in manifest["rulesets"]
                 if item["ruleset_id"] == "GBZ188-2025")
    assert LOADER.file_sha256(os.path.join(DATA_DIR, entry["file"])) == entry["sha256"]


def test_ruleset_2014_sha256_matches_source_manifest():
    manifest = load_json(os.path.join(DATA_DIR, "rules-manifest.json"))
    entry = next(item for item in manifest["rulesets"]
                 if item["ruleset_id"] == "GBZ188-2014")
    assert LOADER.file_sha256(os.path.join(DATA_DIR, entry["file"])) == entry["sha256"]


def test_manifest_cutover_is_2025_effective_date():
    manifest = LOADER.load_manifest(DATA_DIR)
    assert manifest.cutover_date_text == "2026-08-01"
    assert manifest.cutover["before"] == "GBZ188-2014"
    assert manifest.cutover["after"] == "GBZ188-2025"


def test_ruleset_2025_status_counts_are_partial():
    ruleset = LOADER.load_ruleset("GBZ188-2025", DATA_DIR)
    counts = ruleset.status_counts()
    assert counts["verified"] == 2520
    assert counts["pending"] == 90
    assert counts["input_required"] == 22


# ==========================================================================
# §二 schema 校验（24）
# ==========================================================================
def test_schema_accepts_synthetic_ruleset():
    assert SCHEMA.validate_ruleset(make_ruleset())["ruleset_id"] == "SYN-TEST"


def test_schema_rejects_non_object():
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset([])


def test_schema_rejects_wrong_schema_version():
    obj = make_ruleset()
    obj["schema_version"] = "2.0"
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(obj)


def test_schema_rejects_missing_ruleset_id():
    obj = make_ruleset()
    obj["ruleset_id"] = ""
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(obj)


def test_schema_rejects_bad_package_status():
    obj = make_ruleset()
    obj["status"] = "full"
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(obj)


def test_schema_rejects_synthetic_real_doc_code():
    obj = make_ruleset()
    obj["basis"]["doc_code"] = "GBZ 188—2025"
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(obj)


def test_schema_rejects_synthetic_issuer():
    obj = make_ruleset()
    obj["basis"]["issuer"] = "国家卫生健康委员会"
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(obj)


def test_schema_rejects_pending_effective_from_with_value():
    obj = make_ruleset()
    obj["basis"]["effective_from_status"] = "pending"
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(obj)


def test_schema_accepts_pending_effective_from_when_empty():
    obj = make_ruleset()
    obj["basis"]["effective_from_status"] = "pending"
    obj["basis"]["effective_from"] = ""
    assert SCHEMA.validate_ruleset(obj)


def test_schema_rejects_duplicate_factor_id():
    obj = make_ruleset([make_factor(), make_factor(code="T2")])
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(obj)


def test_schema_rejects_duplicate_factor_code():
    obj = make_ruleset([make_factor(), make_factor(fid="5.9.1")])
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(obj)


def test_schema_rejects_bad_category():
    factor = make_factor()
    factor["category"] = "noise"
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor]))


def test_schema_rejects_bad_factor_id():
    factor = make_factor()
    factor["factor_id"] = "5-9"
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor]))


def test_schema_rejects_bad_eligibility_kind():
    factor = make_factor()
    factor["eligibility"]["kind"] = "maybe"
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor]))


def test_schema_rejects_threshold_without_comparator():
    factor = make_factor(kind="threshold", threshold=Decimal("10"))
    factor["eligibility"]["comparator"] = ""
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor]))


def test_schema_rejects_threshold_without_unit():
    factor = make_factor(kind="threshold", threshold=Decimal("10"))
    factor["eligibility"]["unit"] = ""
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor]))


def test_schema_rejects_verified_without_source_doc():
    factor = make_factor()
    factor["eligibility"]["source"]["doc"] = ""
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor]))


def test_schema_rejects_verified_without_source_clause():
    factor = make_factor()
    factor["period"]["source"]["clause"] = ""
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor]))


def test_schema_rejects_pending_with_value():
    factor = make_factor(period_status="pending")
    factor["period"]["kind"] = "months"
    factor["period"]["value"] = 12
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor]))


def test_schema_rejects_input_required_without_basis():
    factor = make_factor()
    factor["period"] = {"kind": "input_required", "value": None,
                        "status": "input_required", "basis": "", "note": ""}
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor]))


def test_schema_rejects_missing_exam_type():
    factor = make_factor()
    factor["examinations"].pop("emergency")
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor]))


def test_schema_rejects_bad_period_kind():
    factor = make_factor()
    factor["period"]["kind"] = "years"
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor]))


def test_schema_rejects_non_positive_period_value():
    factor = make_factor(months=0)
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor]))


def test_schema_rejects_optional_items_under_emergency_only():
    factor = make_factor()
    factor["examinations"]["periodic"]["optional_items"] = [_item("OPT")]
    with pytest.raises(InputError):
        SCHEMA.validate_ruleset(make_ruleset([factor],
                                             optional_items_policy="emergency_only"))


def test_schema_accepts_optional_items_in_emergency_under_emergency_only():
    factor = make_factor()
    factor["examinations"]["emergency"]["optional_items"] = [_item("OPT")]
    assert SCHEMA.validate_ruleset(make_ruleset([factor],
                                                optional_items_policy="emergency_only"))


# ==========================================================================
# §三 manifest / loader（9）
# ==========================================================================
def test_manifest_accepts_synthetic():
    assert SCHEMA.validate_manifest(make_manifest())["cutover"]["date"] == "2026-08-01"


def test_manifest_rejects_missing_cutover():
    obj = make_manifest()
    obj.pop("cutover")
    with pytest.raises(InputError):
        SCHEMA.validate_manifest(obj)


def test_manifest_rejects_missing_thresholds():
    obj = make_manifest()
    obj.pop("benchmark_thresholds")
    with pytest.raises(InputError):
        SCHEMA.validate_manifest(obj)


def test_load_manifest_from_pack_data():
    manifest = LOADER.load_manifest(DATA_DIR)
    assert set(manifest.ruleset_ids()) == {"GBZ188-2014", "GBZ188-2025"}


def test_load_ruleset_unknown_id_raises():
    with pytest.raises(InputError):
        LOADER.load_ruleset("NOPE", DATA_DIR)


def test_load_all_rulesets_production():
    rulesets = LOADER.load_all_rulesets(DATA_DIR)
    assert len(rulesets) == 2


def test_ruleset_factor_lookup():
    ruleset = LOADER.load_ruleset("GBZ188-2025", DATA_DIR)
    factor = ruleset.factor("GBZ188-5.19")
    assert factor["factor_id"] == "5.19"
    assert ruleset.has_factor("GBZ188-5.19")
    assert ruleset.factor("NOPE") is None


def test_ruleset_factor_codes_sorted():
    codes = LOADER.load_ruleset("GBZ188-2025", DATA_DIR).factor_codes
    assert codes == sorted(codes)


def test_file_sha256_is_lower_hex():
    digest = LOADER.file_sha256(os.path.join(DATA_DIR, "ruleset-2014.json"))
    assert len(digest) == 64
    assert digest == digest.lower()


# ==========================================================================
# §四 版本锚定（12）
# ==========================================================================
def test_parse_cutover_date_from_manifest():
    manifest = LOADER.Manifest(make_manifest())
    assert VERSION.parse_cutover_date(manifest).isoformat() == "2026-08-01"


def test_anchor_before_cutover():
    manifest = LOADER.Manifest(make_manifest())
    assert VERSION.resolve_ruleset_id("2026-07-31", manifest) == "SYN-OLD"


def test_anchor_on_cutover_is_after():
    manifest = LOADER.Manifest(make_manifest())
    assert VERSION.resolve_ruleset_id("2026-08-01", manifest) == "SYN-NEW"


def test_anchor_after_cutover():
    manifest = LOADER.Manifest(make_manifest())
    assert VERSION.resolve_ruleset_id("2026-09-15", manifest) == "SYN-NEW"


def test_anchor_year_before_cutover():
    manifest = LOADER.Manifest(make_manifest())
    assert VERSION.resolve_ruleset_id(2025, manifest) == "SYN-OLD"


def test_anchor_year_after_cutover():
    manifest = LOADER.Manifest(make_manifest())
    assert VERSION.resolve_ruleset_id(2027, manifest) == "SYN-NEW"


def test_anchor_year_with_cutover_is_ambiguous():
    manifest = LOADER.Manifest(make_manifest())
    with pytest.raises(AmbiguousYearError):
        VERSION.resolve_ruleset_id(2026, manifest)


def test_anchor_string_year_is_ambiguous():
    manifest = LOADER.Manifest(make_manifest())
    with pytest.raises(AmbiguousYearError):
        VERSION.resolve_ruleset_id("2026", manifest)


def test_anchor_rejects_bad_type():
    manifest = LOADER.Manifest(make_manifest())
    with pytest.raises(InputError):
        VERSION.resolve_ruleset_id([], manifest)


def test_describe_anchor_returns_rule_text():
    manifest = LOADER.Manifest(make_manifest())
    info = VERSION.describe_anchor("2026-09-15", manifest)
    assert info["ruleset_id"] == "SYN-NEW"
    assert info["cutover_date"] == "2026-08-01"


def test_production_anchor_2014_before_cutover():
    manifest = LOADER.load_manifest(DATA_DIR)
    assert VERSION.resolve_ruleset_id("2026-07-31", manifest) == "GBZ188-2014"


def test_production_anchor_2025_on_cutover():
    manifest = LOADER.load_manifest(DATA_DIR)
    assert VERSION.resolve_ruleset_id("2026-08-01", manifest) == "GBZ188-2025"


# ==========================================================================
# §五 status 门控（16）
# ==========================================================================
def test_gate_full_scope_blocks_pending_factor():
    ruleset = LOADER.Ruleset(make_ruleset([make_factor(factor_status="pending")]))
    with pytest.raises(GateBlocked):
        GATE.effective_ruleset(ruleset, "plan", required_factor_ids=["T_FACTOR"])


def test_gate_blocks_pending_period():
    ruleset = LOADER.Ruleset(make_ruleset([make_factor(period_status="pending")]))
    with pytest.raises(GateBlocked):
        GATE.effective_ruleset(ruleset, "check", required_factor_ids=["T_FACTOR"])


def test_gate_blocks_pending_exam_block():
    ruleset = LOADER.Ruleset(make_ruleset([make_factor(exam_status="pending")]))
    with pytest.raises(GateBlocked):
        GATE.effective_ruleset(ruleset, "plan", required_factor_ids=["T_FACTOR"])


def test_gate_minimal_scope_allows_pending_detail():
    ruleset = LOADER.Ruleset(make_ruleset([make_factor(period_status="pending")]))
    eff = GATE.effective_ruleset(ruleset, "compare")
    assert eff.scope == "compare"


def test_gate_minimal_blocks_pending_factor_identity():
    ruleset = LOADER.Ruleset(make_ruleset([make_factor(factor_status="pending")]))
    with pytest.raises(GateBlocked):
        GATE.effective_ruleset(ruleset, "compare")


def test_gate_rejects_unknown_scope():
    ruleset = LOADER.Ruleset(make_ruleset())
    with pytest.raises(ValueError):
        GATE.effective_ruleset(ruleset, "unknown")


def test_gate_rejects_unknown_factor_code():
    ruleset = LOADER.Ruleset(make_ruleset())
    with pytest.raises(InputError):
        GATE.effective_ruleset(ruleset, "plan", required_factor_ids=["NOPE"])


def test_gate_verified_passes():
    ruleset = LOADER.Ruleset(make_ruleset([make_factor()]))
    eff = GATE.effective_ruleset(ruleset, "plan", required_factor_ids=["T_FACTOR"])
    assert eff.used_factor_codes == ["T_FACTOR"]


def test_gate_input_required_is_non_blocking_for_period():
    factor = make_factor()
    factor["period"] = {"kind": "input_required", "value": None,
                        "status": "input_required", "basis": SYN + "周期需分级",
                        "note": ""}
    ruleset = LOADER.Ruleset(make_ruleset([factor]))
    eff = GATE.effective_ruleset(ruleset, "plan", required_factor_ids=["T_FACTOR"])
    assert eff.missing_inputs
    assert eff.missing_inputs[0]["blocking"] is False


def test_gate_input_required_blocking_for_eligibility():
    factor = make_factor()
    factor["eligibility"]["status"] = "input_required"
    factor["eligibility"]["basis"] = SYN + "需接触水平"
    ruleset = LOADER.Ruleset(make_ruleset([factor]))
    eff = GATE.effective_ruleset(ruleset, "plan", required_factor_ids=["T_FACTOR"])
    assert eff.missing_inputs[0]["blocking"] is True


def test_pending_report_returns_coordinates():
    ruleset = LOADER.Ruleset(make_ruleset([make_factor(factor_status="pending")]))
    pending, missing = GATE.pending_report(ruleset, "plan",
                                           required_factor_ids=["T_FACTOR"])
    assert pending
    assert "T_FACTOR" in pending[0]


def test_pending_report_unknown_factor_returns_empty():
    ruleset = LOADER.Ruleset(make_ruleset())
    pending, missing = GATE.pending_report(ruleset, "plan",
                                           required_factor_ids=["NOPE"])
    assert pending == [] and missing == []


def test_gate_blocked_message_mentions_scope():
    ruleset = LOADER.Ruleset(make_ruleset([make_factor(factor_status="pending")]))
    with pytest.raises(GateBlocked) as exc:
        GATE.effective_ruleset(ruleset, "plan", required_factor_ids=["T_FACTOR"])
    assert "scope=plan" in str(exc.value)


def test_gate_blocked_carries_coordinates():
    ruleset = LOADER.Ruleset(make_ruleset([make_factor(factor_status="pending")]))
    with pytest.raises(GateBlocked) as exc:
        GATE.effective_ruleset(ruleset, "plan", required_factor_ids=["T_FACTOR"])
    assert exc.value.blocked


def test_gate_used_codes_sorted():
    factors = [make_factor(code="B_CODE", fid="5.9.1"),
               make_factor(code="A_CODE", fid="5.9.0")]
    ruleset = LOADER.Ruleset(make_ruleset(factors))
    eff = GATE.effective_ruleset(ruleset, "plan",
                                 required_factor_ids=["B_CODE", "A_CODE"])
    assert eff.used_factor_codes == ["A_CODE", "B_CODE"]


# ==========================================================================
# §六 输入模型（18）
# ==========================================================================
BASE_POSITION = {"position_id": "POS-1", "exam_date": "2026-09-15",
                 "factors": [{"factor_code": "GBZ188-5.19"}]}


def test_position_parses_basic_fields():
    profile = MODEL.PositionProfile.from_dict(BASE_POSITION)
    assert profile.position_id == "POS-1"
    assert profile.factor_codes == ["GBZ188-5.19"]


def test_position_requires_position_id():
    with pytest.raises(InputError):
        MODEL.PositionProfile.from_dict({"exam_date": "2026-09-15",
                                         "factors": [{"factor_code": "X"}]})


def test_position_requires_factors_non_empty():
    with pytest.raises(InputError):
        MODEL.PositionProfile.from_dict({"position_id": "P",
                                         "exam_date": "2026-09-15", "factors": []})


def test_position_rejects_bad_date():
    payload = dict(BASE_POSITION)
    payload["exam_date"] = "2026/09/15"
    with pytest.raises(InputError):
        MODEL.PositionProfile.from_dict(payload)


def test_position_parses_exposure_decimal():
    payload = {"position_id": "P", "exam_date": "2026-09-15",
               "factors": [{"factor_code": "X",
                            "exposure": {"value": "3.5", "unit": "mg/m3"}}]}
    profile = MODEL.PositionProfile.from_dict(payload)
    assert profile.factors[0].exposure_value == Decimal("3.5")


def test_position_rejects_bad_exposure():
    payload = {"position_id": "P", "exam_date": "2026-09-15",
               "factors": [{"factor_code": "X",
                            "exposure": {"value": "abc"}}]}
    with pytest.raises(InputError):
        MODEL.PositionProfile.from_dict(payload)


def test_position_rejects_non_int_years():
    payload = {"position_id": "P", "exam_date": "2026-09-15",
               "factors": [{"factor_code": "X", "years": "3"}]}
    with pytest.raises(InputError):
        MODEL.PositionProfile.from_dict(payload)


def test_position_rejects_unknown_last_exam_type():
    payload = dict(BASE_POSITION)
    payload["last_exam_dates"] = {"weekly": "2025-01-01"}
    with pytest.raises(InputError):
        MODEL.PositionProfile.from_dict(payload)


def test_position_parses_last_exam_dates():
    payload = dict(BASE_POSITION)
    payload["last_exam_dates"] = {"periodic": "2025-09-15"}
    profile = MODEL.PositionProfile.from_dict(payload)
    assert profile.last_exam_dates["periodic"].year == 2025


def test_record_parses_items():
    record = MODEL.HealthRecord.from_dict(make_record())
    assert record.items == ["T_ITEM_1"]


def test_record_accepts_item_objects():
    obj = make_record()
    obj["items"] = [{"item_code": "A1"}, {"item_code": "A2"}]
    record = MODEL.HealthRecord.from_dict(obj)
    assert record.items == ["A1", "A2"]


def test_record_rejects_bad_exam_type():
    obj = make_record()
    obj["exam_type"] = "weekly"
    with pytest.raises(InputError):
        MODEL.HealthRecord.from_dict(obj)


def test_record_rejects_bad_item_type():
    obj = make_record()
    obj["items"] = [1]
    with pytest.raises(InputError):
        MODEL.HealthRecord.from_dict(obj)


def test_record_requires_record_id():
    obj = make_record()
    obj.pop("record_id")
    with pytest.raises(InputError):
        MODEL.HealthRecord.from_dict(obj)


def test_record_parses_last_exam_date():
    record = MODEL.HealthRecord.from_dict(
        make_record(last_exam_date="2025-09-15"))
    assert record.last_exam_date.year == 2025


def test_parse_iso_date_accepts_date_object():
    import datetime

    value = MODEL.parse_iso_date(datetime.date(2026, 1, 2))
    assert value.isoformat() == "2026-01-02"


def test_parse_decimal_none_passthrough():
    assert MODEL.parse_decimal(None, "x") is None


def test_verdict_sets_are_disjoint():
    assert MODEL.NONCOMPLIANT_VERDICTS == {"partial", "non_compliant"}
    assert MODEL.VERDICT_UNKNOWN not in MODEL.NONCOMPLIANT_VERDICTS


# ==========================================================================
# §七 监护矩阵（24）
# ==========================================================================
def test_plan_produces_items_for_four_exam_types():
    plan = _plan([make_factor(required=("A1", "A2"))], ["T_FACTOR"])
    for exam_type in ("pre_placement", "periodic", "post_placement", "emergency"):
        assert sorted(MATRIX.expected_items(plan, "T_FACTOR", exam_type)) == \
            ["A1", "A2"]


def test_threshold_below_reference_is_not_applicable():
    factor = make_factor(kind="threshold", threshold=Decimal("10"),
                         comparator=">=")
    plan = _plan([factor], ["T_FACTOR"], exposure=Decimal("3"))
    assert plan.factors[0].applicability.state == "not_applicable"
    assert plan.factors[0].exams == {}


def test_threshold_at_reference_is_applicable():
    factor = make_factor(kind="threshold", threshold=Decimal("10"),
                         comparator=">=")
    plan = _plan([factor], ["T_FACTOR"], exposure=Decimal("10"))
    assert plan.factors[0].applicability.state == "applicable"


def test_threshold_above_reference_is_applicable():
    factor = make_factor(kind="threshold", threshold=Decimal("10"),
                         comparator=">")
    plan = _plan([factor], ["T_FACTOR"], exposure=Decimal("11"))
    assert plan.factors[0].applicability.state == "applicable"


def test_missing_exposure_requests_input():
    factor = make_factor(kind="threshold", threshold=Decimal("10"))
    plan = _plan([factor], ["T_FACTOR"], exposure=None)
    assert plan.factors[0].applicability.state == "input_required"
    assert len(plan.missing_inputs) == 1


def test_unknown_comparator_raises():
    factor = make_factor(kind="threshold", threshold=Decimal("10"),
                         comparator="!!")
    with pytest.raises(ValueError):
        _plan([factor], ["T_FACTOR"], exposure=Decimal("10"))


def test_trace_covers_every_required_item():
    plan = _plan([make_factor(required=("A1", "A2"))], ["T_FACTOR"])
    targets = {row["target"] for row in plan.trace}
    for exam_type in ("pre_placement", "periodic", "post_placement", "emergency"):
        for code in ("A1", "A2"):
            assert "POS-1/T_FACTOR/%s/%s" % (exam_type, code) in targets
    assert all(row["basis"] for row in plan.trace)


def test_supplementary_items_do_not_enter_expected_set():
    factor = make_factor(required=("A1",))
    factor["examinations"]["periodic"]["supplementary_items"] = [_item("SUP1")]
    plan = _plan([factor], ["T_FACTOR"])
    assert MATRIX.expected_items(plan, "T_FACTOR", "periodic") == ["A1"]


def test_optional_items_do_not_enter_expected_set():
    factor = make_factor(required=("A1",))
    factor["examinations"]["periodic"]["optional_items"] = [_item("OPT1")]
    plan = _plan([factor], ["T_FACTOR"])
    assert MATRIX.expected_items(plan, "T_FACTOR", "periodic") == ["A1"]


def test_applicability_of_returns_state():
    plan = _plan([make_factor()], ["T_FACTOR"])
    assert MATRIX.applicability_of(plan, "T_FACTOR").state == "applicable"


def test_period_rule_of_returns_rule():
    plan = _plan([make_factor(months=6)], ["T_FACTOR"])
    assert MATRIX.period_rule_of(plan, "T_FACTOR")["value"] == 6


def test_expected_items_unknown_factor_returns_empty():
    plan = _plan([make_factor()], ["T_FACTOR"])
    assert MATRIX.expected_items(plan, "NOPE", "periodic") == []


def test_plan_notes_mention_period_input_required():
    factor = make_factor()
    factor["period"] = {"kind": "input_required", "value": None,
                        "status": "input_required", "basis": SYN + "分级",
                        "note": ""}
    plan = _plan([factor], ["T_FACTOR"])
    assert any("周期" in note for note in plan.notes)


def test_plan_missing_inputs_period_not_blocking():
    factor = make_factor()
    factor["period"] = {"kind": "input_required", "value": None,
                        "status": "input_required", "basis": SYN + "分级",
                        "note": ""}
    plan = _plan([factor], ["T_FACTOR"])
    assert plan.missing_inputs[0]["blocking"] is False


def test_plan_missing_inputs_applicability_is_blocking():
    factor = make_factor(kind="threshold", threshold=Decimal("10"))
    plan = _plan([factor], ["T_FACTOR"], exposure=None)
    assert plan.missing_inputs[0]["blocking"] is True


def test_plan_factor_name_and_code_preserved():
    plan = _plan([make_factor(code="T_FACTOR")], ["T_FACTOR"])
    fp = plan.factors[0]
    assert fp.factor_code == "T_FACTOR"
    assert SYN in fp.factor_name


def test_plan_period_copied_from_rule():
    plan = _plan([make_factor(months=24)], ["T_FACTOR"])
    assert plan.factors[0].period["value"] == 24


def test_plan_ruleset_id_recorded():
    plan = _plan([make_factor()], ["T_FACTOR"])
    assert plan.ruleset_id == "SYN-TEST"


def test_plan_position_id_recorded():
    plan = _plan([make_factor()], ["T_FACTOR"])
    assert plan.position_id == "POS-1"


def test_pending_applicability_returns_input_required():
    factor = make_factor()
    factor["eligibility"]["kind"] = "pending"
    factor["eligibility"]["status"] = "pending"
    factor["eligibility"]["threshold"] = None
    plan = MATRIX.plan_for_factor(factor, MODEL.FactorRef("T_FACTOR"), "SYN-TEST")
    assert plan.applicability.state == "input_required"


def test_input_required_eligibility_reason_kept():
    factor = make_factor()
    factor["eligibility"]["kind"] = "input_required"
    factor["eligibility"]["status"] = "input_required"
    factor["eligibility"]["basis"] = SYN + "需接触水平"
    plan = _plan([factor], ["T_FACTOR"])
    assert "接触水平" in plan.factors[0].applicability.reason


def test_always_eligibility_reason():
    plan = _plan([make_factor()], ["T_FACTOR"])
    assert "一律纳入" in plan.factors[0].applicability.reason


def test_plan_does_not_emit_exams_when_not_applicable():
    factor = make_factor(kind="threshold", threshold=Decimal("10"))
    plan = _plan([factor], ["T_FACTOR"], exposure=Decimal("1"))
    assert plan.factors[0].exams == {}


# ==========================================================================
# §八 周期判定（14）
# ==========================================================================
def test_add_months_clamps_month_end():
    assert str(PERIOD.add_months("2026-01-31", 1)) == "2026-02-28"
    assert str(PERIOD.add_months("2024-01-31", 1)) == "2024-02-29"
    assert str(PERIOD.add_months("2026-12-31", 2)) == "2027-02-28"


def test_add_months_accepts_date_object():
    import datetime

    assert str(PERIOD.add_months(datetime.date(2026, 3, 15), 12)) == "2027-03-15"


def test_add_months_rejects_negative():
    with pytest.raises(ValueError):
        PERIOD.add_months("2026-01-01", -1)


def test_add_months_rejects_bad_type():
    with pytest.raises(TypeError):
        PERIOD.add_months(123, 1)


def test_period_due_day_is_due_not_overdue():
    got = PERIOD.judge_period({"kind": "months", "value": 12},
                              "2025-09-15", "2026-09-15")
    assert got["verdict"] == "due"
    assert got["due_date"] == "2026-09-15"
    assert not PERIOD.is_period_noncompliant(got["verdict"])


def test_period_one_day_early_is_compliant():
    got = PERIOD.judge_period({"kind": "months", "value": 12},
                              "2025-09-15", "2026-09-14")
    assert got["verdict"] == "compliant"


def test_period_one_day_late_is_overdue():
    got = PERIOD.judge_period({"kind": "months", "value": 12},
                              "2025-09-15", "2026-09-16")
    assert got["verdict"] == "overdue"
    assert PERIOD.is_period_noncompliant("overdue")


def test_period_no_baseline_is_not_overdue():
    got = PERIOD.judge_period({"kind": "months", "value": 12},
                              None, "2026-09-15")
    assert got["verdict"] == "no_baseline"
    assert not PERIOD.is_period_noncompliant(got["verdict"])


def test_period_none_kind_is_not_applicable():
    got = PERIOD.judge_period({"kind": "none"}, "2025-01-01", "2026-09-15")
    assert got["verdict"] == "not_applicable"


def test_period_input_required_keeps_basis():
    got = PERIOD.judge_period({"kind": "input_required", "basis": SYN + "分级"},
                              "2025-01-01", "2026-09-15")
    assert got["verdict"] == "input_required"
    assert SYN in got["note"]


def test_period_pending_is_pending_input():
    got = PERIOD.judge_period({"kind": "pending"}, "2025-01-01", "2026-09-15")
    assert got["verdict"] == "input_required"


def test_period_unknown_kind_raises():
    with pytest.raises(ValueError):
        PERIOD.judge_period({"kind": "weeks", "value": 4},
                            "2025-01-01", "2026-09-15")


def test_period_bad_months_raises():
    with pytest.raises(ValueError):
        PERIOD.judge_period({"kind": "months", "value": 0},
                            "2025-01-01", "2026-09-15")


def test_period_overdue_note_counts_days():
    got = PERIOD.judge_period({"kind": "months", "value": 12},
                              "2025-09-15", "2026-09-20")
    assert "5 天" in got["note"]


# ==========================================================================
# §九 覆盖度（24）
# ==========================================================================
def test_coverage_compliant_when_all_required_present():
    result = _check([make_factor(required=("A1", "A2"))],
                    make_record(items=("A1", "A2"), exam_type="pre_placement"))
    assert result.verdict == "compliant"


def test_coverage_partial_when_one_missing():
    result = _check([make_factor(required=("A1", "A2"))],
                    make_record(items=("A1",), exam_type="pre_placement"))
    assert result.verdict == "partial"
    assert result.missing_items == ["A2"]


def test_coverage_non_compliant_when_none_done():
    result = _check([make_factor(required=("A1", "A2"))],
                    make_record(items=(), exam_type="pre_placement"))
    assert result.verdict == "non_compliant"
    assert result.missing_items == ["A1", "A2"]


def test_coverage_overdue_makes_partial_even_if_complete():
    result = _check([make_factor(required=("A1",), months=12)],
                    make_record(items=("A1",), exam_date="2026-09-15",
                                exam_type="periodic"), last="2024-01-01")
    assert result.verdict == "partial"
    assert result.period_verdict == "overdue"


def test_coverage_not_applicable_is_not_noncompliant():
    factor = make_factor(kind="threshold", threshold=Decimal("10"))
    eff = GATE.effective_ruleset(LOADER.Ruleset(make_ruleset([factor])), "check",
                                 required_factor_ids=["T_FACTOR"])
    profile = MODEL.PositionProfile(
        position_id="P", exam_date="2026-09-15",
        factors=[MODEL.FactorRef("T_FACTOR", exposure_value=Decimal("1"))])
    plan = MATRIX.compute_plan(profile, eff)
    record = MODEL.HealthRecord.from_dict(make_record(items=(),
                                                      exam_type="pre_placement"))
    result = COVERAGE.check_record(record, plan)
    assert result.verdict == "not_applicable"
    assert not result.is_noncompliant


def test_coverage_unmapped_is_warning_not_missing():
    result = _check([make_factor(required=("A1",))],
                    make_record(items=("A1", "某种写法"),
                                exam_type="pre_placement"))
    assert result.verdict == "compliant"
    assert result.unmapped_items == ["某种写法"]
    assert any(f["kind"] == "warning" for f in result.findings)


def test_coverage_alias_map_normalizes():
    result = _check([make_factor(required=("A1",))],
                    make_record(items=("别名A1",), exam_type="pre_placement"),
                    alias_map={"别名A1": "A1"})
    assert result.verdict == "compliant"
    assert not result.unmapped_items


def test_normalize_items_exact_hit_without_alias():
    got, unmapped = COVERAGE.normalize_items(["A1"], known_codes={"A1"},
                                             alias_map=None)
    assert got == {"A1"}
    assert unmapped == []


def test_normalize_items_alias_hit():
    got, unmapped = COVERAGE.normalize_items(["别名"], known_codes={"A1"},
                                             alias_map={"别名": "A1"})
    assert got == {"A1"}
    assert unmapped == []


def test_normalize_items_unknown_goes_unmapped():
    got, unmapped = COVERAGE.normalize_items(["X"], known_codes={"A1"})
    assert got == set()
    assert unmapped == ["X"]


def test_unknown_factor_yields_failed():
    factor = make_factor(code="T_FACTOR")
    eff = GATE.effective_ruleset(LOADER.Ruleset(make_ruleset([factor])), "check",
                                 required_factor_ids=["T_FACTOR"])
    profile = MODEL.PositionProfile(position_id="P", exam_date="2026-09-15",
                                    factors=[MODEL.FactorRef("T_FACTOR")])
    plan = MATRIX.compute_plan(profile, eff)
    record = MODEL.HealthRecord.from_dict(
        make_record(factor_code="OTHER", items=("A1",),
                    exam_type="pre_placement"))
    result = COVERAGE.check_record(record, plan)
    assert result.failed_reason == "unknown_factor"
    assert result.verdict == "unknown"


def test_coverage_missing_item_finding_has_item_basis():
    result = _check([make_factor(required=("A1", "A2"))],
                    make_record(items=("A1",), exam_type="pre_placement"))
    finding = next(f for f in result.findings if f["kind"] == "missing_item")
    assert finding["basis"]


def test_coverage_missing_item_trace_row():
    result = _check([make_factor(required=("A1", "A2"))],
                    make_record(items=("A1",), exam_type="pre_placement"))
    targets = {row["target"] for row in result.trace}
    assert "REC-1/T_FACTOR/pre_placement/A2" in targets


def test_coverage_unmapped_not_counted_as_extra():
    result = _check([make_factor(required=("A1",))],
                    make_record(items=("A1", "EXTRA"),
                                exam_type="pre_placement"))
    assert result.extra_items == []
    assert result.unmapped_items == ["EXTRA"]


def test_coverage_period_not_applicable_for_non_periodic():
    result = _check([make_factor(required=("A1",))],
                    make_record(items=("A1",), exam_type="pre_placement"))
    assert result.period_verdict == "not_applicable"


def test_coverage_period_no_baseline_is_not_overdue():
    result = _check([make_factor(required=("A1",), months=12)],
                    make_record(items=("A1",), exam_type="periodic"))
    assert result.period_verdict == "no_baseline"
    assert result.verdict == "compliant"


def test_coverage_period_due_is_compliant():
    result = _check([make_factor(required=("A1",), months=12)],
                    make_record(items=("A1",), exam_date="2026-09-15",
                                exam_type="periodic"), last="2025-09-15")
    assert result.period_verdict == "due"
    assert result.verdict == "compliant"


def test_coverage_input_required_applicability_yields_unknown():
    factor = make_factor(kind="threshold", threshold=Decimal("10"))
    eff = GATE.effective_ruleset(LOADER.Ruleset(make_ruleset([factor])), "check",
                                 required_factor_ids=["T_FACTOR"])
    profile = MODEL.PositionProfile(position_id="P", exam_date="2026-09-15",
                                    factors=[MODEL.FactorRef("T_FACTOR")])
    plan = MATRIX.compute_plan(profile, eff)
    record = MODEL.HealthRecord.from_dict(make_record(items=(),
                                                      exam_type="pre_placement"))
    result = COVERAGE.check_record(record, plan)
    assert result.verdict == "unknown"
    assert result.failed_reason == "missing_input"


def test_is_noncompliant_flags_partial():
    result = _check([make_factor(required=("A1", "A2"))],
                    make_record(items=("A1",), exam_type="pre_placement"))
    assert COVERAGE.is_noncompliant(result)


def test_verdict_reachability_reports_all_states():
    ruleset = LOADER.Ruleset(make_ruleset())
    rows = COVERAGE.verdict_reachability(ruleset)
    assert {row["state"] for row in rows} == {
        "not_applicable", "unknown", "compliant", "partial", "non_compliant"}


def test_verdict_reachability_not_applicable_false_for_all_always():
    ruleset = LOADER.Ruleset(make_ruleset())
    rows = {row["state"]: row for row in COVERAGE.verdict_reachability(ruleset)}
    assert rows["not_applicable"]["reachable"] is False


def test_verdict_reachability_not_applicable_true_for_threshold():
    factor = make_factor(kind="threshold", threshold=Decimal("10"))
    ruleset = LOADER.Ruleset(make_ruleset([factor]))
    rows = {row["state"]: row for row in COVERAGE.verdict_reachability(ruleset)}
    assert rows["not_applicable"]["reachable"] is True


def test_coverage_result_as_dict_shape():
    result = _check([make_factor(required=("A1",))],
                    make_record(items=("A1",), exam_type="pre_placement"))
    payload = result.as_dict()
    assert payload["verdict"] == "compliant"
    assert payload["verdict_label"] == "符合"


def test_coverage_record_position_id_preserved():
    result = _check([make_factor(required=("A1",))],
                    make_record(items=("A1",), exam_type="pre_placement"))
    assert result.position_id == "POS-1"


# ==========================================================================
# §十 版本对照（16）
# ==========================================================================
def _eff(rid, factors, scope="compare"):
    return GATE.effective_ruleset(LOADER.Ruleset(make_ruleset(factors,
                                                              ruleset_id=rid)),
                                  scope)


def test_compare_no_diff():
    report_ = COMPARE.compare_rulesets(
        _eff("A", [make_factor()]), _eff("B", [make_factor()]))
    assert report_.entries == []
    assert report_.notes


def test_compare_factor_added():
    report_ = COMPARE.compare_rulesets(
        _eff("A", [make_factor()]),
        _eff("B", [make_factor(), make_factor(code="T2", fid="5.9.1")]))
    assert [e.kind for e in report_.entries] == ["factor_added"]
    assert report_.entries[0].key == "T2"


def test_compare_factor_removed():
    report_ = COMPARE.compare_rulesets(
        _eff("A", [make_factor(), make_factor(code="T2", fid="5.9.1")]),
        _eff("B", [make_factor()]))
    assert [e.kind for e in report_.entries] == ["factor_removed"]


def test_compare_required_items_changed():
    report_ = COMPARE.compare_rulesets(
        _eff("A", [make_factor(required=("A1",))]),
        _eff("B", [make_factor(required=("A1", "A2"))]))
    assert "required_items_changed" in [e.kind for e in report_.entries]


def test_compare_period_changed():
    report_ = COMPARE.compare_rulesets(
        _eff("A", [make_factor(months=12)]),
        _eff("B", [make_factor(months=24)]))
    assert [e.kind for e in report_.entries] == ["period_changed"]


def test_compare_period_kind_changed():
    a = make_factor()
    b = make_factor()
    b["period"] = {"kind": "none", "value": None, "status": "verified",
                   "basis": SYN + "无周期", "note": "", "source": _src("9")}
    report_ = COMPARE.compare_rulesets(_eff("A", [a]), _eff("B", [b]))
    assert [e.kind for e in report_.entries] == ["period_changed"]


def test_compare_optional_items_adjusted():
    a = make_factor()
    b = make_factor()
    b["examinations"]["periodic"]["optional_items"] = [_item("OPT")]
    report_ = COMPARE.compare_rulesets(_eff("A", [a]), _eff("B", [b]))
    assert [e.kind for e in report_.entries] == ["optional_items_adjusted"]


def test_compare_skips_detail_when_one_side_pending():
    a = make_factor(period_status="pending")
    b = make_factor()
    report_ = COMPARE.compare_rulesets(_eff("A", [a]), _eff("B", [b]))
    assert report_.entries == []
    assert any("尚未核对" in note for note in report_.notes)


def test_compare_detail_pending_true_for_factor_status():
    assert COMPARE.detail_pending(make_factor(factor_status="pending"))


def test_compare_detail_pending_false_for_verified():
    assert not COMPARE.detail_pending(make_factor())


def test_compare_entries_carry_basis():
    report_ = COMPARE.compare_rulesets(
        _eff("A", [make_factor(required=("A1",))]),
        _eff("B", [make_factor(required=("A1", "A2"))]))
    entry = report_.entries[0]
    assert entry.basis_a and entry.basis_b


def test_compare_report_as_dict_shape():
    report_ = COMPARE.compare_rulesets(
        _eff("A", [make_factor()]), _eff("B", [make_factor()]))
    payload = report_.as_dict()
    assert set(payload) == {"ruleset_a", "ruleset_b", "entries", "notes"}


def test_compare_report_by_kind_filters():
    report_ = COMPARE.compare_rulesets(
        _eff("A", [make_factor()]),
        _eff("B", [make_factor(), make_factor(code="T2", fid="5.9.1")]))
    assert len(report_.by_kind("factor_added")) == 1
    assert report_.by_kind("period_changed") == []


def test_compare_production_has_factor_changes():
    context = PIPE.Context(DATA_DIR)
    report_ = PIPE.compare("GBZ188-2014", "GBZ188-2025", context)
    assert len(report_.entries) >= 20


def test_compare_production_notes_mention_pending_details():
    context = PIPE.Context(DATA_DIR)
    report_ = PIPE.compare("GBZ188-2014", "GBZ188-2025", context)
    assert any("尚未核对" in note for note in report_.notes)


def test_compare_production_contains_added_factor():
    context = PIPE.Context(DATA_DIR)
    report_ = PIPE.compare("GBZ188-2014", "GBZ188-2025", context)
    assert report_.by_kind("factor_added")


# ==========================================================================
# §十一 器官端到端（20）
# ==========================================================================
def test_organ_position_sample_one_pass():
    findings = evaluate(load_json(POSITION_SAMPLE))
    assert len(findings) == 1
    assert findings[0].verdict == PASS
    assert findings[0].anchor.clause_id == "5.19"


def test_organ_record_partial_is_fail():
    findings = evaluate(load_json(RECORD_SAMPLE))
    assert len(findings) == 1
    assert findings[0].verdict == FAIL
    assert report(findings).exit_code() == 1


def test_organ_record_partial_anchor():
    findings = evaluate(load_json(RECORD_SAMPLE))
    assert findings[0].anchor.clause_id == "6.7"


def test_organ_full_sample_counts():
    findings = evaluate(load_json(FULL_SAMPLE))
    assert len(findings) == 26
    counts = report(findings).summary()["verdicts"]
    assert counts[FAIL] == 1
    assert counts[PASS] == 25
    assert counts[NOT_APPLICABLE] == 0


def test_organ_full_sample_coverage_compliant():
    findings = evaluate(load_json(FULL_SAMPLE))
    item = next(f for f in findings if f.rule_id ==
                "occupational.coverage:SYN-TRUTH-001")
    assert item.verdict == PASS
    assert item.evidence["verdict"] == "compliant"


def test_organ_full_sample_coverage_overdue():
    findings = evaluate(load_json(FULL_SAMPLE))
    item = next(f for f in findings if f.rule_id ==
                "occupational.coverage:SYN-TRUTH-018")
    assert item.verdict == FAIL
    assert item.evidence["period_verdict"] == "overdue"


def test_organ_full_sample_compare_summary():
    findings = evaluate(load_json(FULL_SAMPLE))
    summary = next(f for f in findings if f.rule_id ==
                   "occupational.compare:summary")
    assert summary.evidence["entries"] >= 20
    assert summary.evidence["notes"]


def test_organ_plan_evidence_lists_required_items():
    findings = evaluate(load_json(POSITION_SAMPLE))
    evidence = findings[0].evidence
    assert set(evidence["required_items"]) == {
        "pre_placement", "periodic", "post_placement", "emergency"}


def test_organ_record_evidence_has_record_id():
    findings = evaluate(load_json(RECORD_SAMPLE))
    assert findings[0].evidence["record_id"] == "SYN-TRUTH-018"


def test_organ_requires_case_id():
    subject = load_json(POSITION_SAMPLE)
    subject.pop("case_id")
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_requires_one_of_three_inputs():
    with pytest.raises(ValueError):
        evaluate({"case_id": "x"})


def test_organ_rejects_unknown_key():
    subject = load_json(POSITION_SAMPLE)
    subject["future"] = 1
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_rejects_unknown_compare_field():
    subject = load_json(FULL_SAMPLE)
    subject["compare"]["future"] = 1
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_rejects_missing_compare_side():
    subject = load_json(FULL_SAMPLE)
    subject["compare"].pop("ruleset_b")
    with pytest.raises(ValueError):
        evaluate(subject)


def test_organ_compare_only_sample():
    findings = evaluate(load_json(COMPARE_SAMPLE))
    assert compact_assertion(findings)


def compact_assertion(findings):
    return len(findings) >= 1 and any(
        f.rule_id == "occupational.compare:summary" for f in findings)


def test_organ_wrong_basis_version_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(load_json(POSITION_SAMPLE), Basis.empty("0"))


def test_organ_missing_clause_basis_missing():
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate(load_json(POSITION_SAMPLE),
                          Basis(version=REG.VERSION, clauses=[]))


def test_organ_deterministic():
    subject = load_json(FULL_SAMPLE)
    first = [f.as_dict() for f in evaluate(subject)]
    second = [f.as_dict() for f in evaluate(subject)]
    assert first == second


def test_organ_uses_version_anchor_for_record():
    findings = evaluate(load_json(RECORD_SAMPLE))
    assert findings[0].anchor.version == REG.VERSION


def test_organ_plan_finding_id_contains_position_and_factor():
    findings = evaluate(load_json(POSITION_SAMPLE))
    assert findings[0].rule_id == "occupational.plan:SYN-POS-benzene:GBZ188-5.19"


# ==========================================================================
# §十二 CLI 契约（7）
# ==========================================================================
def test_cli_position_returns_ok():
    assert cp_cli.main(["check", SLUG, "--input", POSITION_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_record_returns_noncompliant():
    assert cp_cli.main(["check", SLUG, "--input", RECORD_SAMPLE,
                        "--basis", BASIS_PATH]) == 1


def test_cli_full_returns_noncompliant():
    assert cp_cli.main(["check", SLUG, "--input", FULL_SAMPLE,
                        "--basis", BASIS_PATH]) == 1


def test_cli_missing_basis_returns_contract():
    assert cp_cli.main(["check", SLUG, "--input", POSITION_SAMPLE]) == 3


def test_cli_compare_only_returns_ok():
    assert cp_cli.main(["check", SLUG, "--input", COMPARE_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_unknown_ruleset_in_compare_returns_input(tmp_path):
    subject = load_json(COMPARE_SAMPLE)
    subject["compare"]["ruleset_b"] = "NOPE"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(subject, ensure_ascii=False), encoding="utf-8")
    assert cp_cli.main(["check", SLUG, "--input", str(path),
                        "--basis", BASIS_PATH]) == 2


def test_cli_missing_case_id_returns_input(tmp_path):
    subject = load_json(POSITION_SAMPLE)
    subject.pop("case_id")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(subject, ensure_ascii=False), encoding="utf-8")
    assert cp_cli.main(["check", SLUG, "--input", str(path),
                        "--basis", BASIS_PATH]) == 2


# ==========================================================================
# §十三 数据纪律与边界（8）
# ==========================================================================
def test_pack_registered_in_builtin_modules():
    from clauseproof.packs import BUILTIN_MODULES
    assert SLUG in BUILTIN_MODULES


def test_pack_slug_is_distinct_from_sibling_token():
    assert SLUG == "occupational-surveillance"
    assert "occupational-health" not in SLUG


def test_production_ruleset_has_97_factors():
    ruleset = LOADER.load_ruleset("GBZ188-2025", DATA_DIR)
    assert len(ruleset.factors) == 97


def test_production_ruleset_2014_has_81_factors():
    ruleset = LOADER.load_ruleset("GBZ188-2014", DATA_DIR)
    assert len(ruleset.factors) == 81


def test_production_2025_pending_details_include_chapters_8_9():
    ruleset = LOADER.load_ruleset("GBZ188-2025", DATA_DIR)
    pending = [f for f in ruleset.factors
               if COMPARE.detail_pending(f) and f["chapter"] in ("8", "9")]
    assert pending


def test_production_2025_chapters_5_7_are_verified():
    ruleset = LOADER.load_ruleset("GBZ188-2025", DATA_DIR)
    for factor in ruleset.factors:
        if factor["chapter"] in ("5", "6", "7"):
            assert not COMPARE.detail_pending(factor), factor["factor_code"]


def test_data_clauses_cover_all_2025_factor_ids():
    ruleset = LOADER.load_ruleset("GBZ188-2025", DATA_DIR)
    library = basis()
    missing = [f["factor_id"] for f in ruleset.factors
               if library.clause(f["factor_id"]) is None]
    assert missing == []


def test_clause_for_pending_factor_is_registered():
    clause = basis().clause("8.1")
    assert clause is not None
    assert "GBZ 188—2025" in clause.path