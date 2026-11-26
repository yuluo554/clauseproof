"""字段映射与单位别名表快照（**Python 字面量，零文件读取**）。

迁移的是来源产品 ``data/mapping/mapping.json`` 的两个判定面数据节：

- ``unit_aliases`` —— 单位别名表（别名 → 规范单位），由 :mod:`engine` 的
  :func:`engine.resolve_unit` 消费；
- ``parameters[].variants`` / ``ambiguous_variants`` —— 列名变体与歧义列名
  （列名 → 标准参数名），由 :class:`engine.ParamMapping` 语义消费。

纪律：歧义列名命中即判 ``mapping_uncertain``，**绝不猜**；同一变体登记到两个
参数视为配置错误（``MappingError``）。
"""

from typing import Dict, Mapping, Tuple

# ---------------------------------------------------------------------------
# 单位别名表（与来源 mapping.json::unit_aliases 逐条一致）
# ---------------------------------------------------------------------------
UNIT_ALIASES: Mapping[str, Tuple[str, ...]] = {
    "%": ("%", "％", "百分比"),
    "Ah": ("Ah", "ah", "安时"),
    "V": ("V", "v", "伏", "伏特", "volt"),
    "W": ("W", "w", "瓦", "瓦特", "watt"),
    "g": ("g", "G", "克", "gram"),
    "kg": ("kg", "KG", "千克", "公斤", "kilogram"),
    "km": ("km", "KM", "千米", "公里", "kilometer"),
    "km/h": ("km/h", "KM/H", "千米/小时", "公里/小时", "kph"),
    "m": ("m", "M", "米", "meter"),
    "m/s": ("m/s", "米/秒"),
    "‰": ("‰", "千分比", "per mille"),
}

# ---------------------------------------------------------------------------
# 列名映射表（param → (规范单位, 变体, 歧义变体)；与来源逐条一致）
# ---------------------------------------------------------------------------
MAPPING_ENTRIES: Tuple[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]], ...] = (
    ("max_design_speed", "km/h",
     ("最高设计车速", "最高车速", "设计车速", "最大车速", "最高设计速度",
      "设计最高车速", "max_design_speed"), ("车速", "速度")),
    ("vehicle_mass", "kg",
     ("整车质量", "整车重量", "整车整备质量", "车辆质量", "整车净重", "vehicle_mass"),
     ("重量", "质量")),
    ("battery_type", "",
     ("蓄电池类型", "电池类型", "电池种类", "蓄电池种类", "battery_type"), ()),
    ("plastic_mass_ratio", "%",
     ("塑料占比", "塑料质量占比", "塑料总质量占比", "塑料质量比例", "塑料占总质量比例",
      "plastic_mass_ratio"), ("占比", "比例")),
    ("nominal_voltage", "V",
     ("标称电压", "蓄电池标称电压", "电池组标称电压", "电池标称电压", "nominal_voltage"),
     ("电压",)),
    ("motor_rated_power", "W",
     ("电动机额定连续输出功率", "电动机额定功率", "电机额定功率", "额定连续输出功率",
      "电机功率", "电动机功率", "motor_rated_power"), ("功率",)),
    ("over_speed_power_cutoff", "",
     ("超速断电功能", "超速断电", "车速超限断电", "超速保护功能", "over_speed_power_cutoff"),
     ()),
    ("anti_tamper_battery_pack", "",
     ("电池组防篡改", "电池防篡改", "电池组防篡改功能", "防扩展电池接口",
      "anti_tamper_battery_pack"), ()),
    ("anti_tamper_controller", "",
     ("控制器防篡改", "控制器防篡改功能", "防剪线跳线改装", "防多电压兼容",
      "anti_tamper_controller"), ()),
    ("anti_tamper_speed_limiter", "",
     ("限速器防篡改", "限速器防篡改功能", "防限速修改", "anti_tamper_speed_limiter"), ()),
    ("battery_output_voltage", "V",
     ("电池组最大输出电压", "最大输出电压", "电池最大输出电压", "battery_output_voltage"),
     ("输出电压",)),
    ("charger_no_load_output_voltage", "V",
     ("充电器空载输出电压", "空载输出电压", "充电器开路输出电压",
      "charger_no_load_output_voltage"), ()),
    ("charger_rated_input_voltage", "V",
     ("充电器额定输入电压", "额定输入电压", "充电器输入电压",
      "charger_rated_input_voltage"), ()),
    ("charger_protection_function", "",
     ("充电器保护功能", "保护功能", "非正常工作保护", "charger_protection_function"), ()),
)


class MappingError(Exception):
    """映射表不可用或自相矛盾（同一变体映射到两个参数）。"""


class ParamMapping:
    """一份映射表的内存态（加载时一次校验，之后零成本查询）。"""

    def __init__(self, entries: Tuple = MAPPING_ENTRIES) -> None:
        self.variants: Dict[str, str] = {}
        self.ambiguous: Dict[str, list] = {}
        self.units: Dict[str, str] = {}
        self.param_count = 0
        for param, unit, variants, ambiguous in entries:
            if not param:
                raise MappingError("映射表存在缺 param 的条目")
            self.param_count += 1
            if unit:
                self.units[param] = unit
            for variant in variants:
                owner = self.variants.get(variant)
                if owner is not None and owner != param:
                    raise MappingError(
                        "列名变体 %r 同时映射到 %s 与 %s（歧义必须登记进 ambiguous_variants）"
                        % (variant, owner, param))
                self.variants[variant] = param
            for variant in ambiguous:
                self.ambiguous.setdefault(variant, []).append(param)

    def resolve(self, column: str):
        """列名 → ``(判定, 参数名或 None)``。

        顺序：精确变体优先（确定性），其次歧义表；都未命中 → ``unmapped``。
        """
        token = (column or "").strip()
        if not token:
            return "unmapped", None
        owner = self.variants.get(token)
        if owner is not None:
            return "mapped", owner
        if self.ambiguous.get(token):
            return "uncertain", None
        return "unmapped", None

    def target_unit(self, param: str):
        """参数的规范单位（无量纲/枚举参数无单位 → ``None``）。"""
        return self.units.get(param)


def normalize_params(columns: Mapping, table: ParamMapping = None) -> Dict[str, Dict]:
    """把"厂家列名参数表"归一成"标准参数名参数表"。

    - 精确命中 → 以标准参数名收编（单位走别名表归一）；
    - 歧义列名 → 对其全部候选参数注入 ``mapping_uncertain`` 标记（绝不猜）；
    - 未登记列名 → 丢弃（判定层自然落到 ``not_provided(missing)``）。
    """
    if table is None:
        table = ParamMapping()
    out: Dict[str, Dict] = {}
    uncertain = []
    for column in sorted(columns):
        verdict, param = table.resolve(column)
        if verdict == "uncertain":
            uncertain.append(column)
            continue
        if verdict == "unmapped":
            continue
        entry = columns[column]
        if not isinstance(entry, dict):
            entry = {"value": entry}
        item = dict(entry)
        unit = table.target_unit(param)
        if unit and not item.get("unit"):
            item.setdefault("unit", unit)
        out[param] = item
    for column in uncertain:
        for candidate in table.ambiguous.get(column, []):
            if candidate not in out:
                item = {"value": None, "reason": "mapping_uncertain"}
                unit = table.target_unit(candidate)
                if unit:
                    item["unit"] = unit
                out[candidate] = item
    return out


def unit_alias_index() -> Dict[str, str]:
    """``{别名: 规范单位}``（engine.resolve_unit 的默认表）。"""
    index: Dict[str, str] = {}
    for canonical, aliases in UNIT_ALIASES.items():
        for alias in aliases:
            index.setdefault(alias, canonical)
    return index


__all__ = [
    "UNIT_ALIASES", "MAPPING_ENTRIES", "MappingError", "ParamMapping",
    "normalize_params", "unit_alias_index",
]
