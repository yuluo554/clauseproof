"""器官 ``lease-terms`` 无损判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在「判定结果」上。
来源仓判定层（D1 + D18 机械选 6 文件 / 实跑 111 passed / AST 函数 85）逐文件处置见
``docs/lease-terms.md`` §6。

本文件同时是**漂移门**：``data/rulesets.json`` 与 ``registry.RULE_TABLE``、
``data/clauses.json`` 与规则包 ``quote`` 必须逐条一致（手改任一侧即红）。
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

PACK_MOD = importlib.import_module("clauseproof.packs.lease-terms")
ENGINE = importlib.import_module("clauseproof.packs.lease-terms.engine")
REGISTRY = importlib.import_module("clauseproof.packs.lease-terms.registry")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "lease-terms")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "lease-terms")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
DEMO_PATH = os.path.join(SAMPLES, "card-demo-bj.json")
CARDS_PATH = os.path.join(SAMPLES, "cards.json")


def basis():
    return Basis.from_json(BASIS_PATH)


def ruleset_json():
    with open(os.path.join(DATA_DIR, "rulesets.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)["rulesets"]


def demo():
    with open(DEMO_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def sample_cards():
    with open(CARDS_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)["cards"]


def sample(sample_id):
    for card in sample_cards():
        if card["sample_id"] == sample_id:
            return card
    raise AssertionError(sample_id)


def card(city="北京", party="enterprise", lease_kind="ordinary", fields=None,
         text=None, clauses=None, **extra):
    payload = {
        "city": city,
        "party": party,
        "lease_kind": lease_kind,
        "fields": {"deposit_months": "1"} if fields is None else fields,
        "contract_text": demo()["contract_text"] if text is None else text,
        "clauses": [{"number": "第一条", "text": "租赁"}] if clauses is None else clauses,
    }
    payload.update(extra)
    return payload


def rule(rule_id, city="北京"):
    for item in REGISTRY.rules_for_overlay(city):
        if item["rule_id"] == rule_id:
            return item
    raise AssertionError(rule_id)


def judge(rule_id, subject, city="北京"):
    return ENGINE.judge_rule(rule(rule_id, city), subject)


def findings(subject, rules=None):
    return tuple(PACK_MOD.evaluate_with_rules(subject, basis(), rules))


def one(found, rule_id):
    hits = [finding for finding in found if finding.rule_id == rule_id]
    assert len(hits) == 1, (rule_id, [f.rule_id for f in found])
    return hits[0]


def report(subject, rules=None):
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject="card.json", findings=findings(subject, rules))


def _read(name):
    with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
        return handle.read()


# ==========================================================================
# 一、器官契约与装配
# ==========================================================================
def test_pack_is_registered_under_slug():
    pack = get(SLUG)
    assert isinstance(pack, Pack)
    assert pack.slug == SLUG
    assert pack.version == PACK_MOD.VERSION


def test_pack_version_matches_source_release():
    assert PACK_MOD.VERSION == "0.1.1"


def test_pack_declares_city_as_required_field():
    assert get(SLUG).input_fields == ("city",)


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


def test_pack_has_no_clock_or_network():
    banned = ("time", "datetime", "random", "socket", "urllib", "requests")
    for name in ("__init__.py", "engine.py", "registry.py"):
        tree = ast.parse(_read(name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in banned, (name, alias.name)
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in banned, (name, node.module)


def test_pack_has_no_print_calls():
    for name in ("__init__.py", "engine.py", "registry.py"):
        tree = ast.parse(_read(name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("print", "input"), (name, node.lineno)


def test_engine_has_no_policy_literals_in_dispatch():
    """零政策字面量：engine 的运算符表只有运算符，没有阈值数值。"""
    tree = ast.parse(_read("engine.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            assert node.value in (0, 1), ("engine 出现非结构数值", node.lineno, node.value)


def test_evaluate_signature_is_fixed():
    import inspect

    assert list(inspect.signature(PACK_MOD.evaluate).parameters) == ["subject", "basis"]


# ==========================================================================
# 二、规则包漂移门（registry ↔ data/rulesets.json）
# ==========================================================================
def test_ruleset_json_is_shipped_asset():
    assert os.path.isfile(os.path.join(DATA_DIR, "rulesets.json"))


def test_ruleset_json_has_three_cities():
    payload = ruleset_json()
    assert set(payload) == {"全国", "北京", "上海"}


def test_ruleset_json_rule_counts_match_registry():
    payload = ruleset_json()
    for city in ("全国", "北京", "上海"):
        assert len(payload[city]["rules"]) == len(REGISTRY.rules_for(city)), city


def test_ruleset_ids_match_source():
    payload = ruleset_json()
    for city in ("全国", "北京", "上海"):
        assert payload[city]["ruleset_id"] == REGISTRY.CITY_RULESETS[city][0]


def test_ruleset_versions_match_source():
    payload = ruleset_json()
    for city in ("全国", "北京", "上海"):
        assert payload[city]["version"] == REGISTRY.CITY_RULESETS[city][1]


def test_registry_rule_order_matches_source():
    payload = ruleset_json()
    for city in ("全国", "北京", "上海"):
        expected = [item["rule_id"] for item in payload[city]["rules"]]
        actual = [item["rule_id"] for item in REGISTRY.rules_for(city)]
        assert actual == expected, city


def test_every_rule_value_matches_source():
    payload = ruleset_json()
    for city in ("全国", "北京", "上海"):
        for item in payload[city]["rules"]:
            mine = dict((r["rule_id"], r) for r in REGISTRY.rules_for(city))[item["rule_id"]]
            assert mine["value"] == item.get("value"), (city, item["rule_id"])
            assert mine["unit"] == item.get("unit"), (city, item["rule_id"])


def test_every_rule_operator_matches_source():
    payload = ruleset_json()
    for city in ("全国", "北京", "上海"):
        for item in payload[city]["rules"]:
            mine = dict((r["rule_id"], r) for r in REGISTRY.rules_for(city))[item["rule_id"]]
            assert mine["op"] == item.get("op"), (city, item["rule_id"])


def test_every_rule_applies_if_matches_source():
    payload = ruleset_json()
    for city in ("全国", "北京", "上海"):
        for item in payload[city]["rules"]:
            mine = dict((r["rule_id"], r) for r in REGISTRY.rules_for(city))[item["rule_id"]]
            expected = dict((key, tuple(value)) for key, value in (item.get("applies_if") or {}).items())
            assert dict(mine["applies_if"]) == expected, (city, item["rule_id"])


def test_every_rule_scope_matches_source():
    payload = ruleset_json()
    for city in ("全国", "北京", "上海"):
        for item in payload[city]["rules"]:
            mine = dict((r["rule_id"], r) for r in REGISTRY.rules_for(city))[item["rule_id"]]
            assert mine["scope"] == item["scope"], (city, item["rule_id"])


def test_every_rule_status_is_verified():
    for city in ("全国", "北京", "上海"):
        for item in REGISTRY.rules_for(city):
            assert item["status"] == "verified", item["rule_id"]


def test_every_rule_clause_matches_source():
    payload = ruleset_json()
    for city in ("全国", "北京", "上海"):
        for item in payload[city]["rules"]:
            mine = dict((r["rule_id"], r) for r in REGISTRY.rules_for(city))[item["rule_id"]]
            assert mine["clause"] == item["clause"], (city, item["rule_id"])


def test_every_rule_source_is_registered():
    for city in ("全国", "北京", "上海"):
        for item in REGISTRY.rules_for(city):
            assert item["source_id"] in REGISTRY.SOURCES, item["rule_id"]


def test_elements_are_declared_for_element_rules():
    for city in ("全国", "北京", "上海"):
        for item in REGISTRY.rules_for(city):
            if item["check_type"] == "element_completeness":
                assert item["elements"], item["rule_id"]


def test_elements_match_source_aliases():
    payload = ruleset_json()
    for city in ("全国", "北京", "上海"):
        for item in payload[city]["rules"]:
            if not item.get("elements"):
                continue
            mine = dict((r["rule_id"], r) for r in REGISTRY.rules_for(city))[item["rule_id"]]
            expected = tuple((el["name"], tuple(el.get("aliases") or []))
                             for el in item["elements"])
            assert mine["elements"] == expected, item["rule_id"]


def test_total_rule_count_is_twentyone():
    assert len(REGISTRY.all_rule_ids()) == 21


def test_rule_ids_are_unique_per_city():
    for city in ("全国", "北京", "上海"):
        ids = [item["rule_id"] for item in REGISTRY.rules_for(city)]
        assert len(ids) == len(set(ids)), city


def test_overlay_adds_national_rules_to_city():
    ids = [item["rule_id"] for item in REGISTRY.rules_for_overlay("北京")]
    assert "CN-LEASE-TERM-MAX" in ids
    assert len(ids) == 14


def test_overlay_dedupes_by_rule_id():
    ids = [item["rule_id"] for item in REGISTRY.rules_for_overlay("北京")]
    assert len(ids) == len(set(ids))


def test_national_overlay_is_identity_for_national():
    assert len(REGISTRY.rules_for_overlay("全国")) == 4


def test_shanghai_overlay_count():
    assert len(REGISTRY.rules_for_overlay("上海")) == 11


# ==========================================================================
# 三、条文库（锚点）漂移门
# ==========================================================================
def test_clauses_version_is_composite_coordinate():
    assert basis().version == REGISTRY.CLAUSES_VERSION
    assert basis().version == "cn-2021.01+bj-2024.10+sh-2023.02"


def test_clauses_cover_every_rule():
    assert set(basis().clause_ids()) == set(REGISTRY.clause_ids())


def test_clauses_have_expected_count():
    assert len(basis()) == 21


def test_every_rule_clause_id_exists_in_basis():
    for city in ("全国", "北京", "上海"):
        for item in REGISTRY.rules_for(city):
            assert basis().clause(item["clause_id"]) is not None, item["rule_id"]


def test_clause_text_matches_source_quote():
    payload = ruleset_json()
    catalog = basis()
    for city in ("全国", "北京", "上海"):
        for item in payload[city]["rules"]:
            mine = dict((r["rule_id"], r) for r in REGISTRY.rules_for(city))[item["rule_id"]]
            assert catalog.clause(mine["clause_id"]).text == item["quote"], item["rule_id"]


def test_clause_path_names_the_instrument():
    for clause_id in basis().clause_ids():
        path = basis().clause(clause_id).path
        assert "《" in path and "》" in path, clause_id


def test_clause_effective_dates_come_from_sources():
    payload = ruleset_json()
    by_source = {}
    for city in payload:
        for item in payload[city]["sources"]:
            by_source[item["source_id"]] = item.get("effective_date")
    for city in ("全国", "北京", "上海"):
        for item in REGISTRY.rules_for(city):
            clause = basis().clause(item["clause_id"])
            assert clause.effective == by_source[item["source_id"]], item["rule_id"]


def test_same_clause_different_paragraphs_get_own_entries():
    ids = [item["clause_id"] for item in REGISTRY.rules_for("北京")]
    assert "bj-rental:第三十六条#1" in ids
    assert "bj-rental:第三十六条#2" in ids
    assert "bj-rental:第三十六条#3" in ids


def test_split_entries_keep_distinct_quotes():
    catalog = basis()
    quotes = {catalog.clause("bj-rental:第三十六条#%d" % index).text for index in (1, 2, 3)}
    assert len(quotes) == 3


def test_source_titles_are_registered():
    assert REGISTRY.SOURCES["SRC-CN-CIVIL-CODE"]["title"] == "《中华人民共和国民法典》"
    assert REGISTRY.SOURCES["SRC-BJ-HOUSING-RENTAL"]["title"] == "《北京市住房租赁条例》"


def test_basis_requires_all_clauses_for_a_city():
    catalog = basis()
    for rule_id in ("BJ-DEPOSIT-MAX-1M", "SH-AFFORDABLE-TERM-MIN-1Y", "CN-LEASE-TERM-MAX"):
        city = "上海" if rule_id.startswith("SH") else "北京"
        assert catalog.clause(rule(city=city, rule_id=rule_id)["clause_id"]) is not None


# ==========================================================================
# 四、门控（status / 锚点 / 作用域）
# ==========================================================================
def test_gate_keeps_all_verified_city_rules():
    gated = ENGINE.effective_rules("北京")
    assert len(gated["kept"]) == 12
    assert gated["disabled"] == []


def test_gate_collects_quota_rules_as_reference():
    gated = ENGINE.effective_rules("北京")
    assert {item["rule_id"] for item in gated["reference"]} == {
        "BJ-RENT-INTERVENTION", "BJ-ESCROW-RENT-SUPERVISION"}


def test_gate_rejects_pending_status():
    rules = [dict(rule("BJ-DEPOSIT-MAX-1M"), status="pending")]
    gated = ENGINE.gate_rules(rules)
    assert gated["kept"] == []
    assert gated["disabled"][0]["reason"].startswith("数值核对状态非 verified")


def test_gate_rejects_missing_clause():
    rules = [dict(rule("BJ-DEPOSIT-MAX-1M"), clause=None)]
    gated = ENGINE.gate_rules(rules)
    assert gated["disabled"][0]["reason"] == "缺锚点（条款号），不参与判定"


def test_gate_rejects_missing_clause_id():
    rules = [dict(rule("BJ-DEPOSIT-MAX-1M"), clause_id=None)]
    gated = ENGINE.gate_rules(rules)
    assert "条文锚点" in gated["disabled"][0]["reason"]


def test_gate_rejects_missing_source():
    rules = [dict(rule("BJ-DEPOSIT-MAX-1M"), source_id=None)]
    gated = ENGINE.gate_rules(rules)
    assert "来源" in gated["disabled"][0]["reason"]


def test_gate_scope_check_only_takes_check_rules():
    gated = ENGINE.effective_rules("北京", "check")
    assert {item["scope"] for item in gated["kept"]} == {"check"}


def test_gate_scope_quota_only_takes_quota_rules():
    """口径差：旧仓 quota 作用域实际返回空集（分支先 continue），器官保留 quota 条目。"""
    gated = ENGINE.effective_rules("北京", "quota")
    assert {item["scope"] for item in gated["kept"]} == {"quota"}


def test_gate_scope_calc_includes_check_rules():
    gated = ENGINE.effective_rules("北京", "calc")
    assert "check" in {item["scope"] for item in gated["kept"]}


def test_gate_rejects_unknown_scope():
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.gate_rules([], "shipping")


def test_effective_rules_rejects_unknown_city():
    with pytest.raises(ENGINE.RulesetError):
        ENGINE.effective_rules("广州")


def test_pending_quota_rule_also_enters_disabled():
    rules = [dict(rule("BJ-RENT-INTERVENTION"), status="pending")]
    gated = ENGINE.gate_rules(rules)
    assert gated["disabled"][0]["rule_id"] == "BJ-RENT-INTERVENTION"


def test_disabled_quota_rule_is_listed_once():
    rules = [dict(rule("BJ-RENT-INTERVENTION"), status="pending")]
    gated = ENGINE.gate_rules(rules, "calc")
    assert [entry["rule_id"] for entry in gated["disabled"]] == ["BJ-RENT-INTERVENTION"]


# ==========================================================================
# 五、适用域三态
# ==========================================================================
def test_party_any_always_applies():
    assert judge("BJ-FILING-30D", card(party="individual",
                                       fields={"filing_days": "15"}))["status"] == "compliant"


def test_enterprise_rule_applies_to_enterprise():
    assert ENGINE.applicability(rule("BJ-DEPOSIT-MAX-1M"),
                                card(party="enterprise")) == ENGINE.APPLIES


def test_enterprise_rule_skipped_for_individual():
    outcome = judge("BJ-DEPOSIT-MAX-1M", card(party="individual"))
    assert outcome["status"] == ENGINE.STATUS_SKIPPED
    assert "适用主体限于 enterprise" in outcome["reason"]


def test_enterprise_rule_unknown_for_unknown_party():
    outcome = judge("BJ-DEPOSIT-MAX-1M", card(party="unknown"))
    assert outcome["status"] == ENGINE.STATUS_UNKNOWN
    assert "无法确定合同主体" in outcome["reason"]


def test_unknown_party_is_not_skipped():
    """主体未知 ≠ 不适用：把 indeterminate 记成 skipped 等于替用户断言「这条不适用」。"""
    assert judge("BJ-DEPOSIT-MAX-1M", card(party="unknown"))["status"] != "skipped"


def test_affordable_rule_skipped_for_ordinary():
    assert judge("SH-AFFORDABLE-DEPOSIT-1M", card(city="上海", lease_kind="ordinary"),
                 city="上海")["status"] == ENGINE.STATUS_SKIPPED


def test_affordable_rule_applies_for_affordable():
    outcome = judge("SH-AFFORDABLE-DEPOSIT-1M",
                    card(city="上海", lease_kind="affordable", fields={"deposit_months": "1"}),
                    city="上海")
    assert outcome["status"] == ENGINE.STATUS_COMPLIANT


def test_lease_kind_reason_mentions_kind():
    outcome = judge("SH-AFFORDABLE-DEPOSIT-1M", card(city="上海", lease_kind="ordinary"),
                    city="上海")
    assert "适用房屋类型限于 affordable" in outcome["reason"]


def test_applicability_returns_indeterminate_for_unknown_party():
    assert ENGINE.applicability(rule("BJ-DEPOSIT-MAX-1M"),
                                card(party="unknown")) == ENGINE.INDETERMINATE


def test_applicability_returns_not_applies_for_individual():
    assert ENGINE.applicability(rule("BJ-DEPOSIT-MAX-1M"),
                                card(party="individual")) == ENGINE.NOT_APPLIES


# ==========================================================================
# 六、四类判定
# ==========================================================================
def test_numeric_upper_limit_compliant_at_boundary():
    outcome = judge("BJ-DEPOSIT-MAX-1M", card(fields={"deposit_months": "1"}))
    assert outcome["status"] == ENGINE.STATUS_COMPLIANT


def test_numeric_upper_limit_noncompliant_above():
    outcome = judge("BJ-DEPOSIT-MAX-1M", card(fields={"deposit_months": "1.5"}))
    assert outcome["status"] == ENGINE.STATUS_NONCOMPLIANT
    assert "超过规则上限" in outcome["reason"]


def test_numeric_lower_limit_noncompliant_below():
    subject = card(city="上海", lease_kind="affordable", fields={"lease_term_years": "0.5"})
    outcome = judge("SH-AFFORDABLE-TERM-MIN-1Y", subject, city="上海")
    assert outcome["status"] == ENGINE.STATUS_NONCOMPLIANT
    assert "低于规则下限" in outcome["reason"]


def test_numeric_lower_limit_compliant_at_boundary():
    subject = card(city="上海", lease_kind="affordable", fields={"lease_term_years": "1"})
    assert judge("SH-AFFORDABLE-TERM-MIN-1Y", subject,
                 city="上海")["status"] == ENGINE.STATUS_COMPLIANT


def test_numeric_missing_field_is_unknown():
    outcome = judge("BJ-DEPOSIT-MAX-1M", card(fields={"filing_days": "5"}))
    assert outcome["status"] == ENGINE.STATUS_UNKNOWN
    assert outcome["limit"] == 1


def test_numeric_missing_field_still_shows_limit():
    """规则**有**限值，只是合同侧没观测到——否则读者误以为该条没有数值口径。"""
    outcome = judge("BJ-DEPOSIT-MAX-1M", card(fields={}))
    assert outcome["limit"] == 1


def test_numeric_non_numeric_value_is_unknown():
    outcome = judge("BJ-DEPOSIT-MAX-1M", card(fields={"deposit_months": "一个月"}))
    assert outcome["status"] == ENGINE.STATUS_UNKNOWN
    assert "不是数值" in outcome["reason"]


def test_numeric_accepts_native_integer():
    outcome = judge("BJ-DEPOSIT-MAX-1M", card(fields={"deposit_months": 2}))
    assert outcome["status"] == ENGINE.STATUS_NONCOMPLIANT


def test_numeric_records_observed_value():
    outcome = judge("BJ-DEPOSIT-MAX-1M", card(fields={"deposit_months": "1.5"}))
    assert outcome["observed"] == "1.5"


def test_numeric_rule_without_threshold_is_unknown():
    rule_copy = dict(rule("BJ-DEPOSIT-MAX-1M"), op=None, value=None)
    outcome = ENGINE.judge_rule(rule_copy, card(fields={"deposit_months": "1"}))
    assert outcome["status"] == ENGINE.STATUS_UNKNOWN


def test_numeric_unknown_operator_is_unknown():
    rule_copy = dict(rule("BJ-DEPOSIT-MAX-1M"), op="≈")
    outcome = ENGINE.judge_rule(rule_copy, card(fields={"deposit_months": "1"}))
    assert outcome["status"] == ENGINE.STATUS_UNKNOWN


def test_limit_words_direction_for_upper_bound():
    assert ENGINE.limit_words("<=") == ("未超过规则上限", "超过规则上限")


def test_limit_words_direction_for_lower_bound():
    assert ENGINE.limit_words(">=") == ("不低于规则下限", "低于规则下限")


def test_limit_words_does_not_mix_directions():
    ok_words, bad_words = ENGINE.limit_words(">=")
    assert "上限" not in ok_words and "上限" not in bad_words


def test_deadline_with_threshold_delegates_to_numeric():
    outcome = judge("BJ-FILING-30D", card(fields={"filing_days": "31"}))
    assert outcome["status"] == ENGINE.STATUS_NONCOMPLIANT


def test_deadline_declared_true_is_compliant():
    outcome = judge("CN-RENT-PAY-PERIOD", card(fields={"rent_pay_period_declared": True}))
    assert outcome["status"] == ENGINE.STATUS_COMPLIANT


def test_deadline_declared_false_is_unknown_not_violation():
    outcome = judge("CN-RENT-PAY-PERIOD", card(fields={"rent_pay_period_declared": False}))
    assert outcome["status"] == ENGINE.STATUS_UNKNOWN
    assert "非法定违反" in outcome["reason"]


def test_deadline_absent_is_unknown():
    outcome = judge("CN-RENT-PAY-PERIOD", card(fields={}))
    assert outcome["status"] == ENGINE.STATUS_UNKNOWN


def test_elements_all_present_is_compliant():
    outcome = judge("CN-ELEMENT-COMPLETENESS", demo())
    assert outcome["status"] == ENGINE.STATUS_COMPLIANT


def test_elements_missing_one_is_noncompliant():
    text = "房屋租赁，位于北京，面积 100 平方米，用途居住，租期一年，租金按月支付。"
    outcome = judge("CN-ELEMENT-COMPLETENESS", card(text=text))
    assert outcome["status"] == ENGINE.STATUS_NONCOMPLIANT
    assert "租赁物维修" in outcome["reason"]


def test_elements_multiple_missing_are_listed():
    outcome = judge("CN-ELEMENT-COMPLETENESS", card(text="租赁合同：租期一年，租金按月。"))
    assert outcome["status"] == ENGINE.STATUS_NONCOMPLIANT
    assert "缺失法定要素" in outcome["reason"]


def test_elements_alias_prevents_false_missing():
    text = "租赁：房产在朝阳，建筑面积 80 平米，用于居住，租期 2 年，租金每月支付，维护由甲方负责。"
    outcome = judge("CN-ELEMENT-COMPLETENESS", card(text=text))
    assert outcome["status"] == ENGINE.STATUS_COMPLIANT


def test_elements_without_text_is_unknown():
    outcome = judge("CN-ELEMENT-COMPLETENESS", card(text=""))
    assert outcome["status"] == ENGINE.STATUS_UNKNOWN


def test_elements_non_lease_text_is_unknown_not_missing():
    """非合同文本不得被判「缺失法定要素」——那是假 noncompliant。"""
    outcome = judge("CN-ELEMENT-COMPLETENESS",
                    card(text="今天天气不错，适合出门散步。"))
    assert outcome["status"] == ENGINE.STATUS_UNKNOWN
    assert "不是可识别的租赁合同" in outcome["reason"] or "不构成可识别的租赁合同" in outcome["reason"]


def test_elements_rule_without_elements_is_unknown():
    rule_copy = dict(rule("CN-ELEMENT-COMPLETENESS"), elements=None)
    outcome = ENGINE.judge_rule(rule_copy, demo())
    assert outcome["status"] == ENGINE.STATUS_UNKNOWN


def test_looks_like_lease_contract_requires_keyword():
    assert ENGINE.looks_like_lease_contract(card(text="今天天气不错")) is False


def test_looks_like_lease_contract_requires_clauses():
    assert ENGINE.looks_like_lease_contract(card(clauses=[])) is False


def test_looks_like_lease_contract_accepts_demo():
    assert ENGINE.looks_like_lease_contract(demo()) is True


def test_deposit_element_rule_checks_two_names():
    outcome = judge("BJ-CONTRACT-ELEMENT-DEPOSIT", demo())
    assert outcome["status"] == ENGINE.STATUS_COMPLIANT
    assert "2 项" in outcome["reason"]


def test_prohibition_rule_is_skipped():
    outcome = judge("BJ-RENT-INTERVENTION", demo())
    assert outcome["status"] == ENGINE.STATUS_SKIPPED
    assert "监管裁量" in outcome["reason"]


def test_unknown_check_type_is_unknown():
    rule_copy = dict(rule("BJ-DEPOSIT-MAX-1M"), check_type="magic")
    outcome = ENGINE.judge_rule(rule_copy, demo())
    assert outcome["status"] == ENGINE.STATUS_UNKNOWN


def test_national_lease_term_limit():
    outcome = judge("CN-LEASE-TERM-MAX", card(fields={"lease_term_years": "21"}))
    assert outcome["status"] == ENGINE.STATUS_NONCOMPLIANT


def test_national_lease_term_at_twenty_years_is_compliant():
    outcome = judge("CN-LEASE-TERM-MAX", card(fields={"lease_term_years": "20"}))
    assert outcome["status"] == ENGINE.STATUS_COMPLIANT


# ==========================================================================
# 七、整体等级与计数
# ==========================================================================
def _statuses(*pairs):
    return [{"status": status, "rule_id": str(index)} for index, status in enumerate(pairs)]


def test_overall_compliant_when_all_pass():
    assert ENGINE.overall_status(_statuses("compliant", "compliant")) == "compliant"


def test_overall_noncompliant_wins():
    assert ENGINE.overall_status(
        _statuses("compliant", "noncompliant")) == "noncompliant"


def test_overall_unknown_is_not_assessed():
    assert ENGINE.overall_status(_statuses("compliant", "unknown")) == "not_assessed"


def test_overall_all_skipped_is_not_assessed():
    assert ENGINE.overall_status(_statuses("skipped", "skipped")) == "not_assessed"


def test_overall_empty_is_not_assessed():
    assert ENGINE.overall_status([]) == "not_assessed"


def test_overall_never_claims_compliant_with_unknown():
    assert ENGINE.overall_status(_statuses("unknown")) != "compliant"


def test_status_counts_counts_each_state():
    counts = ENGINE.status_counts(_statuses("compliant", "compliant", "skipped"))
    assert counts == {"compliant": 2, "skipped": 1}


def test_summary_text_mentions_undetermined():
    text = ENGINE.summary_text(_statuses("compliant", "unknown"))
    assert "未能判定 1 项" in text


def test_summary_text_mentions_skipped():
    text = ENGINE.summary_text(_statuses("compliant", "skipped"))
    assert "不适用 1 项" in text


def test_summary_text_starts_with_overall():
    assert ENGINE.summary_text(_statuses("noncompliant")) .startswith("noncompliant")


# ==========================================================================
# 八、样例真值对账（12 例）
# ==========================================================================
def _sample_statuses(card_payload):
    gated = ENGINE.effective_rules(card_payload["city"])
    judged = ENGINE.judge_card(card_payload, gated["kept"])
    return ({item["rule_id"]: item["status"] for item in judged},
            {item["rule_id"] for item in gated["reference"]})


def _check_sample(sample_id):
    payload = sample(sample_id)
    statuses, references = _sample_statuses(payload)
    assert statuses == payload["expect"], sample_id
    assert references == set(payload["also_expect"]), sample_id


def test_sample_bj_001():
    _check_sample("S-BJ-001")


def test_sample_bj_002():
    _check_sample("S-BJ-002")


def test_sample_bj_003():
    _check_sample("S-BJ-003")


def test_sample_bj_004():
    _check_sample("S-BJ-004")


def test_sample_sh_005():
    _check_sample("S-SH-005")


def test_sample_sh_006():
    _check_sample("S-SH-006")


def test_sample_sh_007():
    _check_sample("S-SH-007")


def test_sample_sh_008():
    _check_sample("S-SH-008")


def test_sample_sh_009():
    _check_sample("S-SH-009")


def test_sample_sh_010():
    _check_sample("S-SH-010")


def test_sample_bj_011():
    _check_sample("S-BJ-011")


def test_sample_bj_012():
    _check_sample("S-BJ-012")


def test_sample_bj_012_unknown_party_yields_unknown():
    payload = sample("S-BJ-012")
    statuses, _refs = _sample_statuses(payload)
    assert statuses["BJ-DEPOSIT-MAX-1M"] == "unknown"


def test_sample_bj_002_individual_skips_enterprise_rules():
    statuses, _refs = _sample_statuses(sample("S-BJ-002"))
    assert statuses["BJ-DEPOSIT-MAX-1M"] == "skipped"


def test_sample_sh_009_affordable_rules_apply():
    statuses, _refs = _sample_statuses(sample("S-SH-009"))
    assert statuses["SH-AFFORDABLE-DEPOSIT-1M"] in ("compliant", "noncompliant")


def test_sample_cards_are_twelve():
    assert len(sample_cards()) == 12


# ==========================================================================
# 九、账本映射与退出码
# ==========================================================================
def test_demo_has_fourteen_records():
    assert len(findings(demo())) == 14


def test_demo_pass_count_matches_source_report():
    found = findings(demo())
    assert len([f for f in found if f.verdict == PASS]) == 10


def test_demo_fail_count_matches_source_report():
    found = findings(demo())
    blocking = [f for f in found if f.verdict == FAIL]
    assert len(blocking) == 1
    assert blocking[0].rule_id == "BJ-LODGING-REG-3WD"


def test_demo_na_count_matches_source_report():
    found = findings(demo())
    assert len([f for f in found if f.verdict == NOT_APPLICABLE]) == 3


def test_demo_exit_code_is_blocked():
    assert report(demo()).exit_code() == EXIT_BLOCKED


def test_compliant_sample_exit_code_is_ok():
    assert report(sample("S-BJ-002")).exit_code() == EXIT_OK


def test_every_non_na_finding_has_anchor():
    for finding in findings(demo()):
        if finding.verdict != NOT_APPLICABLE:
            assert finding.anchor is not None, finding.rule_id


def test_unknown_finding_keeps_its_anchor():
    finding = one(findings(demo()), "BJ-ENTERPRISE-FILING-30D")
    assert finding.verdict == NOT_APPLICABLE
    assert finding.anchor is not None


def test_quota_records_are_not_obligations():
    found = findings(demo())
    for rule_id in ("BJ-RENT-INTERVENTION", "BJ-ESCROW-RENT-SUPERVISION"):
        assert one(found, rule_id).verdict == NOT_APPLICABLE


def test_quota_message_says_reference_only():
    assert "仅作提示" in one(findings(demo()), "BJ-RENT-INTERVENTION").message


def test_disabled_rule_has_no_anchor():
    rules = [dict(item) for item in REGISTRY.rules_for_overlay("北京")]
    for item in rules:
        if item["rule_id"] == "BJ-FILING-30D":
            item["status"] = "pending"
    found = findings(demo(), rules)
    disabled = one(found, "BJ-FILING-30D")
    assert disabled.verdict == NOT_APPLICABLE
    assert disabled.anchor is None
    assert disabled.evidence["disabled"] is True


def test_disabled_rule_is_not_judged():
    rules = [dict(item) for item in REGISTRY.rules_for_overlay("北京")]
    for item in rules:
        if item["rule_id"] == "BJ-FILING-30D":
            item["clause"] = None
    found = findings(demo(), rules)
    assert one(found, "BJ-FILING-30D").evidence["disabled"] is True


def test_finding_ids_are_unique():
    ids = [finding.id for finding in report(demo()).findings]
    assert len(ids) == len(set(ids))


def test_report_json_is_deterministic():
    first = json.dumps(report(demo()).as_dict(), ensure_ascii=False, sort_keys=True)
    second = json.dumps(report(demo()).as_dict(), ensure_ascii=False, sort_keys=True)
    assert first == second


def test_evidence_carries_limit_and_observed():
    evidence = one(findings(demo()), "BJ-DEPOSIT-MAX-1M").evidence
    assert evidence["limit"] == 1
    assert evidence["observed"] == "1.00"


def test_evidence_carries_source_metadata():
    evidence = one(findings(demo()), "CN-LEASE-TERM-MAX").evidence
    assert evidence["doc_no"] == "主席令第四十五号"
    assert evidence["source_title"] == "《中华人民共和国民法典》"


def test_evidence_carries_clause_number():
    assert one(findings(demo()), "CN-LEASE-TERM-MAX").evidence["clause"] == "第七百零五条"


def test_missing_basis_clause_is_contract_error():
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate(demo(), Basis.empty(REGISTRY.CLAUSES_VERSION))


def test_basis_version_mismatch_is_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(demo(), Basis.empty("2020-01-01"))


def test_unknown_city_is_input_error():
    with pytest.raises(ENGINE.CardError):
        PACK_MOD.evaluate(card(city="广州"), basis())


def test_unknown_party_is_input_error():
    with pytest.raises(ENGINE.CardError):
        PACK_MOD.evaluate(card(party="company"), basis())


def test_unknown_lease_kind_is_input_error():
    with pytest.raises(ENGINE.CardError):
        PACK_MOD.evaluate(card(lease_kind="luxury"), basis())


def test_fields_must_be_object():
    with pytest.raises(ENGINE.CardError):
        PACK_MOD.evaluate(card(fields=[]), basis())


def test_clause_without_number_is_input_error():
    with pytest.raises(ENGINE.CardError):
        PACK_MOD.evaluate(card(clauses=[{"text": "x"}]), basis())


def test_cli_demo_returns_blocked(capsys):
    code = cp_cli.main(["check", SLUG, "--input", DEMO_PATH, "--basis", BASIS_PATH])
    assert code == EXIT_BLOCKED
    assert "阻断 1 条" in capsys.readouterr().out


def test_cli_missing_basis_returns_contract_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input", DEMO_PATH])
    assert code == EXIT_CONTRACT
    assert "ContractError" in capsys.readouterr().err


def test_cli_missing_file_returns_input_code():
    assert cp_cli.main(["check", SLUG, "--input", "no-such.json",
                        "--basis", BASIS_PATH]) == EXIT_INPUT


def test_cli_json_output_has_organ(capsys):
    cp_cli.main(["check", SLUG, "--input", DEMO_PATH, "--basis", BASIS_PATH, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG
    assert payload["summary"]["blocking"] == 1


def test_cli_json_output_is_deterministic(capsys):
    cp_cli.main(["check", SLUG, "--input", DEMO_PATH, "--basis", BASIS_PATH, "--json"])
    first = capsys.readouterr().out
    cp_cli.main(["check", SLUG, "--input", DEMO_PATH, "--basis", BASIS_PATH, "--json"])
    assert capsys.readouterr().out == first


# ==========================================================================
# 十、确定性与纯函数性
# ==========================================================================
def test_evaluate_does_not_mutate_subject():
    subject = demo()
    before = json.dumps(subject, ensure_ascii=False, sort_keys=True)
    findings(subject)
    assert json.dumps(subject, ensure_ascii=False, sort_keys=True) == before


def test_rule_table_is_not_mutated_by_judging():
    before = copy.deepcopy(REGISTRY.RULE_TABLE)
    findings(demo())
    assert REGISTRY.RULE_TABLE == before


def test_judge_card_order_follows_rule_order():
    gated = ENGINE.effective_rules("北京")
    judged = ENGINE.judge_card(demo(), gated["kept"])
    assert [item["rule_id"] for item in judged] == [item["rule_id"] for item in gated["kept"]]


def test_two_runs_produce_same_statuses():
    first = {f.rule_id: f.verdict for f in findings(demo())}
    second = {f.rule_id: f.verdict for f in findings(demo())}
    assert first == second