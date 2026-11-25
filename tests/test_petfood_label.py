"""器官 ``petfood-label`` 无损测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在"判定结果"上。
来源仓判定层（9 文件 / 196 静态函数 / 实跑 207）逐文件处置见
``docs/petfood-label.md`` §6.1；本文件承载判定面全集：
45 条规则 × 五态 + 干物质基准换算 + 适用域画像 + 五态→账本映射 + 退出码。

本文件同时是**漂移门**：``data/ruleset-*.json``（来源规则包）与
``registry.RULES`` / ``registry.CLAUSES``（字面量）必须逐条一致。
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

SLUG = "petfood-label"
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", SLUG)

pack_mod = importlib.import_module("clauseproof.packs." + SLUG)
registry = importlib.import_module("clauseproof.packs." + SLUG + ".registry")
engine = importlib.import_module("clauseproof.packs." + SLUG + ".engine")

RULES = registry.RULES
PRESENCE_RULES = [r for r in RULES if r.kind == engine.KIND_PRESENCE]
THRESHOLD_RULES = [r for r in RULES if r.kind == engine.KIND_THRESHOLD and r.is_effective]
CLAIM_RULES = [r for r in RULES if r.kind == engine.KIND_CLAIM_SUPPORT]

SAMPLES = os.path.join(ROOT, "samples", SLUG)

LABEL_ALL = {
    "product_name": "测试粮A",
    "category": "猫粮",
    "life_stage": "成年",
    "ingredients": "鸡肉、糙米、鱼油",
    "additives": "维生素A、硫酸锌",
    "net_content": "2kg",
    "producer": "某合成宠物食品有限公司",
    "product_dates": "生产日期 2026-01-01；保质期 18个月",
}


# --------------------------------------------------------------------------
# 夹具
# --------------------------------------------------------------------------
def basis_path():
    return os.path.join(PACK_DIR, "data", "clauses.json")


def shipped_basis():
    return Basis.from_json(basis_path())


def card(**overrides):
    base = {"category": "猫粮", "life_stage": "成年", "fields": dict(LABEL_ALL),
            "guaranteed": {}, "claims": []}
    base.update(overrides)
    return base


def card_obj(**overrides):
    return engine.Card.from_subject(card(**overrides))


def finding_of(rule_id, subject):
    for finding in pack_mod.evaluate(subject, shipped_basis()):
        if finding.rule_id == rule_id:
            return finding
    return None


def raw_of(rule, subject, rules=None):
    for raw in pack_mod.judge(engine.Card.from_subject(subject), tuple(rules or RULES)):
        if raw.rule.rule_id == rule.rule_id:
            return raw
    return None


def rule_applicable_card(rule, guaranteed):
    """构造一张让该规则**适用**的档案（category/life_stage 取自 applies_if）。"""
    data = card()
    if rule.applies_if:
        data["category"] = rule.applies_if["category"][0]
        data["life_stage"] = rule.applies_if["life_stage"][0]
    data["guaranteed"] = guaranteed
    return data


def _dry(value):
    """把干基目标值换回标示值（水分固定 20% → 干基 = 标示 / 0.8）。"""
    return Decimal(value) * Decimal("0.8")


def _as_str(value):
    return str(value)


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
    assert get(SLUG).input_fields == ("category",)


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


def test_engine_has_no_limit_literals():
    """限值只许在 registry：engine 源码不得出现规则限值字符串（零字面量纪律）。"""
    with open(os.path.join(PACK_DIR, "engine.py"), "r", encoding="utf-8") as handle:
        source = handle.read()
    for rule in RULES:
        if rule.value is None:
            continue
        assert rule.value not in source, "%s 的限值 %s 出现在 engine.py 里" % (
            rule.rule_id, rule.value)


# ==========================================================================
# 二、漂移门：data/ruleset-*.json ↔ registry 字面量
# ==========================================================================
def _frozen_rules():
    rows = []
    for name in ("ruleset-claim.json", "ruleset-label.json", "ruleset-nutrition.json"):
        with open(os.path.join(PACK_DIR, "data", name), "r", encoding="utf-8") as handle:
            rows.extend(json.load(handle)["rules"])
    return rows


def test_data_dir_is_present_and_non_empty():
    names = sorted(os.listdir(os.path.join(PACK_DIR, "data")))
    assert names == ["clauses.json", "manifest.json",
                     "ruleset-claim.json", "ruleset-label.json", "ruleset-nutrition.json"]


def test_rule_count_matches_frozen_files():
    assert len(RULES) == len(_frozen_rules()) == 45
    assert len(PRESENCE_RULES) == 8
    assert len(THRESHOLD_RULES) == 30
    assert len(CLAIM_RULES) == 5


def test_pending_rules_are_the_two_taurine_ones():
    assert registry.PENDING_RULE_IDS == ("NUT-CAT-015", "NUT-CAT-016")
    assert all(rule.target == "牛磺酸" for rule in RULES if not rule.is_effective)


def _frozen_entry(rule_id):
    return {item["rule_id"]: item for item in _frozen_rules()}[rule_id]


def _assert_frozen_rule(rule_id):
    rule = [item for item in RULES if item.rule_id == rule_id][0]
    frozen = _frozen_entry(rule_id)
    assert rule.dimension == frozen["dimension"]
    assert rule.kind == frozen["kind"]
    assert rule.target == frozen["target"]
    assert rule.effect == frozen["effect"]
    assert rule.op == frozen.get("op")
    assert rule.value == frozen.get("value")
    assert rule.unit == frozen.get("unit")
    assert rule.basis == (frozen.get("basis") or engine.BASIS_AS_FED)
    assert dict(rule.applies_if) == {key: tuple(value)
                                     for key, value in (frozen.get("applies_if") or {}).items()}
    assert list(rule.required_support) == list(frozen.get("required_support") or [])
    assert rule.status == frozen["status"]
    assert rule.clause_id


def _assert_clause(clause_id):
    numerals = {"五": "5", "六": "6", "九": "9", "十四": "14", "十五": "15", "二十": "20"}
    frozen = {}
    for item in _frozen_rules():
        anchor = item["anchor"]
        if item["dimension"] == "nutrition":
            key = "%s:t1:r%s" % (anchor["doc_id"].lower().replace("-", ""),
                                 anchor.get("table_row"))
            path = anchor["doc_title"] + " 表1 第%s行" % anchor.get("table_row")
        else:
            number = anchor["clause"].replace("第", "").replace("条", "")
            key = "moa-annex3:%s" % numerals.get(number, number)
            path = anchor["doc_title"] + "/" + anchor["clause"]
        frozen[key] = (path, anchor.get("excerpt", ""))
    clause = [item for item in registry.CLAUSES if item[0] == clause_id][0]
    assert clause_id in frozen
    assert clause[1] == frozen[clause_id][0]
    assert clause[2] == frozen[clause_id][1]


def _rule_of(rule_id):
    return [item for item in RULES if item.rule_id == rule_id][0]


def _assert_presence_provided(rule_id):
    assert raw_of(_rule_of(rule_id), card()).verdict == engine.VERDICT_COMPLIANT


def _assert_presence_missing(rule_id):
    rule = _rule_of(rule_id)
    fields = dict(LABEL_ALL)
    data = card(fields=fields)
    fields.pop(rule.target)
    if rule.target in ("category", "life_stage"):
        data.pop(rule.target)
    raw = raw_of(rule, data)
    if rule.effect == engine.EFFECT_OBLIGATION:
        assert raw.verdict == engine.VERDICT_NONCOMPLIANT
    else:
        assert raw.verdict == engine.VERDICT_UNKNOWN


def _assert_obligation_blocks(target):
    fields = dict(LABEL_ALL)
    fields.pop(target)
    assert [f.rule_id for f in pack_mod.evaluate(card(fields=fields), shipped_basis())
            if f.verdict == FAIL]


def _assert_threshold_compliant(rule_id):
    rule = _rule_of(rule_id)
    guaranteed = {"水分": {"value": "20"},
                  rule.target: {"value": _as_str(_dry(rule.value))}}
    assert raw_of(rule, rule_applicable_card(rule, guaranteed)).verdict == engine.VERDICT_COMPLIANT


def _assert_threshold_noncompliant(rule_id):
    rule = _rule_of(rule_id)
    delta = Decimal("0.01")
    target = _dry(rule.value)
    value = target - delta if rule.op in (">=", ">") else target + delta
    guaranteed = {"水分": {"value": "20"}, rule.target: {"value": _as_str(value)}}
    assert raw_of(rule, rule_applicable_card(rule, guaranteed)).verdict == \
        engine.VERDICT_NONCOMPLIANT


def _assert_claim(rule_id, mode):
    rule = _rule_of(rule_id)
    if mode == "pass":
        assert raw_of(rule, card(claims=[rule.target])).verdict == engine.VERDICT_COMPLIANT
    elif mode == "fail":
        fields = dict(LABEL_ALL)
        for name in rule.required_support:
            fields.pop(name, None)
        assert raw_of(rule, card(fields=fields, claims=[rule.target])).verdict == \
            engine.VERDICT_NONCOMPLIANT
    else:
        assert raw_of(rule, card(claims=[])).verdict == engine.VERDICT_SKIPPED


# ---- 45 条规则 × 冻结规则包（逐条一条用例）----
def test_rule_CLAIM_001_frozen(): _assert_frozen_rule("CLAIM-001")
def test_rule_CLAIM_002_frozen(): _assert_frozen_rule("CLAIM-002")
def test_rule_CLAIM_003_frozen(): _assert_frozen_rule("CLAIM-003")
def test_rule_CLAIM_004_frozen(): _assert_frozen_rule("CLAIM-004")
def test_rule_CLAIM_005_frozen(): _assert_frozen_rule("CLAIM-005")
def test_rule_LABEL_001_frozen(): _assert_frozen_rule("LABEL-001")
def test_rule_LABEL_002_frozen(): _assert_frozen_rule("LABEL-002")
def test_rule_LABEL_003_frozen(): _assert_frozen_rule("LABEL-003")
def test_rule_LABEL_004_frozen(): _assert_frozen_rule("LABEL-004")
def test_rule_LABEL_005_frozen(): _assert_frozen_rule("LABEL-005")
def test_rule_LABEL_006_frozen(): _assert_frozen_rule("LABEL-006")
def test_rule_LABEL_007_frozen(): _assert_frozen_rule("LABEL-007")
def test_rule_LABEL_008_frozen(): _assert_frozen_rule("LABEL-008")
def test_rule_NUT_CAT_001_frozen(): _assert_frozen_rule("NUT-CAT-001")
def test_rule_NUT_CAT_002_frozen(): _assert_frozen_rule("NUT-CAT-002")
def test_rule_NUT_CAT_003_frozen(): _assert_frozen_rule("NUT-CAT-003")
def test_rule_NUT_CAT_004_frozen(): _assert_frozen_rule("NUT-CAT-004")
def test_rule_NUT_CAT_005_frozen(): _assert_frozen_rule("NUT-CAT-005")
def test_rule_NUT_CAT_006_frozen(): _assert_frozen_rule("NUT-CAT-006")
def test_rule_NUT_CAT_007_frozen(): _assert_frozen_rule("NUT-CAT-007")
def test_rule_NUT_CAT_008_frozen(): _assert_frozen_rule("NUT-CAT-008")
def test_rule_NUT_CAT_009_frozen(): _assert_frozen_rule("NUT-CAT-009")
def test_rule_NUT_CAT_010_frozen(): _assert_frozen_rule("NUT-CAT-010")
def test_rule_NUT_CAT_011_frozen(): _assert_frozen_rule("NUT-CAT-011")
def test_rule_NUT_CAT_012_frozen(): _assert_frozen_rule("NUT-CAT-012")
def test_rule_NUT_CAT_013_frozen(): _assert_frozen_rule("NUT-CAT-013")
def test_rule_NUT_CAT_014_frozen(): _assert_frozen_rule("NUT-CAT-014")
def test_rule_NUT_CAT_015_frozen(): _assert_frozen_rule("NUT-CAT-015")
def test_rule_NUT_CAT_016_frozen(): _assert_frozen_rule("NUT-CAT-016")
def test_rule_NUT_DOG_001_frozen(): _assert_frozen_rule("NUT-DOG-001")
def test_rule_NUT_DOG_002_frozen(): _assert_frozen_rule("NUT-DOG-002")
def test_rule_NUT_DOG_003_frozen(): _assert_frozen_rule("NUT-DOG-003")
def test_rule_NUT_DOG_004_frozen(): _assert_frozen_rule("NUT-DOG-004")
def test_rule_NUT_DOG_005_frozen(): _assert_frozen_rule("NUT-DOG-005")
def test_rule_NUT_DOG_006_frozen(): _assert_frozen_rule("NUT-DOG-006")
def test_rule_NUT_DOG_007_frozen(): _assert_frozen_rule("NUT-DOG-007")
def test_rule_NUT_DOG_008_frozen(): _assert_frozen_rule("NUT-DOG-008")
def test_rule_NUT_DOG_009_frozen(): _assert_frozen_rule("NUT-DOG-009")
def test_rule_NUT_DOG_010_frozen(): _assert_frozen_rule("NUT-DOG-010")
def test_rule_NUT_DOG_011_frozen(): _assert_frozen_rule("NUT-DOG-011")
def test_rule_NUT_DOG_012_frozen(): _assert_frozen_rule("NUT-DOG-012")
def test_rule_NUT_DOG_013_frozen(): _assert_frozen_rule("NUT-DOG-013")
def test_rule_NUT_DOG_014_frozen(): _assert_frozen_rule("NUT-DOG-014")
def test_rule_NUT_DOG_015_frozen(): _assert_frozen_rule("NUT-DOG-015")
def test_rule_NUT_DOG_016_frozen(): _assert_frozen_rule("NUT-DOG-016")


# ---- 22 条条款 × 冻结锚点（逐条一条用例）----
def test_clause_moa_annex3_5(): _assert_clause("moa-annex3:5")
def test_clause_moa_annex3_6(): _assert_clause("moa-annex3:6")
def test_clause_moa_annex3_9(): _assert_clause("moa-annex3:9")
def test_clause_moa_annex3_14(): _assert_clause("moa-annex3:14")
def test_clause_moa_annex3_15(): _assert_clause("moa-annex3:15")
def test_clause_moa_annex3_20(): _assert_clause("moa-annex3:20")
def test_clause_gbt312162014_r2(): _assert_clause("gbt312162014:t1:r2")
def test_clause_gbt312162014_r3(): _assert_clause("gbt312162014:t1:r3")
def test_clause_gbt312162014_r4(): _assert_clause("gbt312162014:t1:r4")
def test_clause_gbt312162014_r5(): _assert_clause("gbt312162014:t1:r5")
def test_clause_gbt312162014_r6(): _assert_clause("gbt312162014:t1:r6")
def test_clause_gbt312162014_r7(): _assert_clause("gbt312162014:t1:r7")
def test_clause_gbt312162014_r8(): _assert_clause("gbt312162014:t1:r8")
def test_clause_gbt312162014_r9(): _assert_clause("gbt312162014:t1:r9")
def test_clause_gbt312172014_r2(): _assert_clause("gbt312172014:t1:r2")
def test_clause_gbt312172014_r3(): _assert_clause("gbt312172014:t1:r3")
def test_clause_gbt312172014_r4(): _assert_clause("gbt312172014:t1:r4")
def test_clause_gbt312172014_r5(): _assert_clause("gbt312172014:t1:r5")
def test_clause_gbt312172014_r6(): _assert_clause("gbt312172014:t1:r6")
def test_clause_gbt312172014_r7(): _assert_clause("gbt312172014:t1:r7")
def test_clause_gbt312172014_r8(): _assert_clause("gbt312172014:t1:r8")
def test_clause_gbt312172014_r9(): _assert_clause("gbt312172014:t1:r9")


# ---- 8 条标示规则 × 两态（逐条一条用例）----
def test_presence_LABEL_001_provided(): _assert_presence_provided("LABEL-001")
def test_presence_LABEL_001_missing(): _assert_presence_missing("LABEL-001")
def test_presence_LABEL_002_provided(): _assert_presence_provided("LABEL-002")
def test_presence_LABEL_002_missing(): _assert_presence_missing("LABEL-002")
def test_presence_LABEL_003_provided(): _assert_presence_provided("LABEL-003")
def test_presence_LABEL_003_missing(): _assert_presence_missing("LABEL-003")
def test_presence_LABEL_004_provided(): _assert_presence_provided("LABEL-004")
def test_presence_LABEL_004_missing(): _assert_presence_missing("LABEL-004")
def test_presence_LABEL_005_provided(): _assert_presence_provided("LABEL-005")
def test_presence_LABEL_005_missing(): _assert_presence_missing("LABEL-005")
def test_presence_LABEL_006_provided(): _assert_presence_provided("LABEL-006")
def test_presence_LABEL_006_missing(): _assert_presence_missing("LABEL-006")
def test_presence_LABEL_007_provided(): _assert_presence_provided("LABEL-007")
def test_presence_LABEL_007_missing(): _assert_presence_missing("LABEL-007")
def test_presence_LABEL_008_provided(): _assert_presence_provided("LABEL-008")
def test_presence_LABEL_008_missing(): _assert_presence_missing("LABEL-008")
def test_obligation_product_name_blocks(): _assert_obligation_blocks("product_name")
def test_obligation_ingredients_blocks(): _assert_obligation_blocks("ingredients")
def test_obligation_net_content_blocks(): _assert_obligation_blocks("net_content")
def test_obligation_producer_blocks(): _assert_obligation_blocks("producer")
def test_obligation_product_dates_blocks(): _assert_obligation_blocks("product_dates")


# ---- 30 条生效理化指标 × 两态（逐条一条用例）----
def test_threshold_NUT_CAT_001_compliant(): _assert_threshold_compliant("NUT-CAT-001")
def test_threshold_NUT_CAT_001_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-001")
def test_threshold_NUT_CAT_002_compliant(): _assert_threshold_compliant("NUT-CAT-002")
def test_threshold_NUT_CAT_002_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-002")
def test_threshold_NUT_CAT_003_compliant(): _assert_threshold_compliant("NUT-CAT-003")
def test_threshold_NUT_CAT_003_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-003")
def test_threshold_NUT_CAT_004_compliant(): _assert_threshold_compliant("NUT-CAT-004")
def test_threshold_NUT_CAT_004_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-004")
def test_threshold_NUT_CAT_005_compliant(): _assert_threshold_compliant("NUT-CAT-005")
def test_threshold_NUT_CAT_005_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-005")
def test_threshold_NUT_CAT_006_compliant(): _assert_threshold_compliant("NUT-CAT-006")
def test_threshold_NUT_CAT_006_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-006")
def test_threshold_NUT_CAT_007_compliant(): _assert_threshold_compliant("NUT-CAT-007")
def test_threshold_NUT_CAT_007_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-007")
def test_threshold_NUT_CAT_008_compliant(): _assert_threshold_compliant("NUT-CAT-008")
def test_threshold_NUT_CAT_008_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-008")
def test_threshold_NUT_CAT_009_compliant(): _assert_threshold_compliant("NUT-CAT-009")
def test_threshold_NUT_CAT_009_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-009")
def test_threshold_NUT_CAT_010_compliant(): _assert_threshold_compliant("NUT-CAT-010")
def test_threshold_NUT_CAT_010_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-010")
def test_threshold_NUT_CAT_011_compliant(): _assert_threshold_compliant("NUT-CAT-011")
def test_threshold_NUT_CAT_011_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-011")
def test_threshold_NUT_CAT_012_compliant(): _assert_threshold_compliant("NUT-CAT-012")
def test_threshold_NUT_CAT_012_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-012")
def test_threshold_NUT_CAT_013_compliant(): _assert_threshold_compliant("NUT-CAT-013")
def test_threshold_NUT_CAT_013_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-013")
def test_threshold_NUT_CAT_014_compliant(): _assert_threshold_compliant("NUT-CAT-014")
def test_threshold_NUT_CAT_014_noncompliant(): _assert_threshold_noncompliant("NUT-CAT-014")
def test_threshold_NUT_DOG_001_compliant(): _assert_threshold_compliant("NUT-DOG-001")
def test_threshold_NUT_DOG_001_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-001")
def test_threshold_NUT_DOG_002_compliant(): _assert_threshold_compliant("NUT-DOG-002")
def test_threshold_NUT_DOG_002_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-002")
def test_threshold_NUT_DOG_003_compliant(): _assert_threshold_compliant("NUT-DOG-003")
def test_threshold_NUT_DOG_003_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-003")
def test_threshold_NUT_DOG_004_compliant(): _assert_threshold_compliant("NUT-DOG-004")
def test_threshold_NUT_DOG_004_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-004")
def test_threshold_NUT_DOG_005_compliant(): _assert_threshold_compliant("NUT-DOG-005")
def test_threshold_NUT_DOG_005_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-005")
def test_threshold_NUT_DOG_006_compliant(): _assert_threshold_compliant("NUT-DOG-006")
def test_threshold_NUT_DOG_006_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-006")
def test_threshold_NUT_DOG_007_compliant(): _assert_threshold_compliant("NUT-DOG-007")
def test_threshold_NUT_DOG_007_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-007")
def test_threshold_NUT_DOG_008_compliant(): _assert_threshold_compliant("NUT-DOG-008")
def test_threshold_NUT_DOG_008_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-008")
def test_threshold_NUT_DOG_009_compliant(): _assert_threshold_compliant("NUT-DOG-009")
def test_threshold_NUT_DOG_009_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-009")
def test_threshold_NUT_DOG_010_compliant(): _assert_threshold_compliant("NUT-DOG-010")
def test_threshold_NUT_DOG_010_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-010")
def test_threshold_NUT_DOG_011_compliant(): _assert_threshold_compliant("NUT-DOG-011")
def test_threshold_NUT_DOG_011_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-011")
def test_threshold_NUT_DOG_012_compliant(): _assert_threshold_compliant("NUT-DOG-012")
def test_threshold_NUT_DOG_012_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-012")
def test_threshold_NUT_DOG_013_compliant(): _assert_threshold_compliant("NUT-DOG-013")
def test_threshold_NUT_DOG_013_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-013")
def test_threshold_NUT_DOG_014_compliant(): _assert_threshold_compliant("NUT-DOG-014")
def test_threshold_NUT_DOG_014_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-014")
def test_threshold_NUT_DOG_015_compliant(): _assert_threshold_compliant("NUT-DOG-015")
def test_threshold_NUT_DOG_015_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-015")
def test_threshold_NUT_DOG_016_compliant(): _assert_threshold_compliant("NUT-DOG-016")
def test_threshold_NUT_DOG_016_noncompliant(): _assert_threshold_noncompliant("NUT-DOG-016")


# ---- 5 条宣称规则 × 三态（逐条一条用例）----
def test_claim_CLAIM_001_pass(): _assert_claim("CLAIM-001", "pass")
def test_claim_CLAIM_001_fail(): _assert_claim("CLAIM-001", "fail")
def test_claim_CLAIM_001_skipped(): _assert_claim("CLAIM-001", "skipped")
def test_claim_CLAIM_002_pass(): _assert_claim("CLAIM-002", "pass")
def test_claim_CLAIM_002_fail(): _assert_claim("CLAIM-002", "fail")
def test_claim_CLAIM_002_skipped(): _assert_claim("CLAIM-002", "skipped")
def test_claim_CLAIM_003_pass(): _assert_claim("CLAIM-003", "pass")
def test_claim_CLAIM_003_fail(): _assert_claim("CLAIM-003", "fail")
def test_claim_CLAIM_003_skipped(): _assert_claim("CLAIM-003", "skipped")
def test_claim_CLAIM_004_pass(): _assert_claim("CLAIM-004", "pass")
def test_claim_CLAIM_004_fail(): _assert_claim("CLAIM-004", "fail")
def test_claim_CLAIM_004_skipped(): _assert_claim("CLAIM-004", "skipped")
def test_claim_CLAIM_005_pass(): _assert_claim("CLAIM-005", "pass")
def test_claim_CLAIM_005_fail(): _assert_claim("CLAIM-005", "fail")
def test_claim_CLAIM_005_skipped(): _assert_claim("CLAIM-005", "skipped")


# ---- 干物质换算的越界水分（逐值一条用例）----
def test_dry_matter_rejects_zero(): _assert_dry_matter_rejects("0")
def test_dry_matter_rejects_hundred(): _assert_dry_matter_rejects("100")
def test_dry_matter_rejects_negative(): _assert_dry_matter_rejects("-5")
def test_dry_matter_rejects_over(): _assert_dry_matter_rejects("120")


def _assert_dry_matter_rejects(moisture):
    probe = engine.Card.from_subject(card(guaranteed={"水分": {"value": moisture}}))
    assert engine.to_dry_matter(Decimal("8"), probe) is None


def test_every_rule_clause_exists_in_shipped_basis():
    basis = shipped_basis()
    for rule in RULES:
        anchor = basis.anchor(rule.clause_id)
        assert anchor.version == registry.RULESET_VERSION


def test_shipped_basis_has_exactly_the_declared_clauses():
    assert shipped_basis().clause_ids() == list(registry.clause_ids())


def test_claim_vocabulary_matches_rule_targets():
    assert registry.CLAIM_VOCAB == ("天然", "无谷", "无添加", "纯天然", "鲜肉")


# ==========================================================================
# 三、presence（标示项存在性）：8 条规则 × 三态
# ==========================================================================
def test_presence_rule_with_unknown_target_is_unknown():
    probe = engine.Rule("PROBE-P", "label", "presence", "no_such_field", "obligation",
                        None, None, None, "as_fed", {}, (), "verified", "moa-annex3:5")
    raw = raw_of(probe, card(), rules=[probe])
    assert raw.verdict == engine.VERDICT_UNKNOWN


# ==========================================================================
# 四、threshold（保证值 vs 限值）：30 条生效规则 × 四态
# ==========================================================================
@pytest.mark.parametrize("rule", THRESHOLD_RULES, ids=[r.rule_id for r in THRESHOLD_RULES])
def test_threshold_rule_not_provided_when_value_absent(rule):
    guaranteed = {"水分": {"value": "20"}}
    raw = raw_of(rule, rule_applicable_card(rule, guaranteed))
    assert raw.verdict == engine.VERDICT_NOT_PROVIDED


@pytest.mark.parametrize("rule", THRESHOLD_RULES, ids=[r.rule_id for r in THRESHOLD_RULES])
def test_threshold_rule_basis_undetermined_without_moisture(rule):
    """干物质基准缺水分 → 不换算、不比较、不猜（unknown）。"""
    guaranteed = {rule.target: {"value": _as_str(_dry(rule.value))}}
    raw = raw_of(rule, rule_applicable_card(rule, guaranteed))
    assert raw.verdict == engine.VERDICT_UNKNOWN
    assert raw.note == engine.REASON_BASIS_UNDETERMINED


@pytest.mark.parametrize("rule", THRESHOLD_RULES, ids=[r.rule_id for r in THRESHOLD_RULES])
def test_threshold_rule_skipped_when_not_applicable(rule):
    """category/life_stage 不匹配 → 该规则不参与（无 finding）。"""
    data = rule_applicable_card(rule, {"水分": {"value": "20"},
                                       rule.target: {"value": _as_str(_dry(rule.value))}})
    assert raw_of(rule, data) is not None
    data["category"] = "猫粮" if data["category"] == "犬粮" else "犬粮"
    assert raw_of(rule, data) is None


# ==========================================================================
# 五、干物质基准换算（单点实算）
# ==========================================================================
def test_dry_matter_conversion_formula():
    probe = engine.Card.from_subject(card(guaranteed={"水分": {"value": "20"}}))
    assert engine.to_dry_matter(Decimal("8"), probe) == Decimal("10")


def test_dry_matter_conversion_requires_moisture():
    probe = engine.Card.from_subject(card(guaranteed={}))
    assert engine.to_dry_matter(Decimal("8"), probe) is None


def test_dry_matter_conversion_uses_low_moisture():
    probe = engine.Card.from_subject(card(guaranteed={"水分": {"value": "10"}}))
    assert engine.to_dry_matter(Decimal("18"), probe) == Decimal("20.0")


def test_high_moisture_food_is_not_judged_as_fail_by_as_fed_value():
    """湿粮观测值低，但换算到干基后达标——直接比会造假结论（来源实测缺陷）。"""
    data = card()
    data["guaranteed"] = {"水分": {"value": "80"},
                          "粗蛋白": {"value": "6.0"}}
    raw = raw_of([r for r in THRESHOLD_RULES if r.rule_id == "NUT-CAT-002"][0], data)
    assert raw.verdict == engine.VERDICT_COMPLIANT


# ==========================================================================
# 六、claim_support（宣称支撑）：5 条规则 × 三态
# ==========================================================================
def test_claim_support_is_not_semantic_judgement():
    """只查"支撑齐备"，不判"配料是否真天然"——宣称+原料齐备即 compliant。"""
    raw = raw_of(CLAIM_RULES[0], card(claims=["天然"]))
    assert raw.verdict == engine.VERDICT_COMPLIANT


def test_claim_absent_never_blocks():
    report_cached = pack_mod.evaluate(card(claims=[]), shipped_basis())
    assert not [f for f in report_cached if f.verdict == FAIL and
                f.rule_id.startswith("CLAIM-")]


# ==========================================================================
# 七、适用域画像与"未评估"
# ==========================================================================
def test_nutrition_dimension_not_assessed_without_category():
    data = card()
    data["category"] = None
    data.pop("category")
    findings = pack_mod.evaluate(data, shipped_basis())
    assert any(f.rule_id == "dimension.nutrition" for f in findings)


def test_nutrition_dimension_assessed_with_category_and_life_stage():
    findings = pack_mod.evaluate(card(guaranteed={"水分": {"value": "20"},
                                                 "粗蛋白": {"value": "30"}}),
                                 shipped_basis())
    assert not any(f.rule_id == "dimension.nutrition" for f in findings)


def test_unknown_life_stage_makes_rules_inapplicable():
    data = card()
    data["life_stage"] = None
    data.pop("life_stage")
    findings = pack_mod.evaluate(data, shipped_basis())
    assert any(f.rule_id == "dimension.nutrition" for f in findings)


def test_applies_if_requires_every_key():
    rule = [r for r in THRESHOLD_RULES if r.rule_id == "NUT-CAT-002"][0]
    assert rule.applies_to("猫粮", "成年") is True
    assert rule.applies_to("猫粮", None) is False
    assert rule.applies_to(None, "成年") is False
    assert rule.applies_to("犬粮", "成年") is False


def test_dog_and_cat_thresholds_are_not_mixed():
    """犬粮档案不得套用猫粮限值（猫粮粗蛋白 >=25，犬粮成年 >=18）。"""
    data = card()
    data["category"] = "犬粮"
    data["guaranteed"] = {"水分": {"value": "20"},
                          "粗蛋白": {"value": "20"}}
    ids = [raw.rule.rule_id for raw in
           pack_mod.judge(engine.Card.from_subject(data))]
    assert "NUT-DOG-002" in ids
    assert not any(item.startswith("NUT-CAT-") for item in ids)


# ==========================================================================
# 八、账本映射：verdict / 锚点 / 登记行
# ==========================================================================
def test_compliant_maps_to_pass_with_anchor():
    finding = finding_of("LABEL-001", card())
    assert finding.verdict == PASS
    assert finding.anchor.clause_id == "moa-annex3:5"
    assert finding.anchor.version == registry.RULESET_VERSION


def test_noncompliant_maps_to_fail_with_anchor():
    fields = dict(LABEL_ALL)
    fields.pop("net_content")
    finding = finding_of("LABEL-003", card(fields=fields))
    assert finding.verdict == FAIL
    assert finding.anchor.clause_id == "moa-annex3:9"
    assert finding.evidence["source_verdict"] == engine.VERDICT_NONCOMPLIANT


def test_unknown_maps_to_not_applicable():
    fields = dict(LABEL_ALL)
    fields.pop("additives")
    finding = finding_of("LABEL-006", card(fields=fields))
    assert finding.verdict == NOT_APPLICABLE
    assert "未判定（unknown）" in finding.message
    assert finding.anchor is not None, "未观测也要挂条款锚点（说明依据是哪条）"


def test_skipped_maps_to_not_applicable():
    finding = finding_of("CLAIM-002", card(claims=[]))
    assert finding.verdict == NOT_APPLICABLE
    assert "未判定（skipped）" in finding.message


def test_not_provided_maps_to_not_applicable():
    finding = finding_of("NUT-CAT-002",
                         card(guaranteed={"水分": {"value": "20"}}))
    assert finding.verdict == NOT_APPLICABLE
    assert "未判定（not_provided）" in finding.message


def test_pending_registration_line_is_emitted_once():
    findings = pack_mod.evaluate(card(guaranteed={"水分": {"value": "20"}}),
                                 shipped_basis())
    pending = [f for f in findings if f.rule_id == pack_mod.PENDING_RULE_ID]
    assert len(pending) == 1
    assert pending[0].verdict == NOT_APPLICABLE
    assert pending[0].anchor is None
    assert pending[0].evidence["pending_rules"] == 2


def test_every_fail_carries_full_basis_ref():
    fields = dict(LABEL_ALL)
    fields.pop("net_content")
    payload = finding_of("LABEL-003", card(fields=fields)).as_dict()
    assert payload["basis_ref"]["clause_id"]
    assert payload["basis_ref"]["path"]
    assert payload["basis_ref"]["version"]


def test_record_ids_are_unique():
    fields = dict(LABEL_ALL)
    fields.pop("net_content")
    findings = pack_mod.evaluate(card(fields=fields), shipped_basis())
    ids = [f.id for f in findings]
    assert len(ids) == len(set(ids))


def test_output_is_deterministic():
    fields = dict(LABEL_ALL)
    fields.pop("net_content")
    first = json.dumps(pack_mod.evaluate(card(fields=fields), shipped_basis())[0].as_dict(),
                       ensure_ascii=False)
    second = json.dumps(pack_mod.evaluate(card(fields=fields), shipped_basis())[0].as_dict(),
                        ensure_ascii=False)
    assert first == second
    assert ROOT not in first


def test_basis_version_mismatch_is_contract_error():
    with pytest.raises(ContractError):
        pack_mod.evaluate(card(), Basis(version="1999-01-01", clauses=()))


def test_missing_clause_propagates_basis_missing():
    with pytest.raises(BasisMissing):
        pack_mod.evaluate(card(), Basis(version=registry.RULESET_VERSION, clauses=()))


# ==========================================================================
# 九、输入校验（退出码 2）
# ==========================================================================
def test_subject_rejects_non_mapping():
    with pytest.raises(engine.PackError):
        engine.Card.from_subject(["x"])


def test_subject_rejects_unknown_field():
    with pytest.raises(engine.PackError):
        engine.Card.from_subject(card(fields={"no_such": "x"}))


def test_subject_rejects_blank_field_value():
    with pytest.raises(engine.PackError):
        engine.Card.from_subject(card(fields={"product_name": "  "}))


def test_subject_rejects_non_mapping_fields():
    with pytest.raises(engine.PackError):
        engine.Card.from_subject(card(fields=["product_name"]))


def test_subject_rejects_non_mapping_guaranteed():
    with pytest.raises(engine.PackError):
        engine.Card.from_subject(card(guaranteed=["粗蛋白"]))


def test_subject_rejects_bool_guaranteed_value():
    with pytest.raises(engine.PackError):
        engine.Card.from_subject(card(guaranteed={"粗蛋白": {"value": True}}))


def test_subject_rejects_unparsable_guaranteed_value():
    with pytest.raises(engine.PackError):
        engine.Card.from_subject(card(guaranteed={"粗蛋白": {"value": "abc"}}))


def test_subject_accepts_plain_number_guaranteed():
    obj = engine.Card.from_subject(card(guaranteed={"粗蛋白": 28}))
    assert obj.guaranteed_value("粗蛋白") == Decimal("28")


def test_subject_rejects_bad_claims():
    for bad in ([""], [1], "天然"):
        with pytest.raises(engine.PackError):
            engine.Card.from_subject(card(claims=bad))


def test_subject_accepts_null_claims_and_fields():
    obj = engine.Card.from_subject(card(claims=None, fields=None, guaranteed=None))
    assert obj.claims == ()
    assert obj.fields == {}


def test_subject_rejects_blank_category():
    with pytest.raises(engine.PackError):
        engine.Card.from_subject(card(category="  "))


# ==========================================================================
# 十、唯一入口（CLI）：退出码 0/1/2/3
# ==========================================================================
def _write(tmp_path, name, payload):
    target = tmp_path / name
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(target)


def test_cli_list_shows_the_organ(capsys):
    assert cp_cli.main(["list"]) == EXIT_OK
    assert SLUG in capsys.readouterr().out


def test_cli_check_ok_card_exits_zero(capsys):
    assert cp_cli.main(["check", SLUG, "--input",
                        os.path.join(SAMPLES, "card-ok.json"),
                        "--basis", basis_path()]) == EXIT_OK


def test_cli_check_missing_card_exits_one(capsys):
    assert cp_cli.main(["check", SLUG, "--input",
                        os.path.join(SAMPLES, "card-missing.json"),
                        "--basis", basis_path()]) == EXIT_BLOCKED


def test_cli_check_without_basis_is_contract_violation(capsys):
    assert cp_cli.main(["check", SLUG, "--input",
                        os.path.join(SAMPLES, "card-ok.json")]) == EXIT_CONTRACT


def test_cli_check_bad_card_exits_two(capsys, tmp_path):
    target = _write(tmp_path, "bad.json", {"fields": {"no_such": "x"}})
    assert cp_cli.main(["check", SLUG, "--input", target,
                        "--basis", basis_path()]) == EXIT_INPUT


def test_cli_check_missing_file_exits_two(capsys, tmp_path):
    assert cp_cli.main(["check", SLUG, "--input", str(tmp_path / "nope.json"),
                        "--basis", basis_path()]) == EXIT_INPUT


def test_cli_json_is_byte_identical_across_two_runs(capsys):
    path = os.path.join(SAMPLES, "card-missing.json")
    cp_cli.main(["check", SLUG, "--input", path, "--basis", basis_path(), "--json"])
    first = capsys.readouterr().out
    cp_cli.main(["check", SLUG, "--input", path, "--basis", basis_path(), "--json"])
    assert capsys.readouterr().out == first


def test_cli_json_payload_shape(capsys):
    cp_cli.main(["check", SLUG, "--input", os.path.join(SAMPLES, "card-missing.json"),
                 "--basis", basis_path(), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG
    assert payload["summary"]["blocking"] == 1
    assert payload["records"][0]["basis_ref"]["clause_id"]


# ==========================================================================
# 十一、样例件（§7.3 判据 2 的观测面）
# ==========================================================================
def test_sample_cards_are_shipped():
    assert sorted(os.listdir(SAMPLES)) == ["card-missing.json", "card-ok.json"]


def test_sample_ok_card_summary():
    report = Report(product="clauseproof", organ=SLUG, organ_version=pack_mod.VERSION,
                    subject="card-ok.json",
                    findings=tuple(pack_mod.evaluate(
                        json.load(open(os.path.join(SAMPLES, "card-ok.json"),
                                       encoding="utf-8")), shipped_basis())))
    assert report.summary()["blocking"] == 0


def test_sample_missing_card_blocks_on_label_003():
    findings = pack_mod.evaluate(
        json.load(open(os.path.join(SAMPLES, "card-missing.json"), encoding="utf-8")),
        shipped_basis())
    assert [f.rule_id for f in findings if f.verdict == FAIL] == ["LABEL-003"]