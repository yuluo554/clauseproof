"""JSON 读取（浮点字面量 → Decimal，避免二进制尾差进入判定）。"""

import json
from decimal import Decimal


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle, parse_float=Decimal)


__all__ = ["load_json"]