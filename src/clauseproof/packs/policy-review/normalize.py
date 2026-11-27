"""影子串归一化与原文偏移映射（迁自来源 ``normalize``，K1 口径不变）。

原文永不改写；归一化只作用于影子串：

- 全角 ASCII 字母/数字/常见符号 → 半角（中文句读标点保留）；
- 连续 Unicode 空白折叠为一个半角空格；
- ASCII 大写字母 → 小写。

影子串每个字符记录它在原文中的左闭右开区间；命中区间必须经
``Shadow.to_original_span`` 回写原文，禁止把影子串下标当原文偏移。
"""

import unicodedata

_FULLWIDTH_BASE = 0xFF01
_ASCII_BASE = 0x21

_PRESERVE_FULLWIDTH = frozenset(
    ["\uff0c", "\uff1b", "\uff1a", "\uff01", "\uff1f"]
)


class Shadow(object):
    """影子串及其到原文的偏移映射。"""

    __slots__ = ("text", "starts", "ends")

    def __init__(self, text, starts, ends):
        self.text = text
        self.starts = starts
        self.ends = ends

    def __len__(self):
        return len(self.text)

    def to_original_span(self, start, end):
        if start < 0 or end > len(self.text) or start >= end:
            raise ValueError("影子串区间非法：%d:%d" % (start, end))
        return self.starts[start], self.ends[end - 1]


def _fold_char(ch):
    code = ord(ch)
    if _FULLWIDTH_BASE <= code <= 0xFF5E and ch not in _PRESERVE_FULLWIDTH:
        ch = chr(code - _FULLWIDTH_BASE + _ASCII_BASE)
    if "A" <= ch <= "Z":
        ch = ch.lower()
    return ch


def build_shadow(text):
    """构造影子串与偏移映射（连续空白折叠为一个空格，映射覆盖整段空白）。"""
    chars = []
    starts = []
    ends = []

    index = 0
    length = len(text)
    while index < length:
        ch = text[index]
        if ch.isspace():
            run_start = index
            while index < length and text[index].isspace():
                index += 1
            chars.append(" ")
            starts.append(run_start)
            ends.append(index)
            continue

        chars.append(_fold_char(ch))
        starts.append(index)
        ends.append(index + 1)
        index += 1

    return Shadow("".join(chars), starts, ends)


def shadow_text(text):
    return build_shadow(text).text


def is_combining(ch):
    return unicodedata.combining(ch) != 0


__all__ = ["Shadow", "build_shadow", "shadow_text", "is_combining"]