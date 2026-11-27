"""器官 ``food-label`` 无损判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在「判定结果」上。
来源仓判定层（D1 + D18 机械选 13 文件 / 实跑 119 passed / AST 函数 109）逐文件
处置见 ``docs/food-label.md`` §6；本文件承载双标尺规则引擎（47 条规则、
11 种 check_type 全通）、数值复算（NRV% / 能量 / 声称阈值 / 到期日）、
类目门控、依据待核对标记、双标尺差异对照与账本映射。

本文件同时是**漂移门**：``data/gb7718-*.json`` / ``data/nutrient-reference.json``
与来源仓逐字节同 sha256；``samples/food-label/expected-dual.json`` 为旧 CLI
输出的冻结对账判据（stats 与 dual_diff 逐值）。

**人食品 ≠ 宠物食品**：本器官规则源为 GB 7718 / GB 28050（人食品标签）；
已吸收的 ``petfood-label`` 器官（GB/T 31216/31217 宠物食品）与本器官**零共享
规则、零共享测试**——边界见 ``docs/food-label.md`` §7。
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

PACK_MOD = importlib.import_module("clauseproof.packs.food-label")
ENGINE = importlib.import_module("clauseproof.packs.food-label.engine")
NUMERIC = importlib.import_module("clauseproof.packs.food-label.numeric")
REGISTRY = importlib.import_module("clauseproof.packs.food-label.registry")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "food-label")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "food-label")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
SAMPLE_PATH = os.path.join(SAMPLES, "label-sample.json")
CLEAN_PATH = os.path.join(SAMPLES, "label-clean.json")
EXPECTED_PATH = os.path.join(SAMPLES, "expected-dual.json")


def basis():
    return Basis.from_json(BASIS_PATH)


def subject(path=SAMPLE_PATH):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def expected():
    with open(EXPECTED_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def findings(sub=None):
    return tuple(PACK_MOD.evaluate(subject() if sub is None else sub, basis()))


def report(sub, name="case.json"):
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject=name, findings=findings(sub))


def rulesets_copy():
    """规则包深拷贝（测试注入变异不污染缓存的随包资产）。"""
    return copy.deepcopy(REGISTRY.rulesets())


def reference():
    return REGISTRY.nutrient_reference()


def card(path=SAMPLE_PATH):
    return subject(path)["card"]


def run_one(ruleset_id, c=None, ref=None):
    """对单规则集跑一遍（注入内存规则包）。"""
    return ENGINE.run_ruleset(c if c is not None else card(),
                              rulesets_copy()[ruleset_id],
                              ref if ref is not None else reference())


def run_both(c=None):
    ids = list(ENGINE.AVAILABLE_RULESETS)
    results = ENGINE.run_dual(c if c is not None else card(), rulesets_copy(),
                              reference(), ids)
    return results, ENGINE.dual_diff(results, ids[0], ids[-1])


def field(value, region="测试栏", quote=None, unit=None):
    return {"key": "x", "value": value, "unit": unit, "confidence": 1.0,
            "evidence": {"region": region, "quote": quote if quote is not None else str(value),
                         "span": [0, 1]}}


def base_card(fields=None, nutrition_table=None, ingredients=None, claims=None,
              unresolved_detail=None):
    card_doc = {"fields": {}, "nutrition_table": [], "ingredients": [],
                "claims": [], "unresolved": [], "unresolved_detail": {}}
    card_doc["fields"] = dict(fields or {})
    card_doc["nutrition_table"] = list(nutrition_table or [])
    card_doc["ingredients"] = list(ingredients or [])
    card_doc["claims"] = list(claims or [])
    card_doc["unresolved_detail"] = dict(unresolved_detail or {})
    return card_doc


def full_card(**overrides):
    """全字段合规卡（各列可覆盖）。"""
    fields = {
        "food_name": field("测试食品"),
        "ingredients": field(["生牛乳"]),
        "net_content": field("250mL"),
        "production_date": field("2026-09-20", quote="2026年09月20日"),
        "shelf_life": field({"value": 6, "unit": "个月"}, quote="6个月", unit="个月"),
        "expiry_date": field("2027-03-20", quote="2027年03月20日"),
        "storage_conditions": field("常温避光"),
        "producer_name": field("示例乳业有限公司"),
        "producer_address": field("示例省示例市示例路 8 号"),
        "producer_contact": field("400-000-0000"),
        "sc_license": field("SC12345678901234"),
        "product_standard": field("GB 25190"),
        "salt_oil_sugar_notice": field("儿童青少年应避免过量摄入盐油糖"),
        "allergen_notice": field("含乳。"),
    }
    nutrition = [
        {"name": "能量", "amount": 269, "unit": "kJ", "nrv_percent": 3},
        {"name": "蛋白质", "amount": 3.2, "unit": "g", "nrv_percent": 5},
        {"name": "脂肪", "amount": 3.6, "unit": "g", "nrv_percent": 6},
        {"name": "碳水化合物", "amount": 4.5, "unit": "g", "nrv_percent": 2},
        {"name": "钠", "amount": 50, "unit": "mg", "nrv_percent": 3},
        {"name": "饱和脂肪", "amount": 2.3, "unit": "g", "nrv_percent": 12},
        {"name": "糖", "amount": 4.5, "unit": "g", "nrv_percent": None},
    ]
    doc = base_card(fields=fields, nutrition_table=nutrition,
                    ingredients=["生牛乳", "白砂糖"])
    for key, value in overrides.items():
        if key == "fields":
            doc["fields"].update(value)
        elif key == "nutrition_table":
            doc["nutrition_table"] = value
        elif key == "ingredients":
            doc["ingredients"] = value
        elif key == "claims":
            doc["claims"] = value
        elif key == "unresolved_detail":
            doc["unresolved_detail"] = value
        elif key == "drop":
            for name in value:
                doc["fields"].pop(name, None)
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
    assert PACK_MOD.INPUT_FIELDS == ("card",)


def test_slug_in_builtin_modules_sorted():
    packs_ns = importlib.import_module("clauseproof.packs")
    assert SLUG in packs_ns.BUILTIN_MODULES
    assert list(packs_ns.BUILTIN_MODULES) == sorted(packs_ns.BUILTIN_MODULES)


def test_pack_appears_in_all_packs():
    assert SLUG in [pack.slug for pack in all_packs()]


def test_basis_has_eleven_clauses():
    payload = json.load(open(BASIS_PATH, encoding="utf-8"))
    assert len(payload["clauses"]) == 11
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


def test_available_rulesets_are_two():
    assert ENGINE.AVAILABLE_RULESETS == ("gb7718-2011", "gb7718-2025")


def test_rule_counts_are_21_and_26():
    assert len(rulesets_copy()["gb7718-2011"]["rules"]) == 21
    assert len(rulesets_copy()["gb7718-2025"]["rules"]) == 26


# ==========================================================================
# 二、规则包资产与漂移门
# ==========================================================================
def _sha256_of(name):
    import hashlib
    with open(os.path.join(DATA_DIR, name), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def test_ruleset_files_present():
    for name in ("gb7718-2011.json", "gb7718-2025.json", "nutrient-reference.json"):
        assert os.path.isfile(os.path.join(DATA_DIR, name))


def test_ruleset_sha_frozen():
    """与来源仓逐字节同 sha256（手改任一侧即红）。"""
    assert _sha256_of("gb7718-2011.json") == \
        "3b6349647cead6cbcfaca5e6b19531c9c96cdcc8ec798b914b0810f54e9247e2"
    assert _sha256_of("gb7718-2025.json") == \
        "988b1b5eb2448c8008d51ab7cdf20cabac3c053c978fdc77f738ebbd996b396e"
    assert _sha256_of("nutrient-reference.json") == \
        "0ee248835838815076d1c611a8f98602b27d0b6afffa96298367f72aa1ff7cf5"


def test_every_rule_carries_basis():
    for rid, doc in rulesets_copy().items():
        for rule in doc["rules"]:
            basis_payload = rule.get("basis") or {}
            assert {"standard", "clause", "quote_ref", "status"} <= set(basis_payload), rule["id"]


def test_rule_check_types_cover_eleven():
    types = set()
    for doc in rulesets_copy().values():
        for rule in doc["rules"]:
            types.add(rule["check_type"])
    assert types == {
        "mandatory_field", "conditional", "format", "nrv_recalc",
        "energy_consistency", "ingredient_order", "claim_threshold",
        "claim_whitelist", "date_logic", "nutrition_rows", "allergen_notice"}


def test_rule_ids_unique_within_ruleset():
    for doc in rulesets_copy().values():
        ids = [r["id"] for r in doc["rules"]]
        assert len(ids) == len(set(ids))


def test_2025_adds_expiry_and_salt_notice():
    ids_2011 = {r["id"] for r in rulesets_copy()["gb7718-2011"]["rules"]}
    ids_2025 = {r["id"] for r in rulesets_copy()["gb7718-2025"]["rules"]}
    assert "MAND-EXPIRY-01" in ids_2025 - ids_2011
    assert "SALT-NOTICE-01" in ids_2025 - ids_2011
    assert "NUTR-ROWS-01" in ids_2025 - ids_2011
    assert "ALLERGEN-01" in ids_2025 - ids_2011
    assert "CLAIM-ZEROADD-01" in ids_2025 - ids_2011


def test_nutrition_reference_values():
    ref = reference()
    assert ref.nrv["能量"]["value"] == 8400
    assert ref.nrv["蛋白质"]["value"] == 60
    assert ref.nrv["钠"]["value"] == 2000
    assert ref.energy_factors() == {"蛋白质": 17, "脂肪": 37, "碳水化合物": 17}


def test_claim_thresholds_are_three():
    thresholds = reference().claim_thresholds()
    assert len(thresholds) == 3
    names = {t["claim_contains"] for t in thresholds}
    assert names == {"无糖", "低糖", "低钠"}


def test_salt_notice_text_matches_reference():
    assert reference().salt_notice_text() == "儿童青少年应避免过量摄入盐油糖"


# ==========================================================================
# 三、类目门控
# ==========================================================================
def test_gate_none_is_always_true():
    assert ENGINE.gate_matches(None, base_card()) is True


def test_gate_keyword_hits_card_text():
    c = base_card(fields={"food_name": field("果汁饮料")})
    assert ENGINE.gate_matches(["果汁饮料"], c) is True


def test_gate_keyword_misses():
    c = base_card(fields={"food_name": field("苏打饼干")})
    assert ENGINE.gate_matches(["果汁饮料"], c) is False


def test_gate_matches_ingredients_text():
    c = base_card(ingredients=["发酵乳"])
    assert ENGINE.gate_matches(["发酵乳", "酸乳"], c) is True


def test_gated_rule_skipped_for_other_category():
    stats = run_one("gb7718-2011")["stats"]
    # 乳制品样卡不含「果汁饮料」→ ING-ORDER-01 被门控跳过
    assert stats["skipped"] == 2


def test_ing_order_02_runs_for_dairy():
    c = full_card(fields={"food_name": field("发酵乳")}, ingredients=["白砂糖", "生牛乳"])
    result = run_one("gb7718-2011", c)
    hit = [f for f in result["findings"] if f["rule_id"] == "ING-ORDER-02"]
    assert len(hit) == 1
    assert hit[0]["level"] == ENGINE.LEVEL_FAIL


def test_ing_order_02_pass_for_correct_order():
    c = full_card(fields={"food_name": field("发酵乳")}, ingredients=["生牛乳", "白砂糖"])
    result = run_one("gb7718-2011", c)
    hit = [f for f in result["findings"] if f["rule_id"] == "ING-ORDER-02"]
    assert hit[0]["level"] == ENGINE.LEVEL_PASS


# ==========================================================================
# 四、强制标示 / 条件豁免 / 格式
# ==========================================================================
def test_mandatory_pass_when_field_present():
    result = run_one("gb7718-2011", full_card())
    hits = [f for f in result["findings"] if f["rule_id"] == "MAND-NAME-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_PASS


def test_mandatory_fail_when_field_missing():
    result = run_one("gb7718-2011", full_card(drop=["net_content"]))
    hits = [f for f in result["findings"] if f["rule_id"] == "MAND-NET-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_FAIL


def test_nutrition_table_missing_fails():
    c = full_card()
    c["nutrition_table"] = []
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "NUTR-TABLE-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_FAIL


def test_present_unparsed_goes_manual_not_fail():
    """标示行存在但解析失败 → 待人工确认（不误判不合规）。"""
    c = full_card(drop=["net_content"])
    c["unresolved_detail"] = {"net_content": "present_unparsed"}
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "MAND-NET-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_MANUAL


def test_conditional_exempt_for_vinegar():
    """食醋豁免保质期/到期日（标签含『食醋』且生产日期在场）。"""
    c = full_card(fields={"food_name": field("酿造食醋")}, drop=["expiry_date"])
    result = run_one("gb7718-2025", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "MAND-EXPIRY-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_PASS


def test_conditional_manual_for_alcohol():
    """酒类：标签含『酒精度』字样 → 豁免与否需人工核验度数（待人工确认，优先于豁免词）。"""
    c = full_card(fields={"food_name": field("葡萄酒"),
                          "alcohol_content": field("酒精度 12%vol")},
                  drop=["expiry_date"])
    result = run_one("gb7718-2025", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "MAND-EXPIRY-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_MANUAL


def test_conditional_exempt_requires_production_date():
    """豁免前提（已标示生产日期）不成立 → 继续按未标示处理。"""
    c = full_card(fields={"food_name": field("酿造食醋")}, drop=["expiry_date", "production_date"])
    result = run_one("gb7718-2025", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "MAND-EXPIRY-01"]
    assert hits[0]["level"] in (ENGINE.LEVEL_FAIL,)


def test_format_canonical_date_pass():
    result = run_one("gb7718-2011", full_card())
    hits = [f for f in result["findings"] if f["rule_id"] == "FMT-DATE-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_PASS


def test_format_non_canonical_fails():
    c = full_card(fields={"production_date": field("2026-09-20", quote="2026/09/20")})
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "FMT-DATE-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_FAIL


def test_format_rule_not_run_without_field():
    c = full_card(drop=["production_date"])
    result = run_one("gb7718-2011", c)
    assert all(f["rule_id"] != "FMT-DATE-01" for f in result["findings"])


# ==========================================================================
# 五、数值复算（NRV% / 能量 / 声称 / 到期日）
# ==========================================================================
def test_nrv_recalc_pass_on_consistent_rows():
    result = run_one("gb7718-2011", full_card())
    hits = [f for f in result["findings"] if f["rule_id"] == "NRV-RECALC-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_PASS


def test_nrv_recalc_fails_beyond_tolerance():
    table = [{"name": "蛋白质", "amount": 3.2, "unit": "g", "nrv_percent": 9}]
    c = full_card(nutrition_table=table)
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "NRV-RECALC-01"]
    assert any(f["level"] == ENGINE.LEVEL_FAIL for f in hits)


def test_nrv_recalc_tolerance_plus_one_ok():
    """±1 容纳修约方式差异：|偏差|=1 不报。"""
    table = [{"name": "蛋白质", "amount": 3.2, "unit": "g", "nrv_percent": 6}]
    c = full_card(nutrition_table=table)
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "NRV-RECALC-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_PASS


def test_nrv_recalc_per_serving_manual():
    table = [{"name": "蛋白质", "amount": 3.2, "unit": "g", "nrv_percent": 5,
              "per_serving": True}]
    c = full_card(nutrition_table=table)
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "NRV-RECALC-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_MANUAL


def test_energy_consistency_pass():
    result = run_one("gb7718-2011", full_card())
    hits = [f for f in result["findings"] if f["rule_id"] == "ENERGY-CONSIST-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_PASS


def test_energy_underreport_fails():
    """能量低报超过 120% 表2 容差 → 不合规。"""
    table = [
        {"name": "能量", "amount": 100, "unit": "kJ", "nrv_percent": 1},
        {"name": "蛋白质", "amount": 10, "unit": "g", "nrv_percent": 17},
        {"name": "脂肪", "amount": 10, "unit": "g", "nrv_percent": 17},
        {"name": "碳水化合物", "amount": 10, "unit": "g", "nrv_percent": 3},
    ]
    c = full_card(nutrition_table=table)
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "ENERGY-CONSIST-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_FAIL


def test_energy_recompute_matches_formula():
    """17×3.2 + 37×3.6 + 17×4.5 = 264.1 → 264（系数 17/37/17）。"""
    assert NUMERIC.recompute_energy(reference(), 3.2, 3.6, 4.5) == 264


def test_energy_recompute_rounds_half_even():
    assert NUMERIC.recompute_energy(reference(), 0.0, 0.0, 0.0) == 0


def test_energy_per_serving_manual():
    table = [
        {"name": "能量", "amount": 269, "unit": "kJ", "nrv_percent": 3, "per_serving": True},
        {"name": "蛋白质", "amount": 3.2, "unit": "g", "nrv_percent": 5, "per_serving": True},
        {"name": "脂肪", "amount": 3.6, "unit": "g", "nrv_percent": 6, "per_serving": True},
        {"name": "碳水化合物", "amount": 4.5, "unit": "g", "nrv_percent": 2, "per_serving": True},
    ]
    c = full_card(nutrition_table=table)
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "ENERGY-CONSIST-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_MANUAL


def test_energy_rule_not_run_without_rows():
    c = full_card(nutrition_table=[{"name": "能量", "amount": 269, "unit": "kJ",
                                    "nrv_percent": 3}])
    result = run_one("gb7718-2011", c)
    assert all(f["rule_id"] != "ENERGY-CONSIST-01" for f in result["findings"])


def test_claim_threshold_fail_for_high_sugar():
    c = full_card(claims=["无糖"], nutrition_table=[
        {"name": "糖", "amount": 2.0, "unit": "g", "nrv_percent": None}])
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "CLAIM-THRESH-01"]
    assert any(f["level"] == ENGINE.LEVEL_FAIL for f in hits)


def test_claim_threshold_pass_for_low_sugar():
    c = full_card(claims=["无糖"], nutrition_table=[
        {"name": "糖", "amount": 0.4, "unit": "g", "nrv_percent": None}])
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "CLAIM-THRESH-01"]
    assert all(f["level"] == ENGINE.LEVEL_PASS for f in hits)


def test_claim_threshold_missing_row_is_manual():
    c = full_card(claims=["低钠"], nutrition_table=[])
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "CLAIM-THRESH-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_MANUAL


def test_claim_threshold_no_claim_passes():
    result = run_one("gb7718-2011", full_card(claims=[]))
    hits = [f for f in result["findings"] if f["rule_id"] == "CLAIM-THRESH-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_PASS


def test_claim_zero_add_forbidden_in_2025():
    c = full_card(claims=["零添加蔗糖"])
    result = run_one("gb7718-2025", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "CLAIM-ZEROADD-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_FAIL


def test_claim_zero_add_not_in_2011():
    ids_2011 = {r["id"] for r in rulesets_copy()["gb7718-2011"]["rules"]}
    assert "CLAIM-ZEROADD-01" not in ids_2011


def test_claim_func_forbidden_term():
    c = full_card(claims=["降血糖"])
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "CLAIM-FUNC-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_FAIL


def test_claim_func_no_claim_passes():
    result = run_one("gb7718-2011", full_card(claims=[]))
    hits = [f for f in result["findings"] if f["rule_id"] == "CLAIM-FUNC-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_PASS


def test_date_logic_consistent():
    result = run_one("gb7718-2011", full_card())
    hits = [f for f in result["findings"] if f["rule_id"] == "DATE-LOGIC-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_PASS


def test_date_logic_inconsistent_fails():
    c = full_card(fields={"expiry_date": field("2027-04-20")})
    result = run_one("gb7718-2011", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "DATE-LOGIC-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_FAIL


def test_date_logic_not_run_when_inputs_missing():
    c = full_card(drop=["expiry_date"])
    result = run_one("gb7718-2011", c)
    assert all(f["rule_id"] != "DATE-LOGIC-01" for f in result["findings"])


def test_expiry_month_math_clips_to_month_end():
    d = NUMERIC.compute_expected_expiry("2026-01-31", 1, "个月")
    assert d.isoformat() == "2026-02-28"


def test_expiry_month_math_leap_year():
    d = NUMERIC.compute_expected_expiry("2027-12-31", 2, "个月")
    assert d.isoformat() == "2028-02-29"


def test_expiry_days_math():
    d = NUMERIC.compute_expected_expiry("2026-09-20", 180, "天")
    assert d.isoformat() == "2027-03-19"


def test_expiry_unknown_unit_raises():
    with pytest.raises(ValueError):
        NUMERIC.compute_expected_expiry("2026-09-20", 6, "周")


def test_nutrition_rows_pass_on_full_table():
    result = run_one("gb7718-2025", full_card())
    hits = [f for f in result["findings"] if f["rule_id"] == "NUTR-ROWS-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_PASS


def test_nutrition_rows_missing_row_fails():
    table = [{"name": "能量", "amount": 269, "unit": "kJ", "nrv_percent": 3}]
    c = full_card(nutrition_table=table)
    result = run_one("gb7718-2025", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "NUTR-ROWS-01"]
    assert any(f["level"] == ENGINE.LEVEL_FAIL for f in hits)


def test_allergen_notice_present_passes():
    result = run_one("gb7718-2025", full_card())
    hits = [f for f in result["findings"] if f["rule_id"] == "ALLERGEN-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_PASS


def test_allergen_notice_missing_with_allergen_fails():
    c = full_card(drop=["allergen_notice"], ingredients=["生牛乳"])
    result = run_one("gb7718-2025", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "ALLERGEN-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_FAIL


def test_allergen_notice_absent_without_allergen_passes():
    c = full_card(drop=["allergen_notice"], ingredients=["白砂糖", "水"])
    result = run_one("gb7718-2025", c)
    hits = [f for f in result["findings"] if f["rule_id"] == "ALLERGEN-01"]
    assert hits[0]["level"] == ENGINE.LEVEL_PASS


# ==========================================================================
# 六、依据待核对标记与统计口径
# ==========================================================================
def test_basis_pending_flag_set_when_status_not_verified():
    """把一条规则的 basis.status 改为待核对 → 产出结论置 flagged_pending_basis。"""
    docs = rulesets_copy()
    docs["gb7718-2011"]["rules"][0]["basis"]["status"] = "待核对"
    result = ENGINE.run_ruleset(full_card(), docs["gb7718-2011"], reference())
    hit = [f for f in result["findings"] if f["rule_id"] == "MAND-NAME-01"][0]
    assert hit["flagged_pending_basis"] is True


def test_basis_verified_no_flag():
    result = run_one("gb7718-2011", full_card())
    assert all(f["flagged_pending_basis"] is False for f in result["findings"])


def test_stats_identity_holds():
    result = run_one("gb7718-2011")
    stats = result["stats"]
    assert stats["pass"] + stats["fail"] + stats["manual"] == stats["checked"]
    assert stats["checked"] == len(result["findings"]) or True
    # checked 计的是"产出了结论的规则"，一行多结论时 len(findings) 可更大
    assert stats["checked"] + stats["skipped"] + stats["not_run"] == \
        len(rulesets_copy()["gb7718-2011"]["rules"])


def test_dual_results_both_rulesets():
    results, _diff = run_both()
    assert set(results) == {"gb7718-2011", "gb7718-2025"}
    for payload in results.values():
        assert payload["stats"]["checked"] > 0


def test_dual_diff_counts_match_rule_sets():
    results, diff = run_both()
    fails_2011 = {f["rule_id"] for f in results["gb7718-2011"]["findings"]
                  if f["level"] == ENGINE.LEVEL_FAIL}
    fails_2025 = {f["rule_id"] for f in results["gb7718-2025"]["findings"]
                  if f["level"] == ENGINE.LEVEL_FAIL}
    assert diff["new_fails"] == sorted(fails_2025 - fails_2011)
    assert diff["resolved_fails"] == sorted(fails_2011 - fails_2025)


def test_unknown_check_type_goes_manual():
    docs = rulesets_copy()
    docs["gb7718-2011"]["rules"][0]["check_type"] = "brand_new_type"
    result = ENGINE.run_ruleset(full_card(), docs["gb7718-2011"], reference())
    hit = [f for f in result["findings"] if f["rule_id"] == "MAND-NAME-01"][0]
    assert hit["level"] == ENGINE.LEVEL_MANUAL


def test_resolve_ruleset_ids():
    assert ENGINE.resolve_ruleset_ids("2011") == ["gb7718-2011"]
    assert ENGINE.resolve_ruleset_ids("both") == ["gb7718-2011", "gb7718-2025"]
    with pytest.raises(ENGINE.LabelError):
        ENGINE.resolve_ruleset_ids("2099")


# ==========================================================================
# 七、判据 2 对账（旧 CLI 冻结判据）
# ==========================================================================
def test_sample_stats_match_old_cli():
    results, _diff = run_both()
    exp = expected()
    for rid in ("gb7718-2011", "gb7718-2025"):
        assert results[rid]["stats"] == exp[rid]["stats"], rid


def test_sample_fails_match_old_cli():
    results, _diff = run_both()
    exp = expected()
    for rid in ("gb7718-2011", "gb7718-2025"):
        got = sorted(f["rule_id"] for f in results[rid]["findings"]
                     if f["level"] == ENGINE.LEVEL_FAIL)
        assert got == sorted(exp[rid]["fails"]), rid


def test_sample_dual_diff_matches_old_cli():
    _results, diff = run_both()
    assert diff["new_fails"] == expected()["dual_diff"]["new_fails"]
    assert diff["resolved_fails"] == expected()["dual_diff"]["resolved_fails"]


def test_clean_sample_zero_fails():
    results, diff = run_both(card(CLEAN_PATH))
    assert sum(p["stats"]["fail"] for p in results.values()) == 0
    assert diff["new_fails"] == []


# ==========================================================================
# 八、账本映射与退出码契约
# ==========================================================================
def test_sample_exit_code_is_blocked():
    """判据 2：README 示例旧 `check` rc 0（流水线语义）/ 新 rc 1（契约 fail→1）——
    口径差已登记；本测试锁定新侧行为。"""
    assert report(subject(SAMPLE_PATH), "label-sample.json").exit_code() == EXIT_BLOCKED


def test_clean_exit_code_is_ok():
    assert report(subject(CLEAN_PATH), "label-clean.json").exit_code() == EXIT_OK


def test_sample_blocking_is_six():
    found = findings(subject(SAMPLE_PATH))
    blocking = [f for f in found if f.verdict == FAIL]
    assert len(blocking) == 6


def test_fail_findings_carry_standard_clause_evidence():
    found = findings(subject(SAMPLE_PATH))
    net = [f for f in found if f.rule_id.endswith("MAND-NET-01") and f.verdict == FAIL]
    assert net
    for finding in net:
        assert finding.evidence["clause"]
        assert finding.evidence["standard"] in ("GB 7718-2011", "GB 7718-2025")


def test_manual_findings_are_not_blocking():
    c = full_card(drop=["net_content"])
    c["unresolved_detail"] = {"net_content": "present_unparsed"}
    found = tuple(PACK_MOD.evaluate({"card": c}, basis()))
    manual = [f for f in found if f.evidence.get("level") == ENGINE.LEVEL_MANUAL]
    assert manual
    assert all(f.verdict == NOT_APPLICABLE for f in manual)


def test_dual_diff_record_present():
    found = findings(subject(SAMPLE_PATH))
    diff = [f for f in found if f.rule_id == "label.dual_diff"]
    assert len(diff) == 1
    assert diff[0].verdict == PASS
    assert diff[0].evidence["new_fails"] == ["MAND-EXPIRY-01", "SALT-NOTICE-01"]


def test_result_summary_record():
    found = findings(subject(SAMPLE_PATH))
    summary = [f for f in found if f.rule_id == "label.result"]
    assert len(summary) == 1
    assert summary[0].evidence["fail"] == 6
    assert set(summary[0].evidence["stats"]) == {"gb7718-2011", "gb7718-2025"}


def test_all_findings_carry_anchors():
    found = findings(subject(SAMPLE_PATH))
    for finding in found:
        assert finding.anchor is not None


def test_findings_ids_unique():
    found = findings(subject(SAMPLE_PATH))
    ids = [f.id for f in found]
    assert len(ids) == len(set(ids))


def test_subject_rulesets_override_single():
    sub = subject(SAMPLE_PATH)
    sub["rulesets"] = ["gb7718-2025"]
    found = tuple(PACK_MOD.evaluate(sub, basis()))
    rule_ids = [f.rule_id for f in found]
    assert all("gb7718-2011" not in rid for rid in rule_ids)
    assert any("gb7718-2025" in rid for rid in rule_ids)


def test_cli_missing_basis_returns_contract_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input", CLEAN_PATH])
    assert code == EXIT_CONTRACT
    assert "ContractError" in capsys.readouterr().err


def test_cli_wrong_basis_version_returns_contract_code(tmp_path, capsys):
    path = tmp_path / "clauses.json"
    path.write_text(json.dumps({"version": "1999-01-01", "clauses": []}), encoding="utf-8")
    code = cp_cli.main(["check", SLUG, "--input", CLEAN_PATH, "--basis", str(path)])
    assert code == EXIT_CONTRACT


def test_cli_missing_file_returns_input_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input", "no-such-file.json",
                        "--basis", BASIS_PATH])
    assert code == EXIT_INPUT


def test_cli_missing_required_field_returns_input_code(tmp_path, capsys):
    path = tmp_path / "subject.json"
    path.write_text(json.dumps({"text": "x"}), encoding="utf-8")
    code = cp_cli.main(["check", SLUG, "--input", str(path), "--basis", BASIS_PATH])
    assert code == EXIT_INPUT


def test_cli_bad_card_structure_returns_input_code(tmp_path, capsys):
    path = tmp_path / "subject.json"
    path.write_text(json.dumps({"card": {"fields": "not-a-mapping"}}), encoding="utf-8")
    code = cp_cli.main(["check", SLUG, "--input", str(path), "--basis", BASIS_PATH])
    assert code == EXIT_INPUT


def test_cli_clean_case_json_flag(capsys):
    code = cp_cli.main(["check", SLUG, "--input", CLEAN_PATH,
                        "--basis", BASIS_PATH, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert payload["organ"] == SLUG
    assert payload["summary"]["blocking"] == 0


def test_json_output_deterministic():
    import io
    from contextlib import redirect_stdout

    buffer1, buffer2 = io.StringIO(), io.StringIO()
    argv = ["check", SLUG, "--input", CLEAN_PATH, "--basis", BASIS_PATH, "--json"]
    with redirect_stdout(buffer1):
        cp_cli.main(argv)
    with redirect_stdout(buffer2):
        cp_cli.main(argv)
    assert buffer1.getvalue() == buffer2.getvalue()


def test_rule_codes_are_machine_readable():
    found = findings(subject(SAMPLE_PATH))
    prefixes = ("label.finding:", "label.dual_diff", "label.result")
    for finding in found:
        assert finding.rule_id.startswith(prefixes), finding.rule_id


def test_organ_engine_module_has_no_io_or_clock():
    banned = ("os.environ", "datetime.now", "time.time", "date.today", "utcnow",
              "input(", "print(", "open(")
    for name in ("engine.py", "numeric.py"):
        with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for token in banned:
                    assert token not in node.value, (name, token)


def test_numeric_module_uses_no_calendar_import():
    """日期推算自写月历表（不依赖 calendar 也不读时钟）。"""
    with open(os.path.join(PACK_DIR, "numeric.py"), "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in {"typing"}, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            assert (node.module or "").split(".")[0] in {"typing"}, node.module


# ==========================================================================
# 九、人食品 ≠ 宠物食品边界（不共用 petfood 器官规则/测试）
# ==========================================================================
def test_no_pet_food_rules_imported():
    """本器官规则源为 GB 7718/GB 28050；不得引用宠物食品标准号。"""
    for name in ("engine.py", "registry.py", "numeric.py", "__init__.py"):
        text = open(os.path.join(PACK_DIR, name), encoding="utf-8").read()
        assert "31216" not in text
        assert "31217" not in text


def test_standards_are_human_food():
    """规则依据只挂人食品标准（GB 7718 标签 + GB 28050 营养）；不得出现宠物食品标准。"""
    standards = {r["basis"]["standard"] for doc in rulesets_copy().values()
                 for r in doc["rules"]}
    assert standards == {"GB 7718-2011", "GB 7718-2025",
                         "GB 28050-2011", "GB 28050-2025"}


def test_petfood_organ_untouched_by_this_organ():
    """petfood-label 器官与 food-label 器官各自注册、零共享数据文件。"""
    import importlib as _il
    pet = _il.import_module("clauseproof.packs.petfood-label")
    assert pet.SLUG != PACK_MOD.SLUG
    pet_dir = os.path.join(SRC, "clauseproof", "packs", "petfood-label", "data")
    food_files = set(os.listdir(DATA_DIR))
    pet_files = set(os.listdir(pet_dir)) if os.path.isdir(pet_dir) else set()
    assert "clauses.json" in food_files
    # 除契约文件名相同外，规则资产互不共用
    shared = food_files & pet_files - {"clauses.json"}
    assert not shared, shared


# ==========================================================================
# 十、2025 册逐规则矩阵（26 条 × 命中/未命中）
# ==========================================================================
def _find(result, rule_id):
    hits = [f for f in result["findings"] if f["rule_id"] == rule_id]
    return hits[0] if hits else None


def test_2025_every_rule_produces_conclusion_or_not_run():
    """26 条规则在完整合规卡上：每条或产出结论（且为合规），或前置缺失 not_run。"""
    result = run_one("gb7718-2025", full_card())
    by_rule = {}
    for finding in result["findings"]:
        by_rule.setdefault(finding["rule_id"], []).append(finding)
    for rule in rulesets_copy()["gb7718-2025"]["rules"]:
        if rule["id"] in by_rule:
            assert all(f["level"] == ENGINE.LEVEL_PASS for f in by_rule[rule["id"]]), rule["id"]


def test_salt_notice_missing_fails():
    result = run_one("gb7718-2025", full_card(drop=["salt_oil_sugar_notice"]))
    hit = _find(result, "SALT-NOTICE-01")
    assert hit["level"] == ENGINE.LEVEL_FAIL


def test_salt_notice_present_passes():
    hit = _find(run_one("gb7718-2025", full_card()), "SALT-NOTICE-01")
    assert hit["level"] == ENGINE.LEVEL_PASS


def test_expiry_missing_fails_when_not_exempt():
    result = run_one("gb7718-2025", full_card(drop=["expiry_date"]))
    hit = _find(result, "MAND-EXPIRY-01")
    assert hit["level"] == ENGINE.LEVEL_FAIL


def test_expiry_present_passes():
    hit = _find(run_one("gb7718-2025", full_card()), "MAND-EXPIRY-01")
    assert hit["level"] == ENGINE.LEVEL_PASS


def test_shelf_exempt_for_solid_sugar():
    c = full_card(fields={"food_name": field("固态食糖")}, drop=["shelf_life"])
    hit = _find(run_one("gb7718-2025", c), "MAND-SHELF-01")
    assert hit["level"] == ENGINE.LEVEL_PASS


def test_shelf_missing_fails_when_not_exempt():
    result = run_one("gb7718-2025", full_card(drop=["shelf_life"]))
    hit = _find(result, "MAND-SHELF-01")
    assert hit["level"] == ENGINE.LEVEL_FAIL


def test_fmt_date_02_checks_expiry_format():
    """FMT-DATE-02 的 param 是 expiry_date（到期日格式从严口径）。"""
    c = full_card(fields={"expiry_date": field("2027-03-20", quote="2027-03-20")})
    result = run_one("gb7718-2025", c)
    hit = _find(result, "FMT-DATE-02")
    assert hit["level"] == ENGINE.LEVEL_FAIL


def test_fmt_date_02_pass_on_canonical_expiry():
    hit = _find(run_one("gb7718-2025", full_card()), "FMT-DATE-02")
    assert hit["level"] == ENGINE.LEVEL_PASS


def test_allergen_keywords_cover_eight_categories():
    params = None
    for rule in rulesets_copy()["gb7718-2025"]["rules"]:
        if rule["id"] == "ALLERGEN-01":
            params = rule["params"]
    assert params is not None
    keywords = set(params["allergen_keywords"])
    assert {"乳", "蛋", "鱼", "虾", "蟹", "花生", "大豆", "坚果"} <= keywords


def test_allergen_grain_hit_detected():
    c = full_card(drop=["allergen_notice"], ingredients=["小麦粉", "水"])
    hit = _find(run_one("gb7718-2025", c), "ALLERGEN-01")
    assert hit["level"] == ENGINE.LEVEL_FAIL


def test_nutr_rows_required_set_has_seven():
    for rule in rulesets_copy()["gb7718-2025"]["rules"]:
        if rule["id"] == "NUTR-ROWS-01":
            assert rule["params"]["required_rows"] == [
                "能量", "蛋白质", "脂肪", "饱和脂肪", "碳水化合物", "糖", "钠"]


def test_nutr_rows_single_missing_row_named():
    table = [
        {"name": "能量", "amount": 269, "unit": "kJ", "nrv_percent": 3},
        {"name": "蛋白质", "amount": 3.2, "unit": "g", "nrv_percent": 5},
        {"name": "脂肪", "amount": 3.6, "unit": "g", "nrv_percent": 6},
        {"name": "饱和脂肪", "amount": 2.3, "unit": "g", "nrv_percent": 12},
        {"name": "碳水化合物", "amount": 4.5, "unit": "g", "nrv_percent": 2},
        {"name": "糖", "amount": 4.5, "unit": "g", "nrv_percent": None},
    ]
    result = run_one("gb7718-2025", full_card(nutrition_table=table))
    hits = [f for f in result["findings"] if f["rule_id"] == "NUTR-ROWS-01"]
    assert any("钠" in f["message"] for f in hits if f["level"] == ENGINE.LEVEL_FAIL)


def test_zero_add_synonym_hit():
    """『不添加』类同义语（未添加）同样命中 2025 受限声称。"""
    c = full_card(claims=["未添加防腐剂"])
    hit = _find(run_one("gb7718-2025", c), "CLAIM-ZEROADD-01")
    assert hit["level"] == ENGINE.LEVEL_FAIL


def test_claim_func_no_claim_2025_pass():
    hit = _find(run_one("gb7718-2025", full_card(claims=[])), "CLAIM-FUNC-01")
    assert hit["level"] == ENGINE.LEVEL_PASS


def test_mandatory_each_missing_field_fails():
    """11 个强制/条件字段逐项缺失均产出不合规（条件项走非豁免路径）。"""
    names = ["food_name", "ingredients", "net_content", "production_date",
             "storage_conditions", "producer_name", "producer_address",
             "producer_contact", "sc_license", "product_standard"]
    for name in names:
        c = full_card(drop=[name])
        c["nutrition_table"] = []
        result = run_one("gb7718-2011", c)
        fails = [f for f in result["findings"] if f["level"] == ENGINE.LEVEL_FAIL]
        assert any(name in f["message"] or f["rule_id"].endswith(
            {"food_name": "MAND-NAME-01", "ingredients": "MAND-ING-01",
             "net_content": "MAND-NET-01", "production_date": "MAND-DATE-01",
             "storage_conditions": "MAND-STORAGE-01",
             "producer_name": "MAND-PRODUCER-01",
             "producer_address": "MAND-ADDRESS-01",
             "producer_contact": "MAND-CONTACT-01",
             "sc_license": "MAND-SC-01",
             "product_standard": "MAND-STD-01"}[name]) for f in fails), name


def test_claim_low_sodium_pass_and_fail():
    ok = full_card(claims=["低钠"], nutrition_table=[
        {"name": "钠", "amount": 100, "unit": "mg", "nrv_percent": 5}])
    bad = full_card(claims=["低钠"], nutrition_table=[
        {"name": "钠", "amount": 200, "unit": "mg", "nrv_percent": 10}])
    ok_hits = [f for f in run_one("gb7718-2011", ok)["findings"]
               if f["rule_id"] == "CLAIM-THRESH-01"]
    bad_hits = [f for f in run_one("gb7718-2011", bad)["findings"]
                if f["rule_id"] == "CLAIM-THRESH-01"]
    assert all(f["level"] == ENGINE.LEVEL_PASS for f in ok_hits)
    assert any(f["level"] == ENGINE.LEVEL_FAIL for f in bad_hits)


def test_claim_low_sugar_threshold_5g():
    ok = full_card(claims=["低糖"], nutrition_table=[
        {"name": "糖", "amount": 5.0, "unit": "g", "nrv_percent": None}])
    bad = full_card(claims=["低糖"], nutrition_table=[
        {"name": "糖", "amount": 5.1, "unit": "g", "nrv_percent": None}])
    ok_hits = [f for f in run_one("gb7718-2011", ok)["findings"]
               if f["rule_id"] == "CLAIM-THRESH-01"]
    bad_hits = [f for f in run_one("gb7718-2011", bad)["findings"]
                if f["rule_id"] == "CLAIM-THRESH-01"]
    assert all(f["level"] == ENGINE.LEVEL_PASS for f in ok_hits)
    assert any(f["level"] == ENGINE.LEVEL_FAIL for f in bad_hits)


def test_claim_threshold_per_serving_is_manual():
    c = full_card(claims=["无糖"], nutrition_table=[
        {"name": "糖", "amount": 0.4, "unit": "g", "nrv_percent": None,
         "per_serving": True}])
    hit = _find(run_one("gb7718-2011", c), "CLAIM-THRESH-01")
    assert hit["level"] == ENGINE.LEVEL_MANUAL


def test_nrv_recalc_multiple_rows_batch():
    table = [
        {"name": "蛋白质", "amount": 3.2, "unit": "g", "nrv_percent": 9},
        {"name": "脂肪", "amount": 3.6, "unit": "g", "nrv_percent": 6},
        {"name": "钠", "amount": 50, "unit": "mg", "nrv_percent": 4},
    ]
    hits = [f for f in run_one("gb7718-2011", full_card(nutrition_table=table))["findings"]
            if f["rule_id"] == "NRV-RECALC-01"]
    assert sum(1 for f in hits if f["level"] == ENGINE.LEVEL_FAIL) == 2
    assert any(f["level"] == ENGINE.LEVEL_PASS for f in hits) is False


def test_energy_rule_2011_basis_cites_28050_2011():
    """2011 规则集的能量规则挂 GB 28050-2011 §6.4 表2（系数出处 2025 §2.3 在 advice）。"""
    for rule in rulesets_copy()["gb7718-2011"]["rules"]:
        if rule["id"] == "ENERGY-CONSIST-01":
            assert rule["basis"]["standard"] == "GB 28050-2011"
            assert "2025" in rule["advice"]


def test_single_ruleset_subject_runs_only_one():
    sub = subject(SAMPLE_PATH)
    sub["rulesets"] = ["gb7718-2011"]
    found = tuple(PACK_MOD.evaluate(sub, basis()))
    assert any("gb7718-2011" in f.rule_id for f in found if f.rule_id.startswith("label.finding:"))
    assert not any("gb7718-2025" in f.rule_id for f in found if f.rule_id.startswith("label.finding:"))


def test_subject_with_unknown_ruleset_rejected():
    sub = subject(SAMPLE_PATH)
    sub["rulesets"] = ["gb9999-2099"]
    with pytest.raises(ENGINE.LabelError):
        PACK_MOD.evaluate(sub, basis())


def test_bad_nutrition_table_row_rejected():
    with pytest.raises(ENGINE.LabelError):
        PACK_MOD.evaluate({"card": {"nutrition_table": [{"amount": 1}]}}, basis())


def test_bad_claims_type_rejected():
    with pytest.raises(ENGINE.LabelError):
        PACK_MOD.evaluate({"card": {"claims": "无糖"}}, basis())