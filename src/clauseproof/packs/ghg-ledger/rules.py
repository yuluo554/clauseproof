"""规则索引 / status 门控 / 边界识别（来源 rules + boundary 模块的判定面）。

三件事：

1. **门控单点**：``RulesIndex.effective_ruleset(coord, scope)`` 是唯一允许进入
   计算路径的入口，按计算路径作用域（calc / quota / check）校验该路径引用的块；
   任一携带 ``status`` 的条目非 ``verified``（或数值为 null）即抛
   :class:`RulesetNotEffective`；``input_required`` 为外部输入槽（不阻断）；
2. **混算拦截**：``detect_mixed_coordinates`` 在输入里找出全部坐标，多于一个即抛
   :class:`MixedCoordinateError`；
3. **边界识别**：``identify_boundary`` 输出应核算排放源清单（纳入/排除/缺输入）；
   ``diff_boundary`` 双标尺差异（以旧版为基准，按 ``delta_vs_2015`` 声明 +
   结构字段变化交叉校验）。

代码内零坐标字面量、零政策数值：坐标空间与门槛全部来自 manifest dict。
"""

from typing import Any, Dict, List, Mapping, Optional

from .engine import (
    Coordinate,
    CoordinateError,
    MixedCoordinateError,
    RulesetValidationError,
    RulesetNotEffective,
    BoundaryError,
    as_decimal,
)

MANIFEST_SCHEMA = "ghg-manifest/v1"
SCHEMA_RULESET = "ghg-ruleset/v1"
STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"
STATUS_INPUT_REQUIRED = "input_required"

NULLABLE_POLICY_KEYS = ("value",)

SCOPE_CALC = "calc"
SCOPE_QUOTA = "quota"
SCOPE_CHECK = "check"
SCOPE_BLOCKS = {
    SCOPE_CALC: ("standard", "boundary", "engine", "factors"),
    SCOPE_QUOTA: ("quota",),
    SCOPE_CHECK: ("quality",),
}

DELTA_SAME = "same"
DELTA_ADDED = "added"
DELTA_REMOVED = "removed"
DELTA_ADJUSTED = "adjusted"
DELTA_VALUES = (DELTA_SAME, DELTA_ADDED, DELTA_REMOVED, DELTA_ADJUSTED)

_COMPARED_FIELDS = ("name", "category", "required")
ACTIVITY_VALUE_KEY = "value"


def _iter_entries(node, path=""):
    """递归遍历，产出所有携带 ``status`` 字段的条目 (path, node)。"""
    if isinstance(node, dict):
        if "status" in node:
            yield path, node
        for key in sorted(node.keys()):
            child = node[key]
            if isinstance(child, (dict, list)):
                yield from _iter_entries(child, "%s.%s" % (path, key) if path else key)
    elif isinstance(node, list):
        for idx, child in enumerate(node):
            if isinstance(child, (dict, list)):
                yield from _iter_entries(child, "%s[%d]" % (path, idx))


def _entry_label(path, node):
    return node.get("id") or path or "<anonymous>"


def _entry_is_effective(node):
    """该条目是否不阻断其所在计算路径的门控。

    verified 且数值非 null → 放行；verified 但数值为 null → 拦截；
    input_required → 放行（外部输入槽，运行时显式索取）；其余（含 pending）→ 拦截。
    """
    status = node.get("status")
    if status == STATUS_INPUT_REQUIRED:
        return True
    if status != STATUS_VERIFIED:
        return False
    for key in NULLABLE_POLICY_KEYS:
        if key in node and node[key] is None:
            return False
    return True


def _entry_is_usable(node):
    return node.get("status") == STATUS_VERIFIED and node.get("value") is not None


def _scoped_entries(pack, scope):
    top_keys = None if scope is None else SCOPE_BLOCKS[scope]
    for key in sorted(pack.keys()):
        if top_keys is not None and key not in top_keys:
            continue
        child = pack[key]
        if isinstance(child, (dict, list)):
            for path, node in _iter_entries(child, key):
                yield path, node
        elif isinstance(child, dict) and "status" in child:
            yield key, child


class RulesIndex(object):
    """坐标空间索引 + 规则包读取 + 门控（pack 为内存 dict）。"""

    def __init__(self, manifest: Mapping, packs: Mapping[str, Any]) -> None:
        if manifest.get("schema") != MANIFEST_SCHEMA:
            raise RulesetValidationError(
                "manifest schema 不受支持：%r" % manifest.get("schema"))
        self._manifest = manifest
        self._packs = packs
        self._by_key = {}
        for item in manifest.get("coordinates", []):
            coord = Coordinate(item["standard"], item["year"], item["industry"])
            if coord.key in self._by_key:
                raise RulesetValidationError("manifest 坐标重复：%s" % coord.key)
            self._by_key[coord.key] = item

    # ---------- 坐标空间 ----------
    @property
    def standards(self):
        return list(self._manifest.get("standards", []))

    @property
    def years(self):
        return list(self._manifest.get("years", []))

    @property
    def industries(self):
        return list(self._manifest.get("industries", []))

    def coordinates(self):
        return [Coordinate(i["standard"], i["year"], i["industry"])
                for i in self._manifest.get("coordinates", [])]

    def has(self, coord):
        return coord.key in self._by_key

    def require(self, coord):
        if not self.has(coord):
            raise CoordinateError(
                "坐标不存在于规则空间：%s（可用坐标见 manifest）" % coord.key)
        return coord

    def resolve(self, standard, year, industry):
        return self.require(Coordinate(standard, year, industry))

    # ---------- 规则包读取 ----------
    def pack(self, coord):
        """原始规则包（含 pending 条目）——仅供只读预览，不得用于计算。"""
        self.require(coord)
        if coord.key not in self._packs:
            raise RulesetValidationError("规则包文件缺失：%s" % coord.key)
        return self._packs[coord.key]

    def pack_sha256(self, coord):
        return self._by_key[coord.key].get("sha256")

    def bench_targets(self):
        targets = (self._manifest.get("bench") or {}).get("targets")
        if not isinstance(targets, dict) or not targets:
            raise RulesetValidationError("manifest 缺少基准门槛配置 bench.targets")
        return dict(targets)

    def effective_ruleset(self, coord, scope=SCOPE_CALC):
        """门控入口：返回通过校验的规则包，否则抛 :class:`RulesetNotEffective`。"""
        pack = self.pack(coord)
        if pack.get("schema") != SCHEMA_RULESET:
            raise RulesetValidationError(
                "规则包 %s schema 不受支持：%r" % (coord.key, pack.get("schema")))
        declared = pack.get("coordinate") or {}
        if Coordinate(declared.get("standard"), declared.get("year"),
                      declared.get("industry")) != coord:
            raise RulesetValidationError(
                "规则包 %s 内声明的坐标与索引不一致：%r" % (coord.key, declared))
        blocked = [_entry_label(p, n) for p, n in _scoped_entries(pack, scope)
                   if not _entry_is_effective(n)]
        if blocked:
            raise RulesetNotEffective(coord.key, blocked)
        return pack

    def gate_report(self, coord, scope=None):
        """门控体检（不抛异常）：返回待核对条目清单。"""
        pack = self.pack(coord)
        pending = []
        for path, node in _scoped_entries(pack, scope):
            if not _entry_is_effective(node):
                pending.append({"entry": _entry_label(path, node),
                                "path": path, "status": node.get("status")})
        return {"coordinate": coord.key, "scope": scope or "all",
                "effective": not pending, "pending_count": len(pending),
                "pending": pending}

    def collect_numeric_tokens(self):
        """采集全部规则包中的政策数值 token（零政策字面量门禁的数据源）。"""
        tokens = set()
        for coord in self.coordinates():
            pack = self.pack(coord)
            for _path, node in _iter_entries(pack):
                for key in ("value", "coefficient", "threshold", "limit"):
                    val = node.get(key)
                    if isinstance(val, bool):
                        continue
                    if isinstance(val, int):
                        tokens.add(str(val))
        return sorted(tokens)


def parse_coordinate(raw, index: Optional[RulesIndex] = None):
    """从 dict 或 ``a/b/c`` 字符串解析坐标（传入 index 时校验坐标存在）。"""
    if isinstance(raw, Coordinate):
        coord = raw
    elif isinstance(raw, dict):
        coord = Coordinate(raw.get("standard"), raw.get("year"), raw.get("industry"))
    elif isinstance(raw, str):
        parts = raw.split("/")
        if len(parts) != 3:
            raise CoordinateError("坐标字符串应形如 a/b/c：%r" % (raw,))
        coord = Coordinate(parts[0], parts[1], parts[2])
    else:
        raise CoordinateError("坐标必须是对象或 a/b/c 字符串：%r" % (raw,))
    if index is not None:
        index.require(coord)
    return coord


def _looks_like_standard(text):
    if "-" not in text:
        return False
    return any(ch.isdigit() for ch in text) and text.islower()


def detect_mixed_coordinates(payload):
    """在输入载荷里找出全部坐标；多于一个即抛 :class:`MixedCoordinateError`。"""
    found = {}

    def visit(node):
        if isinstance(node, dict):
            if all(k in node for k in ("standard", "year", "industry")):
                try:
                    coord = Coordinate(node["standard"], node["year"], node["industry"])
                except CoordinateError:
                    coord = None
                if coord is not None:
                    found.setdefault(coord.key, node)
            for key in sorted(node.keys()):
                visit(node[key])
        elif isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, str):
            parts = node.split("/")
            if len(parts) == 3 and all(parts):
                try:
                    coord = Coordinate(parts[0], parts[1], parts[2])
                except CoordinateError:
                    return
                if coord.standard and _looks_like_standard(coord.standard):
                    found.setdefault(coord.key, node)

    visit(payload)
    if len(found) > 1:
        raise MixedCoordinateError(
            "输入包含多个规则包坐标（跨坐标混算被拒）：%s"
            % "、".join(sorted(found.keys())))
    return [found[key] for key in sorted(found.keys())]


def parse_payload_coordinate(payload, index=None):
    """从输入载荷取唯一坐标（无坐标 → 抛 CoordinateError）。"""
    coords = detect_mixed_coordinates(payload)
    if not coords:
        raise CoordinateError("输入未声明规则包坐标（需要 standard/year/industry）")
    raw = coords[0]
    return parse_coordinate(raw, index=index)


# ---------------------------------------------------------------------------
# 边界识别（来源 boundary 模块）
# ---------------------------------------------------------------------------
def _sources_of(pack):
    return list(pack.get("boundary", {}).get("sources", []) or [])


def _catalog(pack):
    out = {}
    for src in _sources_of(pack):
        sid = src.get("id")
        if not sid:
            raise BoundaryError("规则包排放源条目缺少 id")
        if sid in out:
            raise BoundaryError("规则包排放源 id 重复：%s" % sid)
        out[sid] = src
    return out


def _provided(payload):
    out = {}
    for item in payload.get("sources", []) or []:
        sid = item.get("source_id")
        if not sid:
            raise BoundaryError("档案中存在缺少 source_id 的排放源条目")
        if sid in out:
            raise BoundaryError("档案中排放源重复：%s" % sid)
        out[sid] = item
    return out


def _has_activity(item):
    activity = (item or {}).get("activity") or {}
    return activity.get(ACTIVITY_VALUE_KEY) is not None


def _clause_text(clause):
    if not clause:
        return ""
    parts = [p for p in (clause.get("code"), clause.get("article")) if p]
    return " ".join(parts)


def _source_report(coord, src, provided, include_optional):
    sid = src["id"]
    item = provided.get(sid)
    has_input = _has_activity(item)
    required = src.get("required") is True
    included = has_input and (required or include_optional)

    if included and required:
        reason = "应核算排放源，档案已提供活动数据"
    elif included:
        reason = "选填排放源，档案已提供活动数据（按 include_optional 纳入）"
    elif required:
        reason = "应核算排放源，但档案未提供活动数据（缺失输入）"
    else:
        reason = "非应核算排放源，档案未提供活动数据（排除）"
    clause_text = _clause_text(src.get("clause"))
    if clause_text:
        reason = "%s；依据 %s" % (reason, clause_text)
    return {"id": sid, "name": src.get("name"), "category": src.get("category"),
            "required": required, "clause": src.get("clause"),
            "included": included, "reason": reason}


def identify_boundary(payload, coord, pack, include_optional=False):
    """识别该坐标下的应核算排放源清单（纳入/排除/缺输入）。"""
    catalog = _catalog(pack)
    provided = _provided(payload)
    unknown = sorted(set(provided) - set(catalog))
    if unknown:
        raise BoundaryError(
            "档案含规则包未定义的排放源 id：%s（坐标 %s）"
            % ("、".join(unknown), coord.key))
    sources = []
    for sid in sorted(catalog):
        sources.append(_source_report(coord, catalog[sid], provided, include_optional))
    included = [s["id"] for s in sources if s["included"]]
    missing = [s["id"] for s in sources if s["required"] and not s["included"]]
    excluded = [s["id"] for s in sources if not s["included"] and not s["required"]]
    return {"coordinate": coord.as_dict(), "coordinate_key": coord.key,
            "sources": sources, "included": included, "excluded": excluded,
            "missing_inputs": missing,
            "required_count": len([s for s in sources if s["required"]]),
            "included_count": len(included), "schema": "ghg-boundaryreport/v1"}


def _structural_changes(old_src, new_src):
    changes = []
    for field in _COMPARED_FIELDS:
        before = old_src.get(field)
        after = new_src.get(field)
        if before != after:
            changes.append({"field": field, "from": before, "to": after})
    return changes


def diff_boundary(coord_old, coord_new, index):
    """双标尺差异（以旧版为基准）：added / removed / adjusted / unchanged。"""
    if coord_old.standard == coord_new.standard:
        raise CoordinateError(
            "双标尺差异需要两个不同通则坐标，收到同一通则：%s" % coord_old.standard)
    old = _catalog(index.pack(coord_old))
    new = _catalog(index.pack(coord_new))
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    adjusted = []
    unchanged = []
    for sid in sorted(set(old) & set(new)):
        old_src = old[sid]
        new_src = new[sid]
        declared = new_src.get("delta_vs_2015")
        if declared not in DELTA_VALUES:
            raise BoundaryError("排放源 %s 的 delta_vs_2015 取值非法：%r" % (sid, declared))
        changes = _structural_changes(old_src, new_src)
        if declared == DELTA_ADJUSTED:
            if not changes:
                changes = [{"field": "clause",
                            "from": _clause_text(old_src.get("clause")),
                            "to": _clause_text(new_src.get("clause"))}]
            for change in changes:
                row = dict(change)
                row["id"] = sid
                row["declared_delta"] = declared
                adjusted.append(row)
        else:
            if changes:
                raise BoundaryError(
                    "排放源 %s 声明 delta_vs_2015=%s，但结构字段实际变化 %s（口径不一致）"
                    % (sid, declared, [c["field"] for c in changes]))
            unchanged.append(sid)
    return {"base": coord_old.key, "target": coord_new.key,
            "added": added, "removed": removed, "adjusted": adjusted,
            "unchanged": unchanged,
            "added_count": len(added), "removed_count": len(removed),
            "adjusted_count": len({row["id"] for row in adjusted}),
            "unchanged_count": len(unchanged),
            "schema": "ghg-boundarydiff/v1"}


__all__ = [
    "MANIFEST_SCHEMA", "SCHEMA_RULESET", "STATUS_VERIFIED", "STATUS_PENDING",
    "STATUS_INPUT_REQUIRED", "SCOPE_CALC", "SCOPE_QUOTA", "SCOPE_CHECK",
    "SCOPE_BLOCKS", "DELTA_SAME", "DELTA_ADDED", "DELTA_REMOVED", "DELTA_ADJUSTED",
    "RulesIndex", "parse_coordinate", "detect_mixed_coordinates",
    "parse_payload_coordinate", "identify_boundary", "diff_boundary",
    "_entry_is_effective", "_entry_is_usable", "_scoped_entries",
    "_iter_entries", "collect_numeric_tokens",
]


def collect_numeric_tokens(index):
    return index.collect_numeric_tokens()