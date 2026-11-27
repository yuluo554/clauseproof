"""器官 ``two-tickets`` 判定测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源判定面（7 类 check_type / 票种类目门控 / 依据闸 / 三级结论 /
问题分级 / 复核锚）逐条搬，断言落在「判定结果 + 依据 + 证据」上。来源判定层
（D1 + D18 机械选 7 文件 / 实跑 82 passed / AST 82）逐文件处置见
``docs/two-tickets.md`` §6。

来源仓只读；合成规则一律**内存注入**（出处 `SYNTHETIC-` 前缀），绝不冒充标准原文。
随包 35 例带真值样例（规则 id + kind + 字段真值）逐例对账。
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

PACK_MOD = importlib.import_module("clauseproof.packs.two-tickets")
MODEL = importlib.import_module("clauseproof.packs.two-tickets.model")
RULES = importlib.import_module("clauseproof.packs.two-tickets.rules")
CHECKS = importlib.import_module("clauseproof.packs.two-tickets.checks")
ENGINE = importlib.import_module("clauseproof.packs.two-tickets.engine")
PIPELINE = importlib.import_module("clauseproof.packs.two-tickets.pipeline")
REG = importlib.import_module("clauseproof.packs.two-tickets.registry")
ERRORS = importlib.import_module("clauseproof.packs.two-tickets.errors")

SLUG = PACK_MOD.SLUG
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", "two-tickets")
DATA_DIR = os.path.join(PACK_DIR, "data")
SAMPLES = os.path.join(ROOT, "samples", "two-tickets")
BASIS_PATH = os.path.join(DATA_DIR, "clauses.json")
README_SAMPLE = os.path.join(SAMPLES, "ticket-operating-readme.json")
SIGNATURE_SAMPLE = os.path.join(SAMPLES, "ticket-signature-gap.json")
PENDING_SAMPLE = os.path.join(SAMPLES, "ticket-time-order-pending.json")
FIVE_PREVENTION_SAMPLE = os.path.join(SAMPLES, "ticket-five-prevention.json")
CASES_PATH = os.path.join(DATA_DIR, "ticket-cases.json")

BASIS = Basis.from_json(BASIS_PATH)
CASES_DATA = None
with open(CASES_PATH, "r", encoding="utf-8") as _handle:
    CASES_DATA = json.load(_handle)
CASES = CASES_DATA["cases"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


# --------------------------------------------------------------------------
# 合成夹具（内存注入；出处一律 SYNTHETIC- 前缀）
# --------------------------------------------------------------------------
def _card(ticket_type="operating", fields=None, steps=None, measures=None):
    return MODEL.TicketCard(
        ticket_type=ticket_type,
        fields={key: MODEL.FieldValue(value=value)
                for key, value in (fields or {}).items()},
        operation_sequence=[MODEL.OperationStep(no=index, action=action)
                            for index, action in enumerate(steps or [], 1)],
        safety_measures=[MODEL.SafetyMeasure(no=index, text=text)
                         for index, text in enumerate(measures or [], 1)],
    )


def _rule(rule_id="R-T-001", check_type="required_field", applies_to=("operating",),
          status="已核对", params=None, risk="一般", name="SYNTHETIC-测试规则"):
    return {
        "id": rule_id,
        "name": name,
        "check_type": check_type,
        "applies_to": list(applies_to),
        "basis": {
            "standard": "SYNTHETIC-标准",
            "clause": "附录 测试条款",
            "quote": "",
            "channel": "SYNTHETIC-TEST",
            "status": status,
            "review_due": "2027-10-02",
        },
        "level": "形式合规",
        "risk": risk,
        "suggestion": "SYNTHETIC-整改建议",
        "params": params or {},
    }


def _library(*rules):
    result = list(rules) if rules else [_rule()]
    RULES.validate(result)
    return RULES.RuleLibrary(result, ["synthetic.json"])


def _ticket(case):
    return {key: case[key] for key in
            ("ticket_type", "fields", "operation_sequence", "safety_measures")}


def _subject(ticket, case_id="case-1"):
    return {"case_id": case_id, "ticket": ticket}


def _records(subject, basis=None, library=None):
    findings = PACK_MOD.evaluate_with_library(subject, basis or BASIS, library)
    return Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                  subject="test.json", findings=tuple(findings))


def _find(records, rule_id):
    for record in records:
        if record.rule_id == rule_id:
            return record
    raise AssertionError("未找到账本行：%s" % rule_id)


def _verdict(rule, card):
    conclusions = ENGINE.run_checks(card, [rule])
    assert len(conclusions) == 1, conclusions
    return conclusions[0]


# --------------------------------------------------------------------------
# §一 规则库加载与校验
# --------------------------------------------------------------------------
def test_load_library_counts():
    library = PIPELINE.load_library()
    assert len(library.rules) == 39
    assert library.status_counts == {"已核对": 9, "待核对": 30}


def test_load_library_files():
    library = PIPELINE.load_library()
    assert library.files == ("rules-content.json", "rules-form.json", "rules-time.json")


def test_load_library_check_types():
    library = PIPELINE.load_library()
    assert set(library.check_type_counts) == set(MODEL.CHECK_TYPES)


def test_load_library_coordinate():
    coordinate = PIPELINE.load_library().coordinate()
    assert coordinate["rules"] == 39
    assert coordinate["verified"] == 9
    assert coordinate["pending"] == 30
    assert coordinate["check_types"]["time_order"] == 19


def test_pending_rules_count():
    assert len(PIPELINE.load_library().pending_rules) == 30


def test_review_dues_registered_for_all_rules():
    dues = PIPELINE.load_library().review_dues
    assert len(dues) == 39
    assert all(value == "2027-10-02" for value in dues.values())


def test_parse_rules_requires_rules_array():
    with pytest.raises(ERRORS.RuleError):
        RULES.parse_rules({"rules": []})


def test_parse_rules_rejects_non_object():
    with pytest.raises(ERRORS.RuleError):
        RULES.parse_rules([])


def test_parse_rules_rejects_missing_key():
    rule = _rule()
    del rule["name"]
    with pytest.raises(ERRORS.RuleError):
        RULES.parse_rules({"rules": [rule]})


def test_parse_rules_rejects_no_basis_standard():
    rule = _rule()
    rule["basis"]["standard"] = ""
    with pytest.raises(ERRORS.RuleError):
        RULES.parse_rules({"rules": [rule]})


def test_validate_rejects_duplicate_id():
    with pytest.raises(ERRORS.RuleError):
        RULES.validate([_rule(), _rule()])


def test_validate_rejects_unknown_check_type():
    rule = _rule()
    rule["check_type"] = "magic"
    with pytest.raises(ERRORS.RuleError):
        RULES.validate([rule])


def test_validate_rejects_unknown_ticket_type():
    rule = _rule(applies_to=("spaceship",))
    with pytest.raises(ERRORS.RuleError):
        RULES.validate([rule])


def test_validate_rejects_empty_applies_to():
    rule = _rule(applies_to=())
    with pytest.raises(ERRORS.RuleError):
        RULES.validate([rule])


def test_validate_rejects_bad_status():
    rule = _rule()
    rule["basis"]["status"] = "confirmed"
    with pytest.raises(ERRORS.RuleError):
        RULES.validate([rule])


def test_validate_rejects_bad_review_due():
    rule = _rule()
    rule["basis"]["review_due"] = "2027/10/02"
    with pytest.raises(ERRORS.RuleError):
        RULES.validate([rule])


def test_validate_rejects_non_object_params():
    rule = _rule()
    rule["params"] = []
    with pytest.raises(ERRORS.RuleError):
        RULES.validate([rule])


def test_validate_accepts_synthetic_rule():
    assert RULES.validate([_rule()])


def test_load_library_missing_dir():
    with pytest.raises(ERRORS.RuleError):
        RULES.load_library(os.path.join(DATA_DIR, "nope"))


def test_load_library_empty_dir(tmp_path):
    with pytest.raises(ERRORS.RuleError):
        RULES.load_library(str(tmp_path))


def test_load_library_rejects_bad_json(tmp_path):
    (tmp_path / "rules-bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(ERRORS.RuleError):
        RULES.load_library(str(tmp_path))


def test_load_library_tmp_ok(tmp_path):
    payload = {"rules": [_rule()]}
    (tmp_path / "rules-x.json").write_text(json.dumps(payload, ensure_ascii=False),
                                           encoding="utf-8")
    library = RULES.load_library(str(tmp_path))
    assert len(library.rules) == 1


# --------------------------------------------------------------------------
# §二 票面参数卡编译
# --------------------------------------------------------------------------
def test_build_card_scalar_fields():
    card = PIPELINE.build_card({"ticket_type": "operating", "fields": {"ticket_no": "CZ-1"}})
    assert card.fields["ticket_no"].value == "CZ-1"
    assert card.fields["ticket_no"].confidence == 1.0


def test_build_card_object_field_with_evidence():
    card = PIPELINE.build_card({
        "ticket_type": "operating",
        "fields": {"ticket_no": {"value": "CZ-1", "confidence": 0.9,
                                 "evidence": {"region": "head", "quote": "编号：CZ-1"}}},
    })
    assert card.fields["ticket_no"].value == "CZ-1"
    assert card.fields["ticket_no"].evidence.quote == "编号：CZ-1"


def test_build_card_rejects_unknown_ticket_key():
    with pytest.raises(ERRORS.InputError):
        PIPELINE.build_card({"ticket_type": "operating", "fields": {}, "extra": 1})


def test_build_card_rejects_unknown_field_key():
    with pytest.raises(ERRORS.InputError):
        PIPELINE.build_card({"ticket_type": "operating",
                             "fields": {"a": {"value": 1, "weight": 2}}})


def test_build_card_rejects_object_without_value():
    with pytest.raises(ERRORS.InputError):
        PIPELINE.build_card({"ticket_type": "operating", "fields": {"a": {}}})


def test_build_card_rejects_bool_confidence():
    with pytest.raises(ERRORS.InputError):
        PIPELINE.build_card({"ticket_type": "operating",
                             "fields": {"a": {"value": 1, "confidence": True}}})


def test_build_card_rejects_unknown_ticket_type():
    with pytest.raises(ERRORS.InputError):
        PIPELINE.build_card({"ticket_type": "nope", "fields": {}})


def test_build_card_rejects_missing_fields():
    with pytest.raises(ERRORS.InputError):
        PIPELINE.build_card({"ticket_type": "operating"})


def test_build_card_sequence_string_shorthand():
    card = PIPELINE.build_card({"ticket_type": "operating", "fields": {},
                                "operation_sequence": ["断开断路器"]})
    assert card.operation_sequence[0].no == 1
    assert card.operation_sequence[0].action == "断开断路器"


def test_build_card_sequence_object():
    card = PIPELINE.build_card({"ticket_type": "operating", "fields": {},
                                "operation_sequence": [{"no": 7, "action": "验电"}]})
    assert card.operation_sequence[0].no == 7


def test_build_card_rejects_sequence_bad_action():
    with pytest.raises(ERRORS.InputError):
        PIPELINE.build_card({"ticket_type": "operating", "fields": {},
                             "operation_sequence": [{"no": 1, "action": ""}]})


def test_build_card_rejects_sequence_bad_no():
    with pytest.raises(ERRORS.InputError):
        PIPELINE.build_card({"ticket_type": "operating", "fields": {},
                             "operation_sequence": [{"no": "1", "action": "x"}]})


def test_build_card_measures_string_shorthand():
    card = PIPELINE.build_card({"ticket_type": "work_first", "fields": {},
                                "safety_measures": ["断开断路器"]})
    assert card.safety_measures[0].text == "断开断路器"


def test_build_card_rejects_measures_bad_text():
    with pytest.raises(ERRORS.InputError):
        PIPELINE.build_card({"ticket_type": "work_first", "fields": {},
                             "safety_measures": [{"no": 1, "text": ""}]})


def test_build_card_rejects_measures_bad_no():
    with pytest.raises(ERRORS.InputError):
        PIPELINE.build_card({"ticket_type": "work_first", "fields": {},
                             "safety_measures": [{"no": True, "text": "x"}]})


def test_to_dict_roundtrip_shape():
    card = _card(fields={"ticket_no": "CZ-1"}, steps=["x"], measures=["m"])
    payload = card.to_dict()
    assert payload["ticket_type_name"] == "变电站倒闸操作票"
    assert payload["operation_sequence"] == [{"no": 1, "action": "x"}]
    assert payload["safety_measures"] == [{"no": 1, "text": "m"}]


# --------------------------------------------------------------------------
# §三 required_field / process_signature
# --------------------------------------------------------------------------
def test_required_field_missing():
    rule = _rule(params={"fields": ["ticket_no"]})
    conclusion = _verdict(rule, _card(fields={}))
    assert conclusion.verdict == MODEL.VERDICT_VIOLATION
    assert "ticket_no" in conclusion.evidence[0]


def test_required_field_empty_string_is_missing():
    rule = _rule(params={"fields": ["ticket_no"]})
    conclusion = _verdict(rule, _card(fields={"ticket_no": "   "}))
    assert conclusion.verdict == MODEL.VERDICT_VIOLATION


def test_required_field_present_compliant():
    rule = _rule(params={"fields": ["ticket_no"]})
    conclusion = _verdict(rule, _card(fields={"ticket_no": "CZ-1"}))
    assert conclusion.verdict == MODEL.VERDICT_COMPLIANT


def test_required_field_multiple_missing_listed():
    rule = _rule(params={"fields": ["ticket_no", "task"]})
    conclusion = _verdict(rule, _card(fields={}))
    assert len(conclusion.evidence) == 2


def test_process_signature_missing_once():
    rule = _rule(check_type="process_signature",
                 params={"fields": ["issuer", "permitor"]})
    conclusion = _verdict(rule, _card(fields={"issuer": "A"}))
    assert conclusion.verdict == MODEL.VERDICT_VIOLATION
    assert "permitor" in conclusion.evidence[0]


def test_process_signature_complete():
    rule = _rule(check_type="process_signature",
                 params={"fields": ["issuer", "permitor"]})
    conclusion = _verdict(rule, _card(fields={"issuer": "A", "permitor": "B"}))
    assert conclusion.verdict == MODEL.VERDICT_COMPLIANT
    assert "签字链完整" in conclusion.evidence[0]


def test_process_signature_missing_field_manual_not_used():
    """签字链缺失在来源里判「不合规」（不是「待人工确认」），逐条保留。"""
    rule = _rule(check_type="process_signature", params={"fields": ["issuer"]})
    assert _verdict(rule, _card(fields={})).verdict == MODEL.VERDICT_VIOLATION


# --------------------------------------------------------------------------
# §四 time_order（interval / in_window）
# --------------------------------------------------------------------------
def test_time_interval_ok():
    rule = _rule(check_type="time_order", params={"start": "start_time",
                                                  "end": "end_time"})
    card = _card(fields={"start_time": "2026-10-15T08:00",
                         "end_time": "2026-10-15T09:00"})
    assert _verdict(rule, card).verdict == MODEL.VERDICT_COMPLIANT


def test_time_interval_reversed_violation():
    rule = _rule(check_type="time_order", params={"start": "start_time",
                                                  "end": "end_time"})
    card = _card(fields={"start_time": "2026-10-15T09:00",
                         "end_time": "2026-10-15T08:00"})
    assert _verdict(rule, card).verdict == MODEL.VERDICT_VIOLATION


def test_time_interval_equal_violation():
    rule = _rule(check_type="time_order", params={"start": "start_time",
                                                  "end": "end_time"})
    card = _card(fields={"start_time": "2026-10-15T08:00",
                         "end_time": "2026-10-15T08:00"})
    assert _verdict(rule, card).verdict == MODEL.VERDICT_VIOLATION


def test_time_interval_missing_field_manual():
    rule = _rule(check_type="time_order", params={"start": "start_time",
                                                  "end": "end_time"})
    card = _card(fields={"start_time": "2026-10-15T08:00"})
    assert _verdict(rule, card).verdict == MODEL.VERDICT_MANUAL


def test_time_interval_unparseable_manual():
    rule = _rule(check_type="time_order", params={"start": "start_time",
                                                  "end": "end_time"})
    card = _card(fields={"start_time": "上午八点", "end_time": "2026-10-15T09:00"})
    assert _verdict(rule, card).verdict == MODEL.VERDICT_MANUAL


def test_time_in_window_ok():
    rule = _rule(check_type="time_order",
                 params={"mode": "in_window", "target": "permit_start",
                         "start": "plan_start", "end": "plan_end"})
    card = _card(fields={"permit_start": "2026-10-15T09:00",
                         "plan_start": "2026-10-15T08:00",
                         "plan_end": "2026-10-15T18:00"})
    assert _verdict(rule, card).verdict == MODEL.VERDICT_COMPLIANT


def test_time_in_window_outside_violation():
    rule = _rule(check_type="time_order",
                 params={"mode": "in_window", "target": "permit_start",
                         "start": "plan_start", "end": "plan_end"})
    card = _card(fields={"permit_start": "2026-10-15T19:00",
                         "plan_start": "2026-10-15T08:00",
                         "plan_end": "2026-10-15T18:00"})
    assert _verdict(rule, card).verdict == MODEL.VERDICT_VIOLATION


def test_time_in_window_on_violation_manual():
    rule = _rule(check_type="time_order",
                 params={"mode": "in_window", "target": "permit_start",
                         "start": "plan_start", "end": "plan_end",
                         "on_violation": "manual"})
    card = _card(fields={"permit_start": "2026-10-15T19:00",
                         "plan_start": "2026-10-15T08:00",
                         "plan_end": "2026-10-15T18:00"})
    conclusion = _verdict(rule, card)
    assert conclusion.verdict == MODEL.VERDICT_MANUAL
    assert "工作变更" in conclusion.evidence[0]


def test_time_in_window_missing_field_manual():
    rule = _rule(check_type="time_order",
                 params={"mode": "in_window", "target": "permit_start"})
    assert _verdict(rule, _card(fields={})).verdict == MODEL.VERDICT_MANUAL


def test_time_in_window_unparseable_manual():
    rule = _rule(check_type="time_order",
                 params={"mode": "in_window", "target": "permit_start",
                         "start": "plan_start", "end": "plan_end"})
    card = _card(fields={"permit_start": "x", "plan_start": "y", "plan_end": "z"})
    assert _verdict(rule, card).verdict == MODEL.VERDICT_MANUAL


# --------------------------------------------------------------------------
# §五 ticket_type_match / measure_coverage
# --------------------------------------------------------------------------
def test_ticket_type_match_task_missing_skips():
    rule = _rule(check_type="ticket_type_match",
                 params={"field": "task", "forbidden_terms": ["停电"],
                         "exempt_terms": ["不需停电"]})
    assert ENGINE.run_checks(_card(fields={}), [rule]) == []


def test_ticket_type_match_forbidden_hit():
    rule = _rule(check_type="ticket_type_match",
                 params={"field": "task", "forbidden_terms": ["停电"],
                         "exempt_terms": ["不需停电"]})
    card = _card(fields={"task": "10kV 线路停电检修"})
    assert _verdict(rule, card).verdict == MODEL.VERDICT_VIOLATION


def test_ticket_type_match_exempt_term():
    rule = _rule(check_type="ticket_type_match",
                 params={"field": "task", "forbidden_terms": ["停电"],
                         "exempt_terms": ["不需停电"]})
    card = _card(fields={"task": "不需停电的巡视检查"})
    assert _verdict(rule, card).verdict == MODEL.VERDICT_COMPLIANT


def test_ticket_type_match_no_conflict():
    rule = _rule(check_type="ticket_type_match",
                 params={"field": "task", "forbidden_terms": ["停电"]})
    card = _card(fields={"task": "设备巡视"})
    assert _verdict(rule, card).verdict == MODEL.VERDICT_COMPLIANT


def test_measure_coverage_no_measures_violation():
    rule = _rule(check_type="measure_coverage",
                 params={"elements": {"停电": ["断开"]}})
    assert _verdict(rule, _card(measures=[])).verdict == MODEL.VERDICT_VIOLATION


def test_measure_coverage_missing_element():
    rule = _rule(check_type="measure_coverage",
                 params={"elements": {"停电": ["断开"], "验电": ["验电"]}})
    conclusion = _verdict(rule, _card(measures=["断开断路器"]))
    assert conclusion.verdict == MODEL.VERDICT_VIOLATION
    assert "验电" in conclusion.evidence[0]


def test_measure_coverage_complete():
    rule = _rule(check_type="measure_coverage",
                 params={"elements": {"停电": ["断开"], "验电": ["验电"]}})
    conclusion = _verdict(rule, _card(measures=["断开断路器", "验电确无电压"]))
    assert conclusion.verdict == MODEL.VERDICT_COMPLIANT
    assert "覆盖齐全" in conclusion.evidence[0]


def test_measure_coverage_keyword_any_measure():
    rule = _rule(check_type="measure_coverage",
                 params={"elements": {"接地": ["装设接地线", "合上接地"]}})
    conclusion = _verdict(rule, _card(measures=["验电后装设接地线一组"]))
    assert conclusion.verdict == MODEL.VERDICT_COMPLIANT


# --------------------------------------------------------------------------
# §六 five_prevention / consistency
# --------------------------------------------------------------------------
def _fp_rule(variants):
    return _rule(check_type="five_prevention", params={"variants": variants})


def test_five_prevention_empty_sequence_manual():
    assert _verdict(_fp_rule(["no_load_disconnector"]), _card()).verdict == \
        MODEL.VERDICT_MANUAL


def test_five_prevention_load_disconnector_hit():
    card = _card(steps=["拉开312-1隔离开关"])
    assert _verdict(_fp_rule(["no_load_disconnector"]), card).verdict == \
        MODEL.VERDICT_VIOLATION


def test_five_prevention_load_disconnector_ok():
    card = _card(steps=["断开312断路器", "拉开312-1隔离开关"])
    assert _verdict(_fp_rule(["no_load_disconnector"]), card).verdict == \
        MODEL.VERDICT_COMPLIANT


def test_five_prevention_ground_close_hit():
    card = _card(steps=["装设接地线一组", "合上312断路器"])
    assert _verdict(_fp_rule(["no_ground_close"]), card).verdict == \
        MODEL.VERDICT_VIOLATION


def test_five_prevention_ground_close_ok():
    card = _card(steps=["装设接地线一组", "拆除接地线", "合上312断路器"])
    assert _verdict(_fp_rule(["no_ground_close"]), card).verdict == \
        MODEL.VERDICT_COMPLIANT


def test_five_prevention_grounding_after_test_hit():
    card = _card(steps=["装设接地线一组"])
    assert _verdict(_fp_rule(["grounding_after_test"]), card).verdict == \
        MODEL.VERDICT_VIOLATION


def test_five_prevention_grounding_after_test_ok():
    card = _card(steps=["验电确无电压", "装设接地线一组"])
    assert _verdict(_fp_rule(["grounding_after_test"]), card).verdict == \
        MODEL.VERDICT_COMPLIANT


def test_five_prevention_unknown_variant_ignored():
    card = _card(steps=["断开312断路器"])
    assert _verdict(_fp_rule(["no_such_variant"]), card).verdict == \
        MODEL.VERDICT_COMPLIANT


def test_five_prevention_multiple_variants_aggregate():
    card = _card(steps=["拉开312-1隔离开关", "装设接地线一组"])
    conclusion = _verdict(_fp_rule(["no_load_disconnector", "grounding_after_test"]), card)
    assert conclusion.verdict == MODEL.VERDICT_VIOLATION
    assert len(conclusion.evidence) == 2


def test_consistency_conflict():
    rule = _rule(check_type="consistency", params={"sources": ["steps"]})
    card = _card(steps=["断开110kV东湖线111断路器", "检查35kV东湖线111断路器"])
    conclusion = _verdict(rule, card)
    assert conclusion.verdict == MODEL.VERDICT_VIOLATION
    assert "电压等级标注不一致" in conclusion.evidence[0]


def test_consistency_no_markings_compliant():
    rule = _rule(check_type="consistency")
    conclusion = _verdict(rule, _card(fields={"task": "设备巡视"}))
    assert conclusion.verdict == MODEL.VERDICT_COMPLIANT
    assert "未发现可互证" in conclusion.evidence[0]


def test_consistency_consistent_markings():
    rule = _rule(check_type="consistency")
    card = _card(steps=["断开110kV东湖线111断路器", "拉开110kV东湖线111隔离开关"])
    conclusion = _verdict(rule, card)
    assert conclusion.verdict == MODEL.VERDICT_COMPLIANT
    assert "互证一致" in conclusion.evidence[0]


def test_consistency_task_source():
    rule = _rule(check_type="consistency", params={"sources": ["task"]})
    card = _card(fields={"task": "断开110kV东湖线111断路器"})
    assert _verdict(rule, card).verdict == MODEL.VERDICT_COMPLIANT


# --------------------------------------------------------------------------
# §七 两道门控：票种 + 依据闸
# --------------------------------------------------------------------------
def test_ticket_type_gate_skips_other_type():
    rule = _rule(applies_to=("work_first",))
    assert ENGINE.run_checks(_card(ticket_type="operating"), [rule]) == []


def test_ticket_type_gate_allows_listed_type():
    rule = _rule(applies_to=("work_first",))
    card = _card(ticket_type="work_first", fields={"ticket_no": "W1-1"})
    assert len(ENGINE.run_checks(card, [rule])) == 1


def test_gate_pending_violation_downgraded():
    rule = _rule(status="待核对", params={"fields": ["ticket_no"]})
    conclusion = _verdict(rule, _card(fields={}))
    assert conclusion.verdict == MODEL.VERDICT_MANUAL
    assert conclusion.downgraded is True


def test_gate_verified_violation_kept():
    rule = _rule(status="已核对", params={"fields": ["ticket_no"]})
    conclusion = _verdict(rule, _card(fields={}))
    assert conclusion.verdict == MODEL.VERDICT_VIOLATION
    assert conclusion.downgraded is False


def test_gate_does_not_swallow_conclusion():
    rule = _rule(status="待核对", params={"fields": ["ticket_no"]})
    conclusions = ENGINE.run_checks(_card(fields={}), [rule])
    assert conclusions
    assert any("ticket_no" in item for item in conclusions[0].evidence)


def test_gate_keeps_compliant_verdict():
    rule = _rule(status="待核对", params={"fields": ["ticket_no"]})
    conclusion = _verdict(rule, _card(fields={"ticket_no": "CZ-1"}))
    assert conclusion.verdict == MODEL.VERDICT_COMPLIANT
    assert conclusion.downgraded is False


def test_gate_keeps_existing_manual_verdict():
    rule = _rule(check_type="time_order", status="待核对",
                 params={"start": "start_time", "end": "end_time"})
    conclusion = _verdict(rule, _card(fields={"start_time": "2026-10-15T08:00"}))
    assert conclusion.verdict == MODEL.VERDICT_MANUAL
    assert conclusion.downgraded is False


def test_production_pending_never_violation():
    library = PIPELINE.load_library()
    for case in CASES:
        card = PIPELINE.build_card(_ticket(case))
        for conclusion in ENGINE.run_checks(card, library.rules):
            if conclusion.basis.get("status") != "已核对":
                assert conclusion.verdict != MODEL.VERDICT_VIOLATION


def test_production_verified_rules_exist():
    library = PIPELINE.load_library()
    verified = [rule for rule in library.rules if rule["basis"]["status"] == "已核对"]
    assert len(verified) == 9
    assert {rule["check_type"] for rule in verified} >= {
        "measure_coverage", "five_prevention", "process_signature"}


# --------------------------------------------------------------------------
# §八 汇总
# --------------------------------------------------------------------------
def _conclusions(verdicts):
    return [MODEL.Conclusion(rule_id="R-%d" % index, name="x", verdict=verdict)
            for index, verdict in enumerate(verdicts, 1)]


def test_summarize_counts():
    tally = ENGINE.summarize(_conclusions(["合规", "不合规", "待人工确认"]))
    assert tally["total"] == 3
    assert tally["compliant"] == 1
    assert tally["violation"] == 1
    assert tally["manual"] == 1


def test_summarize_empty():
    tally = ENGINE.summarize([])
    assert tally["total"] == 0
    assert tally["compliant"] == tally["violation"] == tally["manual"] == 0


def test_summarize_risk_distribution():
    tally = ENGINE.summarize([
        MODEL.Conclusion(rule_id="a", name="x", verdict="不合规", risk="较大"),
        MODEL.Conclusion(rule_id="b", name="x", verdict="不合规", risk="较大"),
        MODEL.Conclusion(rule_id="c", name="x", verdict="不合规", risk="一般"),
    ])
    assert tally["risk"] == {"一般": 1, "较大": 2}


def test_summarize_downgraded_count():
    tally = ENGINE.summarize([
        MODEL.Conclusion(rule_id="a", name="x", verdict="待人工确认", downgraded=True),
        MODEL.Conclusion(rule_id="b", name="x", verdict="待人工确认"),
    ])
    assert tally["downgraded"] == 1


# --------------------------------------------------------------------------
# §九 输入契约 / 条文本版本 / 锚点
# --------------------------------------------------------------------------
def test_subject_requires_case_id():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"ticket": {"ticket_type": "operating", "fields": {}}}, BASIS)


def test_subject_requires_ticket():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c"}, BASIS)


def test_subject_rejects_unknown_key():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c",
                           "ticket": {"ticket_type": "operating", "fields": {}},
                           "extra": 1}, BASIS)


def test_subject_unknown_ticket_type():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "ticket": {"ticket_type": "nope",
                                                      "fields": {}}}, BASIS)


def test_subject_bad_fields():
    with pytest.raises(ValueError):
        PACK_MOD.evaluate({"case_id": "c", "ticket": {"ticket_type": "operating",
                                                      "fields": []}}, BASIS)


def test_basis_version_mismatch_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(_subject(_ticket(CASES[0])), Basis.empty("1999-01-01"))


def test_basis_missing_clause_contract_error():
    with pytest.raises(ContractError):
        PACK_MOD.evaluate(_subject(_ticket(CASES[0])), Basis(REG.VERSION))


def test_contract_scalar_requires_same_version():
    assert BASIS.version == REG.VERSION


# --------------------------------------------------------------------------
# §十 账本映射 / 报告 / 退出码 / CLI
# --------------------------------------------------------------------------
def test_readme_record_count():
    assert len(_records(load_json(README_SAMPLE)).findings) == 7


def test_signature_record_count():
    assert len(_records(load_json(SIGNATURE_SAMPLE)).findings) == 6


def test_rules_finding_anchor():
    record = _find(_records(load_json(README_SAMPLE)).findings, PACK_MOD.RULE_RULES)
    assert record.verdict == PASS
    assert record.anchor.clause_id == PACK_MOD.CLAUSE_RULES
    assert record.evidence["rules"] == 39


def test_pending_finding_registered():
    record = _find(_records(load_json(README_SAMPLE)).findings, PACK_MOD.RULE_PENDING)
    assert record.verdict == NOT_APPLICABLE
    assert record.anchor.clause_id == PACK_MOD.CLAUSE_GATE
    assert record.evidence["pending"] == 30
    assert len(record.evidence["rule_ids"]) == 30


def test_readme_all_compliant_records():
    report = _records(load_json(README_SAMPLE))
    assert report.exit_code() == 0
    assert all(record.verdict == PASS
               for record in report.findings
               if record.rule_id.startswith("ticket.rule:"))


def test_signature_gap_fail_record():
    report = _records(load_json(SIGNATURE_SAMPLE))
    record = _find(report.findings, "ticket.rule:R-ER-003")
    assert record.verdict == FAIL
    assert record.evidence["risk"] == "一般"
    assert record.evidence["basis_status"] == "已核对"


def test_signature_gap_exit_one():
    assert _records(load_json(SIGNATURE_SAMPLE)).exit_code() == 1


def test_pending_sample_has_downgraded_record():
    report = _records(load_json(PENDING_SAMPLE))
    record = _find(report.findings, "ticket.rule:R-OP-002")
    assert record.verdict == NOT_APPLICABLE
    assert record.evidence["downgraded"] is True
    assert record.evidence["basis_status"] == "待核对"


def test_pending_sample_exit_zero():
    assert _records(load_json(PENDING_SAMPLE)).exit_code() == 0


def test_five_prevention_sample_fail():
    report = _records(load_json(FIVE_PREVENTION_SAMPLE))
    record = _find(report.findings, "ticket.rule:R-OP-003")
    assert record.verdict == FAIL
    assert report.exit_code() == 1


def test_summary_fail_when_violation():
    record = _find(_records(load_json(SIGNATURE_SAMPLE)).findings, PACK_MOD.RULE_SUMMARY)
    assert record.verdict == FAIL
    assert record.anchor.clause_id == PACK_MOD.CLAUSE_SUMMARY


def test_summary_pass_when_compliant():
    record = _find(_records(load_json(README_SAMPLE)).findings, PACK_MOD.RULE_SUMMARY)
    assert record.verdict == PASS


def test_summary_manual_when_only_manual(tmp_path):
    ticket = {"ticket_type": "operating",
              "fields": {"ticket_no": "CZ-1", "task": "设备巡视",
                         "start_time": "2026-10-15T09:00", "end_time": "2026-10-15T08:00",
                         "dispatcher": "A", "guardian": "B", "operator": "C"},
              "operation_sequence": ["断开312断路器"]}
    library = _library(_rule(rule_id="R-OP-002", check_type="time_order", status="待核对",
                             params={"start": "start_time", "end": "end_time"}))
    subject = _subject(ticket)
    findings = PACK_MOD.evaluate_with_library(subject, BASIS, library)
    # 注入的 R-OP-002 在条文库里有锚点，但只覆盖 time_order；summary 全为待人工
    report = Report(product="clauseproof", organ=SLUG, organ_version=PACK_MOD.VERSION,
                    subject="x.json", findings=tuple(findings))
    record = _find(report.findings, PACK_MOD.RULE_SUMMARY)
    assert record.verdict == NOT_APPLICABLE
    assert record.anchor.clause_id == PACK_MOD.CLAUSE_MANUAL


def test_every_non_na_record_has_anchor():
    report = _records(load_json(SIGNATURE_SAMPLE))
    for record in report.findings:
        if record.verdict != NOT_APPLICABLE:
            assert record.anchor is not None


def test_report_deterministic():
    first = _records(load_json(SIGNATURE_SAMPLE)).as_dict()["records"]
    second = _records(load_json(SIGNATURE_SAMPLE)).as_dict()["records"]
    assert [item["id"] for item in first] == [item["id"] for item in second]


def test_cli_list_contains_slug(capsys):
    assert cp_cli.main(["list"]) == 0
    assert SLUG in capsys.readouterr().out


def test_cli_check_readme_rc0():
    assert cp_cli.main(["check", SLUG, "--input", README_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_check_signature_rc1():
    assert cp_cli.main(["check", SLUG, "--input", SIGNATURE_SAMPLE,
                        "--basis", BASIS_PATH]) == 1


def test_cli_check_pending_rc0():
    assert cp_cli.main(["check", SLUG, "--input", PENDING_SAMPLE,
                        "--basis", BASIS_PATH]) == 0


def test_cli_missing_basis_is_contract_violation():
    assert cp_cli.main(["check", SLUG, "--input", README_SAMPLE]) == 3


def test_cli_missing_input_is_input_error():
    assert cp_cli.main(["check", SLUG, "--input", os.path.join(SAMPLES, "nope.json"),
                        "--basis", BASIS_PATH]) == 2


def test_cli_json_summary(capsys):
    assert cp_cli.main(["check", SLUG, "--input", README_SAMPLE,
                        "--basis", BASIS_PATH, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG
    assert payload["summary"]["verdicts"]["fail"] == 0


def test_cli_unknown_ticket_in_subject_rc2(tmp_path):
    subject = load_json(README_SAMPLE)
    subject["ticket"]["ticket_type"] = "nope"
    path = tmp_path / "case.json"
    path.write_text(json.dumps(subject, ensure_ascii=False), encoding="utf-8")
    assert cp_cli.main(["check", SLUG, "--input", str(path), "--basis", BASIS_PATH]) == 2


# --------------------------------------------------------------------------
# §十一 随包数据完整性
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


def test_manifest_rules_and_status():
    manifest = _manifest()
    assert manifest["rules"] == 39
    assert manifest["basis_status"] == {"已核对": 9, "待核对": 30}


def test_manifest_clause_count():
    assert _manifest()["clause_count"] == len(Basis.from_json(BASIS_PATH)) == 55


def test_manifest_case_count():
    assert _manifest()["ticket_cases"] == len(CASES) == 35


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


def test_every_rule_has_clause():
    library = PIPELINE.load_library()
    for rule in library.rules:
        assert BASIS.clause("ticket:rule:%s" % rule["id"]) is not None


def test_pending_rule_clauses_marked():
    library = PIPELINE.load_library()
    for rule in library.pending_rules:
        clause = BASIS.clause("ticket:rule:%s" % rule["id"])
        assert clause.text.startswith("【待核对】")


def test_verified_rule_clauses_not_marked():
    library = PIPELINE.load_library()
    for rule in library.rules:
        if rule["basis"]["status"] == "已核对":
            clause = BASIS.clause("ticket:rule:%s" % rule["id"])
            assert not clause.text.startswith("【待核对】")


def test_pending_clause_count_is_thirty():
    marked = [clause_id for clause_id in BASIS.clause_ids()
              if BASIS.clause(clause_id).text.startswith("【待核对】")]
    assert len(marked) == 30


def test_basis_documents_registered():
    for clause_id in ("ticket:basis:dlt-408", "ticket:basis:gb-26859",
                      "ticket:basis:gb-26860", "ticket:basis:nea-25",
                      "ticket:basis:qgdw-1799-1", "ticket:basis:qgdw-1799-2"):
        assert BASIS.clause(clause_id) is not None


def test_contracts_registered():
    expected = {PACK_MOD.CLAUSE_VERSION, PACK_MOD.CLAUSE_RULES, PACK_MOD.CLAUSE_GATE,
                PACK_MOD.CLAUSE_TICKET_TYPE, PACK_MOD.CLAUSE_CHECK_TYPE,
                PACK_MOD.CLAUSE_VERDICT, PACK_MOD.CLAUSE_REVIEW,
                PACK_MOD.CLAUSE_EVIDENCE, PACK_MOD.CLAUSE_SUMMARY,
                PACK_MOD.CLAUSE_MANUAL}
    assert all(BASIS.clause(clause_id) is not None for clause_id in expected)


def test_verified_clause_quote_is_law_text():
    clause = BASIS.clause("ticket:rule:R-W1-007")
    assert "国能发安全〔2023〕22号" in clause.path
    assert "1.2.7" in clause.path
    assert "停电" in clause.text and "验电" in clause.text


# --------------------------------------------------------------------------
# §十二 35 例带真值样例对账（来源基准口径）
# --------------------------------------------------------------------------
def _non_pass(case):
    card = PIPELINE.build_card(_ticket(case))
    conclusions = ENGINE.run_checks(card, PIPELINE.load_library().rules)
    return {conclusion.check_type for conclusion in conclusions
            if conclusion.verdict != MODEL.VERDICT_COMPLIANT}


@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_case_non_pass_set(case):
    expected = set(case["expect"]) | set(case["also_expect"])
    non_pass = _non_pass(case)
    if case["kind"] == "normal":
        assert non_pass == set()
    else:
        assert non_pass == expected


@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_case_verdict_gate_consistency(case):
    card = PIPELINE.build_card(_ticket(case))
    conclusions = ENGINE.run_checks(card, PIPELINE.load_library().rules)
    for conclusion in conclusions:
        if conclusion.basis.get("status") != "已核对":
            assert conclusion.verdict != MODEL.VERDICT_VIOLATION
        if conclusion.downgraded:
            assert conclusion.verdict == MODEL.VERDICT_MANUAL
            assert conclusion.basis.get("status") == "待核对"


@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_case_summary_matches_violations(case):
    card = PIPELINE.build_card(_ticket(case))
    conclusions = ENGINE.run_checks(card, PIPELINE.load_library().rules)
    tally = ENGINE.summarize(conclusions)
    assert tally["violation"] == sum(
        1 for conclusion in conclusions if conclusion.verdict == MODEL.VERDICT_VIOLATION)
    assert tally["compliant"] + tally["violation"] + tally["manual"] == tally["total"]


def test_case_kinds_distribution():
    kinds = {}
    for case in CASES:
        kinds[case["kind"]] = kinds.get(case["kind"], 0) + 1
    assert kinds == {"defect": 28, "normal": 7}


def test_case_ticket_types_covered():
    assert {case["ticket_type"] for case in CASES} == set(MODEL.TICKET_TYPE_NAMES)


def test_case_cards_all_build():
    for case in CASES:
        assert PIPELINE.build_card(_ticket(case)).ticket_type == case["ticket_type"]