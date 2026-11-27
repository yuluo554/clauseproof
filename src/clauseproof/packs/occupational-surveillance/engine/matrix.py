"""监护矩阵推导（迁自来源 ``engine.matrix``）。

应检项集口径：expected = required_items（**只算必检项**），supplementary/optional
不进判定（缺失不报）。本工具不做「该做补充检查没做」的判定。
"""

from ..model import (EXAM_TYPES, ExamPlan, FactorPlan, PlanResult, Applicability,
                     parse_decimal)

STATE_APPLICABLE = "applicable"
STATE_NOT_APPLICABLE = "not_applicable"
STATE_INPUT_REQUIRED = "input_required"

_COMPARATORS = {
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


def _basis_text(basis, factor):
    doc = (basis or {}).get("doc_code") or factor.get("basis") or ""
    clause = factor.get("factor_id") or ""
    if doc and clause:
        return "%s 第 %s 节" % (doc, clause)
    return clause or doc


def _judge_applicability(factor, factor_ref):
    elig = factor["eligibility"]
    kind = elig.get("kind")
    basis = _basis_text(None, factor)
    if kind == "pending":
        return Applicability(STATE_INPUT_REQUIRED, "适用性条目尚未核对", basis)
    if kind == "input_required":
        return Applicability(STATE_INPUT_REQUIRED,
                             elig.get("basis") or "适用性需按具体情况确定", basis)
    if kind == "always":
        return Applicability(STATE_APPLICABLE, "该危害因素一律纳入监护", basis)
    if kind == "threshold":
        comparator = _COMPARATORS.get(elig.get("comparator"))
        if comparator is None:
            raise ValueError("未知比较符 %r" % (elig.get("comparator"),))
        threshold = elig.get("threshold")
        if threshold is None:
            return Applicability(STATE_INPUT_REQUIRED, "适用性阈值尚未核对", basis)
        if factor_ref.exposure_value is None:
            return Applicability(
                STATE_INPUT_REQUIRED,
                "需提供接触浓度/强度（%s %s）方可判定适用性"
                % (elig.get("comparator"), elig.get("unit")), basis)
        threshold_value = parse_decimal(threshold, "eligibility.threshold")
        exposure_value = parse_decimal(factor_ref.exposure_value, "exposure_value")
        ok = comparator(exposure_value, threshold_value)
        return Applicability(
            STATE_APPLICABLE if ok else STATE_NOT_APPLICABLE,
            "接触水平 %s %s %s 阈值 %s"
            % (factor_ref.exposure_value, elig.get("unit"), elig.get("comparator"),
               threshold), basis)
    raise ValueError("未知适用性类型 %r" % (kind,))


def _required_item_codes(block):
    out = []
    for item in block.get("required_items") or []:
        code = item.get("item_code")
        if code:
            out.append(code)
    return out


def _item_maps(block):
    bases = {}
    sources = {}
    for item in block.get("required_items") or []:
        code = item.get("item_code")
        if not code:
            continue
        if item.get("basis"):
            bases[code] = item["basis"]
        if isinstance(item.get("source"), dict):
            sources[code] = dict(item["source"])
    return bases, sources


def _build_exams(factor, basis_text):
    exams = {}
    for key in EXAM_TYPES:
        block = factor["examinations"][key]
        item_bases, item_sources = _item_maps(block)
        exams[key] = ExamPlan(
            exam_type=key,
            required_items=_required_item_codes(block),
            supplementary_items=[i.get("item_code")
                                 for i in block.get("supplementary_items") or []],
            optional_items=[i.get("item_code")
                            for i in block.get("optional_items") or []],
            basis=basis_text,
            item_bases=item_bases,
            item_sources=item_sources,
        )
    return exams


def plan_for_factor(factor, factor_ref, ruleset_id):
    basis_text = _basis_text(factor.get("basis"), factor)
    applicability = _judge_applicability(factor, factor_ref)
    exams = {}
    if applicability.state == STATE_APPLICABLE:
        exams = _build_exams(factor, basis_text)
    return FactorPlan(
        factor_code=factor["factor_code"],
        factor_name=factor["factor_name"],
        applicability=applicability,
        exams=exams,
        period=dict(factor["period"]),
        basis=basis_text,
    )


def _trace_rows(position_id, plan_result_factors):
    rows = []
    for factor_plan in plan_result_factors:
        if factor_plan.applicability.state != STATE_APPLICABLE:
            rows.append({
                "target": "%s/%s/applicability" % (position_id, factor_plan.factor_code),
                "value": factor_plan.applicability.state,
                "basis": factor_plan.applicability.basis,
            })
            continue
        rows.append({
            "target": "%s/%s/period" % (position_id, factor_plan.factor_code),
            "value": factor_plan.period.get("kind", ""),
            "basis": factor_plan.basis,
        })
        for exam_type in EXAM_TYPES:
            exam = factor_plan.exams.get(exam_type)
            if exam is None:
                continue
            for code in exam.required_items:
                row = {
                    "target": "%s/%s/%s/%s"
                    % (position_id, factor_plan.factor_code, exam_type, code),
                    "value": "required",
                    "basis": exam.item_basis(code),
                }
                source = exam.item_source(code)
                if source:
                    row["source"] = source
                rows.append(row)
    return rows


def _period_input_note(factor, factor_ref):
    period = factor.get("period") or {}
    if period.get("status") != "input_required":
        return None
    return {
        "target": "%s/%s/period" % (factor_ref.factor_code, "周期"),
        "basis": period.get("basis") or period.get("note") or "周期需按具体情况确定",
        "factor_code": factor["factor_code"],
        "blocking": False,
    }


def compute_plan(profile, eff_ruleset):
    ruleset = eff_ruleset.ruleset
    factors = []
    missing_inputs = []
    for ref in profile.factors:
        factor = ruleset.factor(ref.factor_code)
        if factor is None:
            raise ValueError("规则集中不存在危害因素 %r" % ref.factor_code)
        fp = plan_for_factor(factor, ref, ruleset.ruleset_id)
        factors.append(fp)
        if fp.applicability.state == STATE_INPUT_REQUIRED:
            missing_inputs.append({
                "target": "%s/%s/applicability" % (profile.position_id, ref.factor_code),
                "basis": fp.applicability.reason,
                "factor_code": ref.factor_code,
                "blocking": True,
            })
        period_note = _period_input_note(factor, ref)
        if period_note is not None:
            missing_inputs.append(period_note)
    notes = []
    blocking = [m for m in missing_inputs if m.get("blocking", True)]
    if blocking:
        notes.append("有 %d 项适用性待外部输入，未满足前不产出该因素的应检清单"
                     % len(blocking))
    deferred = [m for m in missing_inputs if not m.get("blocking", True)]
    if deferred:
        notes.append("有 %d 项周期按具体情况分档、需外部输入（作业分级/接触水平等）；"
                     "应检清单不受影响，周期判定将呈现为「待输入」（决策 D-13）"
                     % len(deferred))
    return PlanResult(
        ruleset_id=ruleset.ruleset_id,
        position_id=profile.position_id,
        factors=factors,
        missing_inputs=missing_inputs,
        trace=_trace_rows(profile.position_id, factors),
        notes=notes,
    )


def expected_items(plan_result, factor_code, exam_type):
    for factor_plan in plan_result.factors:
        if factor_plan.factor_code != factor_code:
            continue
        exam = factor_plan.exams.get(exam_type)
        if exam is None:
            return []
        return list(exam.required_items)
    return []


def applicability_of(plan_result, factor_code):
    for factor_plan in plan_result.factors:
        if factor_plan.factor_code == factor_code:
            return factor_plan.applicability
    return None


def period_rule_of(plan_result, factor_code):
    for factor_plan in plan_result.factors:
        if factor_plan.factor_code == factor_code:
            return factor_plan.period
    return None


__all__ = ["STATE_APPLICABLE", "STATE_NOT_APPLICABLE", "STATE_INPUT_REQUIRED",
           "plan_for_factor", "compute_plan", "expected_items", "applicability_of",
           "period_rule_of"]