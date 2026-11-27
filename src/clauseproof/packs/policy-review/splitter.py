"""条款切分（迁自来源 ``splitter``）：标题/正文/列表/附表行 + 原文偏移。

硬约束：``raw_text`` 必须与原文切片逐字节一致；``char_start``/``char_end``
是原文绝对偏移；同输入同输出（零时钟、零随机）。
"""

import hashlib
import re

from .errors import UsageError

HEADING_RULES = (
    (3, re.compile(r"^\s*\d+\.\d+(?:\.\d+)*\s+")),
    (2, re.compile(r"^\s*[（(][一二三四五六七八九十百千零〇0-9]+[）)]")),
    (1, re.compile(r"^\s*第[一二三四五六七八九十百千零〇0-9]+条(?:\s|　|[:：、.．]|$)")),
    (1, re.compile(r"^\s*[一二三四五六七八九十百千]+、")),
    (2, re.compile(r"^\s*\d+[.、)．]\s*")),
)

BULLET_RE = re.compile(r"^\s*(?:[-*•·]|[（(]\d+[）)]|\d+[）)])\s+")
APPENDIX_RE = re.compile(r"\S\s*\|\s*\S")
SHORT_HEADING_MAX = 30
SENTENCE_MARKS = "。！？!?；;，,"


def _heading_match(line):
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return None
    for level, pattern in HEADING_RULES:
        if pattern.match(line):
            return level, stripped
    return None


def _is_short_heading(line, next_line):
    stripped = line.strip()
    if not stripped or len(stripped) > SHORT_HEADING_MAX:
        return False
    if any(mark in stripped for mark in SENTENCE_MARKS):
        return False
    if APPENDIX_RE.search(stripped) or BULLET_RE.match(stripped):
        return False
    return True


def _make_clause(doc_fp, index, start, end, heading_path, kind, raw_text, compound):
    return {
        "clause_id": "c-%s-%04d" % (doc_fp, index),
        "char_start": start,
        "char_end": end,
        "heading_path": list(heading_path),
        "kind": kind,
        "raw_text": raw_text,
        "compound": bool(compound),
        "structural_path": "%04d" % index,
    }


def split_text(text):
    """把单份纯文本切成条款记录（返回 ``{"document": …, "clauses": …}``）。"""
    if not isinstance(text, str):
        raise UsageError("输入必须是字符串")
    if not text.strip():
        raise UsageError("输入文本为空，无法切分")

    doc_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    doc_fp = doc_sha256[:12]
    lines = text.splitlines(keepends=True)
    clauses = []
    heading_stack = []

    para_start = None
    para_end = None
    offset = 0

    def flush_paragraph():
        nonlocal para_start, para_end
        if para_start is None:
            return
        raw = text[para_start:para_end]
        compound = ("；" in raw) or (";" in raw)
        clauses.append(_make_clause(
            doc_fp, len(clauses) + 1, para_start, para_end,
            [title for _, title in heading_stack], "paragraph", raw, compound,
        ))
        para_start = None
        para_end = None

    for index, line in enumerate(lines):
        content = line.rstrip("\r\n")
        line_start = offset
        offset += len(line)

        if not content.strip():
            flush_paragraph()
            continue

        leading = len(content) - len(content.lstrip())
        start = line_start + leading
        end = line_start + len(content.rstrip())

        heading = _heading_match(content)
        if heading is None:
            next_line = lines[index + 1] if index + 1 < len(lines) else ""
            if _is_short_heading(content, next_line):
                heading = (1, content.strip())

        if heading is not None:
            flush_paragraph()
            level, title = heading
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            clauses.append(_make_clause(
                doc_fp, len(clauses) + 1, start, end,
                [item for _, item in heading_stack], "heading",
                text[start:end], False,
            ))
            continue

        kind = "paragraph"
        if BULLET_RE.match(content):
            kind = "list_item"
        elif APPENDIX_RE.search(content):
            kind = "appendix_row"

        if kind != "paragraph":
            flush_paragraph()
            clauses.append(_make_clause(
                doc_fp, len(clauses) + 1, start, end,
                [title for _, title in heading_stack], kind, text[start:end], False,
            ))
            continue

        if para_start is None:
            para_start = start
            para_end = end
        else:
            para_end = end

    flush_paragraph()

    if not clauses:
        raise UsageError("未识别到任何条款，请检查输入文本")

    return {
        "schema_version": "clauses/1",
        "document": {
            "sha256": doc_sha256,
            "char_count": len(text),
            "clause_count": len(clauses),
        },
        "clauses": clauses,
    }


__all__ = ["split_text", "HEADING_RULES", "BULLET_RE", "APPENDIX_RE"]