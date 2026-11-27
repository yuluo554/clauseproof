"""器官 ``pipl-audit`` 判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源判定面（门槛判定 + 义务分栏 / 检查单四态 / 汇总语义 / status 门控 /
规则包坐标 / auto 映射）逐条搬，断言落在「判定结果 + 依据 + 证据」上。来源判定层
（D1 + D18 机械选 12 文件 / 实跑 122 passed / AST 122）逐文件处置见
``docs/pipl-audit.md`` §6。

来源仓只读；合成规则集一律**内存注入**，绝不写入真实标准内容。真值库快照
（42 例 × 26 项，仅输入与期望）随包，逐例对账。
"""

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
from clauseproof.core.basis import Basis  # noqa: E402
from clauseproof.core.ledger import (  # noqa: E402
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Report,
)

PACK_MOD = importlib.import_module("clauseproof.packs.pipl-audit")
MODEL = importlib.import_module("clauseproof.packs.pipl-audit.model")
RULES = importlib.import_module("clauseproof.packs.pipl-audit.rules")
ENGINE = importlib.import_module("clauseproof.packs.pipl-audit.engine")
PIPELINE = importlib.import_module("clauseproof.packs.pipl-audit.pipeline")
REG = importlib.import_module("clauseproof.packs.pipl-audit.registry")
ERRORS = importlib.import_module("clauseproof.packs.pipl-audit.errors")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "pipl-audit")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "pipl-audit")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
DEMO_SAMPLE = os.path.join(SAMPLES, "card-demo.json")
ALLPASS_SAMPLE = os.path.join(SAMPLES, "card-allpass.json")
THRESHOLDS_SAMPLE = os.path.join(SAMPLES, "card-thresholds.json")
NOT_ASSESSED_SAMPLE = os.path.join(SAMPLES, "card-not-assessed.json")
TRUTH_PATH = os.path.join(DATA_DIR, "truth-cases.json")

AUTH = "pipl-audit-2025"
DEMO = "pipl-audit-demo"


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


BASIS = Basis.from_json(BASIS_PATH)
TRUTH = load_json(TRUTH_PATH)
CASES = TRUTH["cases"]


# --------------------------------------------------------------------------
# 合成夹具（内存注入；出处一律 SYNTHETIC- 前缀，不冒充法规）
# --------------------------------------------------------------------------
def _source(channel="SYNTHETIC-TEST"):
    return {"channel": channel, "url": "", "checked_at": "2026-10-13"}


def _clause(article="第 1 条", basis="SYNTHETIC-依据"):
    return {"basis": basis, "article": article, "point": "SYNTHETIC-要点"}


def _threshold(entry_id="TH-SYN", param="scale", op=">=", value=10,
               conclusion="syn_conclusion", frequency="", effect="standing_obligation",
               severity=1, status="verified", clause=None, source=None):
    return {
        "id": entry_id,
        "param": param,
        "op": op,
        "value": value,
        "conclusion": conclusion,
        "frequency": frequency,
        "effect": effect,
        "severity": severity,
        "status": status,
        "clause": clause or _clause(),
        "source": source if source is not None else _source(),
    }


def _item(item_id="CHK-SYN", method="auto", auto_field="flag", auto_mapping=None,
          only_if=None, status="verified", clause=None, source=None,
          title="SYNTHETIC-检查项", category="流程层"):
    return {
        "id": item_id,
        "category": category,
        "title": title,
        "method": method,
        "criteria": "SYNTHETIC-判定标准",
        "auto_field": auto_field,
        "auto_mapping": auto_mapping,
        "evidence_required": True,
        "only_if": only_if,
        "status": status,
        "clause": clause or _clause(),
        "source": source if source is not None else _source(),
    }


def _ruleset(thresholds=None, checklist=None, basis=None, **overrides):
    data = {
        "schema_version": "1.0",
        "ruleset_id": "synthetic-test",
        "version": REG.VERSION,
        "generated_at": "2026-10-13T00:00:00Z",
        "basis": basis if basis is not None else [
            {"code": "SYNTHETIC-依据", "title": "SYNTHETIC-测试依据",
             "effective_date": None, "status": "verified", "source": _source()},
        ],
        "thresholds": thresholds if thresholds is not None else [_threshold()],
        "checklist": checklist if checklist is not None else [_item()],
    }
    data.update(overrides)
    return data


def _parsed(thresholds=None, checklist=None, **overrides):
    return RULES.parse_ruleset(_ruleset(thresholds, checklist, **overrides))


def _pack(ruleset, synthetic=False, name="synthetic.json"):
    return RULES.RulePack(ruleset, name, synthetic)


def _outcome(result, threshold_id):
    for entry in result.outcomes:
        if entry.threshold.id == threshold_id:
            return entry
    raise AssertionError("未找到门槛结果：%s" % threshold_id)


def _records(subject, basis=None, packs=None):
    findings = PACK_MOD.evaluate_with_packs(subject, basis or BASIS, packs)
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject="test.json", findings=tuple(findings))


def _subject(**overrides):
    data = {"case_id": "case-1", "input_card": {"scale": 0}}
    data.update(overrides)
    return data


def _find(records, rule_id):
    for record in records:
        if record.rule_id == rule_id:
            return record
    raise AssertionError("未找到账本行：%s" % rule_id)


# --------------------------------------------------------------------------
# §一 装配：schema 校验 / status 门控 / 规则包加载
# --------------------------------------------------------------------------
def test_load_packs_returns_two():
    packs = PIPELINE.load_packs()
    assert set(packs) == {AUTH, DEMO}


def test_load_packs_coordinates():
    packs = PIPELINE.load_packs()
    assert packs[AUTH].version == "2025.1"
    assert packs[AUTH].synthetic is False
    assert packs[DEMO].synthetic is True


def test_load_packs_authoritative_counts():
    pack = PIPELINE.load_packs()[AUTH]
    assert pack.counts == {"basis": 3, "thresholds": 4, "checklist": 26}


def test_load_packs_demo_counts():
    pack = PIPELINE.load_packs()[DEMO]
    assert pack.counts == {"basis": 2, "thresholds": 2, "checklist": 4}


def test_parse_ruleset_ok():
    ruleset = _parsed()
    assert ruleset.ruleset_id == "synthetic-test"
    assert len(ruleset.thresholds) == 1
    assert len(ruleset.checklist) == 1


def test_parse_rejects_bad_schema():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(schema_version="9.9")


def test_parse_rejects_missing_ruleset_id():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(ruleset_id="")


def test_parse_rejects_missing_version():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(version="")


def test_parse_rejects_non_object():
    with pytest.raises(ERRORS.RulesetError):
        RULES.parse_ruleset(["not", "an", "object"])


def test_parse_rejects_duplicate_threshold():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(thresholds=[_threshold(), _threshold()])


def test_parse_rejects_duplicate_item():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(checklist=[_item(), _item()])


def test_parse_rejects_bad_operator():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(thresholds=[_threshold(op="~=")])


def test_parse_rejects_float_threshold_value():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(thresholds=[_threshold(value=1.5)])


def test_parse_rejects_bool_threshold_value():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(thresholds=[_threshold(value=True)])


def test_parse_rejects_unknown_effect():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(thresholds=[_threshold(effect="mandatory")])


def test_parse_rejects_threshold_without_clause():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(thresholds=[_threshold(clause={"basis": "", "article": "第 1 条"})])


def test_parse_rejects_item_without_clause():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(checklist=[_item(clause={"basis": "X", "article": ""})])


def test_parse_rejects_bad_method():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(checklist=[_item(method="hybrid")])


def test_parse_rejects_auto_without_field():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(checklist=[_item(method="auto", auto_field=None)])


def test_parse_rejects_only_if_not_object():
    with pytest.raises(ERRORS.RulesetError):
        _parsed(checklist=[_item(method="manual", auto_field=None, only_if=[1])])


def test_parse_rejects_threshold_missing_key():
    entry = _threshold()
    del entry["conclusion"]
    with pytest.raises(ERRORS.RulesetError):
        _parsed(thresholds=[entry])


def test_effective_passes_verified():
    ruleset = _parsed()
    assert RULES.effective(ruleset) is ruleset


def test_effective_blocks_pending_threshold():
    ruleset = _parsed(thresholds=[_threshold(status="pending")])
    with pytest.raises(ERRORS.PendingEntryError) as info:
        RULES.effective(ruleset)
    assert info.value.entries == ["threshold:TH-SYN"]


def test_effective_blocks_pending_item():
    ruleset = _parsed(checklist=[_item(status="pending")])
    with pytest.raises(ERRORS.PendingEntryError) as info:
        RULES.effective(ruleset)
    assert info.value.entries == ["checklist:CHK-SYN"]


def test_effective_blocks_pending_basis():
    ruleset = _parsed(basis=[{"code": "SYNTHETIC-依据", "title": "SYNTHETIC-测试依据",
                              "status": "pending", "source": _source()}])
    with pytest.raises(ERRORS.PendingEntryError) as info:
        RULES.effective(ruleset)
    assert info.value.entries == ["basis:SYNTHETIC-依据"]


def test_effective_blocks_unattributed_threshold():
    ruleset = _parsed(thresholds=[_threshold(source={"channel": "", "checked_at": ""})])
    with pytest.raises(ERRORS.UnattributedEntryError) as info:
        RULES.effective(ruleset)
    assert info.value.entries == ["threshold:TH-SYN"]


def test_effective_blocks_unattributed_item():
    ruleset = _parsed(checklist=[_item(source={"channel": "SYNTHETIC", "checked_at": ""})])
    with pytest.raises(ERRORS.UnattributedEntryError):
        RULES.effective(ruleset)


def test_effective_blocks_unattributed_basis():
    ruleset = _parsed(basis=[{"code": "SYNTHETIC-依据", "title": "SYNTHETIC-测试依据",
                              "status": "verified", "source": {}}])
    with pytest.raises(ERRORS.UnattributedEntryError) as info:
        RULES.effective(ruleset)
    assert info.value.entries == ["basis:SYNTHETIC-依据"]


def test_source_is_attributed_requires_channel_and_date():
    assert MODEL.Source(channel="c", checked_at="d").is_attributed()
    assert not MODEL.Source(channel="c").is_attributed()
    assert not MODEL.Source(checked_at="d").is_attributed()


def test_load_packs_missing_dir():
    with pytest.raises(ERRORS.RulesetError):
        RULES.load_packs(os.path.join(DATA_DIR, "nope"))


def test_load_packs_empty_dir(tmp_path):
    with pytest.raises(ERRORS.RulesetError):
        RULES.load_packs(str(tmp_path))


def test_load_packs_rejects_bad_json(tmp_path):
    (tmp_path / "ruleset-bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(ERRORS.RulesetError):
        RULES.load_packs(str(tmp_path))


def test_load_packs_rejects_duplicate_ruleset_id(tmp_path):
    payload = _ruleset()
    for name in ("ruleset-a.json", "ruleset-b.json"):
        (tmp_path / name).write_text(json.dumps(payload, ensure_ascii=False),
                                     encoding="utf-8")
    with pytest.raises(ERRORS.RulesetError):
        RULES.load_packs(str(tmp_path))


# --------------------------------------------------------------------------
# §二 门槛判定：运算符 / 边界 / 分栏 / 未判定留痕
# --------------------------------------------------------------------------
def test_threshold_ge_boundary_equal_hit():
    ruleset = _parsed(thresholds=[_threshold(op=">=", value=10)])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 10})
    assert _outcome(result, "TH-SYN").outcome == ENGINE.OUTCOME_HIT


def test_threshold_ge_boundary_below_miss():
    ruleset = _parsed(thresholds=[_threshold(op=">=", value=10)])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 9})
    assert _outcome(result, "TH-SYN").outcome == ENGINE.OUTCOME_MISS


def test_threshold_gt_boundary_equal_miss():
    ruleset = _parsed(thresholds=[_threshold(op=">", value=10)])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 10})
    assert _outcome(result, "TH-SYN").outcome == ENGINE.OUTCOME_MISS


def test_threshold_gt_boundary_above_hit():
    ruleset = _parsed(thresholds=[_threshold(op=">", value=10)])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 11})
    assert _outcome(result, "TH-SYN").outcome == ENGINE.OUTCOME_HIT


def test_threshold_lt_hit():
    ruleset = _parsed(thresholds=[_threshold(op="<", value=10)])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 9})
    assert result.triggered is True


def test_threshold_le_boundary_hit():
    ruleset = _parsed(thresholds=[_threshold(op="<=", value=10)])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 10})
    assert result.triggered is True


def test_threshold_eq_hit():
    ruleset = _parsed(thresholds=[_threshold(op="==", value=10)])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 10})
    assert result.triggered is True


def test_threshold_ne_hit():
    ruleset = _parsed(thresholds=[_threshold(op="!=", value=10)])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 9})
    assert result.triggered is True


def test_threshold_missing_param_not_applicable():
    ruleset = _parsed(thresholds=[_threshold(param="scale")])
    result = ENGINE.evaluate_thresholds(ruleset, {})
    assert _outcome(result, "TH-SYN").outcome == ENGINE.OUTCOME_NO_INPUT
    assert result.triggered is False


def test_threshold_string_input_type_mismatch():
    ruleset = _parsed(thresholds=[_threshold(param="scale")])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": "1000"})
    assert _outcome(result, "TH-SYN").outcome == ENGINE.OUTCOME_TYPE_MISMATCH


def test_threshold_bool_input_type_mismatch():
    ruleset = _parsed(thresholds=[_threshold(param="scale")])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": True})
    assert _outcome(result, "TH-SYN").outcome == ENGINE.OUTCOME_TYPE_MISMATCH


def test_threshold_float_input_accepted():
    ruleset = _parsed(thresholds=[_threshold(param="scale", op=">=", value=10)])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 10.5})
    assert result.triggered is True


def test_threshold_negative_value_miss():
    ruleset = _parsed(thresholds=[_threshold(param="scale", op=">=", value=0)])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": -1})
    assert result.triggered is False


def test_threshold_zero_actual_hit():
    ruleset = _parsed(thresholds=[_threshold(param="scale", op=">=", value=0)])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 0})
    assert result.triggered is True


def test_threshold_zero_severity_not_triggered():
    ruleset = _parsed(thresholds=[_threshold(severity=0)])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 100})
    assert result.triggered is False
    assert result.matched


def test_threshold_conclusions_dedup():
    ruleset = _parsed(thresholds=[
        _threshold("TH-A", value=1, conclusion="same", severity=1),
        _threshold("TH-B", value=2, conclusion="same", severity=1),
    ])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 5})
    assert result.conclusions == ["same"]


def test_threshold_severity_ordering():
    ruleset = _parsed(thresholds=[
        _threshold("TH-LOW", value=1, conclusion="low", severity=1),
        _threshold("TH-HIGH", value=1, conclusion="high", severity=5),
    ])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 5})
    assert result.conclusions == ["high", "low"]


def test_threshold_periodic_before_standing():
    ruleset = _parsed(thresholds=[
        _threshold("TH-STAND", value=1, conclusion="stand", severity=1,
                   effect="standing_obligation"),
        _threshold("TH-PERIOD", value=1, conclusion="period", severity=1,
                   effect="periodic_obligation"),
    ])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 5})
    assert result.conclusions == ["period", "stand"]


def test_threshold_conditional_bucket_separated():
    ruleset = _parsed(thresholds=[
        _threshold("TH-OBL", value=1, conclusion="obl", severity=1,
                   effect="standing_obligation"),
        _threshold("TH-COND", value=1, conclusion="cond", severity=2,
                   effect="conditional_institution"),
    ])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 5})
    assert [t.conclusion for t in result.obligations] == ["obl"]
    assert [t.conclusion for t in result.conditional_triggers] == ["cond"]


def test_threshold_frequency_comes_from_obligation():
    ruleset = _parsed(thresholds=[
        _threshold("TH-COND", value=1, conclusion="cond", severity=2,
                   effect="conditional_institution", frequency="不应出现"),
        _threshold("TH-OBL", value=1, conclusion="obl", severity=1,
                   effect="periodic_obligation", frequency="每两年至少一次"),
    ])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 5})
    assert result.frequency == "每两年至少一次"


def test_threshold_frequency_empty_when_no_obligation():
    ruleset = _parsed(thresholds=[
        _threshold(value=1, effect="conditional_institution", frequency="不应出现"),
    ])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 5})
    assert result.frequency == ""


def test_threshold_outcomes_trace_all_entries():
    ruleset = _parsed(thresholds=[
        _threshold("TH-A", param="scale", value=1),
        _threshold("TH-B", param="missing", value=1),
        _threshold("TH-C", param="flag", value=1),
    ])
    result = ENGINE.evaluate_thresholds(ruleset, {"scale": 5, "flag": "yes"})
    assert [entry.outcome for entry in result.outcomes] == [
        ENGINE.OUTCOME_HIT, ENGINE.OUTCOME_NO_INPUT, ENGINE.OUTCOME_TYPE_MISMATCH]


def test_threshold_result_as_dict_keys():
    result = ENGINE.evaluate_thresholds(_parsed(), {"scale": 50})
    payload = result.as_dict()
    assert payload["triggered"] is True
    assert set(payload) >= {"triggered", "conclusions", "frequency",
                            "obligations", "conditional_triggers", "outcomes"}


def test_threshold_outcome_as_dict():
    result = ENGINE.evaluate_thresholds(_parsed(), {"scale": 50})
    payload = _outcome(result, "TH-SYN").as_dict()
    assert payload["param"] == "scale"
    assert payload["actual"] == 50
    assert payload["conclusion"] == "syn_conclusion"


# --------------------------------------------------------------------------
# §三 检查项判定：auto 映射 / 门控 / 人工录入 / 分级
# --------------------------------------------------------------------------
def _one_item(mapping=None, method="auto", only_if=None):
    ruleset = _parsed(checklist=[_item(auto_mapping=mapping, method=method,
                                       auto_field="flag" if method == "auto" else None,
                                       only_if=only_if)])
    return ruleset.checklist[0]


def test_auto_true_compliant():
    item = _one_item()
    result = ENGINE.evaluate_item(item, {"flag": True}, {})
    assert result.state == MODEL.STATE_COMPLIANT


def test_auto_complete_word_compliant():
    item = _one_item([{"match": {"one_of": [True, "complete"]}, "state": "compliant"},
                      {"match": {"default": True}, "state": "noncompliant"}])
    result = ENGINE.evaluate_item(item, {"flag": "complete"}, {})
    assert result.state == MODEL.STATE_COMPLIANT


def test_auto_partial_word_partial():
    item = _one_item([{"match": {"equals": "partial"}, "state": "partial"},
                      {"match": {"default": True}, "state": "noncompliant"}])
    result = ENGINE.evaluate_item(item, {"flag": "partial"}, {})
    assert result.state == MODEL.STATE_PARTIAL


def test_auto_not_required_not_applicable():
    item = _one_item([{"match": {"one_of": ["not_required", "not_applicable"]},
                       "state": "not_applicable"},
                      {"match": {"default": True}, "state": "noncompliant"}])
    result = ENGINE.evaluate_item(item, {"flag": "not_required"}, {})
    assert result.state == MODEL.STATE_NOT_APPLICABLE


def test_auto_false_noncompliant():
    item = _one_item([{"match": {"one_of": [True, "complete"]}, "state": "compliant"},
                      {"match": {"default": True}, "state": "noncompliant"}])
    result = ENGINE.evaluate_item(item, {"flag": False}, {})
    assert result.state == MODEL.STATE_NONCOMPLIANT


def test_auto_absent_false_noncompliant():
    item = _one_item([{"match": {"default": True}, "state": "noncompliant"}])
    result = ENGINE.evaluate_item(item, {"flag": "absent"}, {})
    assert result.state == MODEL.STATE_NONCOMPLIANT


def test_auto_missing_field_unknown():
    item = _one_item()
    result = ENGINE.evaluate_item(item, {}, {})
    assert result.state == MODEL.STATE_UNKNOWN
    assert "未观测" in result.note


def test_auto_mapping_invalid_state_falls_back():
    item = _one_item([{"match": {"default": True}, "state": "compliant_typo"}])
    result = ENGINE.evaluate_item(item, {"flag": True}, {})
    assert result.state == MODEL.STATE_COMPLIANT


def test_auto_fallback_no_mapping_present_true():
    item = _one_item(None)
    result = ENGINE.evaluate_item(item, {"flag": True}, {})
    assert result.state == MODEL.STATE_COMPLIANT


def test_auto_fallback_no_mapping_missing_false():
    item = _one_item(None)
    result = ENGINE.evaluate_item(item, {"flag": ""}, {})
    assert result.state == MODEL.STATE_NONCOMPLIANT


def test_gate_satisfied_not_gated():
    item = _one_item(method="manual", only_if={"sensitive": [True]})
    result = ENGINE.evaluate_item(item, {"sensitive": True}, {"CHK-SYN": {"state": "compliant"}})
    assert result.state == MODEL.STATE_COMPLIANT


def test_gate_unsatisfied_not_applicable():
    item = _one_item(method="manual", only_if={"sensitive": [True]})
    result = ENGINE.evaluate_item(item, {"sensitive": False}, {"CHK-SYN": {"state": "compliant"}})
    assert result.state == MODEL.STATE_NOT_APPLICABLE
    assert "门控" in result.note


def test_gate_missing_key_not_applicable():
    item = _one_item(method="manual", only_if={"sensitive": [True]})
    result = ENGINE.evaluate_item(item, {}, {})
    assert result.state == MODEL.STATE_NOT_APPLICABLE


def test_manual_compliant():
    item = _one_item(method="manual")
    result = ENGINE.evaluate_item(item, {}, {"CHK-SYN": {"state": "compliant"}})
    assert result.state == MODEL.STATE_COMPLIANT


def test_manual_partial():
    item = _one_item(method="manual")
    result = ENGINE.evaluate_item(item, {}, {"CHK-SYN": {"state": "partial"}})
    assert result.state == MODEL.STATE_PARTIAL


def test_manual_noncompliant():
    item = _one_item(method="manual")
    result = ENGINE.evaluate_item(item, {}, {"CHK-SYN": {"state": "noncompliant"}})
    assert result.state == MODEL.STATE_NONCOMPLIANT


def test_manual_not_applicable():
    item = _one_item(method="manual")
    result = ENGINE.evaluate_item(item, {}, {"CHK-SYN": {"state": "not_applicable"}})
    assert result.state == MODEL.STATE_NOT_APPLICABLE


def test_manual_missing_unknown():
    item = _one_item(method="manual")
    result = ENGINE.evaluate_item(item, {}, {})
    assert result.state == MODEL.STATE_UNKNOWN
    assert "待人工确认" in result.note


def test_manual_invalid_state_unknown():
    item = _one_item(method="manual")
    result = ENGINE.evaluate_item(item, {}, {"CHK-SYN": {"state": "pass"}})
    assert result.state == MODEL.STATE_UNKNOWN


def test_manual_note_preserved():
    item = _one_item(method="manual")
    result = ENGINE.evaluate_item(item, {}, {"CHK-SYN": {"state": "partial", "note": "缺加密"}})
    assert result.note == "缺加密"


def test_item_risk_high_for_noncompliant():
    item = _one_item(method="manual")
    result = ENGINE.evaluate_item(item, {}, {"CHK-SYN": {"state": "noncompliant"}})
    assert result.risk == ENGINE.RISK_HIGH


def test_item_risk_medium_for_partial():
    item = _one_item(method="manual")
    result = ENGINE.evaluate_item(item, {}, {"CHK-SYN": {"state": "partial"}})
    assert result.risk == ENGINE.RISK_MEDIUM


def test_item_risk_none_for_compliant():
    item = _one_item(method="manual")
    result = ENGINE.evaluate_item(item, {}, {"CHK-SYN": {"state": "compliant"}})
    assert result.risk is None


def test_item_as_dict_contains_clause_and_risk():
    item = _one_item(method="manual")
    payload = ENGINE.evaluate_item(
        item, {}, {"CHK-SYN": {"state": "partial"}}).as_dict()
    assert payload["clause"]["basis"] == "SYNTHETIC-依据"
    assert payload["risk"] == "medium"
    assert payload["evidence_required"] is True


def test_item_evidence_required_false_is_curried():
    entry = _item(method="manual", auto_field=None)
    entry["evidence_required"] = False
    ruleset = _parsed(checklist=[entry])
    result = ENGINE.evaluate_item(ruleset.checklist[0], {}, {})
    assert result.item.evidence_required is False


# --------------------------------------------------------------------------
# §四 汇总语义
# --------------------------------------------------------------------------
def _results(states):
    item = _one_item(method="manual")
    return [ENGINE.ItemResult(item, state) for state in states]


def test_summary_all_compliant():
    assert ENGINE.summarize(_results(["compliant", "compliant"])) == MODEL.SUMMARY_COMPLIANT


def test_summary_partial():
    assert ENGINE.summarize(_results(["compliant", "partial"])) == MODEL.SUMMARY_PARTIAL


def test_summary_noncompliant_dominates():
    assert ENGINE.summarize(_results(["partial", "noncompliant"])) == MODEL.SUMMARY_NONCOMPLIANT


def test_summary_all_not_applicable_not_assessed():
    assert ENGINE.summarize(_results(["not_applicable", "not_applicable"])) == \
        MODEL.SUMMARY_NOT_ASSESSED


def test_summary_unknown_only_not_assessed():
    assert ENGINE.summarize(_results(["unknown"])) == MODEL.SUMMARY_NOT_ASSESSED


def test_summary_ignores_not_applicable():
    assert ENGINE.summarize(_results(["compliant", "not_applicable"])) == \
        MODEL.SUMMARY_COMPLIANT


def test_summary_ignores_unknown():
    assert ENGINE.summarize(_results(["compliant", "unknown"])) == MODEL.SUMMARY_COMPLIANT


def test_summary_empty_not_assessed():
    assert ENGINE.summarize([]) == MODEL.SUMMARY_NOT_ASSESSED


def test_counts_keys():
    tally = ENGINE.counts(_results(["compliant", "partial", "noncompliant",
                                    "not_applicable", "unknown"]))
    assert tally["total"] == 5
    assert tally["applicable"] == 3
    assert set(tally) == {"compliant", "partial", "noncompliant", "not_applicable",
                          "unknown", "total", "applicable", "risk_high", "risk_medium"}


def test_counts_risk_distribution():
    tally = ENGINE.counts(_results(["noncompliant", "partial", "compliant"]))
    assert tally["risk_high"] == 1
    assert tally["risk_medium"] == 1


# --------------------------------------------------------------------------
# §五 输入契约（subject）/ 条文库版本 / 锚点
# --------------------------------------------------------------------------
def test_subject_requires_case_id():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"input_card": {}}, BASIS)


def test_subject_requires_input_card():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c"}, BASIS)


def test_subject_input_card_must_be_object():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "input_card": []}, BASIS)


def test_subject_rejects_unknown_key():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "input_card": {}, "extra": 1}, BASIS)


def test_subject_manual_results_must_be_object():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "input_card": {}, "manual_results": []}, BASIS)


def test_subject_audit_scope_must_be_object():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "input_card": {}, "audit_scope": "x"}, BASIS)


def test_subject_ruleset_must_be_string():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "input_card": {}, "ruleset": 1}, BASIS)


def test_subject_unknown_ruleset():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "input_card": {}, "ruleset": "nope"}, BASIS)


def test_subject_manual_unknown_item():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "input_card": {},
                           "manual_results": {"CHK-NOPE": {"state": "compliant"}}}, BASIS)


def test_subject_manual_record_must_be_object():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "input_card": {},
                           "manual_results": {"CHK-PRO-002": "compliant"}}, BASIS)


def test_basis_version_mismatch_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(_subject(), Basis.empty("1999-01-01"))


def test_basis_missing_clause_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(_subject(), Basis(REG.VERSION))


def test_contract_scalar_requires_same_version():
    basis = Basis.from_json(BASIS_PATH)
    assert basis.version == REG.VERSION


# --------------------------------------------------------------------------
# §六 账本映射 / 报告 / 退出码
# --------------------------------------------------------------------------
def _load_sample(path):
    return load_json(path)


def test_authoritative_record_count():
    report = _records(_load_sample(ALLPASS_SAMPLE))
    assert len(report.findings) == 33


def test_demo_record_count():
    report = _records(_load_sample(DEMO_SAMPLE))
    assert len(report.findings) == 10


def test_demo_has_synthetic_warning():
    report = _records(_load_sample(DEMO_SAMPLE))
    record = _find(report.findings, PACK_MOD.RULE_PACK_SYNTHETIC)
    assert record.verdict == NOT_APPLICABLE
    assert "合成示例" in record.message


def test_authoritative_has_no_synthetic_warning():
    report = _records(_load_sample(ALLPASS_SAMPLE))
    assert all(record.rule_id != PACK_MOD.RULE_PACK_SYNTHETIC for record in report.findings)


def test_pack_finding_anchored():
    record = _find(_records(_load_sample(ALLPASS_SAMPLE)).findings, PACK_MOD.RULE_PACK)
    assert record.anchor.clause_id == PACK_MOD.CLAUSE_PACK
    assert "pipl-audit-2025" in record.message


def test_pack_finding_counts_evidence():
    record = _find(_records(_load_sample(ALLPASS_SAMPLE)).findings, PACK_MOD.RULE_PACK)
    assert record.evidence["thresholds"] == 4
    assert record.evidence["checklist"] == 26


def test_threshold_hit_is_pass():
    report = _records(_load_sample(DEMO_SAMPLE))
    record = _find(report.findings, "%s:TH-DEMO-PERIODIC" % PACK_MOD.RULE_THRESHOLD)
    assert record.verdict == PASS
    assert "周期" in record.message


def test_threshold_miss_is_not_applicable():
    report = _records(_load_sample(DEMO_SAMPLE))
    record = _find(report.findings, "%s:TH-DEMO-INSTITUTION" % PACK_MOD.RULE_THRESHOLD)
    assert record.verdict == NOT_APPLICABLE


def test_item_fail_has_risk_evidence():
    report = _records(_load_sample(DEMO_SAMPLE))
    record = _find(report.findings, "%s:CHK-DEMO-002" % PACK_MOD.RULE_ITEM)
    assert record.verdict == FAIL
    assert record.evidence["risk"] == "high"


def test_item_na_for_gated_item():
    report = _records(_load_sample(NOT_ASSESSED_SAMPLE))
    record = _find(report.findings, "%s:CHK-PRO-005" % PACK_MOD.RULE_ITEM)
    assert record.verdict == NOT_APPLICABLE
    assert record.evidence["state"] == "not_applicable"


def test_summary_fail_for_noncompliant():
    record = _find(_records(_load_sample(DEMO_SAMPLE)).findings, PACK_MOD.RULE_SUMMARY)
    assert record.verdict == FAIL
    assert record.anchor.clause_id == PACK_MOD.CLAUSE_SUMMARY


def test_summary_fail_for_not_assessed():
    record = _find(_records(_load_sample(NOT_ASSESSED_SAMPLE)).findings,
                   PACK_MOD.RULE_SUMMARY)
    assert record.verdict == FAIL
    assert record.anchor.clause_id == PACK_MOD.CLAUSE_NOT_ASSESSED


def test_summary_pass_for_allpass():
    record = _find(_records(_load_sample(ALLPASS_SAMPLE)).findings, PACK_MOD.RULE_SUMMARY)
    assert record.verdict == PASS


def test_every_non_na_record_has_anchor():
    report = _records(_load_sample(DEMO_SAMPLE))
    for record in report.findings:
        if record.verdict != NOT_APPLICABLE:
            assert record.anchor is not None


def test_every_record_has_rule_id_and_message():
    report = _records(_load_sample(DEMO_SAMPLE))
    for record in report.findings:
        assert record.rule_id
        assert record.message


def test_exit_code_zero_for_allpass():
    assert _records(_load_sample(ALLPASS_SAMPLE)).exit_code() == 0


def test_exit_code_one_for_demo():
    assert _records(_load_sample(DEMO_SAMPLE)).exit_code() == 1


def test_exit_code_one_for_not_assessed():
    assert _records(_load_sample(NOT_ASSESSED_SAMPLE)).exit_code() == 1


def test_exit_code_one_for_threshold_sample():
    assert _records(_load_sample(THRESHOLDS_SAMPLE)).exit_code() == 1


def test_report_order_deterministic():
    first = _records(_load_sample(ALLPASS_SAMPLE)).as_dict()["records"]
    second = _records(_load_sample(ALLPASS_SAMPLE)).as_dict()["records"]
    assert [r["id"] for r in first] == [r["id"] for r in second]


def test_threshold_sample_buckets():
    report = _records(_load_sample(THRESHOLDS_SAMPLE))
    record = _find(report.findings, PACK_MOD.RULE_THRESHOLD_RESULT)
    assert record.evidence["triggered"] is True
    assert "require_personal_info_officer" in record.evidence["conclusions"]


def test_demo_pack_selected_by_subject():
    report = _records(_load_sample(DEMO_SAMPLE))
    record = _find(report.findings, PACK_MOD.RULE_PACK)
    assert record.evidence["ruleset_id"] == DEMO


def test_pack_selection_defaults_to_authoritative():
    subject = _load_sample(ALLPASS_SAMPLE)
    subject.pop("ruleset", None)
    report = _records(subject)
    assert _find(report.findings, PACK_MOD.RULE_PACK).evidence["ruleset_id"] == AUTH


def test_audit_scope_is_not_a_judgement_input():
    subject = _load_sample(ALLPASS_SAMPLE)
    subject["audit_scope"] = {"subject": "另一家（虚构）"}
    assert _records(subject).exit_code() == 0


def test_unknown_card_fields_are_ignored():
    subject = _load_sample(ALLPASS_SAMPLE)
    subject["input_card"]["extra_field"] = "ignored"
    assert _records(subject).exit_code() == 0


# --------------------------------------------------------------------------
# §七 CLI 入口
# --------------------------------------------------------------------------
def test_cli_list_contains_slug(capsys):
    assert cp_cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert SLUG in out


def test_cli_list_json_contains_slug(capsys):
    assert cp_cli.main(["list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert SLUG in {entry["slug"] for entry in payload}


def test_cli_check_allpass_rc0():
    assert cp_cli.main(["check", SLUG, "--input", ALLPASS_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_check_demo_rc1():
    assert cp_cli.main(["check", SLUG, "--input", DEMO_SAMPLE,
                        "--basis", BASIS_PATH]) == 1


def test_cli_check_not_assessed_rc1():
    assert cp_cli.main(["check", SLUG, "--input", NOT_ASSESSED_SAMPLE,
                        "--basis", BASIS_PATH]) == 1


def test_cli_missing_basis_is_contract_violation():
    assert cp_cli.main(["check", SLUG, "--input", DEMO_SAMPLE]) == 3


def test_cli_missing_input_is_input_error():
    assert cp_cli.main(["check", SLUG, "--input", os.path.join(SAMPLES, "nope.json"),
                        "--basis", BASIS_PATH]) == 2


def test_cli_json_summary(capsys):
    assert cp_cli.main(["check", SLUG, "--input", ALLPASS_SAMPLE,
                        "--basis", BASIS_PATH, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG
    assert payload["summary"]["verdicts"]["fail"] == 0


def test_cli_json_contains_synthetic_flag(capsys):
    assert cp_cli.main(["check", SLUG, "--input", DEMO_SAMPLE,
                        "--basis", BASIS_PATH, "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    ids = {record["rule_id"] for record in payload["records"]}
    assert PACK_MOD.RULE_PACK_SYNTHETIC in ids


def test_cli_unknown_ruleset_in_subject_rc2(tmp_path):
    subject = _load_sample(ALLPASS_SAMPLE)
    subject["ruleset"] = "nope"
    path = tmp_path / "case.json"
    path.write_text(json.dumps(subject, ensure_ascii=False), encoding="utf-8")
    assert cp_cli.main(["check", SLUG, "--input", str(path), "--basis", BASIS_PATH]) == 2


def test_cli_unknown_manual_item_rc2(tmp_path):
    subject = _load_sample(ALLPASS_SAMPLE)
    subject["manual_results"] = {"CHK-NOPE": {"state": "compliant"}}
    path = tmp_path / "case.json"
    path.write_text(json.dumps(subject, ensure_ascii=False), encoding="utf-8")
    assert cp_cli.main(["check", SLUG, "--input", str(path), "--basis", BASIS_PATH]) == 2


def test_cli_sample_output_has_disclaimer_line(capsys):
    cp_cli.main(["check", SLUG, "--input", ALLPASS_SAMPLE, "--basis", BASIS_PATH])
    out = capsys.readouterr().out
    assert "合计" in out


# --------------------------------------------------------------------------
# §八 随包数据完整性（manifest / 条款覆盖 / LF）
# --------------------------------------------------------------------------
def _manifest():
    return load_json(os.path.join(DATA_DIR, "manifest.json"))


def test_manifest_file_set_matches_registry():
    assert set(_manifest()["files"]) == set(REG.DATA_FILES)


def test_manifest_bytes_and_sha256():
    import hashlib
    manifest = _manifest()
    for name, record in manifest["files"].items():
        raw = open(os.path.join(DATA_DIR, name), "rb").read()
        assert record["bytes"] == len(raw)
        assert record["sha256"] == hashlib.sha256(raw).hexdigest()


def test_manifest_clause_count():
    assert _manifest()["clause_count"] == len(Basis.from_json(BASIS_PATH))


def test_manifest_ruleset_counts():
    rulesets = _manifest()["rulesets"]
    assert rulesets[AUTH] == {"basis": 3, "thresholds": 4, "checklist": 26,
                              "synthetic": False}
    assert rulesets[DEMO] == {"basis": 2, "thresholds": 2, "checklist": 4,
                              "synthetic": True}


def test_manifest_truth_case_count():
    assert _manifest()["truth_cases"] == len(CASES) == 42


def test_manifest_version_matches_registry():
    assert _manifest()["version"] == REG.VERSION


def test_data_files_are_lf_only():
    for name in REG.DATA_FILES + ("manifest.json",):
        raw = open(os.path.join(DATA_DIR, name), "rb").read()
        assert b"\r\n" not in raw


def test_clauses_all_versioned():
    data = load_json(BASIS_PATH)
    assert data["version"] == REG.VERSION
    for entry in data["clauses"]:
        assert entry["version"] == REG.VERSION


def test_clauses_cover_every_threshold_and_item():
    packs = PIPELINE.load_packs()
    for pack in packs.values():
        for threshold in pack.ruleset.thresholds:
            assert BASIS.clause("pipl:th:%s" % threshold.id) is not None
        for item in pack.ruleset.checklist:
            assert BASIS.clause("pipl:chk:%s" % item.id) is not None


def test_basis_documents_are_registered():
    for clause_id, path_part in (
        ("pipl:basis:order-18", "网信办令第18号"),
        ("pipl:basis:gbt-35273", "GB/T 35273-2020"),
        ("pipl:basis:gbt-42574", "GB/T 42574-2023"),
    ):
        clause = BASIS.clause(clause_id)
        assert clause is not None
        assert path_part in clause.path


def test_basis_documents_effective_dates():
    assert BASIS.clause("pipl:basis:order-18").effective == "2025-05-01"
    assert BASIS.clause("pipl:basis:gbt-35273").effective == "2020-10-01"
    assert BASIS.clause("pipl:basis:gbt-42574").effective == "2023-12-01"


def test_contracts_are_registered():
    expected = {PACK_MOD.CLAUSE_VERSION, PACK_MOD.CLAUSE_PACK, PACK_MOD.CLAUSE_GATE,
                PACK_MOD.CLAUSE_THRESHOLD, PACK_MOD.CLAUSE_CHECKLIST,
                PACK_MOD.CLAUSE_SUMMARY, PACK_MOD.CLAUSE_NOT_ASSESSED,
                PACK_MOD.CLAUSE_RISK, PACK_MOD.CLAUSE_MANUAL,
                PACK_MOD.CLAUSE_INPUT, PACK_MOD.CLAUSE_EVIDENCE}
    assert all(BASIS.clause(clause_id) is not None for clause_id in expected)


def test_demo_clauses_are_marked_synthetic():
    for clause_id in BASIS.clause_ids():
        if clause_id.startswith("pipl:th:TH-DEMO") or clause_id.startswith(
                "pipl:chk:CHK-DEMO"):
            assert BASIS.clause(clause_id).path.startswith("示例（合成）")
            assert "合成示例值" in BASIS.clause(clause_id).text


def test_authoritative_threshold_clause_quotes_law_point():
    clause = BASIS.clause("pipl:th:TH-SCALE-PERIODIC")
    assert "网信办令第18号" in clause.path
    assert "第四条" in clause.path
    assert "1000 万" in clause.text or "1000万" in clause.text


def test_authoritative_checklist_clause_path_uses_guide():
    clause = BASIS.clause("pipl:chk:CHK-PRO-002")
    assert "附件指引2" in clause.path


# --------------------------------------------------------------------------
# §九 真值库快照（42 例 × 26 项；仅输入与期望）
# --------------------------------------------------------------------------
def test_truth_cases_are_unique():
    ids = [case["case_id"] for case in CASES]
    assert len(ids) == len(set(ids))


def test_truth_cases_have_no_observed_key():
    raw = open(TRUTH_PATH, "r", encoding="utf-8").read()
    assert '"observed"' not in raw


def test_truth_cases_count_matches_payload():
    assert TRUTH["count"] == len(CASES)


def test_truth_cases_all_authoritative():
    assert {case["ruleset_id"] for case in CASES} == {AUTH}


@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_truth_case_item_states(case):
    pack = PIPELINE.load_packs()[AUTH]
    result = PIPELINE.compute_audit(pack, case["input_card"],
                                    case.get("manual_results") or {})
    states = {item.item.id: item.state for item in result.item_results}
    assert states == case["expected"]["item_states"]


@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_truth_case_thresholds(case):
    pack = PIPELINE.load_packs()[AUTH]
    result = PIPELINE.compute_audit(pack, case["input_card"],
                                    case.get("manual_results") or {})
    expected = case["expected"]
    assert result.threshold_result.triggered == expected["triggered"]
    assert sorted(set(result.threshold_result.conclusions)) == \
        sorted(expected["threshold_conclusions"])
    assert sorted({item.conclusion for item in result.threshold_result.obligations}) == \
        sorted(expected["obligation_conclusions"])
    assert sorted({item.conclusion
                   for item in result.threshold_result.conditional_triggers}) == \
        sorted(expected["conditional_conclusions"])


@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_truth_case_summary(case):
    pack = PIPELINE.load_packs()[AUTH]
    result = PIPELINE.compute_audit(pack, case["input_card"],
                                    case.get("manual_results") or {})
    assert result.summary == case["expected"]["summary"]


def test_truth_cases_cover_all_summaries():
    summaries = {case["expected"]["summary"] for case in CASES}
    assert summaries == {MODEL.SUMMARY_COMPLIANT, MODEL.SUMMARY_PARTIAL,
                         MODEL.SUMMARY_NONCOMPLIANT, MODEL.SUMMARY_NOT_ASSESSED}