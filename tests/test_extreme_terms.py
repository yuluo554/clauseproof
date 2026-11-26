"""器官 ``extreme-terms`` 无损判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在「判定结果」上。
来源仓判定层（D1 + D18 机械选 5 文件 / 实跑 50 passed / AST 函数 50）逐文件处置见
``docs/extreme-terms.md`` §6。

本文件同时是**漂移门**：``data/wordlists.json`` 与 ``registry.WORD_ENTRIES``（词面 /
类别 / 风险 / 建议 / 锚点 / 依据类型）、``data/clauses.json`` 与来源法条冻结件必须逐条一致。
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

PACK_MOD = importlib.import_module("clauseproof.packs.extreme-terms")
ENGINE = importlib.import_module("clauseproof.packs.extreme-terms.engine")
REGISTRY = importlib.import_module("clauseproof.packs.extreme-terms.registry")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "extreme-terms")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "extreme-terms")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
README_CASE = os.path.join(SAMPLES, "readme-example.json")
MULTI_CASE = os.path.join(SAMPLES, "multi-category.json")
CLEAN_CASE = os.path.join(SAMPLES, "clean.json")


def basis():
    return Basis.from_json(BASIS_PATH)


def wordlists():
    with open(os.path.join(DATA_DIR, "wordlists.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)["wordlists"]


def source_entries():
    rows = []
    payload = wordlists()
    for name in REGISTRY.WORDLIST_FILES:
        for entry in payload[name]["entries"]:
            rows.append((name, entry))
    return rows


def active():
    return ENGINE.load_entries(basis())["active"]


def scan(text, window=10):
    return ENGINE.scan_text(text, active(), window)


def findings(subject, words=None):
    return tuple(PACK_MOD.evaluate_with_words(subject, basis(), words))


def one(found, rule_id):
    hits = [finding for finding in found if finding.rule_id == rule_id]
    assert len(hits) == 1, (rule_id, [f.rule_id for f in found])
    return hits[0]


def report(subject):
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.ORG_VERSION,
                  subject="text.json", findings=findings(subject))


def _read(name):
    with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
        return handle.read()


def _sample(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


# ==========================================================================
# 一、器官契约与装配
# ==========================================================================
def test_pack_is_registered_under_slug():
    pack = get(SLUG)
    assert isinstance(pack, Pack)
    assert pack.slug == SLUG
    assert pack.version == PACK_MOD.ORG_VERSION


def test_pack_version_matches_source_release():
    assert PACK_MOD.ORG_VERSION == "0.0.1"


def test_pack_declares_text_as_required_field():
    assert get(SLUG).input_fields == ("text",)


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


def test_pack_has_no_network_clock_or_llm_imports():
    banned = ("time", "datetime", "random", "socket", "urllib", "requests", "http",
              "openai", "anthropic")
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


def test_engine_has_no_word_literals():
    """词面只在 registry：engine 不得出现词表里的任何词面。"""
    source = _read("engine.py")
    words = sorted({word for word, *_rest in REGISTRY.WORD_ENTRIES}, key=len, reverse=True)
    assert not [word for word in words if word in source]


def test_evaluate_signature_is_fixed():
    import inspect

    assert list(inspect.signature(PACK_MOD.evaluate).parameters) == ["subject", "basis"]


def test_registry_declares_five_risk_free_knobs():
    assert REGISTRY.CONTEXT_WINDOW == 10
    assert REGISTRY.RISK_LEVELS == ("high", "medium", "low")
    assert REGISTRY.ANCHOR_BASES == ("literal", "variant")
    assert REGISTRY.STATUS_VERIFIED == "verified"


def test_registry_wordlist_files_are_four():
    assert REGISTRY.WORDLIST_FILES == ("absolute-terms", "health-food", "industry", "medical")


# ==========================================================================
# 二、词表漂移门（133 条）
# ==========================================================================
def test_wordlist_total_is_133():
    assert len(REGISTRY.WORD_ENTRIES) == 133
    assert sum(len(wordlists()[name]["entries"]) for name in REGISTRY.WORDLIST_FILES) == 133


def test_wordlist_absolute_terms_count():
    assert sum(1 for entry in source_entries() if entry[0] == "absolute-terms") == 50


def test_wordlist_health_food_count():
    assert sum(1 for entry in source_entries() if entry[0] == "health-food") == 22


def test_wordlist_industry_count():
    assert sum(1 for entry in source_entries() if entry[0] == "industry") == 47


def test_wordlist_medical_count():
    assert sum(1 for entry in source_entries() if entry[0] == "medical") == 14


def test_every_word_matches_source():
    expected = [entry["word"] for _name, entry in source_entries()]
    assert [row[0] for row in REGISTRY.WORD_ENTRIES] == expected


def test_every_category_matches_source():
    expected = [entry["category"] for _name, entry in source_entries()]
    assert [row[1] for row in REGISTRY.WORD_ENTRIES] == expected


def test_every_risk_matches_source():
    expected = [entry["risk"] for _name, entry in source_entries()]
    assert [row[2] for row in REGISTRY.WORD_ENTRIES] == expected


def test_every_suggestion_matches_source():
    expected = [entry["suggestion"] for _name, entry in source_entries()]
    assert [row[3] for row in REGISTRY.WORD_ENTRIES] == expected


def test_every_clause_id_matches_source_anchor():
    expected = ["%s:%s" % (entry["anchor"]["doc"], entry["anchor"]["clause"])
                for _name, entry in source_entries()]
    assert [row[4] for row in REGISTRY.WORD_ENTRIES] == expected


def test_every_basis_matches_source():
    expected = [entry["anchor"]["basis"] for _name, entry in source_entries()]
    assert [row[5] for row in REGISTRY.WORD_ENTRIES] == expected


def test_every_status_is_verified_in_source():
    assert {entry["status"] for _name, entry in source_entries()} == {"verified"}


def test_risk_values_are_declared_levels():
    assert {row[2] for row in REGISTRY.WORD_ENTRIES} <= set(REGISTRY.RISK_LEVELS)


def test_category_values_are_four():
    assert {row[1] for row in REGISTRY.WORD_ENTRIES} == {
        "绝对化用语", "保健食品违禁", "行业违禁", "医疗违禁"}


def test_word_entries_are_unique():
    words = [row[0] for row in REGISTRY.WORD_ENTRIES]
    assert len(words) == len(set(words))


def test_clause_ids_are_all_in_path_map():
    for row in REGISTRY.WORD_ENTRIES:
        assert row[4] in REGISTRY.CLAUSE_PATHS, row[0]


def test_literal_entries_appear_verbatim_in_clause_text():
    """basis=literal 的词条必须在条款原文里逐字出现（加载侧核一次，这里再核一次）。"""
    catalog = basis()
    for word, _category, _risk, _suggestion, clause_id, kind in REGISTRY.WORD_ENTRIES:
        if kind != "literal":
            continue
        assert word in catalog.clause(clause_id).text, word


def test_literal_entry_count_is_twelve():
    """literal 12 条：第九条 3 / 第十八条 2 / 第二十五条 3 / 第十七条 1 / 医疗办法第七条 3。"""
    assert sum(1 for row in REGISTRY.WORD_ENTRIES if row[5] == "literal") == 12


def test_variant_entry_count_is_121():
    assert sum(1 for row in REGISTRY.WORD_ENTRIES if row[5] == "variant") == 121


# ==========================================================================
# 三、条文库（法条原文锚点）
# ==========================================================================
def test_clauses_version_matches_wordlist_snapshot():
    assert basis().version == REGISTRY.VERSION == "2026-10-15"


def test_clauses_have_seven_entries():
    assert len(basis()) == 7


def test_clauses_cover_every_spec():
    assert set(basis().clause_ids()) == {cid for cid, _path in REGISTRY.clause_specs()}


def test_clause_paths_name_the_instruments():
    assert basis().clause("advertising-law:第九条").path == "《中华人民共和国广告法》 / 第九条"
    assert basis().clause("medical-ad-measures:第七条").path == "《医疗广告管理办法》 / 第七条"


def test_advertising_law_clause_contains_prohibited_list():
    text = basis().clause("advertising-law:第九条").text
    assert "广告不得有下列情形" in text


def test_medical_ad_clause_is_present():
    assert basis().clause("medical-ad-measures:第七条").text


def test_contract_clause_text_matches_registry():
    assert basis().clause(REGISTRY.CLAUSE_WORDLIST).text == REGISTRY.clause_text(
        REGISTRY.CLAUSE_WORDLIST)


def test_contract_clause_path_is_data_contract():
    assert basis().clause(REGISTRY.CLAUSE_WORDLIST).path.startswith("数据契约 / ")


def test_clause_texts_are_non_empty():
    for clause_id in basis().clause_ids():
        assert basis().clause(clause_id).text.strip(), clause_id


# ==========================================================================
# 四、文本归一
# ==========================================================================
def test_normalize_strips_bom():
    assert ENGINE.normalize_text("\ufeff文案") == "文案"


def test_normalize_crlf_to_lf():
    assert ENGINE.normalize_text("a\r\nb") == "a\nb"


def test_normalize_cr_to_lf():
    assert ENGINE.normalize_text("a\rb") == "a\nb"


def test_normalize_keeps_lf():
    assert ENGINE.normalize_text("a\nb") == "a\nb"


def test_normalize_rejects_non_string():
    with pytest.raises(ENGINE.InputError):
        ENGINE.normalize_text(["文案"])


def test_normalize_keeps_inner_spaces():
    assert ENGINE.normalize_text("a  b") == "a  b"


# ==========================================================================
# 五、词条门控（四步）
# ==========================================================================
def test_all_packaged_entries_are_active():
    gated = ENGINE.load_entries(basis())
    assert len(gated["active"]) == 133
    assert gated["inactive"] == []


def test_gate_rejects_unverified_status():
    words = [{"word": "测试词", "category": "绝对化用语", "risk": "high",
              "suggestion": "删", "clause_id": "advertising-law:第九条",
              "basis": "variant", "status": "pending"}]
    gated = ENGINE.load_entries(basis(), words)
    assert gated["active"] == []
    assert gated["inactive"][0]["reason"] == "status 非 verified"


def test_gate_rejects_missing_anchor():
    words = [{"word": "测试词", "category": "绝对化用语", "risk": "high",
              "suggestion": "删", "clause_id": "", "basis": "variant",
              "status": "verified"}]
    assert ENGINE.load_entries(basis(), words)["inactive"][0]["reason"] == "缺锚点"


def test_gate_rejects_clause_absent_from_basis():
    words = [{"word": "测试词", "category": "绝对化用语", "risk": "high",
              "suggestion": "删", "clause_id": "advertising-law:第九十九条",
              "basis": "variant", "status": "verified"}]
    reason = ENGINE.load_entries(basis(), words)["inactive"][0]["reason"]
    assert reason.startswith("锚点条款不在条文库")


def test_gate_rejects_unregistered_basis_kind():
    words = [{"word": "测试词", "category": "绝对化用语", "risk": "high",
              "suggestion": "删", "clause_id": "advertising-law:第九条",
              "basis": "official", "status": "verified"}]
    reason = ENGINE.load_entries(basis(), words)["inactive"][0]["reason"]
    assert "锚点依据类型未登记" in reason


def test_gate_rejects_literal_word_absent_from_clause():
    words = [{"word": "此词不在原文里", "category": "绝对化用语", "risk": "high",
              "suggestion": "删", "clause_id": "advertising-law:第九条",
              "basis": "literal", "status": "verified"}]
    reason = ENGINE.load_entries(basis(), words)["inactive"][0]["reason"]
    assert reason.startswith("literal 词面未见于条款原文")


def test_gate_accepts_literal_word_present_in_clause():
    words = [{"word": "最高级", "category": "绝对化用语", "risk": "high",
              "suggestion": "删", "clause_id": "advertising-law:第九条",
              "basis": "literal", "status": "verified"}]
    assert len(ENGINE.load_entries(basis(), words)["active"]) == 1


def test_gate_accepts_variant_word_absent_from_clause():
    words = [{"word": "此词只是变体", "category": "绝对化用语", "risk": "high",
              "suggestion": "删", "clause_id": "advertising-law:第九条",
              "basis": "variant", "status": "verified"}]
    assert len(ENGINE.load_entries(basis(), words)["active"]) == 1


def test_gate_active_entry_carries_clause_id():
    entry = ENGINE.load_entries(basis())["active"][0]
    assert entry["clause_id"].startswith("advertising-law:")


# ==========================================================================
# 六、扫描语义
# ==========================================================================
def test_scan_readme_example_hits_sales_first():
    hits = scan("本款产品是全效之王，销量第一。")
    assert [(hit["word"], hit["line"], hit["col"]) for hit in hits] == [("销量第一", 1, 11)]


def test_scan_longest_first_beats_prefix():
    hits = scan("第一品牌")
    assert [hit["word"] for hit in hits] == ["第一品牌"]


def test_scan_longest_first_second_pair():
    hits = scan("最优")
    assert [hit["word"] for hit in hits] == ["最优"]


def test_scan_longest_first_third_pair():
    hits = scan("疗效显著")
    assert [hit["word"] for hit in hits] == ["疗效显著"]


def test_scan_suffix_word_is_matched_as_longest():
    hits = scan("全国第一")
    assert [hit["word"] for hit in hits] == ["全国第一"]


def test_scan_non_overlapping_advances_past_hit():
    hits = scan("第一第一")
    assert [(hit["word"], hit["col"]) for hit in hits] == [("第一", 1), ("第一", 3)]


def test_scan_no_hit_on_clean_text():
    assert scan("本产品采用食品级原料，净含量 500 克，常温保存。") == []


def test_scan_hit_carries_seven_contract_fields():
    hit = scan("绝对安全。")[0]
    assert list(hit) == ["word", "category", "risk", "line", "col", "context", "suggestion"]


def test_scan_hit_col_is_one_based():
    assert scan("绝对")[0]["col"] == 1


def test_scan_hit_context_contains_word():
    hit = scan("前文绝对后文")[0]
    assert hit["word"] in hit["context"]


def test_scan_context_window_is_configurable():
    hit = scan("0123456789绝对9876543210", window=2)[0]
    assert hit["context"] == "89绝对98"


def test_scan_context_window_zero_is_exact_word():
    assert scan("前绝对后", window=0)[0]["context"] == "绝对"


def test_scan_counts_each_line_separately():
    hits = scan("绝对\n销量第一")
    assert [(hit["line"], hit["col"], hit["word"]) for hit in hits] == [
        (1, 1, "绝对"), (2, 1, "销量第一")]


def test_scan_accepts_crlf_via_normalization():
    text = ENGINE.normalize_text("绝对\r\n销量第一")
    assert [hit["line"] for hit in ENGINE.scan_text(text, active())] == [1, 2]


def test_scan_empty_text_has_no_hits():
    assert scan("") == []


def test_scan_whitespace_text_has_no_hits():
    assert scan("   \n\t\n") == []


def test_scan_negative_window_is_input_error():
    with pytest.raises(ENGINE.InputError):
        ENGINE.scan_text("绝对", active(), -1)


def test_scan_sort_order_is_line_then_col():
    hits = scan("绝对\n国家级")
    assert [(hit["line"], hit["col"]) for hit in hits] == [(1, 1), (2, 1)]


def test_scan_ignores_words_beyond_wordlist():
    assert scan("这是一段普通文案") == []


def test_scan_finds_two_categories_in_one_line():
    hits = scan("纯天然且根治")
    assert {hit["category"] for hit in hits} == {"保健食品违禁", "医疗违禁"}


def test_scan_reports_risk_level_from_wordlist():
    hit = scan("治愈")[0]
    assert hit["risk"] in REGISTRY.RISK_LEVELS


def test_scan_suggestion_comes_from_wordlist_field():
    hit = scan("绝对")[0]
    assert "删除" in hit["suggestion"]


def test_build_dfa_root_has_children():
    trie = ENGINE.build_dfa(active())
    assert isinstance(trie, tuple) and trie[0]


def test_build_dfa_terminal_holds_entry():
    entries = [{"word": "甲", "category": "绝对化用语", "risk": "high", "suggestion": "删"}]
    trie = ENGINE.build_dfa(entries)
    assert trie[0]["甲"][1][0][0] == "甲"


def test_scan_line_accepts_precompiled_trie():
    trie = ENGINE.build_dfa(active())
    assert [hit["word"] for hit in ENGINE.scan_line("绝对", trie, 1)] == ["绝对"]


# ==========================================================================
# 七、账本映射与退出码
# ==========================================================================
def test_readme_example_has_two_records():
    assert len(findings(_sample(README_CASE))) == 2


def test_readme_example_hit_is_fail_with_law_anchor():
    finding = one(findings(_sample(README_CASE)),
                  "term:绝对化用语:销量第一:L1C11")
    assert finding.verdict == FAIL
    assert finding.anchor.clause_id == "advertising-law:第九条"


def test_readme_example_summary_is_fail():
    assert one(findings(_sample(README_CASE)), "scan.result").verdict == FAIL


def test_readme_example_exit_code_is_blocked():
    assert report(_sample(README_CASE)).exit_code() == EXIT_BLOCKED


def test_clean_sample_has_single_pass_record():
    found = findings(_sample(CLEAN_CASE))
    assert len(found) == 1
    assert found[0].verdict == PASS


def test_clean_sample_exit_code_is_ok():
    assert report(_sample(CLEAN_CASE)).exit_code() == EXIT_OK


def test_multi_category_sample_hit_count():
    hits = [f for f in findings(_sample(MULTI_CASE)) if f.rule_id.startswith("term:")]
    assert len(hits) == 7


def test_multi_category_sample_all_hits_are_fail():
    hits = [f for f in findings(_sample(MULTI_CASE)) if f.rule_id.startswith("term:")]
    assert all(finding.verdict == FAIL for finding in hits)


def test_multi_category_sample_evidence_has_position():
    finding = one(findings(_sample(MULTI_CASE)), "term:绝对化用语:100%有效:L1C10")
    assert finding.evidence["line"] == 1
    assert finding.evidence["col"] == 10


def test_every_hit_finding_has_anchor():
    for finding in findings(_sample(MULTI_CASE)):
        if finding.rule_id.startswith("term:"):
            assert finding.anchor is not None, finding.rule_id


def test_inactive_entry_is_not_applicable_and_unanchored():
    words = [{"word": "待核对词", "category": "绝对化用语", "risk": "high",
              "suggestion": "删", "clause_id": "advertising-law:第九条",
              "basis": "variant", "status": "pending"}]
    finding = one(findings({"text": "待核对词"}, words), "term.inactive:待核对词")
    assert finding.verdict == NOT_APPLICABLE
    assert finding.anchor is None


def test_inactive_entry_reason_is_recorded():
    words = [{"word": "待核对词", "category": "绝对化用语", "risk": "high",
              "suggestion": "删", "clause_id": "", "basis": "variant",
              "status": "verified"}]
    evidence = one(findings({"text": "待核对词"}, words),
                   "term.inactive:待核对词").evidence
    assert evidence["reason"] == "缺锚点"


def test_inactive_word_is_not_scanned():
    words = [{"word": "待核对词", "category": "绝对化用语", "risk": "high",
              "suggestion": "删", "clause_id": "", "basis": "variant",
              "status": "verified"}]
    found = findings({"text": "待核对词"}, words)
    assert not [f for f in found if f.rule_id.startswith("term:")]


def test_inactive_entry_does_not_block():
    words = [{"word": "待核对词", "category": "绝对化用语", "risk": "high",
              "suggestion": "删", "clause_id": "", "basis": "variant",
              "status": "verified"}]
    report_ = Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.ORG_VERSION,
                     subject="text.json", findings=findings({"text": "普通文案"}, words))
    assert report_.exit_code() == EXIT_OK


def test_summary_evidence_counts_active_and_inactive():
    evidence = one(findings(_sample(CLEAN_CASE)), "scan.result").evidence
    assert evidence["active"] == 133
    assert evidence["inactive"] == 0
    assert evidence["hits"] == 0


def test_summary_evidence_risk_counts():
    evidence = one(findings(_sample(MULTI_CASE)), "scan.result").evidence
    assert evidence["risk_counts"] == {"high": 6, "medium": 1}


def test_finding_ids_are_unique():
    ids = [finding.id for finding in report(_sample(MULTI_CASE)).findings]
    assert len(ids) == len(set(ids))


def test_missing_text_is_input_error():
    with pytest.raises(ENGINE.InputError):
        PACK_MOD.evaluate({"context_window": 5}, basis())


def test_non_string_text_is_input_error():
    with pytest.raises(ENGINE.InputError):
        PACK_MOD.evaluate({"text": ["绝对"]}, basis())


def test_negative_window_in_subject_is_input_error():
    with pytest.raises(ENGINE.InputError):
        PACK_MOD.evaluate({"text": "绝对", "context_window": -1}, basis())


def test_bool_window_is_input_error():
    with pytest.raises(ENGINE.InputError):
        PACK_MOD.evaluate({"text": "绝对", "context_window": True}, basis())


def test_basis_version_mismatch_is_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate({"text": "绝对"}, Basis.empty("2020-01-01"))


def test_missing_contract_clause_is_basis_missing():
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate({"text": "绝对"}, Basis.empty(REGISTRY.VERSION))


def test_cli_readme_case_returns_blocked(capsys):
    code = cp_cli.main(["check", SLUG, "--input", README_CASE, "--basis", BASIS_PATH])
    assert code == EXIT_BLOCKED
    assert "阻断 2 条" in capsys.readouterr().out


def test_cli_clean_case_returns_ok(capsys):
    code = cp_cli.main(["check", SLUG, "--input", CLEAN_CASE, "--basis", BASIS_PATH])
    assert code == EXIT_OK
    assert "阻断 0 条" in capsys.readouterr().out


def test_cli_missing_basis_returns_input_code(capsys):
    """缺 --basis = 空条文库（版本 0）→ 版本不符 → ContractError → 3。"""
    code = cp_cli.main(["check", SLUG, "--input", README_CASE])
    assert code == EXIT_CONTRACT
    assert "ContractError" in capsys.readouterr().err


def test_cli_missing_file_returns_input_code():
    assert cp_cli.main(["check", SLUG, "--input", "no-such.json",
                        "--basis", BASIS_PATH]) == EXIT_INPUT


def test_cli_json_output_has_organ(capsys):
    cp_cli.main(["check", SLUG, "--input", README_CASE, "--basis", BASIS_PATH, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG
    assert payload["summary"]["blocking"] == 2


def test_cli_json_output_is_deterministic(capsys):
    cp_cli.main(["check", SLUG, "--input", MULTI_CASE, "--basis", BASIS_PATH, "--json"])
    first = capsys.readouterr().out
    cp_cli.main(["check", SLUG, "--input", MULTI_CASE, "--basis", BASIS_PATH, "--json"])
    assert capsys.readouterr().out == first


# ==========================================================================
# 八、确定性与纯函数性
# ==========================================================================
def test_evaluate_does_not_mutate_subject():
    subject = _sample(MULTI_CASE)
    before = json.dumps(subject, ensure_ascii=False, sort_keys=True)
    findings(subject)
    assert json.dumps(subject, ensure_ascii=False, sort_keys=True) == before


def test_word_entries_are_not_mutated():
    before = copy.deepcopy(REGISTRY.WORD_ENTRIES)
    findings(_sample(MULTI_CASE))
    assert REGISTRY.WORD_ENTRIES == before


def test_two_scans_are_identical():
    first = scan("绝对\n销量第一 国家级")
    second = scan("绝对\n销量第一 国家级")
    assert first == second


def test_hit_positions_are_stable_between_runs():
    positions = [(hit["word"], hit["line"], hit["col"]) for hit in scan("前绝对后销量第一")]
    assert positions == [("绝对", 1, 2), ("销量第一", 1, 5)]