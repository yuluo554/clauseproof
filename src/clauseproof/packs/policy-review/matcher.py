"""确定性匹配引擎（迁自来源 ``matcher``）。

语义（K4 冻结口径）：

- 只扫描非 heading 条款；标题是结构信息，不作为义务句判定对象；
- 每条 trigger 正则命中后，若同一条款内任一 negation / neutralizer 命中，
  整条 (clause, pattern) 命中被抑制；
- 偏移一律回写原文（K1）：``text[char_start:char_end] == matched_text``；
- 零时钟、零随机、零网络：规则顺序 + 文档顺序即可复现。
"""

from .normalize import build_shadow
from .splitter import split_text


def _feature_hits(feature, shadow, clause, text):
    base = clause["char_start"]
    hits = []
    for match in feature.regex.finditer(shadow.text):
        if match.start() == match.end():
            continue
        local_start, local_end = shadow.to_original_span(match.start(), match.end())
        start = base + local_start
        end = base + local_end
        if text is not None:
            matched_text = text[start:end]
        else:
            matched_text = clause["raw_text"][local_start:local_end]
        hits.append({
            "feature_id": feature.feature_id,
            "matched_text": matched_text,
            "char_start": start,
            "char_end": end,
        })
    return hits


def _dedupe_feature_hits(feature_hits):
    seen = set()
    out = []
    for hit in feature_hits:
        key = (hit["feature_id"], hit["char_start"], hit["char_end"])
        if key in seen:
            continue
        seen.add(key)
        out.append(hit)
    return out


def _pattern_hits_in_clause(pattern, clause, text):
    raw = clause["raw_text"]
    shadow = build_shadow(raw)
    feature_hits = []
    for feature in pattern.trigger_features:
        feature_hits.extend(_feature_hits(feature, shadow, clause, text))
    feature_hits = _dedupe_feature_hits(feature_hits)
    if not feature_hits:
        return None

    for rule in pattern.negation:
        if rule.regex.search(shadow.text):
            return None
    for rule in pattern.neutralizers:
        if rule.regex.search(shadow.text):
            return None

    feature_hits.sort(key=lambda item: (item["char_start"], item["char_end"],
                                        item["feature_id"]))
    return {
        "clause_id": clause["clause_id"],
        "pattern_id": pattern.pattern_id,
        "kind": "deterministic",
        "trigger_features": feature_hits,
        "needs_semantic": pattern.needs_semantic,
    }


def match_document(document, library, text=None):
    """对 clauses 文档跑匹配；返回 hits 文档（原文绝对偏移）。"""
    clauses = document.get("clauses") or []
    if text is not None and not isinstance(text, str):
        raise ValueError("text 必须是字符串或 None")

    hits = []
    for clause in clauses:
        if clause.get("kind") == "heading":
            continue
        if text is not None:
            expected = text[clause["char_start"]:clause["char_end"]]
            if expected != clause.get("raw_text"):
                raise ValueError("条款记录与原文不一致：%s 的 raw_text 不是原文切片"
                                 % clause.get("clause_id"))
        for pattern in library.patterns:
            hit = _pattern_hits_in_clause(pattern, clause, text)
            if hit is not None:
                hits.append(hit)

    return {
        "schema_version": "hits/1",
        "ruleset_version": library.ruleset_version,
        "document": dict(document.get("document") or {}),
        "hits": hits,
    }


def match_text(text, library):
    """切分 + 匹配的一步入口。"""
    document = split_text(text)
    return match_document(document, library, text)


__all__ = ["match_document", "match_text"]