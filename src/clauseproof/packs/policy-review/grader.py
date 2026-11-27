"""确定性分级器（迁自来源 ``grader``，契约 1.4）。

判定只看三样东西（K4）：

1. 模式包声明的 ``severity_base``；
2. 模式包声明的 ``escalation``（同文档共现条件）；
3. 锚点完整性：``high`` 必须至少有一个可参与分级的硬锚点。

背景锚点（``CIVIL-*`` / ``strength: background``）只进背景段，不支撑 ``high``，
也不进入 finding 的 ``anchor_ids``（K12）。分级不读时钟、不用随机数、不用置信度。

本器官的一处实现扩展（docs §5）：finding 记录**附带 ``pattern_id``**——账本需要
稳定的规则身份；来源 ``findings.json`` 契约（1.4）不含该字段，但本器官不产该文件。
"""

from .constants import (EXCERPT_ELLIPSIS, EXCERPT_MAX_CHARS, GRADABLE_KINDS,
                        HIT_KINDS, LEVEL_RANK)
from .errors import UsageError
from .templates import template_for


def _clause_index(clauses_document):
    if not isinstance(clauses_document, dict):
        raise UsageError("clauses 文档必须是对象")
    clauses = clauses_document.get("clauses")
    if not isinstance(clauses, list):
        raise UsageError("clauses 文档必须包含 clauses 数组")
    index = {}
    for clause in clauses:
        clause_id = clause.get("clause_id")
        if not clause_id:
            raise UsageError("clauses 中存在缺少 clause_id 的记录")
        if clause_id in index:
            raise UsageError("clauses 中 clause_id 重复：%s" % clause_id)
        index[clause_id] = clause
    return index


def _mapping_index(mapping_document):
    if not isinstance(mapping_document, dict):
        raise UsageError("mapping 文档必须是对象")
    mappings = mapping_document.get("mappings")
    if not isinstance(mappings, list):
        raise UsageError("mapping 文档必须包含 mappings 数组")
    index = {}
    for mapping in mappings:
        key = (mapping.get("clause_id"), mapping.get("pattern_id"))
        if key in index:
            raise UsageError("mapping 中 (clause_id, pattern_id) 重复：%s / %s"
                             % (key[0], key[1]))
        index[key] = mapping
    return index


def _document_sha(document):
    meta = document.get("document") or {}
    return meta.get("sha256") if isinstance(meta, dict) else None


def hard_anchor_ids(mapping):
    """只收真正可参与分级的硬锚点（``strength=hard`` 且非 ``CIVIL-*``）。"""
    hard = set()
    for anchor in mapping.get("anchors") or []:
        if not isinstance(anchor, dict):
            continue
        anchor_id = anchor.get("anchor_id")
        if not anchor_id or str(anchor_id).startswith("CIVIL-"):
            continue
        if anchor.get("strength") == "hard":
            hard.add(anchor_id)
    ordered = []
    for anchor_id in mapping.get("anchor_ids") or []:
        if anchor_id in hard and anchor_id not in ordered:
            ordered.append(anchor_id)
    return ordered


def _escalated_level(pattern, document_patterns):
    """按模式包声明的共现条件升级；只在条件满足时取更严重等级。"""
    level = pattern.severity_base
    for rule in pattern.escalation or ():
        required = set()
        single = rule.get("pattern_id")
        if single:
            required.add(single)
        for item in rule.get("pattern_ids") or []:
            required.add(item)
        if not required or not required.issubset(document_patterns):
            continue
        candidate = rule.get("level")
        if candidate in LEVEL_RANK and LEVEL_RANK[candidate] < LEVEL_RANK[level]:
            level = candidate
    return level


def truncate_excerpt(text):
    """展示层截断：超长时保留前 N-1 字符并以 ``…`` 结尾（完整区间不变）。"""
    if len(text) <= EXCERPT_MAX_CHARS:
        return text
    return text[: EXCERPT_MAX_CHARS - 1] + EXCERPT_ELLIPSIS


def grade_hits(hits_document, mapping_document, library, clauses_document):
    """把 hits + mapping 转成 findings 列表（附带 ``pattern_id``）。"""
    if not isinstance(hits_document, dict):
        raise UsageError("hits 文档必须是对象")
    hits = hits_document.get("hits")
    if not isinstance(hits, list):
        raise UsageError("hits 文档必须包含 hits 数组")

    hits_sha = _document_sha(hits_document)
    clauses_sha = _document_sha(clauses_document)
    if hits_sha and clauses_sha and hits_sha != clauses_sha:
        raise UsageError("hits 与 clauses 的文档 sha256 不一致：hits=%s clauses=%s"
                         % (hits_sha, clauses_sha))

    clause_by_id = _clause_index(clauses_document)
    mapping_by_key = _mapping_index(mapping_document)

    document_patterns = set()
    for hit in hits:
        kind = hit.get("kind")
        if kind not in HIT_KINDS:
            raise UsageError("hit 的 kind 非法：%s" % kind)
        if kind in GRADABLE_KINDS:
            document_patterns.add(hit.get("pattern_id"))

    graded = []
    for hit in hits:
        kind = hit.get("kind")
        if kind not in GRADABLE_KINDS:
            # semantic_rejected / uncertain 不进入分级（K9）。
            continue

        clause_id = hit.get("clause_id")
        pattern_id = hit.get("pattern_id")
        pattern = library.pattern(pattern_id)
        if pattern is None:
            raise UsageError("hits 中的 pattern_id 不在当前规则包：%s" % pattern_id)

        mapping = mapping_by_key.get((clause_id, pattern_id))
        if mapping is None:
            raise UsageError("hit 缺少对应 mapping：%s / %s" % (clause_id, pattern_id))
        clause = clause_by_id.get(clause_id)
        if clause is None:
            raise UsageError("hit 的 clause_id 不在 clauses 文档：%s" % clause_id)

        anchor_ids = hard_anchor_ids(mapping)
        level = _escalated_level(pattern, document_patterns)
        if level == "high" and not anchor_ids:
            # 缺硬锚点不得 high；背景锚点不补位（K12 / D12）。
            level = "medium"

        explanation, suggestion = template_for(pattern_id)
        if not explanation.strip() or not suggestion.strip():
            raise UsageError("模式 %s 的说明/修改方向模板为空" % pattern_id)

        finding = {
            "clause_id": clause_id,
            "pattern_id": pattern_id,
            "level": level,
            "char_start": clause["char_start"],
            "char_end": clause["char_end"],
            "excerpt": truncate_excerpt(clause.get("raw_text", "")),
            "explanation": explanation,
            "suggestion": suggestion,
            "anchor_ids": list(anchor_ids),
        }
        graded.append((
            (LEVEL_RANK[level], clause["char_start"], clause_id, pattern_id),
            finding,
        ))

    graded.sort(key=lambda item: item[0])
    return [item[1] for item in graded]


__all__ = ["hard_anchor_ids", "truncate_excerpt", "grade_hits"]