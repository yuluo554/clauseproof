"""器官 ``bid-conformity`` 无损判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在「判定结果」上。
来源仓判定层（D1 + D18 机械选 14 文件 / 实跑 169 passed / AST 函数 119）逐文件处置见
``docs/bid-conformity.md`` §6。

本文件同时是**漂移门**：``data/rules.json`` 与 ``registry.RULES``、
``data/blocks.json`` 与 ``data/clauses.json`` 必须逐条一致（手改任一侧即红）。
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

from clauseproof.core.basis import Basis, Clause  # noqa: E402
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

PACK_MOD = importlib.import_module("clauseproof.packs.bid-conformity")
ENGINE = importlib.import_module("clauseproof.packs.bid-conformity.engine")
REGISTRY = importlib.import_module("clauseproof.packs.bid-conformity.registry")
AMOUNTS = importlib.import_module("clauseproof.packs.bid-conformity.amounts")
GATES = importlib.import_module("clauseproof.packs.bid-conformity.gates")
SCHEMA = importlib.import_module("clauseproof.packs.bid-conformity.schema")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "bid-conformity")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "bid-conformity")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
GOODS1 = os.path.join(SAMPLES, "subject-demo-goods-1.json")
GOODS2 = os.path.join(SAMPLES, "subject-demo-goods-2.json")


def basis():
    return Basis.from_json(BASIS_PATH)


def rules_json():
    with open(os.path.join(DATA_DIR, "rules.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)


def blocks_json():
    with open(os.path.join(DATA_DIR, "blocks.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)["blocks"]


def sample(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def tender(**overrides):
    payload = {"qualifications": [], "star_clauses": [], "rejection_clauses": [],
               "key_dates": {}}
    payload.update(overrides)
    return SCHEMA.TenderCard.from_dict(payload)


def bid(**overrides):
    payload = {"qualifications": [], "star_responses": [], "personnel": [],
               "performance": [], "key_dates": {}}
    payload.update(overrides)
    return SCHEMA.BidCard.from_dict(payload)


def subject(tender_card, bid_card, doc_text=None):
    payload = {"tender": tender_card.to_dict(), "bid": bid_card.to_dict()}
    if doc_text is not None:
        payload["doc_text"] = doc_text
    return payload


def findings(subject_payload, rules=None):
    return tuple(PACK_MOD.evaluate_with_rules(subject_payload, basis(), rules))


def ids(found):
    return [finding.rule_id for finding in found]


def one(found, rule_id):
    hits = [finding for finding in found if finding.rule_id == rule_id]
    assert len(hits) == 1, (rule_id, ids(found))
    return hits[0]


def report(subject_payload):
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.ORG_VERSION,
                  subject="cards.json", findings=findings(subject_payload))


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
    assert pack.version == PACK_MOD.ORG_VERSION


def test_pack_version_matches_source_release():
    assert PACK_MOD.ORG_VERSION == "0.6.0"


def test_pack_declares_tender_and_bid_fields():
    assert get(SLUG).input_fields == ("tender", "bid")


def test_pack_is_listed_in_builtin_modules_and_sorted():
    packs_ns = importlib.import_module("clauseproof.packs")
    assert SLUG in packs_ns.BUILTIN_MODULES
    assert list(packs_ns.BUILTIN_MODULES) == sorted(packs_ns.BUILTIN_MODULES)


def test_pack_appears_in_all_packs():
    assert SLUG in [pack.slug for pack in all_packs()]


def test_pack_has_no_own_argument_parser():
    for name in ("__init__.py", "engine.py", "registry.py", "amounts.py", "gates.py"):
        tree = ast.parse(_read(name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(alias.name == "argparse" for alias in node.names), name
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "argparse", name


def test_pack_has_no_file_io():
    for name in ("__init__.py", "engine.py", "registry.py", "amounts.py", "gates.py"):
        tree = ast.parse(_read(name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id != "open", (name, node.lineno)
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("read_text", "write_text"), (name, node.lineno)


def test_pack_has_no_clock_network_or_llm_imports():
    banned = ("time", "datetime", "random", "socket", "urllib", "requests", "http",
              "openai", "anthropic", "httpx")
    for name in ("__init__.py", "engine.py", "registry.py", "amounts.py", "gates.py"):
        tree = ast.parse(_read(name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in banned, (name, alias.name)
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in banned, (name, node.module)


def test_pack_has_no_print_calls():
    for name in ("__init__.py", "engine.py", "registry.py", "amounts.py", "gates.py"):
        tree = ast.parse(_read(name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("print", "input"), (name, node.lineno)


def test_engine_declares_seven_rule_types():
    assert ENGINE.RULE_TYPES == (
        "qualification_match", "star_response", "arithmetic_consistency", "date_logic",
        "bond_check", "rejection_scan", "price_check")


def test_engine_declares_twentyone_check_ids():
    assert len(ENGINE.CHECK_IDS) == 21


def test_evaluate_signature_is_fixed():
    import inspect

    assert list(inspect.signature(PACK_MOD.evaluate).parameters) == ["subject", "basis"]


# ==========================================================================
# 二、规则包漂移门（21 条）
# ==========================================================================
def test_rules_json_is_shipped_asset():
    assert os.path.isfile(os.path.join(DATA_DIR, "rules.json"))


def test_rules_count_is_twentyone():
    assert len(REGISTRY.RULES) == len(rules_json()) == 21


def test_rule_ids_match_source_order():
    assert [rule["id"] for rule in REGISTRY.RULES] == [rule["id"] for rule in rules_json()]


def test_rule_names_match_source():
    assert [rule.get("name") for rule in REGISTRY.RULES] == [
        rule.get("name") for rule in rules_json()]


def test_rule_types_match_source():
    assert [rule.get("rule_type") for rule in REGISTRY.RULES] == [
        rule.get("rule_type") for rule in rules_json()]


def test_rule_severities_match_source():
    assert [rule.get("severity") for rule in REGISTRY.RULES] == [
        rule.get("severity") for rule in rules_json()]


def test_rule_basis_match_source():
    assert [rule.get("basis") for rule in REGISTRY.RULES] == [
        rule.get("basis") for rule in rules_json()]


def test_rule_advice_match_source():
    assert [rule.get("advice") for rule in REGISTRY.RULES] == [
        rule.get("advice") for rule in rules_json()]


def test_only_if_is_empty_in_every_rule():
    assert all(not rule.get("only_if") for rule in REGISTRY.RULES)


def test_only_if_absent_in_source():
    assert all(not rule.get("only_if") for rule in rules_json())


def test_only_ratio_param_is_registered():
    params = {rule["id"]: rule.get("params") for rule in REGISTRY.RULES
              if rule.get("params")}
    assert params == {"CHK-PC-01": {"ratio": 0.8}}


def test_rule_by_id_returns_rule():
    assert REGISTRY.rule_by_id("CHK-PC-01")["params"]["ratio"] == 0.8


def test_rule_by_id_raises_for_unknown():
    with pytest.raises(KeyError):
        REGISTRY.rule_by_id("CHK-NOPE-99")


def test_rule_ids_are_unique():
    rule_ids = [rule["id"] for rule in REGISTRY.RULES]
    assert len(rule_ids) == len(set(rule_ids))


def test_rule_types_are_declared_or_collusion():
    assert {rule["rule_type"] for rule in REGISTRY.RULES} == set(ENGINE.RULE_TYPES) | {"collusion"}


def test_cite_impl_reject_matches_registry_constant():
    assert REGISTRY.CITE_IMPL_REJECT == "《%s》第五十一条" % REGISTRY.LAW_IMPL_REG


def test_cite_87_invalid_matches_registry_constant():
    assert REGISTRY.CITE_87_INVALID == "《%s》第六十三条" % REGISTRY.LAW_87


def test_law_prefix_covers_three_laws():
    assert set(REGISTRY.LAW_PREFIX.values()) == {"87-order", "impl-reg", "tender-law"}


def test_every_engine_citation_is_verified_block():
    """引擎引用的 6 个条号必须都在**已核对**条文块里（来源仓口径）。"""
    catalog = basis()
    for cite in (REGISTRY.CITE_IMPL_REJECT, REGISTRY.CITE_87_VALIDITY, REGISTRY.CITE_87_OPEN,
                 REGISTRY.CITE_87_PRICE_FIX, REGISTRY.CITE_87_LOW_PRICE,
                 REGISTRY.CITE_87_INVALID):
        assert cite in [
            "《%s》%s" % (block["law"], block["article_no"]) for block in blocks_json()
            if block["status"] == "已核对"], cite


def test_citation_prefixes_are_registered():
    catalog = basis()
    for cite in (REGISTRY.CITE_87_OPEN, REGISTRY.CITE_87_INVALID):
        article = cite.split("》")[1]
        assert catalog.clause("87-order:%s" % article) is not None


# ==========================================================================
# 三、条文库（已核对条文块）
# ==========================================================================
def test_clauses_version_matches_knowledge_coordinate():
    assert basis().version == REGISTRY.VERSION == "2026-10-05"


def test_clauses_have_sixteen_entries():
    assert len(basis()) == 16


def test_clauses_cover_every_spec():
    assert set(basis().clause_ids()) == {cid for cid, _path in REGISTRY.clause_specs()}


def test_all_verified_blocks_are_in_basis():
    catalog = basis()
    for block in blocks_json():
        if block["status"] != "已核对":
            continue
        prefix = REGISTRY.LAW_PREFIX[block["law"]]
        assert catalog.clause("%s:%s" % (prefix, block["article_no"])) is not None


def test_pending_blocks_are_not_in_basis():
    """待核对条文（招标投标法第三十三/三十四条）不进依据路径——引擎也不引用它们。"""
    catalog = basis()
    pending = [block for block in blocks_json() if block["status"] != "已核对"]
    assert len(pending) == 2
    for block in pending:
        prefix = REGISTRY.LAW_PREFIX[block["law"]]
        assert catalog.clause("%s:%s" % (prefix, block["article_no"])) is None


def test_clause_texts_match_blocks():
    catalog = basis()
    for block in blocks_json():
        if block["status"] != "已核对":
            continue
        clause_id = "%s:%s" % (REGISTRY.LAW_PREFIX[block["law"]], block["article_no"])
        assert catalog.clause(clause_id).text == block["text"], clause_id


def test_clause_paths_name_instruments():
    assert basis().clause("87-order:第三十九条").path.startswith(
        "《政府采购货物和服务招标投标管理办法》")


def test_tender_clause_contract_is_registered():
    assert basis().clause(REGISTRY.CLAUSE_TENDER_CLAUSE) is not None


def test_rule_pack_contract_is_registered():
    assert basis().clause(REGISTRY.CLAUSE_RULE_PACK) is not None


# ==========================================================================
# 四、IR 序列化
# ==========================================================================
def test_tender_card_round_trips():
    card = tender(qualifications=[{"item_id": "Q1", "requirement": "营业执照",
                                   "category": "qualification"}])
    again = SCHEMA.TenderCard.from_dict(card.to_dict())
    assert again.to_dict() == card.to_dict()


def test_bid_card_round_trips():
    card = bid(qualifications=[{"item_id": "Q1", "level": "AAA"}])
    assert SCHEMA.BidCard.from_dict(card.to_dict()).to_dict() == card.to_dict()


def test_from_dict_ignores_unknown_keys():
    card = SCHEMA.TenderCard.from_dict({"project": {"name": "示例"}, "unknown": 1})
    assert card.project.name == "示例"


def test_from_dict_uses_defaults_for_missing_keys():
    card = SCHEMA.BidCard.from_dict({})
    assert card.qualifications == []
    assert card.bidder is None


def test_from_dict_normalises_int_to_float():
    prices = SCHEMA.Prices.from_dict({"total_number": 100})
    assert isinstance(prices.total_number, float)


def test_from_dict_normalises_int_validity_days():
    dates = SCHEMA.KeyDates.from_dict({"validity_days": 90})
    assert dates.validity_days == 90


def test_evidence_round_trips_quote():
    card = tender(qualifications=[{"item_id": "Q1", "evidence": {
        "section": "第二章", "quote": "营业执照副本", "line": 12}}])
    assert card.qualifications[0].evidence.quote == "营业执照副本"


def test_status_constants_are_three():
    assert SCHEMA.STATUS_ALL == ("符合", "不符合", "待人工确认")


def test_from_dict_rejects_non_mapping_for_dataclass():
    with pytest.raises(TypeError):
        SCHEMA.TenderCard.from_dict([])


# ==========================================================================
# 五、金额换算
# ==========================================================================
def test_render_amount_formats_thousands():
    assert AMOUNTS.render_amount(2800000) == "￥2,800,000.00"


def test_render_amount_two_decimals():
    assert AMOUNTS.render_amount(1.5) == "￥1.50"


def test_render_amount_rejects_negative():
    with pytest.raises(ValueError):
        AMOUNTS.render_amount(-1)


def test_amount_to_words_zero():
    assert AMOUNTS.amount_to_words(0) == "零元整"


def test_amount_to_words_simple():
    assert AMOUNTS.amount_to_words(1) == "壹元整"


def test_amount_to_words_hundred():
    assert AMOUNTS.amount_to_words(100) == "壹佰元整"


def test_amount_to_words_ten_uses_shang():
    assert AMOUNTS.amount_to_words(10) == "壹拾元整"


def test_amount_to_words_wan_group():
    assert AMOUNTS.amount_to_words(10000) == "壹万元整"


def test_amount_to_words_yi_group():
    assert AMOUNTS.amount_to_words(100000000) == "壹亿元整"


def test_amount_to_words_jiao_only():
    assert AMOUNTS.amount_to_words(0.5) == "伍角整"


def test_amount_to_words_fen_only():
    assert AMOUNTS.amount_to_words(0.05) == "零伍分"


def test_amount_to_words_jiao_and_fen():
    assert AMOUNTS.amount_to_words(1.23) == "壹元贰角叁分"


def test_amount_to_words_rejects_negative():
    with pytest.raises(ValueError):
        AMOUNTS.amount_to_words(-1)


def test_amount_to_words_rejects_out_of_range():
    with pytest.raises(ValueError):
        AMOUNTS.amount_to_words(10 ** 12)


def test_words_to_amount_round_trip_integer():
    assert AMOUNTS.words_to_amount(AMOUNTS.amount_to_words(3283600)) == 3283600.0


def test_words_to_amount_round_trip_decimal():
    assert AMOUNTS.words_to_amount(AMOUNTS.amount_to_words(1234.56)) == 1234.56


def test_words_to_amount_reads_jiao_fen():
    assert AMOUNTS.words_to_amount("壹元贰角叁分") == 1.23


def test_words_to_amount_rejects_unknown_char():
    with pytest.raises(ValueError):
        AMOUNTS.words_to_amount("壹元X整")


def test_words_to_amount_handles_missing_yuan():
    assert AMOUNTS.words_to_amount("壹佰") == 100.0


def test_words_to_amount_rejects_residual_after_yuan():
    with pytest.raises(ValueError):
        AMOUNTS.words_to_amount("壹元贰")


def test_words_to_amount_parses_sample_word_string():
    assert AMOUNTS.words_to_amount("叁佰贰拾捌万叁仟陆佰元整") == 3283600.0


def test_amount_round_trip_for_sample():
    for value in (0.01, 0.1, 9.99, 105, 1000000, 99999999):
        assert abs(AMOUNTS.words_to_amount(AMOUNTS.amount_to_words(value)) - value) < 0.005


# ==========================================================================
# 六、类目门控
# ==========================================================================
def test_rule_without_only_if_always_applies():
    assert GATES.rule_applies({"id": "X"}, "") is True


def test_rule_with_empty_keywords_always_applies():
    assert GATES.rule_applies({"only_if": {"keywords": []}}, "任意文本") is True


def test_rule_activates_when_all_keywords_present():
    rule = {"only_if": {"keywords": ["货物", "采购"]}}
    assert GATES.rule_applies(rule, "货物采购项目") is True


def test_rule_inactive_when_keyword_missing():
    rule = {"only_if": {"keywords": ["货物", "服务"]}}
    assert GATES.rule_applies(rule, "货物采购项目") is False


def test_rule_accepts_object_with_only_if_attribute():
    class Rule(object):
        only_if = {"keywords": ["货物"]}

    assert GATES.rule_applies(Rule(), "货物") is True


def test_rule_accepts_only_if_as_list():
    assert GATES.rule_applies({"only_if": ["货物"]}, "货物采购") is True


# ==========================================================================
# 七、资格比对
# ==========================================================================
def _qual(item_id, category="qualification", **extra):
    payload = {"item_id": item_id, "requirement": extra.pop("requirement", "要求"),
               "category": category}
    payload.update(extra)
    return payload


def test_missing_qualification_evidence_is_nonconform():
    found = ENGINE.run_checks(tender(qualifications=[_qual("Q1")]), bid())
    assert [item.check_id for item in found] == ["CHK-Q-01"]


def test_missing_qualification_cites_tender_clause_and_law():
    found = ENGINE.run_checks(tender(qualifications=[_qual("Q1")]), bid())
    assert "Q1" in found[0].basis
    assert REGISTRY.CITE_87_INVALID in found[0].basis


def test_present_qualification_produces_no_finding():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q1")]),
        bid(qualifications=[{"item_id": "Q1", "valid_until": "2030-01-01"}]))
    assert found == []


def test_expired_certificate_is_nonconform():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q1")],
               key_dates={"submit_deadline": "2026-10-19T09:30"}),
        bid(qualifications=[{"item_id": "Q1", "valid_until": "2026-10-09"}]))
    assert [item.check_id for item in found] == ["CHK-Q-02"]


def test_certificate_valid_after_deadline_passes():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q1")],
               key_dates={"submit_deadline": "2026-10-19T09:30"}),
        bid(qualifications=[{"item_id": "Q1", "valid_until": "2027-10-09"}]))
    assert found == []


def test_required_valid_until_is_used_when_later():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q1", valid_until="2027-01-01")]),
        bid(qualifications=[{"item_id": "Q1", "valid_until": "2026-12-01"}]))
    assert [item.check_id for item in found] == ["CHK-Q-02"]


def test_level_below_requirement_is_nonconform():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q4", level="AAA")]),
        bid(qualifications=[{"item_id": "Q4", "level": "AA"}]))
    assert [item.check_id for item in found] == ["CHK-Q-03"]


def test_level_equal_requirement_passes():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q4", level="AAA")]),
        bid(qualifications=[{"item_id": "Q4", "level": "AAA"}]))
    assert found == []


def test_level_above_requirement_passes():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q4", level="A")]),
        bid(qualifications=[{"item_id": "Q4", "level": "AAA"}]))
    assert found == []


def test_level_unranked_falls_back_to_equality():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q4", level="特级")]),
        bid(qualifications=[{"item_id": "Q4", "level": "甲级"}]))
    assert [item.check_id for item in found] == ["CHK-Q-03"]


def test_missing_level_in_bid_is_nonconform():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q4", level="AAA")]),
        bid(qualifications=[{"item_id": "Q4"}]))
    assert [item.check_id for item in found] == ["CHK-Q-03"]


def test_finance_category_is_checked_like_qualification():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q2", category="finance")]), bid())
    assert [item.check_id for item in found] == ["CHK-Q-01"]


def test_performance_missing_is_nonconform():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q5", category="performance")]), bid())
    assert [item.check_id for item in found] == ["CHK-Q-04"]


def test_performance_since_year_filters_old():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q5", category="performance",
                                     requirement="提供2023年以来至少1个类似项目业绩")]),
        bid(performance=[{"name": "旧合同", "date": "2020-01-01"}]))
    assert [item.check_id for item in found] == ["CHK-Q-04"]


def test_performance_recent_counts():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q5", category="performance",
                                     requirement="提供2023年以来至少1个类似项目业绩")]),
        bid(performance=[{"name": "新合同", "date": "2024-05-01"}]))
    assert found == []


def test_performance_at_least_two_needs_two():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q5", category="performance",
                                     requirement="提供2023年以来至少2个类似项目业绩")]),
        bid(performance=[{"name": "新合同", "date": "2024-05-01"}]))
    assert [item.check_id for item in found] == ["CHK-Q-04"]


def test_personnel_missing_is_nonconform():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q6", category="personnel")]), bid())
    assert [item.check_id for item in found] == ["CHK-Q-05"]


def test_personnel_certificate_token_required():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q6", category="personnel",
                                     requirement="具备PMP证书")]),
        bid(personnel=[{"name": "张三", "cert_name": "信息系统项目管理师"}]))
    assert [item.check_id for item in found] == ["CHK-Q-05"]


def test_personnel_certificate_present():
    found = ENGINE.run_checks(
        tender(qualifications=[_qual("Q6", category="personnel",
                                     requirement="具备PMP证书")]),
        bid(personnel=[{"name": "张三", "cert_name": "PMP"}]))
    assert found == []


# ==========================================================================
# 八、星号条款
# ==========================================================================
def _star(item_id="S1", marker="★", text="质保期不少于36个月"):
    return {"item_id": item_id, "marker": marker, "text": text}


def test_missing_star_response_is_nonconform():
    found = ENGINE.run_checks(tender(star_clauses=[_star()]), bid())
    assert [item.check_id for item in found] == ["CHK-SR-01"]


def test_missing_triangle_response_is_nonconform_mid():
    found = ENGINE.run_checks(tender(star_clauses=[_star(marker="▲")]), bid())
    assert found[0].check_id == "CHK-SR-01"
    assert found[0].risk_level == "mid"


def test_star_response_below_floor_is_nonconform():
    found = ENGINE.run_checks(
        tender(star_clauses=[_star()]),
        bid(star_responses=[{"star_id": "S1", "quote": "质保期24个月"}]))
    assert [item.check_id for item in found] == ["CHK-SR-02"]


def test_star_response_meeting_floor_passes():
    found = ENGINE.run_checks(
        tender(star_clauses=[_star()]),
        bid(star_responses=[{"star_id": "S1", "quote": "质保期36个月"}]))
    assert found == []


def test_star_ceiling_violation_is_nonconform():
    found = ENGINE.run_checks(
        tender(star_clauses=[_star(text="交付期不超过30日")]),
        bid(star_responses=[{"star_id": "S1", "quote": "交付期45日"}]))
    assert [item.check_id for item in found] == ["CHK-SR-02"]


def test_star_ceiling_satisfied_passes():
    found = ENGINE.run_checks(
        tender(star_clauses=[_star(text="交付期不超过30日")]),
        bid(star_responses=[{"star_id": "S1", "quote": "交付期20日"}]))
    assert found == []


def test_star_value_without_unit_is_skipped():
    found = ENGINE.run_checks(
        tender(star_clauses=[_star(text="质保不少于三年")]),
        bid(star_responses=[{"star_id": "S1", "quote": "质保两年"}]))
    assert found == []


def test_star_value_with_two_numbers_is_skipped():
    found = ENGINE.run_checks(
        tender(star_clauses=[_star(text="不少于36个月且不超过60个月")]),
        bid(star_responses=[{"star_id": "S1", "quote": "24个月"}]))
    assert found == []


def test_star_unit_mismatch_is_skipped():
    found = ENGINE.run_checks(
        tender(star_clauses=[_star(text="质保不少于36个月")]),
        bid(star_responses=[{"star_id": "S1", "quote": "质保36日"}]))
    assert found == []


def test_triangle_declared_deviation_is_manual():
    found = ENGINE.run_checks(
        tender(star_clauses=[_star(marker="▲")]),
        bid(star_responses=[{"star_id": "S1", "quote": "质保24个月",
                             "deviation": "负偏离"}]))
    assert [item.check_id for item in found] == ["CHK-SR-03"]
    assert found[0].status == SCHEMA.STATUS_MANUAL


def test_triangle_undeclared_deviation_is_nonconform():
    found = ENGINE.run_checks(
        tender(star_clauses=[_star(marker="▲")]),
        bid(star_responses=[{"star_id": "S1", "quote": "质保24个月",
                             "deviation": "无偏离"}]))
    assert [item.check_id for item in found] == ["CHK-SR-02"]


def test_star_deviation_sets_rejection_flag():
    engine = ENGINE._Checker(tender(star_clauses=[_star()]), bid(), "", None)
    engine.check_star_responses()
    assert engine.flags.get("star_rejection") is not None


def test_unrelated_star_response_ignored():
    found = ENGINE.run_checks(
        tender(star_clauses=[_star("S1")]),
        bid(star_responses=[{"star_id": "S9", "quote": "质保36个月"}]))
    assert [item.check_id for item in found] == ["CHK-SR-01"]


# ==========================================================================
# 九、算术复核
# ==========================================================================
def test_words_number_mismatch_is_nonconform():
    found = ENGINE.run_checks(tender(), bid(prices={"total_words": "壹佰元整",
                                                     "total_number": 200}))
    assert [item.check_id for item in found] == ["CHK-AR-01"]


def test_words_number_match_passes():
    found = ENGINE.run_checks(tender(), bid(prices={"total_words": "壹佰元整",
                                                     "total_number": 100}))
    assert found == []


def test_items_sum_mismatch_is_nonconform():
    found = ENGINE.run_checks(tender(), bid(prices={"items_sum": 100, "total_number": 200}))
    assert [item.check_id for item in found] == ["CHK-AR-02"]


def test_items_total_mismatch_is_nonconform():
    found = ENGINE.run_checks(tender(), bid(prices={
        "items": [{"name": "a", "amount": 10}, {"name": "b", "amount": 20}],
        "items_sum": 40, "total_number": 40}))
    assert [item.check_id for item in found] == ["CHK-AR-03"]


def test_items_total_match_passes():
    found = ENGINE.run_checks(tender(), bid(prices={
        "items": [{"name": "a", "amount": 10}, {"name": "b", "amount": 30}],
        "items_sum": 40, "total_number": 40}))
    assert found == []


def test_arithmetic_tolerance_is_half_cent():
    found = ENGINE.run_checks(tender(), bid(prices={"items_sum": 100.001,
                                                     "total_number": 100}))
    assert found == []


def test_invalid_words_are_skipped():
    found = ENGINE.run_checks(tender(), bid(prices={"total_words": "壹元X整",
                                                     "total_number": 1}))
    assert found == []


def test_no_prices_produces_no_finding():
    assert ENGINE.run_checks(tender(), bid()) == []


# ==========================================================================
# 十、保证金与时间逻辑
# ==========================================================================
def test_bond_amount_below_required_is_nonconform():
    found = ENGINE.run_checks(tender(bond={"amount": 50000}),
                              bid(bond_response={"amount": 40000}))
    assert [item.check_id for item in found] == ["CHK-BD-01"]


def test_bond_amount_equal_passes():
    assert ENGINE.run_checks(tender(bond={"amount": 50000}),
                             bid(bond_response={"amount": 50000})) == []


def test_bond_form_not_allowed_is_nonconform():
    found = ENGINE.run_checks(
        tender(bond={"amount": 1, "forms": ["转账"]}),
        bid(bond_response={"amount": 1, "forms": ["现金"]}))
    assert [item.check_id for item in found] == ["CHK-BD-02"]


def test_bond_form_allowed_passes():
    assert ENGINE.run_checks(
        tender(bond={"amount": 1, "forms": ["转账"]}),
        bid(bond_response={"amount": 1, "forms": ["转账"]})) == []


def test_bond_missing_response_is_skipped():
    assert ENGINE.run_checks(tender(bond={"amount": 1}), bid()) == []


def test_bond_failure_sets_flag():
    engine = ENGINE._Checker(tender(bond={"amount": 50000}), bid(bond_response={"amount": 1}),
                             "", None)
    engine.check_bond()
    assert engine.flags.get("bond") is True


def test_validity_short_with_clause_is_nonconform():
    found = ENGINE.run_checks(
        tender(key_dates={"validity_days": 90},
               rejection_clauses=[{"item_id": "R3", "text": "投标有效期不足的，投标无效"}]),
        bid(key_dates={"validity_days": 60}))
    assert {item.check_id for item in found} == {"CHK-DT-01", "CHK-RJ-03"}


def test_validity_short_without_clause_is_skipped():
    assert ENGINE.run_checks(tender(key_dates={"validity_days": 90}),
                             bid(key_dates={"validity_days": 60})) == []


def test_validity_sufficient_passes():
    assert ENGINE.run_checks(tender(key_dates={"validity_days": 90}),
                             bid(key_dates={"validity_days": 90})) == []


def test_tender_open_before_deadline_is_nonconform():
    found = ENGINE.run_tender_checks(tender(key_dates={
        "open_time": "2026-10-19T09:00", "submit_deadline": "2026-10-19T09:30"}))
    assert [item.check_id for item in found] == ["CHK-DT-02"]


def test_tender_open_at_deadline_passes():
    assert ENGINE.run_tender_checks(tender(key_dates={
        "open_time": "2026-10-19T09:30", "submit_deadline": "2026-10-19T09:30"})) == []


# ==========================================================================
# 十一、否决联动与低价提示
# ==========================================================================
def _rejections():
    return [
        {"item_id": "R1", "text": "投标报价超过最高限价（人民币2,800,000.00元）的，投标无效"},
        {"item_id": "R2", "text": "未按要求提交投标保证金的，投标无效"},
        {"item_id": "R3", "text": "投标有效期不足的，投标无效"},
        {"item_id": "R4", "text": "★号条款不满足或者未响应的，其投标无效。"},
    ]


def test_over_cap_is_nonconform():
    found = ENGINE.run_checks(tender(rejection_clauses=_rejections()),
                              bid(prices={"total_number": 3000000}))
    assert "CHK-RJ-01" in [item.check_id for item in found]


def test_under_cap_no_rejection():
    found = ENGINE.run_checks(tender(rejection_clauses=_rejections()),
                              bid(prices={"total_number": 2800000}))
    assert "CHK-RJ-01" not in [item.check_id for item in found]


def test_price_cap_is_parsed_from_clause():
    engine = ENGINE._Checker(tender(rejection_clauses=_rejections()), bid(), "", None)
    assert engine._price_cap() == 2800000.0


def test_price_cap_absent_without_clause():
    engine = ENGINE._Checker(tender(), bid(), "", None)
    assert engine._price_cap() is None


def test_implied_bond_rejection_fires():
    found = ENGINE.run_checks(tender(bond={"amount": 50000}, rejection_clauses=_rejections()),
                              bid(bond_response={"amount": 1}))
    assert "CHK-RJ-02" in [item.check_id for item in found]


def test_implied_validity_rejection_fires():
    found = ENGINE.run_checks(
        tender(key_dates={"validity_days": 90}, rejection_clauses=_rejections()),
        bid(key_dates={"validity_days": 10}))
    assert "CHK-RJ-03" in [item.check_id for item in found]


def test_implied_star_rejection_fires():
    found = ENGINE.run_checks(tender(star_clauses=[_star()], rejection_clauses=_rejections()),
                              bid())
    assert "CHK-RJ-04" in [item.check_id for item in found]


def test_low_price_hint_is_manual():
    found = ENGINE.run_checks(tender(rejection_clauses=_rejections()),
                              bid(prices={"total_number": 1000000}))
    manual = [item for item in found if item.check_id == "CHK-PC-01"]
    assert manual and manual[0].status == SCHEMA.STATUS_MANUAL


def test_low_price_hint_uses_rule_param():
    rules = [dict(rule) for rule in REGISTRY.RULES]
    for rule in rules:
        if rule["id"] == "CHK-PC-01":
            rule["params"] = {"ratio": 0.5}
    found = ENGINE.run_checks(tender(rejection_clauses=_rejections()),
                              bid(prices={"total_number": 1500000}), rules=rules)
    assert [item.check_id for item in found if item.check_id == "CHK-PC-01"] == []


def test_low_price_hint_absent_without_cap():
    found = ENGINE.run_checks(tender(), bid(prices={"total_number": 1}))
    assert [item.check_id for item in found if item.check_id == "CHK-PC-01"] == []


def test_rejection_scan_cites_impl_regulation():
    found = ENGINE.run_checks(tender(rejection_clauses=_rejections()),
                              bid(prices={"total_number": 3000000}))
    row = [item for item in found if item.check_id == "CHK-RJ-01"][0]
    assert REGISTRY.CITE_IMPL_REJECT in row.basis


# ==========================================================================
# 十二、账本映射与退出码
# ==========================================================================
def test_goods1_offers_four_records():
    assert len(findings(sample(GOODS1))) == 4


def test_goods1_three_blocking_findings():
    found = findings(sample(GOODS1))
    blocking = [item for item in found if item.verdict == FAIL and item.rule_id != "review.result"]
    assert sorted(item.rule_id for item in blocking) == ["CHK-DT-02#1", "CHK-RJ-04#1", "CHK-SR-01#1"]


def test_goods1_summary_is_fail():
    assert one(findings(sample(GOODS1)), "review.result").verdict == FAIL


def test_goods1_exit_code_is_blocked():
    assert report(sample(GOODS1)).exit_code() == EXIT_BLOCKED


def test_goods1_fail_anchors_resolve_to_basis():
    for item in findings(sample(GOODS1)):
        if item.verdict == FAIL:
            assert item.anchor is not None, item.rule_id
            assert item.anchor.clause_id in basis().clause_ids()


def test_goods1_star_missing_anchors_to_tender_clause_contract():
    finding = one(findings(sample(GOODS1)), "CHK-SR-01#1")
    assert finding.anchor.clause_id == REGISTRY.CLAUSE_TENDER_CLAUSE


def test_goods1_date_finding_anchors_to_87_order():
    finding = one(findings(sample(GOODS1)), "CHK-DT-02#1")
    assert finding.anchor.clause_id == "87-order:第三十九条"


def test_goods1_rejection_anchors_to_impl_regulation():
    finding = one(findings(sample(GOODS1)), "CHK-RJ-04#1")
    assert finding.anchor.clause_id == "impl-reg:第五十一条"


def test_goods2_is_clean():
    found = findings(sample(GOODS2))
    assert len(found) == 1
    assert found[0].verdict == PASS


def test_goods2_exit_code_is_ok():
    assert report(sample(GOODS2)).exit_code() == EXIT_OK


def test_goods2_summary_evidence_counts():
    evidence = one(findings(sample(GOODS2)), "review.result").evidence
    assert evidence["findings"] == 0
    assert evidence["blocking"] == 0


def test_manual_finding_maps_to_not_applicable():
    payload = subject(tender(rejection_clauses=_rejections()),
                      bid(prices={"total_number": 1000000}))
    finding = one(findings(payload), "CHK-PC-01#1")
    assert finding.verdict == NOT_APPLICABLE


def test_manual_finding_does_not_block():
    payload = subject(tender(rejection_clauses=_rejections()),
                      bid(prices={"total_number": 1000000}))
    assert report(payload).blocking() == ()


def _partial_basis():
    """只有规则包契约、没有法条与招标条款契约的条文库（模拟依据不可解析）。"""
    return Basis(REGISTRY.VERSION, [Clause(
        clause_id=REGISTRY.CLAUSE_RULE_PACK, path="数据契约 / 规则包注册",
        version=REGISTRY.VERSION, text="规则包")])


def test_unresolvable_basis_degrades_to_not_applicable():
    """依据不可解析 → 降级为待人工确认（无锚点），绝不带锚点造假。"""
    payload = subject(tender(qualifications=[_qual("Q1")]), bid())
    found = tuple(PACK_MOD.evaluate_with_rules(payload, _partial_basis(), None))
    finding = one(found, "CHK-Q-01#1")
    assert finding.verdict == NOT_APPLICABLE
    assert finding.anchor is None
    assert "依据不可解析" in finding.message


def test_unresolvable_basis_keeps_exit_ok():
    payload = subject(tender(qualifications=[_qual("Q1")]), bid())
    report_ = Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.ORG_VERSION,
                     subject="cards.json",
                     findings=PACK_MOD.evaluate_with_rules(payload, _partial_basis(), None))
    assert report_.exit_code() == EXIT_OK


def test_multiple_findings_same_check_get_distinct_ids():
    tender_card = tender(qualifications=[_qual("Q1"), _qual("Q2")])
    found = findings(subject(tender_card, bid()))
    check_ids = [item.rule_id for item in found if item.rule_id.startswith("CHK-Q-01")]
    assert check_ids == ["CHK-Q-01#1", "CHK-Q-01#2"]


def test_every_finding_has_unique_id():
    ids_ = [item.id for item in report(sample(GOODS1)).findings]
    assert len(ids_) == len(set(ids_))


def test_evidence_carries_check_id_and_risk():
    evidence = one(findings(sample(GOODS1)), "CHK-RJ-04#1").evidence
    assert evidence["check_id"] == "CHK-RJ-04"
    assert evidence["risk_level"] == "high"


def test_evidence_carries_basis_list():
    evidence = one(findings(sample(GOODS1)), "CHK-DT-02#1").evidence
    assert REGISTRY.CITE_87_OPEN in evidence["basis"]


def test_missing_tender_is_input_error():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"bid": {}}, basis())


def test_missing_bid_is_input_error():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"tender": {}}, basis())


def test_non_string_doc_text_is_input_error():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"tender": {}, "bid": {}, "doc_text": 1}, basis())


def test_basis_version_mismatch_is_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(sample(GOODS2), Basis.empty("2020-01-01"))


def test_cli_goods1_returns_blocked(capsys):
    code = cp_cli.main(["check", SLUG, "--input", GOODS1, "--basis", BASIS_PATH])
    assert code == EXIT_BLOCKED
    assert "阻断 4 条" in capsys.readouterr().out


def test_cli_goods2_returns_ok(capsys):
    code = cp_cli.main(["check", SLUG, "--input", GOODS2, "--basis", BASIS_PATH])
    assert code == EXIT_OK
    assert "阻断 0 条" in capsys.readouterr().out


def test_cli_missing_basis_returns_contract_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input", GOODS2])
    assert code == EXIT_CONTRACT
    assert "ContractError" in capsys.readouterr().err


def test_cli_missing_file_returns_input_code():
    assert cp_cli.main(["check", SLUG, "--input", "no-such.json",
                        "--basis", BASIS_PATH]) == EXIT_INPUT


def test_cli_json_output_has_organ(capsys):
    cp_cli.main(["check", SLUG, "--input", GOODS1, "--basis", BASIS_PATH, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG
    assert payload["summary"]["blocking"] == 4


# ==========================================================================
# 十三、确定性与纯函数性
# ==========================================================================
def test_evaluate_does_not_mutate_subject():
    payload = sample(GOODS1)
    before = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    findings(payload)
    assert json.dumps(payload, ensure_ascii=False, sort_keys=True) == before


def test_rule_pack_is_not_mutated():
    before = copy.deepcopy(REGISTRY.RULES)
    findings(sample(GOODS1))
    assert REGISTRY.RULES == before


def test_two_runs_are_identical():
    first = json.dumps([item.as_dict() for item in findings(sample(GOODS1))],
                       ensure_ascii=False, sort_keys=True)
    second = json.dumps([item.as_dict() for item in findings(sample(GOODS1))],
                        ensure_ascii=False, sort_keys=True)
    assert first == second


def test_report_json_is_deterministic():
    first = json.dumps(report(sample(GOODS1)).as_dict(), ensure_ascii=False, sort_keys=True)
    second = json.dumps(report(sample(GOODS1)).as_dict(), ensure_ascii=False, sort_keys=True)
    assert first == second


def test_finding_order_puts_summary_last():
    found = findings(sample(GOODS1))
    assert found[-1].rule_id == "review.result"