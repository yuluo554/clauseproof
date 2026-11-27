"""版本差异对照（迁自来源 ``engine.compare``）。

scope="compare" 只校验结构字段，不要求项目明细 verified；明细任一待核对时，
该因素只出因素级差异，条目级比较跳过并记 notes（避免把「未转写」误报成「标准差异」）。
"""

from ..model import EXAM_TYPES


class DiffEntry:
    __slots__ = ("kind", "key", "label", "detail", "basis_a", "basis_b")

    def __init__(self, kind, key, label, detail="", basis_a="", basis_b=""):
        self.kind = kind
        self.key = key
        self.label = label
        self.detail = detail
        self.basis_a = basis_a
        self.basis_b = basis_b

    def as_dict(self):
        return {"kind": self.kind, "key": self.key, "label": self.label,
                "detail": self.detail, "basis_a": self.basis_a,
                "basis_b": self.basis_b}


class DiffReport:
    __slots__ = ("ruleset_a", "ruleset_b", "entries", "notes")

    def __init__(self, ruleset_a, ruleset_b, entries=None, notes=None):
        self.ruleset_a = ruleset_a
        self.ruleset_b = ruleset_b
        self.entries = list(entries or [])
        self.notes = list(notes or [])

    def by_kind(self, kind):
        return [e for e in self.entries if e.kind == kind]

    def as_dict(self):
        return {"ruleset_a": self.ruleset_a, "ruleset_b": self.ruleset_b,
                "entries": [e.as_dict() for e in self.entries],
                "notes": list(self.notes)}


def _factor_codes(eff):
    return set(eff.ruleset.factor_codes)


def _basis_of(eff, code):
    factor = eff.ruleset.factor(code)
    if factor is None:
        return ""
    return "%s 第 %s 节" % (
        (factor.get("basis") or {}).get("doc_code")
        or eff.ruleset.basis.get("doc_code", ""), factor.get("factor_id", ""))


def detail_pending(factor):
    if factor.get("status") == "pending":
        return True
    if factor.get("eligibility", {}).get("status") == "pending":
        return True
    if factor.get("period", {}).get("status") == "pending":
        return True
    if any(d.get("status") == "pending" for d in factor.get("target_diseases") or []):
        return True
    for key in EXAM_TYPES:
        block = factor["examinations"][key]
        if block.get("status") == "pending":
            return True
        for group in ("required_items", "supplementary_items", "optional_items"):
            for item in block.get(group) or []:
                if item.get("status") == "pending":
                    return True
    return False


def compare_rulesets(eff_a, eff_b):
    codes_a = _factor_codes(eff_a)
    codes_b = _factor_codes(eff_b)
    entries = []
    for code in sorted(codes_b - codes_a):
        entries.append(DiffEntry(
            "factor_added", code,
            "新增危害因素：%s" % eff_b.ruleset.factor(code)["factor_name"],
            basis_b=_basis_of(eff_b, code)))
    for code in sorted(codes_a - codes_b):
        entries.append(DiffEntry(
            "factor_removed", code,
            "删除危害因素：%s" % eff_a.ruleset.factor(code)["factor_name"],
            basis_a=_basis_of(eff_a, code)))
    skipped_detail = []
    for code in sorted(codes_a & codes_b):
        fa = eff_a.ruleset.factor(code)
        fb = eff_b.ruleset.factor(code)
        if detail_pending(fa) or detail_pending(fb):
            pending_sides = []
            if detail_pending(fa):
                pending_sides.append(eff_a.ruleset_id)
            if detail_pending(fb):
                pending_sides.append(eff_b.ruleset_id)
            skipped_detail.append((code, pending_sides))
            continue
        for exam_type in EXAM_TYPES:
            block_a = fa["examinations"][exam_type]
            block_b = fb["examinations"][exam_type]
            req_a = {i.get("item_code") for i in block_a.get("required_items") or []}
            req_b = {i.get("item_code") for i in block_b.get("required_items") or []}
            if req_a != req_b:
                added = sorted(req_b - req_a)
                removed = sorted(req_a - req_b)
                detail = []
                if added:
                    detail.append("新增 %s" % ", ".join(added))
                if removed:
                    detail.append("删除 %s" % ", ".join(removed))
                entries.append(DiffEntry(
                    "required_items_changed", "%s/%s" % (code, exam_type),
                    "%s 的 %s 必检项目构成变化" % (fa["factor_name"], exam_type),
                    detail="；".join(detail),
                    basis_a=_basis_of(eff_a, code), basis_b=_basis_of(eff_b, code)))
            opt_a = block_a.get("optional_items") or []
            opt_b = block_b.get("optional_items") or []
            if (not opt_a) != (not opt_b):
                entries.append(DiffEntry(
                    "optional_items_adjusted", "%s/%s" % (code, exam_type),
                    "%s 的 %s 选检项目调整" % (fa["factor_name"], exam_type),
                    detail="由 %d 项变为 %d 项" % (len(opt_a), len(opt_b)),
                    basis_a=_basis_of(eff_a, code), basis_b=_basis_of(eff_b, code)))
        if fa["period"].get("kind") != fb["period"].get("kind") or \
                fa["period"].get("value") != fb["period"].get("value"):
            entries.append(DiffEntry(
                "period_changed", code, "%s 检查周期变化" % fa["factor_name"],
                detail="%s/%s → %s/%s"
                       % (fa["period"].get("kind"), fa["period"].get("value"),
                          fb["period"].get("kind"), fb["period"].get("value")),
                basis_a=_basis_of(eff_a, code), basis_b=_basis_of(eff_b, code)))
    notes = []
    if skipped_detail:
        by_side = {}
        for code, sides in skipped_detail:
            by_side.setdefault(", ".join(sides), []).append(code)
        for sides, codes in sorted(by_side.items()):
            notes.append(
                "%d 个共同因素的明细在 %s 侧尚未核对 → 已跳过其条目级比较"
                "（避免把「未转写」误报成「标准差异」）：%s%s"
                % (len(codes), sides, "、".join(codes[:8]),
                   "" if len(codes) <= 8 else "（等 %d 个）" % len(codes)))
    if not entries:
        notes.append("两版结构对照无差异条目。")
    return DiffReport(eff_a.ruleset_id, eff_b.ruleset_id, entries, notes)


__all__ = ["DiffEntry", "DiffReport", "detail_pending", "compare_rulesets"]