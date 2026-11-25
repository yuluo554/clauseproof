"""器官 ``checkup-ranges`` 无损测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在"判定结果"上。
来源仓判定层（21 文件 / 392 静态函数 / 实跑 424）逐文件处置见
``docs/checkup-ranges.md`` §6.1；本文件承载其中**可搬**的全部判定面：
四态比较、三级优先选区间、边界语义（闭/开、单侧）、主体适用域、名称/单位归一、
区间结构门，以及知识库漂移门与样例真值 parity。

本文件同时是**漂移门**：``data/indicators.yaml``（来源资产）与
``registry.INDICATORS``（字面量）必须逐条一致。
"""

import importlib
import json
import os
import sys

import pytest
import yaml

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

SLUG = "checkup-ranges"
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", SLUG)

pack_mod = importlib.import_module("clauseproof.packs." + SLUG)
registry = importlib.import_module("clauseproof.packs." + SLUG + ".registry")
engine = importlib.import_module("clauseproof.packs." + SLUG + ".engine")

INDICATORS = registry.INDICATORS
FLAG_HIGH = engine.FLAG_HIGH
FLAG_LOW = engine.FLAG_LOW
FLAG_NORMAL = engine.FLAG_NORMAL
FLAG_NOT_ASSESSED = engine.FLAG_NOT_ASSESSED
RANGE_REPORT = engine.RANGE_SOURCE_REPORT
RANGE_BUILTIN = engine.RANGE_SOURCE_BUILTIN
RANGE_NONE = engine.RANGE_SOURCE_NONE

SAMPLES = os.path.join(ROOT, "samples", SLUG)


# --------------------------------------------------------------------------
# 夹具：subject 构造与速取
# --------------------------------------------------------------------------
def ref(low, high, bounds="closed", source=RANGE_REPORT):
    return engine.RefRange(low=low, high=high, bounds=bounds, source=source)


def subject(**overrides):
    base = {"canonical_name": "WBC", "value": 6.0, "unit": "10^9/L"}
    base.update(overrides)
    return base


def flag_of(data, indicators=None):
    return pack_mod.judge(data, indicators or INDICATORS).flag


def basis_path():
    return os.path.join(PACK_DIR, "data", "clauses.json")


def shipped_basis():
    return Basis.from_json(basis_path())


def report_of(data, basis=None):
    raw = pack_mod.judge(data)
    findings = pack_mod.evaluate(data, basis or shipped_basis())
    return Report(product="clauseproof", organ=SLUG, organ_version=pack_mod.VERSION,
                  subject=str(data.get("canonical_name", "")), findings=tuple(findings))


def sample_records():
    with open(os.path.join(SAMPLES, "measurements.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)["records"]


# --------------------------------------------------------------------------
# 参数集（全部从知识库实算，不在测试里抄第二份数值）
# --------------------------------------------------------------------------
def _all_names():
    pairs = []
    for indicator in INDICATORS:
        for name in indicator.names:
            pairs.append((indicator.canonical_name, name))
    return pairs


def _all_units():
    seen = []
    for indicator in INDICATORS:
        for unit in dict.fromkeys(indicator.units):
            seen.append((indicator.canonical_name, unit))
    return seen


def _midpoint(indicator):
    if indicator.low is None:
        return indicator.high - 0.1
    if indicator.high is None:
        return indicator.low + 0.1
    return (indicator.low + indicator.high) / 2.0


TWO_SIDED = [i for i in INDICATORS if i.low is not None and i.high is not None]
ALL_LOW_BOUND = [i for i in INDICATORS if i.low is not None]
ALL_HIGH_BOUND = [i for i in INDICATORS if i.high is not None]


def printed(indicator, bounds="closed"):
    return engine.RefRange(low=indicator.low, high=indicator.high, bounds=bounds,
                           source=RANGE_REPORT)


def measure(indicator, value, range_obj):
    return {"canonical_name": indicator.canonical_name, "value": value,
            "unit": indicator.unit, "range": {
                "low": range_obj.low, "high": range_obj.high, "bounds": range_obj.bounds}}


# ==========================================================================
# 一、器官契约
# ==========================================================================
def test_pack_is_registered_under_slug():
    pack = get(SLUG)
    assert isinstance(pack, Pack)
    assert pack.slug == SLUG
    assert pack.version == pack_mod.VERSION


def test_pack_is_listed_in_builtin_modules_and_sorted():
    packs_ns = importlib.import_module("clauseproof.packs")
    assert SLUG in packs_ns.BUILTIN_MODULES
    assert list(packs_ns.BUILTIN_MODULES) == sorted(packs_ns.BUILTIN_MODULES)


def test_pack_appears_in_all_packs():
    assert SLUG in [pack.slug for pack in all_packs()]


def test_pack_declares_input_fields():
    assert get(SLUG).input_fields == pack_mod.INPUT_FIELDS
    assert "canonical_name" in get(SLUG).input_fields


def test_pack_has_no_own_argument_parser():
    import ast

    for name in ("__init__.py", "engine.py", "registry.py"):
        with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(alias.name == "argparse" for alias in node.names), name
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "argparse", name


def test_engine_has_no_io_clock_or_env():
    """判定内核不读文件、不读环境变量、不读时钟、不打印（执行约束的静态形态）。"""
    import ast

    with open(os.path.join(PACK_DIR, "engine.py"), "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in ("os", "time", "datetime", "pathlib"), alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in ("os", "time", "datetime", "pathlib"), node.module
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("print", "open"), node.func.id


# ==========================================================================
# 二、漂移门：data/indicators.yaml ↔ registry 字面量
# ==========================================================================
def _yaml_indicators():
    with open(os.path.join(PACK_DIR, "data", "indicators.yaml"), "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_data_dir_is_present_and_non_empty():
    names = sorted(os.listdir(os.path.join(PACK_DIR, "data")))
    assert names == ["clauses.json", "indicators.yaml"]


def test_registry_schema_version_matches_frozen_file():
    frozen = _yaml_indicators()
    assert frozen["schema_version"] == 1
    assert str(frozen["updated"]) == registry.REGISTRY_VERSION


def test_indicator_count_matches_frozen_file():
    assert len(INDICATORS) == len(_yaml_indicators()["indicators"]) == 19


def _yaml_entry(canonical):
    return {item["canonical_name"]: item for item in _yaml_indicators()["indicators"]}[canonical]


def _assert_kit_range(canonical):
    entry = engine.find_indicator(canonical, INDICATORS)
    item = _yaml_entry(canonical)
    assert entry.low == item["default_range"]["low"], canonical
    assert entry.high == item["default_range"]["high"], canonical
    assert entry.bounds == item["default_range"].get("bounds", "closed"), canonical


def _assert_kit_meta(canonical):
    entry = engine.find_indicator(canonical, INDICATORS)
    item = _yaml_entry(canonical)
    assert entry.display_name == item["display_name"], canonical
    assert list(entry.aliases) == list(item["aliases"]), canonical
    assert entry.unit == item["unit"], canonical
    assert list(entry.unit_aliases) == list(item["unit_aliases"]), canonical
    assert entry.sex == item["applies_to"]["sex"], canonical
    assert entry.standard == item["source"]["standard"], canonical
    assert entry.status == item["source"]["status"], canonical


def _assert_kit_pending(canonical):
    entry = engine.find_indicator(canonical, INDICATORS)
    assert entry.status == engine.STATUS_PENDING, canonical
    assert entry.is_effective is False, canonical


# ---- 19 条区间条目 × 三项数据门（逐条一条用例）----
def test_kit_range_WBC(): _assert_kit_range("WBC")
def test_kit_meta_WBC(): _assert_kit_meta("WBC")
def test_kit_pending_WBC(): _assert_kit_pending("WBC")
def test_kit_range_RBC(): _assert_kit_range("RBC")
def test_kit_meta_RBC(): _assert_kit_meta("RBC")
def test_kit_pending_RBC(): _assert_kit_pending("RBC")
def test_kit_range_HGB(): _assert_kit_range("HGB")
def test_kit_meta_HGB(): _assert_kit_meta("HGB")
def test_kit_pending_HGB(): _assert_kit_pending("HGB")
def test_kit_range_HCT(): _assert_kit_range("HCT")
def test_kit_meta_HCT(): _assert_kit_meta("HCT")
def test_kit_pending_HCT(): _assert_kit_pending("HCT")
def test_kit_range_PLT(): _assert_kit_range("PLT")
def test_kit_meta_PLT(): _assert_kit_meta("PLT")
def test_kit_pending_PLT(): _assert_kit_pending("PLT")
def test_kit_range_ALT(): _assert_kit_range("ALT")
def test_kit_meta_ALT(): _assert_kit_meta("ALT")
def test_kit_pending_ALT(): _assert_kit_pending("ALT")
def test_kit_range_AST(): _assert_kit_range("AST")
def test_kit_meta_AST(): _assert_kit_meta("AST")
def test_kit_pending_AST(): _assert_kit_pending("AST")
def test_kit_range_ALP(): _assert_kit_range("ALP")
def test_kit_meta_ALP(): _assert_kit_meta("ALP")
def test_kit_pending_ALP(): _assert_kit_pending("ALP")
def test_kit_range_GGT(): _assert_kit_range("GGT")
def test_kit_meta_GGT(): _assert_kit_meta("GGT")
def test_kit_pending_GGT(): _assert_kit_pending("GGT")
def test_kit_range_TBIL(): _assert_kit_range("TBIL")
def test_kit_meta_TBIL(): _assert_kit_meta("TBIL")
def test_kit_pending_TBIL(): _assert_kit_pending("TBIL")
def test_kit_range_TP(): _assert_kit_range("TP")
def test_kit_meta_TP(): _assert_kit_meta("TP")
def test_kit_pending_TP(): _assert_kit_pending("TP")
def test_kit_range_TC(): _assert_kit_range("TC")
def test_kit_meta_TC(): _assert_kit_meta("TC")
def test_kit_pending_TC(): _assert_kit_pending("TC")
def test_kit_range_TG(): _assert_kit_range("TG")
def test_kit_meta_TG(): _assert_kit_meta("TG")
def test_kit_pending_TG(): _assert_kit_pending("TG")
def test_kit_range_HDLC(): _assert_kit_range("HDL-C")
def test_kit_meta_HDLC(): _assert_kit_meta("HDL-C")
def test_kit_pending_HDLC(): _assert_kit_pending("HDL-C")
def test_kit_range_LDLC(): _assert_kit_range("LDL-C")
def test_kit_meta_LDLC(): _assert_kit_meta("LDL-C")
def test_kit_pending_LDLC(): _assert_kit_pending("LDL-C")
def test_kit_range_CREA(): _assert_kit_range("CREA")
def test_kit_meta_CREA(): _assert_kit_meta("CREA")
def test_kit_pending_CREA(): _assert_kit_pending("CREA")
def test_kit_range_UREA(): _assert_kit_range("UREA")
def test_kit_meta_UREA(): _assert_kit_meta("UREA")
def test_kit_pending_UREA(): _assert_kit_pending("UREA")
def test_kit_range_UA(): _assert_kit_range("UA")
def test_kit_meta_UA(): _assert_kit_meta("UA")
def test_kit_pending_UA(): _assert_kit_pending("UA")
def test_kit_range_GLU(): _assert_kit_range("GLU")
def test_kit_meta_GLU(): _assert_kit_meta("GLU")
def test_kit_pending_GLU(): _assert_kit_pending("GLU")


def test_registry_has_no_verified_indicator_today():
    assert registry.VERIFIED_INDICATORS == ()
    assert len(registry.PENDING_INDICATORS) == 19


def test_clause_ids_track_the_verified_subset():
    assert registry.clause_ids() == ("range:report-printed",)


def test_registry_standard_is_explicit_for_every_entry():
    for indicator in INDICATORS:
        assert indicator.standard.strip()
        assert indicator.standard != ""


def test_unlocated_standards_are_labelled_as_such():
    unlocated = [i for i in INDICATORS if i.standard == registry.STANDARD_UNLOCATED]
    assert len(unlocated) == 6
    assert {i.canonical_name for i in unlocated} == {"TC", "TG", "HDL-C", "LDL-C", "UA", "GLU"}


def test_registry_declaration_order_is_preserved():
    """归一命中顺序 = 声明序（同名词不会在不同指标间抢先后）。"""
    assert [i.canonical_name for i in INDICATORS] == [
        "WBC", "RBC", "HGB", "HCT", "PLT", "ALT", "AST", "ALP", "GGT", "TBIL",
        "TP", "TC", "TG", "HDL-C", "LDL-C", "CREA", "UREA", "UA", "GLU"]


def test_no_name_is_claimed_by_two_indicators():
    """同一别名不得跨条目抢注（同一条目内"规范名重复出现在别名里"是允许的）。"""
    owners = {}
    for indicator in INDICATORS:
        for name in indicator.names:
            assert owners.get(name, indicator.canonical_name) == indicator.canonical_name, name
            owners[name] = indicator.canonical_name


def test_no_unit_alias_is_claimed_by_two_indicators_with_different_units():
    owners = {}
    for indicator in INDICATORS:
        for unit in indicator.units:
            owners.setdefault(unit, set()).add(indicator.unit)
    assert all(len(units) == 1 for units in owners.values())


# ==========================================================================
# 三、名称 / 单位归一（每条别名一条用例）
# ==========================================================================
def _assert_name_at(canonical, offset):
    ind = engine.find_indicator(canonical, INDICATORS)
    name = ind.names[offset]
    got = engine.normalize_name(name, INDICATORS)
    assert got is not None and got.canonical_name == canonical, (canonical, name)


def _assert_unit_at(canonical, offset):
    ind = engine.find_indicator(canonical, INDICATORS)
    unit = list(dict.fromkeys(ind.units))[offset]
    assert engine.normalize_unit(unit, ind) == ind.unit, (canonical, unit)


# ---- 105 条指标名（规范名 + 别名）逐条一条用例：都要归一到同一规范名 ----
def test_name_WBC_0(): _assert_name_at("WBC", 0)
def test_name_WBC_1(): _assert_name_at("WBC", 1)
def test_name_WBC_2(): _assert_name_at("WBC", 2)
def test_name_WBC_3(): _assert_name_at("WBC", 3)
def test_name_WBC_4(): _assert_name_at("WBC", 4)
def test_name_WBC_5(): _assert_name_at("WBC", 5)
def test_name_RBC_0(): _assert_name_at("RBC", 0)
def test_name_RBC_1(): _assert_name_at("RBC", 1)
def test_name_RBC_2(): _assert_name_at("RBC", 2)
def test_name_RBC_3(): _assert_name_at("RBC", 3)
def test_name_RBC_4(): _assert_name_at("RBC", 4)
def test_name_HGB_0(): _assert_name_at("HGB", 0)
def test_name_HGB_1(): _assert_name_at("HGB", 1)
def test_name_HGB_2(): _assert_name_at("HGB", 2)
def test_name_HGB_3(): _assert_name_at("HGB", 3)
def test_name_HGB_4(): _assert_name_at("HGB", 4)
def test_name_HCT_0(): _assert_name_at("HCT", 0)
def test_name_HCT_1(): _assert_name_at("HCT", 1)
def test_name_HCT_2(): _assert_name_at("HCT", 2)
def test_name_HCT_3(): _assert_name_at("HCT", 3)
def test_name_HCT_4(): _assert_name_at("HCT", 4)
def test_name_HCT_5(): _assert_name_at("HCT", 5)
def test_name_PLT_0(): _assert_name_at("PLT", 0)
def test_name_PLT_1(): _assert_name_at("PLT", 1)
def test_name_PLT_2(): _assert_name_at("PLT", 2)
def test_name_PLT_3(): _assert_name_at("PLT", 3)
def test_name_PLT_4(): _assert_name_at("PLT", 4)
def test_name_ALT_0(): _assert_name_at("ALT", 0)
def test_name_ALT_1(): _assert_name_at("ALT", 1)
def test_name_ALT_2(): _assert_name_at("ALT", 2)
def test_name_ALT_3(): _assert_name_at("ALT", 3)
def test_name_ALT_4(): _assert_name_at("ALT", 4)
def test_name_AST_0(): _assert_name_at("AST", 0)
def test_name_AST_1(): _assert_name_at("AST", 1)
def test_name_AST_2(): _assert_name_at("AST", 2)
def test_name_AST_3(): _assert_name_at("AST", 3)
def test_name_AST_4(): _assert_name_at("AST", 4)
def test_name_ALP_0(): _assert_name_at("ALP", 0)
def test_name_ALP_1(): _assert_name_at("ALP", 1)
def test_name_ALP_2(): _assert_name_at("ALP", 2)
def test_name_ALP_3(): _assert_name_at("ALP", 3)
def test_name_ALP_4(): _assert_name_at("ALP", 4)
def test_name_GGT_0(): _assert_name_at("GGT", 0)
def test_name_GGT_1(): _assert_name_at("GGT", 1)
def test_name_GGT_2(): _assert_name_at("GGT", 2)
def test_name_GGT_3(): _assert_name_at("GGT", 3)
def test_name_GGT_4(): _assert_name_at("GGT", 4)
def test_name_GGT_5(): _assert_name_at("GGT", 5)
def test_name_TBIL_0(): _assert_name_at("TBIL", 0)
def test_name_TBIL_1(): _assert_name_at("TBIL", 1)
def test_name_TBIL_2(): _assert_name_at("TBIL", 2)
def test_name_TBIL_3(): _assert_name_at("TBIL", 3)
def test_name_TBIL_4(): _assert_name_at("TBIL", 4)
def test_name_TBIL_5(): _assert_name_at("TBIL", 5)
def test_name_TP_0(): _assert_name_at("TP", 0)
def test_name_TP_1(): _assert_name_at("TP", 1)
def test_name_TP_2(): _assert_name_at("TP", 2)
def test_name_TP_3(): _assert_name_at("TP", 3)
def test_name_TP_4(): _assert_name_at("TP", 4)
def test_name_TC_0(): _assert_name_at("TC", 0)
def test_name_TC_1(): _assert_name_at("TC", 1)
def test_name_TC_2(): _assert_name_at("TC", 2)
def test_name_TC_3(): _assert_name_at("TC", 3)
def test_name_TC_4(): _assert_name_at("TC", 4)
def test_name_TC_5(): _assert_name_at("TC", 5)
def test_name_TG_0(): _assert_name_at("TG", 0)
def test_name_TG_1(): _assert_name_at("TG", 1)
def test_name_TG_2(): _assert_name_at("TG", 2)
def test_name_TG_3(): _assert_name_at("TG", 3)
def test_name_TG_4(): _assert_name_at("TG", 4)
def test_name_HDLC_0(): _assert_name_at("HDL-C", 0)
def test_name_HDLC_1(): _assert_name_at("HDL-C", 1)
def test_name_HDLC_2(): _assert_name_at("HDL-C", 2)
def test_name_HDLC_3(): _assert_name_at("HDL-C", 3)
def test_name_HDLC_4(): _assert_name_at("HDL-C", 4)
def test_name_HDLC_5(): _assert_name_at("HDL-C", 5)
def test_name_LDLC_0(): _assert_name_at("LDL-C", 0)
def test_name_LDLC_1(): _assert_name_at("LDL-C", 1)
def test_name_LDLC_2(): _assert_name_at("LDL-C", 2)
def test_name_LDLC_3(): _assert_name_at("LDL-C", 3)
def test_name_LDLC_4(): _assert_name_at("LDL-C", 4)
def test_name_LDLC_5(): _assert_name_at("LDL-C", 5)
def test_name_CREA_0(): _assert_name_at("CREA", 0)
def test_name_CREA_1(): _assert_name_at("CREA", 1)
def test_name_CREA_2(): _assert_name_at("CREA", 2)
def test_name_CREA_3(): _assert_name_at("CREA", 3)
def test_name_CREA_4(): _assert_name_at("CREA", 4)
def test_name_CREA_5(): _assert_name_at("CREA", 5)
def test_name_UREA_0(): _assert_name_at("UREA", 0)
def test_name_UREA_1(): _assert_name_at("UREA", 1)
def test_name_UREA_2(): _assert_name_at("UREA", 2)
def test_name_UREA_3(): _assert_name_at("UREA", 3)
def test_name_UREA_4(): _assert_name_at("UREA", 4)
def test_name_UREA_5(): _assert_name_at("UREA", 5)
def test_name_UA_0(): _assert_name_at("UA", 0)
def test_name_UA_1(): _assert_name_at("UA", 1)
def test_name_UA_2(): _assert_name_at("UA", 2)
def test_name_UA_3(): _assert_name_at("UA", 3)
def test_name_GLU_0(): _assert_name_at("GLU", 0)
def test_name_GLU_1(): _assert_name_at("GLU", 1)
def test_name_GLU_2(): _assert_name_at("GLU", 2)
def test_name_GLU_3(): _assert_name_at("GLU", 3)
def test_name_GLU_4(): _assert_name_at("GLU", 4)
def test_name_GLU_5(): _assert_name_at("GLU", 5)
def test_name_GLU_6(): _assert_name_at("GLU", 6)


# ---- 52 条单位别名逐条一条用例：都要归一到规范单位 ----
def test_unit_WBC_0(): _assert_unit_at("WBC", 0)
def test_unit_WBC_1(): _assert_unit_at("WBC", 1)
def test_unit_WBC_2(): _assert_unit_at("WBC", 2)
def test_unit_WBC_3(): _assert_unit_at("WBC", 3)
def test_unit_RBC_0(): _assert_unit_at("RBC", 0)
def test_unit_RBC_1(): _assert_unit_at("RBC", 1)
def test_unit_RBC_2(): _assert_unit_at("RBC", 2)
def test_unit_HGB_0(): _assert_unit_at("HGB", 0)
def test_unit_HGB_1(): _assert_unit_at("HGB", 1)
def test_unit_HGB_2(): _assert_unit_at("HGB", 2)
def test_unit_HCT_0(): _assert_unit_at("HCT", 0)
def test_unit_HCT_1(): _assert_unit_at("HCT", 1)
def test_unit_HCT_2(): _assert_unit_at("HCT", 2)
def test_unit_PLT_0(): _assert_unit_at("PLT", 0)
def test_unit_PLT_1(): _assert_unit_at("PLT", 1)
def test_unit_PLT_2(): _assert_unit_at("PLT", 2)
def test_unit_ALT_0(): _assert_unit_at("ALT", 0)
def test_unit_ALT_1(): _assert_unit_at("ALT", 1)
def test_unit_ALT_2(): _assert_unit_at("ALT", 2)
def test_unit_ALT_3(): _assert_unit_at("ALT", 3)
def test_unit_AST_0(): _assert_unit_at("AST", 0)
def test_unit_AST_1(): _assert_unit_at("AST", 1)
def test_unit_AST_2(): _assert_unit_at("AST", 2)
def test_unit_ALP_0(): _assert_unit_at("ALP", 0)
def test_unit_ALP_1(): _assert_unit_at("ALP", 1)
def test_unit_ALP_2(): _assert_unit_at("ALP", 2)
def test_unit_GGT_0(): _assert_unit_at("GGT", 0)
def test_unit_GGT_1(): _assert_unit_at("GGT", 1)
def test_unit_GGT_2(): _assert_unit_at("GGT", 2)
def test_unit_TBIL_0(): _assert_unit_at("TBIL", 0)
def test_unit_TBIL_1(): _assert_unit_at("TBIL", 1)
def test_unit_TBIL_2(): _assert_unit_at("TBIL", 2)
def test_unit_TP_0(): _assert_unit_at("TP", 0)
def test_unit_TP_1(): _assert_unit_at("TP", 1)
def test_unit_TP_2(): _assert_unit_at("TP", 2)
def test_unit_TC_0(): _assert_unit_at("TC", 0)
def test_unit_TC_1(): _assert_unit_at("TC", 1)
def test_unit_TG_0(): _assert_unit_at("TG", 0)
def test_unit_TG_1(): _assert_unit_at("TG", 1)
def test_unit_HDLC_0(): _assert_unit_at("HDL-C", 0)
def test_unit_HDLC_1(): _assert_unit_at("HDL-C", 1)
def test_unit_LDLC_0(): _assert_unit_at("LDL-C", 0)
def test_unit_LDLC_1(): _assert_unit_at("LDL-C", 1)
def test_unit_CREA_0(): _assert_unit_at("CREA", 0)
def test_unit_CREA_1(): _assert_unit_at("CREA", 1)
def test_unit_CREA_2(): _assert_unit_at("CREA", 2)
def test_unit_UREA_0(): _assert_unit_at("UREA", 0)
def test_unit_UREA_1(): _assert_unit_at("UREA", 1)
def test_unit_UA_0(): _assert_unit_at("UA", 0)
def test_unit_UA_1(): _assert_unit_at("UA", 1)
def test_unit_GLU_0(): _assert_unit_at("GLU", 0)
def test_unit_GLU_1(): _assert_unit_at("GLU", 1)


def test_name_normalization_tolerates_spaces_and_case():
    assert engine.normalize_name(" wbc 白细胞 ", INDICATORS).canonical_name == "WBC"
    assert engine.normalize_name("hdlc", INDICATORS).canonical_name == "HDL-C"


def test_unknown_name_is_refused_not_guessed():
    assert engine.normalize_name("不存在的指标", INDICATORS) is None


def test_substring_name_is_not_matched():
    """不做子串匹配："白细胞" 能命中，但 "白细胞计数X" 不能。"""
    assert engine.normalize_name("白细胞计数X", INDICATORS) is None


def test_unknown_unit_is_refused():
    indicator = engine.find_indicator("WBC", INDICATORS)
    assert engine.normalize_unit("mg/dL", indicator) is None


def test_unit_normalization_tolerates_spaces_and_case():
    indicator = engine.find_indicator("WBC", INDICATORS)
    assert engine.normalize_unit(" 10e9/l ", indicator) == "10^9/L"


# ==========================================================================
# 四、四态比较（闭/开区间、单侧区间、边界）
# ==========================================================================
def _flag_printed(canonical, kind):
    ind = engine.find_indicator(canonical, INDICATORS)
    if kind == "single_sided":
        return flag_of(measure(ind, -1e6, engine.RefRange(
            low=None, high=ind.high, bounds="closed", source=RANGE_REPORT)))
    if kind == "normal":
        value, bounds = _midpoint(ind), "closed"
    elif kind == "high":
        value, bounds = ind.high + 0.1, "closed"
    elif kind == "low":
        value, bounds = ind.low - 0.1, "closed"
    elif kind == "closed_low":
        value, bounds = ind.low, "closed"
    elif kind == "closed_high":
        value, bounds = ind.high, "closed"
    elif kind == "open_low":
        value, bounds = ind.low, "open"
    elif kind == "open_high":
        value, bounds = ind.high, "open"
    else:
        raise AssertionError(kind)
    return flag_of(measure(ind, value, engine.RefRange(
        low=ind.low, high=ind.high, bounds=bounds, source=RANGE_REPORT)))


# ---- 19 条区间 × 三态 + 边界（闭/开/单侧），逐条一条用例 ----
def test_printed_normal_WBC(): assert _flag_printed("WBC", "normal") == FLAG_NORMAL
def test_printed_high_WBC(): assert _flag_printed("WBC", "high") == FLAG_HIGH
def test_printed_low_WBC(): assert _flag_printed("WBC", "low") == FLAG_LOW
def test_printed_closed_low_WBC(): assert _flag_printed("WBC", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_WBC(): assert _flag_printed("WBC", "closed_high") == FLAG_NORMAL
def test_printed_open_low_WBC(): assert _flag_printed("WBC", "open_low") == FLAG_LOW
def test_printed_open_high_WBC(): assert _flag_printed("WBC", "open_high") == FLAG_HIGH
def test_printed_single_sided_WBC(): assert _flag_printed("WBC", "single_sided") == FLAG_NORMAL
def test_printed_normal_RBC(): assert _flag_printed("RBC", "normal") == FLAG_NORMAL
def test_printed_high_RBC(): assert _flag_printed("RBC", "high") == FLAG_HIGH
def test_printed_low_RBC(): assert _flag_printed("RBC", "low") == FLAG_LOW
def test_printed_closed_low_RBC(): assert _flag_printed("RBC", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_RBC(): assert _flag_printed("RBC", "closed_high") == FLAG_NORMAL
def test_printed_open_low_RBC(): assert _flag_printed("RBC", "open_low") == FLAG_LOW
def test_printed_open_high_RBC(): assert _flag_printed("RBC", "open_high") == FLAG_HIGH
def test_printed_single_sided_RBC(): assert _flag_printed("RBC", "single_sided") == FLAG_NORMAL
def test_printed_normal_HGB(): assert _flag_printed("HGB", "normal") == FLAG_NORMAL
def test_printed_high_HGB(): assert _flag_printed("HGB", "high") == FLAG_HIGH
def test_printed_low_HGB(): assert _flag_printed("HGB", "low") == FLAG_LOW
def test_printed_closed_low_HGB(): assert _flag_printed("HGB", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_HGB(): assert _flag_printed("HGB", "closed_high") == FLAG_NORMAL
def test_printed_open_low_HGB(): assert _flag_printed("HGB", "open_low") == FLAG_LOW
def test_printed_open_high_HGB(): assert _flag_printed("HGB", "open_high") == FLAG_HIGH
def test_printed_single_sided_HGB(): assert _flag_printed("HGB", "single_sided") == FLAG_NORMAL
def test_printed_normal_HCT(): assert _flag_printed("HCT", "normal") == FLAG_NORMAL
def test_printed_high_HCT(): assert _flag_printed("HCT", "high") == FLAG_HIGH
def test_printed_low_HCT(): assert _flag_printed("HCT", "low") == FLAG_LOW
def test_printed_closed_low_HCT(): assert _flag_printed("HCT", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_HCT(): assert _flag_printed("HCT", "closed_high") == FLAG_NORMAL
def test_printed_open_low_HCT(): assert _flag_printed("HCT", "open_low") == FLAG_LOW
def test_printed_open_high_HCT(): assert _flag_printed("HCT", "open_high") == FLAG_HIGH
def test_printed_single_sided_HCT(): assert _flag_printed("HCT", "single_sided") == FLAG_NORMAL
def test_printed_normal_PLT(): assert _flag_printed("PLT", "normal") == FLAG_NORMAL
def test_printed_high_PLT(): assert _flag_printed("PLT", "high") == FLAG_HIGH
def test_printed_low_PLT(): assert _flag_printed("PLT", "low") == FLAG_LOW
def test_printed_closed_low_PLT(): assert _flag_printed("PLT", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_PLT(): assert _flag_printed("PLT", "closed_high") == FLAG_NORMAL
def test_printed_open_low_PLT(): assert _flag_printed("PLT", "open_low") == FLAG_LOW
def test_printed_open_high_PLT(): assert _flag_printed("PLT", "open_high") == FLAG_HIGH
def test_printed_single_sided_PLT(): assert _flag_printed("PLT", "single_sided") == FLAG_NORMAL
def test_printed_normal_ALT(): assert _flag_printed("ALT", "normal") == FLAG_NORMAL
def test_printed_high_ALT(): assert _flag_printed("ALT", "high") == FLAG_HIGH
def test_printed_low_ALT(): assert _flag_printed("ALT", "low") == FLAG_LOW
def test_printed_closed_low_ALT(): assert _flag_printed("ALT", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_ALT(): assert _flag_printed("ALT", "closed_high") == FLAG_NORMAL
def test_printed_open_low_ALT(): assert _flag_printed("ALT", "open_low") == FLAG_LOW
def test_printed_open_high_ALT(): assert _flag_printed("ALT", "open_high") == FLAG_HIGH
def test_printed_single_sided_ALT(): assert _flag_printed("ALT", "single_sided") == FLAG_NORMAL
def test_printed_normal_AST(): assert _flag_printed("AST", "normal") == FLAG_NORMAL
def test_printed_high_AST(): assert _flag_printed("AST", "high") == FLAG_HIGH
def test_printed_low_AST(): assert _flag_printed("AST", "low") == FLAG_LOW
def test_printed_closed_low_AST(): assert _flag_printed("AST", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_AST(): assert _flag_printed("AST", "closed_high") == FLAG_NORMAL
def test_printed_open_low_AST(): assert _flag_printed("AST", "open_low") == FLAG_LOW
def test_printed_open_high_AST(): assert _flag_printed("AST", "open_high") == FLAG_HIGH
def test_printed_single_sided_AST(): assert _flag_printed("AST", "single_sided") == FLAG_NORMAL
def test_printed_normal_ALP(): assert _flag_printed("ALP", "normal") == FLAG_NORMAL
def test_printed_high_ALP(): assert _flag_printed("ALP", "high") == FLAG_HIGH
def test_printed_low_ALP(): assert _flag_printed("ALP", "low") == FLAG_LOW
def test_printed_closed_low_ALP(): assert _flag_printed("ALP", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_ALP(): assert _flag_printed("ALP", "closed_high") == FLAG_NORMAL
def test_printed_open_low_ALP(): assert _flag_printed("ALP", "open_low") == FLAG_LOW
def test_printed_open_high_ALP(): assert _flag_printed("ALP", "open_high") == FLAG_HIGH
def test_printed_single_sided_ALP(): assert _flag_printed("ALP", "single_sided") == FLAG_NORMAL
def test_printed_normal_GGT(): assert _flag_printed("GGT", "normal") == FLAG_NORMAL
def test_printed_high_GGT(): assert _flag_printed("GGT", "high") == FLAG_HIGH
def test_printed_low_GGT(): assert _flag_printed("GGT", "low") == FLAG_LOW
def test_printed_closed_low_GGT(): assert _flag_printed("GGT", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_GGT(): assert _flag_printed("GGT", "closed_high") == FLAG_NORMAL
def test_printed_open_low_GGT(): assert _flag_printed("GGT", "open_low") == FLAG_LOW
def test_printed_open_high_GGT(): assert _flag_printed("GGT", "open_high") == FLAG_HIGH
def test_printed_single_sided_GGT(): assert _flag_printed("GGT", "single_sided") == FLAG_NORMAL
def test_printed_normal_TBIL(): assert _flag_printed("TBIL", "normal") == FLAG_NORMAL
def test_printed_high_TBIL(): assert _flag_printed("TBIL", "high") == FLAG_HIGH
def test_printed_low_TBIL(): assert _flag_printed("TBIL", "low") == FLAG_LOW
def test_printed_closed_low_TBIL(): assert _flag_printed("TBIL", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_TBIL(): assert _flag_printed("TBIL", "closed_high") == FLAG_NORMAL
def test_printed_open_low_TBIL(): assert _flag_printed("TBIL", "open_low") == FLAG_LOW
def test_printed_open_high_TBIL(): assert _flag_printed("TBIL", "open_high") == FLAG_HIGH
def test_printed_single_sided_TBIL(): assert _flag_printed("TBIL", "single_sided") == FLAG_NORMAL
def test_printed_normal_TP(): assert _flag_printed("TP", "normal") == FLAG_NORMAL
def test_printed_high_TP(): assert _flag_printed("TP", "high") == FLAG_HIGH
def test_printed_low_TP(): assert _flag_printed("TP", "low") == FLAG_LOW
def test_printed_closed_low_TP(): assert _flag_printed("TP", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_TP(): assert _flag_printed("TP", "closed_high") == FLAG_NORMAL
def test_printed_open_low_TP(): assert _flag_printed("TP", "open_low") == FLAG_LOW
def test_printed_open_high_TP(): assert _flag_printed("TP", "open_high") == FLAG_HIGH
def test_printed_single_sided_TP(): assert _flag_printed("TP", "single_sided") == FLAG_NORMAL
def test_printed_normal_TC(): assert _flag_printed("TC", "normal") == FLAG_NORMAL
def test_printed_high_TC(): assert _flag_printed("TC", "high") == FLAG_HIGH
def test_printed_closed_high_TC(): assert _flag_printed("TC", "closed_high") == FLAG_NORMAL
def test_printed_open_high_TC(): assert _flag_printed("TC", "open_high") == FLAG_HIGH
def test_printed_single_sided_TC(): assert _flag_printed("TC", "single_sided") == FLAG_NORMAL
def test_printed_normal_TG(): assert _flag_printed("TG", "normal") == FLAG_NORMAL
def test_printed_high_TG(): assert _flag_printed("TG", "high") == FLAG_HIGH
def test_printed_closed_high_TG(): assert _flag_printed("TG", "closed_high") == FLAG_NORMAL
def test_printed_open_high_TG(): assert _flag_printed("TG", "open_high") == FLAG_HIGH
def test_printed_single_sided_TG(): assert _flag_printed("TG", "single_sided") == FLAG_NORMAL
def test_printed_normal_HDLC(): assert _flag_printed("HDL-C", "normal") == FLAG_NORMAL
def test_printed_high_HDLC(): assert _flag_printed("HDL-C", "high") == FLAG_HIGH
def test_printed_low_HDLC(): assert _flag_printed("HDL-C", "low") == FLAG_LOW
def test_printed_closed_low_HDLC(): assert _flag_printed("HDL-C", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_HDLC(): assert _flag_printed("HDL-C", "closed_high") == FLAG_NORMAL
def test_printed_open_low_HDLC(): assert _flag_printed("HDL-C", "open_low") == FLAG_LOW
def test_printed_open_high_HDLC(): assert _flag_printed("HDL-C", "open_high") == FLAG_HIGH
def test_printed_single_sided_HDLC(): assert _flag_printed("HDL-C", "single_sided") == FLAG_NORMAL
def test_printed_normal_LDLC(): assert _flag_printed("LDL-C", "normal") == FLAG_NORMAL
def test_printed_high_LDLC(): assert _flag_printed("LDL-C", "high") == FLAG_HIGH
def test_printed_closed_high_LDLC(): assert _flag_printed("LDL-C", "closed_high") == FLAG_NORMAL
def test_printed_open_high_LDLC(): assert _flag_printed("LDL-C", "open_high") == FLAG_HIGH
def test_printed_single_sided_LDLC(): assert _flag_printed("LDL-C", "single_sided") == FLAG_NORMAL
def test_printed_normal_CREA(): assert _flag_printed("CREA", "normal") == FLAG_NORMAL
def test_printed_high_CREA(): assert _flag_printed("CREA", "high") == FLAG_HIGH
def test_printed_low_CREA(): assert _flag_printed("CREA", "low") == FLAG_LOW
def test_printed_closed_low_CREA(): assert _flag_printed("CREA", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_CREA(): assert _flag_printed("CREA", "closed_high") == FLAG_NORMAL
def test_printed_open_low_CREA(): assert _flag_printed("CREA", "open_low") == FLAG_LOW
def test_printed_open_high_CREA(): assert _flag_printed("CREA", "open_high") == FLAG_HIGH
def test_printed_single_sided_CREA(): assert _flag_printed("CREA", "single_sided") == FLAG_NORMAL
def test_printed_normal_UREA(): assert _flag_printed("UREA", "normal") == FLAG_NORMAL
def test_printed_high_UREA(): assert _flag_printed("UREA", "high") == FLAG_HIGH
def test_printed_low_UREA(): assert _flag_printed("UREA", "low") == FLAG_LOW
def test_printed_closed_low_UREA(): assert _flag_printed("UREA", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_UREA(): assert _flag_printed("UREA", "closed_high") == FLAG_NORMAL
def test_printed_open_low_UREA(): assert _flag_printed("UREA", "open_low") == FLAG_LOW
def test_printed_open_high_UREA(): assert _flag_printed("UREA", "open_high") == FLAG_HIGH
def test_printed_single_sided_UREA(): assert _flag_printed("UREA", "single_sided") == FLAG_NORMAL
def test_printed_normal_UA(): assert _flag_printed("UA", "normal") == FLAG_NORMAL
def test_printed_high_UA(): assert _flag_printed("UA", "high") == FLAG_HIGH
def test_printed_low_UA(): assert _flag_printed("UA", "low") == FLAG_LOW
def test_printed_closed_low_UA(): assert _flag_printed("UA", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_UA(): assert _flag_printed("UA", "closed_high") == FLAG_NORMAL
def test_printed_open_low_UA(): assert _flag_printed("UA", "open_low") == FLAG_LOW
def test_printed_open_high_UA(): assert _flag_printed("UA", "open_high") == FLAG_HIGH
def test_printed_single_sided_UA(): assert _flag_printed("UA", "single_sided") == FLAG_NORMAL
def test_printed_normal_GLU(): assert _flag_printed("GLU", "normal") == FLAG_NORMAL
def test_printed_high_GLU(): assert _flag_printed("GLU", "high") == FLAG_HIGH
def test_printed_low_GLU(): assert _flag_printed("GLU", "low") == FLAG_LOW
def test_printed_closed_low_GLU(): assert _flag_printed("GLU", "closed_low") == FLAG_NORMAL
def test_printed_closed_high_GLU(): assert _flag_printed("GLU", "closed_high") == FLAG_NORMAL
def test_printed_open_low_GLU(): assert _flag_printed("GLU", "open_low") == FLAG_LOW
def test_printed_open_high_GLU(): assert _flag_printed("GLU", "open_high") == FLAG_HIGH
def test_printed_single_sided_GLU(): assert _flag_printed("GLU", "single_sided") == FLAG_NORMAL


def test_compare_returns_not_assessed_when_no_bounds():
    assert engine.compare(1.0, engine.RefRange()) == FLAG_NOT_ASSESSED


def test_compare_ignores_bounds_of_single_side():
    assert engine.compare(5.0, ref(None, 4.0)) == FLAG_HIGH
    assert engine.compare(5.0, ref(6.0, None)) == FLAG_LOW


def test_compare_is_deterministic():
    assert engine.compare(3.5, ref(3.5, 9.5)) == engine.compare(3.5, ref(3.5, 9.5))


# ==========================================================================
# 五、区间结构门（缺陷显式暴露，不静默降级成"拒判"）
# ==========================================================================
def test_unknown_bounds_is_error():
    with pytest.raises(engine.RangeError):
        engine.validate_range(ref(1.0, 2.0, bounds="half"))


def test_unknown_source_is_error():
    with pytest.raises(engine.RangeError):
        engine.validate_range(engine.RefRange(low=1.0, high=2.0, source="oracle"))


def test_low_above_high_is_error():
    with pytest.raises(engine.RangeError):
        engine.validate_range(ref(9.0, 1.0))


def test_no_bounds_but_claims_source_is_error():
    with pytest.raises(engine.RangeError):
        engine.validate_range(ref(None, None, source=RANGE_REPORT))


def test_no_bounds_with_none_source_is_legal():
    engine.validate_range(engine.RefRange())


def test_single_bound_is_legal():
    engine.validate_range(ref(None, 5.2))
    engine.validate_range(ref(3.9, None))


def test_subject_with_unknown_bounds_is_input_error():
    with pytest.raises(engine.RangeError):
        engine.validate_subject(subject(range={"low": 1, "high": 2, "bounds": "half"}))


def test_subject_with_inverted_range_is_input_error():
    with pytest.raises(engine.RangeError):
        engine.validate_subject(subject(range={"low": 9, "high": 2}))


def test_subject_range_bound_must_be_numeric():
    with pytest.raises(engine.CheckupError):
        engine.validate_subject(subject(range={"low": "3.5", "high": 9.5}))


def test_subject_range_must_be_object():
    with pytest.raises(engine.CheckupError):
        engine.validate_subject(subject(range=[3.5, 9.5]))


# ==========================================================================
# 六、主体适用域（sex 硬门）
# ==========================================================================
SEXED = [i for i in INDICATORS if i.sex != "any"]
UNSEXED = [i for i in INDICATORS if i.sex == "any"]


def _assert_sex_mismatch(canonical):
    ind = engine.find_indicator(canonical, INDICATORS)
    other = "female" if ind.sex == "male" else "male"
    assert engine.range_applies_to(ind.sex, other) is False, canonical


def _assert_sex_match(canonical):
    ind = engine.find_indicator(canonical, INDICATORS)
    assert engine.range_applies_to(ind.sex, ind.sex) is True, canonical


def _assert_sex_any(canonical):
    ind = engine.find_indicator(canonical, INDICATORS)
    assert engine.range_applies_to(ind.sex, None) is True, canonical


# ---- 5 条性别约束条目 × 两向（逐条一条用例）----
def test_sex_RBC_mismatch(): _assert_sex_mismatch("RBC")
def test_sex_RBC_match(): _assert_sex_match("RBC")
def test_sex_HGB_mismatch(): _assert_sex_mismatch("HGB")
def test_sex_HGB_match(): _assert_sex_match("HGB")
def test_sex_HCT_mismatch(): _assert_sex_mismatch("HCT")
def test_sex_HCT_match(): _assert_sex_match("HCT")
def test_sex_GGT_mismatch(): _assert_sex_mismatch("GGT")
def test_sex_GGT_match(): _assert_sex_match("GGT")
def test_sex_UA_mismatch(): _assert_sex_mismatch("UA")
def test_sex_UA_match(): _assert_sex_match("UA")


# ---- 14 条 any 条目：主体未知也适用（逐条一条用例）----
def test_sex_any_WBC(): _assert_sex_any("WBC")
def test_sex_any_PLT(): _assert_sex_any("PLT")
def test_sex_any_ALT(): _assert_sex_any("ALT")
def test_sex_any_AST(): _assert_sex_any("AST")
def test_sex_any_ALP(): _assert_sex_any("ALP")
def test_sex_any_TBIL(): _assert_sex_any("TBIL")
def test_sex_any_TP(): _assert_sex_any("TP")
def test_sex_any_TC(): _assert_sex_any("TC")
def test_sex_any_TG(): _assert_sex_any("TG")
def test_sex_any_HDLC(): _assert_sex_any("HDL-C")
def test_sex_any_LDLC(): _assert_sex_any("LDL-C")
def test_sex_any_CREA(): _assert_sex_any("CREA")
def test_sex_any_UREA(): _assert_sex_any("UREA")
def test_sex_any_GLU(): _assert_sex_any("GLU")


def test_sex_constraint_unknown_value_is_error():
    with pytest.raises(engine.RangeError):
        engine.range_applies_to("other", "male")


def test_subject_sex_unknown_value_is_input_error():
    with pytest.raises(engine.CheckupError):
        engine.validate_subject(subject(subject_sex="other"))


def test_printed_range_ignores_sex_constraint():
    """报告自印区间是该受检者报告上的区间，主体天然适用。"""
    hgb = engine.find_indicator("HGB", INDICATORS)
    data = measure(hgb, 200.0, printed(hgb))
    data["subject_sex"] = "female"
    assert flag_of(data) == FLAG_HIGH


# ==========================================================================
# 七、三级优先选区间
# ==========================================================================
def test_printed_range_wins_over_builtin_default():
    chosen = engine.select_range(ref(50.0, 60.0), ref(57.0, 97.0), subject_sex=None,
                                 default_constraint="any")
    assert chosen.source == RANGE_REPORT
    assert (chosen.low, chosen.high) == (50.0, 60.0)


def test_builtin_default_used_when_no_printed_range():
    chosen = engine.select_range(None, ref(57.0, 97.0, source=RANGE_BUILTIN),
                                 subject_sex="male", default_constraint="male")
    assert chosen.source == RANGE_BUILTIN


def test_builtin_default_skipped_when_sex_mismatches():
    chosen = engine.select_range(None, ref(130.0, 175.0, source=RANGE_BUILTIN),
                                 subject_sex="female", default_constraint="male")
    assert chosen.source == RANGE_NONE
    assert chosen.low is None and chosen.high is None


def test_no_range_at_all_is_refused():
    chosen = engine.select_range(None, None, subject_sex="male")
    assert chosen.source == RANGE_NONE


def test_printed_range_is_validated_before_use():
    with pytest.raises(engine.RangeError):
        engine.select_range(ref(9.0, 1.0), None)


def test_unknown_indicator_is_refused():
    raw = pack_mod.judge({"canonical_name": "外星指标", "value": 1.0, "unit": "x"})
    assert raw.flag == FLAG_NOT_ASSESSED
    assert raw.code == "indicator_unknown"
    assert raw.clause_id is None


def test_unknown_unit_is_refused_with_reason():
    raw = pack_mod.judge({"canonical_name": "WBC", "value": 6.0, "unit": "mg/dL"})
    assert raw.flag == FLAG_NOT_ASSESSED
    assert raw.code == "unit_unknown"
    assert raw.clause_id is None


def test_pending_builtin_range_is_refused_with_reason():
    """内置条目全 pending → 无自印区间时拒判，并把"为什么"写进 code。"""
    raw = pack_mod.judge(subject())
    assert raw.flag == FLAG_NOT_ASSESSED
    assert raw.code == "builtin_pending"
    assert raw.clause_id is None


def test_sex_mismatch_refusal_reason():
    hgb = engine.find_indicator("HGB", INDICATORS)
    probe = tuple([engine.Indicator(
        canonical_name=hgb.canonical_name, display_name=hgb.display_name,
        aliases=hgb.aliases, unit=hgb.unit, unit_aliases=hgb.unit_aliases,
        low=hgb.low, high=hgb.high, bounds=hgb.bounds, sex=hgb.sex,
        standard=hgb.standard, status=engine.STATUS_VERIFIED)])
    raw = pack_mod.judge({"canonical_name": "HGB", "value": 140.0, "unit": "g/L",
                          "subject_sex": "female"}, probe)
    assert raw.flag == FLAG_NOT_ASSESSED
    assert raw.code == "range_not_applicable"


# ==========================================================================
# 八、已核对条目（verified）的完整通路（当前知识库为 0 条，用探针条目验活）
# ==========================================================================
def verified_probe(canonical="PROBE", low=10.0, high=20.0, sex="any"):
    return (engine.Indicator(
        canonical_name=canonical, display_name=canonical, aliases=("探针指标",),
        unit="U/L", unit_aliases=("U/L",), low=low, high=high, bounds="closed",
        sex=sex, standard="WS/T 9999-2099", status=engine.STATUS_VERIFIED),)


def test_verified_entry_judges_with_builtin_range():
    raw = pack_mod.judge({"canonical_name": "PROBE", "value": 25.0, "unit": "U/L"},
                         verified_probe())
    assert raw.flag == FLAG_HIGH
    assert raw.range_source == RANGE_BUILTIN
    assert raw.clause_id == "wst:PROBE"


def test_verified_entry_normal_case():
    raw = pack_mod.judge({"canonical_name": "PROBE", "value": 15.0, "unit": "U/L"},
                         verified_probe())
    assert raw.flag == FLAG_NORMAL
    assert raw.clause_id == "wst:PROBE"


def test_verified_entry_low_case():
    raw = pack_mod.judge({"canonical_name": "PROBE", "value": 1.0, "unit": "U/L"},
                         verified_probe())
    assert raw.flag == FLAG_LOW


def test_verified_entry_still_yields_to_printed_range():
    raw = pack_mod.judge({"canonical_name": "PROBE", "value": 25.0, "unit": "U/L",
                          "range": {"low": 10.0, "high": 30.0}}, verified_probe())
    assert raw.flag == FLAG_NORMAL
    assert raw.range_source == RANGE_REPORT


def test_verified_entry_clause_must_exist_in_basis():
    """已核对条目要锚定 wst:<指标>；条文库没有该条目 → 契约违约（冒到 CLI）。"""
    probe = verified_probe()
    raw = pack_mod.judge({"canonical_name": "PROBE", "value": 25.0, "unit": "U/L"}, probe)
    assert raw.clause_id == "wst:PROBE"
    basis = Basis.from_json(basis_path())
    assert "wst:PROBE" not in basis.clause_ids()
    with pytest.raises(BasisMissing):
        pack_mod._to_finding(raw, basis)


def test_verified_entry_is_anchorable_once_the_clause_exists():
    probe = verified_probe()
    raw = pack_mod.judge({"canonical_name": "PROBE", "value": 25.0, "unit": "U/L"}, probe)
    basis = Basis.from_dict({
        "version": registry.REGISTRY_VERSION,
        "clauses": [{"clause_id": "wst:PROBE", "path": "WS/T 9999-2099/探针指标",
                     "text": "探针区间 10–20 U/L"}],
    })
    finding = pack_mod._to_finding(raw, basis)
    assert finding.verdict == FAIL
    assert finding.anchor.clause_id == "wst:PROBE"


# ==========================================================================
# 九、账本映射：verdict / 锚点 / 退出码
# ==========================================================================
def test_normal_maps_to_pass_with_report_anchor():
    data = {"canonical_name": "TC", "value": 5.2, "unit": "mmol/L",
            "range": {"low": None, "high": 5.2, "bounds": "closed"}}
    findings = pack_mod.evaluate(data, shipped_basis())
    assert len(findings) == 1
    finding = findings[0]
    assert finding.verdict == PASS
    assert finding.anchor.clause_id == "range:report-printed"
    assert finding.anchor.version == registry.REGISTRY_VERSION


def test_high_maps_to_fail_with_report_anchor():
    data = {"canonical_name": "ALT", "value": 43.0, "unit": "U/L",
            "range": {"low": 9.0, "high": 40.0, "bounds": "closed"}}
    finding = pack_mod.evaluate(data, shipped_basis())[0]
    assert finding.verdict == FAIL
    assert finding.anchor.clause_id == "range:report-printed"
    assert finding.evidence["flag"] == FLAG_HIGH


def test_low_maps_to_fail():
    data = {"canonical_name": "ALT", "value": 1.0, "unit": "U/L",
            "range": {"low": 9.0, "high": 40.0, "bounds": "closed"}}
    assert pack_mod.evaluate(data, shipped_basis())[0].verdict == FAIL


def test_refusal_maps_to_not_applicable_without_anchor():
    finding = pack_mod.evaluate(subject(), shipped_basis())[0]
    assert finding.verdict == NOT_APPLICABLE
    assert finding.anchor is None
    assert "builtin_pending" in finding.message


def test_record_id_is_stable_and_derived():
    finding = pack_mod.evaluate(subject(), shipped_basis())[0]
    assert finding.id == "measurement.range:WBC@na"


def test_record_id_carries_clause_when_anchored():
    data = {"canonical_name": "WBC", "value": 6.0, "unit": "10^9/L",
            "range": {"low": 3.5, "high": 9.5, "bounds": "closed"}}
    finding = pack_mod.evaluate(data, shipped_basis())[0]
    assert finding.id == "measurement.range:WBC@range:report-printed"


def test_every_fail_carries_full_basis_ref():
    data = {"canonical_name": "WBC", "value": 99.0, "unit": "10^9/L",
            "range": {"low": 3.5, "high": 9.5, "bounds": "closed"}}
    payload = pack_mod.evaluate(data, shipped_basis())[0].as_dict()
    assert payload["basis_ref"]["clause_id"]
    assert payload["basis_ref"]["path"]
    assert payload["basis_ref"]["version"]


def test_evidence_carries_range_and_standard():
    data = {"canonical_name": "HGB", "value": 100.0, "unit": "g/L",
            "range": {"low": 130.0, "high": 175.0, "bounds": "closed"}}
    evidence = pack_mod.evaluate(data, shipped_basis())[0].evidence
    assert evidence["range_low"] == 130.0
    assert evidence["range_high"] == 175.0
    assert evidence["standard"] == "WS/T 405-2012"
    assert evidence["registry_status"] == engine.STATUS_PENDING


def test_output_is_deterministic():
    data = {"canonical_name": "ALT", "value": 43.0, "unit": "U/L",
            "range": {"low": 9.0, "high": 40.0, "bounds": "closed"}}
    first = json.dumps(report_of(data).as_dict(), ensure_ascii=False)
    second = json.dumps(report_of(data).as_dict(), ensure_ascii=False)
    assert first == second
    assert ROOT not in first


def test_basis_version_mismatch_is_contract_error():
    basis = Basis(version="1999-01-01", clauses=())
    with pytest.raises(ContractError):
        pack_mod.evaluate(subject(), basis)


def test_missing_clause_propagates_basis_missing():
    data = {"canonical_name": "WBC", "value": 6.0, "unit": "10^9/L",
            "range": {"low": 3.5, "high": 9.5, "bounds": "closed"}}
    with pytest.raises(BasisMissing):
        pack_mod.evaluate(data, Basis(version=registry.REGISTRY_VERSION, clauses=()))


# ==========================================================================
# 十、输入校验（退出码 2）
# ==========================================================================
def test_subject_rejects_non_mapping():
    with pytest.raises(engine.CheckupError):
        engine.validate_subject(["x"])


def test_subject_rejects_blank_name():
    with pytest.raises(engine.CheckupError):
        engine.validate_subject(subject(canonical_name="  "))


def test_subject_rejects_non_numeric_value():
    for bad in ("6.0", None, True, [6]):
        with pytest.raises(engine.CheckupError):
            engine.validate_subject(subject(value=bad))


def test_subject_rejects_non_string_unit():
    with pytest.raises(engine.CheckupError):
        engine.validate_subject(subject(unit=10))


def test_subject_accepts_null_unit():
    engine.validate_subject(subject(unit=None))


def test_subject_accepts_int_value():
    engine.validate_subject(subject(value=6))


def test_subject_accepts_missing_unit():
    engine.validate_subject({"canonical_name": "WBC", "value": 6.0})


# ==========================================================================
# 十一、样例真值 parity（来源 data/samples/truth 的 20 条记录）
# ==========================================================================
def _assert_sample(index):
    record = sample_records()[index]
    assert flag_of(record["subject"]) == record["expected_flag"], record["case_id"]


# ---- 20 条来源真值记录逐条一条用例 ----
def test_sample_00(): _assert_sample(0)
def test_sample_01(): _assert_sample(1)
def test_sample_02(): _assert_sample(2)
def test_sample_03(): _assert_sample(3)
def test_sample_04(): _assert_sample(4)
def test_sample_05(): _assert_sample(5)
def test_sample_06(): _assert_sample(6)
def test_sample_07(): _assert_sample(7)
def test_sample_08(): _assert_sample(8)
def test_sample_09(): _assert_sample(9)
def test_sample_10(): _assert_sample(10)
def test_sample_11(): _assert_sample(11)
def test_sample_12(): _assert_sample(12)
def test_sample_13(): _assert_sample(13)
def test_sample_14(): _assert_sample(14)
def test_sample_15(): _assert_sample(15)
def test_sample_16(): _assert_sample(16)
def test_sample_17(): _assert_sample(17)
def test_sample_18(): _assert_sample(18)
def test_sample_19(): _assert_sample(19)


def test_sample_file_is_shipped_and_complete():
    records = sample_records()
    assert len(records) == 20
    assert {r["expected_flag"] for r in records} == {FLAG_NORMAL, FLAG_HIGH,
                                                     FLAG_NOT_ASSESSED}


def test_sample_with_printed_range_overrides_bench_default():
    """来源基准夹具注入了 default_range 期望 low；产品通路（全 pending）应拒判。"""
    record = [r for r in sample_records() if r["case_id"] == "case-005-wangwu-2024"][0]
    assert record["bench_flag"] == "low"
    assert record["bench_range_source"] == RANGE_BUILTIN
    assert record["expected_flag"] == FLAG_NOT_ASSESSED


# ==========================================================================
# 十二、唯一入口（CLI）：退出码 0/1/2/3
# ==========================================================================
def _write(tmp_path, name, payload):
    target = tmp_path / name
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(target)


def test_cli_list_shows_the_organ(capsys):
    assert cp_cli.main(["list"]) == EXIT_OK
    assert SLUG in capsys.readouterr().out


def test_cli_check_normal_exits_zero(capsys, tmp_path):
    target = _write(tmp_path, "normal.json",
                    {"canonical_name": "TC", "value": 5.2, "unit": "mmol/L",
                     "range": {"low": None, "high": 5.2}})
    assert cp_cli.main(["check", SLUG, "--input", target,
                        "--basis", basis_path()]) == EXIT_OK


def test_cli_check_high_exits_one(capsys, tmp_path):
    target = _write(tmp_path, "high.json",
                    {"canonical_name": "ALT", "value": 43.0, "unit": "U/L",
                     "range": {"low": 9.0, "high": 40.0}})
    assert cp_cli.main(["check", SLUG, "--input", target,
                        "--basis", basis_path()]) == EXIT_BLOCKED


def test_cli_check_without_basis_is_contract_violation(capsys, tmp_path):
    target = _write(tmp_path, "normal.json",
                    {"canonical_name": "TC", "value": 5.2, "unit": "mmol/L",
                     "range": {"low": None, "high": 5.2}})
    assert cp_cli.main(["check", SLUG, "--input", target]) == EXIT_CONTRACT


def test_cli_check_bad_subject_exits_two(capsys, tmp_path):
    target = _write(tmp_path, "bad.json", {"canonical_name": "WBC", "value": "six"})
    assert cp_cli.main(["check", SLUG, "--input", target,
                        "--basis", basis_path()]) == EXIT_INPUT


def test_cli_check_missing_file_exits_two(capsys, tmp_path):
    assert cp_cli.main(["check", SLUG, "--input", str(tmp_path / "nope.json"),
                        "--basis", basis_path()]) == EXIT_INPUT


def test_cli_json_is_byte_identical_across_two_runs(capsys, tmp_path):
    target = _write(tmp_path, "high.json",
                    {"canonical_name": "ALT", "value": 43.0, "unit": "U/L",
                     "range": {"low": 9.0, "high": 40.0}})
    cp_cli.main(["check", SLUG, "--input", target, "--basis", basis_path(), "--json"])
    first = capsys.readouterr().out
    cp_cli.main(["check", SLUG, "--input", target, "--basis", basis_path(), "--json"])
    assert capsys.readouterr().out == first


def test_cli_json_payload_shape(capsys, tmp_path):
    target = _write(tmp_path, "high.json",
                    {"canonical_name": "ALT", "value": 43.0, "unit": "U/L",
                     "range": {"low": 9.0, "high": 40.0}})
    cp_cli.main(["check", SLUG, "--input", target, "--basis", basis_path(), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG
    assert payload["summary"]["blocking"] == 1