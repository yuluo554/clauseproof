"""器官 ``cost-card`` 无损判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在「判定结果」上。
来源仓判定层（D1 + D18 机械选 16 文件 / 实跑 270 passed / AST 函数 261）逐文件处置见
``docs/cost-card.md`` §6；本文件承载进货单三态、换算公式 F1–F5、参数门控、成本卡、
定价、波动预警与账本映射；真值库 41 用例的活跃对账在 ``tests/test_cost_card_extra.py``。

本文件同时是**漂移门**：``data/params.json``（来源资产）与 ``registry.PARAMS``（字面量）
必须逐条一致。
"""

import ast
import copy
import importlib
import json
import os
import sys

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

PACK_MOD = importlib.import_module("clauseproof.packs.cost-card")
ENGINE = importlib.import_module("clauseproof.packs.cost-card.engine")
REGISTRY = importlib.import_module("clauseproof.packs.cost-card.registry")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "cost-card")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "cost-card")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")

HEADER = ["日期", "品名", "类别", "数量", "单位", "单价", "金额"]
ROW_CABBAGE = ["2026-10-01", "大白菜", "蔬菜", "10", "斤", "1.20", "12.00"]
ROW_POTATO = ["2026-10-01", "土豆", "蔬菜", "10", "斤", "2.00", "20.00"]
DISH = {"name": "醋溜白菜", "items": [{"food": "大白菜", "qty": "1.5"}]}

LEDGER_SOURCE = {"kind": "user", "ref": "case.csv", "date": None, "note": None}
BOM_SOURCE = {"kind": "user", "ref": "case.json", "date": None, "note": None}


def basis():
    return Basis.from_json(BASIS_PATH)


def make_subject(rows=None, header=None, dishes=None, snapshots=None):
    subject = {
        "purchase_ledger": {
            "header": list(HEADER if header is None else header),
            "rows": [list(row) for row in ([ROW_CABBAGE, ROW_POTATO] if rows is None else rows)],
            "source": dict(LEDGER_SOURCE),
        },
    }
    if dishes is not False:
        subject["dishes"] = copy.deepcopy(
            [DISH] if dishes is None else dishes)
        subject["dishes_source"] = dict(BOM_SOURCE)
    if snapshots is not None:
        subject["snapshots"] = copy.deepcopy(snapshots)
    return subject


def findings(subject, params=None):
    if params is None:
        return tuple(PACK_MOD.evaluate(subject, basis()))
    return tuple(PACK_MOD.evaluate_with_params(subject, basis(), params))


def rules(found):
    return [finding.rule_id for finding in found]


def one(found, rule_id):
    hits = [finding for finding in found if finding.rule_id == rule_id]
    assert len(hits) == 1, (rule_id, rules(found))
    return hits[0]


def report(subject, params=None):
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject="case.json", findings=findings(subject, params))


def params_copy():
    return copy.deepcopy(dict(REGISTRY.PARAMS))


# ==========================================================================
# 一、器官契约与装配
# ==========================================================================
def test_pack_is_registered_under_slug():
    pack = get(SLUG)
    assert isinstance(pack, Pack)
    assert pack.slug == SLUG
    assert pack.version == PACK_MOD.VERSION


def test_pack_version_matches_source_release():
    assert PACK_MOD.VERSION == "0.2.0"


def test_pack_summary_states_basis_is_param_pack():
    assert "参数包" in PACK_MOD.SUMMARY


def test_pack_declares_input_fields():
    assert get(SLUG).input_fields == PACK_MOD.INPUT_FIELDS
    assert "purchase_ledger" in get(SLUG).input_fields


def test_pack_is_listed_in_builtin_modules_and_sorted():
    packs_ns = importlib.import_module("clauseproof.packs")
    assert SLUG in packs_ns.BUILTIN_MODULES
    assert list(packs_ns.BUILTIN_MODULES) == sorted(packs_ns.BUILTIN_MODULES)


def test_pack_appears_in_all_packs():
    assert SLUG in [pack.slug for pack in all_packs()]


def test_pack_has_no_own_argument_parser():
    for name in ("__init__.py", "engine.py", "registry.py"):
        tree = ast.parse(_read(name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(alias.name == "argparse" for alias in node.names), name
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "argparse", name


def test_pack_has_no_file_io():
    for name in ("__init__.py", "engine.py", "registry.py"):
        tree = ast.parse(_read(name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id != "open", (name, node.lineno)
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("read_text", "write_text"), (name, node.lineno)


def test_pack_has_no_clock_or_environment():
    banned = ("time", "datetime", "random", "socket")
    for name in ("__init__.py", "engine.py", "registry.py"):
        tree = ast.parse(_read(name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in banned, (name, alias.name)
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in banned, (name, node.module)
            elif isinstance(node, ast.Attribute):
                assert node.attr != "environ", name


def test_pack_has_no_print_calls():
    for name in ("__init__.py", "engine.py", "registry.py"):
        tree = ast.parse(_read(name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("print", "input"), (name, node.lineno)


def test_evaluate_signature_is_fixed():
    import inspect

    signature = inspect.signature(PACK_MOD.evaluate)
    assert list(signature.parameters) == ["subject", "basis"]


def test_evaluate_returns_iterable_of_findings():
    found = findings(make_subject())
    assert found
    for finding in found:
        assert finding.verdict in (PASS, FAIL, NOT_APPLICABLE)


def test_subject_label_is_ledger_basename():
    assert cp_cli._subject_label(os.path.join("x", "ledger.json")) == "ledger.json"


def _read(name):
    with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
        return handle.read()


# ==========================================================================
# 二、参数包漂移门（registry 字面量 ↔ data/params.json）
# ==========================================================================
def test_params_json_is_shipped_asset():
    assert os.path.isfile(os.path.join(DATA_DIR, "params.json"))


def test_params_json_parses_and_has_three_sections():
    payload = _params_json()
    for section in ("yield_rates", "pricing", "alert"):
        assert section in payload, section


def test_params_json_has_schema_version():
    assert _params_json()["schema_version"] == "1"


def test_params_json_generated_by_generator():
    assert _params_json()["generated_by"].endswith("gen_params.py")


def test_registry_yield_entry_count_matches_source():
    assert len(REGISTRY.YIELD_RATE_ENTRIES) == len(_params_json()["yield_rates"]) == 10


def test_registry_yield_names_preserve_source_order():
    assert [name for name, _v, _n in REGISTRY.YIELD_RATE_ENTRIES] == list(
        _params_json()["yield_rates"])


def test_every_yield_entry_matches_source_value():
    for name, value, _note in REGISTRY.YIELD_RATE_ENTRIES:
        assert str(REGISTRY.PARAMS["yield_rates"][name]["value"]) == value
        assert value == _params_json()["yield_rates"][name]["value"], name


def test_every_yield_entry_matches_source_status():
    for name, _value, _note in REGISTRY.YIELD_RATE_ENTRIES:
        assert (REGISTRY.PARAMS["yield_rates"][name]["status"]
                == _params_json()["yield_rates"][name]["status"]), name


def test_every_yield_entry_matches_source_kind():
    for name, _value, _note in REGISTRY.YIELD_RATE_ENTRIES:
        assert (REGISTRY.PARAMS["yield_rates"][name]["source"]["kind"]
                == _params_json()["yield_rates"][name]["source"]["kind"]), name


def test_every_yield_entry_matches_source_note():
    for name, _value, note in REGISTRY.YIELD_RATE_ENTRIES:
        assert note == _params_json()["yield_rates"][name]["source"]["note"], name


def test_all_yield_rates_are_builtin_experience():
    for name, _value, _note in REGISTRY.YIELD_RATE_ENTRIES:
        assert REGISTRY.PARAMS["yield_rates"][name]["source"]["kind"] == "builtin_experience", name


def test_all_yield_rate_notes_declare_not_official():
    for name, _value, note in REGISTRY.YIELD_RATE_ENTRIES:
        assert "非官方数据" in note, name


def test_yield_rates_are_within_domain():
    for name, _value, _note in REGISTRY.YIELD_RATE_ENTRIES:
        rate = ENGINE.to_decimal(REGISTRY.PARAMS["yield_rates"][name]["value"])
        assert ENGINE.Decimal(0) < rate <= ENGINE.Decimal(1), name


def test_target_margin_matches_source():
    assert (REGISTRY.PARAMS["pricing"]["target_margin"]["value"]
            == _params_json()["pricing"]["target_margin"]["value"] == "0.60")


def test_target_margin_source_is_user():
    assert REGISTRY.PARAMS["pricing"]["target_margin"]["source"]["kind"] == "user"


def test_alert_threshold_matches_source():
    assert (REGISTRY.PARAMS["alert"]["threshold"]["value"]
            == _params_json()["alert"]["threshold"]["value"] == "0.10")


def test_alert_threshold_source_is_user():
    assert REGISTRY.PARAMS["alert"]["threshold"]["source"]["kind"] == "user"


def test_all_parameter_entries_are_verified():
    engine = ENGINE
    for scope in ENGINE.SCOPES:
        report_ = engine.scope_report(REGISTRY.PARAMS, scope)
        assert report_["pending"] == [], scope
        assert report_["verified"], scope


def test_registry_version_is_baseline_date():
    assert REGISTRY.PARAMS_VERSION == "2026-10-14"


# ==========================================================================
# 三、条文库（锚点）漂移门
# ==========================================================================
def test_clauses_json_exists():
    assert os.path.isfile(BASIS_PATH)


def test_clauses_version_matches_registry():
    assert basis().version == REGISTRY.PARAMS_VERSION


def test_clauses_cover_every_registry_spec():
    loaded = set(basis().clause_ids())
    expected = {clause_id for clause_id, _path in REGISTRY.clause_specs()}
    assert loaded == expected


def test_clauses_have_expected_count():
    assert len(basis()) == 14


def test_clause_paths_match_registry_specs():
    catalog = basis()
    for clause_id, path in REGISTRY.clause_specs():
        assert catalog.clause(clause_id).path == path, clause_id


def test_clause_texts_match_registry():
    catalog = basis()
    for clause_id, _path in REGISTRY.clause_specs():
        assert catalog.clause(clause_id).text == REGISTRY.clause_text(clause_id), clause_id


def test_clauses_cite_no_law_name():
    """依据是参数包条目，不冒充法规：条款正文不出现书名号。"""
    catalog = basis()
    for clause_id in catalog.clause_ids():
        assert "《" not in catalog.clause(clause_id).text, clause_id


def test_clauses_declare_internal_experience_for_yield():
    catalog = basis()
    for name, _value, _note in REGISTRY.YIELD_RATE_ENTRIES:
        assert "非官方数据" in catalog.clause("param:yield-rate:%s" % name).text


def test_import_clause_lists_whitelist_columns():
    text = basis().clause(REGISTRY.CLAUSE_IMPORT_MAP).text
    for column in ENGINE.COLUMN_MAP:
        assert column in text, column


# ==========================================================================
# 四、表头形态门
# ==========================================================================
def test_header_missing_required_column_is_rejected():
    with pytest.raises(ENGINE.CostError):
        ENGINE.validate_header(["日期", "品名", "类别", "单位", "单价", "金额"])


def test_header_missing_quantity_column_is_rejected():
    with pytest.raises(ENGINE.CostError):
        ENGINE.validate_header(["日期", "品名", "类别", "数量", "单位", "金额"])


def test_header_missing_price_column_is_rejected():
    with pytest.raises(ENGINE.CostError):
        ENGINE.validate_header(["日期", "品名", "类别", "数量", "单位", "金额"])


def test_header_empty_is_rejected():
    with pytest.raises(ENGINE.CostError):
        ENGINE.validate_header([""])
    with pytest.raises(ENGINE.CostError):
        ENGINE.validate_header([])


def test_header_none_is_rejected():
    with pytest.raises(ENGINE.CostError):
        ENGINE.validate_header(None)


def test_header_whitespace_is_trimmed():
    names, _unknown = ENGINE.validate_header([" 日期 ", "品名", " 类别 ", "数量", "单位", "单价", "金额"])
    assert names == ("日期", "品名", "类别", "数量", "单位", "单价", "金额")


def test_header_unknown_column_is_reported():
    names, unknown = ENGINE.validate_header(HEADER + ["备注"])
    assert unknown == ["备注"]
    assert names[-1] == "备注"


def test_header_unknown_column_keeps_rows_usable():
    parsed = ENGINE.judge_rows(HEADER + ["备注"], [ROW_CABBAGE + ["甲"]])
    assert len(parsed["rows"]) == 1
    assert [issue["code"] for issue in parsed["issues"]] == [ENGINE.ISSUE_MAPPING_UNCERTAIN]


def test_header_unknown_column_issue_points_at_line_one():
    parsed = ENGINE.judge_rows(HEADER + ["备注"], [ROW_CABBAGE + ["甲"]])
    assert parsed["issues"][0]["line"] == 1


def test_header_requires_exactly_three_required_columns():
    assert set(ENGINE.REQUIRED_COLUMNS) == {"品名", "数量", "单价"}


def test_header_maps_every_whitelist_column():
    assert set(ENGINE.COLUMN_MAP) == set(HEADER)


def test_header_reverse_map_derives_required_columns():
    assert ENGINE.REQUIRED_COLUMNS == tuple(
        {field: column for column, field in ENGINE.COLUMN_MAP.items()}[field]
        for field in ENGINE.REQUIRED_FIELDS)


def test_header_minimal_three_columns_is_accepted():
    names, unknown = ENGINE.validate_header(["品名", "数量", "单价"])
    assert names == ("品名", "数量", "单价")
    assert unknown == []


# ==========================================================================
# 五、进货行三态
# ==========================================================================
def test_ok_row_becomes_usable():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE])
    assert parsed["issues"] == []
    assert parsed["rows"][0]["name"] == "大白菜"
    assert parsed["rows"][0]["qty"] == ENGINE.to_decimal("10")
    assert parsed["rows"][0]["unit_price"] == ENGINE.to_decimal("1.20")


def test_line_numbers_start_at_two():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE, ROW_POTATO])
    assert [row["line"] for row in parsed["rows"]] == [2, 3]


def test_required_empty_name_is_invalid():
    parsed = ENGINE.judge_rows(HEADER, [["2026-10-01", "", "蔬菜", "10", "斤", "1.20", "12"]])
    assert parsed["rows"] == []
    assert parsed["issues"][0]["code"] == ENGINE.ISSUE_REQUIRED_EMPTY
    assert parsed["issues"][0]["status"] == ENGINE.STATUS_INVALID


def test_required_empty_keeps_other_rows():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE, ["", "", "", "", "", "", ""]])
    assert len(parsed["rows"]) == 1
    assert parsed["issues"][0]["line"] == 3


def test_qty_not_numeric_is_invalid():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE[:3] + ["abc"] + ROW_CABBAGE[4:]])
    assert parsed["issues"][0]["code"] == ENGINE.ISSUE_NOT_NUMERIC
    assert parsed["rows"] == []


def test_price_not_numeric_is_invalid():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE[:5] + ["一元"] + ROW_CABBAGE[6:]])
    assert parsed["issues"][0]["code"] == ENGINE.ISSUE_NOT_NUMERIC
    assert parsed["rows"] == []


def test_negative_qty_is_invalid():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE[:3] + ["-2"] + ROW_CABBAGE[4:]])
    assert parsed["issues"][0]["code"] == ENGINE.ISSUE_NEGATIVE


def test_negative_price_is_invalid():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE[:5] + ["-1.20"] + ROW_CABBAGE[6:]])
    assert parsed["issues"][0]["code"] == ENGINE.ISSUE_NEGATIVE


def test_extra_fields_is_structure_unparsable():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE + ["甲", "多余"]])
    assert parsed["issues"][0]["code"] == ENGINE.ISSUE_STRUCTURE
    assert parsed["issues"][0]["status"] == ENGINE.STATUS_UNKNOWN
    assert parsed["rows"] == []


def test_extra_fields_do_not_enter_library():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE + ["甲"]])
    assert ENGINE.build_food_library(parsed["rows"]) == {}


def test_unregistered_unit_is_unknown_but_row_usable():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE[:4] + ["克拉"] + ROW_CABBAGE[5:]])
    assert parsed["issues"][0]["code"] == ENGINE.ISSUE_UNIT_UNREGISTERED
    assert parsed["issues"][0]["status"] == ENGINE.STATUS_UNKNOWN
    assert len(parsed["rows"]) == 1


def test_registered_unit_produces_no_issue():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE[:4] + ["公斤"] + ROW_CABBAGE[5:]])
    assert parsed["issues"] == []


def test_amount_column_is_not_validated():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE[:6] + ["不是数字"]])
    assert parsed["issues"] == []
    assert len(parsed["rows"]) == 1


def test_blank_unit_is_accepted():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE[:4] + [""] + ROW_CABBAGE[5:]])
    assert parsed["issues"] == []
    assert parsed["rows"][0]["unit"] is None


def test_short_row_leaves_missing_cells_empty():
    parsed = ENGINE.judge_rows(HEADER, [["2026-10-01", "大白菜", "蔬菜", "10", "斤", "1.20"]])
    assert parsed["issues"] == []
    assert parsed["rows"][0]["unit_price"] == ENGINE.to_decimal("1.20")


def test_row_missing_name_cell_is_required_empty():
    parsed = ENGINE.judge_rows(HEADER, [["2026-10-01"]])
    assert parsed["issues"][0]["code"] == ENGINE.ISSUE_REQUIRED_EMPTY


def test_values_are_stripped():
    parsed = ENGINE.judge_rows(HEADER, [[" 2026-10-01 ", " 大白菜 ", " 蔬菜 ", " 10 ", " 斤 ",
                                         " 1.20 ", " 12.00 "]])
    assert parsed["rows"][0]["name"] == "大白菜"
    assert parsed["rows"][0]["unit_price"] == ENGINE.to_decimal("1.20")


def test_numeric_cells_accept_numbers():
    parsed = ENGINE.judge_rows(HEADER, [["2026-10-01", "大白菜", "蔬菜", 10, "斤", 1.2, 12]])
    assert parsed["rows"][0]["qty"] == ENGINE.to_decimal("10")


def test_none_cell_is_treated_as_empty():
    parsed = ENGINE.judge_rows(HEADER, [["2026-10-01", None, "蔬菜", "10", "斤", "1.20", "12"]])
    assert parsed["issues"][0]["code"] == ENGINE.ISSUE_REQUIRED_EMPTY


def test_unknown_column_value_is_ignored():
    parsed = ENGINE.judge_rows(HEADER + ["备注"], [ROW_CABBAGE + ["备注甲"]])
    assert "备注" not in parsed["rows"][0]


def test_shuffled_columns_are_mapped_by_name():
    header = ["单价", "类别", "数量", "单位", "品名", "日期", "金额"]
    row = ["1.20", "蔬菜", "10", "斤", "大白菜", "2026-10-01", "12.00"]
    parsed = ENGINE.judge_rows(header, [row])
    assert parsed["rows"][0]["name"] == "大白菜"
    assert parsed["rows"][0]["unit_price"] == ENGINE.to_decimal("1.20")
    assert parsed["rows"][0]["date"] == "2026-10-01"


def test_duplicate_header_columns_take_last_value():
    header = ["品名", "数量", "单价", "品名"]
    row = ["大白菜", "10", "1.20", "土豆"]
    parsed = ENGINE.judge_rows(header, [row])
    assert parsed["rows"][0]["name"] == "土豆"


def test_status_counts_are_reported():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE, ["", "", "", "", "", "", ""]])
    assert parsed["status_counts"] == {ENGINE.STATUS_OK: 1, ENGINE.STATUS_INVALID: 1,
                                      ENGINE.STATUS_UNKNOWN: 0}


def test_status_counts_count_unknown_rows():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE[:4] + ["克拉"] + ROW_CABBAGE[5:]])
    assert parsed["status_counts"][ENGINE.STATUS_UNKNOWN] == 1


def test_all_unknown_codes_are_distinct():
    codes = {
        ENGINE.ISSUE_MAPPING_UNCERTAIN, ENGINE.ISSUE_STRUCTURE, ENGINE.ISSUE_REQUIRED_EMPTY,
        ENGINE.ISSUE_NOT_NUMERIC, ENGINE.ISSUE_NEGATIVE, ENGINE.ISSUE_UNIT_REGISTERED
        if hasattr(ENGINE, "ISSUE_UNIT_REGISTERED") else ENGINE.ISSUE_UNIT_UNREGISTERED,
    }
    assert len(codes) == 6


def test_issue_entries_carry_line_status_code_reason():
    parsed = ENGINE.judge_rows(HEADER, [["", "", "", "", "", "", ""]])
    issue = parsed["issues"][0]
    assert issue["line"] == 2
    assert issue["status"] == ENGINE.STATUS_INVALID
    assert issue["code"] == ENGINE.ISSUE_REQUIRED_EMPTY
    assert issue["reason"]


def test_source_is_attached_to_usable_rows():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE], source=LEDGER_SOURCE)
    assert parsed["rows"][0]["source"]["ref"] == "case.csv"


def test_no_source_key_when_not_provided():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE])
    assert "source" not in parsed["rows"][0]


def test_empty_row_list_is_not_an_error():
    parsed = ENGINE.judge_rows(HEADER, [])
    assert parsed["rows"] == []
    assert parsed["issues"] == []


def test_blank_row_list_entry_counts_as_required_empty():
    parsed = ENGINE.judge_rows(HEADER, [[]])
    assert parsed["issues"][0]["code"] == ENGINE.ISSUE_REQUIRED_EMPTY


def test_issue_order_follows_row_order():
    parsed = ENGINE.judge_rows(HEADER, [["", "", "", "", "", "", ""],
                                        ROW_CABBAGE[:3] + ["abc"] + ROW_CABBAGE[4:]])
    assert [issue["line"] for issue in parsed["issues"]] == [2, 3]


def test_unknown_column_issue_precedes_row_issues():
    parsed = ENGINE.judge_rows(HEADER + ["备注"], [["", "", "", "", "", "", "", ""]])
    assert parsed["issues"][0]["code"] == ENGINE.ISSUE_MAPPING_UNCERTAIN
    assert parsed["issues"][1]["code"] == ENGINE.ISSUE_REQUIRED_EMPTY


# ==========================================================================
# 六、换算公式 F1–F5
# ==========================================================================
def test_f1_net_unit_price_divides_by_yield():
    assert ENGINE.net_unit_price("1.20", "0.85") == ENGINE.Decimal("1.20") / ENGINE.Decimal("0.85")


def test_f1_rate_one_keeps_price():
    assert ENGINE.net_unit_price("8", "1") == ENGINE.Decimal("8")


def test_f1_rate_zero_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.net_unit_price("8", "0")


def test_f1_rate_above_one_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.net_unit_price("8", "1.01")


def test_f1_negative_price_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.net_unit_price("-1", "0.9")


def test_f1_net_price_is_never_below_purchase_price():
    net = ENGINE.net_unit_price("5", "0.5")
    assert net == ENGINE.Decimal("10") > ENGINE.Decimal("5")


def test_f1_is_exact_decimal():
    assert ENGINE.net_unit_price("1", "0.25") == ENGINE.Decimal("4")
    assert ENGINE.net_unit_price("0.9", "0.9") == ENGINE.Decimal("1")


def test_loss_rate_is_one_minus_yield():
    assert ENGINE.loss_rate("0.85") == ENGINE.Decimal("0.15")


def test_loss_rate_rejects_zero():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.loss_rate("0")


def test_loss_rate_rejects_above_one():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.loss_rate("1.2")


def test_f2_sums_lines():
    total = ENGINE.dish_cost([("1.5", "2"), ("2", "1")])
    assert total == ENGINE.Decimal("5")


def test_f2_single_line():
    assert ENGINE.dish_cost([("2.5", "4")]) == ENGINE.Decimal("10")


def test_f2_empty_bom_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.dish_cost([])


def test_f2_zero_qty_contributes_nothing():
    assert ENGINE.dish_cost([("5", "0"), ("3", "2")]) == ENGINE.Decimal("6")


def test_f2_negative_price_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.dish_cost([("-1", "2")])


def test_f2_negative_qty_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.dish_cost([("1", "-2")])


def test_f2_is_additive():
    single = ENGINE.dish_cost([("5", "4")])
    split = ENGINE.dish_cost([("5", "2"), ("5", "2")])
    assert single == split


def test_f3_margin_zero_gives_cost_as_price():
    assert ENGINE.suggested_price("10", "0") == ENGINE.Decimal("10")


def test_f3_applies_target_margin():
    assert ENGINE.suggested_price("10", "0.6") == ENGINE.Decimal("25")


def test_f3_quantizes_to_money():
    price = ENGINE.suggested_price("2.117647058823529411764705882", "0.6")
    assert str(price) == "5.29"


def test_f3_margin_one_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.suggested_price("10", "1")


def test_f3_margin_above_one_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.suggested_price("10", "1.2")


def test_f3_negative_margin_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.suggested_price("10", "-0.1")


def test_f3_negative_cost_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.suggested_price("-1", "0.6")


def test_f4_actual_margin_formula():
    assert ENGINE.actual_margin("25", "10") == ENGINE.Decimal("0.6")


def test_f4_negative_margin_is_reported_as_is():
    assert ENGINE.actual_margin("5", "10") == ENGINE.Decimal("-1")


def test_f4_zero_price_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.actual_margin("0", "1")


def test_f4_negative_cost_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.actual_margin("5", "-1")


def test_f5_change_rate_up():
    assert ENGINE.change_rate("1", "1.1") == ENGINE.Decimal("0.1")


def test_f5_change_rate_down_is_negative():
    assert ENGINE.change_rate("1", "0.9") == ENGINE.Decimal("-0.1")


def test_f5_change_rate_flat():
    assert ENGINE.change_rate("1", "1") == ENGINE.Decimal("0")


def test_f5_zero_old_price_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.change_rate("0", "1")


def test_f5_negative_new_price_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.change_rate("1", "-1")


def test_to_decimal_accepts_string_and_strips():
    assert ENGINE.to_decimal(" 1.20 ") == ENGINE.Decimal("1.20")


def test_to_decimal_accepts_int():
    assert ENGINE.to_decimal(3) == ENGINE.Decimal("3")


def test_to_decimal_accepts_float_via_str():
    assert ENGINE.to_decimal(0.1) == ENGINE.Decimal("0.1")


def test_to_decimal_rejects_bool():
    with pytest.raises(TypeError):
        ENGINE.to_decimal(True)


def test_to_decimal_rejects_none():
    with pytest.raises(TypeError):
        ENGINE.to_decimal(None)


def test_to_decimal_rejects_list():
    with pytest.raises(TypeError):
        ENGINE.to_decimal([])


def test_quantize_money_half_up():
    assert str(ENGINE.quantize_money("2.125")) == "2.13"


def test_quantize_rate_four_decimals():
    assert str(ENGINE.quantize_rate("0.123456")) == "0.1235"


def test_quantize_rate_half_up():
    assert str(ENGINE.quantize_rate("0.00005")) == "0.0001"


def test_source_kinds_are_closed_set():
    assert ENGINE.SOURCE_KINDS == ("snapshot", "user", "builtin_experience")


def test_make_source_rejects_unknown_kind():
    with pytest.raises(ENGINE.SourceMissing):
        ENGINE.make_source("official", "x")


def test_make_source_rejects_empty_ref():
    with pytest.raises(ENGINE.SourceMissing):
        ENGINE.make_source("user", "")


def test_make_source_round_trips_fields():
    source = ENGINE.make_source("snapshot", "x.json", date="2026-08-06", note="n")
    assert source == {"kind": "snapshot", "ref": "x.json", "date": "2026-08-06", "note": "n"}


def test_validate_source_rejects_missing():
    with pytest.raises(ENGINE.SourceMissing):
        ENGINE.validate_source(None)


def test_validate_source_rejects_unknown_kind():
    with pytest.raises(ENGINE.SourceMissing):
        ENGINE.validate_source({"kind": "official", "ref": "x"})


def test_validate_source_rejects_empty_ref():
    with pytest.raises(ENGINE.SourceMissing):
        ENGINE.validate_source({"kind": "user", "ref": ""})


def test_validate_source_accepts_string_kinds():
    assert ENGINE.validate_source({"kind": "user", "ref": "x"})["ref"] == "x"


# ==========================================================================
# 七、食材库与重复品名
# ==========================================================================
def test_library_takes_last_price_for_duplicates():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE, ROW_CABBAGE[:5] + ["1.60"] + ROW_CABBAGE[6:]])
    library = ENGINE.build_food_library(parsed["rows"])
    assert library["大白菜"]["ref_price"] == ENGINE.to_decimal("1.60")


def test_library_records_category_and_unit():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE], source=LEDGER_SOURCE)
    library = ENGINE.build_food_library(parsed["rows"])
    assert library["大白菜"]["category"] == "蔬菜"
    assert library["大白菜"]["unit"] == "斤"


def test_library_carries_row_source():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE], source=LEDGER_SOURCE)
    library = ENGINE.build_food_library(parsed["rows"])
    assert library["大白菜"]["source"]["ref"] == "case.csv"


def test_library_is_empty_for_no_rows():
    assert ENGINE.build_food_library([]) == {}


def test_duplicate_names_are_reported_once():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE, ROW_CABBAGE, ROW_CABBAGE])
    assert ENGINE.duplicate_names(parsed["rows"]) == ["大白菜"]


def test_duplicate_names_preserve_first_seen_order():
    parsed = ENGINE.judge_rows(HEADER, [ROW_POTATO, ROW_CABBAGE, ROW_POTATO, ROW_CABBAGE])
    assert ENGINE.duplicate_names(parsed["rows"]) == ["土豆", "大白菜"]


def test_duplicate_names_empty_for_distinct_foods():
    parsed = ENGINE.judge_rows(HEADER, [ROW_CABBAGE, ROW_POTATO])
    assert ENGINE.duplicate_names(parsed["rows"]) == []


def test_duplicates_are_flagged_in_ledger():
    found = findings(make_subject(rows=[ROW_CABBAGE, ROW_CABBAGE]))
    assert one(found, "purchase.duplicate:大白菜").verdict == NOT_APPLICABLE


def test_duplicate_flag_carries_no_blocking():
    found = findings(make_subject(rows=[ROW_CABBAGE, ROW_CABBAGE]))
    assert not [f for f in found if f.verdict == FAIL]


# ==========================================================================
# 八、参数门控
# ==========================================================================
def test_scope_sections_are_registered():
    assert ENGINE.SCOPE_SECTIONS == {"cost": "yield_rates", "pricing": "pricing",
                                     "alert": "alert"}


def test_validate_params_rejects_missing_section():
    params = params_copy()
    del params["alert"]
    with pytest.raises(ENGINE.ParamsError):
        ENGINE.validate_params(params)


def test_validate_params_rejects_unregistered_status():
    params = params_copy()
    params["pricing"]["target_margin"]["status"] = "unknown"
    with pytest.raises(ENGINE.ParamsError):
        ENGINE.validate_params(params)


def test_validate_params_rejects_entry_without_status():
    params = params_copy()
    params["pricing"]["target_margin"] = {"value": "0.6"}
    with pytest.raises(ENGINE.ParamsError):
        ENGINE.validate_params(params)


def test_scope_report_lists_verified_entries():
    entries = ENGINE.scope_report(REGISTRY.PARAMS, "cost")
    assert len(entries["verified"]) == 10


def test_scope_report_lists_pending_entries():
    params = params_copy()
    params["yield_rates"]["土豆"]["status"] = ENGINE.PARAM_PENDING
    assert ENGINE.scope_report(params, "cost")["pending"] == ["土豆"]


def test_scope_report_lists_input_required_entries():
    params = params_copy()
    params["yield_rates"]["土豆"]["status"] = ENGINE.PARAM_INPUT_REQUIRED
    assert ENGINE.scope_report(params, "cost")["input_required"] == ["土豆"]


def test_scope_report_rejects_unknown_scope():
    with pytest.raises(ENGINE.ParamsError):
        ENGINE.scope_report(REGISTRY.PARAMS, "shipping")


def test_effective_params_returns_only_verified():
    params = params_copy()
    params["yield_rates"]["土豆"]["status"] = ENGINE.PARAM_INPUT_REQUIRED
    assert "土豆" not in ENGINE.effective_params(params, "cost")


def test_effective_params_raises_on_pending():
    params = params_copy()
    params["yield_rates"]["土豆"]["status"] = ENGINE.PARAM_PENDING
    with pytest.raises(ENGINE.ParamsPending):
        ENGINE.effective_params(params, "cost")


def test_effective_params_pending_message_names_entry():
    params = params_copy()
    params["yield_rates"]["土豆"]["status"] = ENGINE.PARAM_PENDING
    with pytest.raises(ENGINE.ParamsPending) as info:
        ENGINE.effective_params(params, "cost")
    assert "土豆" in str(info.value)


def test_effective_params_validates_sources():
    params = params_copy()
    params["pricing"]["target_margin"]["source"] = {"kind": "official", "ref": "x"}
    with pytest.raises(ENGINE.SourceMissing):
        ENGINE.effective_params(params, "pricing")


def test_effective_params_rejects_missing_source():
    params = params_copy()
    del params["alert"]["threshold"]["source"]
    with pytest.raises(ENGINE.SourceMissing):
        ENGINE.effective_params(params, "alert")


def test_yield_rate_for_returns_decimal_and_entry():
    cost_params = ENGINE.effective_params(REGISTRY.PARAMS, "cost")
    rate, entry = ENGINE.yield_rate_for(cost_params, "大白菜")
    assert rate == ENGINE.to_decimal("0.85")
    assert entry["source"]["kind"] == "builtin_experience"


def test_yield_rate_for_missing_food_requires_input():
    cost_params = ENGINE.effective_params(REGISTRY.PARAMS, "cost")
    with pytest.raises(ENGINE.InputRequired) as info:
        ENGINE.yield_rate_for(cost_params, "芥蓝")
    assert "芥蓝" in str(info.value)


def test_input_required_is_a_cost_error():
    assert issubclass(ENGINE.InputRequired, ENGINE.CostError)


def test_params_pending_is_a_params_error():
    assert issubclass(ENGINE.ParamsPending, ENGINE.ParamsError)


# ==========================================================================
# 九、成本卡
# ==========================================================================
def _card(subject=None, params=None):
    subject = subject or make_subject()
    parsed = ENGINE.judge_rows(subject["purchase_ledger"]["header"],
                              subject["purchase_ledger"]["rows"],
                              source=subject["purchase_ledger"].get("source", LEDGER_SOURCE))
    library = ENGINE.build_food_library(parsed["rows"])
    cost_params = ENGINE.effective_params(params or REGISTRY.PARAMS, "cost")
    return ENGINE.compute_costcard(subject["dishes"], library, cost_params,
                                   subject.get("dishes_source", BOM_SOURCE))


def test_costcard_single_food_cost():
    result = _card()
    assert str(result["cards"][0]["cost"]) == "2.12"


def test_costcard_two_foods_cost():
    subject = make_subject(dishes=[{"name": "醋溜白菜", "items": [
        {"food": "大白菜", "qty": "1.5"}, {"food": "土豆", "qty": "0.5"}]}])
    assert str(_card(subject)["cards"][0]["cost"]) == "3.23"


def test_costcard_zero_qty_food_contributes_nothing():
    subject = make_subject(dishes=[{"name": "醋溜白菜", "items": [
        {"food": "大白菜", "qty": "0"}, {"food": "土豆", "qty": "0.5"}]}])
    assert str(_card(subject)["cards"][0]["cost"]) == "1.11"


def test_costcard_rate_one_keeps_purchase_price():
    params = params_copy()
    params["yield_rates"]["大白菜"]["value"] = "1"
    assert str(_card(params=params)["cards"][0]["cost"]) == "1.80"


def test_costcard_tiny_rate_amplifies_cost():
    params = params_copy()
    params["yield_rates"]["大白菜"]["value"] = "0.01"
    assert str(_card(params=params)["cards"][0]["cost"]) == "180.00"


def test_costcard_yield_out_of_range_excludes_dish():
    params = params_copy()
    params["yield_rates"]["大白菜"]["value"] = "1.2"
    result = _card(params=params)
    assert result["cards"] == []
    assert result["issues"][0]["code"] == ENGINE.ISSUE_YIELD_OUT_OF_RANGE


def test_costcard_negative_yield_is_out_of_range():
    params = params_copy()
    params["yield_rates"]["大白菜"]["value"] = "-0.5"
    result = _card(params=params)
    assert result["issues"][0]["code"] == ENGINE.ISSUE_YIELD_OUT_OF_RANGE


def test_costcard_invalid_qty_excludes_dish():
    subject = make_subject(dishes=[{"name": "醋溜白菜", "items": [
        {"food": "大白菜", "qty": "abc"}]}])
    result = _card(subject)
    assert result["cards"] == []
    assert result["issues"][0]["code"] == ENGINE.ISSUE_QTY_INVALID


def test_costcard_negative_qty_excludes_dish():
    subject = make_subject(dishes=[{"name": "醋溜白菜", "items": [
        {"food": "大白菜", "qty": "-1"}]}])
    result = _card(subject)
    assert result["issues"][0]["code"] == ENGINE.ISSUE_QTY_INVALID


def test_costcard_line_issue_locates_dish_and_food():
    subject = make_subject(dishes=[{"name": "醋溜白菜", "items": [
        {"food": "大白菜", "qty": "-1"}]}])
    assert _card(subject)["issues"][0]["where"] == "菜品「醋溜白菜」·食材「大白菜」"


def test_costcard_one_bad_dish_does_not_block_others():
    subject = make_subject(dishes=[
        {"name": "醋溜白菜", "items": [{"food": "大白菜", "qty": "-1"}]},
        {"name": "清炒时蔬", "items": [{"food": "土豆", "qty": "1"}]},
    ])
    result = _card(subject)
    assert [card["dish"] for card in result["cards"]] == ["清炒时蔬"]


def test_costcard_excluded_dish_is_not_priced():
    found = findings(make_subject(dishes=[{"name": "醋溜白菜", "items": [
        {"food": "大白菜", "qty": "-1"}]}]))
    assert "pricing.price:醋溜白菜" not in rules(found)


def test_costcard_unknown_food_is_input_error():
    subject = make_subject(dishes=[{"name": "醋溜白菜", "items": [
        {"food": "并不存在的食材", "qty": "1"}]}])
    with pytest.raises(ENGINE.CostError):
        _card(subject)


def test_costcard_missing_yield_entry_is_input_error():
    subject = make_subject(dishes=[{"name": "醋溜白菜", "items": [
        {"food": "莲藕", "qty": "1"}]}])
    subject["purchase_ledger"]["rows"] = [["2026-10-01", "莲藕", "蔬菜", "4", "斤", "3.50", "14"]]
    with pytest.raises(ENGINE.CostError):
        _card(subject)


def test_costcard_missing_qty_source_is_rejected():
    subject = make_subject()
    subject["dishes_source"] = {"kind": "official", "ref": "x"}
    with pytest.raises(ENGINE.SourceMissing):
        _card(subject)


def test_costcard_missing_yield_source_is_rejected():
    params = params_copy()
    del params["yield_rates"]["大白菜"]["source"]
    with pytest.raises(ENGINE.SourceMissing):
        _card(params=params)


def test_costcard_missing_price_source_is_rejected():
    subject = make_subject()
    subject["purchase_ledger"]["source"] = {"kind": "user", "ref": ""}
    with pytest.raises(ENGINE.SourceMissing):
        _card(subject)


def test_costcard_line_records_all_five_formula_fields():
    line = _card()["cards"][0]["lines"][0]
    for key in ("purchase_unit_price", "yield_rate", "loss_rate", "net_unit_price",
                "qty", "line_cost"):
        assert key in line, key


def test_costcard_line_carries_three_sources():
    line = _card()["cards"][0]["lines"][0]
    assert line["yield_source"]["kind"] == "builtin_experience"
    assert line["price_source"]["kind"] == "user"
    assert line["qty_source"]["kind"] == "user"


def test_costcard_line_net_price_matches_f1():
    line = _card()["cards"][0]["lines"][0]
    assert line["net_unit_price"] == ENGINE.quantize_money(
        ENGINE.net_unit_price(line["purchase_unit_price"], line["yield_rate"]))


def test_costcard_line_loss_rate_matches_yield():
    line = _card()["cards"][0]["lines"][0]
    assert line["loss_rate"] == ENGINE.quantize_rate(
        ENGINE.loss_rate(line["yield_rate"]))


def test_costcard_keeps_exact_cost_for_pricing():
    card = _card()["cards"][0]
    assert isinstance(card["cost_exact"], ENGINE.Decimal)
    assert ENGINE.quantize_money(card["cost_exact"]) == card["cost"]
    assert card["cost_exact"] != card["cost"]


def test_costcard_empty_items_raises_formula_error():
    subject = make_subject(dishes=[{"name": "醋溜白菜", "items": []}])
    with pytest.raises(ENGINE.FormulaError):
        _card(subject)


def test_costcard_two_dishes_produce_two_cards():
    subject = make_subject(dishes=[
        {"name": "醋溜白菜", "items": [{"food": "大白菜", "qty": "1.5"}]},
        {"name": "土豆丝", "items": [{"food": "土豆", "qty": "1"}]},
    ])
    assert len(_card(subject)["cards"]) == 2


def test_costcard_issue_count_for_two_bad_lines():
    subject = make_subject(dishes=[{"name": "乱炖", "items": [
        {"food": "大白菜", "qty": "-1"}, {"food": "土豆", "qty": "-2"}]}])
    assert len(_card(subject)["issues"]) == 2


def test_costcard_both_issues_share_dish_where():
    subject = make_subject(dishes=[{"name": "乱炖", "items": [
        {"food": "大白菜", "qty": "-1"}, {"food": "土豆", "qty": "-2"}]}])
    wheres = {issue["where"] for issue in _card(subject)["issues"]}
    assert wheres == {"菜品「乱炖」·食材「大白菜」", "菜品「乱炖」·食材「土豆」"}


def test_costcard_all_dishes_excluded_reports_file_level():
    found = findings(make_subject(dishes=[{"name": "醋溜白菜", "items": [
        {"food": "大白菜", "qty": "-1"}]}]))
    assert one(found, "purchase.file:no_usable_dishes").verdict == FAIL


def test_costcard_excluded_dish_is_fail_with_yield_anchor():
    found = findings(make_subject(dishes=[{"name": "醋溜白菜", "items": [
        {"food": "大白菜", "qty": "-1"}]}]))
    finding = one(found, "dish.cost:醋溜白菜")
    assert finding.verdict == FAIL
    assert finding.anchor.clause_id == "param:yield-rate:大白菜"


def test_costcard_pass_dish_is_anchored_to_yield_section():
    finding = one(findings(make_subject()), "dish.cost:醋溜白菜")
    assert finding.anchor.clause_id == REGISTRY.CLAUSE_SECTION_YIELD


def test_costcard_pass_evidence_carries_cost_and_foods():
    evidence = one(findings(make_subject()), "dish.cost:醋溜白菜").evidence
    assert evidence["cost"] == "2.12"
    assert evidence["foods"] == ["大白菜"]


def test_costcard_without_dishes_skips_dish_records():
    found = findings(make_subject(dishes=False))
    assert not [f for f in found if f.rule_id.startswith("dish.")]
    assert not [f for f in found if f.rule_id.startswith("pricing.")]


# ==========================================================================
# 十、定价
# ==========================================================================
def test_pricing_suggested_price():
    card = _card()["cards"]
    row = ENGINE.compute_pricing(card, ENGINE.effective_params(REGISTRY.PARAMS, "pricing"))[0]
    assert str(row["suggested_price"]) == "5.29"


def test_pricing_actual_margin_after_quantization():
    card = _card()["cards"]
    row = ENGINE.compute_pricing(card, ENGINE.effective_params(REGISTRY.PARAMS, "pricing"))[0]
    assert str(row["actual_margin"]) == "0.5997"


def test_pricing_target_margin_is_quantized():
    card = _card()["cards"]
    row = ENGINE.compute_pricing(card, ENGINE.effective_params(REGISTRY.PARAMS, "pricing"))[0]
    assert str(row["target_margin"]) == "0.6000"


def test_pricing_missing_target_margin_is_rejected():
    with pytest.raises(ENGINE.FormulaError):
        ENGINE.compute_pricing(_card()["cards"], {})


def test_pricing_margin_zero_gives_cost_price():
    params = params_copy()
    params["pricing"]["target_margin"]["value"] = "0"
    row = ENGINE.compute_pricing(_card()["cards"],
                                 ENGINE.effective_params(params, "pricing"))[0]
    assert str(row["suggested_price"]) == "2.12"


def test_pricing_row_records_margin_source():
    row = ENGINE.compute_pricing(_card()["cards"],
                                 ENGINE.effective_params(REGISTRY.PARAMS, "pricing"))[0]
    assert row["margin_source"]["kind"] == "user"


def test_pricing_ledger_record_is_pass():
    assert one(findings(make_subject()), "pricing.price:醋溜白菜").verdict == PASS


def test_pricing_ledger_evidence_has_four_values():
    evidence = one(findings(make_subject()), "pricing.price:醋溜白菜").evidence
    for key in ("cost", "target_margin", "suggested_price", "actual_margin"):
        assert key in evidence, key


def test_pricing_anchor_is_target_margin_clause():
    assert one(findings(make_subject()),
               "pricing.price:醋溜白菜").anchor.clause_id == REGISTRY.CLAUSE_SECTION_PRICING


def test_pricing_pending_margin_blocks_detection_path():
    params = params_copy()
    params["pricing"]["target_margin"]["status"] = ENGINE.PARAM_PENDING
    with pytest.raises(ContractError):
        findings(make_subject(), params=params)


def test_pricing_input_required_margin_is_missing_input():
    params = params_copy()
    params["pricing"]["target_margin"]["status"] = ENGINE.PARAM_INPUT_REQUIRED
    with pytest.raises(ENGINE.FormulaError):
        findings(make_subject(), params=params)


# ==========================================================================
# 十一、价格波动预警
# ==========================================================================
def _snap(date, prices):
    return {"date": date, "prices": prices,
            "source": {"kind": "snapshot", "ref": "s-%s.json" % date}}


def test_diff_prices_up():
    rows = ENGINE.diff_prices({"a": "1"}, {"a": "1.1"})
    assert rows[0]["status"] == "up"
    assert str(rows[0]["change_rate"]) == "0.1000"


def test_diff_prices_down():
    rows = ENGINE.diff_prices({"a": "1"}, {"a": "0.9"})
    assert rows[0]["status"] == "down"


def test_diff_prices_flat():
    rows = ENGINE.diff_prices({"a": "1"}, {"a": "1"})
    assert rows[0]["status"] == "flat"


def test_diff_prices_new_has_no_rate():
    rows = ENGINE.diff_prices({"a": "1"}, {"a": "1", "b": "2"})
    row = [item for item in rows if item["name"] == "b"][0]
    assert row["status"] == "new"
    assert row["change_rate"] is None
    assert row["old_price"] is None


def test_diff_prices_gone_has_no_rate():
    rows = ENGINE.diff_prices({"a": "1", "b": "2"}, {"a": "1"})
    row = [item for item in rows if item["name"] == "b"][0]
    assert row["status"] == "gone"
    assert row["new_price"] is None


def test_diff_prices_is_sorted_descending():
    rows = ENGINE.diff_prices({"a": "1", "b": "1", "c": "1"}, {"a": "2", "b": "0.5", "c": "1"})
    assert [row["name"] for row in rows] == ["a", "c", "b"]


def test_diff_prices_places_no_baseline_last():
    rows = ENGINE.diff_prices({"a": "1"}, {"a": "2", "b": "3"})
    assert rows[-1]["name"] == "b"


def test_diff_prices_quantizes_prices():
    rows = ENGINE.diff_prices({"a": "1.005"}, {"a": "1"})
    assert str(rows[0]["old_price"]) == "1.01"


def test_flag_marks_equal_threshold_as_flagged():
    rows = ENGINE.diff_prices({"a": "1"}, {"a": "1.1"})
    assert [row["name"] for row in ENGINE.flag(rows, "0.1")] == ["a"]


def test_flag_marks_downward_move_by_absolute_value():
    rows = ENGINE.diff_prices({"a": "1"}, {"a": "0.8"})
    assert [row["name"] for row in ENGINE.flag(rows, "0.1")] == ["a"]


def test_flag_skips_below_threshold():
    rows = ENGINE.diff_prices({"a": "1"}, {"a": "1.05"})
    assert ENGINE.flag(rows, "0.1") == []


def test_flag_skips_no_baseline_rows():
    rows = ENGINE.diff_prices({"a": "1"}, {"a": "1", "b": "9"})
    assert [row["name"] for row in ENGINE.flag(rows, "0.1")] == []


def test_impacted_dishes_recomputes_cost():
    cards = _card()["cards"]
    changes = ENGINE.diff_prices({"大白菜": "1.20"}, {"大白菜": "1.80"})
    rows = ENGINE.impacted_dishes(cards, changes, {"大白菜": "1.20"}, {"大白菜": "1.80"})
    assert str(rows[0]["old_cost"]) == "2.12"
    assert str(rows[0]["new_cost"]) == "3.18"


def test_impacted_dishes_skips_untouched():
    cards = _card()["cards"]
    changes = ENGINE.diff_prices({"土豆": "2.00"}, {"土豆": "3.00"})
    assert ENGINE.impacted_dishes(cards, changes, {"土豆": "2.00"}, {"土豆": "3.00"}) == []


def test_impacted_dishes_uses_card_price_when_snapshot_missing():
    cards = _card()["cards"]
    changes = ENGINE.diff_prices({"大白菜": "1.20"}, {"大白菜": "1.80"})
    rows = ENGINE.impacted_dishes(cards, changes, {"大白菜": "1.20"}, {})
    assert str(rows[0]["new_cost"]) == "2.12"


def test_impacted_dishes_rate_is_negative_when_price_drops():
    cards = _card()["cards"]
    changes = ENGINE.diff_prices({"大白菜": "1.20"}, {"大白菜": "0.60"})
    rows = ENGINE.impacted_dishes(cards, changes, {"大白菜": "1.20"}, {"大白菜": "0.60"})
    assert rows[0]["change_rate"] < 0


def test_require_distinct_periods_rejects_same_date():
    with pytest.raises(ENGINE.CostError):
        ENGINE.require_distinct_periods("2026-08-06", "2026-08-06")


def test_require_distinct_periods_accepts_different_dates():
    ENGINE.require_distinct_periods("2026-08-06", "2026-10-06")


def test_alert_records_are_not_applicable():
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {"大白菜": "1.20"}),
                                      "new": _snap("2026-10-06", {"大白菜": "0.80"})})
    finding = one(findings(subject), "alert.food:大白菜")
    assert finding.verdict == NOT_APPLICABLE


def test_alert_messages_say_warning_is_not_a_verdict():
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {"大白菜": "1.20"}),
                                      "new": _snap("2026-10-06", {"大白菜": "0.80"})})
    assert "预警" in one(findings(subject), "alert.food:大白菜").message


def test_alert_flags_move_above_threshold():
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {"大白菜": "1.20"}),
                                      "new": _snap("2026-10-06", {"大白菜": "0.80"})})
    assert one(findings(subject), "alert.food:大白菜").evidence["flagged"] is True


def test_alert_does_not_flag_small_move():
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {"大白菜": "1.20"}),
                                      "new": _snap("2026-10-06", {"大白菜": "1.21"})})
    assert one(findings(subject), "alert.food:大白菜").evidence["flagged"] is False


def test_alert_evidence_carries_both_periods():
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {"大白菜": "1.20"}),
                                      "new": _snap("2026-10-06", {"大白菜": "0.80"})})
    assert one(findings(subject), "alert.food:大白菜").evidence["periods"] == [
        "2026-08-06", "2026-10-06"]


def test_alert_dish_record_reports_delta():
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {"大白菜": "1.20"}),
                                      "new": _snap("2026-10-06", {"大白菜": "1.80"})})
    evidence = one(findings(subject), "alert.dish:醋溜白菜").evidence
    assert evidence["delta"] == "1.06"
    assert evidence["touched_foods"] == ["大白菜"]


def test_alert_scope_is_menu_only():
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {"大白菜": "1.20", "冬瓜": "1"}),
                                      "new": _snap("2026-10-06", {"大白菜": "1.20", "冬瓜": "2"})})
    found = findings(subject)
    assert "alert.food:冬瓜" not in rules(found)


def test_alert_without_snapshots_emits_nothing():
    assert not [f for f in findings(make_subject()) if f.rule_id.startswith("alert.")]


def test_alert_same_period_is_input_error():
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {"大白菜": "1.20"}),
                                      "new": _snap("2026-08-06", {"大白菜": "1.20"})})
    with pytest.raises(ENGINE.CostError):
        findings(subject)


def test_alert_anchor_is_threshold_clause():
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {"大白菜": "1.20"}),
                                      "new": _snap("2026-10-06", {"大白菜": "0.80"})})
    assert one(findings(subject),
               "alert.food:大白菜").anchor.clause_id == REGISTRY.CLAUSE_SECTION_ALERT


def test_alert_pending_threshold_is_contract_error():
    params = params_copy()
    params["alert"]["threshold"]["status"] = ENGINE.PARAM_PENDING
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {"大白菜": "1.20"}),
                                      "new": _snap("2026-10-06", {"大白菜": "0.80"})})
    with pytest.raises(ContractError):
        findings(subject, params=params)


def test_alert_new_food_has_no_rate():
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {}),
                                      "new": _snap("2026-10-06", {"大白菜": "1.20"})})
    evidence = one(findings(subject), "alert.food:大白菜").evidence
    assert evidence["status"] == "new"
    assert evidence["change_rate"] is None


def test_alert_gone_food_has_no_rate():
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {"大白菜": "1.20"}),
                                      "new": _snap("2026-10-06", {})})
    evidence = one(findings(subject), "alert.food:大白菜").evidence
    assert evidence["status"] == "gone"


def test_alert_threshold_is_recorded():
    subject = make_subject(snapshots={"old": _snap("2026-08-06", {"大白菜": "1.20"}),
                                      "new": _snap("2026-10-06", {"大白菜": "0.80"})})
    assert one(findings(subject), "alert.food:大白菜").evidence["threshold"] == "0.1000"


# ==========================================================================
# 十二、账本映射与退出码
# ==========================================================================
def test_missing_basis_clause_is_contract_error():
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate(make_subject(), Basis.empty(REGISTRY.PARAMS_VERSION))


def test_basis_version_mismatch_is_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(make_subject(), Basis.empty("2020-01-01"))


def test_every_non_na_finding_has_anchor():
    for finding in findings(make_subject(rows=[ROW_CABBAGE, ["", "", "", "", "", "", ""]])):
        if finding.verdict != NOT_APPLICABLE:
            assert finding.anchor is not None, finding.rule_id


def test_every_finding_has_unique_id():
    report_ = report(make_subject(rows=[ROW_CABBAGE, ["", "", "", "", "", "", ""]]))
    ids = [finding.id for finding in report_.findings]
    assert len(ids) == len(set(ids))


def test_report_is_deterministic():
    subject = make_subject()
    first = report(subject).as_dict()
    second = report(subject).as_dict()
    assert json.dumps(first, ensure_ascii=False) == json.dumps(second, ensure_ascii=False)


def test_report_json_has_no_decimal_objects():
    payload = report(make_subject()).as_dict()
    json.dumps(payload, ensure_ascii=False)  # Decimal 会在此抛 TypeError


def test_demo_exit_code_is_blocked():
    payload = json.load(open(os.path.join(SAMPLES, "ledger-demo.json"), encoding="utf-8"))
    assert report(payload).exit_code() == EXIT_BLOCKED


def test_clean_exit_code_is_ok():
    payload = json.load(open(os.path.join(SAMPLES, "ledger-clean.json"), encoding="utf-8"))
    assert report(payload).exit_code() == EXIT_OK


def test_demo_has_three_blocking_rows():
    payload = json.load(open(os.path.join(SAMPLES, "ledger-demo.json"), encoding="utf-8"))
    blocking = report(payload).blocking()
    assert len(blocking) == 3
    assert all(finding.verdict == FAIL for finding in blocking)


def test_unknown_rows_are_not_blocking():
    payload = json.load(open(os.path.join(SAMPLES, "ledger-demo.json"), encoding="utf-8"))
    unknown = [f for f in report(payload).findings
               if f.evidence.get("status") == ENGINE.STATUS_UNKNOWN]
    assert unknown and all(f.verdict == NOT_APPLICABLE for f in unknown)


def test_cli_missing_basis_returns_contract_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input",
                        os.path.join(SAMPLES, "ledger-clean.json")])
    assert code == EXIT_CONTRACT
    assert "ContractError" in capsys.readouterr().err


def test_cli_wrong_basis_version_returns_contract_code(tmp_path, capsys):
    path = tmp_path / "clauses.json"
    path.write_text(json.dumps({"version": "1999-01-01", "clauses": []}), encoding="utf-8")
    code = cp_cli.main(["check", SLUG, "--input",
                        os.path.join(SAMPLES, "ledger-clean.json"),
                        "--basis", str(path)])
    assert code == EXIT_CONTRACT
    assert "ContractError" in capsys.readouterr().err


def test_cli_missing_file_returns_input_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input", "no-such-file.json",
                        "--basis", BASIS_PATH])
    assert code == EXIT_INPUT


def test_cli_missing_required_field_returns_input_code(tmp_path, capsys):
    path = tmp_path / "subject.json"
    path.write_text(json.dumps({"dishes": []}), encoding="utf-8")
    code = cp_cli.main(["check", SLUG, "--input", str(path), "--basis", BASIS_PATH])
    assert code == EXIT_INPUT
    assert "purchase_ledger" in capsys.readouterr().err


def test_cli_bad_ledger_source_returns_input_code(tmp_path, capsys):
    subject = make_subject()
    subject["purchase_ledger"]["source"] = {"kind": "official", "ref": "x"}
    path = tmp_path / "subject.json"
    path.write_text(json.dumps(subject, ensure_ascii=False), encoding="utf-8")
    code = cp_cli.main(["check", SLUG, "--input", str(path), "--basis", BASIS_PATH])
    assert code == EXIT_INPUT


def test_cli_clean_subject_returns_ok(capsys):
    code = cp_cli.main(["check", SLUG, "--input",
                        os.path.join(SAMPLES, "ledger-clean.json"), "--basis", BASIS_PATH])
    assert code == EXIT_OK
    assert "合计" in capsys.readouterr().out


def test_cli_blocked_subject_returns_one(capsys):
    code = cp_cli.main(["check", SLUG, "--input",
                        os.path.join(SAMPLES, "ledger-demo.json"), "--basis", BASIS_PATH])
    assert code == EXIT_BLOCKED
    assert "阻断" in capsys.readouterr().out


def test_cli_json_output_is_parseable(capsys):
    cp_cli.main(["check", SLUG, "--input", os.path.join(SAMPLES, "ledger-clean.json"),
                 "--basis", BASIS_PATH, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG
    assert payload["summary"]["blocking"] == 0


def test_cli_json_output_has_contract_keys(capsys):
    cp_cli.main(["check", SLUG, "--input", os.path.join(SAMPLES, "ledger-clean.json"),
                 "--basis", BASIS_PATH, "--json"])
    payload = json.loads(capsys.readouterr().out)
    for key in ("product", "organ", "organ_version", "subject", "records", "summary"):
        assert key in payload, key


def test_cli_json_output_has_no_absolute_path(capsys):
    cp_cli.main(["check", SLUG, "--input", os.path.join(SAMPLES, "ledger-clean.json"),
                 "--basis", BASIS_PATH, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert os.sep not in payload["subject"]


def test_summary_counts_verdicts():
    summary = report(make_subject()).summary()
    assert summary["total"] == 2
    assert summary["verdicts"] == {PASS: 2, FAIL: 0, NOT_APPLICABLE: 0}


def test_no_usable_rows_reports_file_level_fail():
    subject = make_subject(rows=[["", "", "", "", "", "", ""]], dishes=False)
    assert one(findings(subject), "purchase.file:no_usable_rows").verdict == FAIL


def test_header_only_ledger_is_input_error():
    subject = make_subject(rows=[], dishes=False)
    with pytest.raises(ENGINE.CostError):
        findings(subject)


def test_row_verdicts_follow_status():
    subject = make_subject(rows=[ROW_CABBAGE[:4] + ["克拉"] + ROW_CABBAGE[5:], ROW_CABBAGE],
                           dishes=False)
    assert one(findings(subject),
               "purchase.row:L2:unit_unregistered").verdict == NOT_APPLICABLE


def test_invalid_row_verdict_is_fail():
    subject = make_subject(rows=[["", "", "", "", "", "", ""]], dishes=False)
    assert one(findings(subject), "purchase.row:L2:required_empty").verdict == FAIL


def test_all_row_records_anchor_to_import_contract():
    subject = make_subject(rows=[["", "", "", "", "", "", ""]], dishes=False)
    assert one(findings(subject),
               "purchase.row:L2:required_empty").anchor.clause_id == REGISTRY.CLAUSE_IMPORT_MAP


def test_duplicate_dish_names_are_rejected():
    subject = make_subject(dishes=[DISH, DISH])
    with pytest.raises(ENGINE.CostError):
        findings(subject)


def test_subject_must_be_mapping():
    with pytest.raises(ENGINE.CostError):
        PACK_MOD.evaluate([], basis())


def test_ledger_header_must_be_array():
    subject = make_subject()
    subject["purchase_ledger"]["header"] = "日期,品名"
    with pytest.raises(ENGINE.CostError):
        findings(subject)


def test_ledger_row_must_be_array():
    subject = make_subject()
    subject["purchase_ledger"]["rows"] = ["not-a-row"]
    with pytest.raises(ENGINE.CostError):
        findings(subject)


def test_dishes_must_be_non_empty_when_present():
    subject = make_subject()
    subject["dishes"] = []
    with pytest.raises(ENGINE.CostError):
        findings(subject)


def test_snapshots_must_have_old_and_new():
    subject = make_subject()
    subject["snapshots"] = {"old": _snap("2026-08-06", {})}
    with pytest.raises(ENGINE.CostError):
        findings(subject)


def _params_json():
    with open(os.path.join(DATA_DIR, "params.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)