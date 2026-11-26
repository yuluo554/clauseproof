"""极限用语扫描内核（**零 I/O / 零时钟 / 零环境变量 / 零 LLM**）。

迁移的是来源产品的确定性扫描面：词条门控（status + 锚点 + literal 词面自证）、
前缀树编译、左→右长词优先非重叠匹配、命中位置与上下文。

三条确定性纪律原样保留：

1. **同输入 → 同命中集合与同位置**（无随机、无时间、无环境依赖）；
2. **位置可逐字回定位**（行号/列号 1 起、按 Unicode 码点；CRLF/CR 归一为 LF 后计数）；
3. **`suggestion` 只来自词表内置字段**，不做自由生成（生成属产品层/LLM 面，不迁）。

词面**只能来自** :mod:`registry`；本模块只吃编译好的词条，不含任何词条字面量。

本模块不读文件：``scan`` 收**已解码文本**（str）。文件读取、编码判定、stdout 排版属输入层，
见 ``docs/extreme-terms.md`` §5。
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import registry


class InputError(ValueError):
    """输入不合法（文本缺失 / 窗口非法）。内核映射退出码 2。"""


# ------------------------------------------------------------------ 文本归一
def normalize_text(raw: Any) -> str:
    """剥离 UTF-8 BOM、归一换行（CRLF/CR → LF）。"""
    if not isinstance(raw, str):
        raise InputError("输入文本必须是字符串，得到 %s" % type(raw).__name__)
    text = raw[1:] if raw.startswith("\ufeff") else raw
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ------------------------------------------------------------------ 词条门控
def load_entries(basis: Any,
                 words: Optional[Sequence[Mapping]] = None) -> Dict[str, Any]:
    """词条门控：返回 ``{"active": [...], "inactive": [{word, reason}]}``。

    门控四步（顺序与来源仓一致）：状态 → 锚点字段 → 条款在条文库 → literal 词面自证。
    **被拒条目必须显式列出**（未启用清单），绝不静默按最宽松规则扫。
    """
    source = registry.words() if words is None else words
    active, inactive = [], []
    for entry in source:
        if entry.get("status") != registry.STATUS_VERIFIED:
            inactive.append({"word": entry.get("word"), "reason": "status 非 verified"})
            continue
        clause_id = entry.get("clause_id")
        if not clause_id:
            inactive.append({"word": entry.get("word"), "reason": "缺锚点"})
            continue
        clause = basis.clause(clause_id)
        if clause is None:
            inactive.append({"word": entry.get("word"),
                             "reason": "锚点条款不在条文库（%s）" % clause_id})
            continue
        basis_kind = entry.get("basis")
        if basis_kind not in registry.ANCHOR_BASES:
            inactive.append({"word": entry.get("word"),
                             "reason": "锚点依据类型未登记（%r）" % (basis_kind,)})
            continue
        if basis_kind == "literal" and entry.get("word") not in (clause.text or ""):
            inactive.append({"word": entry.get("word"),
                             "reason": "literal 词面未见于条款原文（%s）" % clause_id})
            continue
        active.append({
            "word": entry["word"],
            "category": entry["category"],
            "risk": entry["risk"],
            "suggestion": entry["suggestion"],
            "clause_id": clause_id,
        })
    return {"active": active, "inactive": inactive}


# ------------------------------------------------------------------ 扫描
def build_dfa(entries: Sequence[Mapping]) -> Tuple[Dict[str, Any], List[Any]]:
    """把生效词条编译成前缀树；终止节点存该词面下的全部（类别, 风险, 建议）项。"""
    root = ({}, [])
    for entry in entries:
        node = root
        for char in entry["word"]:
            children = node[0]
            nxt = children.get(char)
            if nxt is None:
                nxt = ({}, [])
                children[char] = nxt
            node = nxt
        node[1].append((entry["word"], entry["category"], entry["risk"], entry["suggestion"]))
    return root


def make_hit(entry: Mapping, line: str, col0: int, line_no: int,
             window: int = registry.CONTEXT_WINDOW) -> Dict[str, Any]:
    """构造一条命中（字段序固定：word, category, risk, line, col, context, suggestion）。"""
    start = max(0, col0 - window)
    end = min(len(line), col0 + len(entry["word"]) + window)
    return {
        "word": entry["word"],
        "category": entry["category"],
        "risk": entry["risk"],
        "line": line_no,
        "col": col0 + 1,
        "context": line[start:end],
        "suggestion": entry["suggestion"],
    }


def scan_line(line: str, trie: Any, line_no: int,
              window: int = registry.CONTEXT_WINDOW) -> List[Dict[str, Any]]:
    """单行扫描：左→右、长词优先、非重叠。"""
    hits = []
    pos = 0
    length = len(line)
    while pos < length:
        children = trie[0]
        depth = 0
        last = None
        while True:
            nxt = children.get(line[pos + depth]) if pos + depth < length else None
            if nxt is None:
                break
            depth += 1
            if nxt[1]:
                last = nxt
            children = nxt[0]
        if last is None:
            pos += 1
            continue
        seen = set()
        for word, category, risk, suggestion in last[1]:
            key = (word, category)
            if key in seen:
                continue
            seen.add(key)
            hits.append(make_hit({"word": word, "category": category, "risk": risk,
                                  "suggestion": suggestion}, line, pos, line_no, window))
        pos += len(last[1][0][0])
    return hits


def scan_text(text: str, entries: Sequence[Mapping],
              window: int = registry.CONTEXT_WINDOW) -> List[Dict[str, Any]]:
    """确定性扫描（排序 = 扫描序，最终按 (line, col, category, word) 稳定排序）。"""
    if window < 0:
        raise InputError("context_window 必须为非负整数")
    trie = build_dfa(entries)
    hits = []
    for line_no, line in enumerate(str(text).split("\n"), start=1):
        hits.extend(scan_line(line, trie, line_no, window))
    hits.sort(key=lambda hit: (hit["line"], hit["col"], hit["category"], hit["word"]))
    return hits


# ------------------------------------------------------------------ 输入
def validate_subject(subject: Any) -> Mapping:
    """输入结构校验：``{"text": str, "context_window": int?}``。"""
    if not isinstance(subject, Mapping):
        raise InputError("输入必须是 JSON 对象，得到 %s" % type(subject).__name__)
    if "text" not in subject:
        raise InputError("缺少 text（待扫描文案）")
    if not isinstance(subject["text"], str):
        raise InputError("text 必须是字符串")
    window = subject.get("context_window")
    if window is not None and (isinstance(window, bool) or not isinstance(window, int)
                                or window < 0):
        raise InputError("context_window 必须为非负整数")
    return subject


def run_scan(subject: Mapping,
             words: Optional[Sequence[Mapping]] = None,
             basis: Optional[Any] = None) -> Dict[str, Any]:
    """端到端扫描（门控 → 归一 → 扫描）。"""
    validate_subject(subject)
    if basis is None:
        raise InputError("缺少条文库（词条门控需要条款原文）")
    gated = load_entries(basis, words)
    text = normalize_text(subject["text"])
    window = subject.get("context_window")
    window = registry.CONTEXT_WINDOW if window is None else window
    hits = scan_text(text, gated["active"], window)
    return {
        "text": text,
        "hits": hits,
        "active": gated["active"],
        "inactive": gated["inactive"],
    }


__all__ = [
    "InputError", "normalize_text", "load_entries", "build_dfa", "make_hit",
    "scan_line", "scan_text", "validate_subject", "run_scan",
]