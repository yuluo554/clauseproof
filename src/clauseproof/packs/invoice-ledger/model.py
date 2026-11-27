"""发票参数卡：器官内统一中间表示（迁自来源判定层 ``models/invoice``）。

来源契约：金额一律 Decimal 文本（``str``），比较在判定层用 :class:`decimal.Decimal`
做，杜绝浮点误差；解析不到的字段留空串 + ``field_flags`` 登记，不造默认值。
本器官只收**内存卡**：发票文件解析（XML/PDF/OFD）、编码探测、批次扫描留输入层。
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Tuple

#: 主键三要素：任一缺失即输入不合法（来源解析层同口径）
REQUIRED_FIELDS: Tuple[str, ...] = ("invoice_number", "invoice_type", "issue_date")


class CardError(ValueError):
    """发票卡不合法（主键缺失/字段类型不对）→ 器官入口按输入不合法处理。"""


@dataclass
class Evidence:
    """字段证据：来源文件 + 原文摘录（+ 可选定位）。"""

    source_file: str = ""
    quote: str = ""
    location: str = ""


@dataclass
class LineItem:
    """项目明细行。"""

    name: str = ""
    amount: str = ""
    tax_rate: str = ""
    tax_amount: str = ""


@dataclass
class InvoiceCard:
    """一张发票卡（字段名与来源 ``InvoiceCard`` 同构）。"""

    invoice_number: str
    invoice_type: str
    issue_date: str
    buyer_name: str = ""
    buyer_tax_id: str = ""
    seller_name: str = ""
    seller_tax_id: str = ""
    items: List[LineItem] = field(default_factory=list)
    amount: str = ""
    tax_amount: str = ""
    total_with_tax: str = ""
    total_with_tax_cn: str = ""
    remark: str = ""
    batch_id: str = ""
    confidence: float = 1.0
    field_flags: List[str] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvoiceCard":
        """从内存 dict 重建；主键三要素缺失/为空即拒绝（``CardError``）。

        未知键忽略（向前兼容），``items`` / ``evidence`` 还原为子对象列表。
        """
        if not isinstance(data, dict):
            raise CardError("发票卡必须是 JSON 对象")
        missing = [
            name for name in REQUIRED_FIELDS
            if not str(data.get(name) or "").strip()
        ]
        if missing:
            raise CardError(
                "发票卡缺主键字段：%s（无主键的卡不得进入判定）" % ", ".join(missing)
            )
        known = {name for name in cls.__dataclass_fields__}
        filtered = {key: value for key, value in data.items() if key in known}
        raw_items = filtered.pop("items", []) or []
        raw_evidence = filtered.pop("evidence", []) or []
        if not isinstance(raw_items, list) or not isinstance(raw_evidence, list):
            raise CardError("items / evidence 必须是数组")
        try:
            items = [
                item if isinstance(item, LineItem) else LineItem(**dict(item))
                for item in raw_items
            ]
            evidence = [
                ev if isinstance(ev, Evidence) else Evidence(**dict(ev))
                for ev in raw_evidence
            ]
        except (TypeError, ValueError) as exc:
            raise CardError("items / evidence 结构不合法：%s" % exc) from exc
        for key in ("field_flags",):
            if filtered.get(key) is None:
                filtered[key] = []
        try:
            return cls(items=items, evidence=evidence, **filtered)
        except TypeError as exc:
            raise CardError("发票卡字段类型不合法：%s" % exc) from exc