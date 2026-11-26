"""参数包快照（**Python 字面量，零文件读取**）。

迁移的是来源产品随包冻结的参数包 ``rules/params.json``：10 条净料率条目、1 条目标
毛利率、1 条波动预警阈值。三条纪律原样保留：

1. **业务数值只在参数包**：本模块是器官内唯一的业务数值定义点；``engine.py`` 只出现
   数学定义域的端点（``0`` / ``1``），不出现任何口径数值。
2. **每个条目必须挂来源**：``builtin_experience`` / ``user`` / ``snapshot`` 三选一。
   净料率全部是**内置经验默认值（非官方数据）**——来源仓 `data/README.md` 实测
   「《餐饮业成本核算规范》SB/T 10573」查证失败（检索 43 条无成本核算类标准），
   故**不引用、不编造文号**；本器官据此把依据锚点登记为**参数包条目**，不冒充法规条文。
3. **状态三态**：``verified`` 放行 / ``pending`` 阻断该作用域 / ``input_required``
   放行门控但运行期必索。随包 12 条目**全部 verified**（与来源参数包一致）。

``data/params.json`` 仍逐字保存来源资产作为可复核出处，随 wheel 进包，并由
``tests/test_cost_card.py`` 的「漂移门」逐条比对（手改任一侧即红）。
"""

from typing import Any, Dict, Mapping, Tuple

from .engine import PARAM_VERIFIED, make_source

#: 参数包快照版本（= 条文库坐标）。来源仓 ``data/README.md`` 标注基准日 2026-10-14
#: （M0 数据底座复核于 2026-10-15）。参数或快照口径变化时此值必须同步。
PARAMS_VERSION = "2026-10-14"

#: 依据锚点 id（条文库必须具备的全部条目；缺一即 ``BasisMissing`` → 退出码 3）
CLAUSE_SECTION_YIELD = "param:yield-rate"
CLAUSE_SECTION_PRICING = "param:target-margin"
CLAUSE_SECTION_ALERT = "param:alert-threshold"
CLAUSE_IMPORT_MAP = "import:column-map"

#: 净料率条目（顺序 = 来源参数包声明序）
YIELD_RATE_ENTRIES: Tuple[Tuple[str, str, str], ...] = (
    ("土豆", "0.90", "块茎类去皮后的出成率经验值（内置经验默认值，非官方数据；用户可覆盖）"),
    ("大白菜", "0.85", "叶菜类去外叶与根部后的出成率经验值（内置经验默认值，非官方数据；用户可覆盖）"),
    ("娃娃菜", "0.88", "叶菜类去外叶后的出成率经验值（内置经验默认值，非官方数据；用户可覆盖）"),
    ("小白菜", "0.80", "叶菜类去根去黄叶后的出成率经验值（内置经验默认值，非官方数据；用户可覆盖）"),
    ("洋葱", "0.88", "鳞茎类去外皮后的出成率经验值（内置经验默认值，非官方数据；用户可覆盖）"),
    ("牛肉", "0.92", "去筋膜与修整后的出成率经验值（内置经验默认值，非官方数据；用户可覆盖）"),
    ("猪肉", "0.95", "去包装与筋膜后的出成率经验值（内置经验默认值，非官方数据；用户可覆盖）"),
    ("胡萝卜", "0.85", "根茎类去皮去头尾后的出成率经验值（内置经验默认值，非官方数据；用户可覆盖）"),
    ("草鱼", "0.55", "活鱼去鳞去内脏去头后的出成率经验值（内置经验默认值，非官方数据；用户可覆盖）"),
    ("鸡蛋", "0.90", "带壳蛋去壳后的可食部分经验值（内置经验默认值，非官方数据；用户可覆盖）"),
)

#: 来源仓参数包里的 ``source.ref``（参数体系说明章节）
SOURCE_REF = "参数体系说明#参数体系"


def _entry(value: str, kind: str, note: str) -> Dict[str, Any]:
    return {
        "value": value,
        "status": PARAM_VERIFIED,
        "source": make_source(kind, SOURCE_REF, note=note),
    }


#: 参数包（结构与来源 ``params.json`` 的三分区一致）
PARAMS: Mapping[str, Dict[str, Dict[str, Any]]] = {
    "yield_rates": {
        name: _entry(value, "builtin_experience", note)
        for name, value, note in YIELD_RATE_ENTRIES
    },
    "pricing": {
        "target_margin": _entry(
            "0.60", "user", "示例值（非官方），用户须按自身经营情况配置"),
    },
    "alert": {
        "threshold": _entry(
            "0.10", "user", "示例阈值（非官方），用户可配置"),
    },
}


def clause_specs() -> Tuple[Tuple[str, str], ...]:
    """条文库应含的 ``(clause_id, path)``：章节锚点 + 逐食材净料率条目 + 进货单列名契约。"""
    specs = [
        (CLAUSE_SECTION_YIELD, "参数包 / 净料率"),
        (CLAUSE_SECTION_PRICING, "参数包 / 目标毛利率"),
        (CLAUSE_SECTION_ALERT, "参数包 / 波动预警阈值"),
        (CLAUSE_IMPORT_MAP, "进货单 / 列名白名单"),
    ]
    specs.extend(
        ("param:yield-rate:%s" % name, "参数包 / 净料率 / %s" % name)
        for name, _value, _note in YIELD_RATE_ENTRIES
    )
    return tuple(specs)


def clause_text(clause_id: str) -> str:
    """条款正文：参数条目用它自己的来源说明（**不编造法规名称与文号**）。"""
    for name, _value, note in YIELD_RATE_ENTRIES:
        if clause_id == "param:yield-rate:%s" % name:
            return "%s（来源类型：内置经验值，非官方数据）" % note
    if clause_id == CLAUSE_SECTION_YIELD:
        return "净料率条目清单：%s（全部为内置经验默认值，非官方数据）" % "、".join(
            name for name, _value, _note in YIELD_RATE_ENTRIES)
    if clause_id == CLAUSE_SECTION_PRICING:
        return "目标毛利率：用户配置项（示例值，非官方），由经营主体自行设定"
    if clause_id == CLAUSE_SECTION_ALERT:
        return "价格波动预警阈值：用户配置项（示例阈值，非官方），预警不等于判定"
    if clause_id == CLAUSE_IMPORT_MAP:
        return ("已登记列名：日期、品名、类别、数量、单位、单价、金额；"
                "必填列：品名、数量、单价；未登记列名记 unknown（不猜）")
    raise KeyError(clause_id)


__all__ = [
    "PARAMS_VERSION", "PARAMS", "YIELD_RATE_ENTRIES", "SOURCE_REF",
    "CLAUSE_SECTION_YIELD", "CLAUSE_SECTION_PRICING", "CLAUSE_SECTION_ALERT",
    "CLAUSE_IMPORT_MAP", "clause_specs", "clause_text",
]