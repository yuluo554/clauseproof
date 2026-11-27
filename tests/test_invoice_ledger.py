"""器官 ``invoice-ledger`` 判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源判定面的八规则（R-DUP-01/02/03、R-SEQ-01、R-ARITH-01/02、
R-TIME-01/02）逐条搬，断言落在「判定结果 + 级别 + 证据」上。来源判定层
（D1 + D18 机械选 11 文件 / 实跑 137 passed / AST 110）逐文件处置见
``docs/invoice-ledger.md`` §6。

来源仓只读；卡与时间基准一律**内存注入**，测试不写盘（CLI 契约用例用 tmp_path）。
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

from clauseproof import cli as cp_cli  # noqa: E402
from clauseproof.core.basis import Basis, BasisMissing  # noqa: E402
from clauseproof.core.ledger import (  # noqa: E402
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Report,
)

PACK_MOD = importlib.import_module("clauseproof.packs.invoice-ledger")
ENGINE = importlib.import_module("clauseproof.packs.invoice-ledger.engine")
CA = importlib.import_module("clauseproof.packs.invoice-ledger.cn_amount")
MODEL = importlib.import_module("clauseproof.packs.invoice-ledger.model")
REG = importlib.import_module("clauseproof.packs.invoice-ledger.registry")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "invoice-ledger")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "invoice-ledger")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
README_SAMPLE = os.path.join(SAMPLES, "ledger-readme.json")
CLEAN_SAMPLE = os.path.join(SAMPLES, "ledger-clean.json")


# --------------------------------------------------------------------------
# 夹具与工具
# --------------------------------------------------------------------------
def basis():
    return Basis.from_json(BASIS_PATH)


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def make_card(**overrides):
    data = {
        "invoice_number": "25910000000000123456",
        "invoice_type": "数电普票",
        "issue_date": "2026-01-05",
        "buyer_name": "星辰科技有限公司",
        "buyer_tax_id": "91330100DEMO0000001",
        "seller_name": "云图商贸有限公司",
        "seller_tax_id": "91330100DEMO0000101",
        "items": [{"name": "会议服务费", "amount": "1000.00",
                   "tax_rate": "0.13", "tax_amount": "130.00"}],
        "amount": "1000.00",
        "tax_amount": "130.00",
        "total_with_tax": "1130.00",
        "total_with_tax_cn": "壹仟壹佰叁拾元整",
        "remark": "",
        "batch_id": "batch_01",
        "confidence": 1.0,
        "field_flags": [],
        "evidence": [],
    }
    data.update(overrides)
    return data


def make_subject(cards, **overrides):
    subject = {
        "ledger_id": "test-ledger",
        "anchors": {
            "default": "2026-01-10",
            "batches": {"batch_01": "2026-01-10"},
        },
        "params": {},
        "existing_numbers": [],
        "cards": cards,
    }
    subject.update(overrides)
    return subject


def evaluate(cards, **overrides):
    return evaluate_subject(make_subject(cards, **overrides))


def evaluate_subject(subject):
    return tuple(PACK_MOD.evaluate(subject, basis()))


def hits(findings, family):
    prefix = "invoice.%s:" % family
    return [f for f in findings if f.rule_id.startswith(prefix)]


def summaries(findings):
    return [f for f in findings if ":" not in f.rule_id]


def by_rule(findings, family):
    return [f for f in findings if f.rule_id.startswith("invoice.%s" % family)]


def report(findings):
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject="test", findings=findings)


def seq_cards(start, count, prefix="259100000000", seller_tax_id="91330100DEMO0000101",
              start_day=1, batch_id="batch_01"):
    return [
        make_card(
            invoice_number="%s%08d" % (prefix, start + i),
            issue_date="2026-01-%02d" % (start_day + i),
            seller_tax_id=seller_tax_id,
            batch_id=batch_id,
        )
        for i in range(count)
    ]


# ==========================================================================
# §一 条文库与随包数据（11）
# ==========================================================================
def test_basis_version_is_source_review_date():
    assert basis().version == REG.PARAMS_VERSION == "2026-10-06"


def test_basis_has_twenty_clauses():
    assert len(basis()) == 20


def test_basis_covers_every_rule_clause():
    library = basis()
    for family, clause_id in REG.RULE_CLAUSES.items():
        assert library.clause(clause_id) is not None, family
        assert library.anchor(clause_id).path


def test_basis_has_all_contract_clauses():
    ids = basis().clause_ids()
    for clause_id in ("contract.anchor", "contract.ledger",
                      "contract.levels", "contract.params"):
        assert clause_id in ids


def test_basis_clause_ids_unique():
    ids = basis().clause_ids()
    assert len(ids) == len(set(ids))


def test_basis_clause_versions_match_library():
    library = basis()
    for clause_id in library.clause_ids():
        assert library.clause(clause_id).version == library.version


def test_basis_quote_764_21_1_verbatim():
    text = basis().clause("764-21-1").text
    assert text.startswith("开具发票应当按照规定的时限、顺序、栏目")
    assert text.endswith("开具纸质发票应当加盖发票专用章。")


def test_basis_quote_no11_number_rule_verbatim():
    text = basis().clause("no11-number-rule").text
    assert "数电发票的号码为20位" in text
    assert "第6-20位为顺序编码" in text


def test_basis_paths_non_empty():
    library = basis()
    for clause_id in library.clause_ids():
        assert library.clause(clause_id).path.strip()
        assert library.clause(clause_id).text.strip()


def test_manifest_clause_count_matches_library():
    manifest = load_json(os.path.join(DATA_DIR, "manifest.json"))
    assert manifest["clause_count"] == len(basis())
    assert manifest["version"] == REG.PARAMS_VERSION


def test_manifest_sha256_matches_files():
    import hashlib

    manifest = load_json(os.path.join(DATA_DIR, "manifest.json"))
    assert set(manifest["files"]) == set(REG.DATA_FILES)
    for name, record in manifest["files"].items():
        path = os.path.join(DATA_DIR, name)
        assert os.path.getsize(path) == record["bytes"], name
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        assert digest == record["sha256"], name


def test_manifest_rule_clauses_match_registry():
    manifest = load_json(os.path.join(DATA_DIR, "manifest.json"))
    assert manifest["rule_clauses"] == REG.RULE_CLAUSES


def test_registry_data_files_cover_directory():
    on_disk = sorted(
        name for name in os.listdir(DATA_DIR) if name.endswith(".json")
    )
    assert on_disk == sorted(REG.DATA_FILES + (REG.MANIFEST_FILE,))


# ==========================================================================
# §二 中文大写金额（20）
# ==========================================================================
def test_cn_zero():
    assert CA.encode_amount("0.00") == "零元整"


def test_cn_ten():
    assert CA.encode_amount("10.00") == "壹拾元整"


def test_cn_twenty():
    assert CA.encode_amount("20.00") == "贰拾元整"


def test_cn_one_hundred_ten():
    assert CA.encode_amount("110.00") == "壹佰壹拾元整"


def test_cn_1130():
    assert CA.encode_amount("1130.00") == "壹仟壹佰叁拾元整"


def test_cn_2120():
    assert CA.encode_amount("2120.00") == "贰仟壹佰贰拾元整"


def test_cn_1002_50():
    assert CA.encode_amount("1002.50") == "壹仟零贰元伍角"


def test_cn_1130_50():
    assert CA.encode_amount("1130.50") == "壹仟壹佰叁拾元伍角"


def test_cn_1130_05():
    assert CA.encode_amount("1130.05") == "壹仟壹佰叁拾元零伍分"


def test_cn_110_05():
    assert CA.encode_amount("110.05") == "壹佰壹拾元零伍分"


def test_cn_105000():
    assert CA.encode_amount("105000.00") == "壹拾万零伍仟元整"


def test_cn_100010000():
    assert CA.encode_amount("100010000.00") == "壹亿零壹万元整"


def test_cn_100000001():
    assert CA.encode_amount("100000001.00") == "壹亿零壹元整"


def test_cn_half_yuan():
    assert CA.encode_amount("0.50") == "伍角"


def test_cn_five_fen():
    assert CA.encode_amount("0.05") == "伍分"


def test_cn_half_yuan_five_fen():
    assert CA.encode_amount("0.55") == "伍角伍分"


def test_cn_mixed_digits():
    assert CA.encode_amount("1234567.89") == "壹佰贰拾叁万肆仟伍佰陆拾柒元捌角玖分"


def test_cn_rounds_extra_decimals():
    assert CA.encode_amount("1.004") == "壹元整"
    assert CA.encode_amount("1.005") == "壹元零壹分"
    assert CA.encode_amount("1.006") == "壹元零壹分"


def test_cn_rejects_negative():
    with pytest.raises(ValueError):
        CA.encode_amount("-1.00")


def test_cn_rejects_garbage():
    with pytest.raises(ValueError):
        CA.encode_amount("不是金额")


# ==========================================================================
# §三 发票卡模型（6）
# ==========================================================================
def test_card_dict_roundtrip():
    card = MODEL.InvoiceCard.from_dict(make_card())
    assert MODEL.InvoiceCard.from_dict(card.to_dict()) == card


def test_card_rejects_missing_number():
    payload = make_card()
    payload.pop("invoice_number")
    with pytest.raises(MODEL.CardError):
        MODEL.InvoiceCard.from_dict(payload)


def test_card_rejects_missing_type():
    payload = make_card()
    payload.pop("invoice_type")
    with pytest.raises(MODEL.CardError):
        MODEL.InvoiceCard.from_dict(payload)


def test_card_rejects_missing_issue_date():
    payload = make_card()
    payload.pop("issue_date")
    with pytest.raises(MODEL.CardError):
        MODEL.InvoiceCard.from_dict(payload)


def test_card_ignores_unknown_keys():
    payload = make_card()
    payload["future_field"] = "anything"
    assert MODEL.InvoiceCard.from_dict(payload).invoice_number == "25910000000000123456"


def test_card_defaults_confidence_and_flags():
    card = MODEL.InvoiceCard.from_dict(make_card())
    assert card.confidence == 1.0
    assert card.field_flags == []


# ==========================================================================
# §四 输入校验（13）
# ==========================================================================
def test_input_rejects_empty_cards():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(make_subject([]), basis())


def test_input_rejects_cards_not_list():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(make_subject({"a": 1}), basis())


def test_input_rejects_card_not_object():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(make_subject(["x"]), basis())


def test_input_requires_anchors():
    subject = make_subject([make_card()])
    subject.pop("anchors")
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(subject, basis())


def test_input_rejects_bad_default_anchor():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(make_subject(
            [make_card()], anchors={"default": "2026-13-01"}), basis())


def test_input_rejects_bad_batch_anchor():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(make_subject(
            [make_card()], anchors={"default": "2026-01-10",
                                    "batches": {"batch_01": "不是日期"}}), basis())


def test_input_rejects_unknown_anchor_key():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(make_subject(
            [make_card()], anchors={"default": "2026-01-10", "future": 1}), basis())


def test_input_rejects_unknown_param():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(make_subject([make_card()], params={"tolerance": 1}), basis())


def test_input_rejects_bad_tolerance():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(make_subject(
            [make_card()], params={"arith_tolerance": "abc"}), basis())


def test_input_rejects_negative_window():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(make_subject(
            [make_card()], params={"dup_date_window_days": -1}), basis())


def test_input_rejects_non_integer_window():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(make_subject(
            [make_card()], params={"seq_min_len": "three"}), basis())


def test_input_rejects_existing_numbers_not_list():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(make_subject(
            [make_card()], existing_numbers="25910000000000123456"), basis())


def test_input_rejects_empty_existing_number_item():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate(make_subject([make_card()], existing_numbers=[""]), basis())


# ==========================================================================
# §五 引擎编排（5）
# ==========================================================================
def test_engine_rule_order_matches_contract():
    assert ENGINE.RULE_ORDER == (
        "duplicate.exact", "duplicate.joint", "duplicate.fuzzy", "series",
        "arithmetic.total", "arithmetic.cn", "time.future", "time.stale",
    )


def test_engine_demo_all_eight_rules_hit():
    context = ENGINE.build_context(load_json(README_SAMPLE))
    _, stats = ENGINE.run(context)
    assert {family: stats[family]["hits"] > 0 for family in ENGINE.RULE_ORDER} == {
        family: True for family in ENGINE.RULE_ORDER
    }


def test_engine_clean_all_rules_zero_hits():
    context = ENGINE.build_context(load_json(CLEAN_SAMPLE))
    _, stats = ENGINE.run(context)
    assert all(stats[family] == {"hits": 0, "skipped": 0}
               for family in ENGINE.RULE_ORDER)


def test_findings_ids_unique():
    findings = evaluate_subject(load_json(README_SAMPLE))
    ids = [finding.id for finding in findings]
    assert len(ids) == len(set(ids))


def test_evaluate_is_deterministic():
    subject = load_json(README_SAMPLE)
    first = [f.as_dict() for f in PACK_MOD.evaluate(subject, basis())]
    second = [f.as_dict() for f in PACK_MOD.evaluate(subject, basis())]
    assert first == second


# ==========================================================================
# §六 R-DUP-01 精确重复（6）
# ==========================================================================
def test_dup01_in_batch_duplicate_is_fail():
    findings = evaluate([make_card(), make_card(),
                         make_card(invoice_number="25910000000000123457")])
    dup = hits(findings, "duplicate.exact")
    assert len(dup) == 1
    assert dup[0].verdict == FAIL
    assert dup[0].evidence["occurrences"] == 2


def test_dup01_pre_existing_number_is_fail():
    card = make_card()
    findings = evaluate([card], existing_numbers=[card["invoice_number"]])
    dup = hits(findings, "duplicate.exact")
    assert len(dup) == 1
    assert dup[0].evidence["pre_existing_in_ledger"] is True


def test_dup01_three_occurrences_evidence():
    findings = evaluate([make_card(), make_card(), make_card()])
    assert hits(findings, "duplicate.exact")[0].evidence["occurrences"] == 3


def test_dup01_distinct_numbers_pass():
    findings = evaluate([make_card(),
                         make_card(invoice_number="25910000000000123457")])
    assert hits(findings, "duplicate.exact") == []
    assert any(f.rule_id == "invoice.duplicate.exact" for f in summaries(findings))


def test_dup01_evidence_batches():
    findings = evaluate([
        make_card(batch_id="batch_01"),
        make_card(batch_id="batch_02", seller_name="另一家有限公司"),
    ])
    assert hits(findings, "duplicate.exact")[0].evidence["batches"] == [
        "batch_01", "batch_02"]


def test_dup01_message_mentions_duplicate():
    findings = evaluate([make_card(), make_card()])
    assert "重复" in hits(findings, "duplicate.exact")[0].message


# ==========================================================================
# §七 R-DUP-02 联合键重复（7）
# ==========================================================================
def test_dup02_joint_pair_is_fail():
    findings = evaluate([
        make_card(),
        make_card(batch_id="batch_02", buyer_name="另一家收购主体有限公司",
                  remark="再制票备注"),
    ])
    joint = hits(findings, "duplicate.joint")
    assert len(joint) == 1
    assert joint[0].verdict == FAIL


def test_dup02_exact_copy_excluded():
    findings = evaluate([make_card(), make_card(batch_id="batch_02")])
    assert hits(findings, "duplicate.joint") == []
    assert len(hits(findings, "duplicate.exact")) == 1


def test_dup02_same_batch_not_flagged():
    findings = evaluate([
        make_card(),
        make_card(batch_id="batch_01", buyer_name="另一家收购主体有限公司"),
    ])
    assert hits(findings, "duplicate.joint") == []


def test_dup02_different_total_not_flagged():
    findings = evaluate([
        make_card(),
        make_card(batch_id="batch_02", total_with_tax="2260.00",
                  total_with_tax_cn="贰仟贰佰陆拾元整",
                  amount="2000.00", tax_amount="260.00",
                  items=[{"name": "会议服务费", "amount": "2000.00",
                          "tax_rate": "0.13", "tax_amount": "260.00"}]),
    ])
    assert hits(findings, "duplicate.joint") == []


def test_dup02_different_date_not_flagged():
    findings = evaluate([
        make_card(),
        make_card(batch_id="batch_02", issue_date="2026-01-06",
                  buyer_name="另一家有限公司"),
    ])
    assert hits(findings, "duplicate.joint") == []


def test_dup02_pair_evidence_batches():
    findings = evaluate([
        make_card(),
        make_card(batch_id="batch_02", buyer_name="另一家有限公司"),
    ])
    evidence = hits(findings, "duplicate.joint")[0].evidence["pairs"]
    assert evidence[0]["batches"] == ["batch_01", "batch_02"]
    assert evidence[0]["total_with_tax"] == "1130.00"


def test_dup02_single_card_pass_summary():
    findings = evaluate([make_card()])
    assert any(f.rule_id == "invoice.duplicate.joint" and f.verdict == PASS
               for f in findings)


# ==========================================================================
# §八 R-DUP-03 模糊重复（8）
# ==========================================================================
def test_dup03_fuzzy_pair_is_na():
    findings = evaluate([
        make_card(),
        make_card(invoice_number="25910000000000123457", issue_date="2026-01-06"),
    ])
    fuzzy = hits(findings, "duplicate.fuzzy")
    assert len(fuzzy) == 1
    assert fuzzy[0].verdict == NOT_APPLICABLE


def test_dup03_gated_by_dup01():
    findings = evaluate([
        make_card(),
        make_card(batch_id="batch_02"),
        make_card(invoice_number="25910000000000123457", issue_date="2026-01-05"),
    ])
    assert len(hits(findings, "duplicate.exact")) == 1
    assert hits(findings, "duplicate.fuzzy") == []


def test_dup03_amount_mismatch_not_flagged():
    findings = evaluate([
        make_card(),
        make_card(invoice_number="25910000000000123457", issue_date="2026-01-06",
                  total_with_tax="1131.00", total_with_tax_cn="壹仟壹佰叁拾壹元整",
                  amount="1001.00"),
    ])
    assert hits(findings, "duplicate.fuzzy") == []


def test_dup03_seller_mismatch_not_flagged():
    findings = evaluate([
        make_card(),
        make_card(invoice_number="25910000000000123457", issue_date="2026-01-05",
                  seller_tax_id="91330100DEMO0000109", seller_name="别家公司有限公司"),
    ])
    assert hits(findings, "duplicate.fuzzy") == []


def test_dup03_default_window_excludes_three_days():
    findings = evaluate([
        make_card(),
        make_card(invoice_number="25910000000000123457", issue_date="2026-01-08"),
    ])
    assert hits(findings, "duplicate.fuzzy") == []


def test_dup03_window_param_widens():
    findings = evaluate(
        [make_card(),
         make_card(invoice_number="25910000000000123457", issue_date="2026-01-08")],
        params={"dup_date_window_days": 5},
    )
    assert len(hits(findings, "duplicate.fuzzy")) == 1


def test_dup03_na_evidence_keeps_level():
    findings = evaluate([
        make_card(),
        make_card(invoice_number="25910000000000123457", issue_date="2026-01-06"),
    ])
    assert hits(findings, "duplicate.fuzzy")[0].evidence["level"] == "suspicious"


def test_dup03_numbers_sorted():
    findings = evaluate([
        make_card(invoice_number="25910000000000123457", issue_date="2026-01-06"),
        make_card(),
    ])
    rule_id = hits(findings, "duplicate.fuzzy")[0].rule_id
    expected = "invoice.duplicate.fuzzy:25910000000000123456|25910000000000123457"
    assert rule_id == expected


# ==========================================================================
# §九 R-SEQ-01 连号拆分（9）
# ==========================================================================
def test_seq_cluster_is_na():
    findings = evaluate(seq_cards(10000101, 3))
    series = hits(findings, "series")
    assert len(series) == 1
    assert series[0].verdict == NOT_APPLICABLE
    assert series[0].evidence["count"] == 3


def test_seq_below_min_len_not_flagged():
    assert hits(evaluate(seq_cards(10000101, 2)), "series") == []


def test_seq_gap_breaks_cluster():
    cards = seq_cards(10000101, 2) + seq_cards(10000104, 2)
    assert hits(evaluate(cards), "series") == []


def test_seq_date_span_beyond_window_not_flagged():
    cards = [
        make_card(invoice_number="2591000000" "00100001%02d" % (i + 1),
                  issue_date="2026-01-%02d" % (1 + i * 5),
                  seller_tax_id="91330100DEMO0000101")
        for i in range(3)
    ]
    assert hits(evaluate(cards), "series") == []


def test_seq_mixed_prefix_not_flagged():
    cards = seq_cards(10000101, 3) + seq_cards(10000104, 1, prefix="269100000000")
    assert hits(evaluate(cards), "series") == []


def test_seq_requires_same_seller():
    cards = [
        make_card(invoice_number="2591000000" "00100001%02d" % (i + 1),
                  issue_date="2026-01-0%d" % (i + 1),
                  seller_tax_id="91330100DEMO00001%02d" % (i + 1))
        for i in range(3)
    ]
    assert hits(evaluate(cards), "series") == []


def test_seq_non_digit_suffix_skipped():
    cards = [
        make_card(invoice_number="259100000000100001AB", issue_date="2026-01-01",
                  seller_tax_id="91330100DEMO0000101"),
        make_card(invoice_number="259100000000100001AC", issue_date="2026-01-02",
                  seller_tax_id="91330100DEMO0000101"),
    ]
    findings = evaluate(cards)
    assert hits(findings, "series") == []
    assert any(f.rule_id == "invoice.series" and f.evidence["skipped"] == 2
               for f in findings)


def test_seq_min_len_param_respected():
    findings = evaluate(seq_cards(10000101, 3), params={"seq_min_len": 4})
    assert hits(findings, "series") == []


def test_seq_numbers_listed_in_rule_id():
    findings = evaluate(seq_cards(10000101, 3))
    rule_id = hits(findings, "series")[0].rule_id
    assert rule_id.count("|") == 2


# ==========================================================================
# §十 R-ARITH-01 票面算术（9）
# ==========================================================================
def test_arith_ok_card_no_fail():
    findings = evaluate([make_card()])
    assert report(findings).blocking() == ()
    assert any(f.rule_id == "invoice.arithmetic.total" and f.verdict == PASS
               for f in findings)


def test_arith_tampered_total_is_fail():
    findings = evaluate([make_card(total_with_tax="2180.00",
                                   total_with_tax_cn="贰仟壹佰捌拾元整")])
    arith = hits(findings, "arithmetic.total")
    assert len(arith) == 1
    assert arith[0].verdict == FAIL
    assert arith[0].evidence["check"] == "total"


def test_arith_non_numeric_degrades_to_na():
    findings = evaluate([make_card(amount="一千元")])
    arith = hits(findings, "arithmetic.total")
    assert len(arith) == 1
    assert arith[0].verdict == NOT_APPLICABLE
    assert arith[0].evidence["check"] == "unparseable"


def test_arith_default_tolerance_absorbs_half_cent():
    card = make_card(total_with_tax="1130.005",
                     total_with_tax_cn="壹仟壹佰叁拾元零壹分")
    assert not report(evaluate([card])).blocking()


def test_arith_strict_tolerance_flags_half_cent():
    card = make_card(total_with_tax="1130.005",
                     total_with_tax_cn="壹仟壹佰叁拾元零壹分")
    findings = evaluate([card], params={"arith_tolerance": "0.001"})
    assert hits(findings, "arithmetic.total")[0].verdict == FAIL


def test_arith_item_sum_mismatch_is_fail():
    card = make_card(items=[
        {"name": "咨询费", "amount": "800.00", "tax_rate": "0.13", "tax_amount": "130.00"},
        {"name": "服务费", "amount": "100.00", "tax_rate": "0.13", "tax_amount": "0.00"},
    ])
    hits_ = hits(evaluate([card]), "arithmetic.total")
    assert len(hits_) == 1
    assert hits_[0].evidence["check"] == "sum"


def test_arith_item_check_skipped_when_item_incomplete():
    card = make_card(items=[
        {"name": "咨询费", "amount": "", "tax_rate": "0.13", "tax_amount": "130.00"},
    ])
    assert hits(evaluate([card]), "arithmetic.total") == []


def test_arith_item_and_total_can_both_fire():
    card = make_card(
        amount="2000.00", tax_amount="260.00", total_with_tax="9999.00",
        total_with_tax_cn="玖仟玖佰玖拾玖元整",
        items=[{"name": "咨询费", "amount": "100.00",
                "tax_rate": "0.13", "tax_amount": "260.00"}],
    )
    checks = {f.evidence["check"] for f in hits(evaluate([card]), "arithmetic.total")}
    assert checks == {"sum", "total"}


def test_arith_evidence_expect_total():
    findings = evaluate([make_card(total_with_tax="2180.00",
                                   total_with_tax_cn="贰仟壹佰捌拾元整")])
    assert hits(findings, "arithmetic.total")[0].evidence["expect_total"] == "1130.00"


# ==========================================================================
# §十一 R-ARITH-02 大写金额（6）
# ==========================================================================
def test_cn_mismatch_is_fail():
    findings = evaluate([make_card(total_with_tax_cn="壹仟贰佰元整")])
    cn = hits(findings, "arithmetic.cn")
    assert len(cn) == 1
    assert cn[0].verdict == FAIL
    assert cn[0].evidence["expect_cn"] == "壹仟壹佰叁拾元整"


def test_cn_ok_passes():
    assert hits(evaluate([make_card()]), "arithmetic.cn") == []


def test_cn_unparseable_total_degrades_to_na():
    findings = evaluate([make_card(total_with_tax="１１３０元")])
    cn = hits(findings, "arithmetic.cn")
    assert cn[0].verdict == NOT_APPLICABLE
    assert cn[0].evidence["level"] == "review"


def test_cn_missing_fields_marked_skipped():
    findings = evaluate([make_card(total_with_tax="", total_with_tax_cn="")])
    summary = next(f for f in findings if f.rule_id == "invoice.arithmetic.cn")
    assert summary.verdict == NOT_APPLICABLE
    assert summary.evidence["skipped"] == 1


def test_cn_evidence_expect_cn():
    findings = evaluate([make_card(total_with_tax_cn="壹仟贰佰元整")])
    assert hits(findings, "arithmetic.cn")[0].evidence["total_with_tax"] == "1130.00"


def test_cn_whitespace_trimmed():
    findings = evaluate([make_card(total_with_tax_cn=" 壹仟壹佰叁拾元整 ")])
    assert hits(findings, "arithmetic.cn") == []


# ==========================================================================
# §十二 R-TIME 时间逻辑（10）
# ==========================================================================
def test_time_future_issue_is_fail():
    findings = evaluate([make_card(issue_date="2026-07-16")],
                        anchors={"default": "2026-07-15",
                                 "batches": {"batch_01": "2026-07-15"}})
    future = hits(findings, "time.future")
    assert len(future) == 1
    assert future[0].verdict == FAIL
    assert future[0].evidence["delta_days"] == 1


def test_time_issue_on_anchor_passes():
    findings = evaluate([make_card(issue_date="2026-07-15")],
                        anchors={"default": "2026-07-15",
                                 "batches": {"batch_01": "2026-07-15"}})
    assert hits(findings, "time.future") == []


def test_time_issue_before_anchor_passes():
    findings = evaluate([make_card(issue_date="2026-05-01")],
                        anchors={"default": "2026-07-15",
                                 "batches": {"batch_01": "2026-07-15"}})
    assert hits(findings, "time.future") == []


def test_time_default_anchor_for_unmapped_batch():
    findings = evaluate([make_card(issue_date="2027-01-01", batch_id="batch_99")],
                        anchors={"default": "2026-07-15", "batches": {}})
    future = hits(findings, "time.future")
    assert len(future) == 1
    assert future[0].evidence["anchor"] == "2026-07-15"


def test_time_stale_beyond_n_period_is_na():
    findings = evaluate([make_card(issue_date="2026-01-01")],
                        anchors={"default": "2026-07-15",
                                 "batches": {"batch_01": "2026-07-15"}})
    stale = hits(findings, "time.stale")
    assert len(stale) == 1
    assert stale[0].verdict == NOT_APPLICABLE
    assert stale[0].evidence["months_behind"] == 6


def test_time_within_n_period_passes():
    findings = evaluate([make_card(issue_date="2026-05-01")],
                        anchors={"default": "2026-07-15",
                                 "batches": {"batch_01": "2026-07-15"}})
    assert hits(findings, "time.stale") == []


def test_time_future_not_double_flagged():
    findings = evaluate([make_card(issue_date="2027-06-01")],
                        anchors={"default": "2026-07-15",
                                 "batches": {"batch_01": "2026-07-15"}})
    assert [f.rule_id.split(":")[0] for f in findings if ":" in f.rule_id] == [
        "invoice.time.future"]


def test_time_n_period_param_respected():
    findings = evaluate([make_card(issue_date="2026-05-01")],
                        anchors={"default": "2026-07-15",
                                 "batches": {"batch_01": "2026-07-15"}},
                        params={"time_n_period": 1})
    assert len(hits(findings, "time.stale")) == 1


def test_time_unparseable_date_skipped():
    findings = evaluate([make_card(issue_date="二〇二六年七月一日")])
    summary = next(f for f in findings if f.rule_id == "invoice.time.future")
    assert summary.verdict == NOT_APPLICABLE
    assert summary.evidence["skipped"] == 1


def test_time_evidence_anchor_iso():
    findings = evaluate([make_card(issue_date="2026-07-16")],
                        anchors={"default": "2026-07-15",
                                 "batches": {"batch_01": "2026-07-15"}})
    assert hits(findings, "time.future")[0].evidence["anchor"] == "2026-07-15"


# ==========================================================================
# §十三 端到端样例（9）
# ==========================================================================
def test_readme_demo_total_13():
    findings = evaluate_subject(load_json(README_SAMPLE))
    assert len(findings) == 13


def test_readme_demo_verdict_counts():
    findings = evaluate_subject(load_json(README_SAMPLE))
    counts = report(findings).summary()["verdicts"]
    assert counts[FAIL] == 9
    assert counts[NOT_APPLICABLE] == 4
    assert counts[PASS] == 0


def test_readme_demo_exact_duplicate_numbers():
    findings = evaluate_subject(load_json(README_SAMPLE))
    numbers = sorted(f.rule_id.split(":")[1] for f in hits(findings, "duplicate.exact"))
    assert numbers == ["14410000000010000106", "25910000000010000111"]


def test_readme_demo_series_has_five_numbers():
    findings = evaluate_subject(load_json(README_SAMPLE))
    assert hits(findings, "series")[0].rule_id.count("|") == 4


def test_readme_demo_fuzzy_pair():
    findings = evaluate_subject(load_json(README_SAMPLE))
    assert hits(findings, "duplicate.fuzzy")[0].evidence["amount"] == "24325.07"


def test_readme_demo_arithmetic_two_each():
    findings = evaluate_subject(load_json(README_SAMPLE))
    assert len(hits(findings, "arithmetic.total")) == 2
    assert len(hits(findings, "arithmetic.cn")) == 2


def test_clean_sample_all_pass():
    findings = evaluate_subject(load_json(CLEAN_SAMPLE))
    assert len(findings) == 8
    assert all(f.verdict == PASS for f in findings)


def test_clean_sample_exit_code_zero():
    findings = evaluate_subject(load_json(CLEAN_SAMPLE))
    assert report(findings).exit_code() == 0


def test_readme_demo_exit_code_blocked():
    findings = evaluate_subject(load_json(README_SAMPLE))
    assert report(findings).exit_code() == 1


def test_existing_numbers_make_clean_card_fail():
    subject = load_json(CLEAN_SAMPLE)
    card = subject["cards"][0]
    subject["cards"] = [card]
    subject["existing_numbers"] = [card["invoice_number"]]
    findings = evaluate_subject(subject)
    assert hits(findings, "duplicate.exact")[0].verdict == FAIL


# ==========================================================================
# §十四 账本契约（8）
# ==========================================================================
def test_all_fail_findings_have_anchor():
    findings = evaluate_subject(load_json(README_SAMPLE))
    assert all(f.anchor is not None for f in findings if f.verdict == FAIL)


def test_all_na_findings_have_anchor():
    findings = evaluate_subject(load_json(README_SAMPLE))
    assert all(f.anchor is not None for f in findings if f.verdict == NOT_APPLICABLE)


def test_every_finding_carries_source_rule():
    findings = evaluate_subject(load_json(README_SAMPLE))
    assert all(f.evidence["source_rule"].startswith("R-") for f in findings)


def test_heuristic_note_on_series():
    findings = evaluate(seq_cards(10000101, 3))
    assert "工程口径" in hits(findings, "series")[0].evidence["heuristic_note"]


def test_no_heuristic_note_on_arithmetic():
    findings = evaluate([make_card(total_with_tax="2180.00",
                                   total_with_tax_cn="贰仟壹佰捌拾元整")])
    hit = hits(findings, "arithmetic.total")[0]
    assert hit.evidence["heuristic"] is False
    assert "heuristic_note" not in hit.evidence


def test_missing_clause_raises_basis_missing():
    limited = Basis(version=REG.PARAMS_VERSION, clauses=[])
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate(make_subject([make_card()]), limited)


def test_wrong_basis_version_raises_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(make_subject([make_card()]), Basis.empty("0"))


def test_basis_with_foreign_version_raises_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(make_subject([make_card()]), Basis.empty("2099-01-01"))


# ==========================================================================
# §十五 CLI 契约（5）
# ==========================================================================
def test_cli_demo_returns_blocked():
    assert cp_cli.main(["check", SLUG, "--input", README_SAMPLE,
                        "--basis", BASIS_PATH]) == 1


def test_cli_clean_returns_ok():
    assert cp_cli.main(["check", SLUG, "--input", CLEAN_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_missing_basis_returns_contract():
    assert cp_cli.main(["check", SLUG, "--input", CLEAN_SAMPLE]) == 3


def test_cli_bad_card_returns_input(tmp_path):
    payload = make_subject([make_card()])
    payload["cards"][0].pop("invoice_number")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert cp_cli.main(["check", SLUG, "--input", str(path),
                        "--basis", BASIS_PATH]) == 2


def test_cli_empty_cards_returns_input(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps(make_subject([]), ensure_ascii=False),
                    encoding="utf-8")
    assert cp_cli.main(["check", SLUG, "--input", str(path),
                        "--basis", BASIS_PATH]) == 2


# ==========================================================================
# §十六 参数与汇总（5）
# ==========================================================================
def test_params_defaults_exact():
    params = ENGINE.parse_params(None)
    assert params["arith_tolerance"] == Decimal("0.01")
    assert params["dup_date_window_days"] == 1
    assert params["dup_amount_tol"] == Decimal("0.00")
    assert params["seq_suffix_len"] == 8
    assert params["seq_min_len"] == 3
    assert params["seq_date_window_days"] == 7
    assert params["time_n_period"] == 3


def test_params_custom_values_respected():
    params = ENGINE.parse_params({
        "arith_tolerance": "0.001", "dup_date_window_days": 2,
        "dup_amount_tol": "0.50", "seq_suffix_len": 6,
        "seq_min_len": 4, "seq_date_window_days": 10, "time_n_period": 6,
    })
    assert params["dup_amount_tol"] == Decimal("0.50")
    assert params["seq_suffix_len"] == 6


def test_clean_summary_message_contains_rule_code():
    findings = evaluate([make_card()])
    summary = next(f for f in findings if f.rule_id == "invoice.duplicate.exact")
    assert "R-DUP-01" in summary.message


def test_skipped_summary_message_mentions_card_count():
    findings = evaluate([make_card(amount="")])
    summary = next(f for f in findings if f.rule_id == "invoice.arithmetic.total")
    assert "1 张卡" in summary.message


def test_clean_has_eight_summaries():
    findings = evaluate([make_card()])
    assert len(summaries(findings)) == 8