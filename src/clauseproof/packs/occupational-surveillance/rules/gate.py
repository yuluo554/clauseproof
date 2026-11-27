"""status 门控：按计算路径分作用域（迁自来源 ``rules.gate``）。

门控问的是「这次计算用到的条目核对了吗」，不是「整包核对了吗」。
第三态 input_required **放行门控**，但运行时必须显式索取（missing_inputs）。
"""

from ..errors import GateBlocked, InputError

SCOPES = ("plan", "check", "compare", "bench")
SCOPE_DEPTH = {"plan": "full", "check": "full", "compare": "minimal",
               "bench": "minimal"}


class EffectiveRuleset:
    __slots__ = ("ruleset", "scope", "used_factor_codes", "missing_inputs")

    def __init__(self, ruleset, scope, used_factor_codes, missing_inputs=None):
        self.ruleset = ruleset
        self.scope = scope
        self.used_factor_codes = sorted(used_factor_codes)
        self.missing_inputs = list(missing_inputs or [])

    @property
    def ruleset_id(self):
        return self.ruleset.ruleset_id

    def factor(self, code):
        return self.ruleset.factor(code)

    def has_factor(self, code):
        return self.ruleset.has_factor(code)


def _collect_full(factor):
    pending = []
    required_inputs = []
    code = factor["factor_code"]
    label = "%s(%s)" % (factor["factor_id"], code)

    for name, block in (("", factor), ("eligibility", factor["eligibility"]),
                        ("period", factor["period"])):
        status = block.get("status")
        where = "%s.%s" % (label, name) if name else label
        if status == "pending":
            pending.append(where)
        elif status == "input_required":
            required_inputs.append({
                "target": where,
                "basis": block.get("basis", ""),
                "factor_code": code,
                "blocking": name != "period",
            })

    for di, disease in enumerate(factor.get("target_diseases") or []):
        if disease.get("status") == "pending":
            pending.append("%s.target_diseases[%d]" % (label, di))

    for key in ("pre_placement", "periodic", "post_placement", "emergency"):
        block = factor["examinations"][key]
        if block.get("status") == "pending":
            pending.append("%s.examinations.%s" % (label, key))
        for group in ("required_items", "supplementary_items", "optional_items"):
            for ii, item in enumerate(block.get(group) or []):
                item_where = "%s.examinations.%s.%s[%d]" % (label, key, group, ii)
                if item.get("status") == "pending":
                    pending.append(item_where)
                elif item.get("status") == "input_required":
                    required_inputs.append({
                        "target": item_where,
                        "basis": item.get("basis", ""),
                        "factor_code": code,
                        "blocking": True,
                    })
    return pending, required_inputs


def _collect_minimal(factor):
    pending = []
    required_inputs = []
    code = factor["factor_code"]
    if factor.get("status") == "pending":
        pending.append("%s(%s)" % (factor["factor_id"], code))
    if factor["eligibility"].get("status") == "input_required":
        required_inputs.append({
            "target": "%s(%s).eligibility" % (factor["factor_id"], code),
            "basis": factor["eligibility"].get("basis", ""),
            "factor_code": code,
            "blocking": True,
        })
    return pending, required_inputs


def _resolve_codes(ruleset, required_factor_ids):
    if required_factor_ids is None:
        return ruleset.factor_codes
    codes = sorted(set(required_factor_ids))
    unknown = [c for c in codes if not ruleset.has_factor(c)]
    if unknown:
        raise InputError("规则集 %s 中不存在危害因素：%s"
                         % (ruleset.ruleset_id, ", ".join(unknown)),
                         reason="unknown_factor")
    return codes


def effective_ruleset(ruleset, scope, required_factor_ids=None):
    if scope not in SCOPES:
        raise ValueError("未知门控作用域 %r（合法值：%s）"
                         % (scope, ", ".join(SCOPES)))
    collector = _collect_full if SCOPE_DEPTH[scope] == "full" else _collect_minimal
    codes = _resolve_codes(ruleset, required_factor_ids)
    pending = []
    missing_inputs = []
    for code in codes:
        p, m = collector(ruleset.factor(code))
        pending.extend(p)
        missing_inputs.extend(m)
    if pending:
        raise GateBlocked(scope, pending)
    return EffectiveRuleset(ruleset, scope, codes, missing_inputs)


def pending_report(ruleset, scope="plan", required_factor_ids=None):
    collector = _collect_full if SCOPE_DEPTH.get(scope, "minimal") == "full" \
        else _collect_minimal
    try:
        codes = _resolve_codes(ruleset, required_factor_ids)
    except InputError:
        return ([], [])
    pending = []
    missing_inputs = []
    for code in codes:
        p, m = collector(ruleset.factor(code))
        pending.extend(p)
        missing_inputs.extend(m)
    return pending, missing_inputs


__all__ = ["SCOPES", "SCOPE_DEPTH", "EffectiveRuleset", "effective_ruleset",
           "pending_report"]