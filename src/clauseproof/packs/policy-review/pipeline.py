"""编排层（迁自来源 ``cli.run`` 的判定链）：split → match → map → grade。

来源的 ``match`` / ``map`` / ``report`` / ``run`` 四个命令收敛为一次判定；
产物（clauses/hits/mapping/findings）只在内存中传递，不写盘。
"""

from . import grader, mapping, matcher, registry, rules, splitter

_LIBRARY_CACHE = {}


class Analysis(object):
    """一次隐私政策审查的全部中间结论。"""

    __slots__ = ("clauses", "hits", "mapping", "findings", "library")

    def __init__(self, clauses, hits, mapping_document, findings, library):
        self.clauses = clauses
        self.hits = hits
        self.mapping = mapping_document
        self.findings = findings
        self.library = library

    @property
    def document(self):
        return self.clauses.get("document") or {}

    @property
    def levels(self):
        counts = {"high": 0, "medium": 0, "notice": 0}
        for finding in self.findings:
            counts[finding["level"]] = counts.get(finding["level"], 0) + 1
        return counts

    @property
    def pending_anchor_ids(self):
        out = []
        for entry in self.mapping.get("mappings") or []:
            for anchor_id in entry.get("pending_anchor_ids") or []:
                if anchor_id not in out:
                    out.append(anchor_id)
        return out

    @property
    def background_anchor_ids(self):
        out = []
        for entry in self.mapping.get("mappings") or []:
            for anchor in entry.get("anchors") or []:
                if anchor.get("strength") == "background":
                    anchor_id = anchor.get("anchor_id")
                    if anchor_id not in out:
                        out.append(anchor_id)
        return out


def load_library(data_dir=None):
    """装配面：载入并校验随包规则库（按目录缓存）。"""
    key = data_dir or registry.data_dir()
    if key not in _LIBRARY_CACHE:
        _LIBRARY_CACHE[key] = rules.load_library(key)
    return _LIBRARY_CACHE[key]


def reset_cache():
    _LIBRARY_CACHE.clear()


def run(text, library=None):
    """跑完整判定链（text = 隐私政策/用户协议全文）。"""
    library = library or load_library()
    clauses = splitter.split_text(text)
    hits = matcher.match_document(clauses, library, text)
    mapping_document = mapping.map_hits(hits, library)
    findings = grader.grade_hits(hits, mapping_document, library, clauses)
    return Analysis(clauses, hits, mapping_document, findings, library)


__all__ = ["Analysis", "load_library", "reset_cache", "run"]