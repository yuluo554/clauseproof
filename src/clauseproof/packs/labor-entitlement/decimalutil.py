"""Decimal 口径与 JSON 加载（迁自来源 ``decimalutil``）。

纪律：金额/天数一律 ``Decimal``；JSON 浮点用 ``parse_float=Decimal``，float 绝不
进入计算路径。呈现量化统一两位小数 ``ROUND_HALF_UP``（精度约定，非政策数值）。
"""

import json
from decimal import Decimal, ROUND_HALF_UP

MONEY_QUANTUM = Decimal("0.01")


def to_decimal(value, field="value"):
    """把 str/int/Decimal/float 转 Decimal；bool 与非法类型报错。"""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError("%s: 布尔值不是合法数值" % field)
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("%s: 空字符串不是合法数值" % field)
        return Decimal(text)
    raise TypeError("%s: 不支持的数值类型 %s" % (field, type(value).__name__))


def quantize_money(value):
    """金额呈现口径：两位小数，ROUND_HALF_UP。"""
    return to_decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def load_json_decimal(path):
    """读 JSON，浮点字面量一律解析为 Decimal。"""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle, parse_float=Decimal)


def money_str(value):
    return str(quantize_money(value))


def decimal_default(obj):
    if isinstance(obj, Decimal):
        return money_str(obj)
    raise TypeError("不可序列化类型: %s" % type(obj).__name__)


__all__ = ["MONEY_QUANTUM", "to_decimal", "quantize_money", "load_json_decimal",
           "money_str", "decimal_default"]