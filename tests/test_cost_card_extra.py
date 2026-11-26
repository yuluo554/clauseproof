"""器官 ``cost-card`` 真值对账与边界测试（§7.3 判据 1 的观测面续）。

**真值库是只读拷贝**：``samples/cost-card/truth-*.json`` 来自来源仓冻结真值库
（输入 + 期望；观测结果不冻进库）。本文件按用例 **活体观测**：把内联输入喂给本器官的
同一批公开函数，再与冻结期望键对账——引擎坏掉就会被抓出来。

对账键格式沿用来源仓的「结论键」口径（``issue:L2:not_numeric:invalid`` /
``card:醋溜白菜:ok`` / ``cost:醋溜白菜=2.12`` / ``status:大白菜=up``）：
键名把结论编进名字，值恒为 ``ok``，故「漏一个 + 多一个」同时暴露。

**输入侧不复刻的两处**（见 ``docs/cost-card.md`` §5）：一是文件编码（只收 UTF-8 是
输入层的门，器官收已解码文本）；二是 CSV 物理解析（引号/换行由输入层处理）。
"""

import copy
import csv
import importlib
import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from clauseproof.core.basis import Basis  # noqa: E402
from clauseproof.core.ledger import FAIL, NOT_APPLICABLE, PASS  # noqa: E402

PACK_MOD = importlib.import_module("clauseproof.packs.cost-card")
ENGINE = importlib.import_module("clauseproof.packs.cost-card.engine")
REGISTRY = importlib.import_module("clauseproof.packs.cost-card.registry")

SAMPLES = os.path.join(ROOT, "samples", "cost-card")
BASIS = Basis.from_json(os.path.join(SRC, "clauseproof", "packs", "cost-card", "data",
                                     "clauses.json"))
LEDGER_SOURCE = {"kind": "user", "ref": "truth.csv"}
BOM_SOURCE = {"kind": "user", "ref": "truth.json"}


# ------------------------------------------------------------------ 通用工具
def _truth(name):
    with open(os.path.join(SAMPLES, "truth-%s.json" % name), "r", encoding="utf-8") as handle:
        return json.load(handle)["cases"]


def _case(name, case_id):
    for case in _truth(name):
        if case["id"] == case_id:
            return case
    raise AssertionError("真值库没有用例 %s/%s" % (name, case_id))


def _expected(name, case_id):
    return set(_case(name, case_id)["expect_keys"])


def _csv_rows(text):
    """输入层替身：已解码文本 → 表头 + 行数组（BOM 由解码层吃掉）。"""
    reader = csv.reader(io.StringIO(text.lstrip("\ufeff"), newline=""))
    rows = list(reader)
    if not rows:
        return [], []
    return rows[0], [row for row in rows[1:] if row]


def _observe_import(case):
    header, rows = _csv_rows(case["input"]["purchases_csv"])
    try:
        parsed = ENGINE.judge_rows(header, rows, source=LEDGER_SOURCE)
    except ENGINE.CostError:
        return {"form:rejected"}
    if not parsed["rows"] and not parsed["issues"]:
        return {"form:rejected"}
    observed = {"form:accepted", "rows:%d" % len(parsed["rows"])}
    for issue in parsed["issues"]:
        observed.add("issue:L%s:%s:%s" % (issue["line"], issue["code"], issue["status"]))
    return observed


def _params_with(overrides):
    params = copy.deepcopy(dict(REGISTRY.PARAMS))
    for section, entries in sorted((overrides or {}).items()):
        for name, entry in sorted(entries.items()):
            params[section][name].update(entry)
    return params


def _observe_costcard(case):
    inp = case["input"]
    header, rows = _csv_rows(inp["purchases_csv"])
    dishes = json.loads(inp["bom_json"]).get("dishes")
    params = _params_with(inp.get("params_overrides"))
    try:
        parsed = ENGINE.judge_rows(header, rows, source=LEDGER_SOURCE)
        if not parsed["rows"]:
            raise ENGINE.CostError("无可用行")
        if not dishes:
            raise ENGINE.CostError("BOM 无菜品")
        for dish in dishes:
            if not dish.get("name"):
                raise ENGINE.CostError("菜品缺 name")
        library = ENGINE.build_food_library(parsed["rows"])
        result = ENGINE.compute_costcard(dishes, library,
                                         ENGINE.effective_params(params, "cost"), BOM_SOURCE)
        cards = {card["dish"]: card for card in result["cards"]}
        if not cards:
            raise ENGINE.CostError("成本卡为空")
        ENGINE.compute_pricing(list(cards.values()),
                               ENGINE.effective_params(params, "pricing"))
    except (ValueError, TypeError):
        return {"pipeline:failed"}

    observed = {"pipeline:ok"}
    for dish in dishes:
        name = dish["name"]
        observed.add("card:%s:%s" % (name, "ok" if name in cards else "excluded"))
    for issue in result["issues"]:
        if issue.get("code") in (ENGINE.ISSUE_YIELD_OUT_OF_RANGE, ENGINE.ISSUE_QTY_INVALID):
            observed.add("issue:%s:%s" % (issue["code"], issue["where"]))
    for name in inp.get("observe_costs") or []:
        if name in cards:
            observed.add("cost:%s=%s" % (name, cards[name]["cost"]))
        else:
            observed.add("cost:%s=excluded" % name)
    return observed


def _snapshots():
    with open(os.path.join(SAMPLES, "snapshots.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)


def _snapshot_for(path):
    snapshots = _snapshots()
    if "2026-08-06" in path:
        return snapshots["old"]
    if "2026-09-06" in path:
        return snapshots["mid"]
    return snapshots["new"]


def _observe_alert(case):
    inp = case["input"]
    if inp.get("same_period_guard"):
        snap = _snapshot_for(inp["old_snapshot"])
        try:
            ENGINE.require_distinct_periods(snap["date"], snap["date"])
        except ENGINE.CostError:
            return {"guard:same_period:rejected"}
        return {"guard:same_period:not_rejected"}

    old = _snapshot_for(inp["old_snapshot"])
    new = _snapshot_for(inp["new_snapshot"])
    changes = ENGINE.diff_prices(old["prices"], new["prices"])
    by_name = {row["name"]: row for row in changes}
    observed = set()
    for name in inp.get("observe_foods") or []:
        row = by_name.get(name)
        observed.add("status:%s=%s" % (name, row["status"] if row else "absent"))
    if not inp.get("observe_summary"):
        return observed

    counts = {}
    for row in changes:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    for status in sorted(counts):
        observed.add("count:%s=%d" % (status, counts[status]))
    observed.add("total:%d" % len(changes))
    observed.add("order:%s" % ("descending" if _is_descending(changes) else "not_descending"))
    threshold = REGISTRY.PARAMS["alert"]["threshold"]["value"]
    observed.add("flagged:%d" % len(ENGINE.flag(changes, threshold)))
    return observed


def _is_descending(rows):
    seen_none, last = False, None
    for row in rows:
        rate = row["change_rate"]
        if rate is None:
            seen_none = True
            continue
        if seen_none:
            return False
        if last is not None and rate > last:
            return False
        last = rate
    return True


# ==========================================================================
# 一、真值库活跃对账（19 + 15 + 7 = 41 用例）
# ==========================================================================
def test_truth_import_ok_row():
    assert _observe_import(_case("import", "imp-ok-row")) == _expected("import", "imp-ok-row")


def test_truth_import_required_empty():
    assert _observe_import(_case("import", "imp-required-empty")) == _expected(
        "import", "imp-required-empty")


def test_truth_import_qty_not_numeric():
    assert _observe_import(_case("import", "imp-qty-not-numeric")) == _expected(
        "import", "imp-qty-not-numeric")


def test_truth_import_price_not_numeric():
    assert _observe_import(_case("import", "imp-price-not-numeric")) == _expected(
        "import", "imp-price-not-numeric")


def test_truth_import_negative():
    assert _observe_import(_case("import", "imp-negative")) == _expected("import", "imp-negative")


def test_truth_import_unknown_column_header_level():
    assert _observe_import(_case("import", "imp-unknown-column-header-level")) == _expected(
        "import", "imp-unknown-column-header-level")


def test_truth_import_structure_unparsable():
    assert _observe_import(_case("import", "imp-structure-unparsable")) == _expected(
        "import", "imp-structure-unparsable")


def test_truth_import_unit_unregistered():
    assert _observe_import(_case("import", "imp-unit-unregistered")) == _expected(
        "import", "imp-unit-unregistered")


def test_truth_import_duplicate_names():
    assert _observe_import(_case("import", "imp-duplicate-names")) == _expected(
        "import", "imp-duplicate-names")


def test_truth_import_blank_lines_tolerated():
    assert _observe_import(_case("import", "imp-blank-lines-tolerated")) == _expected(
        "import", "imp-blank-lines-tolerated")


def test_truth_import_amount_not_validated():
    assert _observe_import(_case("import", "imp-amount-not-validated")) == _expected(
        "import", "imp-amount-not-validated")


def test_truth_import_utf8_bom_header():
    assert _observe_import(_case("import", "imp-bom-header")) == _expected(
        "import", "imp-bom-header")


def test_truth_import_shuffled_columns():
    assert _observe_import(_case("import", "imp-shuffled-columns")) == _expected(
        "import", "imp-shuffled-columns")


def test_truth_import_header_whitespace():
    assert _observe_import(_case("import", "imp-header-whitespace")) == _expected(
        "import", "imp-header-whitespace")


def test_truth_import_empty_file():
    assert _observe_import(_case("import", "imp-empty-file")) == _expected(
        "import", "imp-empty-file")


def test_truth_import_whitespace_only():
    assert _observe_import(_case("import", "imp-whitespace-only")) == _expected(
        "import", "imp-whitespace-only")


def test_truth_import_header_only():
    assert _observe_import(_case("import", "imp-header-only")) == _expected(
        "import", "imp-header-only")


def test_truth_import_missing_required_column():
    assert _observe_import(_case("import", "imp-missing-required-column")) == _expected(
        "import", "imp-missing-required-column")


def test_truth_import_non_utf8_is_input_layer_gate():
    """非 UTF-8 进货单由**输入层**拒绝（器官收已解码文本）。

    本用例证明两件事：真值库里该用例的形态是「编码问题」，且器官对**字节**输入
    明确拒绝——不会把未解码的字节当表头静默解出一堆乱码列名。
    """
    case = _case("import", "imp-non-utf8-rejected")
    assert case["input"]["purchases_encoding"] == "gbk"
    with pytest.raises(ENGINE.CostError):
        ENGINE.judge_rows([b"\xd2\xbb\xbb", "品名"], [])


def test_truth_costcard_single_food():
    assert _observe_costcard(_case("costcard", "cc-single-food")) == _expected(
        "costcard", "cc-single-food")


def test_truth_costcard_multi_food():
    assert _observe_costcard(_case("costcard", "cc-multi-food")) == _expected(
        "costcard", "cc-multi-food")


def test_truth_costcard_two_dishes():
    assert _observe_costcard(_case("costcard", "cc-two-dishes")) == _expected(
        "costcard", "cc-two-dishes")


def test_truth_costcard_qty_zero():
    assert _observe_costcard(_case("costcard", "cc-qty-zero")) == _expected(
        "costcard", "cc-qty-zero")


def test_truth_costcard_yield_rate_one():
    assert _observe_costcard(_case("costcard", "cc-yield-rate-one")) == _expected(
        "costcard", "cc-yield-rate-one")


def test_truth_costcard_yield_rate_tiny():
    assert _observe_costcard(_case("costcard", "cc-yield-rate-tiny")) == _expected(
        "costcard", "cc-yield-rate-tiny")


def test_truth_costcard_yield_out_of_range():
    assert _observe_costcard(_case("costcard", "cc-yield-out-of-range")) == _expected(
        "costcard", "cc-yield-out-of-range")


def test_truth_costcard_qty_negative():
    assert _observe_costcard(_case("costcard", "cc-qty-negative")) == _expected(
        "costcard", "cc-qty-negative")


def test_truth_costcard_all_dishes_excluded():
    assert _observe_costcard(_case("costcard", "cc-all-dishes-excluded")) == _expected(
        "costcard", "cc-all-dishes-excluded")


def test_truth_costcard_bom_empty_dishes():
    assert _observe_costcard(_case("costcard", "cc-bom-empty-dishes")) == _expected(
        "costcard", "cc-bom-empty-dishes")


def test_truth_costcard_bom_missing_dishes():
    assert _observe_costcard(_case("costcard", "cc-bom-missing-dishes")) == _expected(
        "costcard", "cc-bom-missing-dishes")


def test_truth_costcard_bom_dish_missing_name():
    assert _observe_costcard(_case("costcard", "cc-bom-dish-missing-name")) == _expected(
        "costcard", "cc-bom-dish-missing-name")


def test_truth_costcard_bom_unknown_food():
    assert _observe_costcard(_case("costcard", "cc-bom-unknown-food")) == _expected(
        "costcard", "cc-bom-unknown-food")


def test_truth_costcard_missing_yield_rate_entry():
    assert _observe_costcard(_case("costcard", "cc-missing-yield-rate-entry")) == _expected(
        "costcard", "cc-missing-yield-rate-entry")


def test_truth_costcard_purchases_no_usable_rows():
    assert _observe_costcard(_case("costcard", "cc-purchases-no-usable-rows")) == _expected(
        "costcard", "cc-purchases-no-usable-rows")


def test_truth_alert_status_down():
    assert _observe_alert(_case("alert", "al-status-down")) == _expected(
        "alert", "al-status-down")


def test_truth_alert_status_flat():
    assert _observe_alert(_case("alert", "al-status-flat")) == _expected(
        "alert", "al-status-flat")


def test_truth_alert_status_gone():
    assert _observe_alert(_case("alert", "al-status-gone")) == _expected(
        "alert", "al-status-gone")


def test_truth_alert_status_new():
    assert _observe_alert(_case("alert", "al-status-new")) == _expected(
        "alert", "al-status-new")


def test_truth_alert_status_up():
    assert _observe_alert(_case("alert", "al-status-up")) == _expected(
        "alert", "al-status-up")


def test_truth_alert_summary_order_threshold():
    assert _observe_alert(_case("alert", "al-summary-order-threshold")) == _expected(
        "alert", "al-summary-order-threshold")


def test_truth_alert_degenerate_same_period():
    assert _observe_alert(_case("alert", "al-degenerate-same-period")) == _expected(
        "alert", "al-degenerate-same-period")


# ==========================================================================
# 二、演示样例与旧 CLI 输出对账（判据 2 的逐值证据）
# ==========================================================================
def _demo():
    with open(os.path.join(SAMPLES, "ledger-demo.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)


def _demo_alert():
    with open(os.path.join(SAMPLES, "ledger-demo-alert.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)


def _run(subject):
    return tuple(PACK_MOD.evaluate(subject, BASIS))


def test_demo_dish_costs_match_old_cli():
    costs = {f.evidence["dish"]: f.evidence["cost"] for f in _run(_demo())
             if f.rule_id.startswith("dish.cost:") and f.verdict == PASS}
    assert costs == {"醋溜白菜": "55.04", "土豆烧牛肉": "7.62", "番茄炒蛋": "16.84",
                     "清蒸草鱼": "100.12", "娃娃菜粉丝煲": "10.44"}


def test_demo_suggested_prices_match_old_cli():
    prices = {f.evidence["dish"]: f.evidence["suggested_price"] for f in _run(_demo())
              if f.rule_id.startswith("pricing.price:")}
    assert prices == {"醋溜白菜": "137.61", "土豆烧牛肉": "19.05", "番茄炒蛋": "42.09",
                      "清蒸草鱼": "250.30", "娃娃菜粉丝煲": "26.10"}


def test_demo_issue_count_matches_old_cli():
    issues = [f for f in _run(_demo()) if f.rule_id.startswith("purchase.row:")]
    assert len(issues) == 6


def test_demo_issue_codes_match_old_cli():
    codes = {f.evidence["code"] for f in _run(_demo()) if f.rule_id.startswith("purchase.row:")}
    assert codes == {"mapping_uncertain", "not_numeric", "required_empty", "negative",
                     "structure_unparsable", "unit_unregistered"}


def test_demo_duplicate_food_matches_old_cli():
    duplicate = [f for f in _run(_demo()) if f.rule_id == "purchase.duplicate:土豆"]
    assert len(duplicate) == 1


def test_demo_library_uses_last_potato_price():
    ledger = _demo()["purchase_ledger"]
    parsed = ENGINE.judge_rows(ledger["header"], ledger["rows"], source=LEDGER_SOURCE)
    library = ENGINE.build_food_library(parsed["rows"])
    assert library["土豆"]["ref_price"] == ENGINE.to_decimal("1.65")


def test_demo_alert_flags_three_menu_foods():
    flagged = {f.evidence["food"] for f in _run(_demo_alert())
               if f.rule_id.startswith("alert.food:") and f.evidence["flagged"]}
    assert flagged == {"大白菜", "娃娃菜", "小白菜"}


def test_demo_alert_reports_four_impacted_dishes():
    """番茄炒蛋的食材（鸡蛋、洋葱）在两期快照里都没有 → 不受价格波动影响。"""
    dishes = {f.evidence["dish"] for f in _run(_demo_alert())
              if f.rule_id.startswith("alert.dish:")}
    assert dishes == {"醋溜白菜", "土豆烧牛肉", "娃娃菜粉丝煲", "清蒸草鱼"}


def test_demo_alert_foods_outside_snapshot_are_absent():
    found = _run(_demo_alert())
    for food in ("洋葱", "牛肉", "猪肉", "鸡蛋"):
        assert "alert.food:%s" % food not in [f.rule_id for f in found]


def test_demo_alert_does_not_change_blocking_count():
    plain = [f for f in _run(_demo()) if f.verdict == FAIL]
    alerted = [f for f in _run(_demo_alert()) if f.verdict == FAIL]
    assert len(plain) == len(alerted) == 3


def test_demo_clean_subject_has_no_blocking():
    with open(os.path.join(SAMPLES, "ledger-clean.json"), "r", encoding="utf-8") as handle:
        clean = json.load(handle)
    assert [f for f in _run(clean) if f.verdict == FAIL] == []


# ==========================================================================
# 三、边界与探活
# ==========================================================================
def test_boundary_f1_monotone_in_yield():
    full = ENGINE.net_unit_price("8", "0.85")
    half = ENGINE.net_unit_price("8", "0.425")
    assert half > full


def test_boundary_f1_near_one_is_just_above_purchase_price():
    near = ENGINE.net_unit_price("10", "0.9999")
    assert near > ENGINE.Decimal("10")


def test_boundary_f3_monotone_in_margin():
    low = ENGINE.suggested_price("10", "0.3")
    high = ENGINE.suggested_price("10", "0.6")
    assert high > low


def test_boundary_f4_round_trip_within_quantization():
    margin = ENGINE.Decimal("0.6")
    price = ENGINE.suggested_price("10", margin)
    actual = ENGINE.actual_margin(price, "10")
    assert abs(actual - margin) < ENGINE.Decimal("0.001")


def test_boundary_flag_just_below_threshold_is_not_flagged():
    changes = ENGINE.diff_prices({"a": "1"}, {"a": "1.0999"})
    assert ENGINE.flag(changes, "0.1") == []


def test_boundary_flag_exactly_at_threshold_is_flagged():
    changes = ENGINE.diff_prices({"a": "1"}, {"a": "1.1"})
    assert len(ENGINE.flag(changes, "0.1")) == 1


def test_boundary_diff_flat_rows_sort_by_name():
    changes = ENGINE.diff_prices({"b": "1", "a": "1"}, {"b": "1", "a": "1"})
    assert [row["name"] for row in changes] == ["a", "b"]


def test_boundary_alert_threshold_override_changes_flagging():
    params = copy.deepcopy(dict(REGISTRY.PARAMS))
    params["alert"]["threshold"]["value"] = "0.50"
    subject = {
        "purchase_ledger": {
            "header": ["品名", "数量", "单价"],
            "rows": [["大白菜", "10", "1.20"]],
            "source": dict(LEDGER_SOURCE),
        },
        "dishes": [{"name": "醋溜白菜", "items": [{"food": "大白菜", "qty": "1.5"}]}],
        "dishes_source": dict(BOM_SOURCE),
        "snapshots": {
            "old": {"date": "2026-08-06", "prices": {"大白菜": "1.20"},
                    "source": {"kind": "snapshot", "ref": "old.json"}},
            "new": {"date": "2026-10-06", "prices": {"大白菜": "1.00"},
                    "source": {"kind": "snapshot", "ref": "new.json"}},
        },
    }
    found = tuple(PACK_MOD.evaluate_with_params(subject, BASIS, params))
    row = [f for f in found if f.rule_id == "alert.food:大白菜"][0]
    assert row.evidence["flagged"] is False


def test_probe_wrong_yield_flips_cost_expectation():
    """探活：把净料率改掉，成本卡必须变——否则「成本算出来了」是永真门。"""
    base = copy.deepcopy(dict(REGISTRY.PARAMS))
    altered = copy.deepcopy(base)
    altered["yield_rates"]["大白菜"]["value"] = "0.50"
    subject = _demo()
    first = [f for f in PACK_MOD.evaluate_with_params(subject, BASIS, base)
             if f.rule_id == "dish.cost:醋溜白菜"][0].evidence["cost"]
    second = [f for f in PACK_MOD.evaluate_with_params(subject, BASIS, altered)
              if f.rule_id == "dish.cost:醋溜白菜"][0].evidence["cost"]
    assert first == "55.04"
    assert second != first


def test_probe_invalid_row_removes_it_from_library():
    subject = _demo()
    ledger = subject["purchase_ledger"]
    clean_rows = [row for row in ledger["rows"] if row[1] == "大白菜"]
    ledger["rows"] = clean_rows + [["2026-10-10", "大白菜", "蔬菜", "abc", "斤", "9.99", "0"]]
    parsed = ENGINE.judge_rows(ledger["header"], ledger["rows"], source=LEDGER_SOURCE)
    library = ENGINE.build_food_library(parsed["rows"])
    assert library["大白菜"]["ref_price"] == ENGINE.to_decimal("37.20")


def test_probe_mutated_threshold_file_would_be_caught_by_drift_gate():
    """漂移门探活：参数包与字面量不一致时，逐条比对必须报红。"""
    payload = json.load(open(os.path.join(SRC, "clauseproof", "packs", "cost-card",
                                          "data", "params.json"), encoding="utf-8"))
    payload["yield_rates"]["土豆"]["value"] = "0.99"
    mismatched = [name for name, _value, _note in REGISTRY.YIELD_RATE_ENTRIES
                  if payload["yield_rates"][name]["value"]
                  != REGISTRY.PARAMS["yield_rates"][name]["value"]]
    assert mismatched == ["土豆"]


# ==========================================================================
# 四、确定性与纯函数性
# ==========================================================================
def test_determinism_two_runs_are_byte_identical():
    first = json.dumps([f.as_dict() for f in _run(_demo())], ensure_ascii=False, sort_keys=True)
    second = json.dumps([f.as_dict() for f in _run(_demo())], ensure_ascii=False,
                        sort_keys=True)
    assert first == second


def test_determinism_evaluate_does_not_mutate_subject():
    subject = _demo()
    before = json.dumps(subject, ensure_ascii=False, sort_keys=True)
    _run(subject)
    assert json.dumps(subject, ensure_ascii=False, sort_keys=True) == before


def test_determinism_alert_run_does_not_mutate_subject():
    subject = _demo_alert()
    before = json.dumps(subject, ensure_ascii=False, sort_keys=True)
    _run(subject)
    assert json.dumps(subject, ensure_ascii=False, sort_keys=True) == before


def test_determinism_record_order_is_stable():
    first = [f.id for f in _run(_demo())]
    second = [f.id for f in _run(_demo())]
    assert first == second


def test_purity_engine_functions_accept_plain_mappings():
    header = ["品名", "数量", "单价"]
    parsed = ENGINE.judge_rows(header, [["大白菜", "1", "1"]])
    assert parsed["rows"][0]["name"] == "大白菜"