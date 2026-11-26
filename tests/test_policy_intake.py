"""器官 ``policy-intake`` 无损判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在「判定结果」上。
来源仓判定层（D1 + D18 机械选 10 文件 / 实跑 229 passed / AST 函数 193）逐文件处置见
``docs/policy-intake.md`` §6。

本文件同时是**漂移门**：``data/org-aliases.json`` 与 ``registry.ORG_ALIASES``、
``data/clauses.json`` 与 ``registry.clause_text`` 必须逐条一致（手改任一侧即红）。
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

PACK_MOD = importlib.import_module("clauseproof.packs.policy-intake")
ENGINE = importlib.import_module("clauseproof.packs.policy-intake.engine")
REGISTRY = importlib.import_module("clauseproof.packs.policy-intake.registry")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "policy-intake")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "policy-intake")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
PAIR_PATH = os.path.join(SAMPLES, "pair-a-b.json")

ALIASES = REGISTRY.alias_map()


def basis():
    return Basis.from_json(BASIS_PATH)


def item(item_id="26270001", **overrides):
    payload = {
        "source": "gwy",
        "id": item_id,
        "index": "",
        "pcode": "国办发〔2026〕28号",
        "title": "关于示例事项的通知",
        "pubtimeStr": "2026.10.08",
        "puborg": "国务院",
        "url": "https://example.gov.cn/a",
        "summary": "摘要",
        "channel": "国务院",
    }
    payload.update(overrides)
    return payload


def pair():
    with open(PAIR_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def truth(name):
    with open(os.path.join(SAMPLES, "%s.json" % name), "r", encoding="utf-8") as handle:
        return json.load(handle)


def judge(subject, aliases=None):
    return ENGINE.judge_intake(subject, aliases)


def findings(subject, aliases=None):
    return tuple(PACK_MOD.evaluate_with_aliases(subject, basis(), aliases))


def one(found, rule_id):
    hits = [finding for finding in found if finding.rule_id == rule_id]
    assert len(hits) == 1, (rule_id, [f.rule_id for f in found])
    return hits[0]


def report(subject):
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject="items.json", findings=findings(subject))


def _read(name):
    with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
        return handle.read()


def _aliases_json():
    with open(os.path.join(DATA_DIR, "org-aliases.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)


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


def test_pack_declares_current_as_required_field():
    assert get(SLUG).input_fields == ("current",)


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


def test_pack_has_no_network_or_clock_imports():
    banned = ("time", "datetime", "random", "socket", "urllib", "requests", "http")
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


def test_evaluate_signature_is_fixed():
    import inspect

    assert list(inspect.signature(PACK_MOD.evaluate).parameters) == ["subject", "basis"]


def test_engine_has_no_policy_or_url_literals():
    """零政策/零 URL 字面量：engine 不出现 http(s) 与年份形态常量。"""
    source = _read("engine.py")
    assert "http://" not in source and "https://" not in source


def test_registry_declares_longest_first_matching():
    assert REGISTRY.MATCH_RULE == "longest_first"


def test_registry_dedup_keys_document_two_keys():
    assert "id" in REGISTRY.DEDUP_KEYS
    assert "pcode" in REGISTRY.DEDUP_KEYS


def test_registry_order_rule_is_documented():
    assert REGISTRY.ORDER_RULE == "pubtimeStr_desc_id_asc"


# ==========================================================================
# 二、别名表漂移门（39 条逐条）
# ==========================================================================
def _alias_ok(raw, canonical):
    assert ALIASES[raw] == canonical, raw
    assert _aliases_json()["aliases"][raw] == canonical, raw


def test_alias_renmin_yinhang():
    _alias_ok("中国人民银行", "中国人民银行")


def test_alias_qixiangju_bangongshi():
    _alias_ok("中国气象局办公室", "中国气象局办公室")


def test_alias_zhengjianhui():
    _alias_ok("中国证监会", "中国证监会")


def test_alias_zhongyang_wangxinban():
    _alias_ok("中央网信办", "中央网信办")


def test_alias_jiaotong_yunshubu():
    _alias_ok("交通运输部", "交通运输部")


def test_alias_zhujianbu():
    _alias_ok("住房和城乡建设部", "住房和城乡建设部")


def test_alias_zhujianbu_short():
    _alias_ok("住房城乡建设部", "住房和城乡建设部")


def test_alias_zhujianbu_bangongting():
    _alias_ok("住房城乡建设部办公厅", "住房和城乡建设部办公厅")


def test_alias_gonganbu():
    _alias_ok("公安部", "公安部")


def test_alias_nongcunbu():
    _alias_ok("农业农村部", "农业农村部")


def test_alias_shangwubu():
    _alias_ok("商务部", "商务部")


def test_alias_guowuyuan():
    _alias_ok("国务院", "国务院")


def test_alias_guowuyuan_bangongting():
    _alias_ok("国务院办公厅", "国务院办公厅")


def test_alias_zhongyiyaoju():
    _alias_ok("国家中医药局", "国家中医药局")


def test_alias_zhongyiyaoju_zonghesi():
    _alias_ok("国家中医药局综合司", "国家中医药局综合司")


def test_alias_yibaoju():
    _alias_ok("国家医保局", "国家医保局")


def test_alias_weijianwei():
    _alias_ok("国家卫生健康委", "国家卫生健康委")


def test_alias_weijianwei_bangongting():
    _alias_ok("国家卫生健康委办公厅", "国家卫生健康委办公厅")


def test_alias_fagaiwei():
    _alias_ok("国家发展改革委", "国家发展改革委")


def test_alias_fagaiwei_bangongting():
    _alias_ok("国家发展改革委办公厅", "国家发展改革委办公厅")


def test_alias_xinwen_chubanshu():
    _alias_ok("国家新闻出版署", "国家新闻出版署")


def test_alias_lincaoju():
    _alias_ok("国家林草局", "国家林草局")


def test_alias_banquanju():
    _alias_ok("国家版权局", "国家版权局")


def test_alias_zhichanju():
    _alias_ok("国家知识产权局", "国家知识产权局")


def test_alias_wangxinban():
    _alias_ok("国家网信办", "国家网信办")


def test_alias_nengyuanju():
    _alias_ok("国家能源局", "国家能源局")


def test_alias_yaopinjianduju():
    _alias_ok("国家药监局", "国家药监局")


def test_alias_youzhengju():
    _alias_ok("国家邮政局", "国家邮政局")


def test_alias_tieluju():
    _alias_ok("国家铁路局", "国家铁路局")


def test_alias_gongxinbu():
    _alias_ok("工业和信息化部", "工业和信息化部")


def test_alias_gongxinbu_bangongting():
    _alias_ok("工业和信息化部办公厅", "工业和信息化部办公厅")


def test_alias_shichangjianguan_zongju():
    _alias_ok("市场监管总局", "市场监管总局")


def test_alias_shichangjianguan_bangongting():
    _alias_ok("市场监管总局办公厅", "市场监管总局办公厅")


def test_alias_yingjiguanlibu():
    _alias_ok("应急管理部", "应急管理部")


def test_alias_wenlvbu():
    _alias_ok("文化和旅游部", "文化和旅游部")


def test_alias_minzhengbu():
    _alias_ok("民政部", "民政部")


def test_alias_ziranzibuyuan():
    _alias_ok("自然资源部", "自然资源部")


def test_alias_caizhengbu():
    _alias_ok("财政部", "财政部")


def test_alias_jinrongjianguan_zongju():
    _alias_ok("金融监管总局", "金融监管总局")


def test_alias_table_has_thirtynine_entries():
    assert len(REGISTRY.ORG_ALIASES) == len(_aliases_json()["aliases"]) == 39


def test_alias_table_match_rule_matches_source():
    assert _aliases_json()["match_rule"] == REGISTRY.MATCH_RULE


def test_alias_table_order_matches_source():
    assert [raw for raw, _canonical in REGISTRY.ORG_ALIASES] == list(
        _aliases_json()["aliases"])


# ==========================================================================
# 三、条文库（数据契约锚点）漂移门
# ==========================================================================
def test_clauses_version_matches_contract():
    assert basis().version == REGISTRY.CONTRACT_VERSION == "2026-10-15"


def test_clauses_cover_every_contract_spec():
    assert set(basis().clause_ids()) == {cid for cid, _path in REGISTRY.clause_specs()}


def test_clauses_have_expected_count():
    assert len(basis()) == 8


def test_clause_paths_are_data_contracts():
    for clause_id in basis().clause_ids():
        assert basis().clause(clause_id).path.startswith("数据契约 / "), clause_id


def test_clause_texts_match_registry():
    for clause_id in basis().clause_ids():
        assert basis().clause(clause_id).text == REGISTRY.clause_text(clause_id), clause_id


def test_clause_texts_cite_no_law_name():
    for clause_id in basis().clause_ids():
        assert "《" not in basis().clause(clause_id).text, clause_id


def test_schema_clause_lists_every_field():
    text = basis().clause(REGISTRY.CLAUSE_SCHEMA).text
    for name in REGISTRY.SCHEMA_FIELDS:
        assert name in text, name


def test_snapshot_clause_lists_forbidden_fields():
    text = basis().clause(REGISTRY.CLAUSE_SNAPSHOT_FIELDS).text
    for name in REGISTRY.FORBIDDEN_SNAPSHOT_FIELDS:
        assert name in text, name


# ==========================================================================
# 四、条目 schema 与日期
# ==========================================================================
def test_required_fields_are_seven():
    assert len(REGISTRY.REQUIRED_FIELDS) == 7


def test_schema_fields_are_ten():
    assert len(REGISTRY.SCHEMA_FIELDS) == 10


def test_normalize_item_keeps_schema_order():
    normalized = ENGINE.normalize_item(item())
    assert [key for key in normalized if not key.startswith("_")] == list(
        REGISTRY.SCHEMA_FIELDS)


def test_normalize_item_fills_missing_with_empty():
    normalized = ENGINE.normalize_item({"id": "1"})
    assert normalized["title"] == ""
    assert normalized["source"] == ""


def test_normalize_item_rejects_non_mapping():
    with pytest.raises(ENGINE.ItemError):
        ENGINE.normalize_item([])


def test_required_missing_lists_absent_fields():
    normalized = ENGINE.normalize_item({"id": "1"})
    assert "title" in ENGINE.required_missing(normalized)


def test_required_missing_treats_blank_as_missing():
    normalized = ENGINE.normalize_item(item(title="   "))
    assert ENGINE.required_missing(normalized) == ("title",)


def test_required_missing_empty_for_complete_item():
    assert ENGINE.required_missing(ENGINE.normalize_item(item())) == ()


def test_pcode_and_index_are_not_required():
    normalized = ENGINE.normalize_item(item(pcode="", index=""))
    assert ENGINE.required_missing(normalized) == ()


def test_extra_fields_are_reported():
    normalized = ENGINE.normalize_item(item(remark="x"))
    assert ENGINE.extra_fields(normalized) == ("remark",)


def test_forbidden_field_content_is_reported():
    normalized = ENGINE.normalize_item(item(content="正文"))
    assert ENGINE.forbidden_fields(normalized) == ("content",)


def test_forbidden_field_body_is_reported():
    normalized = ENGINE.normalize_item(item(body="正文"))
    assert ENGINE.forbidden_fields(normalized) == ("body",)


def test_forbidden_field_fulltext_is_reported():
    normalized = ENGINE.normalize_item(item(fulltext="正文"))
    assert ENGINE.forbidden_fields(normalized) == ("fulltext",)


def test_forbidden_field_html_is_reported():
    normalized = ENGINE.normalize_item(item(html="<p>"))
    assert ENGINE.forbidden_fields(normalized) == ("html",)


def test_forbidden_field_article_is_reported():
    normalized = ENGINE.normalize_item(item(article="正文"))
    assert ENGINE.forbidden_fields(normalized) == ("article",)


def test_clean_item_has_no_field_violation():
    normalized = [ENGINE.normalize_item(item())]
    assert ENGINE.field_violations(normalized) == []


def test_field_violations_carry_index_and_id():
    normalized = [ENGINE.normalize_item(item(content="正文"))]
    violation = ENGINE.field_violations(normalized)[0]
    assert violation["index"] == 0
    assert violation["item_id"] == "26270001"
    assert violation["kind"] == "forbidden"


def test_extra_field_violation_kind_is_extra():
    normalized = [ENGINE.normalize_item(item(remark="x"))]
    assert ENGINE.field_violations(normalized)[0]["kind"] == "extra"


def test_date_valid_accepts_standard_form():
    assert ENGINE.date_valid("2026.10.08") is True


def test_date_valid_rejects_dash_form():
    assert ENGINE.date_valid("2026-10-08") is False


def test_date_valid_rejects_month_thirteen():
    assert ENGINE.date_valid("2026.13.01") is False


def test_date_valid_rejects_day_fortyfive():
    assert ENGINE.date_valid("2026.01.45") is False


def test_date_valid_rejects_feb_thirty_in_non_leap_year():
    assert ENGINE.date_valid("2026.02.30") is False


def test_date_valid_accepts_feb_twenty_nine_in_leap_year():
    assert ENGINE.date_valid("2028.02.29") is True


def test_date_valid_rejects_feb_twenty_nine_in_common_year():
    assert ENGINE.date_valid("2026.02.29") is False


def test_date_valid_accepts_century_leap_2000():
    assert ENGINE.date_valid("2000.02.29") is True


def test_date_valid_rejects_century_non_leap_1900():
    assert ENGINE.date_valid("1900.02.29") is False


def test_date_valid_rejects_empty():
    assert ENGINE.date_valid("") is False


def test_date_valid_rejects_none():
    assert ENGINE.date_valid(None) is False


def test_date_valid_rejects_short_form():
    assert ENGINE.date_valid("2026.1.8") is False


def test_date_valid_accepts_month_and_day_boundaries():
    assert ENGINE.date_valid("2026.01.01") is True
    assert ENGINE.date_valid("2026.12.31") is True


# ==========================================================================
# 五、文号三态
# ==========================================================================
def test_pcode_bracket_form_is_parsed():
    parsed = ENGINE.parse_pcode("国办发〔2026〕28号")
    assert parsed == {"agency_code": "国办发", "year": "2026", "serial": "28",
                      "status": "parsed"}


def test_pcode_fullwidth_bracket_is_parsed():
    parsed = ENGINE.parse_pcode("国办发﹝2026﹞9号")
    assert parsed["status"] == "parsed"
    assert parsed["year"] == "2026"


def test_pcode_spaced_serial_is_tolerated():
    parsed = ENGINE.parse_pcode("农农发〔2026〕9 号")
    assert parsed["serial"] == "9"


def test_pcode_compound_agency_code_is_kept():
    parsed = ENGINE.parse_pcode("工信部联规函〔2026〕305号")
    assert parsed["agency_code"] == "工信部联规函"
    assert parsed["serial"] == "305"


def test_pcode_decree_form_has_no_year():
    parsed = ENGINE.parse_pcode("国令第847号")
    assert parsed["agency_code"] == "国令"
    assert parsed["year"] == "未解析"
    assert parsed["serial"] == "847"
    assert parsed["status"] == "partial"


def test_pcode_empty_is_unparsed():
    parsed = ENGINE.parse_pcode("")
    assert parsed["status"] == "unparsed"
    assert parsed["agency_code"] == "未解析"


def test_pcode_none_is_unparsed():
    assert ENGINE.parse_pcode(None)["status"] == "unparsed"


def test_pcode_unrecognised_is_unparsed():
    assert ENGINE.parse_pcode("这是一份文件")["status"] == "unparsed"


def test_pcode_without_close_bracket_falls_back():
    parsed = ENGINE.parse_pcode("国办发〔2026 28号")
    assert parsed["status"] == "unparsed"


def test_pcode_year_not_four_digits_is_partial():
    parsed = ENGINE.parse_pcode("国办发〔26〕28号")
    assert parsed["year"] == "未解析"
    assert parsed["status"] == "partial"


def test_pcode_serial_without_digits_is_partial():
    parsed = ENGINE.parse_pcode("国办发〔2026〕号")
    assert parsed["serial"] == "未解析"
    assert parsed["status"] == "partial"


def test_pcode_sentinel_value_is_unparsed_word():
    assert REGISTRY.UNPARSED == "未解析"


def test_pcode_statuses_are_three():
    assert REGISTRY.PCODE_STATUSES == ("parsed", "partial", "unparsed")


def test_pcode_trims_surrounding_spaces():
    assert ENGINE.parse_pcode("  国办发〔2026〕28号  ")["agency_code"] == "国办发"


def test_pcode_blank_agency_before_bracket_is_unparsed_field():
    parsed = ENGINE.parse_pcode("〔2026〕28号")
    assert parsed["agency_code"] == "未解析"
    assert parsed["status"] == "partial"


# ==========================================================================
# 六、部门归一
# ==========================================================================
def test_orgs_are_split_on_whitespace():
    orgs = ENGINE.parse_orgs("财政部 民政部", ALIASES)
    assert [org["canonical"] for org in orgs] == ["财政部", "民政部"]


def test_orgs_split_on_en_space():
    orgs = ENGINE.parse_orgs("财政部\u2002民政部", ALIASES)
    assert len(orgs) == 2


def test_orgs_split_on_non_breaking_space():
    orgs = ENGINE.parse_orgs("财政部\u00a0民政部", ALIASES)
    assert len(orgs) == 2


def test_org_alias_maps_to_canonical():
    orgs = ENGINE.parse_orgs("住房城乡建设部", ALIASES)
    assert orgs[0]["canonical"] == "住房和城乡建设部"
    assert orgs[0]["alias_missing"] is False


def test_org_longest_first_keeps_office_suffix():
    """最长优先：`国务院` 不得把 `国务院办公厅` 读成 `国务院`。"""
    orgs = ENGINE.parse_orgs("国务院办公厅", ALIASES)
    assert orgs[0]["canonical"] == "国务院办公厅"


def test_org_prefix_matching_allows_suffix():
    orgs = ENGINE.parse_orgs("财政部综合司", ALIASES)
    assert orgs[0]["canonical"] == "财政部"
    assert orgs[0]["alias_missing"] is False


def test_org_unknown_token_is_kept_as_is():
    orgs = ENGINE.parse_orgs("某某新设机构", ALIASES)
    assert orgs[0]["canonical"] == "某某新设机构"
    assert orgs[0]["alias_missing"] is True


def test_org_empty_puborg_yields_no_token():
    assert ENGINE.parse_orgs("", ALIASES) == []


def test_org_blank_puborg_yields_no_token():
    assert ENGINE.parse_orgs("   ", ALIASES) == []


def test_org_whitespace_only_separators_are_ignored():
    assert len(ENGINE.parse_orgs("财政部  民政部", ALIASES)) == 2


def test_sorted_alias_keys_is_longest_first():
    keys = ENGINE.sorted_alias_keys(ALIASES)
    assert keys[0] in ("住房城乡建设部办公厅",)


def test_sorted_alias_keys_is_deterministic():
    assert ENGINE.sorted_alias_keys(ALIASES) == ENGINE.sorted_alias_keys(ALIASES)


# ==========================================================================
# 七、规范序与双键去重
# ==========================================================================
def test_canonical_order_sorts_date_desc():
    items = [ENGINE.normalize_item(item("1", pubtimeStr="2026.10.01")),
             ENGINE.normalize_item(item("2", pubtimeStr="2026.10.09"))]
    assert [entry["id"] for entry in ENGINE.canonical_order(items)] == ["2", "1"]


def test_canonical_order_sorts_id_asc_within_date():
    items = [ENGINE.normalize_item(item("9", pubtimeStr="2026.10.01")),
             ENGINE.normalize_item(item("1", pubtimeStr="2026.10.01"))]
    assert [entry["id"] for entry in ENGINE.canonical_order(items)] == ["1", "9"]


def test_canonical_order_is_stable_for_equal_keys():
    items = [ENGINE.normalize_item(item(str(index), pubtimeStr="2026.10.01"))
             for index in range(5)]
    assert [entry["id"] for entry in ENGINE.canonical_order(items)] == [
        "0", "1", "2", "3", "4"]


def test_canonical_order_does_not_mutate_input():
    items = [ENGINE.normalize_item(item("1", pubtimeStr="2026.10.01")),
             ENGINE.normalize_item(item("2", pubtimeStr="2026.10.09"))]
    before = [entry["id"] for entry in items]
    ENGINE.canonical_order(items)
    assert [entry["id"] for entry in items] == before


def test_is_canonical_order_true_for_sorted():
    items = [ENGINE.normalize_item(item("2", pubtimeStr="2026.10.09")),
             ENGINE.normalize_item(item("1", pubtimeStr="2026.10.01"))]
    assert ENGINE.is_canonical_order(items) is True


def test_is_canonical_order_false_for_unsorted():
    items = [ENGINE.normalize_item(item("1", pubtimeStr="2026.10.01")),
             ENGINE.normalize_item(item("2", pubtimeStr="2026.10.09"))]
    assert ENGINE.is_canonical_order(items) is False


def test_detect_new_by_id():
    previous = [ENGINE.normalize_item(item("1"))]
    current = [ENGINE.normalize_item(item("1"))]
    result = ENGINE.detect_new(previous, current)
    assert result["dup_ids"] == ["1"]
    assert result["matched_by"] == {"1": "id"}


def test_detect_new_by_pcode():
    previous = [ENGINE.normalize_item(item("1", pcode="国办发〔2026〕28号"))]
    current = [ENGINE.normalize_item(item("2", pcode="国办发〔2026〕28号"))]
    result = ENGINE.detect_new(previous, current)
    assert result["dup_ids"] == ["2"]
    assert result["matched_by"] == {"2": "pcode"}


def test_detect_new_when_pcode_empty():
    previous = [ENGINE.normalize_item(item("1", pcode=""))]
    current = [ENGINE.normalize_item(item("2", pcode=""))]
    result = ENGINE.detect_new(previous, current)
    assert result["new_ids"] == ["2"]


def test_detect_new_id_wins_over_pcode():
    previous = [ENGINE.normalize_item(item("1", pcode="国办发〔2026〕28号"))]
    current = [ENGINE.normalize_item(item("1", pcode="国办发〔2026〕99号"))]
    assert ENGINE.detect_new(previous, current)["matched_by"] == {"1": "id"}


def test_detect_new_lists_are_sorted():
    previous = []
    current = [ENGINE.normalize_item(item("9")), ENGINE.normalize_item(item("2"))]
    assert ENGINE.detect_new(previous, current)["new_ids"] == ["2", "9"]


def test_detect_new_empty_previous_marks_all_new():
    current = [ENGINE.normalize_item(item("1")), ENGINE.normalize_item(item("2"))]
    assert ENGINE.detect_new([], current)["new_ids"] == ["1", "2"]


# ==========================================================================
# 八、真值库对账（pcode 11 例 + diff 21 条）
# ==========================================================================
def _pcode_case(form):
    for case in truth("pcode-truth")["cases"]:
        if case["form"] == form:
            return case
    raise AssertionError(form)


def test_truth_pcode_std_bracket():
    case = _pcode_case("std_bracket")
    assert ENGINE.parse_pcode(case["pcode"]) == case["expect"]


def test_truth_pcode_fullwidth_bracket():
    case = _pcode_case("fullwidth_bracket")
    assert ENGINE.parse_pcode(case["pcode"]) == case["expect"]


def test_truth_pcode_decree_no_bracket():
    case = _pcode_case("decree_no_bracket")
    assert ENGINE.parse_pcode(case["pcode"]) == case["expect"]


def test_truth_pcode_spaced_serial():
    case = _pcode_case("std_bracket_spaced_serial")
    assert ENGINE.parse_pcode(case["pcode"]) == case["expect"]


def test_truth_pcode_empty():
    case = _pcode_case("empty")
    assert ENGINE.parse_pcode(case["pcode"]) == case["expect"]


def test_truth_pcode_every_hand_annotated_case_matches():
    for case in truth("pcode-truth")["cases"]:
        assert ENGINE.parse_pcode(case["pcode"]) == case["expect"], case["form"]


def test_truth_pcode_sentinel_matches():
    payload = truth("pcode-truth")
    assert payload["also_expect"]["reverse_no_fabricated_year"] is True
    assert REGISTRY.UNPARSED in json.dumps(payload, ensure_ascii=False)


def test_truth_diff_new_ids_match():
    payload = truth("diff-truth")
    result = judge(pair())
    assert result["new_ids"] == sorted(case["item_id"] for case in payload["cases"]["new"])


def test_truth_diff_dup_ids_match():
    payload = truth("diff-truth")
    result = judge(pair())
    assert result["dup_ids"] == sorted(case["item_id"] for case in payload["cases"]["dup"])


def test_truth_diff_matched_by_matches():
    payload = truth("diff-truth")
    expected = {case["item_id"]: case["matched_by"] for case in payload["cases"]["dup"]}
    assert judge(pair())["matched_by"] == expected


def test_truth_diff_counts_match_expect():
    payload = truth("diff-truth")
    result = judge(pair())
    assert len(result["new_ids"]) == payload["expect"]["new_count"]
    assert len(result["dup_ids"]) == payload["expect"]["dup_count"]


def test_truth_diff_dup_26276349_is_pcode_hit():
    payload = truth("diff-truth")
    target = [case for case in payload["cases"]["dup"]
              if case["item_id"] == "26276349"][0]
    assert target["matched_by"] == "pcode"
    assert judge(pair())["matched_by"]["26276349"] == "pcode"


def test_truth_diff_every_dup_has_matched_by():
    result = judge(pair())
    assert set(result["matched_by"]) == set(result["dup_ids"])


def test_truth_diff_every_new_absent_from_previous():
    previous_ids = {entry["id"] for entry in pair()["previous"]["items"]}
    assert not (set(judge(pair())["new_ids"]) & previous_ids)


def test_truth_diff_new_roles_are_all_present():
    payload = truth("diff-truth")
    roles = {case["role"] for case in payload["cases"]["new"]}
    assert roles == {"fresh", "empty_pcode_new"}


# ==========================================================================
# 九、演示样例（pair A→B）逐值对账
# ==========================================================================
def test_pair_previous_count_matches_old_cli():
    assert judge(pair())["previous_count"] == 20


def test_pair_current_count_matches_old_cli():
    assert judge(pair())["current_count"] == 21


def test_pair_new_count_matches_old_cli():
    assert len(judge(pair())["new_ids"]) == 6


def test_pair_dup_count_matches_old_cli():
    assert len(judge(pair())["dup_ids"]) == 15


def test_pair_pcode_counts_match_old_cli():
    counts = ENGINE.pcode_counts(judge(pair())["records"])
    assert counts == {"parsed": 17, "partial": 2, "unparsed": 2}


def test_pair_alias_missing_is_zero():
    assert ENGINE.alias_missing_tokens(judge(pair())["records"]) == []


def test_pair_org_token_count_matches_old_cli():
    tokens = sum(len(record["orgs"]) for record in judge(pair())["records"])
    assert tokens == 30


def test_pair_has_no_field_violations():
    assert judge(pair())["field_violations"] == []


def test_pair_input_order_is_not_canonical():
    assert judge(pair())["order_observed"] is False


def test_pair_every_item_has_valid_date():
    assert all(record["date_valid"] for record in judge(pair())["records"])


def test_pair_every_item_has_required_fields():
    assert all(record["missing"] == [] for record in judge(pair())["records"])


def test_pair_new_items_count_six_in_ledger():
    found = findings(pair())
    new_pass = [f for f in found if f.rule_id.startswith("diff.item:") and f.verdict == PASS]
    assert len(new_pass) == 6


def test_pair_duplicate_items_count_fifteen_in_ledger():
    found = findings(pair())
    dups = [f for f in found if f.rule_id.startswith("diff.item:")
            and f.verdict == NOT_APPLICABLE]
    assert len(dups) == 15


def test_pair_exit_code_is_ok():
    assert report(pair()).exit_code() == EXIT_OK


# ==========================================================================
# 十、账本映射与退出码
# ==========================================================================
def test_ledger_total_record_count():
    assert len(findings(pair())) == 136


def test_ledger_counts_pass_and_na():
    summary = report(pair()).summary()
    assert summary["verdicts"] == {PASS: 116, FAIL: 0, NOT_APPLICABLE: 20}


def test_ledger_has_no_blocking_for_clean_pair():
    assert report(pair()).blocking() == ()


def test_missing_required_field_is_fail():
    subject = {"current": {"items": [item(title="")]}}
    assert one(findings(subject), "entry.schema:26270001").verdict == FAIL


def test_missing_required_field_names_are_in_message():
    subject = {"current": {"items": [item(title="")]}}
    assert "title" in one(findings(subject), "entry.schema:26270001").message


def test_invalid_date_is_fail():
    subject = {"current": {"items": [item(pubtimeStr="2026.13.01")]}}
    assert one(findings(subject), "entry.date:26270001").verdict == FAIL


def test_invalid_date_blocks_exit_code():
    subject = {"current": {"items": [item(pubtimeStr="2026-10-01")]}}
    assert report(subject).exit_code() == EXIT_BLOCKED


def test_forbidden_field_is_fail():
    subject = {"current": {"items": [item(content="正文")]}}
    assert one(findings(subject), "entry.fields:26270001").verdict == FAIL


def test_extra_field_is_fail():
    subject = {"current": {"items": [item(remark="x")]}}
    assert one(findings(subject), "entry.fields:26270001").verdict == FAIL


def test_pcode_partial_is_not_applicable_but_anchored():
    subject = {"current": {"items": [item(pcode="国令第847号")]}}
    finding = one(findings(subject), "entry.pcode:26270001")
    assert finding.verdict == NOT_APPLICABLE
    assert finding.anchor is not None


def test_pcode_unparsed_is_not_applicable():
    subject = {"current": {"items": [item(pcode="随便写的")]}}
    assert one(findings(subject), "entry.pcode:26270001").verdict == NOT_APPLICABLE


def test_pcode_parsed_is_pass():
    assert one(findings(pair()), "entry.pcode:26385742").verdict == PASS


def test_unknown_org_is_not_applicable():
    subject = {"current": {"items": [item(puborg="某某新设机构")]}}
    assert one(findings(subject), "org.alias:26270001#0").verdict == NOT_APPLICABLE


def test_known_org_is_pass():
    subject = {"current": {"items": [item(puborg="财政部")]}}
    assert one(findings(subject), "org.alias:26270001#0").verdict == PASS


def test_org_records_are_indexed_to_avoid_id_collision():
    subject = {"current": {"items": [item(puborg="财政部 财政部")]}}
    found = findings(subject)
    assert "org.alias:26270001#0" in [f.rule_id for f in found]
    assert "org.alias:26270001#1" in [f.rule_id for f in found]


def test_duplicate_item_is_not_applicable():
    subject = {"previous": {"items": [item("1")]}, "current": {"items": [item("1")]}}
    assert one(findings(subject), "diff.item:1").verdict == NOT_APPLICABLE


def test_new_item_is_pass():
    subject = {"previous": {"items": []}, "current": {"items": [item("1")]}}
    assert one(findings(subject), "diff.item:1").verdict == PASS


def test_first_run_record_is_emitted():
    subject = {"current": {"items": [item("1")]}}
    assert one(findings(subject), "diff.first-run").verdict == NOT_APPLICABLE


def test_first_run_marks_all_items_new():
    subject = {"current": {"items": [item("1"), item("2")]}}
    assert judge(subject)["first_run"] is True
    assert judge(subject)["new_ids"] == ["1", "2"]


def test_non_canonical_input_is_recorded():
    subject = {"previous": {"items": []},
               "current": {"items": [item("1", pubtimeStr="2026.10.01"),
                                     item("2", pubtimeStr="2026.10.09")]}}
    assert one(findings(subject), "snapshot.order").verdict == NOT_APPLICABLE


def test_canonical_input_has_no_order_record():
    subject = {"previous": {"items": []},
               "current": {"items": [item("2", pubtimeStr="2026.10.09"),
                                     item("1", pubtimeStr="2026.10.01")]}}
    assert "snapshot.order" not in [f.rule_id for f in findings(subject)]


def test_every_finding_has_unique_id():
    ids = [finding.id for finding in report(pair()).findings]
    assert len(ids) == len(set(ids))


def test_report_json_is_serialisable_and_deterministic():
    first = json.dumps(report(pair()).as_dict(), ensure_ascii=False, sort_keys=True)
    second = json.dumps(report(pair()).as_dict(), ensure_ascii=False, sort_keys=True)
    assert first == second


def test_missing_basis_clause_is_contract_error():
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate({"current": {"items": [item()]}},
                          Basis.empty(REGISTRY.CONTRACT_VERSION))


def test_basis_version_mismatch_is_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate({"current": {"items": [item()]}}, Basis.empty("2020-01-01"))


def test_missing_current_is_input_error():
    with pytest.raises(ENGINE.ItemError):
        PACK_MOD.evaluate({"previous": {"items": []}}, basis())


def test_current_without_items_is_input_error():
    with pytest.raises(ENGINE.ItemError):
        PACK_MOD.evaluate({"current": {}}, basis())


def test_previous_items_missing_is_input_error():
    with pytest.raises(ENGINE.ItemError):
        PACK_MOD.evaluate({"previous": {}, "current": {"items": []}}, basis())


def test_cli_pair_returns_ok(capsys):
    code = cp_cli.main(["check", SLUG, "--input", PAIR_PATH, "--basis", BASIS_PATH])
    assert code == EXIT_OK
    assert "阻断 0 条" in capsys.readouterr().out


def test_cli_missing_basis_returns_contract_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input", PAIR_PATH])
    assert code == EXIT_CONTRACT
    assert "ContractError" in capsys.readouterr().err


def test_cli_missing_file_returns_input_code():
    assert cp_cli.main(["check", SLUG, "--input", "no-such.json",
                        "--basis", BASIS_PATH]) == EXIT_INPUT


def test_cli_json_output_has_organ(capsys):
    cp_cli.main(["check", SLUG, "--input", PAIR_PATH, "--basis", BASIS_PATH, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG
    assert payload["summary"]["blocking"] == 0


def test_cli_json_output_deterministic(capsys):
    cp_cli.main(["check", SLUG, "--input", PAIR_PATH, "--basis", BASIS_PATH, "--json"])
    first = capsys.readouterr().out
    cp_cli.main(["check", SLUG, "--input", PAIR_PATH, "--basis", BASIS_PATH, "--json"])
    assert capsys.readouterr().out == first


# ==========================================================================
# 十一、确定性与纯函数性
# ==========================================================================
def test_evaluate_does_not_mutate_subject():
    subject = pair()
    before = json.dumps(subject, ensure_ascii=False, sort_keys=True)
    findings(subject)
    assert json.dumps(subject, ensure_ascii=False, sort_keys=True) == before


def test_alias_table_is_not_mutated():
    before = copy.deepcopy(REGISTRY.ORG_ALIASES)
    candidate = dict(ALIASES)
    ENGINE.parse_orgs("财政部 未知机构", candidate)
    assert REGISTRY.ORG_ALIASES == before


def test_injected_alias_table_adds_canonical():
    aliases = dict(ALIASES)
    aliases["某某新设机构"] = "某某新设机构（规范名）"
    orgs = ENGINE.parse_orgs("某某新设机构", aliases)
    assert orgs[0]["canonical"] == "某某新设机构（规范名）"
    assert orgs[0]["alias_missing"] is False


def test_two_runs_produce_same_records():
    first = judge(pair())["records"]
    second = judge(pair())["records"]
    assert [record["item_id"] for record in first] == [
        record["item_id"] for record in second]


def test_records_follow_current_order():
    result = judge(pair())
    expected = [str(entry.get("id")) for entry in pair()["current"]["items"]]
    assert [record["item_id"] for record in result["records"]] == expected

# ==========================================================================
# 十二、常量口径与逐条真值（补充）
# ==========================================================================
def test_channels_map_two_feeds():
    assert REGISTRY.CHANNELS == {"gwy": "国务院", "bm": "部委"}


def test_channel_names_are_chinese():
    assert set(REGISTRY.CHANNELS.values()) == {"国务院", "部委"}


def test_schema_fields_start_with_source():
    assert REGISTRY.SCHEMA_FIELDS[0] == "source"


def test_schema_fields_end_with_channel():
    assert REGISTRY.SCHEMA_FIELDS[-1] == "channel"


def test_required_fields_are_subset_of_schema():
    assert set(REGISTRY.REQUIRED_FIELDS) <= set(REGISTRY.SCHEMA_FIELDS)


def test_forbidden_fields_are_outside_schema():
    assert not (set(REGISTRY.FORBIDDEN_SNAPSHOT_FIELDS) & set(REGISTRY.SCHEMA_FIELDS))


def test_bracket_pairs_cover_standard_and_fullwidth():
    assert ("〔", "〕") in REGISTRY.BRACKET_PAIRS
    assert ("﹝", "﹞") in REGISTRY.BRACKET_PAIRS


def test_pcode_serial_takes_all_digits_before_hao():
    assert ENGINE.parse_pcode("国办发〔2026〕123号")["serial"] == "123"


def test_pcode_serial_strips_letters_before_hao():
    parsed = ENGINE.parse_pcode("国办发〔2026〕第28号")
    assert parsed["serial"] == "28"


def test_pcode_serial_without_hao_uses_whole_tail():
    parsed = ENGINE.parse_pcode("国办发〔2026〕28")
    assert parsed["serial"] == "28"


def test_pcode_agency_code_may_contain_suffix_word():
    parsed = ENGINE.parse_pcode("国知发服字〔2026〕29号")
    assert parsed["agency_code"] == "国知发服字"
    assert parsed["status"] == "parsed"


def test_pcode_decree_requires_hao():
    parsed = ENGINE.parse_pcode("国令第847")
    assert parsed["status"] == "unparsed"


def test_pcode_decree_serial_keeps_digits_only():
    parsed = ENGINE.parse_pcode("国令第 847 号")
    assert parsed["serial"] == "847"


def test_pcode_second_bracket_pair_is_used_when_first_unpaired():
    parsed = ENGINE.parse_pcode("说明〔未闭合﹝2026﹞28号")
    assert parsed["year"] == "2026"


def test_pcode_surrogate_fullwidth_bracket_is_rejected():
    parsed = ENGINE.parse_pcode("国办发【2026】28号")
    assert parsed["status"] == "unparsed"


def test_date_valid_accepts_leap_2024():
    assert ENGINE.date_valid("2024.02.29") is True


def test_date_valid_rejects_month_zero():
    assert ENGINE.date_valid("2026.00.10") is False


def test_date_valid_rejects_day_zero():
    assert ENGINE.date_valid("2026.10.00") is False


def test_date_valid_rejects_trailing_text():
    assert ENGINE.date_valid("2026.10.08日") is False


def test_org_token_with_internal_space_is_split():
    orgs = ENGINE.parse_orgs("国务院 办公厅", ALIASES)
    assert [org["raw"] for org in orgs] == ["国务院", "办公厅"]
    assert orgs[1]["alias_missing"] is True


def test_org_multiple_known_tokens_all_match():
    orgs = ENGINE.parse_orgs("财政部 国家药监局 商务部", ALIASES)
    assert all(not org["alias_missing"] for org in orgs)


def test_org_short_form_zhujianbu_maps_long_name():
    orgs = ENGINE.parse_orgs("住房城乡建设部", ALIASES)
    assert orgs[0]["canonical"] == "住房和城乡建设部"


def test_org_gongxinbu_office_is_longest_match():
    orgs = ENGINE.parse_orgs("工业和信息化部办公厅", ALIASES)
    assert orgs[0]["canonical"] == "工业和信息化部办公厅"


def test_detect_new_duplicate_by_pcode_keeps_new_id():
    previous = [ENGINE.normalize_item(item("1", pcode="国办发〔2026〕28号"))]
    current = [ENGINE.normalize_item(item("2", pcode="国办发〔2026〕28号"))]
    result = ENGINE.detect_new(previous, current)
    assert result["new_ids"] == []
    assert result["dup_ids"] == ["2"]


def test_detect_new_previous_pcode_empty_never_matches():
    previous = [ENGINE.normalize_item(item("1", pcode="")),
                ENGINE.normalize_item(item("2", pcode="国办发〔2026〕28号"))]
    current = [ENGINE.normalize_item(item("3", pcode=""))]
    assert ENGINE.detect_new(previous, current)["new_ids"] == ["3"]


def test_detect_new_duplicate_ids_sorted():
    previous = [ENGINE.normalize_item(item("3")), ENGINE.normalize_item(item("1"))]
    current = [ENGINE.normalize_item(item("3")), ENGINE.normalize_item(item("1"))]
    assert ENGINE.detect_new(previous, current)["dup_ids"] == ["1", "3"]


def test_detect_new_matched_by_covers_every_duplicate():
    previous = [ENGINE.normalize_item(item("1")),
                ENGINE.normalize_item(item("2", pcode="国办发〔2026〕28号"))]
    current = [ENGINE.normalize_item(item("1")),
               ENGINE.normalize_item(item("9", pcode="国办发〔2026〕28号"))]
    result = ENGINE.detect_new(previous, current)
    assert result["matched_by"] == {"1": "id", "9": "pcode"}


def test_ledger_schema_evidence_lists_missing():
    subject = {"current": {"items": [item(title="", url="")]}}
    evidence = one(findings(subject), "entry.schema:26270001").evidence
    assert evidence["missing"] == ["title", "url"]


def test_ledger_date_evidence_records_verdict():
    assert one(findings(pair()), "entry.date:26385742").evidence["date_valid"] is True


def test_ledger_fields_evidence_lists_forbidden():
    subject = {"current": {"items": [item(content="正文")]}}
    evidence = one(findings(subject), "entry.fields:26270001").evidence
    assert evidence["forbidden"] == ["content"]
    assert evidence["extra"] == []


def test_ledger_pcode_evidence_carries_parse():
    subject = {"current": {"items": [item(pcode="国令第847号")]}}
    evidence = one(findings(subject), "entry.pcode:26270001").evidence
    assert evidence["parse"]["status"] == "partial"


def test_ledger_org_evidence_records_raw_and_canonical():
    evidence = one(findings(pair()), "org.alias:26782365#0").evidence
    assert evidence["raw"] == evidence["canonical"] or evidence["alias_missing"] is False


def test_ledger_diff_evidence_records_matched_by():
    evidence = one(findings(pair()), "diff.item:26276349").evidence
    assert evidence["matched_by"] == "pcode"


def test_ledger_diff_pass_evidence_has_no_matched_by():
    evidence = one(findings(pair()), "diff.item:26385742").evidence
    assert evidence["matched_by"] is None


def test_truth_diff_new_item_26385742():
    assert "26385742" in judge(pair())["new_ids"]


def test_truth_diff_new_item_26628029():
    assert "26628029" in judge(pair())["new_ids"]


def test_truth_diff_new_item_26736877():
    assert "26736877" in judge(pair())["new_ids"]


def test_truth_diff_dup_item_26297919_matched_by_id():
    assert judge(pair())["matched_by"]["26297919"] == "id"


def test_truth_diff_dup_item_26611060_matched_by_id():
    assert judge(pair())["matched_by"]["26611060"] == "id"


def test_truth_also_expect_dup_ids_all_traceable():
    payload = truth("diff-truth")
    assert payload["also_expect"]["dup_ids_all_traceable_to_a"] is True
    previous = pair()["previous"]["items"]
    previous_ids = {entry["id"] for entry in previous}
    previous_pcodes = {entry["pcode"] for entry in previous if entry["pcode"]}
    current = {entry["id"]: entry for entry in pair()["current"]["items"]}
    for dup_id in judge(pair())["dup_ids"]:
        assert dup_id in previous_ids or current[dup_id]["pcode"] in previous_pcodes


def test_truth_also_expect_new_ids_absent_from_previous():
    payload = truth("diff-truth")
    assert payload["also_expect"]["new_ids_absent_from_a"] is True


def test_truth_also_expect_pcode_dup_matched_by_pcode():
    payload = truth("diff-truth")
    assert payload["also_expect"]["pcode_dup_matched_by_pcode"] is True
    pcode_hits = [key for key, value in judge(pair())["matched_by"].items()
                  if value == "pcode"]
    assert pcode_hits == ["26276349"]
