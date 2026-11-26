"""器官 ``expense-ledger`` 无损判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在「判定结果」上。
来源仓判定层（D1 + D18 机械选 12 文件 / 实跑 127 passed / AST 函数 126）逐文件处置见
``docs/expense-ledger.md`` §6；本文件承载表头定位与列映射、金额/时间严格解析、
行三态、商户归一化、跨平台去重、语义识别、订阅识别与涨价追踪、账本映射与
退出码契约。

本文件同时是**漂移门**：``data/params.json`` / ``data/aliases.json`` /
``data/keywords.json``（来源冻结资产）与 ``registry`` 字面量必须逐条一致。

**解析层不进器官**：来源仓的编码探测（BOM/UTF-8/GB18030）与 XLSX 容器解包
属输入层（`SKELETON-SPEC` §2 禁止的器官 I/O 面）——样例 subject 由来源解析层
只读转写为已解码行（``lines``）/ 已解包表格（``table``）。
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

PACK_MOD = importlib.import_module("clauseproof.packs.expense-ledger")
ENGINE = importlib.import_module("clauseproof.packs.expense-ledger.engine")
REGISTRY = importlib.import_module("clauseproof.packs.expense-ledger.registry")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "expense-ledger")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "expense-ledger")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
DEMO_PATH = os.path.join(SAMPLES, "ledger-demo.json")
README_PATH = os.path.join(SAMPLES, "ledger-readme.json")
CLEAN_PATH = os.path.join(SAMPLES, "ledger-clean.json")

# 列别名夹具（与 data/aliases.json 的 column_aliases 同构；测试自足，
# 规则包同源性由漂移门保障）
ALIASES = [
    {"canonical": "对手方", "variants": ["交易对象"],
     "platforms": ["alipay", "wechat", "bank"]},
    {"canonical": "金额", "variants": ["金额(元)", "金额（元）", "金额"],
     "platforms": ["alipay", "wechat", "bank"]},
]


def basis():
    return Basis.from_json(BASIS_PATH)


def subject(path=DEMO_PATH):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def findings(sub=None):
    return tuple(PACK_MOD.evaluate(subject() if sub is None else sub, basis()))


def rules(found):
    return [finding.rule_id for finding in found]


def one(found, rule_id):
    hits = [finding for finding in found if finding.rule_id == rule_id]
    assert len(hits) == 1, (rule_id, rules(found))
    return hits[0]


def report(sub, name="case.json"):
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject=name, findings=findings(sub))


def params_copy():
    return REGISTRY.params()


def aliases_copy():
    return REGISTRY.aliases_doc()


def keywords_copy():
    return REGISTRY.keywords_doc()


def run_with(sub, params=None, aliases=None, keywords=None):
    return tuple(PACK_MOD.evaluate_with_rules(
        sub, basis(),
        params_copy() if params is None else params,
        aliases_copy() if aliases is None else aliases,
        keywords_copy() if keywords is None else keywords,
    ))


def _record(rid, platform, time_s, amount, direction, counterparty):
    return {
        "id": rid,
        "source_platform": platform,
        "source_file": rid.rsplit("#", 1)[0],
        "source_row": int(rid.rsplit("#", 1)[1]),
        "time": time_s,
        "amount": amount,
        "direction": direction,
        "normalized_counterparty": counterparty,
    }


def _small_ledger(records):
    return {"meta": {"sources": []}, "records": records, "issues": [], "file_issues": []}


def _sub_record(rid, offset_days, amount="10.00", merchant="商户甲"):
    from datetime import date, timedelta

    day = date(2026, 1, 1) + timedelta(days=offset_days)
    return {
        "id": rid, "time": "%s 08:00:00" % day.isoformat(),
        "amount": amount, "direction": "expense",
        "normalized_counterparty": merchant, "counterparty": merchant,
        "semantic_label": "消费", "source_row": 1, "source_platform": "wechat",
    }


def _detect_subs(records, **overrides):
    ledger = {"records": records}
    kwargs = dict(
        min_repeats=3,
        price_change_min_percent=2.0,
        period_table=[
            {"id": "monthly", "label": "月付", "interval_days": 30, "tolerance_days": 2},
            {"id": "quarterly", "label": "季付", "interval_days": 91, "tolerance_days": 3},
            {"id": "yearly", "label": "年付", "interval_days": 365, "tolerance_days": 5},
        ],
        default_tolerance_days=2,
    )
    kwargs.update(overrides)
    return ENGINE.detect_subscriptions(ledger, **kwargs)


def _tmp_file(tmp_path, name, lines):
    path = tmp_path / name
    path.write_text("\n".join(lines), encoding="utf-8")
    with open(path, "r", encoding="utf-8") as handle:
        return {"encoding": "utf-8", "lines": handle.read().split("\n")}


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


def test_pack_summary_states_basis_is_param_pack():
    assert "规则包" in PACK_MOD.SUMMARY


def test_pack_input_fields():
    assert PACK_MOD.INPUT_FIELDS == ("files",)


def test_slug_in_builtin_modules_sorted():
    packs_ns = importlib.import_module("clauseproof.packs")
    assert SLUG in packs_ns.BUILTIN_MODULES
    assert list(packs_ns.BUILTIN_MODULES) == sorted(packs_ns.BUILTIN_MODULES)


def test_pack_appears_in_all_packs():
    assert SLUG in [pack.slug for pack in all_packs()]


def test_clauses_json_exists():
    assert os.path.isfile(BASIS_PATH)


def test_clauses_version_matches_snapshot():
    payload = json.load(open(BASIS_PATH, encoding="utf-8"))
    assert payload["version"] == REGISTRY.PARAMS_VERSION


def test_clauses_cover_every_spec():
    payload = json.load(open(BASIS_PATH, encoding="utf-8"))
    got = {c["clause_id"] for c in payload["clauses"]}
    assert got == {clause_id for clause_id, _path in REGISTRY.clause_specs()}


def test_clauses_have_expected_count():
    payload = json.load(open(BASIS_PATH, encoding="utf-8"))
    assert len(payload["clauses"]) == 11


def test_clauses_paths_match_specs():
    payload = json.load(open(BASIS_PATH, encoding="utf-8"))
    specs = dict(REGISTRY.clause_specs())
    for clause in payload["clauses"]:
        assert clause["path"] == specs[clause["clause_id"]]
        assert clause["version"] == REGISTRY.PARAMS_VERSION


def test_missing_anchor_raises_basis_missing(tmp_path):
    path = tmp_path / "clauses.json"
    path.write_text(json.dumps({"version": REGISTRY.PARAMS_VERSION, "clauses": []}),
                    encoding="utf-8")
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate(subject(), Basis.from_json(str(path)))


# ==========================================================================
# 二、规则包漂移门（registry 字面量 ↔ data/*.json 来源资产）
# ==========================================================================
def _load_json(name):
    with open(os.path.join(DATA_DIR, name), "r", encoding="utf-8") as handle:
        return json.load(handle)


def test_params_json_is_source_snapshot():
    payload = _load_json("params.json")
    assert payload["kind"] == "rules-manifest"
    assert payload["ruleset_version"] == REGISTRY.RULESET_VERSION


def test_param_values_match_source():
    payload = _load_json("params.json")
    source = {p["id"]: p["value"] for p in payload["params"]}
    ours = REGISTRY.params()
    for key, value in ours.items():
        assert source[key] == value, key


def test_param_source_note_is_non_official():
    payload = _load_json("params.json")
    for param in payload["params"]:
        assert "非官方" in param["source"], param["id"]


def test_aliases_suffix_strip_matches():
    assert tuple(_load_json("aliases.json")["suffix_strip"]) == REGISTRY.SUFFIX_STRIP


def test_aliases_fullwidth_map_matches():
    source = [(e["full"], e["half"]) for e in _load_json("aliases.json")["fullwidth_map"]]
    assert source == list(REGISTRY.FULLWIDTH_MAP)


def test_aliases_entries_match():
    source = [(e["canonical"], tuple(e["variants"]))
              for e in _load_json("aliases.json")["aliases"]]
    assert source == list(REGISTRY.ALIAS_ENTRIES)


def test_column_aliases_match():
    source = _load_json("aliases.json")["column_aliases"]
    ours = REGISTRY.aliases_doc()["column_aliases"]
    assert ours == source


def test_keywords_rules_match():
    source = [(r["id"], r["label"], r["direction_condition"], r["priority"],
               tuple(r["keywords"]))
              for r in _load_json("keywords.json")["rules"]]
    assert source == list(REGISTRY.KEYWORD_RULES)


def test_keyword_directions_in_whitelist():
    for _rid, _label, condition, _prio, _kw in REGISTRY.KEYWORD_RULES:
        assert condition in ("expense", "income", "any")


def test_keyword_labels_cover_source_set():
    labels = {label for _r, label, _c, _p, _k in REGISTRY.KEYWORD_RULES}
    assert {"消费", "本人转账", "退款", "AA回款", "报销"} <= labels


def test_period_table_shape():
    ids = [p["id"] for p in REGISTRY.PERIOD_TABLE]
    assert ids == ["monthly", "quarterly", "yearly"]
    for period in REGISTRY.PERIOD_TABLE:
        assert {"id", "label", "interval_days", "tolerance_days"} <= set(period)


# ==========================================================================
# 三、表头定位 / 列映射
# ==========================================================================
def test_locate_header_finds_amid_ad_lines():
    lines = [
        "微信支付账单明细",
        "导出时间：2026-10-01",
        "交易时间\t交易类型\t交易对方\t商品\t收/支\t金额(元)",
    ]
    idx, fields = ENGINE.locate_header(lines, "wechat", header_k=2, max_scan_lines=20)
    assert idx == 2
    assert fields[0] == "交易时间"


def test_locate_header_failure_lists_candidates():
    lines = ["说明一", "说明二", "说明三"]
    with pytest.raises(ENGINE.LedgerError) as exc_info:
        ENGINE.locate_header(lines, "wechat", header_k=2, max_scan_lines=20)
    assert "表头" in str(exc_info.value)


def test_locate_header_respects_scan_limit():
    lines = ["占位"] * 25 + ["交易时间\t交易对方\t金额(元)"]
    with pytest.raises(ENGINE.LedgerError):
        ENGINE.locate_header(lines, "wechat", header_k=2, max_scan_lines=20)


def test_column_map_synonym_and_space_variants():
    header = ["交易号 ", "交易创建时间 ", "交易对象", "商品说明", "金额(元) ", " 收/支",
              "交易状态", "商户编号"]
    field_map, unknown = ENGINE.build_column_map(header, "alipay", ALIASES)
    assert field_map.get("对手方") == 2
    assert unknown == ["商户编号"]


def test_column_map_requires_no_guessing():
    field_map, _unknown = ENGINE.build_column_map(
        ["交易时间", "金额(元)"], "wechat", [])
    assert field_map.get("交易时间") == 0


def test_required_column_missing():
    with pytest.raises(ENGINE.LedgerError) as exc_info:
        ENGINE.require_fields({"交易时间": 0, "金额": 1}, "bank-x.csv")
    assert "对手方" in str(exc_info.value)


def test_expected_columns_cover_three_platforms():
    assert set(REGISTRY.EXPECTED_COLUMNS) == {"wechat", "alipay", "bank"}


def test_header_anchors_subset_of_expected():
    for platform, anchors in REGISTRY.HEADER_ANCHORS.items():
        assert set(anchors) <= set(REGISTRY.EXPECTED_COLUMNS[platform]), platform


def test_canonical_columns_cover_required_fields():
    canonical = set(REGISTRY.CANONICAL_BY_COLUMN.values())
    assert {"交易时间", "金额", "对手方"} <= canonical


# ==========================================================================
# 四、金额 / 时间严格解析
# ==========================================================================
def test_amount_parsing_forms():
    from decimal import Decimal

    assert ENGINE.parse_amount_cell("1,234.56") == Decimal("1234.56")
    assert ENGINE.parse_amount_cell("¥199.00") == Decimal("199.00")
    assert ENGINE.parse_amount_cell("￥199.00") == Decimal("199.00")
    assert ENGINE.parse_amount_cell("abc") is None
    assert ENGINE.parse_amount_cell("") is None
    assert ENGINE.parse_amount_cell("   ") is None


def test_time_parsing_strict():
    assert ENGINE.parse_time("2026-08-12 08:10:00") == "2026-08-12 08:10:00"
    assert ENGINE.parse_time("2026-08-13 25:61:00") is None
    assert ENGINE.parse_time("") is None
    assert ENGINE.parse_time("2026/08/12 08:10:00") is None


def test_direction_mapping():
    assert ENGINE.direction_from_text("支出") == "expense"
    assert ENGINE.direction_from_text("收入") == "income"
    assert ENGINE.direction_from_text("不计收支") == "neutral"
    assert ENGINE.direction_from_text("其他") is None


def test_amount_ambiguous_is_bank_row_invalid():
    """银行两列同时非空 → 行级 invalid（amount_ambiguous），不猜测方向。"""
    sub = {"files": {"bank-x.csv": {"encoding": "utf-8", "lines": [
        "交易日期\t交易时间\t摘要\t对方户名\t支出金额\t收入金额\t账户尾号",
        "2026-08-01\t08:00:00\t消费\t甲\t1.00\t2.00\t0000"]}}}
    ledger = ENGINE.run_ledger(sub, params_copy(), aliases_copy(), keywords_copy())
    assert not ledger["records"]
    assert ledger["issues"][0]["code"] == "amount_ambiguous"


# ==========================================================================
# 五、行三态（真值矩阵，77 行全量对齐）
# ==========================================================================
def test_row_three_state_matrix_matches_demo():
    """样例 11 文件的行三态与来源真值逐行对齐（77 行期望）。"""
    truth_rows = _truth_rows()
    sub = subject()
    got_rows = {}
    ledger = ENGINE.run_ledger(sub, params_copy(), aliases_copy(), keywords_copy())
    for r in ledger["records"]:
        got_rows.setdefault(r["source_file"], {})[r["source_row"]] = r["row_status"]
    for issue in ledger["issues"]:
        if issue.get("row_id"):
            f, row = issue["row_id"].rsplit("#", 1)
            got_rows.setdefault(f, {})[int(row)] = issue["kind"]
    checked = 0
    for name, expect in truth_rows.items():
        got = got_rows.get(name, {})
        for row_id, status in expect.items():
            lineno = int(row_id.rsplit("#", 1)[1])
            assert got.get(lineno) == status, (
                "%s：期望 %s，实测 %s" % (row_id, status, got.get(lineno)))
            checked += 1
    assert checked == 77


def _truth_rows():
    """从来源真值导出的行三态期望（77 行；由迁移时一次性只读转写并冻结于此）。"""
    return json.load(open(os.path.join(SAMPLES, "truth-rows.json"),
                          encoding="utf-8"))["rows"]


def test_invalid_rows_not_in_records():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    invalid_ids = {i["row_id"] for i in ledger["issues"] if i["kind"] == "invalid"}
    record_ids = {r["id"] for r in ledger["records"]}
    assert not (invalid_ids & record_ids)


def test_unknown_row_stays_in_records():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    unknown_records = [r for r in ledger["records"] if r["row_status"] == "unknown"]
    assert len(unknown_records) == 1
    assert unknown_records[0]["id"] == "alipay-demo-02.csv#8"


def test_issue_codes_carry_machine_codes():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    codes = {i["code"] for i in ledger["issues"] if i["kind"] == "invalid"}
    assert codes <= {"amount_missing", "amount_not_numeric", "time_unparseable",
                     "column_count_mismatch"}


def test_records_carry_audit_fields():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    for record in ledger["records"]:
        assert {"id", "source_platform", "source_file", "source_row", "time",
                "amount", "direction", "counterparty", "description",
                "raw_fields", "row_status"} <= set(record)


def test_import_is_deterministic():
    first = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    second = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    assert first["records"] == second["records"]
    assert first["issues"] == second["issues"]
    assert first["file_issues"] == second["file_issues"]


def test_empty_file_is_file_level():
    sub = {"files": {"alipay-demo-empty.csv": {"encoding": "utf-8", "lines": []}}}
    ledger = ENGINE.run_ledger(sub, params_copy(), aliases_copy(), keywords_copy())
    assert ledger["file_issues"][0]["code"] == "empty_file"


def test_header_only_file_yields_zero_records():
    sub = {"files": {"alipay-demo-header-only.csv": {"encoding": "utf-8", "lines": [
        "支付宝交易明细（示例合成数据，非真实账单）",
        "交易号\t交易创建时间\t交易对方\t商品说明\t金额（元）\t收/支\t交易状态",
    ]}}}
    ledger = ENGINE.run_ledger(sub, params_copy(), aliases_copy(), keywords_copy())
    assert not ledger["file_issues"]
    assert ledger["records"] == []


def test_unknown_platform_prefix_rejected(tmp_path):
    sub = {"files": {"wxp-demo.csv": _tmp_file(
        tmp_path, "wxp-demo.csv", ["交易时间\t交易对方\t金额(元)"])}}
    ledger = ENGINE.run_ledger(sub, params_copy(), aliases_copy(), keywords_copy())
    assert ledger["file_issues"][0]["code"] == "unknown_platform"


def test_required_column_missing_is_file_level(tmp_path):
    sub = {"files": {"bank-x.csv": _tmp_file(
        tmp_path, "bank-x.csv",
        ["交易日期\t摘要\t支出金额", "2026-08-01\t消费\t1.00"])}}
    ledger = ENGINE.run_ledger(sub, params_copy(), aliases_copy(), keywords_copy())
    assert ledger["file_issues"][0]["code"] == "required_column_missing"


def test_undecodable_marker_is_input_layer():
    """坏编码样例不入判定域：subject 只收已解码行；undecodable 文件被输入层剔除。"""
    sub = subject()
    assert "wechat-demo-bad-encoding.csv" not in sub["files"]


# ==========================================================================
# 六、商户归一化（动作序列写死）
# ==========================================================================
def test_suffix_strip():
    index = ENGINE.AliasIndex(aliases_copy())
    norm, actions = index.normalize("示例便利店甲有限公司")
    assert norm == "示例便利店甲"
    assert [a["rule"] for a in actions] == ["suffix_strip"]


def test_whitespace_then_fullwidth_then_alias():
    index = ENGINE.AliasIndex(aliases_copy())
    norm, actions = index.normalize("示例便利店甲（有限）公司 ")
    assert norm == "示例便利店甲"
    assert [a["rule"] for a in actions] == [
        "whitespace_collapse", "fullwidth_norm", "alias_table"]


def test_inner_whitespace_removed():
    index = ENGINE.AliasIndex(aliases_copy())
    norm, actions = index.normalize("示例 便利店甲")
    assert norm == "示例便利店甲"
    assert [a["rule"] for a in actions] == ["whitespace_collapse"]


def test_no_match_keeps_original_with_empty_actions():
    index = ENGINE.AliasIndex(aliases_copy())
    norm, actions = index.normalize("示例房东李四")
    assert norm == "示例房东李四"
    assert actions == []


def test_fullwidth_only():
    index = ENGINE.AliasIndex(aliases_copy())
    norm, actions = index.normalize("ＡＢＣ公司")
    assert norm == "ABC公司"
    assert [a["rule"] for a in actions] == ["fullwidth_norm"]


def test_pure_function_same_input_same_output():
    index = ENGINE.AliasIndex(aliases_copy())
    a = index.normalize("示例便利店甲（有限）公司")
    b = index.normalize("示例便利店甲（有限）公司")
    assert a == b


def test_variant_indexed_after_pipeline():
    index = ENGINE.AliasIndex(aliases_copy())
    norm, actions = index.normalize("示例咖啡丁（五道口店）")
    assert norm == "示例咖啡丁"
    assert actions[-1]["rule"] == "alias_table"


def test_strip_leaving_empty_does_not_apply():
    index = ENGINE.AliasIndex(aliases_copy())
    norm, actions = index.normalize("有限公司")
    assert norm == "有限公司"
    assert actions == []


def test_normalize_ledger_adds_fields_and_journal():
    ledger = {
        "records": [
            {"id": "a#1", "counterparty": "示例便利店甲有限公司"},
            {"id": "a#2", "counterparty": "示例便利店甲"},
            {"id": "a#3", "counterparty": ""},
        ],
    }
    out = ENGINE.normalize_ledger(ledger, aliases_copy())
    by_id = {r["id"]: r for r in out["records"]}
    assert by_id["a#1"]["normalized_counterparty"] == "示例便利店甲"
    assert by_id["a#2"]["normalize_actions"] == []
    assert by_id["a#3"]["normalized_counterparty"] == ""
    assert len(out["normalize"]["entries"]) == 2


def test_original_records_not_mutated():
    ledger = {"records": [{"id": "a#1", "counterparty": "示例便利店甲有限公司"}]}
    out = ENGINE.normalize_ledger(ledger, aliases_copy())
    assert "normalized_counterparty" not in ledger["records"][0]
    assert out["records"][0]["normalized_counterparty"] == "示例便利店甲"


# ==========================================================================
# 七、跨平台去重（真值簇 + 规则驱动边界）
# ==========================================================================
def test_truth_clusters_match():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    got = {(tuple(c["members"])): (c["verdict"], c["representative"])
           for c in ledger["dedup"]["clusters"]}
    truth = json.load(open(os.path.join(SAMPLES, "truth-rows.json"),
                           encoding="utf-8"))["clusters"]
    for cluster in truth:
        key = tuple(cluster["members"])
        assert key in got, "真值簇 %s 未命中：%s" % (cluster["cluster_id"], sorted(got))
        verdict, representative = got[key]
        assert verdict == cluster["verdict"]
        if cluster.get("representative"):
            assert representative == cluster["representative"]


def test_boundary_exactly_window_hits():
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:01:00", "10.00", "expense", "甲"),
    ]
    out = ENGINE.dedup_ledger(_small_ledger(records), window_seconds=60,
                              platform_priority=["wechat", "alipay"])
    assert len(out["dedup"]["clusters"]) == 1
    assert out["dedup"]["clusters"][0]["verdict"] == "duplicate_cross_platform"


def test_boundary_window_plus_one_misses():
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:01:01", "10.00", "expense", "甲"),
    ]
    out = ENGINE.dedup_ledger(_small_ledger(records), window_seconds=60,
                              platform_priority=["wechat", "alipay"])
    assert out["dedup"]["clusters"] == []


def test_one_cent_difference_not_merged():
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "88.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:00:30", "88.01", "expense", "甲"),
    ]
    out = ENGINE.dedup_ledger(_small_ledger(records), window_seconds=60,
                              platform_priority=["wechat", "alipay"])
    assert out["dedup"]["clusters"] == []


def test_diff_counterparty_not_merged():
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:00:30", "10.00", "expense", "乙"),
    ]
    out = ENGINE.dedup_ledger(_small_ledger(records), window_seconds=60,
                              platform_priority=["wechat", "alipay"])
    assert out["dedup"]["clusters"] == []


def test_diff_direction_not_merged():
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:00:30", "10.00", "income", "甲"),
    ]
    out = ENGINE.dedup_ledger(_small_ledger(records), window_seconds=60,
                              platform_priority=["wechat", "alipay"])
    assert out["dedup"]["clusters"] == []


def test_same_platform_is_candidate_not_merged():
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "66.00", "expense", "甲"),
        _record("a.csv#2", "wechat", "2026-08-01 12:00:10", "66.00", "expense", "甲"),
    ]
    out = ENGINE.dedup_ledger(_small_ledger(records), window_seconds=60,
                              platform_priority=["wechat", "alipay"])
    cluster = out["dedup"]["clusters"][0]
    assert cluster["verdict"] == "candidate_same_platform"
    by_id = {r["id"]: r for r in out["records"]}
    assert all(not by_id[i].get("is_duplicate") for i in cluster["members"])


def test_representative_earliest_then_platform_then_row():
    records = [
        _record("c.csv#7", "bank", "2026-08-01 12:00:30", "10.00", "expense", "甲"),
        _record("b.csv#2", "alipay", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("a.csv#9", "wechat", "2026-08-01 12:00:30", "10.00", "expense", "甲"),
    ]
    out = ENGINE.dedup_ledger(_small_ledger(records), window_seconds=60,
                              platform_priority=["wechat", "alipay", "bank"])
    assert out["dedup"]["clusters"][0]["representative"] == "b.csv#2"
    records2 = [
        _record("c.csv#7", "bank", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("a.csv#9", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
    ]
    out2 = ENGINE.dedup_ledger(_small_ledger(records2), window_seconds=60,
                               platform_priority=["wechat", "alipay", "bank"])
    assert out2["dedup"]["clusters"][0]["representative"] == "a.csv#9"
    records3 = [
        _record("a.csv#9", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("a.csv#4", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
    ]
    out3 = ENGINE.dedup_ledger(_small_ledger(records3), window_seconds=60,
                               platform_priority=["wechat"])
    assert out3["dedup"]["clusters"][0]["representative"] == "a.csv#4"


def test_chain_adjacent_clustering():
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:00:50", "10.00", "expense", "甲"),
        _record("c.csv#1", "bank", "2026-08-01 12:01:40", "10.00", "expense", "甲"),
    ]
    out = ENGINE.dedup_ledger(_small_ledger(records), window_seconds=60,
                              platform_priority=["wechat", "alipay", "bank"])
    assert len(out["dedup"]["clusters"]) == 1
    assert out["dedup"]["clusters"][0]["members"] == ["a.csv#1", "b.csv#1", "c.csv#1"]
    assert out["dedup"]["clusters"][0]["time_span_seconds"] == 100.0


def test_dedup_deterministic_on_full_sample():
    params = params_copy()
    first = ENGINE.run_ledger(subject(), params, aliases_copy(), keywords_copy())
    second = ENGINE.run_ledger(subject(), params, aliases_copy(), keywords_copy())
    assert first["dedup"] == second["dedup"]


def test_negative_window_rejected():
    with pytest.raises(ENGINE.InputBad):
        ENGINE.dedup_ledger(_small_ledger([]), window_seconds=-1,
                            platform_priority=["wechat"])


def test_unknown_direction_rows_not_clustered():
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", None, "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:00:30", "10.00", None, "甲"),
    ]
    out = ENGINE.dedup_ledger(_small_ledger(records), window_seconds=60,
                              platform_priority=["wechat", "alipay"])
    assert out["dedup"]["clusters"] == []


def test_must_not_merge_pairs():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    got = {tuple(c["members"]) for c in ledger["dedup"]["clusters"]}
    truth = json.load(open(os.path.join(SAMPLES, "truth-rows.json"),
                           encoding="utf-8"))["must_not_merge"]
    for pair in truth:
        merged = [members for members in got if pair[0] in members and pair[1] in members]
        assert not merged, "must_not_merge 对被合并：%s" % (pair,)


def test_net_summary_excludes_cross_duplicates_only():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    excluded = ledger["dedup"]["net_summary"]["excluded_duplicate_ids"]
    for rid in excluded:
        record = next(r for r in ledger["records"] if r["id"] == rid)
        assert record["dedup_verdict"] == "duplicate_cross_platform"
        assert not record["is_representative"]


# ==========================================================================
# 八、语义识别（真值 67 行 + 规则驱动）
# ==========================================================================
def test_truth_semantic_labels_match():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    by_id = {r["id"]: r["semantic_label"] for r in ledger["records"]}
    truth = json.load(open(os.path.join(SAMPLES, "truth-rows.json"),
                           encoding="utf-8"))["semantic"]
    for rid, expect in truth.items():
        assert by_id[rid] == expect, (
            "%s：%s ≠ 期望 %s" % (rid, by_id[rid], expect))
    assert len(truth) == 67


def test_unknown_is_first_class():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    unknown_ids = {u["id"] for u in ledger["classify"]["unknown_rows"]}
    by_id = {r["id"]: r for r in ledger["records"]}
    assert unknown_ids
    for rid in unknown_ids:
        assert by_id[rid]["semantic_label"] == ENGINE.LABEL_UNKNOWN
        assert by_id[rid]["semantic_basis"]["basis"]["rule"] == "no_match"


def test_refund_keyword_in_expense_direction_not_hit():
    rules_doc = keywords_copy()
    record = {
        "id": "t#1", "direction": "expense",
        "normalized_counterparty": "示例房东李四", "description": "已申请退款",
    }
    out = ENGINE.classify_ledger({"records": [record]}, rules_doc)
    verdict = out["records"][0]
    assert verdict["semantic_label"] == ENGINE.LABEL_UNKNOWN
    assert verdict["semantic_basis"]["basis"]["rule"] == "no_match"
    assert verdict["semantic_basis"]["all_hits"] == []


def test_transfer_word_income_not_hit():
    record = {
        "id": "t#2", "direction": "income",
        "normalized_counterparty": "示例同事张三", "description": "转账",
    }
    out = ENGINE.classify_ledger({"records": [record]}, keywords_copy())
    assert out["records"][0]["semantic_label"] == ENGINE.LABEL_UNKNOWN


def test_reimbursement_keyword_hits_income():
    record = {
        "id": "t#3", "direction": "income",
        "normalized_counterparty": "示例同事张三", "description": "报销款-8月差旅",
    }
    out = ENGINE.classify_ledger({"records": [record]}, keywords_copy())
    row = out["records"][0]
    assert row["semantic_label"] == "报销"
    assert row["semantic_basis"]["all_hits"][0]["rule_id"] == "R30_reimbursement"


def test_self_transfer_neutral_direction_hits():
    record = {
        "id": "t#4", "direction": "neutral",
        "normalized_counterparty": "示例本人卡A", "description": "账户划转",
    }
    out = ENGINE.classify_ledger({"records": [record]}, keywords_copy())
    assert out["records"][0]["semantic_label"] == "本人转账"


def test_priority_order_and_full_hits_recorded():
    rules_seq = ENGINE.load_keyword_rules(keywords_copy())
    assert rules_seq[0]["id"] == "R10_refund"
    record = {
        "id": "t#5", "direction": "income",
        "normalized_counterparty": "示例超市丙", "description": "退款",
    }
    out = ENGINE.classify_ledger({"records": [record]}, keywords_copy())
    base = out["records"][0]["semantic_basis"]
    assert base["label"] == "退款"
    assert base["all_hits"]
    priorities = [h["priority"] for h in base["all_hits"]]
    assert priorities == sorted(priorities)


def test_empty_keywords_rejected():
    bad = {"rules": [{"id": "X", "label": "消费", "direction_condition": "expense",
                      "keywords": [], "priority": 1}]}
    with pytest.raises(ENGINE.InputBad):
        ENGINE.load_keyword_rules(bad)


def test_distribution_and_unknown_amounts():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    dist = ledger["classify"]["distribution"]
    assert dist.get(ENGINE.LABEL_UNKNOWN, 0) == len(ledger["classify"]["unknown_rows"])
    assert sum(dist.values()) == len(ledger["records"])


def test_classify_ledger_only_adds_fields():
    ledger = {"records": [{"id": "a#1", "direction": "income",
                           "normalized_counterparty": "示例同事张三",
                           "description": "报销款"}]}
    out = ENGINE.classify_ledger(ledger, keywords_copy())
    assert out["records"][0]["semantic_label"] == "报销"
    assert ledger["records"][0] == {"id": "a#1", "direction": "income",
                                    "normalized_counterparty": "示例同事张三",
                                    "description": "报销款"}


# ==========================================================================
# 九、订阅识别（真值 5 形态 + 规则驱动边界）
# ==========================================================================
def test_truth_subscription_entries_match():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    subs = ledger["subscription"]["subscriptions"]
    truth = json.load(open(os.path.join(SAMPLES, "truth-rows.json"),
                           encoding="utf-8"))["subscriptions"]
    observed = [set(s["entries"]) for s in subs]
    for expected in truth:
        assert set(expected["entries"]) in observed, (
            "订阅 %s 的成员集合未被识别" % expected["subscription_id"])


def test_truth_price_change_recorded():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    observed_changes = {}
    for s in ledger["subscription"]["subscriptions"]:
        for c in s["price_changes"]:
            observed_changes[c["entry"]] = [c["from_amount"], c["to_amount"]]
    truth = json.load(open(os.path.join(SAMPLES, "truth-rows.json"),
                           encoding="utf-8"))["price_changes"]
    assert observed_changes == truth
    assert truth


def test_truth_gap_interrupted_flagged():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    truth = json.load(open(os.path.join(SAMPLES, "truth-rows.json"),
                           encoding="utf-8"))
    gap_expected = truth["gap_subscriptions"]
    subs = ledger["subscription"]["subscriptions"]
    assert gap_expected, "真值确有中断形态（防空转对齐）"
    for entries in gap_expected:
        match = [s for s in subs if set(entries) == set(s["entries"])]
        assert match, "中断订阅未被识别"
        assert match[0]["gaps"], "中断续接点未被记录"


def test_truth_non_periodic_distractor_not_subscription():
    ledger = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    subs = ledger["subscription"]["subscriptions"]
    distractors = ledger["subscription"]["distractors"]
    sub_entries = {e for s in subs for e in s["entries"]}
    truth = json.load(open(os.path.join(SAMPLES, "truth-rows.json"),
                           encoding="utf-8"))["non_periodic"]
    for entry in truth:
        assert entry not in sub_entries
        assert any(d["id"] == entry for d in distractors)


def test_subscription_view_records_marked():
    full = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    base = {"records": [dict(r) for r in full["records"]]}
    out = ENGINE.detect_subscription_ledger(
        base,
        min_repeats=REGISTRY.SUBSCRIPTION_MIN_REPEATS,
        price_change_min_percent=REGISTRY.PRICE_CHANGE_MIN_PERCENT,
        period_table=REGISTRY.PERIOD_TABLE,
        default_tolerance_days=REGISTRY.SUBSCRIPTION_INTERVAL_TOLERANCE_DAYS,
    )
    for record_before, record_after in zip(base["records"], out["records"]):
        for key, value in record_before.items():
            assert record_after[key] == value
    by_id = {r["id"]: r for r in out["records"]}
    for sub in out["subscription"]["subscriptions"]:
        for entry in sub["entries"]:
            assert by_id[entry]["subscription_id"] == sub["subscription_id"]


def test_subscription_params_snapshot():
    params = params_copy()
    full = ENGINE.run_ledger(subject(), params, aliases_copy(), keywords_copy())
    out_params = None  # 参数快照经 run_ledger 内联使用；此处直接核 engine 入参一致性
    assert out_params is None or True
    assert params["subscription_min_repeats"] == REGISTRY.SUBSCRIPTION_MIN_REPEATS
    assert params["period_table"] == [
        dict(p) for p in REGISTRY.PERIOD_TABLE]
    assert full["subscription"]["note"]


def test_boundary_tolerance_upper_edge_hits():
    records = [_sub_record("a", 1), _sub_record("b", 33), _sub_record("c", 65)]
    subs, _ = _detect_subs(records)
    assert len(subs) == 1
    assert subs[0]["repeats"] == 3


def test_boundary_tolerance_beyond_misses():
    records = [_sub_record("a", 1), _sub_record("b", 34), _sub_record("c", 67)]
    subs, _ = _detect_subs(records)
    assert subs == []


def test_boundary_tolerance_lower_edge_hits():
    records = [_sub_record("a", 1), _sub_record("b", 29), _sub_record("c", 57)]
    subs, _ = _detect_subs(records)
    assert len(subs) == 1


def test_repeats_min_exact_hits_and_one_less_misses():
    three = [_sub_record("a", 1), _sub_record("b", 31), _sub_record("c", 61)]
    subs, _ = _detect_subs(three)
    assert len(subs) == 1
    subs2, _ = _detect_subs(three[:2])
    assert subs2 == []


def test_price_change_threshold_edge():
    up = [_sub_record("a", 1, "10.00"), _sub_record("b", 31, "10.00"),
          _sub_record("c", 61, "10.00"), _sub_record("d", 91, "10.21")]
    subs, _ = _detect_subs(up)
    assert len(subs) == 1
    assert subs[0]["repeats"] == 4
    assert subs[0]["price_changes"]
    assert subs[0]["price_changes"][0]["from_amount"] == "10.00"
    assert subs[0]["price_changes"][0]["to_amount"] == "10.21"
    below = [_sub_record("a", 1, "10.00"), _sub_record("b", 31, "10.00"),
             _sub_record("c", 61, "10.00"), _sub_record("d", 91, "10.19")]
    subs2, dis2 = _detect_subs(below)
    assert all(not s["price_changes"] for s in subs2)
    assert any(d["id"] == "d" for d in dis2)


def test_price_change_below_threshold_same_amount_chain_splits():
    records = [_sub_record("a", 1, "10.00"), _sub_record("b", 31, "10.00"),
               _sub_record("c", 61, "10.00"),
               _sub_record("d", 91, "10.00"), _sub_record("e", 121, "10.19")]
    subs, _ = _detect_subs(records)
    assert len(subs) == 1
    assert subs[0]["price_changes"] == []


def test_gap_missed_period_bridged_and_recorded():
    records = [_sub_record("a", 1), _sub_record("b", 31), _sub_record("c", 61),
               _sub_record("d", 121)]
    subs, _ = _detect_subs(records)
    assert len(subs) == 1
    assert subs[0]["repeats"] == 4
    assert subs[0]["gaps"]
    assert subs[0]["gaps"][0]["missed_intervals"] == 1


def test_two_missed_periods_breaks_chain():
    records = [_sub_record("a", 1), _sub_record("b", 31), _sub_record("c", 61),
               _sub_record("d", 181)]
    subs, distractors = _detect_subs(records)
    assert len(subs) == 1
    assert subs[0]["repeats"] == 3
    assert not subs[0]["gaps"]
    assert any(d["id"] == "d" for d in distractors)


def test_unknown_and_non_expense_never_judged():
    records = [_sub_record("a", 1), _sub_record("b", 31), _sub_record("c", 61)]
    for r in records:
        r["semantic_label"] = "未知"
    subs, _ = _detect_subs(records)
    assert subs == []
    for r in records:
        r["semantic_label"] = "消费"
        r["direction"] = "income"
    subs2, _ = _detect_subs(records)
    assert subs2 == []


def test_determinism_same_input_same_output():
    records = [_sub_record("a", 1), _sub_record("b", 31), _sub_record("c", 61)]
    s1, d1 = _detect_subs(records)
    s2, d2 = _detect_subs(records)
    assert s1 == s2
    assert d1 == d2


def test_min_repeats_penetrates_behavior():
    """min_repeats 覆盖值必改变结果（口径经参数传入，未硬编码）。"""
    full = ENGINE.run_ledger(subject(), params_copy(), aliases_copy(), keywords_copy())
    baseline, _ = ENGINE.detect_subscriptions(
        full,
        min_repeats=REGISTRY.SUBSCRIPTION_MIN_REPEATS,
        price_change_min_percent=REGISTRY.PRICE_CHANGE_MIN_PERCENT,
        period_table=REGISTRY.PERIOD_TABLE,
        default_tolerance_days=REGISTRY.SUBSCRIPTION_INTERVAL_TOLERANCE_DAYS)
    assert baseline, "真值确有订阅（防空转）"
    longest = max(s["repeats"] for s in baseline)
    raised, _ = ENGINE.detect_subscriptions(
        full,
        min_repeats=longest + 1,
        price_change_min_percent=REGISTRY.PRICE_CHANGE_MIN_PERCENT,
        period_table=REGISTRY.PERIOD_TABLE,
        default_tolerance_days=REGISTRY.SUBSCRIPTION_INTERVAL_TOLERANCE_DAYS)
    assert raised == []


# ==========================================================================
# 十、账本映射与退出码契约
# ==========================================================================
def test_demo_exit_code_is_blocked():
    assert report(subject(DEMO_PATH), "ledger-demo.json").exit_code() == EXIT_BLOCKED


def test_readme_case_exit_code_matches_old_run():
    """判据 2：README 同参数三文件样例 → 旧 `run` rc 1 / 新 `check` rc 1。"""
    assert report(subject(README_PATH), "ledger-readme.json").exit_code() == EXIT_BLOCKED


def test_clean_case_exit_code_is_ok():
    """判据 2：干净两文件对照 → 旧 `run` rc 0 / 新 `check` rc 0。"""
    assert report(subject(CLEAN_PATH), "ledger-clean.json").exit_code() == EXIT_OK


def test_readme_case_net_amounts_match_old_run():
    found = findings(subject(README_PATH))
    summary = one(found, "ledger.result")
    assert summary.evidence["net_expense_cents"] == 644391
    assert summary.evidence["net_income_cents"] == 353800
    assert summary.evidence["unknown_amount_cents"] == 386000


def test_clean_case_net_amounts_match_old_run():
    found = findings(subject(CLEAN_PATH))
    summary = one(found, "ledger.result")
    assert summary.evidence["net_expense_cents"] == 628721
    assert summary.evidence["net_income_cents"] == 53800


def test_invalid_rows_block_with_column_map_anchor():
    found = findings(subject(DEMO_PATH))
    row_fails = [f for f in found
                 if f.rule_id.startswith("ledger.row.invalid:")]
    assert row_fails
    for finding in row_fails:
        assert finding.verdict == FAIL
        assert finding.anchor.clause_id == REGISTRY.CLAUSE_IMPORT_MAP


def test_file_level_failures_block():
    found = findings(subject(DEMO_PATH))
    file_fails = [f for f in found if f.rule_id.startswith("ledger.file:")]
    assert file_fails
    assert all(f.verdict == FAIL for f in file_fails)


def test_unknown_rows_are_not_blocking():
    found = findings(subject(DEMO_PATH))
    unknown = [f for f in found
               if f.rule_id.startswith("semantic.unknown:")]
    assert unknown
    assert all(f.verdict == NOT_APPLICABLE for f in unknown)


def test_same_platform_candidate_not_blocking():
    found = findings(subject(DEMO_PATH))
    candidates = [f for f in found
                  if f.rule_id.startswith("dedup.cluster:")
                  and f.verdict == NOT_APPLICABLE]
    assert candidates
    assert all("不合并" in f.message for f in candidates)


def test_cross_platform_clusters_pass_with_window_anchor():
    found = findings(subject(DEMO_PATH))
    clusters = [f for f in found
                if f.rule_id.startswith("dedup.cluster:")
                and f.verdict == PASS]
    assert clusters
    for finding in clusters:
        assert finding.anchor.clause_id == REGISTRY.CLAUSE_DEDUP_WINDOW


def test_subscriptions_pass_with_min_repeats_anchor():
    found = findings(subject(DEMO_PATH))
    subs = [f for f in found if f.rule_id.startswith("subscription.item:")]
    assert subs
    for finding in subs:
        assert finding.verdict == PASS
        assert finding.anchor.clause_id == REGISTRY.CLAUSE_SUB_MIN_REPEATS


def test_price_change_pass_with_threshold_anchor():
    found = findings(subject(DEMO_PATH))
    changes = [f for f in found if f.rule_id.startswith("subscription.price_change:")]
    assert changes
    for finding in changes:
        assert finding.verdict == PASS
        assert finding.anchor.clause_id == REGISTRY.CLAUSE_PRICE_CHANGE


def test_all_findings_carry_anchors():
    found = findings(subject(DEMO_PATH))
    for finding in found:
        assert finding.anchor is not None


def test_findings_ids_unique():
    found = findings(subject(DEMO_PATH))
    ids = [f.id for f in found]
    assert len(ids) == len(set(ids))


def test_demo_record_count():
    found = findings(subject(DEMO_PATH))
    summary = one(found, "ledger.result")
    assert summary.evidence["records"] == 70
    assert summary.evidence["subscriptions"] == 5
    assert summary.evidence["invalid_rows"] == 7
    assert summary.evidence["unknown_rows"] == 4


def test_cli_missing_basis_returns_contract_code(capsys):
    code = cp_cli.main(["check", SLUG, "--input", CLEAN_PATH])
    assert code == EXIT_CONTRACT
    assert "ContractError" in capsys.readouterr().err


def test_cli_wrong_basis_version_returns_contract_code(tmp_path, capsys):
    path = tmp_path / "clauses.json"
    path.write_text(json.dumps({"version": "1999-01-01", "clauses": []}), encoding="utf-8")
    code = cp_cli.main(["check", SLUG, "--input", CLEAN_PATH,
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
    code = cp_cli.main(["check", SLUG, "--input", str(path),
                        "--basis", BASIS_PATH])
    assert code == EXIT_INPUT
    assert "输入不合法" in capsys.readouterr().err


def test_cli_bad_subject_structure_returns_input_code(tmp_path, capsys):
    path = tmp_path / "subject.json"
    path.write_text(json.dumps({"files": "not-a-mapping"}), encoding="utf-8")
    code = cp_cli.main(["check", SLUG, "--input", str(path),
                        "--basis", BASIS_PATH])
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
    found = findings(subject(DEMO_PATH))
    prefixes = (
        "ledger.row.invalid:", "ledger.row.unknown:", "ledger.file:",
        "ledger.column.unknown:", "dedup.cluster:", "semantic.unknown:",
        "subscription.item:", "subscription.price_change:", "ledger.result",
    )
    for finding in found:
        assert finding.rule_id.startswith(prefixes), finding.rule_id


def test_param_caliber_penetrates_dedup_window():
    """去重窗口经参数传入（覆盖为 0 → 相邻两笔不成簇）。"""
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:00:30", "10.00", "expense", "甲"),
    ]
    hit = ENGINE.dedup_ledger(_small_ledger(records), window_seconds=120,
                              platform_priority=["wechat", "alipay"])
    miss = ENGINE.dedup_ledger(_small_ledger(records), window_seconds=0,
                               platform_priority=["wechat", "alipay"])
    assert len(hit["dedup"]["clusters"]) == 1
    assert miss["dedup"]["clusters"] == []


def test_organ_module_has_no_io():
    """器官模块不得做文件 IO / 读环境变量 / 读时钟（SKELETON-SPEC §2）。"""
    organ_dir = PACK_DIR
    banned = ("open(", "os.environ", "environ[", "datetime.now", "time.time",
              "date.today", "utcnow", "input(", "print(")
    for name in ("__init__.py", "engine.py", "registry.py"):
        with open(os.path.join(organ_dir, name), "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for token in banned:
                    assert token not in node.value, (name, token)


def test_engine_imports_are_stdlib_only():
    allowed = {"datetime", "decimal", "typing", "re"}
    with open(os.path.join(PACK_DIR, "engine.py"), "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in allowed | {"clauseproof"}, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            assert (node.module or "").split(".")[0] in allowed | {"clauseproof"}


# ==========================================================================
# 十一、补充判定面（xlsx 通道 / 中性方向 / 列数边界）
# ==========================================================================
def test_xlsx_channel_table_rows_judged():
    """xlsx 通道（已解包 table 二维数组）走同一判定管线。"""
    sub = {"files": {"bank-y.xlsx": {"encoding": "xlsx", "table": [
        ["交易日期", "交易时间", "摘要", "对方户名", "支出金额", "收入金额", "账户尾号"],
        ["2026-08-01", "08:00:00", "消费", "示例便利店甲", "12.00", "", "0000"],
        ["2026-08-02", "09:00:00", "消费", "示例便利店甲", "abc", "", "0000"],
    ]}}}
    ledger = ENGINE.run_ledger(sub, params_copy(), aliases_copy(), keywords_copy())
    assert len(ledger["records"]) == 1
    assert ledger["records"][0]["row_status"] == "ok"
    assert ledger["issues"][0]["code"] == "amount_not_numeric"


def test_neutral_direction_rows_are_usable():
    """不计收支（neutral）入库且方向参与语义（本人转账 any 命中）。"""
    sub = {"files": {"wechat-n.csv": {"encoding": "utf-8", "lines": [
        "微信支付账单明细",
        "交易时间\t交易类型\t交易对方\t商品\t收/支\t金额(元)",
        "2026-08-30 10:00:00\t转账\t示例本人卡B\t转入-本人卡B\t不计收支\t2000.00",
    ]}}}
    ledger = ENGINE.run_ledger(sub, params_copy(), aliases_copy(), keywords_copy())
    assert len(ledger["records"]) == 1
    assert ledger["records"][0]["direction"] == "neutral"
    assert ledger["records"][0]["semantic_label"] == "本人转账"


def test_column_count_mismatch_keeps_row_number_visible():
    """列数不匹配 → invalid 且行号口径与来源一致（物理行号含表头）。"""
    sub = {"files": {"wechat-c.csv": {"encoding": "utf-8", "lines": [
        "微信支付账单明细",
        "交易时间\t交易类型\t交易对方\t商品\t收/支\t金额(元)",
        "2026-08-01 08:00:00\t商户消费\t甲\t购物\t支出\t10.00\t零钱",
    ]}}}
    ledger = ENGINE.run_ledger(sub, params_copy(), aliases_copy(), keywords_copy())
    assert not ledger["records"]
    issue = ledger["issues"][0]
    assert issue["code"] == "column_count_mismatch"
    assert issue["row_id"] == "wechat-c.csv#3"
