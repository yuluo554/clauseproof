"""规则包装配（随包冻结资产 + 条文库坐标声明）。

**文件读取只发生在这里**（与 ``Basis.from_json`` 同形态的装配）：manifest / 八个年度
规则包 / 真值库 / 条文库由本模块读入一次（进程内缓存），判定内核只收内存 dict。

随包资产与来源仓**逐字节同 sha256**（manifest 登记，测试逐文件核对——漂移门）。
条文库的 ref 条款 = 来源规则包 ``ref`` 节点的并集（source id + 条款定位词），
不手写、不复制：任何规则包新增 ref 而条文库未登记，测试立刻红。
"""

import json
import os
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from . import rules as R

#: 规则包快照版本（= 条文库坐标 = 来源仓核对日期）。
PARAMS_VERSION = "2026-10-07"

PACK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PACK_DIR, "data")

#: 数据契约条款（不属任何一册规则包，是器官自身的出账口径）
CLAUSE_GATE = "contract:status-gate"
CLAUSE_SOCIAL = "contract:social-input"
CLAUSE_MONTHS = "contract:months-padding"
CLAUSE_LEDGER = "contract:ledger"

CONTRACT_CLAUSES = (CLAUSE_GATE, CLAUSE_SOCIAL, CLAUSE_MONTHS, CLAUSE_LEDGER)

_CACHE: Dict[str, Any] = {}


def _load_json(name: str) -> Any:
    """读 JSON 且 float → Decimal（禁 float 进计算路径）。"""
    with open(os.path.join(DATA_DIR, name), "r", encoding="utf-8") as handle:
        return json.load(handle, parse_float=Decimal)


def manifest() -> Dict[str, Any]:
    if "manifest" not in _CACHE:
        _CACHE["manifest"] = _load_json("manifest.json")
    return _CACHE["manifest"]


def pack_entries() -> Tuple[Dict[str, Any], ...]:
    """manifest 登记的年度规则包条目（year / file / sha256 / bytes）。"""
    return tuple(manifest().get("packs", ()))


def years() -> Tuple[int, ...]:
    return tuple(entry["year"] for entry in pack_entries())


def pack_filenames() -> List[str]:
    return [entry["file"] for entry in pack_entries()]


def raw_packs() -> Dict[int, Dict[str, Any]]:
    """全部年度规则包原始 dict ``{year: raw}``（进程序列缓存）。"""
    if "raw_packs" not in _CACHE:
        loaded = {}
        for entry in pack_entries():
            loaded[entry["year"]] = _load_json(entry["file"])
        _CACHE["raw_packs"] = loaded
    return _CACHE["raw_packs"]


def ruleset(year: int) -> R.Ruleset:
    """随包规则包 → 已校验 ``Ruleset``（结构加载；生效仍走 status 门控）。"""
    cache_key = "ruleset:%d" % year
    if cache_key not in _CACHE:
        raw = raw_packs().get(year)
        if raw is None:
            raise R.RulesetNotFoundError(year, sorted(raw_packs()))
        _CACHE[cache_key] = R.build_ruleset(raw, expected_year=year)
    return _CACHE[cache_key]


def truth() -> Dict[str, Any]:
    """算例真值库（随包冻结；engine 对账的独立真值）。"""
    if "truth" not in _CACHE:
        _CACHE["truth"] = _load_json(manifest()["truth"]["file"])
    return _CACHE["truth"]


def truth_cases() -> Dict[str, Dict[str, Any]]:
    return {case["id"]: case for case in truth()["cases"]}


def clauses() -> Dict[str, Any]:
    if "clauses" not in _CACHE:
        _CACHE["clauses"] = _load_json("clauses.json")
    return _CACHE["clauses"]


def ref_clause_id(ref: Any) -> str:
    """规则包 ref 节点 → 条文库稳定键 ``<source>:<clause>``。"""
    if not isinstance(ref, dict) or not ref.get("source") or not ref.get("clause"):
        raise R.RulesetSchemaError("ref 节点缺 source/clause（规则包自相矛盾）")
    return "%s:%s" % (ref["source"], ref["clause"])


def clause_ids() -> List[str]:
    return sorted(clause["clause_id"] for clause in clauses()["clauses"])


def refs_used(year: int) -> List[str]:
    """某年度规则包全部 ref 节点对应的条文库键（条文库覆盖面的证据源）。"""
    keys = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("ref"), dict):
                keys.add(ref_clause_id(node["ref"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(raw_packs()[year])
    return sorted(keys)


__all__ = [
    "PARAMS_VERSION",
    "DATA_DIR",
    "CLAUSE_GATE",
    "CLAUSE_SOCIAL",
    "CLAUSE_MONTHS",
    "CLAUSE_LEDGER",
    "CONTRACT_CLAUSES",
    "manifest",
    "pack_entries",
    "years",
    "pack_filenames",
    "raw_packs",
    "ruleset",
    "truth",
    "truth_cases",
    "clauses",
    "clause_ids",
    "ref_clause_id",
    "refs_used",
]