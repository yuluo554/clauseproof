"""规则包装配（随包冻结资产 + 条文库契约声明）。

规则集 ``gb7718-2011.json`` / ``gb7718-2025.json`` 与参数表
``nutrient-reference.json`` 与来源仓逐字节同 sha256（漂移门核对），由本模块
读入一次（与 ``Basis.from_json`` 同形态的装配）；判定内核只收内存 dict。

依据纪律原样保留：每条规则的 ``basis.status``（"已核对"/其他）是**规则级**
标记，产出结论时置 ``flagged_pending_basis``；本器官不修改规则包内容。
"""

from typing import Any, Dict, Tuple
import json
import os

from . import numeric

#: 规则包快照版本（= 条文库坐标）。来源基准日 2026-10-04（M1 条文块核对）。
PARAMS_VERSION = "2026-10-04"

PACK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PACK_DIR, "data")

#: 依据锚点 id（条文库必须具备的全部条目；缺一即 ``BasisMissing`` → 退出码 3）
CLAUSE_DUAL_RULESETS = "contract:dual-rulesets"
CLAUSE_THREE_LEVELS = "contract:three-levels"
CLAUSE_STATS = "contract:stats"
CLAUSE_BASIS_PENDING = "contract:basis-pending"
CLAUSE_GATE = "contract:gate"
CLAUSE_NRV = "numeric:nrv"
CLAUSE_ENERGY = "numeric:energy"
CLAUSE_CLAIM_THRESHOLD = "numeric:claim-threshold"
CLAUSE_DATE_LOGIC = "numeric:date-logic"
CLAUSE_NUTRITION_ROWS = "numeric:nutrition-rows"
CLAUSE_ALLERGEN = "numeric:allergen"

#: 检查类型 → 依据锚点（结论挂对应契约条目）
CHECK_TYPE_CLAUSE = {
    "mandatory_field": CLAUSE_THREE_LEVELS,
    "conditional": CLAUSE_THREE_LEVELS,
    "format": CLAUSE_THREE_LEVELS,
    "ingredient_order": CLAUSE_THREE_LEVELS,
    "claim_whitelist": CLAUSE_THREE_LEVELS,
    "nrv_recalc": CLAUSE_NRV,
    "energy_consistency": CLAUSE_ENERGY,
    "claim_threshold": CLAUSE_CLAIM_THRESHOLD,
    "date_logic": CLAUSE_DATE_LOGIC,
    "nutrition_rows": CLAUSE_NUTRITION_ROWS,
    "allergen_notice": CLAUSE_ALLERGEN,
}

_CACHE: Dict[str, Any] = {}


def _load_json(name: str) -> Any:
    path = os.path.join(DATA_DIR, name)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def ruleset(ruleset_id: str) -> Dict[str, Any]:
    """单个规则集 dict（进程内缓存一次）。"""
    key = "ruleset:" + ruleset_id
    if key not in _CACHE:
        _CACHE[key] = _load_json("%s.json" % ruleset_id)
    return _CACHE[key]


def rulesets() -> Dict[str, Dict[str, Any]]:
    """双标尺规则集 dict（``engine.run_dual`` 的装配入口）。"""
    return {rid: ruleset(rid) for rid in ("gb7718-2011", "gb7718-2025")}


def nutrient_reference() -> numeric.NutrientReference:
    """营养参考表内存视图（数值唯一出处）。"""
    if "reference" not in _CACHE:
        _CACHE["reference"] = numeric.NutrientReference(_load_json("nutrient-reference.json"))
    return _CACHE["reference"]


def rule_check_type(ruleset_id: str, rule_id: str) -> str:
    """规则 id → check_type（结论锚点选择用）。"""
    for rule in ruleset(ruleset_id).get("rules", []):
        if rule.get("id") == rule_id:
            return rule.get("check_type", "")
    return ""


def clause_specs() -> Tuple[Tuple[str, str], ...]:
    """条文库应含的 ``(clause_id, path)``：11 条数据契约条目。"""
    return (
        (CLAUSE_DUAL_RULESETS, "数据契约 / 双标尺规则集"),
        (CLAUSE_THREE_LEVELS, "数据契约 / 三级判定"),
        (CLAUSE_STATS, "数据契约 / 统计口径"),
        (CLAUSE_BASIS_PENDING, "数据契约 / 依据待核对标记"),
        (CLAUSE_GATE, "数据契约 / 类目门控"),
        (CLAUSE_NRV, "数值口径 / NRV% 复算"),
        (CLAUSE_ENERGY, "数值口径 / 能量折算"),
        (CLAUSE_CLAIM_THRESHOLD, "数值口径 / 声称阈值"),
        (CLAUSE_DATE_LOGIC, "数值口径 / 到期日推算"),
        (CLAUSE_NUTRITION_ROWS, "数据契约 / 强制营养行"),
        (CLAUSE_ALLERGEN, "数据契约 / 致敏物质提示"),
    )


def clause_text(clause_id: str) -> str:
    """契约条目正文（数据契约与数值口径，不冒充法规文号）。"""
    if clause_id == CLAUSE_DUAL_RULESETS:
        return ("双标尺：GB 7718-2011（现行，21 条）与 GB 7718-2025（过渡期，26 条）"
                "跑同一标签；规则逐条挂标准号+条款号+条文块出处（status=已核对）")
    if clause_id == CLAUSE_THREE_LEVELS:
        return ("三级判定：合规 / 不合规 / 待人工确认；「标示行存在但解析失败」转"
                "待人工确认而非误判不合规；「没查到问题」与「没检查过」可区分")
    if clause_id == CLAUSE_STATS:
        return ("统计口径：pass + fail + manual == checked == len(findings)；skipped 为"
                "门控未命中跳过数；not_run 为前置缺失未执行数（不产生结论）")
    if clause_id == CLAUSE_BASIS_PENDING:
        return ("依据纪律：basis.status != 已核对 的规则产出结论自动置"
                "flagged_pending_basis（报告与账本同步显示「依据待核对」）")
    if clause_id == CLAUSE_GATE:
        return ("类目隔离门控：only_if 为 None 恒真；否则任一关键词命中卡片平文本即真，"
                "对全部 check_type 生效（含 conditional 豁免分支）")
    if clause_id == CLAUSE_NRV:
        return ("NRV%% 复算：round(amount / NRV × 100)，修约间隔 1（2011 A.2 / 2025 "
                "A.3.2）；行级 |标示-复算| > 1 判不一致；NRV 表挂 GB 28050 附录A")
    if clause_id == CLAUSE_ENERGY:
        return ("能量折算：E = round(17×蛋白 + 37×脂肪 + 17×碳水)（GB 28050-2025 §2.3）；"
                "表2 允许误差只约束低报方向：复算值 > 120% 标示值（+1 kJ 修约容差）判矛盾")
    if clause_id == CLAUSE_CLAIM_THRESHOLD:
        return ("声称阈值（两版表C.1）：无糖 ≤0.5g/100g(mL)、低糖 ≤5、低钠 ≤120mg；"
                "营养成分表缺该行或按份标示时无法复算 → 待人工确认")
    if clause_id == CLAUSE_DATE_LOGIC:
        return ("到期日推算（生成器约定口径，GB 未明文规定）：月单位月加法且日截断到月末、"
                "天单位按天加法；不做 -1 天修正")
    if clause_id == CLAUSE_NUTRITION_ROWS:
        return "强制营养行完整性（GB 28050-2025 §4.1：能量 + 6 项核心营养素）"
    if clause_id == CLAUSE_ALLERGEN:
        return ("致敏物质提示（GB 7718-2025 §4.12 八类）：确定性近似——只检索配料表；"
                "提示行在位 → 通过；含八类关键词而提示缺失 → 不合规；深加工/单一配料"
                "豁免无法自动判定，advice 注明人工复核")
    raise KeyError(clause_id)


__all__ = [
    "PARAMS_VERSION", "CLAUSE_DUAL_RULESETS", "CLAUSE_THREE_LEVELS", "CLAUSE_STATS",
    "CLAUSE_BASIS_PENDING", "CLAUSE_GATE", "CLAUSE_NRV", "CLAUSE_ENERGY",
    "CLAUSE_CLAIM_THRESHOLD", "CLAUSE_DATE_LOGIC", "CLAUSE_NUTRITION_ROWS",
    "CLAUSE_ALLERGEN", "CHECK_TYPE_CLAUSE", "ruleset", "rulesets",
    "nutrient_reference", "rule_check_type", "clause_specs", "clause_text",
]