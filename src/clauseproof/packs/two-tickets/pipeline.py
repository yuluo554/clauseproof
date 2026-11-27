"""装配与输入编译：规则库缓存 + 票面参数卡校验（零文件 IO 在判定内核侧）。

来源的解析层（7 票种文本 → 参数卡、LLM 兜底抽取、编解码清洗）**留输入层**；
本模块只把 subject 里的「已解析卡」编译成内存对象。
"""

from . import registry, rules
from .errors import InputError, RuleError
from .model import (Evidence, FieldValue, OperationStep, SafetyMeasure,
                    TICKET_TYPE_NAMES, TicketCard)

_LIBRARY_CACHE = {}

_TICKET_KEYS = {"ticket_type", "fields", "operation_sequence", "safety_measures", "note"}
_FIELD_KEYS = {"value", "confidence", "evidence"}


def load_library(data_dir=None):
    """装配面：载入随包规则库（按目录缓存）。"""
    key = data_dir or registry.data_dir()
    if key not in _LIBRARY_CACHE:
        _LIBRARY_CACHE[key] = rules.load_library(key)
    return _LIBRARY_CACHE[key]


def reset_cache():
    _LIBRARY_CACHE.clear()


def _evidence(raw, where):
    if raw is None:
        return None
    if not hasattr(raw, "get"):
        raise InputError("%s.evidence 必须是对象 {region, quote}" % where)
    return Evidence(region=str(raw.get("region", "")), quote=str(raw.get("quote", "")))


def _field_value(raw, where):
    if hasattr(raw, "get"):
        unknown = sorted(set(raw) - _FIELD_KEYS)
        if unknown:
            raise InputError("%s 含未知字段：%s" % (where, ", ".join(unknown)))
        if "value" not in raw:
            raise InputError("%s 是对象时必须含 value" % where)
        confidence = raw.get("confidence", 1.0)
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise InputError("%s.confidence 必须是数值" % where)
        return FieldValue(value=raw["value"], confidence=float(confidence),
                          evidence=_evidence(raw.get("evidence"), where))
    return FieldValue(value=raw)


def _sequence(raw):
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise InputError("ticket.operation_sequence 必须是数组")
    steps = []
    for index, item in enumerate(raw, 1):
        if isinstance(item, str):
            steps.append(OperationStep(no=index, action=item))
            continue
        if not hasattr(item, "get"):
            raise InputError("operation_sequence[%d] 必须是对象或字符串" % (index - 1))
        action = item.get("action")
        if not isinstance(action, str) or not action.strip():
            raise InputError("operation_sequence[%d].action 必须是非空字符串" % (index - 1))
        no = item.get("no", index)
        if not isinstance(no, int) or isinstance(no, bool):
            raise InputError("operation_sequence[%d].no 必须是整数" % (index - 1))
        steps.append(OperationStep(no=no, action=action,
                                   evidence=_evidence(item.get("evidence"),
                                                      "operation_sequence[%d]" % (index - 1))))
    return steps


def _measures(raw):
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise InputError("ticket.safety_measures 必须是数组")
    measures = []
    for index, item in enumerate(raw, 1):
        if isinstance(item, str):
            measures.append(SafetyMeasure(no=index, text=item))
            continue
        if not hasattr(item, "get"):
            raise InputError("safety_measures[%d] 必须是对象或字符串" % (index - 1))
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise InputError("safety_measures[%d].text 必须是非空字符串" % (index - 1))
        no = item.get("no", index)
        if not isinstance(no, int) or isinstance(no, bool):
            raise InputError("safety_measures[%d].no 必须是整数" % (index - 1))
        measures.append(SafetyMeasure(no=no, text=text))
    return measures


def build_card(raw):
    """subject.ticket → :class:`TicketCard`（未知字段/票种即输入不合法）。"""
    if not hasattr(raw, "get"):
        raise InputError("ticket 必须是对象")
    unknown = sorted(set(raw) - _TICKET_KEYS)
    if unknown:
        raise InputError("ticket 含未知字段：%s" % ", ".join(unknown))
    ticket_type = raw.get("ticket_type")
    if ticket_type not in TICKET_TYPE_NAMES:
        raise InputError("未知票种：%r（可用：%s）"
                         % (ticket_type, ", ".join(sorted(TICKET_TYPE_NAMES))))
    fields_raw = raw.get("fields")
    if not hasattr(fields_raw, "get"):
        raise InputError("ticket.fields 必须是对象")
    fields = {}
    for name, value in fields_raw.items():
        if not isinstance(name, str) or not name:
            raise InputError("ticket.fields 的键必须是非空字符串")
        fields[name] = _field_value(value, "fields.%s" % name)
    return TicketCard(
        ticket_type=ticket_type,
        fields=fields,
        operation_sequence=_sequence(raw.get("operation_sequence")),
        safety_measures=_measures(raw.get("safety_measures")),
    )


__all__ = ["load_library", "reset_cache", "build_card", "RuleError"]