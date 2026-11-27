"""器官 ``policy-review`` 判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源判定面（条款切分 / 影子串归一化 / 十类模式匹配 + 否定中和抑制 /
锚点映射 / 三级分级 / 升级条件 / 硬锚点完整性）逐条搬，断言落在「命中 + 偏移 +
锚点 + 等级」上。来源判定层（D1 + D18 机械选 11 文件 / 实跑 95 passed / AST 93）
逐文件处置见 ``docs/policy-review.md`` §6。

来源仓只读；合成规则包一律**内存注入**（模式 + 锚点），不冒充条文原文。
随包 5 份合成样例（文本 + 真值）逐例对账。
"""

import importlib
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from clauseproof import cli as cp_cli  # noqa: E402
from clauseproof.core.basis import Basis  # noqa: E402
from clauseproof.core.ledger import (  # noqa: E402
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Report,
)

PACK_MOD = importlib.import_module("clauseproof.packs.policy-review")
MODEL = importlib.import_module("clauseproof.packs.policy-review.model")
RULES = importlib.import_module("clauseproof.packs.policy-review.rules")
NORMALIZE = importlib.import_module("clauseproof.packs.policy-review.normalize")
SPLITTER = importlib.import_module("clauseproof.packs.policy-review.splitter")
MATCHER = importlib.import_module("clauseproof.packs.policy-review.matcher")
MAPPING = importlib.import_module("clauseproof.packs.policy-review.mapping")
GRADER = importlib.import_module("clauseproof.packs.policy-review.grader")
PIPELINE = importlib.import_module("clauseproof.packs.policy-review.pipeline")
TEMPLATES = importlib.import_module("clauseproof.packs.policy-review.templates")
CONSTANTS = importlib.import_module("clauseproof.packs.policy-review.constants")
ERRORS = importlib.import_module("clauseproof.packs.policy-review.errors")
REG = importlib.import_module("clauseproof.packs.policy-review.registry")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "policy-review")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "policy-review")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
CASE03_SAMPLE = os.path.join(SAMPLES, "policy-case-03.json")
CASE01_SAMPLE = os.path.join(SAMPLES, "policy-case-01.json")
CLEAN_SAMPLE = os.path.join(SAMPLES, "policy-clean.json")
CASES_PATH = os.path.join(DATA_DIR, "synthetic-cases.json")

BASIS = Basis.from_json(BASIS_PATH)
with open(CASES_PATH, "r", encoding="utf-8") as _handle:
    CASES_DATA = json.load(_handle)
CASES = CASES_DATA["cases"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


# --------------------------------------------------------------------------
# 合成夹具（内存注入；规则文本为测试用简写，不冒充条文原文）
# --------------------------------------------------------------------------
def _feature(feature_id="F1", pattern=r"共享|提供"):
    return MODEL.FeatureRule(feature_id, "regex", pattern, "SYNTHETIC",
                             re.compile(pattern))


def _pattern(pattern_id="P01", severity="high", hard=("PIPL-1",), background=(),
             triggers=None, negation=None, neutralizers=None, escalation=(),
             needs_semantic=False):
    data = {
        "pattern_id": pattern_id,
        "name_zh": "SYNTHETIC 模式",
        "severity_base": severity,
        "needs_semantic": needs_semantic,
        "statute_anchors": list(hard),
        "background_anchors": list(background),
        "evidence_date": "2026-10-18",
        "version": "0.1.0",
    }
    return MODEL.PatternRule(
        data,
        triggers or [_feature()],
        negation or [],
        neutralizers or [],
        escalation,
    )


def _anchor(anchor_id="PIPL-1", eligible=True, status="verified",
            text="第一条 SYNTHETIC 条文"):
    return {
        "anchor_id": anchor_id,
        "statute_id": anchor_id.split("-")[0],
        "article": anchor_id.split("-")[-1],
        "anchor_text": text,
        "source_url": "https://example.invalid/synthetic",
        "verified_on": "2026-10-18",
        "status": status,
        "eligible": eligible,
    }


def _library(patterns=None, anchors=None):
    manifest = {"ruleset_version": "0.1.0", "generated_on": "2026-10-18"}
    return MODEL.RulesPackage(
        manifest,
        patterns or [_pattern()],
        anchors if anchors is not None else {"PIPL-1": _anchor()},
    )


def _document(*paragraphs):
    text = "隐私政策\n" + "\n".join(paragraphs) + "\n"
    return text, SPLITTER.split_text(text)


def _clauses_doc(*texts, kind="paragraph"):
    clauses = []
    for index, text in enumerate(texts, 1):
        clauses.append({
            "clause_id": "c-test-%04d" % index,
            "char_start": (index - 1) * 100,
            "char_end": (index - 1) * 100 + len(text),
            "heading_path": [],
            "kind": kind,
            "raw_text": text,
            "compound": False,
            "structural_path": "%04d" % index,
        })
    return {"schema_version": "clauses/1",
            "document": {"sha256": "x" * 12, "char_count": 1000,
                         "clause_count": len(clauses)},
            "clauses": clauses}


def _subject(text, case_id="case-1"):
    return {"case_id": case_id, "text": text}


def _records(subject, basis=None, library=None):
    findings = PACK_MOD.evaluate_with_library(subject, basis or BASIS, library)
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject="test.json", findings=tuple(findings))


def _find(records, rule_id):
    for record in records:
        if record.rule_id == rule_id:
            return record
    raise AssertionError("未找到账本行：%s" % rule_id)


def _write_package(tmp_path, patterns=None, anchors=None, manifest_overrides=None):
    """写一份最小合法规则包（用于加载/校验测试）。"""
    patterns = patterns if patterns is not None else [_pattern()]
    anchors = anchors if anchors is not None else [_anchor()]
    files = {}

    statute_ids = sorted({anchor["statute_id"] for anchor in anchors})
    for statute_id in statute_ids:
        data = {
            "statute_id": statute_id,
            "title": "SYNTHETIC 依据 %s" % statute_id,
            "source_url": "https://example.invalid/synthetic",
            "verified_on": "2026-10-18",
            "version": "2026-10-18",
            "article_count": 0,
            "articles": [],
        }
        for anchor in anchors:
            if anchor["statute_id"] == statute_id:
                data["articles"].append({
                    "anchor_id": anchor["anchor_id"],
                    "article": anchor["article"],
                    "anchor_text": anchor["anchor_text"],
                    "status": anchor["status"],
                })
        data["article_count"] = len(data["articles"])
        name = RULES.statute_file(statute_id)
        (tmp_path / name).write_text(json.dumps(data, ensure_ascii=False),
                                     encoding="utf-8")
        files[name] = (tmp_path / name).read_bytes()

    pattern_data = {}
    for pattern in patterns:
        data = {
            "pattern_id": pattern.pattern_id,
            "name_zh": pattern.name_zh,
            "severity_base": pattern.severity_base,
            "needs_semantic": pattern.needs_semantic,
            "trigger_features": [
                {"feature_id": feature.feature_id, "type": "regex",
                 "value": feature.value} for feature in pattern.trigger_features],
            "negation": [],
            "neutralizers": [],
            "escalation": [dict(rule) for rule in pattern.escalation],
            "statute_anchors": list(pattern.statute_anchors),
            "background_anchors": list(pattern.background_anchors),
            "evidence_date": pattern.evidence_date,
            "version": pattern.version,
        }
        pattern_data[pattern.pattern_id] = data
        name = RULES.pattern_file(pattern.pattern_id)
        (tmp_path / name).write_text(json.dumps(data, ensure_ascii=False),
                                     encoding="utf-8")
        files[name] = (tmp_path / name).read_bytes()

    import hashlib
    manifest = {
        "schema": RULES.SCHEMA_MANIFEST,
        "version": "2026-10-18",
        "ruleset_version": "0.1.0",
        "generated_on": "2026-10-18",
        "patterns": list(CONSTANTS.EXPECTED_PATTERN_IDS),
        "statutes": statute_ids,
        "files": {name: {"bytes": len(blob),
                         "sha256": hashlib.sha256(blob).hexdigest()}
                  for name, blob in files.items()},
    }
    for pattern_id in CONSTANTS.EXPECTED_PATTERN_IDS:
        if pattern_id not in pattern_data:
            filler = dict(pattern_data[list(pattern_data)[0]])
            filler["pattern_id"] = pattern_id
            name = RULES.pattern_file(pattern_id)
            (tmp_path / name).write_text(json.dumps(filler, ensure_ascii=False),
                                         encoding="utf-8")
            blob = (tmp_path / name).read_bytes()
            manifest["files"][name] = {"bytes": len(blob),
                                       "sha256": hashlib.sha256(blob).hexdigest()}
    manifest.update(manifest_overrides or {})
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------
# §一 影子串归一化
# --------------------------------------------------------------------------
def test_shadow_fullwidth_letters_folded():
    assert NORMALIZE.shadow_text("ＡＢＣ１２３") == "abc123"


def test_shadow_chinese_punctuation_preserved():
    assert "，" in NORMALIZE.shadow_text("你好，世界")


def test_shadow_uppercase_lowered():
    assert NORMALIZE.shadow_text("Privacy") == "privacy"


def test_shadow_whitespace_collapsed():
    assert NORMALIZE.shadow_text("a \n\t b") == "a b"


def test_shadow_span_maps_back():
    text = "我 们 共享信息"
    shadow = NORMALIZE.build_shadow(text)
    start = shadow.text.index("共享")
    original_start, original_end = shadow.to_original_span(start, start + 2)
    assert text[original_start:original_end] == "共享"


def test_shadow_span_rejects_empty():
    shadow = NORMALIZE.build_shadow("abc")
    with pytest.raises(ValueError):
        shadow.to_original_span(1, 1)


def test_shadow_span_rejects_out_of_range():
    shadow = NORMALIZE.build_shadow("abc")
    with pytest.raises(ValueError):
        shadow.to_original_span(0, 9)


def test_shadow_length_matches_text():
    shadow = NORMALIZE.build_shadow("abc  def")
    assert len(shadow) == len(shadow.text) == 7


# --------------------------------------------------------------------------
# §二 条款切分
# --------------------------------------------------------------------------
def test_split_numbered_heading():
    doc = SPLITTER.split_text("1. 信息收集\n我们收集必要信息。\n")
    kinds = [clause["kind"] for clause in doc["clauses"]]
    assert kinds[0] == "heading"


def test_split_article_heading():
    doc = SPLITTER.split_text("第一条 总则\n本政策适用。\n")
    assert doc["clauses"][0]["kind"] == "heading"
    assert "第一条" in doc["clauses"][0]["raw_text"]


def test_split_short_heading():
    doc = SPLITTER.split_text("争议解决\n双方协商解决。\n")
    assert doc["clauses"][0]["kind"] == "heading"


def test_split_list_item():
    doc = SPLITTER.split_text("- 手机号\n")
    assert doc["clauses"][0]["kind"] == "list_item"


def test_split_appendix_row():
    doc = SPLITTER.split_text("信息类型 | 保存期限 | 用途\n")
    assert doc["clauses"][0]["kind"] == "appendix_row"


def test_split_paragraph_merges_lines():
    doc = SPLITTER.split_text("第一段内容。\n第二段内容。\n")
    assert len(doc["clauses"]) == 1
    assert doc["clauses"][0]["kind"] == "paragraph"


def test_split_offsets_slice_back():
    text = "标题\n正文一句。\n"
    doc = SPLITTER.split_text(text)
    for clause in doc["clauses"]:
        assert text[clause["char_start"]:clause["char_end"]] == clause["raw_text"]


def test_split_document_meta():
    text = "标题\n正文。\n"
    doc = SPLITTER.split_text(text)
    assert doc["document"]["char_count"] == len(text)
    assert doc["document"]["clause_count"] == len(doc["clauses"])
    assert len(doc["document"]["sha256"]) == 64


def test_split_same_input_same_output():
    text = "标题\n正文。\n"
    assert SPLITTER.split_text(text) == SPLITTER.split_text(text)


def test_split_compound_flag():
    doc = SPLITTER.split_text("我们收集信息；并用于推荐。\n")
    assert doc["clauses"][0]["compound"] is True


def test_split_empty_text_rejected():
    with pytest.raises(ERRORS.UsageError):
        SPLITTER.split_text("   ")


def test_split_non_string_rejected():
    with pytest.raises(ERRORS.UsageError):
        SPLITTER.split_text(None)


def test_split_heading_path_stack():
    text = "1. 收集\n1.1 范围\n我们收集手机号。\n"
    doc = SPLITTER.split_text(text)
    assert doc["clauses"][-1]["heading_path"] == ["1. 收集", "1.1 范围"]


# --------------------------------------------------------------------------
# §三 匹配引擎
# --------------------------------------------------------------------------
def test_match_hit_offsets_slice_back():
    text, doc = _document("我们将信息共享给合作伙伴。")
    hits = MATCHER.match_document(doc, _library(), text)["hits"]
    assert hits
    feature = hits[0]["trigger_features"][0]
    assert text[feature["char_start"]:feature["char_end"]] == feature["matched_text"]


def test_match_skips_heading():
    doc = SPLITTER.split_text("共享信息\n正文无命中。\n")
    hits = MATCHER.match_document(doc, _library())["hits"]
    assert hits == []


def test_match_negation_suppresses():
    pattern = _pattern(negation=[_feature("N1", r"不会|不共享")])
    text, doc = _document("我们不会共享你的信息。")
    hits = MATCHER.match_document(doc, _library([pattern]))["hits"]
    assert hits == []


def test_match_neutralizer_suppresses():
    pattern = _pattern(neutralizers=[_feature("Z1", r"依法")])
    text, doc = _document("依法共享信息。")
    hits = MATCHER.match_document(doc, _library([pattern]))["hits"]
    assert hits == []


def test_match_multiple_features_deduped():
    pattern = _pattern(triggers=[
        _feature("F1", r"共享"), _feature("F1", r"共享")])
    text, doc = _document("共享信息。")
    hits = MATCHER.match_document(doc, _library([pattern]))["hits"]
    assert len(hits[0]["trigger_features"]) == 1


def test_match_needs_semantic_flag():
    pattern = _pattern(needs_semantic=True)
    text, doc = _document("共享信息。")
    hits = MATCHER.match_document(doc, _library([pattern]))["hits"]
    assert hits[0]["needs_semantic"] is True


def test_match_document_sha_in_output():
    text, doc = _document("共享信息。")
    hits = MATCHER.match_document(doc, _library(), text)
    assert hits["document"]["sha256"] == doc["document"]["sha256"]


def test_match_rejects_mismatched_raw_text():
    text, doc = _document("共享信息。")
    doc["clauses"][-1]["raw_text"] = "被篡改"
    with pytest.raises(ValueError):
        MATCHER.match_document(doc, _library(), text)


def test_match_no_hits_document():
    text, doc = _document("本政策不涉及第三方。")
    hits = MATCHER.match_document(doc, _library(), text)
    assert hits["hits"] == []


def test_match_two_patterns_same_clause():
    one = _pattern("P01")
    two = _pattern("P02")
    text, doc = _document("共享信息。")
    hits = MATCHER.match_document(doc, _library([one, two]), text)["hits"]
    assert {hit["pattern_id"] for hit in hits} == {"P01", "P02"}


# --------------------------------------------------------------------------
# §四 锚点映射
# --------------------------------------------------------------------------
def _hits_doc(clause_id="c-test-0001", pattern_id="P01"):
    return {"schema_version": "hits/1", "ruleset_version": "0.1.0",
            "document": {}, "hits": [{"clause_id": clause_id,
                                      "pattern_id": pattern_id,
                                      "kind": "deterministic",
                                      "trigger_features": [],
                                      "needs_semantic": False}]}


def test_mapping_hard_anchor():
    mapping = MAPPING.map_hits(_hits_doc(), _library())["mappings"][0]
    assert mapping["anchor_ids"] == ["PIPL-1"]
    assert mapping["pending_anchor_ids"] == []
    assert mapping["anchors"][0]["strength"] == "hard"


def test_mapping_pending_anchor():
    library = _library(anchors={"PIPL-1": _anchor(eligible=False, status="pending")})
    mapping = MAPPING.map_hits(_hits_doc(), library)["mappings"][0]
    assert mapping["anchor_ids"] == []
    assert mapping["pending_anchor_ids"] == ["PIPL-1"]


def test_mapping_background_anchor():
    pattern = _pattern(severity="notice", hard=(), background=("CIVIL-496",))
    library = _library([pattern], {})
    mapping = MAPPING.map_hits(_hits_doc(), library)["mappings"][0]
    assert mapping["anchor_ids"] == []
    assert mapping["anchors"][0]["strength"] == "background"
    assert mapping["anchors"][0]["statute_id"] == "CIVIL"


def test_mapping_unknown_pattern():
    with pytest.raises(ERRORS.UsageError):
        MAPPING.map_hits(_hits_doc(pattern_id="P99"), _library())


def test_mapping_document_meta():
    mapping = MAPPING.map_hits(_hits_doc(), _library())
    assert mapping["schema_version"] == "mapping/1"
    assert mapping["ruleset_version"] == "0.1.0"


# --------------------------------------------------------------------------
# §五 分级器
# --------------------------------------------------------------------------
def _grade_case(paragraphs, patterns=None, anchors=None):
    text, doc = _document(*paragraphs)
    library = _library(patterns, anchors)
    hits = MATCHER.match_document(doc, library, text)
    mapping_doc = MAPPING.map_hits(hits, library)
    return GRADER.grade_hits(hits, mapping_doc, library, doc), doc


def test_grade_high_with_hard_anchor():
    findings, _ = _grade_case(["我们将共享信息。"])
    assert findings[0]["level"] == "high"
    assert findings[0]["anchor_ids"] == ["PIPL-1"]


def test_grade_high_without_anchor_downgraded():
    pattern = _pattern(hard=())
    findings, _ = _grade_case(["我们将共享信息。"], [pattern], {})
    assert findings[0]["level"] == "medium"
    assert findings[0]["anchor_ids"] == []


def test_grade_high_with_pending_anchor_downgraded():
    library_anchors = {"PIPL-1": _anchor(eligible=False, status="pending")}
    findings, _ = _grade_case(["我们将共享信息。"], None, library_anchors)
    assert findings[0]["level"] == "medium"


def test_grade_notice_pattern_without_anchor():
    pattern = _pattern(severity="notice", hard=(), background=("CIVIL-496",))
    findings, _ = _grade_case(["我们将共享信息。"], [pattern], {})
    assert findings[0]["level"] == "notice"
    assert findings[0]["anchor_ids"] == []


def test_grade_medium_base():
    pattern = _pattern(severity="medium")
    findings, _ = _grade_case(["我们将共享信息。"], [pattern], None)
    assert findings[0]["level"] == "medium"


def test_grade_escalation_upgrades():
    companion = _pattern("P02")
    escalation = ({"level": "high", "pattern_id": "P02"},)
    main = _pattern("P01", severity="medium", escalation=escalation)
    findings, _ = _grade_case(["我们将共享信息。"], [main, companion], None)
    assert {finding["pattern_id"]: finding["level"]
            for finding in findings}["P01"] == "high"


def test_grade_escalation_requires_companion():
    escalation = ({"level": "high", "pattern_id": "P02"},)
    main = _pattern("P01", severity="medium", escalation=escalation)
    findings, _ = _grade_case(["我们将共享信息。"], [main], None)
    assert findings[0]["level"] == "medium"


def test_grade_escalation_never_downgrades():
    companion = _pattern("P02")
    escalation = ({"level": "medium", "pattern_id": "P02"},)
    main = _pattern("P01", severity="high", escalation=escalation)
    findings, _ = _grade_case(["我们将共享信息。"], [main, companion], None)
    assert {finding["pattern_id"]: finding["level"]
            for finding in findings}["P01"] == "high"


def test_grade_sort_order_high_first():
    notice = _pattern("P02", severity="notice", hard=(), background=("CIVIL-1",),
                      triggers=[_feature("F1", r"仲裁")])
    findings, _ = _grade_case(["我们将共享信息。", "争议提交仲裁。"],
                              [_pattern("P01"), notice], None)
    assert [finding["level"] for finding in findings] == ["high", "notice"]


def test_grade_finding_offsets_are_clause_span():
    findings, doc = _grade_case(["我们将共享信息。"])
    clause = [item for item in doc["clauses"] if item["kind"] != "heading"][0]
    assert findings[0]["char_start"] == clause["char_start"]
    assert findings[0]["char_end"] == clause["char_end"]


def test_truncate_excerpt_short_text():
    assert GRADER.truncate_excerpt("短文本") == "短文本"


def test_truncate_excerpt_long_text():
    text = "字" * (CONSTANTS.EXCERPT_MAX_CHARS + 10)
    result = GRADER.truncate_excerpt(text)
    assert result.endswith("…")
    assert len(result) == CONSTANTS.EXCERPT_MAX_CHARS


def test_grade_templates_non_empty():
    findings, _ = _grade_case(["我们将共享信息。"])
    assert findings[0]["explanation"].strip()
    assert findings[0]["suggestion"].strip()


def test_grade_finding_carries_pattern_id():
    findings, _ = _grade_case(["我们将共享信息。"])
    assert findings[0]["pattern_id"] == "P01"


def test_grade_unknown_pattern():
    doc = _clauses_doc("共享信息。")
    hits = _hits_doc(clause_id="c-test-0001", pattern_id="P99")
    with pytest.raises(ERRORS.UsageError):
        GRADER.grade_hits(hits, MAPPING.map_hits(hits, _library()), _library(), doc)


def test_grade_missing_mapping():
    doc = _clauses_doc("共享信息。")
    hits = _hits_doc()
    with pytest.raises(ERRORS.UsageError):
        GRADER.grade_hits(hits, {"mappings": []}, _library(), doc)


def test_grade_missing_clause():
    hits = _hits_doc()
    mapping_doc = MAPPING.map_hits(hits, _library())
    other = _clauses_doc("别的条款")
    other["clauses"][0]["clause_id"] = "c-other-0001"
    with pytest.raises(ERRORS.UsageError):
        GRADER.grade_hits(hits, mapping_doc, _library(), other)


def test_grade_sha_mismatch():
    clauses = _clauses_doc("共享信息。")
    hits = _hits_doc()
    hits["document"] = {"sha256": "a" * 12}
    clauses["document"]["sha256"] = "b" * 12
    with pytest.raises(ERRORS.UsageError):
        GRADER.grade_hits(hits, MAPPING.map_hits(hits, _library()), _library(), clauses)


def test_grade_skips_semantic_rejected():
    doc = _clauses_doc("共享信息。")
    hits = _hits_doc()
    hits["hits"][0]["kind"] = "semantic_rejected"
    findings = GRADER.grade_hits(hits, {"mappings": []}, _library(), doc)
    assert findings == []


def test_hard_anchor_ids_excludes_background():
    mapping = {"anchor_ids": ["CIVIL-1", "PIPL-1"],
               "anchors": [{"anchor_id": "CIVIL-1", "strength": "hard"},
                           {"anchor_id": "PIPL-1", "strength": "hard"}]}
    assert GRADER.hard_anchor_ids(mapping) == ["PIPL-1"]


def test_hard_anchor_ids_dedupes():
    mapping = {"anchor_ids": ["PIPL-1", "PIPL-1"],
               "anchors": [{"anchor_id": "PIPL-1", "strength": "hard"}]}
    assert GRADER.hard_anchor_ids(mapping) == ["PIPL-1"]


# --------------------------------------------------------------------------
# §六 规则包加载与校验
# --------------------------------------------------------------------------
def test_load_library_coordinate():
    library = PIPELINE.load_library()
    coordinate = library.coordinate()
    assert coordinate["ruleset_version"] == "0.1.0"
    assert coordinate["patterns"] == 10
    assert coordinate["statutes"] == 5
    assert coordinate["anchors"] == 165
    assert coordinate["hard_anchors"] == 165
    assert coordinate["pending_anchors"] == 0


def test_load_library_pattern_lookup():
    library = PIPELINE.load_library()
    assert library.pattern("P01").name_zh == "数据共享给第三方"
    assert library.pattern("P99") is None


def test_load_library_anchor_lookup():
    library = PIPELINE.load_library()
    anchor = library.anchor("PIPL-31")
    assert anchor["eligible"] is True
    assert "未成年人" in anchor["anchor_text"]


def test_load_library_missing_manifest(tmp_path):
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


def test_load_library_bad_schema(tmp_path):
    _write_package(tmp_path, manifest_overrides={"schema": "nope"})
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


def test_load_library_sha_mismatch(tmp_path):
    _write_package(tmp_path)
    target = tmp_path / RULES.pattern_file("P01")
    target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ERRORS.RulesPackageError) as info:
        RULES.load_library(str(tmp_path))
    assert "sha256" in str(info.value) or "字节数" in str(info.value)


def test_load_library_missing_pattern(tmp_path):
    _write_package(tmp_path)
    (tmp_path / RULES.pattern_file("P10")).unlink()
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


def test_load_library_bad_regex(tmp_path):
    bad = _pattern()
    bad.trigger_features = (MODEL.FeatureRule("F1", "regex", "(", "", re.compile("x")),)
    _write_package(tmp_path, patterns=[bad])
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


def test_load_library_unknown_anchor(tmp_path):
    _write_package(tmp_path, patterns=[_pattern(hard=("PIPL-999",))])
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


def test_load_library_background_prefix(tmp_path):
    _write_package(tmp_path, patterns=[_pattern(severity="notice", hard=(),
                                                background=("BAD-1",))])
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


def test_load_library_hard_and_background_overlap(tmp_path):
    _write_package(tmp_path, patterns=[_pattern(background=("PIPL-1",))])
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


def test_load_library_no_hard_requires_notice(tmp_path):
    _write_package(tmp_path, patterns=[_pattern(severity="high", hard=())])
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


def test_load_library_accepts_valid_package(tmp_path):
    _write_package(tmp_path)
    library = RULES.load_library(str(tmp_path))
    assert library.pattern("P01") is not None


def test_validate_statute_article_count_mismatch(tmp_path):
    _write_package(tmp_path)
    path = tmp_path / RULES.statute_file("PIPL")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["article_count"] = 99
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    import hashlib
    blob = path.read_bytes()
    manifest["files"][path.name] = {"bytes": len(blob),
                                    "sha256": hashlib.sha256(blob).hexdigest()}
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


def test_validate_article_status(tmp_path):
    anchors = [dict(_anchor(), status="magic", eligible=False)]
    _write_package(tmp_path, anchors=anchors)
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


def test_validate_empty_anchor_text(tmp_path):
    anchors = [dict(_anchor(), anchor_text="")]
    _write_package(tmp_path, anchors=anchors)
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


def test_escalation_self_reference(tmp_path):
    escalation = ({"level": "high", "pattern_id": "P01"},)
    _write_package(tmp_path, patterns=[_pattern(escalation=escalation)])
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


def test_escalation_unknown_pattern(tmp_path):
    escalation = ({"level": "high", "pattern_id": "P99"},)
    _write_package(tmp_path, patterns=[_pattern(escalation=escalation)])
    with pytest.raises(ERRORS.RulesPackageError):
        RULES.load_library(str(tmp_path))


# --------------------------------------------------------------------------
# §七 输入契约 / 条文库 / 锚点
# --------------------------------------------------------------------------
def test_subject_requires_case_id():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"text": "我们共享信息。"}, BASIS)


def test_subject_requires_text():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c"}, BASIS)


def test_subject_text_must_be_string():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "text": 1}, BASIS)


def test_subject_text_must_not_be_blank():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "text": "   "}, BASIS)


def test_subject_rejects_unknown_key():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "text": "共享。", "extra": 1}, BASIS)


def test_basis_version_mismatch_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(_subject("共享信息。"), Basis.empty("1999-01-01"))


def test_basis_missing_clause_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(_subject("共享信息。"), Basis(REG.VERSION))


def test_contract_scalar_requires_same_version():
    assert BASIS.version == REG.VERSION


# --------------------------------------------------------------------------
# §八 账本映射 / 报告 / 退出码 / CLI
# --------------------------------------------------------------------------
def _sample_subject(path):
    return load_json(path)


def test_case03_levels():
    report = _records(_sample_subject(CASE03_SAMPLE))
    assert report.summary()["verdicts"]["fail"] == 2  # 1 high + summary


def test_case03_exit_one():
    assert _records(_sample_subject(CASE03_SAMPLE)).exit_code() == 1


def test_case01_exit_one():
    assert _records(_sample_subject(CASE01_SAMPLE)).exit_code() == 1


def test_clean_exit_zero():
    assert _records(_sample_subject(CLEAN_SAMPLE)).exit_code() == 0


def test_clean_has_no_findings():
    report = _records(_sample_subject(CLEAN_SAMPLE))
    assert all(not record.rule_id.startswith("policy.finding:")
               for record in report.findings)


def test_rules_finding_anchor():
    record = _find(_records(_sample_subject(CASE03_SAMPLE)).findings,
                   PACK_MOD.RULE_RULES)
    assert record.verdict == PASS
    assert record.anchor.clause_id == PACK_MOD.CLAUSE_RULES
    assert record.evidence["patterns"] == 10


def test_split_finding_anchor():
    record = _find(_records(_sample_subject(CASE03_SAMPLE)).findings,
                   PACK_MOD.RULE_SPLIT)
    assert record.verdict == PASS
    assert record.anchor.clause_id == PACK_MOD.CLAUSE_SPLIT
    assert record.evidence["clause_count"] > 0


def test_high_finding_is_fail_with_hard_anchor():
    report = _records(_sample_subject(CASE03_SAMPLE))
    high = [record for record in report.findings
            if record.rule_id.startswith("policy.finding:")
            and record.verdict == FAIL]
    assert len(high) == 1
    assert high[0].anchor.clause_id.startswith("PIPL-") or \
        high[0].anchor.clause_id.startswith("DATA_SEC-")


def test_medium_finding_is_pass():
    report = _records(_sample_subject(CASE03_SAMPLE))
    medium = [record for record in report.findings
              if record.rule_id.startswith("policy.finding:")
              and record.evidence["level"] == "medium"]
    assert medium and all(record.verdict == PASS for record in medium)


def test_notice_finding_anchor_is_notice_contract():
    report = _records(_sample_subject(CASE03_SAMPLE))
    notices = [record for record in report.findings
               if record.rule_id.startswith("policy.finding:")
               and record.evidence["level"] == "notice"]
    assert notices
    assert all(record.anchor.clause_id == PACK_MOD.CLAUSE_NOTICE for record in notices)


def test_background_anchor_records():
    report = _records(_sample_subject(CASE03_SAMPLE))
    background = [record for record in report.findings
                  if record.rule_id.startswith(PACK_MOD.RULE_ANCHOR_BACKGROUND + ":")]
    assert background
    assert all(record.verdict == NOT_APPLICABLE for record in background)
    assert all(record.anchor is None for record in background)


def test_no_pending_anchor_records_for_shipped_pack():
    report = _records(_sample_subject(CASE03_SAMPLE))
    assert not [record for record in report.findings
                if record.rule_id.startswith(PACK_MOD.RULE_ANCHOR_PENDING + ":")]


def test_pending_anchor_record_with_injected_library():
    library = _library(anchors={"PIPL-1": _anchor(eligible=False, status="pending")})
    findings = PACK_MOD.evaluate_with_library(_subject("我们将共享信息。"),
                                              BASIS, library)
    pending = [finding for finding in findings
               if finding.rule_id == "policy.anchor.pending:PIPL-1"]
    assert pending
    assert pending[0].verdict == NOT_APPLICABLE


def test_summary_fail_when_high():
    record = _find(_records(_sample_subject(CASE03_SAMPLE)).findings,
                   PACK_MOD.RULE_SUMMARY)
    assert record.verdict == FAIL
    assert record.anchor.clause_id == PACK_MOD.CLAUSE_SUMMARY


def test_summary_pass_when_clean():
    record = _find(_records(_sample_subject(CLEAN_SAMPLE)).findings,
                   PACK_MOD.RULE_SUMMARY)
    assert record.verdict == PASS
    assert record.evidence["high"] == 0


def test_every_non_na_record_has_anchor():
    report = _records(_sample_subject(CASE03_SAMPLE))
    for record in report.findings:
        if record.verdict != NOT_APPLICABLE:
            assert record.anchor is not None


def test_report_deterministic():
    first = _records(_sample_subject(CASE03_SAMPLE)).as_dict()["records"]
    second = _records(_sample_subject(CASE03_SAMPLE)).as_dict()["records"]
    assert [item["id"] for item in first] == [item["id"] for item in second]


def test_cli_list_contains_slug(capsys):
    assert cp_cli.main(["list"]) == 0
    assert SLUG in capsys.readouterr().out


def test_cli_check_case03_rc1():
    assert cp_cli.main(["check", SLUG, "--input", CASE03_SAMPLE,
                        "--basis", BASIS_PATH]) == 1


def test_cli_check_clean_rc0():
    assert cp_cli.main(["check", SLUG, "--input", CLEAN_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_missing_basis_is_contract_violation():
    assert cp_cli.main(["check", SLUG, "--input", CASE03_SAMPLE]) == 3


def test_cli_missing_input_is_input_error():
    assert cp_cli.main(["check", SLUG, "--input", os.path.join(SAMPLES, "nope.json"),
                        "--basis", BASIS_PATH]) == 2


def test_cli_json_summary(capsys):
    assert cp_cli.main(["check", SLUG, "--input", CASE03_SAMPLE,
                        "--basis", BASIS_PATH, "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG
    assert payload["summary"]["verdicts"]["fail"] >= 1


# --------------------------------------------------------------------------
# §九 随包数据完整性
# --------------------------------------------------------------------------
def _manifest():
    return load_json(os.path.join(DATA_DIR, "manifest.json"))


def test_manifest_file_set():
    assert set(_manifest()["files"]) == set(REG.DATA_FILES)


def test_manifest_bytes_and_sha256():
    import hashlib
    for name, record in _manifest()["files"].items():
        raw = open(os.path.join(DATA_DIR, name), "rb").read()
        assert record["bytes"] == len(raw)
        assert record["sha256"] == hashlib.sha256(raw).hexdigest()


def test_manifest_counts():
    manifest = _manifest()
    assert manifest["anchor_count"] == 165
    assert manifest["clause_count"] == 174
    assert manifest["synthetic_cases"] == 5
    assert manifest["patterns"] == list(CONSTANTS.EXPECTED_PATTERN_IDS)


def test_manifest_version():
    assert _manifest()["version"] == REG.VERSION


def test_data_files_lf_only():
    for name in REG.DATA_FILES + ("manifest.json",):
        raw = open(os.path.join(DATA_DIR, name), "rb").read()
        assert b"\r\n" not in raw


def test_clauses_all_versioned():
    data = load_json(BASIS_PATH)
    assert data["version"] == REG.VERSION
    for entry in data["clauses"]:
        assert entry["version"] == REG.VERSION


def test_every_hard_anchor_has_clause():
    library = PIPELINE.load_library()
    for pattern in library.patterns:
        for anchor_id in pattern.statute_anchors:
            assert BASIS.clause(anchor_id) is not None


def test_background_anchors_not_in_clauses():
    for anchor_id in ("CIVIL-496", "CIVIL-497", "CIVIL-498"):
        assert BASIS.clause(anchor_id) is None


def test_contracts_registered():
    expected = {PACK_MOD.CLAUSE_VERSION, PACK_MOD.CLAUSE_RULES,
                PACK_MOD.CLAUSE_SPLIT, PACK_MOD.CLAUSE_ANCHOR,
                PACK_MOD.CLAUSE_GRADING, PACK_MOD.CLAUSE_NOTICE,
                PACK_MOD.CLAUSE_INPUT, PACK_MOD.CLAUSE_SUMMARY,
                PACK_MOD.CLAUSE_EVIDENCE}
    assert all(BASIS.clause(clause_id) is not None for clause_id in expected)


def test_anchor_clause_path_uses_statute_title():
    clause = BASIS.clause("PIPL-31")
    assert "个人信息保护法" in clause.path
    assert "第31条" in clause.path


def test_anchor_clause_text_matches_statute():
    statute = load_json(os.path.join(DATA_DIR, "statute-PIPL.json"))
    article = next(item for item in statute["articles"]
                   if item["anchor_id"] == "PIPL-31")
    assert BASIS.clause("PIPL-31").text == article["anchor_text"]


# --------------------------------------------------------------------------
# §十 5 份合成样例对账（来源 bench 口径）
# --------------------------------------------------------------------------
def _actual(case):
    library = PIPELINE.load_library()
    analysis = PIPELINE.run(case["text"], library)
    path_by_clause = {clause["clause_id"]: clause["structural_path"]
                      for clause in analysis.clauses["clauses"]}
    actual = {}
    for hit in analysis.hits["hits"]:
        key = (path_by_clause.get(hit["clause_id"]), hit["pattern_id"])
        actual[key] = hit
    findings = {(path_by_clause.get(finding["clause_id"]), finding["pattern_id"]): finding
                for finding in analysis.findings}
    return analysis, actual, findings


@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_case_expected_hits(case):
    analysis, actual, findings = _actual(case)
    expected_positive = {}
    expected_negation = set()
    for item in case["truth"]["expected"]:
        key = (item["structural_path"], item["pattern_id"])
        if item["kind"] == "positive":
            expected_positive[key] = item
        else:
            expected_negation.add(key)
    assert set(actual) == set(expected_positive)
    for key in expected_negation:
        assert key not in actual


@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_case_levels_and_anchors(case):
    analysis, actual, findings = _actual(case)
    for item in case["truth"]["expected"]:
        if item["kind"] != "positive":
            continue
        key = (item["structural_path"], item["pattern_id"])
        finding = findings[key]
        assert finding["level"] == item["level"]
        assert sorted(finding["anchor_ids"]) == sorted(item["anchor_ids"])


@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_case_offsets_roundtrip(case):
    analysis, actual, findings = _actual(case)
    for key, hit in actual.items():
        for feature in hit["trigger_features"]:
            start, end = feature["char_start"], feature["char_end"]
            assert case["text"][start:end] == feature["matched_text"]


def test_cases_count_and_documents():
    assert len(CASES) == 5
    for case in CASES:
        assert case["truth"]["doc_sha256"]
        assert case["text"].strip()


def test_cases_cover_all_levels():
    levels = set()
    for case in CASES:
        for item in case["truth"]["expected"]:
            if item["kind"] == "positive":
                levels.add(item["level"])
    assert levels == {"high", "medium", "notice"}


# --------------------------------------------------------------------------
# §十一 结构纪律（纯本地 / 零文件 IO）
# --------------------------------------------------------------------------
FORBIDDEN_NETWORK = {"socket", "ssl", "http", "urllib", "ftplib", "requests",
                     "aiohttp", "httpx"}

JUDGMENT_MODULES = ("constants.py", "normalize.py", "splitter.py", "matcher.py",
                    "mapping.py", "grader.py", "templates.py", "model.py",
                    "__init__.py")


def _module_tree(name):
    import ast
    with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
        return ast.parse(handle.read())


def test_no_network_imports_in_judgment_modules():
    import ast
    for name in JUDGMENT_MODULES:
        tree = _module_tree(name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
                assert not (roots & FORBIDDEN_NETWORK), (name, roots)
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in FORBIDDEN_NETWORK, name


def test_judgment_modules_have_no_file_io():
    import ast
    for name in JUDGMENT_MODULES:
        tree = _module_tree(name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "open", (name, "judgment module calls open()")
            if isinstance(node, ast.With):
                for item in node.items:
                    call = item.context_expr
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                        assert call.func.id != "open", name