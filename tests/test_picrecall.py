"""器官 ``picrecall`` 判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源判定面（pHash 单链聚类 / 保留优先级 / 只读纪律 / 确定性）
逐条搬，断言落在「分组结果 + 保留建议 + 不写用户文件」上。来源判定层
（D1 + D18 机械选 12 文件 / 实跑 101 passed / AST 100）逐文件处置见
``docs/picrecall.md`` §6。

来源仓只读；合成指纹一律内存注入，不读写用户图片。
"""

import ast
import importlib
import json
import os
import sys

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

PACK_MOD = importlib.import_module("clauseproof.packs.picrecall")
ENGINE = importlib.import_module("clauseproof.packs.picrecall.engine")
REG = importlib.import_module("clauseproof.packs.picrecall.registry")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "picrecall")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "picrecall")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
DUPES_SAMPLE = os.path.join(SAMPLES, "dedupe-dupes.json")
CLEAN_SAMPLE = os.path.join(SAMPLES, "dedupe-clean.json")

H0 = "0000000000000000"
H1 = "0000000000000001"
H8 = "00000000000000ff"
FAR = "ffffffffffffffff"


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def basis():
    return Basis.from_json(BASIS_PATH)


def item(path="a.png", phash=H0, width=100, height=100, size=1000, mtime_ns=1):
    return {"path": path, "phash": phash, "width": width, "height": height,
            "size": size, "mtime_ns": mtime_ns}


def subject(items, threshold=8, case_id="c"):
    return {"case_id": case_id,
            "dedupe": {"threshold": threshold, "items": items}}


def evaluate(payload):
    return tuple(PACK_MOD.evaluate(payload, basis()))


def report(findings):
    return Report(product="clauseproof", organ=SLUG,
                  organ_version=PACK_MOD.VERSION, subject="test",
                  findings=findings)


# ==========================================================================
# §一 pHash 解析（10）
# ==========================================================================
def test_parse_phash_zero():
    assert ENGINE.parse_phash(H0) == 0


def test_parse_phash_one():
    assert ENGINE.parse_phash(H1) == 1


def test_parse_phash_ff():
    assert ENGINE.parse_phash(H8) == 255


def test_parse_phash_uppercase():
    assert ENGINE.parse_phash("00000000000000AB") == 0xAB


def test_parse_phash_strips_whitespace():
    assert ENGINE.parse_phash(" 00000000000000ab ") == 0xAB


def test_parse_phash_rejects_short():
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_phash("abc")


def test_parse_phash_rejects_long():
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_phash("0" * 17)


def test_parse_phash_rejects_non_hex():
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_phash("zzzzzzzzzzzzzzzz")


def test_parse_phash_rejects_non_string():
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_phash(1)


def test_hamming_distance():
    assert ENGINE._hamming(0, 0) == 0
    assert ENGINE._hamming(0, 1) == 1
    assert ENGINE._hamming(int(FAR, 16), 0) == 64


# ==========================================================================
# §二 指纹条目校验（12）
# ==========================================================================
def test_parse_items_accepts_valid():
    items = ENGINE.parse_items([item()])
    assert items[0]["path"] == "a.png"
    assert items[0]["hash_int"] == 0


def test_parse_items_sorts_by_path():
    items = ENGINE.parse_items([item(path="b.png"), item(path="a.png")])
    assert [i["path"] for i in items] == ["a.png", "b.png"]


def test_parse_items_rejects_non_list():
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_items({})


def test_parse_items_rejects_empty():
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_items([])


def test_parse_items_rejects_non_object():
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_items(["a"])


def test_parse_items_requires_path():
    payload = item()
    payload.pop("path")
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_items([payload])


def test_parse_items_requires_phash():
    payload = item()
    payload.pop("phash")
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_items([payload])


def test_parse_items_rejects_bad_width():
    payload = item()
    payload["width"] = "wide"
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_items([payload])


def test_parse_items_rejects_negative_size():
    payload = item()
    payload["size"] = -1
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_items([payload])


def test_parse_items_rejects_negative_mtime():
    payload = item()
    payload["mtime_ns"] = -1
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_items([payload])


def test_parse_items_accepts_zero_dimensions():
    payload = item(width=0, height=0)
    assert ENGINE.parse_items([payload])[0]["width"] == 0


def test_parse_items_accepts_missing_dimension_zero():
    payload = item()
    payload.pop("width")
    with pytest.raises(ENGINE.ItemError):
        ENGINE.parse_items([payload])


# ==========================================================================
# §三 分组（20）
# ==========================================================================
def test_group_identical_hashes():
    groups = ENGINE.group_items(ENGINE.parse_items([item(path="a.png"),
                                                     item(path="b.png")]))
    assert len(groups) == 1
    assert len(groups[0]["members"]) == 2


def test_group_distance_within_threshold():
    groups = ENGINE.group_items(ENGINE.parse_items([
        item(path="a.png", phash=H0),
        item(path="b.png", phash="0000000000000003")]), 2)
    assert len(groups) == 1


def test_group_distance_beyond_threshold():
    groups = ENGINE.group_items(ENGINE.parse_items([
        item(path="a.png", phash=H0),
        item(path="b.png", phash="0000000000000003")]), 1)
    assert groups == []


def test_group_single_item_no_group():
    assert ENGINE.group_items(ENGINE.parse_items([item()])) == []


def test_group_three_chain_single_link():
    payload = [
        item(path="a.png", phash="0000000000000000"),
        item(path="b.png", phash="000000000000000f"),
        item(path="c.png", phash="00000000000000f0"),
    ]
    groups = ENGINE.group_items(ENGINE.parse_items(payload), 8)
    assert len(groups) == 1
    assert len(groups[0]["members"]) == 3


def test_group_chain_breaks_beyond_threshold():
    payload = [
        item(path="a.png", phash="0000000000000000"),
        item(path="b.png", phash="000000000000000f"),
        item(path="c.png", phash="00000000000000f0"),
    ]
    groups = ENGINE.group_items(ENGINE.parse_items(payload), 3)
    assert groups == []


def test_group_two_independent_groups():
    payload = [
        item(path="a.png", phash=H0),
        item(path="b.png", phash=H0, mtime_ns=2),
        item(path="c.png", phash=FAR),
        item(path="d.png", phash=FAR, mtime_ns=2),
    ]
    groups = ENGINE.group_items(ENGINE.parse_items(payload), 8)
    assert len(groups) == 2


def test_group_ids_start_at_one():
    payload = [item(path="a.png"), item(path="b.png")]
    groups = ENGINE.group_items(ENGINE.parse_items(payload))
    assert groups[0]["group_id"] == 1


def test_group_members_carry_phash_hex():
    payload = [item(path="a.png", phash=H1), item(path="b.png", phash=H1)]
    groups = ENGINE.group_items(ENGINE.parse_items(payload))
    assert groups[0]["members"][0]["phash"] == "0000000000000001"


def test_group_members_carry_distance_to_rep():
    payload = [item(path="a.png", phash=H0, width=10, height=10),
               item(path="b.png", phash=H8)]
    groups = ENGINE.group_items(ENGINE.parse_items(payload))
    distances = {m["path"]: m["max_distance_to_rep"] for m in groups[0]["members"]}
    assert distances["a.png"] == 8


def test_group_threshold_rejects_negative():
    with pytest.raises(ValueError):
        ENGINE.group_items(ENGINE.parse_items([item()]), -1)


def test_group_threshold_rejects_non_int():
    with pytest.raises(ValueError):
        ENGINE.group_items(ENGINE.parse_items([item()]), "8")


def test_group_separates_unrelated():
    payload = [item(path="a.png", phash=H0),
               item(path="b.png", phash=FAR)]
    assert ENGINE.group_items(ENGINE.parse_items(payload)) == []


def test_group_zero_threshold_still_groups_identical():
    payload = [item(path="a.png", phash=H0), item(path="b.png", phash=H0)]
    assert len(ENGINE.group_items(ENGINE.parse_items(payload), 0)) == 1


def test_group_membership_is_deterministic():
    payload = [item(path="b.png", phash=H0), item(path="a.png", phash=H0)]
    first = ENGINE.group_items(ENGINE.parse_items(payload))
    second = ENGINE.group_items(ENGINE.parse_items(list(reversed(payload))))
    assert first == second


def test_group_order_by_path():
    payload = [item(path="c.png", phash=H0), item(path="a.png", phash=H0),
               item(path="b.png", phash=H0)]
    members = ENGINE.group_items(ENGINE.parse_items(payload))[0]["members"]
    assert [m["path"] for m in members] == ["a.png", "b.png", "c.png"]


def test_group_handles_five_members():
    payload = [item(path="%d.png" % i, phash=H0) for i in range(5)]
    groups = ENGINE.group_items(ENGINE.parse_items(payload))
    assert len(groups[0]["members"]) == 5


def test_group_independent_of_input_order():
    a = [item(path="a.png", phash=H0), item(path="b.png", phash=H0),
         item(path="c.png", phash=FAR), item(path="d.png", phash=FAR)]
    assert ENGINE.group_items(ENGINE.parse_items(a)) == \
        ENGINE.group_items(ENGINE.parse_items(list(reversed(a))))


def test_group_empty_when_all_far():
    payload = [item(path="a.png", phash="0000000000000000"),
               item(path="b.png", phash="00000000ffffffff")]
    assert ENGINE.group_items(ENGINE.parse_items(payload)) == []


def test_group_real_sample_six_groups():
    data = load_json(os.path.join(DATA_DIR, "phash-cases.json"))
    items = ENGINE.parse_items(data["items"])
    groups = ENGINE.group_items(items, data["threshold"])
    assert len(groups) == 6


def test_group_real_sample_membership_matches_families():
    data = load_json(os.path.join(DATA_DIR, "phash-cases.json"))
    families = {}
    for entry in data["items"]:
        families.setdefault(entry["family_id"], set()).add(entry["path"])
    items = ENGINE.parse_items(data["items"])
    groups = ENGINE.group_items(items, data["threshold"])
    got = [{m["path"] for m in g["members"]} for g in groups]
    assert sorted(got) == sorted(families.values())


# ==========================================================================
# §四 保留建议（14）
# ==========================================================================
def test_representative_highest_resolution():
    members = [
        {"path": "a.png", "width": 10, "height": 10, "size": 9999,
         "mtime_ns": 9},
        {"path": "b.png", "width": 100, "height": 100, "size": 1,
         "mtime_ns": 1},
    ]
    assert ENGINE.choose_representative(members)["path"] == "b.png"


def test_representative_size_tiebreak():
    members = [
        {"path": "a.png", "width": 10, "height": 10, "size": 1, "mtime_ns": 9},
        {"path": "b.png", "width": 10, "height": 10, "size": 2, "mtime_ns": 1},
    ]
    assert ENGINE.choose_representative(members)["path"] == "b.png"


def test_representative_mtime_tiebreak():
    members = [
        {"path": "a.png", "width": 10, "height": 10, "size": 1, "mtime_ns": 1},
        {"path": "b.png", "width": 10, "height": 10, "size": 1, "mtime_ns": 2},
    ]
    assert ENGINE.choose_representative(members)["path"] == "b.png"


def test_representative_path_tiebreak():
    members = [
        {"path": "b.png", "width": 10, "height": 10, "size": 1, "mtime_ns": 1},
        {"path": "a.png", "width": 10, "height": 10, "size": 1, "mtime_ns": 1},
    ]
    assert ENGINE.choose_representative(members)["path"] == "a.png"


def test_representative_real_sample_is_hi_res():
    data = load_json(os.path.join(DATA_DIR, "phash-cases.json"))
    items = ENGINE.parse_items(data["items"])
    groups = ENGINE.group_items(items, data["threshold"])
    for group in groups:
        assert group["representative"]["path"].endswith("hi_res.png")


def test_representative_zero_dimensions_handled():
    members = [
        {"path": "a.png", "width": 0, "height": 0, "size": 1, "mtime_ns": 1},
        {"path": "b.png", "width": 1, "height": 1, "size": 1, "mtime_ns": 1},
    ]
    assert ENGINE.choose_representative(members)["path"] == "b.png"


def test_suggestion_rows_keep_one_per_group():
    data = load_json(os.path.join(DATA_DIR, "phash-cases.json"))
    groups = ENGINE.group_items(ENGINE.parse_items(data["items"]),
                                data["threshold"])
    rows = ENGINE.suggestion_rows(groups)
    keeps = [row for row in rows if row[1] == "keep"]
    assert len(keeps) == len(groups)


def test_suggestion_rows_redundant_count():
    data = load_json(os.path.join(DATA_DIR, "phash-cases.json"))
    groups = ENGINE.group_items(ENGINE.parse_items(data["items"]),
                                data["threshold"])
    rows = ENGINE.suggestion_rows(groups)
    redundant = [row for row in rows if row[1] == "redundant"]
    assert len(redundant) == len(data["items"]) - len(groups)


def test_suggestion_rows_sorted_by_path_within_group():
    groups = [{"group_id": 1,
               "representative": {"path": "a.png"},
               "members": [{"path": "c.png", "phash": H0, "file_size": 1,
                            "width": 1, "height": 1, "mtime_ns": 1,
                            "max_distance_to_rep": 0},
                           {"path": "a.png", "phash": H0, "file_size": 1,
                            "width": 1, "height": 1, "mtime_ns": 1,
                            "max_distance_to_rep": 0}]}]
    rows = ENGINE.suggestion_rows(groups)
    assert [row[2] for row in rows] == ["a.png", "c.png"]


def test_suggestion_header_shape():
    assert ENGINE.RESUGGESTION_HEADER[0] == "group_id"
    assert "suggestion" in ENGINE.RESUGGESTION_HEADER
    assert ENGINE.RESUGGESTION_HEADER[-1] == "max_distance_to_rep"


def test_suggestion_keep_for_representative():
    groups = [{"group_id": 1, "representative": {"path": "a.png"},
               "members": [{"path": "a.png", "phash": H0, "file_size": 1,
                            "width": 1, "height": 1, "mtime_ns": 1,
                            "max_distance_to_rep": 0}]}]
    assert ENGINE.suggestion_rows(groups)[0][1] == "keep"


def test_default_threshold_is_8():
    assert ENGINE.DEFAULT_THRESHOLD == 8


def test_default_hash_size_is_8():
    assert ENGINE.DEFAULT_HASH_SIZE == 8


def test_member_distance_non_negative():
    data = load_json(os.path.join(DATA_DIR, "phash-cases.json"))
    groups = ENGINE.group_items(ENGINE.parse_items(data["items"]),
                                data["threshold"])
    for group in groups:
        for member in group["members"]:
            assert member["max_distance_to_rep"] >= 0


# ==========================================================================
# §五 器官端到端（25）
# ==========================================================================
def test_organ_dupes_six_fail_groups():
    findings = evaluate(load_json(DUPES_SAMPLE))
    groups = [f for f in findings if f.rule_id.startswith("picrecall.group:")]
    assert len(groups) == 6
    assert all(f.verdict == FAIL for f in groups)


def test_organ_dupes_total_counts():
    findings = evaluate(load_json(DUPES_SAMPLE))
    counts = report(findings).summary()["verdicts"]
    assert counts[FAIL] == 6
    assert counts[PASS] == 7
    assert counts[NOT_APPLICABLE] == 12


def test_organ_dupes_rc_blocked():
    assert report(evaluate(load_json(DUPES_SAMPLE))).exit_code() == 1


def test_organ_dupes_summary_counts():
    findings = evaluate(load_json(DUPES_SAMPLE))
    summary = next(f for f in findings if f.rule_id == "picrecall.summary")
    assert summary.evidence["groups"] == 6
    assert summary.evidence["items"] == 18


def test_organ_dupes_group_evidence_keep():
    findings = evaluate(load_json(DUPES_SAMPLE))
    group = next(f for f in findings if f.rule_id == "picrecall.group:1")
    assert group.evidence["keep"].endswith("hi_res.png")
    assert len(group.evidence["members"]) == 3


def test_organ_dupes_keep_member_pass():
    findings = evaluate(load_json(DUPES_SAMPLE))
    keep = next(f for f in findings
                if f.rule_id.endswith("dup_0001_hi_res.png"))
    assert keep.verdict == PASS
    assert keep.anchor.clause_id == "contract.keep"


def test_organ_dupes_redundant_member_na():
    findings = evaluate(load_json(DUPES_SAMPLE))
    redundant = next(f for f in findings
                     if f.rule_id.endswith("dup_0001_base.png"))
    assert redundant.verdict == NOT_APPLICABLE
    assert redundant.anchor.clause_id == "contract.readonly"


def test_organ_dupes_member_evidence_suggestion():
    findings = evaluate(load_json(DUPES_SAMPLE))
    member = next(f for f in findings if f.rule_id.endswith("dup_0001_base.png"))
    assert member.evidence["suggestion"] == "redundant"


def test_organ_clean_no_groups():
    findings = evaluate(load_json(CLEAN_SAMPLE))
    assert len(findings) == 1
    assert findings[0].verdict == PASS
    assert findings[0].evidence["groups"] == 0


def test_organ_clean_rc_zero():
    assert report(evaluate(load_json(CLEAN_SAMPLE))).exit_code() == 0


def test_organ_threshold_0_reduces_members():
    data = load_json(DUPES_SAMPLE)
    data["dedupe"] = dict(data["dedupe"], threshold=0)
    findings = evaluate(data)
    summary = next(f for f in findings if f.rule_id == "picrecall.summary")
    grouped = len([f for f in findings if f.rule_id.startswith("picrecall.group:")])
    assert grouped <= 6
    assert summary.evidence["threshold"] == 0


def test_organ_threshold_changes_group_counts():
    loose = evaluate(load_json(DUPES_SAMPLE))
    tight = evaluate(dict(load_json(DUPES_SAMPLE), dedupe=dict(
        load_json(DUPES_SAMPLE)["dedupe"], threshold=0)))
    loose_summary = next(f for f in loose if f.rule_id == "picrecall.summary")
    tight_summary = next(f for f in tight if f.rule_id == "picrecall.summary")
    assert tight_summary.evidence["groups"] <= loose_summary.evidence["groups"]


def test_organ_requires_case_id():
    subject_ = load_json(DUPES_SAMPLE)
    subject_.pop("case_id")
    with pytest.raises(ValueError):
        evaluate(subject_)


def test_organ_requires_dedupe_section():
    with pytest.raises(ValueError):
        evaluate({"case_id": "x"})


def test_organ_rejects_unknown_top_level():
    subject_ = load_json(DUPES_SAMPLE)
    subject_["future"] = 1
    with pytest.raises(ValueError):
        evaluate(subject_)


def test_organ_rejects_unknown_dedupe_field():
    subject_ = load_json(DUPES_SAMPLE)
    subject_["dedupe"]["future"] = 1
    with pytest.raises(ValueError):
        evaluate(subject_)


def test_organ_rejects_empty_items():
    with pytest.raises(ValueError):
        evaluate(subject([]))


def test_organ_rejects_bad_items_type():
    with pytest.raises(ValueError):
        evaluate({"case_id": "x", "dedupe": {"items": "nope"}})


def test_organ_rejects_bad_phash():
    with pytest.raises(ValueError):
        evaluate(subject([item(phash="xyz")]))


def test_organ_rejects_negative_threshold():
    with pytest.raises(ValueError):
        evaluate(subject([item(), item()], threshold=-1))


def test_organ_wrong_basis_version():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(load_json(DUPES_SAMPLE), Basis.empty("0"))


def test_organ_missing_clause():
    with pytest.raises(BasisMissing):
        PACK_MOD.evaluate(load_json(DUPES_SAMPLE),
                          Basis(version=REG.VERSION, clauses=[]))


def test_organ_deterministic():
    payload = load_json(DUPES_SAMPLE)
    first = [f.as_dict() for f in evaluate(payload)]
    second = [f.as_dict() for f in evaluate(payload)]
    assert first == second


def test_organ_single_item_summary_only():
    findings = evaluate(subject([item()]))
    assert len(findings) == 1
    assert findings[0].evidence["groups"] == 0


def test_organ_group_anchor_is_dedupe_contract():
    findings = evaluate(load_json(DUPES_SAMPLE))
    group = next(f for f in findings if f.rule_id == "picrecall.group:1")
    assert group.anchor.clause_id == "contract.dedupe"


# ==========================================================================
# §六 只读纪律（6）
# ==========================================================================
def test_engine_has_no_deletion_calls():
    dangerous = {"os.remove", "os.unlink", "os.rename", "os.replace",
                 "os.rmdir", "shutil.rmtree", "shutil.move"}
    tree = ast.parse(open(os.path.join(PACK_DIR, "engine.py"),
                          encoding="utf-8").read())
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name):
            resolved = "%s.%s" % (node.func.value.id, node.func.attr)
            if resolved in dangerous:
                hits.append(resolved)
    assert hits == []


def test_pack_has_no_file_io_imports():
    tree = ast.parse(open(os.path.join(PACK_DIR, "__init__.py"),
                          encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "os" not in imported
    assert "shutil" not in imported


def test_no_write_actions_in_engine():
    source = open(os.path.join(PACK_DIR, "engine.py"), encoding="utf-8").read()
    for banned in ("open(", ".write(", "unlink", "remove(", "rmtree"):
        assert banned not in source, banned


def test_readonly_clause_registered():
    assert basis().clause("contract.readonly") is not None


def test_readonly_clause_text_mentions_no_delete():
    text = basis().clause("contract.readonly").text
    assert "不得删除" in text and "改名" in text


def test_fail_does_not_imply_deletion():
    findings = evaluate(load_json(DUPES_SAMPLE))
    for finding in findings:
        if finding.verdict == FAIL:
            assert "不删除" in finding.message


# ==========================================================================
# §七 CLI（6）
# ==========================================================================
def test_cli_dupes_blocked():
    assert cp_cli.main(["check", SLUG, "--input", DUPES_SAMPLE,
                        "--basis", BASIS_PATH]) == 1


def test_cli_clean_ok():
    assert cp_cli.main(["check", SLUG, "--input", CLEAN_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_missing_basis():
    assert cp_cli.main(["check", SLUG, "--input", CLEAN_SAMPLE]) == 3


def test_cli_bad_input(tmp_path):
    payload = load_json(CLEAN_SAMPLE)
    payload.pop("case_id")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert cp_cli.main(["check", SLUG, "--input", str(path),
                        "--basis", BASIS_PATH]) == 2


def test_cli_unknown_slug():
    assert cp_cli.main(["check", "nope", "--input", CLEAN_SAMPLE,
                        "--basis", BASIS_PATH]) == 3


def test_cli_json_flag_ok():
    assert cp_cli.main(["check", SLUG, "--input", CLEAN_SAMPLE,
                        "--basis", BASIS_PATH, "--json"]) == 0


# ==========================================================================
# §八 数据与边界（8）
# ==========================================================================
def test_pack_registered():
    from clauseproof.packs import BUILTIN_MODULES
    assert SLUG in BUILTIN_MODULES


def test_basis_has_five_clauses():
    assert len(basis()) == 5


def test_basis_ids():
    assert set(basis().clause_ids()) == {
        "contract.dedupe", "contract.keep", "contract.readonly",
        "contract.threshold", "contract.ledger"}


def test_manifest_sha256_matches():
    import hashlib

    manifest = load_json(os.path.join(DATA_DIR, "manifest.json"))
    assert set(manifest["files"]) == set(REG.DATA_FILES)
    for name, record in manifest["files"].items():
        path = os.path.join(DATA_DIR, name)
        assert os.path.getsize(path) == record["bytes"]
        assert hashlib.sha256(open(path, "rb").read()).hexdigest() == \
            record["sha256"]


def test_phash_cases_are_eighteen():
    assert len(load_json(os.path.join(DATA_DIR, "phash-cases.json"))["items"]) == 18


def test_phash_clean_is_three():
    assert len(load_json(os.path.join(DATA_DIR, "phash-clean.json"))["items"]) == 3


def test_threshold_contract_registered():
    assert "阈值" in basis().clause("contract.threshold").text


def test_queue_note_discrepancy_recorded():
    assert "缺陷产品召回" in PACK_MOD.__doc__
    assert "截图" in PACK_MOD.__doc__