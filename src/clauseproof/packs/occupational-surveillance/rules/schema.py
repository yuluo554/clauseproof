"""规则包 schema 校验（迁自来源 ``rules.schema``）。

不变式：
    status == verified      ⇒ source.doc / source.clause 非空，承载值非 null
    status == pending       ⇒ 承载值为 null（不许「半核对」悬空值）
    status == input_required⇒ basis 非空（说明为何不由规则包承载）
违反即 ``InputError``（退出码 2），绝不宽容放行。
"""

import re

from ..errors import InputError

STATUSES = ("verified", "pending", "input_required")
PACKAGE_STATUSES = ("partial", "scaffold")
FACTOR_CATEGORIES = ("chemical", "physical", "dust", "biological", "special")
EXAM_TYPE_KEYS = ("pre_placement", "periodic", "post_placement", "emergency")
ELIGIBILITY_KINDS = ("always", "threshold", "input_required", "pending")
PERIOD_KINDS = ("months", "none", "input_required", "pending")
OPTIONAL_ITEMS_POLICIES = ("any", "emergency_only")

SCHEMA_VERSION = "1.0"
SYNTHETIC_MARKER = "SYNTHETIC-"

_CLAUSE_RE = re.compile(r"^[0-9]+(\.[0-9]+)*$")


def _fail(msg):
    raise InputError("规则包 schema 校验失败：%s" % msg)


def _require_synthetic_provenance(src, where):
    doc = str(src.get("doc") or "")
    if not doc.startswith(SYNTHETIC_MARKER):
        _fail("%s 属合成夹具，source.doc 必须以 %r 开头（实际 %r）——"
              "合成数据不得冒充真实标准出处" % (where, SYNTHETIC_MARKER, doc))


def _check_source(src, where):
    if not isinstance(src, dict):
        _fail("%s.source 必须是对象" % where)
    for key in ("doc", "clause", "url", "fetched"):
        if key not in src:
            _fail("%s.source 缺少字段 %r" % (where, key))


def _check_status_block(block, where, value_field=None, synthetic=False,
                        value_required=None):
    if not isinstance(block, dict):
        _fail("%s 必须是对象" % where)
    status = block.get("status")
    if status not in STATUSES:
        _fail("%s.status %r 非法（合法值：%s）" % (where, status, ", ".join(STATUSES)))
    if value_required is None:
        value_required = value_field is not None
    if status == "verified":
        src = block.get("source")
        _check_source(src, where)
        if synthetic:
            _require_synthetic_provenance(src, where)
        if not str(src.get("doc") or "").strip():
            _fail("%s 已标 verified 但 source.doc 为空——未挂原文核对不得标 verified" % where)
        if not str(src.get("clause") or "").strip():
            _fail("%s 已标 verified 但 source.clause 为空" % where)
        if value_required and block.get(value_field) is None:
            _fail("%s 已标 verified 但 %s 为 null（不许半核对的悬空值）"
                  % (where, value_field))
    elif status == "pending":
        if value_required and block.get(value_field) is not None:
            _fail("%s 标 pending 却已填 %s——pending 一律为 null，防止"
                  "「先填大概值再标待核对」" % (where, value_field))
    elif status == "input_required":
        if not str(block.get("basis") or "").strip():
            _fail("%s 标 input_required 但 basis 为空——须说明为何本不由规则包承载" % where)
    return status


def _validate_item(item, where, synthetic=False):
    if not isinstance(item, dict):
        _fail("%s 必须是对象" % where)
    for key in ("item_code", "item_name"):
        if key not in item:
            _fail("%s 缺少字段 %r" % (where, key))
    _check_status_block(item, where, value_field=None, synthetic=synthetic)
    if item.get("status") == "verified" and not str(item.get("item_code") or "").strip():
        _fail("%s 已标 verified 但 item_code 为空" % where)


def _validate_exam_block(block, where, key, optional_policy=None, synthetic=False):
    if not isinstance(block, dict):
        _fail("%s 必须是对象" % where)
    for group in ("required_items", "supplementary_items", "optional_items"):
        if not isinstance(block.get(group), list):
            _fail("%s.%s 必须是数组" % (where, group))
        for idx, item in enumerate(block.get(group) or []):
            _validate_item(item, "%s.%s[%d]" % (where, group, idx), synthetic)
    _check_status_block(block, where, value_field=None, synthetic=synthetic)
    if optional_policy == "emergency_only" and key != "emergency":
        if block.get("optional_items"):
            _fail("%s 在本规则集口径（optional_items_policy=emergency_only）下"
                  "不得有选检项目：仅应急检查保留选检项" % where)


def _validate_factor(factor, idx, optional_policy, synthetic=False):
    where = "factors[%d]" % idx
    if not isinstance(factor, dict):
        _fail("%s 必须是对象" % where)
    for key in ("factor_id", "factor_code", "factor_name", "chapter", "category"):
        if not str(factor.get(key) or "").strip():
            _fail("%s 缺少非空字段 %r" % (where, key))
    if factor["category"] not in FACTOR_CATEGORIES:
        _fail("%s.category %r 非法" % (where, factor["category"]))
    if not _CLAUSE_RE.match(str(factor["factor_id"])):
        _fail("%s.factor_id %r 不是合法节号（如 5.1.0）" % (where, factor["factor_id"]))
    elig = factor.get("eligibility")
    if not isinstance(elig, dict):
        _fail("%s.eligibility 必须是对象" % where)
    if elig.get("kind") not in ELIGIBILITY_KINDS:
        _fail("%s.eligibility.kind %r 非法" % (where, elig.get("kind")))
    elig_kind = elig.get("kind")
    if elig_kind == "threshold":
        if not str(elig.get("comparator") or "").strip():
            _fail("%s.eligibility 为 threshold 但 comparator 为空" % where)
        if not str(elig.get("unit") or "").strip():
            _fail("%s.eligibility 为 threshold 但 unit 为空" % where)
    _check_status_block(elig, "%s.eligibility" % where, value_field="threshold",
                        synthetic=synthetic,
                        value_required=(elig_kind == "threshold"))
    for di, disease in enumerate(factor.get("target_diseases") or []):
        _check_status_block(disease, "%s.target_diseases[%d]" % (where, di),
                            value_field="name", synthetic=synthetic)
    exams = factor.get("examinations")
    if not isinstance(exams, dict):
        _fail("%s.examinations 必须是对象" % where)
    for key in EXAM_TYPE_KEYS:
        if key not in exams:
            _fail("%s.examinations 缺少时点 %r" % (where, key))
        _validate_exam_block(exams[key], "%s.examinations.%s" % (where, key), key,
                             optional_policy, synthetic)
    period = factor.get("period")
    if not isinstance(period, dict):
        _fail("%s.period 必须是对象" % where)
    period_kind = period.get("kind")
    if period_kind not in PERIOD_KINDS:
        _fail("%s.period.kind %r 非法" % (where, period_kind))
    if period_kind == "months":
        value = period.get("value")
        if not isinstance(value, int) or value <= 0:
            _fail("%s.period.value 必须是正整数月数" % where)
    _check_status_block(period, "%s.period" % where, value_field="value",
                        synthetic=synthetic, value_required=(period_kind == "months"))
    _check_status_block(factor, where, value_field=None, synthetic=synthetic)


def validate_ruleset(obj):
    if not isinstance(obj, dict):
        _fail("规则集根必须是对象")
    if obj.get("schema_version") != SCHEMA_VERSION:
        _fail("schema_version 必须是 %r，实际 %r"
              % (SCHEMA_VERSION, obj.get("schema_version")))
    synthetic = bool(obj.get("synthetic"))
    if not str(obj.get("ruleset_id") or "").strip():
        _fail("缺少 ruleset_id")
    if "status" in obj and obj["status"] not in PACKAGE_STATUSES:
        _fail("顶层 status %r 非法（整包完成度标签，合法值：%s；注意它不参与门控）"
              % (obj.get("status"), ", ".join(PACKAGE_STATUSES)))
    basis = obj.get("basis")
    if not isinstance(basis, dict):
        _fail("缺少 basis 对象")
    for key in ("doc_code", "doc_title"):
        if not str(basis.get(key) or "").strip():
            _fail("basis 缺少非空字段 %r" % key)
    eff_status = basis.get("effective_from_status", "verified")
    if eff_status not in STATUSES:
        _fail("basis.effective_from_status %r 非法（合法值：%s）"
              % (eff_status, ", ".join(STATUSES)))
    if eff_status == "pending":
        if str(basis.get("effective_from") or "").strip():
            _fail("basis.effective_from_status 标 pending 却已填 effective_from——"
                  "待核对的日期不得预填")
    elif not str(basis.get("effective_from") or "").strip():
        _fail("basis 缺少非空字段 'effective_from'")
    if synthetic:
        if not str(basis.get("doc_code") or "").startswith(SYNTHETIC_MARKER):
            _fail("合成规则集的 basis.doc_code 必须以 %r 开头，实际 %r"
                  % (SYNTHETIC_MARKER, basis.get("doc_code")))
        if not str(basis.get("doc_title") or "").startswith(SYNTHETIC_MARKER):
            _fail("合成规则集的 basis.doc_title 必须以 %r 开头" % SYNTHETIC_MARKER)
        if str(basis.get("issuer") or "").strip():
            _fail("合成规则集不得填写真实发布机关（issuer 必须为空）")
    factors = obj.get("factors")
    if not isinstance(factors, list):
        _fail("factors 必须是数组")
    optional_policy = obj.get("optional_items_policy", "any")
    if optional_policy not in OPTIONAL_ITEMS_POLICIES:
        _fail("optional_items_policy %r 非法（合法值：%s）"
              % (optional_policy, ", ".join(OPTIONAL_ITEMS_POLICIES)))
    seen_ids = set()
    seen_codes = set()
    for idx, factor in enumerate(factors):
        _validate_factor(factor, idx, optional_policy, synthetic)
        fid = factor["factor_id"]
        code = factor["factor_code"]
        if fid in seen_ids:
            _fail("factor_id 重复：%s" % fid)
        if code in seen_codes:
            _fail("factor_code 重复：%s" % code)
        seen_ids.add(fid)
        seen_codes.add(code)
    return obj


def validate_manifest(obj):
    if not isinstance(obj, dict):
        _fail("manifest 根必须是对象")
    if obj.get("schema_version") != SCHEMA_VERSION:
        _fail("manifest.schema_version 必须是 %r" % SCHEMA_VERSION)
    cutover = obj.get("cutover")
    if not isinstance(cutover, dict):
        _fail("manifest 缺少 cutover 对象")
    for key in ("date", "before", "after"):
        if not str(cutover.get(key) or "").strip():
            _fail("manifest.cutover 缺少非空字段 %r" % key)
    if not isinstance(obj.get("rulesets"), list):
        _fail("manifest.rulesets 必须是数组")
    thresholds = obj.get("benchmark_thresholds")
    if not isinstance(thresholds, dict):
        _fail("manifest 缺少 benchmark_thresholds——门槛随 manifest 下发（数据非代码），"
              "不得回落代码默认值")
    return obj


__all__ = ["STATUSES", "PACKAGE_STATUSES", "FACTOR_CATEGORIES", "EXAM_TYPE_KEYS",
           "ELIGIBILITY_KINDS", "PERIOD_KINDS", "OPTIONAL_ITEMS_POLICIES",
           "SCHEMA_VERSION", "SYNTHETIC_MARKER", "validate_ruleset",
           "validate_manifest"]