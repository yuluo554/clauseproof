"""编排层（迁自来源 ``engine.pipeline``）：CLI 与器官入口共用的唯一编排事实源。

IO（规则加载/门控）集中在此；判定层保持纯函数。
"""

from .errors import MissingInputError
from .model import FactorRef, HealthRecord, PositionProfile
from .rules import load_manifest, load_ruleset
from .rules.gate import effective_ruleset
from .rules.version import resolve_ruleset_id


class Context:
    __slots__ = ("data_dir", "manifest", "_rulesets")

    def __init__(self, data_dir=None):
        self.data_dir = data_dir
        self.manifest = load_manifest(data_dir)
        self._rulesets = {}

    def ruleset(self, ruleset_id):
        if ruleset_id not in self._rulesets:
            self._rulesets[ruleset_id] = load_ruleset(
                ruleset_id, self.data_dir, self.manifest)
        return self._rulesets[ruleset_id]

    def all_rulesets(self):
        return {rid: self.ruleset(rid) for rid in self.manifest.ruleset_ids()}


def build_context(data_dir=None):
    return Context(data_dir)


def build_position(obj):
    return PositionProfile.from_dict(obj)


def build_record(obj):
    if isinstance(obj, dict) and "record_id" not in obj and isinstance(obj.get("record"), dict):
        obj = obj["record"]
    return HealthRecord.from_dict(obj)


def resolve_ruleset_for(exam_date, context):
    ruleset_id = resolve_ruleset_id(exam_date, context.manifest)
    return context.ruleset(ruleset_id)


def _blocking_inputs(items):
    return [it for it in items if it.get("blocking", True)]


def compute_plan(profile, context, scope="plan"):
    from .engine.matrix import compute_plan as _compute

    ruleset = resolve_ruleset_for(profile.exam_date, context)
    eff = effective_ruleset(ruleset, scope, required_factor_ids=profile.factor_codes)
    blocking = _blocking_inputs(eff.missing_inputs)
    if blocking:
        raise MissingInputError(blocking)
    result = _compute(profile, eff)
    result_blocking = _blocking_inputs(result.missing_inputs)
    if result_blocking:
        raise MissingInputError(result_blocking)
    return result


def _plan_for_record(record, context, scope="check"):
    from .engine.matrix import compute_plan as _compute

    ruleset = resolve_ruleset_for(record.exam_date, context)
    eff = effective_ruleset(ruleset, scope, required_factor_ids=[record.factor_code])
    blocking = _blocking_inputs(eff.missing_inputs)
    if blocking:
        raise MissingInputError(blocking)
    profile = PositionProfile(
        position_id=record.position_id or record.record_id,
        exam_date=record.exam_date,
        factors=[FactorRef(record.factor_code)],
    )
    plan_result = _compute(profile, eff)
    plan_blocking = _blocking_inputs(plan_result.missing_inputs)
    if plan_blocking:
        raise MissingInputError(plan_blocking)
    return plan_result, record.last_exam_date


def compute_coverage(record, context):
    from .engine.coverage import check_record

    plan_result, last_exam_date = _plan_for_record(record, context)
    alias_map = _alias_map(context, plan_result.ruleset_id)
    return check_record(record, plan_result, alias_map=alias_map,
                        last_exam_date=last_exam_date)


def _alias_map(context, ruleset_id):
    ids = [ruleset_id] if ruleset_id else context.manifest.ruleset_ids()
    merged = {}
    any_verified = False
    for rid in ids:
        ruleset = context.ruleset(rid)
        block = ruleset.obj.get("alias_map")
        if not isinstance(block, dict):
            continue
        if block.get("status") != "verified":
            continue
        any_verified = True
        for alias, code in (block.get("map") or {}).items():
            merged[alias] = code
    return merged if any_verified else None


def compare(ruleset_id_a, ruleset_id_b, context):
    from .engine.compare import compare_rulesets

    eff_a = effective_ruleset(context.ruleset(ruleset_id_a), "compare")
    eff_b = effective_ruleset(context.ruleset(ruleset_id_b), "compare")
    return compare_rulesets(eff_a, eff_b)


__all__ = ["Context", "build_context", "build_position", "build_record",
           "resolve_ruleset_for", "compute_plan", "compute_coverage", "compare"]