"""器官 ``labeling-claims`` 无损测试（§7.3 判据 1/3 的观测面）。

移植纪律：来源产品的判定语义**逐条搬**，断言落在"判定结果"上。
来源仓判定层（13 文件 / 202 静态函数 / 实跑 205）逐文件处置见
``docs/labeling-claims.md`` §6.1；本文件按「27 条生效规则 × `pass`/`fail`/
`not_applicable` 三态 = 81 条」重建判定面，另加结构门、漂移门、边界与机制用例，
实跑条数 ≥ 判据 1 的 X = 205。

本文件同时是**漂移门**：``data/{gb45438-2025,labeling-measures}.json`` 与
``rulebook.RULES``、``data/national-fields.json`` 与 ``rulebook.FIELDS``、
``data/clauses.json`` 与 ``rulebook.CLAUSES`` 必须逐条一致。
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

SLUG = "labeling-claims"
PACK_DIR = os.path.join(SRC, "clauseproof", "packs", SLUG)

pack_mod = importlib.import_module("clauseproof.packs." + SLUG)
rulebook = importlib.import_module("clauseproof.packs." + SLUG + ".rulebook")
engine = importlib.import_module("clauseproof.packs." + SLUG + ".engine")

RULES = rulebook.RULES
PENDING = rulebook.PENDING_RULE_IDS
FIELDS = rulebook.FIELDS

SAMPLES = os.path.join(ROOT, "samples", SLUG)

SHA256 = "b" * 64
NOTICE = "本内容由人工智能生成合成"
PENDING_RULE_ID = pack_mod.PENDING_RULE_ID

#: 规则 id（冻结规则表里的稳定键；测试里一律引用常量，不抄第二份）
R_EXPORT_LABEL = "measures:explicit:export.file.label.presence"
R_PLATFORM_HINT = "measures:propagation:platform.hint.presence"


def gb(carrier, kind):
    """GB 45438-2025 §5 显式规则的 rule_id。"""
    return "gb45438:explicit:%s.notice.%s" % (carrier, kind)


R_PROPERTY_PRESENCE = "gb45438:implicit:content_property.presence"
R_PROPERTY_ENUM = "gb45438:implicit:content_property.enum"
R_PRODUCER_PRESENCE = "gb45438:implicit:content_producer.presence"
R_PRODUCER_TYPE = "gb45438:implicit:content_producer.type"
R_CONTENT_ID_PRESENCE = "gb45438:implicit:content_id.presence"
R_CONTENT_ID_TYPE = "gb45438:implicit:content_id.type"
R_UNIQUENESS = "gb45438:implicit:implicit_label.uniqueness"
R_PROPAGATOR = "gb45438:implicit:content_propagator.presence"
R_PROPAGATE_ID = "gb45438:implicit:propagate_id.presence"

KIND = {"presence": "presence", "position": "position",
        "ai": "ai_element", "gen": "gen_element"}


# --------------------------------------------------------------------------
# 夹具：标识卡构造与速取
# --------------------------------------------------------------------------
def element(name, present=True, position=None, value=None):
    item = {"element": name, "present": present}
    if position is not None:
        item["position"] = position
    if value is not None:
        item["value"] = value
    return item


def default_position(carrier):
    return "corner" if carrier == "image" else "head"


IMPLICIT_OK = {"AIGC:Label": "1",
               "AIGC:ContentProducer": "SYN-0001",
               "AIGC:ProduceID": "SYN-0001"}


def card(carrier="text", scenario="authored", explicit=None, implicit=None,
         observed=None, duplicates=None):
    """构造一张标识卡；默认是"全要素齐备"的卡片。"""
    if explicit is None:
        explicit = [element(carrier + "_explicit_notice", True,
                            default_position(carrier), NOTICE)]
        if scenario == "exported":
            explicit.append(element("exported_file_explicit_label", True))
        if scenario == "propagated":
            explicit.append(element("propagation_platform_hint", True))
    if implicit is None:
        implicit = dict(IMPLICIT_OK)
        if scenario == "propagated":
            implicit["AIGC:ContentPropagator"] = "PROP-0001"
            implicit["AIGC:PropagateID"] = "PROP-0001"
    data = {"card_id": "CASE-0001", "carrier": carrier, "content_sha256": SHA256,
            "explicit": explicit, "implicit": implicit, "scenario": scenario}
    if observed is not None:
        data["observed"] = observed
    if duplicates is not None:
        data["implicit_duplicate_keys"] = duplicates
    return data


def notice_card(carrier, **overrides):
    """只放该载体的显式要素（其余按 overrides 调整）。"""
    kwargs = {"position": default_position(carrier), "value": NOTICE}
    kwargs.update(overrides)
    return card(carrier, explicit=[element(carrier + "_explicit_notice", **kwargs)])


def findings_of(subject):
    return pack_mod.evaluate(subject, shipped_basis())


def find(rule_id, subject):
    matches = [finding for finding in findings_of(subject)
               if finding.rule_id == rule_id]
    assert len(matches) == 1, "规则 %s 应恰好产出一条结论，实得 %d" % (
        rule_id, len(matches))
    return matches[0]


def verdict_of(rule_id, subject):
    return find(rule_id, subject).verdict


def basis_path():
    return os.path.join(PACK_DIR, "data", "clauses.json")


def shipped_basis():
    return Basis.from_json(basis_path())


def frozen(name):
    with open(os.path.join(PACK_DIR, "data", name), "r", encoding="utf-8") as handle:
        return json.load(handle)


def frozen_rules():
    rows = []
    for name in ("gb45438-2025.json", "labeling-measures.json"):
        rows.extend(frozen(name)["rules"])
    return rows


def rule_of(rule_id):
    return [rule for rule in RULES if rule.rule_id == rule_id][0]


def probe_rule(**overrides):
    base = {"rule_id": "PROBE", "scope": "explicit", "carrier": (), "target": "probe",
            "check_type": "presence", "params": {}, "severity": "minor",
            "scenarios": (), "clause_id": "gb45438:5.1:a", "status": "verified"}
    base.update(overrides)
    return engine.Rule(**base)


# ==========================================================================
# 一、器官契约与规则表结构
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
    assert get(SLUG).input_fields == ("card_id", "carrier", "content_sha256")


def test_pack_has_no_own_argument_parser():
    import ast

    for name in ("__init__.py", "engine.py", "rulebook.py"):
        with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(alias.name == "argparse" for alias in node.names), name
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "argparse", name


def test_engine_has_no_io_clock_or_env():
    """判定内核不读文件、不读环境变量、不读时钟、不打印（执行约束的静态形态）。"""
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


def test_rulebook_does_not_read_files():
    """规则表是 Python 字面量：不得 import 文件/JSON/路径库，不得调用 open。"""
    import ast

    with open(os.path.join(PACK_DIR, "rulebook.py"), "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in ("os", "io", "json", "pathlib"), alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in ("os", "io", "json", "pathlib"), node.module
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("open", "print"), node.func.id


def test_engine_and_rulebook_do_not_print():
    import ast

    for name in ("engine.py", "rulebook.py"):
        with open(os.path.join(PACK_DIR, name), "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "print", name


def test_rule_count_is_34():
    assert len(RULES) == 34
    assert len([rule for rule in RULES if rule.is_effective]) == 27
    assert len(PENDING) == 7


def test_effective_rules_are_27():
    assert len([rule for rule in RULES if rule.is_effective]) == 27


def test_pending_rules_are_the_seven_measures_entries():
    assert len(PENDING) == 7
    assert all(rule_id.startswith("measures:") for rule_id in PENDING)
    assert all(not rule_of(rule_id).is_effective for rule_id in PENDING)


def test_rule_ids_are_unique():
    ids = [rule.rule_id for rule in RULES]
    assert len(ids) == len(set(ids))


def test_every_rule_declares_legal_enums():
    for rule in RULES:
        assert rule.scope in engine.SCOPES, rule.rule_id
        assert rule.check_type in engine.CHECK_TYPES, rule.rule_id
        assert rule.severity in engine.SEVERITIES, rule.rule_id
        for scenario in rule.scenarios:
            assert scenario in engine.SCENARIOS, rule.rule_id
        for carrier in rule.carrier:
            assert carrier in engine.CARRIERS, rule.rule_id


def test_every_effective_rule_has_a_clause():
    clause_ids = set(rulebook.clause_ids())
    for rule in RULES:
        if rule.is_effective:
            assert rule.clause_id, rule.rule_id
            assert rule.clause_id in clause_ids, rule.rule_id


def test_pending_rules_carry_no_clause():
    """待核对条目的条号未核对，因此没有可引用的 clause_id（不得锚定半个条款）。"""
    for rule_id in PENDING:
        assert rule_of(rule_id).clause_id == ""


def test_effective_rule_split_is_16_plus_2_plus_9():
    explicit = [rule for rule in RULES if rule.is_effective and rule.scope == "explicit"]
    implicit = [rule for rule in RULES if rule.is_effective and rule.scope == "implicit"]
    assert len(explicit) == 18
    assert len(implicit) == 9
    assert len([rule for rule in explicit if rule.carrier]) == 16
    assert len([rule for rule in explicit if not rule.carrier]) == 2


def test_rule_declaration_order_is_stable():
    """规则表声明序 = 冻结产物顺序（判定输出顺序依赖它）：先办法 9 条，再国标 25 条。"""
    measures = [row["rule_id"] for row in frozen("labeling-measures.json")["rules"]]
    gb_rows = [row["rule_id"] for row in frozen("gb45438-2025.json")["rules"]]
    assert [rule.rule_id for rule in RULES] == measures + gb_rows


# ==========================================================================
# 二、漂移门：data/*.json ↔ rulebook 字面量
# ==========================================================================
def test_data_dir_is_present_and_non_empty():
    names = sorted(os.listdir(os.path.join(PACK_DIR, "data")))
    assert names == ["clauses.json", "gb45438-2025.json",
                     "labeling-measures.json", "national-fields.json"]


def test_clause_count_matches_shipped_basis():
    assert len(rulebook.CLAUSES) == len(shipped_basis()) == 27


def test_clause_ids_match_shipped_basis():
    basis = shipped_basis()
    assert list(rulebook.clause_ids()) == basis.clause_ids()


def test_clause_paths_match_shipped_basis():
    basis = shipped_basis()
    for clause_id, path, _text, _source in rulebook.CLAUSES:
        assert basis.clause(clause_id).path == path, clause_id


def test_clause_texts_match_shipped_basis():
    basis = shipped_basis()
    for clause_id, _path, text, _source in rulebook.CLAUSES:
        assert basis.clause(clause_id).text == text, clause_id


def test_basis_version_is_single_value():
    assert shipped_basis().version == rulebook.BASIS_VERSION


def test_gb_frozen_rule_ids_match():
    frozen_ids = [row["rule_id"] for row in frozen("gb45438-2025.json")["rules"]]
    literal_ids = [rule.rule_id for rule in RULES
                   if rule.rule_id.startswith("gb45438:")]
    assert literal_ids == frozen_ids
    assert len(literal_ids) == 25


def test_measures_frozen_rule_ids_match():
    frozen_ids = [row["rule_id"] for row in frozen("labeling-measures.json")["rules"]]
    literal_ids = [rule.rule_id for rule in RULES
                   if rule.rule_id.startswith("measures:")]
    assert literal_ids == frozen_ids
    assert len(literal_ids) == 9


def test_frozen_rule_fields_match_literal():
    by_id = {rule.rule_id: rule for rule in RULES}
    for row in frozen_rules():
        rule = by_id[row["rule_id"]]
        only_if = row.get("only_if") or {}
        assert rule.scope == row["scope"], row["rule_id"]
        assert list(rule.carrier) == list(row["carrier"]), row["rule_id"]
        assert rule.target == row["target"], row["rule_id"]
        assert rule.check_type == row["check_type"], row["rule_id"]
        assert dict(rule.params) == row["params"], row["rule_id"]
        assert rule.severity == row["severity"], row["rule_id"]
        assert rule.status == row["status"], row["rule_id"]
        assert list(rule.scenarios) == list(only_if.get("scenario") or ()), row["rule_id"]
        assert list(rule.carrier) == list(only_if.get("carrier") or ()), row["rule_id"]


def test_frozen_rule_clause_text_matches_clauses():
    by_id = {rule.rule_id: rule for rule in RULES}
    clauses = {clause_id: (path, text)
               for clause_id, path, text, _source in rulebook.CLAUSES}
    for row in frozen_rules():
        rule = by_id[row["rule_id"]]
        if not rule.is_effective:
            assert rule.clause_id == ""
            continue
        assert clauses[rule.clause_id][1] == row["clause"]["excerpt"], row["rule_id"]


def test_gb_clause_path_is_composed_from_article():
    by_id = {rule.rule_id: rule for rule in RULES}
    clauses = {clause_id: path for clause_id, path, _t, _s in rulebook.CLAUSES}
    for row in frozen("gb45438-2025.json")["rules"]:
        rule = by_id[row["rule_id"]]
        if not rule.is_effective:
            continue
        assert clauses[rule.clause_id] == "GB 45438-2025/" + row["clause"]["article"]


def test_measures_clause_path_is_composed_from_article():
    by_id = {rule.rule_id: rule for rule in RULES}
    clauses = {clause_id: path for clause_id, path, _t, _s in rulebook.CLAUSES}
    for row in frozen("labeling-measures.json")["rules"]:
        rule = by_id[row["rule_id"]]
        if not rule.is_effective:
            continue
        assert clauses[rule.clause_id] == rulebook.MEASURES + "/" + row["clause"]["article"]


def test_field_mapping_count_is_five():
    assert len(FIELDS) == len(frozen("national-fields.json")["fields"]) == 5


def _frozen_field(national_field):
    rows = frozen("national-fields.json")["fields"]
    return [row for row in rows if row["national_field"] == national_field][0]


def _assert_field_matches(national_field):
    mapping = [item for item in FIELDS if item.national_field == national_field][0]
    row = _frozen_field(national_field)
    assert list(mapping.aliases) == list(row["aliases"])
    assert row["status"] == "verified"


def test_field_content_property_matches_frozen():
    _assert_field_matches("content_property")


def test_field_content_producer_matches_frozen():
    _assert_field_matches("content_producer")


def test_field_content_id_matches_frozen():
    _assert_field_matches("content_id")


def test_field_content_propagator_matches_frozen():
    _assert_field_matches("content_propagator")


def test_field_propagate_id_matches_frozen():
    _assert_field_matches("propagate_id")


def test_mapping_order_matches_frozen_files():
    frozen_order = [row["national_field"]
                    for row in frozen("national-fields.json")["fields"]]
    assert [mapping.national_field for mapping in FIELDS] == frozen_order


# ==========================================================================
# 三、27 条生效规则 × pass / fail / not_applicable 三态（81 条）
# ==========================================================================
# ---- 《标识办法》2 条 verified：导出与传播场景义务 ----
def test_rule_export_label_pass():
    assert verdict_of(R_EXPORT_LABEL, card("text", "exported")) == PASS


def test_rule_export_label_fail():
    assert verdict_of(R_EXPORT_LABEL, card("text", "exported", explicit=[])) == FAIL


def test_rule_export_label_na():
    assert verdict_of(R_EXPORT_LABEL, card("text", "authored")) == NOT_APPLICABLE


def test_rule_platform_hint_pass():
    assert verdict_of(R_PLATFORM_HINT, card("text", "propagated")) == PASS


def test_rule_platform_hint_fail():
    assert verdict_of(R_PLATFORM_HINT,
                      card("text", "propagated", explicit=[])) == FAIL


def test_rule_platform_hint_na():
    assert verdict_of(R_PLATFORM_HINT, card("text", "authored")) == NOT_APPLICABLE


# ---- GB 45438-2025 §5.1 文本显式 ----
def test_rule_text_presence_pass():
    assert verdict_of(gb("text", KIND["presence"]), notice_card("text")) == PASS


def test_rule_text_presence_fail():
    assert verdict_of(gb("text", KIND["presence"]),
                      notice_card("text", present=False)) == FAIL


def test_rule_text_presence_na():
    assert verdict_of(gb("text", KIND["presence"]),
                      card("text", observed={"explicit": False})) == NOT_APPLICABLE


def test_rule_text_position_pass():
    assert verdict_of(gb("text", KIND["position"]),
                      notice_card("text", position="middle")) == PASS


def test_rule_text_position_fail():
    assert verdict_of(gb("text", KIND["position"]),
                      notice_card("text", position="corner")) == FAIL


def test_rule_text_position_na():
    assert verdict_of(gb("text", KIND["position"]),
                      notice_card("text", position=None)) == NOT_APPLICABLE


def test_rule_text_ai_pass():
    assert verdict_of(gb("text", KIND["ai"]), notice_card("text")) == PASS


def test_rule_text_ai_fail():
    assert verdict_of(gb("text", KIND["ai"]),
                      notice_card("text", value="本内容由生成合成")) == FAIL


def test_rule_text_ai_na():
    assert verdict_of(gb("text", KIND["ai"]),
                      notice_card("text", value=None)) == NOT_APPLICABLE


def test_rule_text_gen_pass():
    assert verdict_of(gb("text", KIND["gen"]), notice_card("text")) == PASS


def test_rule_text_gen_fail():
    assert verdict_of(gb("text", KIND["gen"]),
                      notice_card("text", value="本内容由人工智能提供")) == FAIL


def test_rule_text_gen_na():
    assert verdict_of(gb("text", KIND["gen"]),
                      notice_card("text", value=None)) == NOT_APPLICABLE


# ---- GB 45438-2025 §5.2 图片显式 ----
def test_rule_image_presence_pass():
    assert verdict_of(gb("image", KIND["presence"]), notice_card("image")) == PASS


def test_rule_image_presence_fail():
    assert verdict_of(gb("image", KIND["presence"]),
                      notice_card("image", present=False)) == FAIL


def test_rule_image_presence_na():
    assert verdict_of(gb("image", KIND["presence"]),
                      card("image", observed={"explicit": False})) == NOT_APPLICABLE


def test_rule_image_position_pass():
    assert verdict_of(gb("image", KIND["position"]),
                      notice_card("image", position="edge")) == PASS


def test_rule_image_position_fail():
    assert verdict_of(gb("image", KIND["position"]),
                      notice_card("image", position="head")) == FAIL


def test_rule_image_position_na():
    assert verdict_of(gb("image", KIND["position"]),
                      notice_card("image", position=None)) == NOT_APPLICABLE


def test_rule_image_ai_pass():
    assert verdict_of(gb("image", KIND["ai"]), notice_card("image")) == PASS


def test_rule_image_ai_fail():
    assert verdict_of(gb("image", KIND["ai"]),
                      notice_card("image", value="本内容由合成")) == FAIL


def test_rule_image_ai_na():
    assert verdict_of(gb("image", KIND["ai"]),
                      notice_card("image", value=None)) == NOT_APPLICABLE


def test_rule_image_gen_pass():
    assert verdict_of(gb("image", KIND["gen"]), notice_card("image")) == PASS


def test_rule_image_gen_fail():
    assert verdict_of(gb("image", KIND["gen"]),
                      notice_card("image", value="本内容由AI提供")) == FAIL


def test_rule_image_gen_na():
    assert verdict_of(gb("image", KIND["gen"]),
                      notice_card("image", value=None)) == NOT_APPLICABLE


# ---- GB 45438-2025 §5.3 音频显式 ----
def test_rule_audio_presence_pass():
    assert verdict_of(gb("audio", KIND["presence"]), notice_card("audio")) == PASS


def test_rule_audio_presence_fail():
    assert verdict_of(gb("audio", KIND["presence"]),
                      notice_card("audio", present=False)) == FAIL


def test_rule_audio_presence_na():
    assert verdict_of(gb("audio", KIND["presence"]),
                      card("audio", observed={"explicit": False})) == NOT_APPLICABLE


def test_rule_audio_position_pass():
    assert verdict_of(gb("audio", KIND["position"]),
                      notice_card("audio", position="tail")) == PASS


def test_rule_audio_position_fail():
    assert verdict_of(gb("audio", KIND["position"]),
                      notice_card("audio", position="corner")) == FAIL


def test_rule_audio_position_na():
    assert verdict_of(gb("audio", KIND["position"]),
                      notice_card("audio", position=None)) == NOT_APPLICABLE


def test_rule_audio_ai_pass():
    assert verdict_of(gb("audio", KIND["ai"]), notice_card("audio")) == PASS


def test_rule_audio_ai_fail():
    assert verdict_of(gb("audio", KIND["ai"]),
                      notice_card("audio", value="本内容由生成合成")) == FAIL


def test_rule_audio_ai_na():
    assert verdict_of(gb("audio", KIND["ai"]),
                      notice_card("audio", value=None)) == NOT_APPLICABLE


def test_rule_audio_gen_pass():
    assert verdict_of(gb("audio", KIND["gen"]), notice_card("audio")) == PASS


def test_rule_audio_gen_fail():
    assert verdict_of(gb("audio", KIND["gen"]),
                      notice_card("audio", value="本内容由人工智能提供")) == FAIL


def test_rule_audio_gen_na():
    assert verdict_of(gb("audio", KIND["gen"]),
                      notice_card("audio", value=None)) == NOT_APPLICABLE


# ---- GB 45438-2025 §5.4 视频显式 ----
def test_rule_video_presence_pass():
    assert verdict_of(gb("video", KIND["presence"]), notice_card("video")) == PASS


def test_rule_video_presence_fail():
    assert verdict_of(gb("video", KIND["presence"]),
                      notice_card("video", present=False)) == FAIL


def test_rule_video_presence_na():
    assert verdict_of(gb("video", KIND["presence"]),
                      card("video", observed={"explicit": False})) == NOT_APPLICABLE


def test_rule_video_position_pass():
    assert verdict_of(gb("video", KIND["position"]),
                      notice_card("video", position="tail")) == PASS


def test_rule_video_position_fail():
    assert verdict_of(gb("video", KIND["position"]),
                      notice_card("video", position="corner")) == FAIL


def test_rule_video_position_na():
    assert verdict_of(gb("video", KIND["position"]),
                      notice_card("video", position=None)) == NOT_APPLICABLE


def test_rule_video_ai_pass():
    assert verdict_of(gb("video", KIND["ai"]), notice_card("video")) == PASS


def test_rule_video_ai_fail():
    assert verdict_of(gb("video", KIND["ai"]),
                      notice_card("video", value="本内容由合成")) == FAIL


def test_rule_video_ai_na():
    assert verdict_of(gb("video", KIND["ai"]),
                      notice_card("video", value=None)) == NOT_APPLICABLE


def test_rule_video_gen_pass():
    assert verdict_of(gb("video", KIND["gen"]), notice_card("video")) == PASS


def test_rule_video_gen_fail():
    assert verdict_of(gb("video", KIND["gen"]),
                      notice_card("video", value="本内容由AI提供")) == FAIL


def test_rule_video_gen_na():
    assert verdict_of(gb("video", KIND["gen"]),
                      notice_card("video", value=None)) == NOT_APPLICABLE


# ---- GB 45438-2025 §6.1 隐式标识（标签要素） ----
def test_rule_property_presence_pass():
    assert verdict_of(R_PROPERTY_PRESENCE, card()) == PASS


def test_rule_property_presence_fail():
    implicit = {"AIGC:ContentProducer": "SYN-0001", "AIGC:ProduceID": "SYN-0001"}
    assert verdict_of(R_PROPERTY_PRESENCE, card(implicit=implicit)) == FAIL


def test_rule_property_presence_na():
    assert verdict_of(R_PROPERTY_PRESENCE,
                      card(observed={"implicit": False})) == NOT_APPLICABLE


def test_rule_property_enum_pass():
    assert verdict_of(R_PROPERTY_ENUM, card()) == PASS


def test_rule_property_enum_fail():
    implicit = dict(IMPLICIT_OK, **{"AIGC:Label": "9"})
    assert verdict_of(R_PROPERTY_ENUM, card(implicit=implicit)) == FAIL


def test_rule_property_enum_na():
    implicit = {"AIGC:ContentProducer": "SYN-0001", "AIGC:ProduceID": "SYN-0001"}
    assert verdict_of(R_PROPERTY_ENUM, card(implicit=implicit)) == NOT_APPLICABLE


# ---- GB 45438-2025 §6.1 隐式标识（服务提供者要素） ----
def test_rule_producer_presence_pass():
    assert verdict_of(R_PRODUCER_PRESENCE, card()) == PASS


def test_rule_producer_presence_fail():
    implicit = {"AIGC:Label": "1", "AIGC:ProduceID": "SYN-0001"}
    assert verdict_of(R_PRODUCER_PRESENCE, card(implicit=implicit)) == FAIL


def test_rule_producer_presence_na():
    assert verdict_of(R_PRODUCER_PRESENCE,
                      card(observed={"implicit": False})) == NOT_APPLICABLE


def test_rule_producer_type_pass():
    assert verdict_of(R_PRODUCER_TYPE, card()) == PASS


def test_rule_producer_type_fail():
    implicit = dict(IMPLICIT_OK, **{"AIGC:ContentProducer": 123})
    assert verdict_of(R_PRODUCER_TYPE, card(implicit=implicit)) == FAIL


def test_rule_producer_type_na():
    implicit = {"AIGC:Label": "1", "AIGC:ProduceID": "SYN-0001"}
    assert verdict_of(R_PRODUCER_TYPE, card(implicit=implicit)) == NOT_APPLICABLE


# ---- GB 45438-2025 §6.1 隐式标识（内容制作编号要素） ----
def test_rule_content_id_presence_pass():
    assert verdict_of(R_CONTENT_ID_PRESENCE, card()) == PASS


def test_rule_content_id_presence_fail():
    implicit = {"AIGC:Label": "1", "AIGC:ContentProducer": "SYN-0001"}
    assert verdict_of(R_CONTENT_ID_PRESENCE, card(implicit=implicit)) == FAIL


def test_rule_content_id_presence_na():
    assert verdict_of(R_CONTENT_ID_PRESENCE,
                      card(observed={"implicit": False})) == NOT_APPLICABLE


def test_rule_content_id_type_pass():
    assert verdict_of(R_CONTENT_ID_TYPE, card()) == PASS


def test_rule_content_id_type_fail():
    implicit = dict(IMPLICIT_OK, **{"AIGC:ProduceID": 456})
    assert verdict_of(R_CONTENT_ID_TYPE, card(implicit=implicit)) == FAIL


def test_rule_content_id_type_na():
    implicit = {"AIGC:Label": "1", "AIGC:ContentProducer": "SYN-0001"}
    assert verdict_of(R_CONTENT_ID_TYPE, card(implicit=implicit)) == NOT_APPLICABLE


# ---- GB 45438-2025 §6.1 c)：隐式标识唯一性 ----
def test_rule_uniqueness_pass():
    assert verdict_of(R_UNIQUENESS, card()) == PASS


def test_rule_uniqueness_fail():
    implicit = dict(IMPLICIT_OK, Label="1")
    assert verdict_of(R_UNIQUENESS, card(implicit=implicit)) == FAIL


def test_rule_uniqueness_na():
    assert verdict_of(R_UNIQUENESS, card(implicit={})) == NOT_APPLICABLE


# ---- 传播场景两条（§6.1 a) 4/5)）----
def test_rule_propagator_presence_pass():
    assert verdict_of(R_PROPAGATOR, card("text", "propagated")) == PASS


def test_rule_propagator_presence_fail():
    implicit = {"AIGC:Label": "1", "AIGC:ContentProducer": "SYN-0001",
                "AIGC:ProduceID": "SYN-0001", "AIGC:PropagateID": "PROP-0001"}
    assert verdict_of(R_PROPAGATOR, card("text", "propagated",
                                         implicit=implicit)) == FAIL


def test_rule_propagator_presence_na():
    assert verdict_of(R_PROPAGATOR, card("text", "authored")) == NOT_APPLICABLE


def test_rule_propagate_id_presence_pass():
    assert verdict_of(R_PROPAGATE_ID, card("text", "propagated")) == PASS


def test_rule_propagate_id_presence_fail():
    implicit = {"AIGC:Label": "1", "AIGC:ContentProducer": "SYN-0001",
                "AIGC:ProduceID": "SYN-0001", "AIGC:ContentPropagator": "PROP-0001"}
    assert verdict_of(R_PROPAGATE_ID, card("text", "propagated",
                                           implicit=implicit)) == FAIL


def test_rule_propagate_id_presence_na():
    assert verdict_of(R_PROPAGATE_ID, card("text", "authored")) == NOT_APPLICABLE


# ==========================================================================
# 四、边界、账本映射与机制
# ==========================================================================
def report_of(subject):
    return Report(product="clauseproof", organ=SLUG, organ_version=pack_mod.VERSION,
                  subject="case", findings=tuple(findings_of(subject)))


def resolution(national_field, implicit):
    return engine.resolve_fields(implicit, FIELDS)[national_field]


# ---- 4.1 四载体全绿与载体门控 ----
def test_text_all_green_zero_blocking():
    assert report_of(card("text")).summary()["blocking"] == 0


def test_image_all_green_zero_blocking():
    assert report_of(card("image")).summary()["blocking"] == 0


def test_audio_all_green_zero_blocking():
    assert report_of(card("audio")).summary()["blocking"] == 0


def test_video_all_green_zero_blocking():
    assert report_of(card("video")).summary()["blocking"] == 0


def test_text_card_ignores_image_rules():
    ids = [finding.rule_id for finding in findings_of(card("text"))]
    assert not any("image.notice" in rule_id for rule_id in ids)


def test_image_card_ignores_text_rules():
    ids = [finding.rule_id for finding in findings_of(card("image"))]
    assert not any("text.notice" in rule_id for rule_id in ids)


def test_audio_card_ignores_video_rules():
    ids = [finding.rule_id for finding in findings_of(card("audio"))]
    assert not any("video.notice" in rule_id for rule_id in ids)


def test_empty_element_list_equals_element_absent():
    finding = find(gb("text", KIND["presence"]), card("text", explicit=[]))
    assert finding.verdict == FAIL
    assert finding.evidence["code"] == "element_absent"


# ---- 4.2 位置允许集（逐值）----
def test_text_position_head_passes():
    assert verdict_of(gb("text", KIND["position"]),
                      notice_card("text", position="head")) == PASS


def test_text_position_middle_passes():
    assert verdict_of(gb("text", KIND["position"]),
                      notice_card("text", position="middle")) == PASS


def test_text_position_tail_passes():
    assert verdict_of(gb("text", KIND["position"]),
                      notice_card("text", position="tail")) == PASS


def test_text_position_corner_fails():
    assert verdict_of(gb("text", KIND["position"]),
                      notice_card("text", position="corner")) == FAIL


def test_image_position_edge_passes():
    assert verdict_of(gb("image", KIND["position"]),
                      notice_card("image", position="edge")) == PASS


def test_image_position_head_fails():
    assert verdict_of(gb("image", KIND["position"]),
                      notice_card("image", position="head")) == FAIL


def test_video_position_tail_passes():
    assert verdict_of(gb("video", KIND["position"]),
                      notice_card("video", position="tail")) == PASS


# ---- 4.3 关键词分裂（AI / 生成合成 互不串台）----
def test_value_without_ai_breaks_only_ai_rule():
    subject = notice_card("text", value="本内容由生成合成")
    assert verdict_of(gb("text", KIND["ai"]), subject) == FAIL
    assert verdict_of(gb("text", KIND["gen"]), subject) == PASS


def test_value_without_gen_breaks_only_gen_rule():
    subject = notice_card("text", value="本内容由人工智能提供")
    assert verdict_of(gb("text", KIND["gen"]), subject) == FAIL
    assert verdict_of(gb("text", KIND["ai"]), subject) == PASS


def test_value_with_both_keywords_passes_both():
    subject = notice_card("text")
    assert verdict_of(gb("text", KIND["ai"]), subject) == PASS
    assert verdict_of(gb("text", KIND["gen"]), subject) == PASS


def test_lowercase_ai_does_not_match_the_keyword_set():
    """关键词集是「人工智能|AI」：小写 ai 不命中（保持来源产品的字面口径）。"""
    assert verdict_of(gb("text", KIND["ai"]),
                      notice_card("text", value="本内容由ai生成")) == FAIL


# ---- 4.4 场景门控 ----
def test_export_rule_skipped_in_authored_scenario():
    finding = find(R_EXPORT_LABEL, card("text", "authored"))
    assert finding.verdict == NOT_APPLICABLE
    assert finding.evidence["code"] == "scenario_not_applicable"


def test_export_rule_applies_in_exported_scenario():
    assert verdict_of(R_EXPORT_LABEL, card("text", "exported")) == PASS


def test_export_rule_fails_when_exported_label_absent():
    explicit = [element("text_explicit_notice", True, "head", NOTICE)]
    assert verdict_of(R_EXPORT_LABEL,
                      card("text", "exported", explicit=explicit)) == FAIL


def test_propagation_hint_skipped_in_authored_scenario():
    finding = find(R_PLATFORM_HINT, card("text", "authored"))
    assert finding.verdict == NOT_APPLICABLE
    assert finding.evidence["code"] == "scenario_not_applicable"


def test_propagation_hint_applies_when_propagated():
    assert verdict_of(R_PLATFORM_HINT, card("text", "propagated")) == PASS


def test_propagation_hint_fails_when_absent():
    explicit = [element("text_explicit_notice", True, "head", NOTICE)]
    assert verdict_of(R_PLATFORM_HINT,
                      card("text", "propagated", explicit=explicit)) == FAIL


# ---- 4.5 待核对 7 条 ----
def test_pending_rules_never_enter_judgement():
    ids = {finding.rule_id for finding in findings_of(card("text"))}
    assert ids.isdisjoint(set(PENDING))


def test_pending_registration_line_is_single_and_unanchored():
    pending = [finding for finding in findings_of(card("text"))
               if finding.rule_id == PENDING_RULE_ID]
    assert len(pending) == 1
    assert pending[0].verdict == NOT_APPLICABLE
    assert pending[0].anchor is None


def test_pending_message_lists_all_seven_ids():
    message = find(PENDING_RULE_ID, card("text")).message
    assert "7 条待核对" in message
    for rule_id in PENDING:
        assert rule_id in message


# ---- 4.6 观测作用域 ----
def test_unobserved_explicit_marks_each_explicit_rule_na():
    findings = [finding for finding in findings_of(card("text", observed={"explicit": False}))
                if finding.evidence.get("code") == "explicit_not_observed"]
    assert len(findings) == 4
    assert all(finding.verdict == NOT_APPLICABLE for finding in findings)


def test_unobserved_explicit_yields_no_fail_verdicts():
    subject = card("text", explicit=[], observed={"explicit": False})
    assert not [f for f in findings_of(subject) if f.verdict == FAIL]


def test_unobserved_implicit_marks_each_implicit_rule_na():
    """9 条隐式生效规则里，7 条走"未观测"、2 条传播场景规则先被场景门控拦下。"""
    findings = [finding for finding in findings_of(card("text", observed={"implicit": False}))
                if finding.evidence.get("code") == "implicit_not_observed"]
    assert len(findings) == 7
    assert all(finding.verdict == NOT_APPLICABLE for finding in findings)
    assert verdict_of(R_PROPAGATOR, card("text", observed={"implicit": False})) == \
        NOT_APPLICABLE


def test_unobserved_implicit_yields_no_fail_verdicts():
    subject = card("text", implicit={}, observed={"implicit": False})
    assert not [f for f in findings_of(subject) if f.verdict == FAIL]


def test_both_scopes_unobserved_yields_zero_blocking():
    subject = card("text", explicit=[], implicit={},
                   observed={"explicit": False, "implicit": False})
    assert report_of(subject).summary()["blocking"] == 0


# ---- 4.7 标识卡契约（输入不合法 → 退出码 2）----
def test_card_is_accepted_with_required_fields_only():
    obj = engine.Card.from_subject({"card_id": "X", "carrier": "text",
                                    "content_sha256": SHA256})
    assert obj.explicit == []
    assert obj.implicit == {}


def test_card_rejects_non_mapping():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(["x"])


def test_card_rejects_blank_card_id():
    for bad in ("", "   ", None):
        with pytest.raises(engine.CheckError):
            engine.Card.from_subject(dict(card(), card_id=bad))


def test_card_rejects_unknown_carrier():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), carrier="pdf"))


def test_card_rejects_short_sha256():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), content_sha256="abc"))


def test_card_rejects_uppercase_sha256():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), content_sha256="B" * 64))


def test_card_rejects_non_hex_sha256():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), content_sha256="g" * 64))


def test_card_rejects_missing_sha256():
    data = card()
    data.pop("content_sha256")
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(data)


def test_card_rejects_unknown_source():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), source="auto"))


def test_card_rejects_unknown_scenario():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), scenario="broadcast"))


def test_card_rejects_non_list_explicit():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), explicit={}))


def test_card_rejects_non_dict_explicit_item():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), explicit=["text_explicit_notice"]))


def test_card_rejects_explicit_item_without_element():
    for bad in ({}, {"element": ""}, {"element": None}):
        with pytest.raises(engine.CheckError):
            engine.Card.from_subject(dict(card(), explicit=[bad]))


def test_card_rejects_non_dict_implicit():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), implicit=[]))


def test_card_rejects_bad_duplicate_keys():
    for bad in ([""], [1], "AIGC:Label", [None]):
        with pytest.raises(engine.CheckError):
            engine.Card.from_subject(dict(card(), implicit_duplicate_keys=bad))


def test_card_rejects_non_string_notes():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), notes=123))


def test_card_rejects_unknown_observed_scope():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), observed={"else": True}))


def test_card_rejects_non_bool_observed():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), observed={"explicit": "yes"}))


def test_card_rejects_non_object_observed():
    with pytest.raises(engine.CheckError):
        engine.Card.from_subject(dict(card(), observed=["explicit"]))


# ---- 4.8 默认值与等价形态 ----
def test_default_source_is_manual():
    assert engine.Card.from_subject(card()).source == "manual"


def test_default_scenario_is_authored():
    assert engine.Card.from_subject(card()).scenario == "authored"


def test_default_observed_observes_both_scopes():
    obj = engine.Card.from_subject(card())
    assert obj.observes("explicit") is True
    assert obj.observes("implicit") is True


def test_notes_null_is_empty():
    assert engine.Card.from_subject(dict(card(), notes=None)).notes == ""


def test_duplicate_keys_null_is_empty():
    assert engine.Card.from_subject(
        dict(card(), implicit_duplicate_keys=None)).implicit_duplicate_keys == ()


# ---- 4.9 字段映射（别名归一与歧义登记）----
def test_primary_key_beats_alias():
    got = resolution("content_property", {"AIGC:Label": "1", "Label": "2"})
    assert got.matched_key == "AIGC:Label"
    assert got.value == "1"
    assert got.alternatives == ("Label",)


def test_alias_order_is_declaration_order():
    got = resolution("content_producer",
                     {"AIGC.ContentProducer": "A", "ContentProducer": "B"})
    assert got.matched_key == "AIGC.ContentProducer"
    assert got.alternatives == ("ContentProducer",)


def test_alternatives_are_recorded_not_discarded():
    got = resolution("content_id", {"AIGC:ProduceID": "X", "ProduceID": "X"})
    assert got.all_matched_keys == ("AIGC:ProduceID", "ProduceID")


def _assert_aliases_resolve(national_field):
    mapping = [item for item in FIELDS if item.national_field == national_field][0]
    for alias in mapping.aliases:
        got = resolution(national_field, {alias: "V"})
        assert got.found is True, alias
        assert got.matched_key == alias, alias
        assert got.value == "V", alias


def test_field_content_property_aliases_resolve():
    _assert_aliases_resolve("content_property")


def test_field_content_producer_aliases_resolve():
    _assert_aliases_resolve("content_producer")


def test_field_content_id_aliases_resolve():
    _assert_aliases_resolve("content_id")


def test_field_content_propagator_aliases_resolve():
    _assert_aliases_resolve("content_propagator")


def test_field_propagate_id_aliases_resolve():
    _assert_aliases_resolve("propagate_id")


def test_missing_field_is_not_found():
    got = resolution("content_property", {})
    assert got.found is False
    assert got.value is None


# ---- 4.10 账本映射：verdict / 锚点 / 登记行 ----
def test_pass_maps_to_pass_with_anchor():
    finding = find(gb("text", KIND["presence"]), notice_card("text"))
    assert finding.verdict == PASS
    assert finding.anchor.clause_id == "gb45438:5.1:a"


def test_fail_maps_to_fail_with_anchor():
    finding = find(gb("text", KIND["presence"]), notice_card("text", present=False))
    assert finding.verdict == FAIL
    assert finding.anchor.clause_id == "gb45438:5.1:a"
    assert finding.evidence["code"] == "element_not_present"


def test_unknown_maps_to_not_applicable_with_code_prefix():
    finding = find(gb("text", KIND["position"]), notice_card("text", position=None))
    assert finding.verdict == NOT_APPLICABLE
    assert finding.message.startswith("未判定（position_unknown）")


def test_skipped_maps_to_not_applicable_with_scenario_prefix():
    finding = find(R_EXPORT_LABEL, card("text", "authored"))
    assert finding.verdict == NOT_APPLICABLE
    assert finding.message.startswith("未判定（scenario_not_applicable）")


def test_pending_line_has_no_anchor():
    assert find(PENDING_RULE_ID, card("text")).anchor is None


def test_evidence_carries_scope_target_code_severity_scenario():
    evidence = find(gb("text", KIND["presence"]), notice_card("text")).evidence
    assert evidence["scope"] == "explicit"
    assert evidence["target"] == "text_explicit_notice"
    assert evidence["code"] == ""
    assert evidence["severity"] == "major"
    assert evidence["scenario"] == "authored"


def test_every_fail_carries_full_basis_ref():
    subject = card("text", explicit=[], implicit={})
    fails = [finding for finding in findings_of(subject) if finding.verdict == FAIL]
    assert fails
    for finding in fails:
        payload = finding.as_dict()["basis_ref"]
        assert payload["clause_id"]
        assert payload["path"]
        assert payload["version"]


def test_record_ids_are_unique():
    ids = [finding.id for finding in findings_of(card("text"))]
    assert len(ids) == len(set(ids))


def test_anchor_version_equals_basis_version():
    for finding in findings_of(card("text")):
        if finding.anchor is not None:
            assert finding.anchor.version == rulebook.BASIS_VERSION


def test_report_header_and_summary_shape():
    summary = report_of(card("text")).summary()
    assert summary["total"] == 16
    assert sum(summary["verdicts"].values()) == summary["total"]
    assert summary["blocking"] == summary["verdicts"]["fail"]


# ---- 4.11 唯一入口（CLI）：退出码 0/1/2/3 ----
def _write(tmp_path, name, payload):
    target = tmp_path / name
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(target)


def test_cli_list_shows_the_organ(capsys):
    assert cp_cli.main(["list"]) == EXIT_OK
    assert SLUG in capsys.readouterr().out


def test_cli_check_basic_text_exits_zero(capsys):
    assert cp_cli.main(["check", SLUG, "--input",
                        os.path.join(SAMPLES, "card-text-basic.json"),
                        "--basis", basis_path()]) == EXIT_OK


def test_cli_check_stripped_image_exits_one(capsys):
    assert cp_cli.main(["check", SLUG, "--input",
                        os.path.join(SAMPLES, "card-image-metadata-stripped.json"),
                        "--basis", basis_path()]) == EXIT_BLOCKED


def test_cli_check_without_basis_is_contract_violation(capsys):
    assert cp_cli.main(["check", SLUG, "--input",
                        os.path.join(SAMPLES, "card-text-basic.json")]) == EXIT_CONTRACT


def test_cli_check_bad_card_exits_two(capsys, tmp_path):
    target = _write(tmp_path, "bad.json",
                    {"card_id": "X", "carrier": "pdf", "content_sha256": SHA256})
    assert cp_cli.main(["check", SLUG, "--input", target,
                        "--basis", basis_path()]) == EXIT_INPUT


def test_cli_check_missing_file_exits_two(capsys, tmp_path):
    assert cp_cli.main(["check", SLUG, "--input", str(tmp_path / "nope.json"),
                        "--basis", basis_path()]) == EXIT_INPUT


def test_cli_check_unknown_organ_exits_three(capsys):
    assert cp_cli.main(["check", "no-such-organ", "--input",
                        os.path.join(SAMPLES, "card-text-basic.json"),
                        "--basis", basis_path()]) == EXIT_CONTRACT


def test_cli_json_payload_shape(capsys):
    cp_cli.main(["check", SLUG, "--input",
                 os.path.join(SAMPLES, "card-image-metadata-stripped.json"),
                 "--basis", basis_path(), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG
    assert payload["summary"]["blocking"] == 3
    anchored = [record for record in payload["records"]
                if record["rule_id"] != PENDING_RULE_ID]
    assert all(record["basis_ref"]["clause_id"] for record in anchored)


# ---- 4.12 样例件与确定性 ----
def test_sample_cards_are_shipped():
    assert sorted(os.listdir(SAMPLES)) == ["card-image-metadata-stripped.json",
                                           "card-text-basic.json"]


def test_sample_text_card_is_all_green():
    with open(os.path.join(SAMPLES, "card-text-basic.json"), "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    summary = report_of(payload).summary()
    assert summary["verdicts"]["fail"] == 0
    assert summary["blocking"] == 0


def test_sample_image_card_blocks_on_three_implicit_fields():
    with open(os.path.join(SAMPLES, "card-image-metadata-stripped.json"),
              "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    fails = {finding.rule_id for finding in findings_of(payload)
             if finding.verdict == FAIL}
    assert fails == {R_PROPERTY_PRESENCE, R_PRODUCER_PRESENCE, R_CONTENT_ID_PRESENCE}


def test_output_is_deterministic():
    first = json.dumps(report_of(card("text")).as_dict(), ensure_ascii=False)
    second = json.dumps(report_of(card("text")).as_dict(), ensure_ascii=False)
    assert first == second
    assert ROOT not in first


def test_cli_json_is_byte_identical_across_two_runs(capsys):
    path = os.path.join(SAMPLES, "card-text-basic.json")
    cp_cli.main(["check", SLUG, "--input", path, "--basis", basis_path(), "--json"])
    first = capsys.readouterr().out
    cp_cli.main(["check", SLUG, "--input", path, "--basis", basis_path(), "--json"])
    assert capsys.readouterr().out == first


# ---- 4.13 条文库契约（退出码 3）----
def basis_without(clause_id):
    payload = {"version": rulebook.BASIS_VERSION, "clauses": []}
    basis = shipped_basis()
    for cid in basis.clause_ids():
        if cid == clause_id:
            continue
        clause = basis.clause(cid)
        payload["clauses"].append({"clause_id": cid, "path": clause.path,
                                   "version": clause.version, "text": clause.text})
    return Basis.from_dict(payload)


def test_basis_version_mismatch_is_contract_error():
    with pytest.raises(ContractError):
        pack_mod.evaluate(card("text"), Basis(version="1999-01-01", clauses=()))


def test_missing_clause_propagates_basis_missing():
    with pytest.raises(BasisMissing):
        pack_mod.evaluate(notice_card("text"),
                          basis_without("gb45438:5.1:a"))


def test_every_effective_rule_requires_its_clause():
    for rule in RULES:
        if not rule.is_effective:
            continue
        carrier = rule.carrier[0] if rule.carrier else "text"
        scenario = rule.scenarios[0] if rule.scenarios else "authored"
        with pytest.raises(BasisMissing):
            pack_mod.evaluate(card(carrier, scenario),
                              basis_without(rule.clause_id))


# ---- 4.14 规则对象与 check_type 机制 ----
def test_rule_rejects_unknown_scope():
    with pytest.raises(ValueError):
        probe_rule(scope="body")


def test_rule_rejects_unknown_check_type():
    with pytest.raises(ValueError):
        probe_rule(check_type="existence")


def test_rule_rejects_unknown_severity():
    with pytest.raises(ValueError):
        probe_rule(severity="blocker")


def test_rule_rejects_unknown_scenario():
    with pytest.raises(ValueError):
        probe_rule(scenarios=("broadcast",))


def test_unique_rule_is_implicit_only():
    with pytest.raises(ValueError):
        probe_rule(check_type="unique", scope="explicit")
    engine.Rule("PROBE-U", "implicit", (), "content_property", "unique", {},
                "major", (), "gb45438:6.1:c", "verified")


def test_evaluate_check_rejects_unique():
    with pytest.raises(ValueError):
        engine.evaluate_check(probe_rule(check_type="unique", scope="implicit"), "x")


def test_range_check_passes_within_bounds():
    rule = probe_rule(check_type="range", params={"min": 1, "max": 5})
    assert engine.evaluate_check(rule, 2.0)[0] == engine.STATUS_PASS


def test_range_check_fails_out_of_bounds():
    rule = probe_rule(check_type="range", params={"min": 1, "max": 5})
    status, code, _message, _evidence = engine.evaluate_check(rule, 9.0)
    assert status == engine.STATUS_FAIL
    assert code == "value_out_of_range"


def test_range_check_rejects_non_numeric():
    rule = probe_rule(check_type="range", params={"min": 1, "max": 5})
    status, code, _message, _evidence = engine.evaluate_check(rule, "abc")
    assert status == engine.STATUS_FAIL
    assert code == "type_mismatch"


def test_type_check_int_rejects_bool():
    """bool 是 int 的子类，但契约里它不是数值（来源产品的同一纪律）。"""
    rule = probe_rule(check_type="type", params={"expect": "int"})
    status, code, _message, _evidence = engine.evaluate_check(rule, True)
    assert status == engine.STATUS_FAIL
    assert code == "type_mismatch"


# ---- 4.15 规则筛选与字段归一 ----
def test_rules_for_splits_applicable_and_skipped():
    applicable, skipped = engine.rules_for(RULES, "explicit", "text", "authored")
    assert len(applicable) == 4
    assert {rule.rule_id for rule in skipped} == {R_EXPORT_LABEL, R_PLATFORM_HINT}


def test_rules_for_excludes_pending():
    applicable, skipped = engine.rules_for(RULES, "explicit", "text", "authored")
    assert {rule.rule_id for rule in applicable + skipped}.isdisjoint(set(PENDING))


def test_rules_for_excludes_other_carriers():
    applicable, skipped = engine.rules_for(RULES, "explicit", "text", "authored")
    for rule in applicable + skipped:
        assert not rule.carrier or "text" in rule.carrier


def test_resolve_fields_keeps_declaration_order():
    assert list(engine.resolve_fields({}, FIELDS)) == [
        mapping.national_field for mapping in FIELDS]


def test_resolve_fields_returns_not_found_for_empty():
    resolved = engine.resolve_fields({}, FIELDS)
    assert all(item.found is False for item in resolved.values())
    assert all(item.all_matched_keys == () for item in resolved.values())


# ---- 4.16 严重度只进 evidence、fail 一律阻断 ----
def test_minor_fail_still_blocks():
    subject = notice_card("image", position="head")
    assert report_of(subject).summary()["blocking"] == 1


def test_minor_fail_records_severity_in_evidence():
    finding = find(gb("image", KIND["position"]), notice_card("image", position="head"))
    assert finding.verdict == FAIL
    assert finding.evidence["severity"] == "minor"


def test_critical_major_minor_failures_all_block():
    subject = card("text", explicit=[], implicit={})
    fails = [finding for finding in findings_of(subject) if finding.verdict == FAIL]
    severities = {finding.evidence["severity"] for finding in fails}
    assert {"critical", "major", "minor"} <= severities
    assert report_of(subject).summary()["blocking"] == len(fails)


# ---- 4.17 覆盖完整性 ----
def test_every_effective_rule_is_reachable_via_evaluate():
    for rule in RULES:
        if not rule.is_effective:
            continue
        carrier = rule.carrier[0] if rule.carrier else "text"
        scenario = rule.scenarios[0] if rule.scenarios else "authored"
        ids = {finding.rule_id for finding in findings_of(card(carrier, scenario))}
        assert rule.rule_id in ids, rule.rule_id


def test_all_34_rules_are_accounted_for():
    effective = [rule for rule in RULES if rule.is_effective]
    pending = [rule for rule in RULES if not rule.is_effective]
    assert len(effective) + len(pending) == 34
    assert {rule.rule_id for rule in pending} == set(PENDING)