"""覆盖度核查（迁自来源 ``engine.coverage``）：应检 vs 实检 → 四态 + 缺项挂依据。

定级边界：
    应检项全齐 + 周期合规                  → compliant
    缺 1 项以上必检项 / 周期超期            → partial
    必检项一项未做（expected ⊆ missing）   → non_compliant
    岗位危害因素不适用该人员                → not_applicable（不计违规）
    危害因素不识别 / 缺必填字段             → 不产出 verdict，记 failed + 原因码
    别名归一不成立                          → 该单项降级 warning，不硬判缺失
"""

from ..model import (NONCOMPLIANT_VERDICTS, VERDICT_COMPLIANT,
                     VERDICT_NON_COMPLIANT, VERDICT_NOT_APPLICABLE,
                     VERDICT_PARTIAL, VERDICT_UNKNOWN, CoverageResult)
from .matrix import STATE_INPUT_REQUIRED, STATE_NOT_APPLICABLE
from .period import (PERIOD_NOT_APPLICABLE, PERIOD_PENDING_INPUT,
                     is_period_noncompliant, judge_period)


def normalize_items(items, known_codes=None, alias_map=None):
    """实检项目归一：精确命中 → 显式别名 → unmapped（不猜）。"""
    alias_map = alias_map or {}
    known = set(known_codes or ())
    normalized = set()
    unmapped = []
    for raw in items:
        text = str(raw).strip()
        if text in known:
            normalized.add(text)
            continue
        if text in alias_map:
            normalized.add(str(alias_map[text]))
            continue
        unmapped.append(text)
    return normalized, unmapped


def _classify(expected_set, missing_set, period_verdict):
    period_bad = is_period_noncompliant(period_verdict)
    if not expected_set:
        return VERDICT_PARTIAL if period_bad else VERDICT_COMPLIANT
    if not missing_set:
        return VERDICT_PARTIAL if period_bad else VERDICT_COMPLIANT
    if expected_set.issubset(missing_set):
        return VERDICT_NON_COMPLIANT
    return VERDICT_PARTIAL


def check_record(record, plan_result, alias_map=None, last_exam_date=None):
    factor_plan = None
    for item in plan_result.factors:
        if item.factor_code == record.factor_code:
            factor_plan = item
            break
    if factor_plan is None:
        return CoverageResult(
            record_id=record.record_id, employee_id=record.employee_id,
            position_id=record.position_id, factor_code=record.factor_code,
            exam_type=record.exam_type, verdict=VERDICT_UNKNOWN,
            failed_reason="unknown_factor",
            failed_message="规则集中不存在危害因素 %r" % record.factor_code)
    if factor_plan.applicability.state == STATE_NOT_APPLICABLE:
        return CoverageResult(
            record_id=record.record_id, employee_id=record.employee_id,
            position_id=record.position_id, factor_code=record.factor_code,
            exam_type=record.exam_type, verdict=VERDICT_NOT_APPLICABLE,
            period_verdict=PERIOD_NOT_APPLICABLE,
            findings=[{"kind": "not_applicable",
                       "message": factor_plan.applicability.reason,
                       "basis": factor_plan.applicability.basis}],
            trace=[{"target": "%s/%s/applicability"
                             % (record.record_id, record.factor_code),
                    "value": "not_applicable",
                    "basis": factor_plan.applicability.basis}])
    if factor_plan.applicability.state == STATE_INPUT_REQUIRED:
        return CoverageResult(
            record_id=record.record_id, employee_id=record.employee_id,
            position_id=record.position_id, factor_code=record.factor_code,
            exam_type=record.exam_type, verdict=VERDICT_UNKNOWN,
            period_verdict=PERIOD_PENDING_INPUT,
            findings=[{"kind": "input_required",
                       "message": factor_plan.applicability.reason,
                       "basis": factor_plan.applicability.basis}],
            failed_reason="missing_input",
            failed_message=factor_plan.applicability.reason)
    exam = factor_plan.exams.get(record.exam_type)
    if exam is None:
        return CoverageResult(
            record_id=record.record_id, employee_id=record.employee_id,
            position_id=record.position_id, factor_code=record.factor_code,
            exam_type=record.exam_type, verdict=VERDICT_UNKNOWN,
            failed_reason="unknown_exam_type",
            failed_message="该因素的应检清单未包含时点 %r" % record.exam_type)
    expected = set(exam.required_items)
    actual, unmapped = normalize_items(record.items, known_codes=expected,
                                       alias_map=alias_map)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    period_verdict = None
    period_info = None
    if record.exam_type == "periodic":
        period_info = judge_period(factor_plan.period, last_exam_date, record.exam_date)
        period_verdict = period_info["verdict"]
    else:
        period_verdict = "not_applicable"
    verdict = _classify(expected, set(missing), period_verdict)
    findings = []
    trace = [{"target": "%s/%s/%s" % (record.record_id, record.factor_code,
                                       record.exam_type),
              "value": verdict, "basis": exam.basis}]
    for code in missing:
        item_basis = exam.item_basis(code)
        finding = {"kind": "missing_item", "message": "缺必检项目 %s" % code,
                   "item_code": code, "basis": item_basis}
        source = exam.item_source(code)
        if source:
            finding["source"] = source
        findings.append(finding)
        row = {"target": "%s/%s/%s/%s" % (record.record_id, record.factor_code,
                                          record.exam_type, code),
               "value": "missing", "basis": item_basis}
        if source:
            row["source"] = source
        trace.append(row)
    for text in unmapped:
        findings.append({"kind": "warning",
                         "message": "实检项目 %r 无法归一到规范项目代码（不判缺失，请人工确认）"
                                    % text,
                         "basis": exam.basis, "item_code": text})
    if period_info and is_period_noncompliant(period_verdict):
        findings.append({"kind": "period_overdue",
                         "message": period_info.get("note") or "检查周期超期",
                         "basis": factor_plan.basis})
    return CoverageResult(
        record_id=record.record_id, employee_id=record.employee_id,
        position_id=record.position_id, factor_code=record.factor_code,
        exam_type=record.exam_type, verdict=verdict, missing_items=missing,
        extra_items=extra, unmapped_items=unmapped, period_verdict=period_verdict,
        findings=findings, trace=trace)


def is_noncompliant(coverage_result):
    return coverage_result.verdict in NONCOMPLIANT_VERDICTS


def verdict_reachability(ruleset):
    kinds = set()
    for factor in ruleset.factors:
        kinds.add((factor.get("eligibility") or {}).get("kind"))
    threshold = "threshold" in kinds
    input_req = "input_required" in kinds
    rows = [
        {"state": "not_applicable", "reachable": threshold,
         "reason": ("规则包含接触水平阈值型适用性（kind=threshold）" if threshold
                    else "标准对所列危害因素「接触即纳入」，全为 kind=always；"
                         "逐因素不设接触水平阈值 → 本规则包不可达")},
        {"state": "unknown", "reachable": input_req,
         "reason": ("存在适用性待输入（kind=input_required）" if input_req
                    else "无适用性待输入条目")},
        {"state": "compliant", "reachable": True, "reason": "必检项齐备且周期合规时可达"},
        {"state": "partial", "reachable": True, "reason": "存在缺项或周期超期时可达"},
        {"state": "non_compliant", "reachable": True, "reason": "必检项一项未做时可达"},
    ]
    return sorted(rows, key=lambda r: r["state"])


__all__ = ["normalize_items", "check_record", "is_noncompliant",
           "verdict_reachability"]