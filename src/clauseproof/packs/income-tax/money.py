"""金额口径与依据引用的公共约定（移植判定层，见 SKELETON-SPEC §3–§5）。

三件事原样保留：

- **金额 = 两位小数 ROUND_HALF_UP**：申报表精度约定（不是政策数值）。真值库
  「商数查表保留两位」口径同源——商数只用于定档，税基仍是奖金全额；
- **ref 节点 → 文号全称**：ref 存规则包原始节点 ``{"source": "S61", "clause": "第六条"}``，
  ``source_doc`` 把 source id 解析为 sources[] 里的文号全称（找不到原样返回 id）；
- **短引用**：``S61·第六条``（账本行内紧凑引用；完整文号由来源图例给出）。

**不搬**：整行排版（表格宽度、标题、依据图例、免责声明）——器官不输出排版。
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List

MONEY_QUANT = Decimal("0.01")


def money(value) -> Decimal:
    """金额按申报口径保留两位小数（ROUND_HALF_UP）。"""
    return Decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def source_doc(source_id: str, sources: List[Dict[str, Any]]) -> str:
    """ref 节点里的 source id → sources[] 里的文号全称；找不到原样返回 id。"""
    for src in sources:
        if src.get("id") == source_id:
            return str(src.get("doc", source_id))
    return source_id


def render_ref(ref_node: Any, sources: List[Dict[str, Any]]) -> str:
    """ref 节点 → "文号 条款"（依据面板可直接读）。"""
    if not isinstance(ref_node, dict):
        return str(ref_node)
    doc = source_doc(str(ref_node.get("source", "")), sources)
    clause = str(ref_node.get("clause", ""))
    return f"{doc} {clause}".strip()


def short_ref(ref_node: Any) -> str:
    """ref 节点 → "S61·第六条"（账本行内紧凑引用）。"""
    if not isinstance(ref_node, dict):
        return str(ref_node)
    source_id = str(ref_node.get("source", ""))
    clause = str(ref_node.get("clause", ""))
    return f"{source_id}·{clause}".strip("·")