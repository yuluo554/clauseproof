"""双版本差异对照（迁自来源 ``ruleset.diff``）。

按 ``(industry_id, variant_id)`` 配对，四类差异：
``value_changed`` / ``rate_changed`` / ``added`` / ``removed``；每条挂两版条款号。
两版都登记的行业即使无数值差异也记「已比对」，让"无差异"与"未比对"可区分。
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class DiffItem:
    industry_id: str
    variant_id: Optional[str]
    kind: str
    old_value: Optional[str]
    new_value: Optional[str]
    old_clause: str
    new_clause: str
    old_doc_no: str
    new_doc_no: str

    def as_dict(self) -> dict:
        return {
            "industry_id": self.industry_id,
            "variant_id": self.variant_id,
            "kind": self.kind,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "old_clause": self.old_clause,
            "new_clause": self.new_clause,
            "old_doc_no": self.old_doc_no,
            "new_doc_no": self.new_doc_no,
        }


@dataclass(frozen=True)
class DiffReport:
    old_doc_no: str
    new_doc_no: str
    items: Tuple[DiffItem, ...]
    compared_industries: Tuple[str, ...] = ()

    def counts(self) -> Dict[str, int]:
        out = {}
        for item in self.items:
            out[item.kind] = out.get(item.kind, 0) + 1
        return out

    def as_dict(self) -> dict:
        return {
            "old_doc_no": self.old_doc_no,
            "new_doc_no": self.new_doc_no,
            "counts": self.counts(),
            "compared_industries": list(self.compared_industries),
            "items": [item.as_dict() for item in self.items],
        }


def _index(ruleset: dict) -> Dict[Tuple[str, Optional[str]], dict]:
    index = {}
    for industry in ruleset.get("industries", []):
        industry_id = str(industry.get("industry_id"))
        variants = industry.get("variants") or []
        if not variants:
            index[(industry_id, None)] = dict(industry, _industry_id=industry_id)
        for variant in variants:
            node = dict(variant, _industry_id=industry_id)
            node.setdefault("mechanism", industry.get("mechanism"))
            index[(industry_id, str(variant.get("variant_id")))] = node
    return index


def _metric(node: dict) -> Tuple[Optional[str], Optional[str]]:
    value = node.get("value")
    rate = node.get("rate")
    segments = node.get("segments")
    if segments and value is None and rate is None:
        rate = "|".join(str(segment.get("rate")) for segment in segments)
    return (None if value is None else str(value),
            None if rate is None else str(rate))


def compare(old_ruleset: dict, new_ruleset: dict) -> DiffReport:
    old_index = _index(old_ruleset)
    new_index = _index(new_ruleset)
    old_doc = str(old_ruleset.get("doc_no", ""))
    new_doc = str(new_ruleset.get("doc_no", ""))

    items: List[DiffItem] = []
    for key in sorted(set(old_index) | set(new_index),
                      key=lambda k: (k[0], k[1] or "")):
        industry_id, variant_id = key
        old_node = old_index.get(key)
        new_node = new_index.get(key)
        if old_node is None:
            new_value, new_rate = _metric(new_node)
            items.append(DiffItem(industry_id, variant_id, "added", None,
                                  new_value or new_rate, "",
                                  str(new_node.get("clause", "")), old_doc, new_doc))
            continue
        if new_node is None:
            old_value, old_rate = _metric(old_node)
            items.append(DiffItem(industry_id, variant_id, "removed",
                                  old_value or old_rate, None,
                                  str(old_node.get("clause", "")), "", old_doc, new_doc))
            continue
        old_value, old_rate = _metric(old_node)
        new_value, new_rate = _metric(new_node)
        if old_value != new_value:
            items.append(DiffItem(industry_id, variant_id, "value_changed",
                                  old_value, new_value,
                                  str(old_node.get("clause", "")),
                                  str(new_node.get("clause", "")), old_doc, new_doc))
        if old_rate != new_rate:
            items.append(DiffItem(industry_id, variant_id, "rate_changed",
                                  old_rate, new_rate,
                                  str(old_node.get("clause", "")),
                                  str(new_node.get("clause", "")), old_doc, new_doc))
    compared = tuple(sorted({industry for industry, _ in old_index}
                            & {industry for industry, _ in new_index}))
    return DiffReport(old_doc_no=old_doc, new_doc_no=new_doc, items=tuple(items),
                      compared_industries=compared)


__all__ = ["DiffItem", "DiffReport", "compare"]