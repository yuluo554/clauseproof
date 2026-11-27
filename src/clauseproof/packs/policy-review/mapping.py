"""锚点映射（迁自来源 ``mapping``，契约 1.3）：只查表 + 校验锚点完整性。

- ``anchor_ids`` 只含可参与分级的硬锚点（``status=verified`` 且三件套齐全）；
- ``pending_anchor_ids`` 收留缺失 / 未核的硬锚点；
- 背景锚点（``CIVIL-*``）进 ``anchors``，标 ``strength: background``，
  不进 ``anchor_ids``、不参与分级（K12）。
"""

from .constants import BACKGROUND_PREFIX
from .errors import UsageError


def _background_record(anchor_id):
    statute_id, separator, article = anchor_id.partition("-")
    return {
        "anchor_id": anchor_id,
        "statute_id": statute_id if separator else "",
        "article": article if separator else "",
        "anchor_text": "",
        "source_url": "",
        "verified_on": "",
        "strength": "background",
    }


def _hard_record(anchor):
    return {
        "anchor_id": anchor["anchor_id"],
        "statute_id": anchor["statute_id"],
        "article": anchor["article"],
        "anchor_text": anchor["anchor_text"],
        "source_url": anchor["source_url"],
        "verified_on": anchor["verified_on"],
        "strength": "hard",
    }


def map_hits(hits_document, library):
    """把 hits 文档映射为 mapping 文档。"""
    mappings = []
    for hit in hits_document.get("hits") or []:
        pattern = library.pattern(hit.get("pattern_id"))
        if pattern is None:
            raise UsageError("hits 中的 pattern_id 不在当前规则包：%s"
                             % hit.get("pattern_id"))

        anchor_ids = []
        pending = []
        anchors = []
        for anchor_id in pattern.statute_anchors:
            anchor = library.anchor(anchor_id)
            if anchor is None or not anchor.get("eligible"):
                pending.append(anchor_id)
                continue
            anchor_ids.append(anchor_id)
            anchors.append(_hard_record(anchor))
        for anchor_id in pattern.background_anchors:
            if not str(anchor_id).startswith(BACKGROUND_PREFIX):
                raise UsageError("背景锚点前缀非法：%s" % anchor_id)
            anchors.append(_background_record(anchor_id))

        mappings.append({
            "clause_id": hit.get("clause_id"),
            "pattern_id": pattern.pattern_id,
            "anchor_ids": anchor_ids,
            "anchors": anchors,
            "pending_anchor_ids": pending,
        })

    return {
        "schema_version": "mapping/1",
        "ruleset_version": library.ruleset_version,
        "document": dict(hits_document.get("document") or {}),
        "mappings": mappings,
    }


__all__ = ["map_hits"]