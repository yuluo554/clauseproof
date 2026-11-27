"""规则包装配（随包冻结资产 + 条文库契约声明）。

manifest / 40 份规则包 / units.json 与来源仓逐字节同 sha256（漂移门核对），由本模块
读入一次（与 ``Basis.from_json`` 同形态的装配）；判定内核只收内存 dict。
"""

from typing import Any, Dict, List, Tuple
import json
import os
from decimal import Decimal

from . import engine, rules

#: 规则包快照版本（= 条文库坐标）。来源基准日 2026-10-13。
PARAMS_VERSION = "2026-10-13"

PACK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PACK_DIR, "data")

CLAUSE_THREE_AXIS = "contract:three-axis"
CLAUSE_GATE = "contract:status-gate"
CLAUSE_MIXED = "contract:mixed-coordinates"
CLAUSE_BOUNDARY = "contract:boundary"
CLAUSE_FACTOR_PRIORITY = "contract:factor-priority"
CLAUSE_FORMULA_GRAMMAR = "contract:formula-grammar"
CLAUSE_UNITS = "contract:units"
CLAUSE_QUALITY = "contract:quality-checks"
CLAUSE_QUOTA = "contract:quota-methods"
CLAUSE_DISCLAIMER = "contract:quota-disclaimer"

_CACHE: Dict[str, Any] = {}


def _load_json(name: str) -> Any:
    """读 JSON 且 float → Decimal（禁 float 进入计算路径；与来源 jsonio 同口径）。"""
    with open(os.path.join(DATA_DIR, name), "r", encoding="utf-8") as handle:
        return json.load(handle, parse_float=Decimal)


def manifest() -> Dict[str, Any]:
    if "manifest" not in _CACHE:
        _CACHE["manifest"] = _load_json("manifest.json")
    return _CACHE["manifest"]


def packs() -> Dict[str, Dict[str, Any]]:
    """全部坐标规则包 ``{key: pack}``（进程内缓存）。"""
    if "packs" not in _CACHE:
        loaded = {}
        for entry in manifest().get("coordinates", []):
            key = "%s/%s/%s" % (entry["standard"], entry["year"], entry["industry"])
            loaded[key] = _load_json(entry["file"])
        _CACHE["packs"] = loaded
    return _CACHE["packs"]


def index() -> rules.RulesIndex:
    """坐标索引 + 门控（``RulesIndex``）。"""
    if "index" not in _CACHE:
        _CACHE["index"] = rules.RulesIndex(manifest(), packs())
    return _CACHE["index"]


def unit_table() -> engine.UnitTable:
    if "units" not in _CACHE:
        _CACHE["units"] = engine.UnitTable(_load_json("units.json"))
    return _CACHE["units"]


def pack_filenames() -> List[str]:
    return [entry["file"] for entry in manifest().get("coordinates", [])]


def clause_specs() -> Tuple[Tuple[str, str], ...]:
    """条文库应含的 ``(clause_id, path)``：10 条契约条目。"""
    return (
        (CLAUSE_THREE_AXIS, "数据契约 / 三维坐标"),
        (CLAUSE_GATE, "数据契约 / status 门控"),
        (CLAUSE_MIXED, "数据契约 / 跨坐标混算拦截"),
        (CLAUSE_BOUNDARY, "数据契约 / 核算边界"),
        (CLAUSE_FACTOR_PRIORITY, "数据契约 / 因子来源优先级"),
        (CLAUSE_FORMULA_GRAMMAR, "数据契约 / 公式表达式文法"),
        (CLAUSE_UNITS, "数据契约 / 单位换算"),
        (CLAUSE_QUALITY, "数据契约 / 数据质量校核"),
        (CLAUSE_QUOTA, "数据契约 / 配额方法学"),
        (CLAUSE_DISCLAIMER, "数据契约 / 配额免责声明"),
    )


def clause_text(clause_id: str) -> str:
    if clause_id == CLAUSE_THREE_AXIS:
        return ("三维坐标：GB/T 32150 新旧双标尺 × 年度（2022–2026）× 行业"
                "（发电/钢铁/水泥/铝冶炼）；坐标空间由 manifest 单点索引，代码内零坐标字面量")
    if clause_id == CLAUSE_GATE:
        return ("status 门控按计算路径分作用域：calc / quota / check 各查各的块；"
                "pending 条目零参与其自身路径；input_required 为外部输入槽（不阻断，"
                "运行时显式索取，不得静默取 0）")
    if clause_id == CLAUSE_MIXED:
        return "跨坐标混算拦截：一次核算输入出现两个及以上坐标即拒绝（退出码 2）"
    if clause_id == CLAUSE_BOUNDARY:
        return ("核算边界：应核算源缺活动数据即报缺失输入（不得静默按空核算）；"
                "双标尺差异以 delta_vs_2015 声明为准并以结构字段交叉校验")
    if clause_id == CLAUSE_FACTOR_PRIORITY:
        return ("因子来源优先级：实测 > 官方因子库 > 行业缺省（按类别分派）；"
                "三层皆不可用不得静默取 0 或 1；档案自报来源不在白名单按不可用处理")
    if clause_id == CLAUSE_FORMULA_GRAMMAR:
        return ("公式表达式树文法：mul/add/sub/div/var/const 白名单；const 只允许引用"
                "系数 id（禁内联数值）；除数为 0 报错")
    if clause_id == CLAUSE_UNITS:
        return ("单位换算：量纲 → 基准单位 → 换算因子（定义性关系，表来自随包 units.json）；"
                "跨量纲禁止换算；复合因子单位 <排放单位>_per_<活动单位>")
    if clause_id == CLAUSE_QUALITY:
        return ("数据质量校核四类：单位一致性 / 量级异常 / 跨年度突变 / 比强度合理性；"
                "阈值全部取自规则包 quality.thresholds；pending 规则不执行并记跳过原因")
    if clause_id == CLAUSE_QUOTA:
        return ("配额试算方法学：benchmark（A=Qe×Be×Ff）/ intensity_coefficient"
                "（A=E×(1+α)，α 由偏离度分段）/ historical_intensity / none（显式不适用）")
    if clause_id == CLAUSE_DISCLAIMER:
        return ("配额试算强制免责声明：返回结构 disclaimer_required 恒为 True，"
                "渲染层必须输出规则包携带的声明正文")
    raise KeyError(clause_id)


__all__ = [
    "PARAMS_VERSION", "manifest", "packs", "index", "unit_table", "pack_filenames",
    "clause_specs", "clause_text", "CLAUSE_THREE_AXIS", "CLAUSE_GATE",
    "CLAUSE_MIXED", "CLAUSE_BOUNDARY", "CLAUSE_FACTOR_PRIORITY",
    "CLAUSE_FORMULA_GRAMMAR", "CLAUSE_UNITS", "CLAUSE_QUALITY", "CLAUSE_QUOTA",
    "CLAUSE_DISCLAIMER",
]