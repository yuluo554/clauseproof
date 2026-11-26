"""规则包快照装配（**零文件读取**：分册 dict 由 :mod:`clauseproof.core.basis`
同款纪律经输入通路装载——本器官的分册随包冻结，由 ``__init__`` 用字面量声明
文件名与作用域，实际 dict 从随包冻结资产读入一次并缓存）。

注：与其他器官的「参数包字面量」不同，本器官的规则包是**带条款原文与来源
URL 的完整台账**（约 15KB × 4 册），逐条目改写成 Python 字面量会引入转写
误差风险；故采用「随包冻结 JSON + 漂移门」结构——``data/*.json`` 与来源仓
逐字节同 sha256，``tests/test_ebike_limits.py`` 的漂移门核对 manifest 登记
的 sha256 与文件实际值一致，手改任一侧即红。引擎只收内存 dict（``__init__``
负责读随包文件——这与 SKELETON-SPEC §2 的「器官不做文件 IO」的判定语义
一致：判定发生在 :mod:`engine`，装载是器官包的装配面（与 ``clauses.json``
的 ``Basis.from_json`` 同一形态）。
"""

from typing import Any, Dict, Mapping, Tuple
import json
import os

from . import engine

#: 规则包快照版本（= 条文库坐标）。来源基准日 2026-10-14（M1 逐条核到条款号）。
PARAMS_VERSION = "2026-10-14"

PACK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PACK_DIR, "data")

#: 依据锚点 id（条文库必须具备的全部条目；缺一即 ``BasisMissing`` → 退出码 3）
CLAUSE_RULESETS = "contract:rulesets"
CLAUSE_STATUS_GATE = "contract:status-gate"
CLAUSE_CLAUSE_DISCIPLINE = "contract:clause-discipline"
CLAUSE_FOUR_STATES = "contract:four-states"
CLAUSE_NOT_PROVIDED = "contract:not-provided"
CLAUSE_UNIT_ALIASES = "contract:unit-aliases"
CLAUSE_VERSION_ANCHORS = "param:version-anchors"
CLAUSE_MAPPING_TABLE = "contract:mapping-table"

#: 分册文件 → (作用域, 版本键)；与 engine.RULESET_FILES 同源
RULESET_FILES: Tuple[Tuple[str, str, str], ...] = engine.RULESET_FILES

_RULESET_CACHE: Dict[str, Any] = {}


def _load_json(name: str) -> Any:
    path = os.path.join(DATA_DIR, name)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def manifest() -> Dict[str, Any]:
    """manifest dict（漂移门与装配共用）。"""
    return _load_json("manifest.json")


def ruleset_doc(file_name: str) -> Dict[str, Any]:
    """分册 dict（进程内缓存一次）。"""
    if file_name not in _RULESET_CACHE:
        _RULESET_CACHE[file_name] = _load_json(file_name)
    return _RULESET_CACHE[file_name]


def ruleset_docs() -> Dict[str, Dict[str, Any]]:
    """全部分册 dict（``engine.check_profile`` 的装配入口）。"""
    return {name: ruleset_doc(name) for name, _scope, _key in RULESET_FILES}


def unit_alias_index() -> Dict[str, str]:
    """单位别名表（来自随包映射节字面量）。"""
    from .mapping import unit_alias_index as _index
    return _index()


def clause_specs() -> Tuple[Tuple[str, str], ...]:
    """条文库应含的 ``(clause_id, path)``：8 条契约条目。"""
    return (
        (CLAUSE_RULESETS, "数据契约 / 规则包分册"),
        (CLAUSE_STATUS_GATE, "数据契约 / status 门控"),
        (CLAUSE_CLAUSE_DISCIPLINE, "数据契约 / 条款号核对纪律"),
        (CLAUSE_FOUR_STATES, "数据契约 / 判定四态"),
        (CLAUSE_NOT_PROVIDED, "数据契约 / 未提供不判符合"),
        (CLAUSE_UNIT_ALIASES, "数据契约 / 单位别名表"),
        (CLAUSE_VERSION_ANCHORS, "参数包 / 版本锚定窗口"),
        (CLAUSE_MAPPING_TABLE, "数据契约 / 字段映射"),
    )


def clause_text(clause_id: str) -> str:
    """契约条目正文（数据契约，不冒充法规文号）。"""
    if clause_id == CLAUSE_RULESETS:
        return ("随包冻结四册规则包：GB 17761-2024（整车）/ GB 17761-2018（整车历史）/"
                " GB 43854-2024（电池）/ GB 42296-2022（充电器）；限值以正式标准全文核对"
                "（基准日 2026-10-14）；pending 条目零参与核查")
    if clause_id == CLAUSE_STATUS_GATE:
        return ("status != verified 的条目零参与核查路径，只进 excluded 集合并显式列出；"
                "pending 条目 value 必须为 null（待核对不许预填数值）")
    if clause_id == CLAUSE_CLAUSE_DISCIPLINE:
        return ("clause_status 与 status 分开跟踪；clause_status=verified 必须有 clause；"
                "pending 时 clause 必须为 null——绝不编造条款号（编造标准内容比缺失更严重）")
    if clause_id == CLAUSE_FOUR_STATES:
        return ("判定四态：compliant / non_compliant / not_applicable / not_provided；"
                "整体结论按最弱优先聚合（non_compliant > not_provided > not_assessed > "
                "compliant）；一条规则都不适用时整体记 not_assessed")
    if clause_id == CLAUSE_NOT_PROVIDED:
        return ("未提供参数绝不判为符合——「没查到问题」与「没检查过」绝不等同；"
                " applies_if 引用参数不可解析时按「不知道是否适用」处理，"
                "不出 not_applicable")
    if clause_id == CLAUSE_UNIT_ALIASES:
        return ("单位换算系数是数学常量（kg↔g、km↔m、%↔‰ 等显式无损十进换算）；"
                "可换算 → 判定并降级 warning；不可换算一律 not_provided(unit_incompatible)，"
                "绝不臆测；全链路 Decimal（禁 float）")
    if clause_id == CLAUSE_VERSION_ANCHORS:
        return ("GB17761 族版本锚定：>=2025-09-01 → GB17761-2024；<2025-09-01 → "
                "GB17761-2018（历史车型对照）；无日期不猜，要求显式指定")
    if clause_id == CLAUSE_MAPPING_TABLE:
        return ("字段映射：已登记列名变体 → 标准参数名；歧义列名（如「车速」）→ "
                "mapping_uncertain 显式未提供，绝不猜；未登记列名 → missing")
    raise KeyError(clause_id)


__all__ = [
    "PARAMS_VERSION", "RULESET_FILES", "CLAUSE_RULESETS", "CLAUSE_STATUS_GATE",
    "CLAUSE_CLAUSE_DISCIPLINE", "CLAUSE_FOUR_STATES", "CLAUSE_NOT_PROVIDED",
    "CLAUSE_UNIT_ALIASES", "CLAUSE_VERSION_ANCHORS", "CLAUSE_MAPPING_TABLE",
    "manifest", "ruleset_doc", "ruleset_docs", "unit_alias_index",
    "clause_specs", "clause_text",
]
