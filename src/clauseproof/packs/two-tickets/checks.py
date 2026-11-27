"""check_type 实现（迁自来源 ``rules.checks``；签名 ``(rule, card) -> [Conclusion]``）。

结论纪律（来源既定口径，逐条保留）：

- 字段缺失或值非法 → **待人工确认**，不硬判；
- 任务字段缺失时 ``ticket_type_match`` **跳过**（缺失语义归 ``required_field``，
  防同一缺陷归因双计）；
- ``five_prevention`` 只做操作序列本身可判的形式化初查；序列为空 → 待人工确认；
- 全部判定零时钟、零文件 IO、零 LLM（``datetime.fromisoformat`` 只解析输入值）。
"""

import re
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set, Tuple

from .model import (VERDICT_COMPLIANT, VERDICT_MANUAL, VERDICT_VIOLATION,
                    Conclusion, TicketCard)

# 票面字段中文名（证据文案用；字段键为来源既定口径）
FIELD_LABELS: Dict[str, str] = {
    "ticket_no": "编号",
    "work_unit": "工作单位",
    "work_head": "工作负责人",
    "crew": "工作班成员",
    "location": "工作地点及设备双重名称",
    "task": "工作任务",
    "plan_start": "计划开始工作时间",
    "plan_end": "计划结束工作时间",
    "permit_start": "许可开始工作时间",
    "permitor": "工作许可人",
    "issuer": "工作票签发人",
    "end_time": "工作终结时间",
    "start_time": "操作/抢修开始时间",
    "dispatcher": "发令人",
    "guardian": "监护人",
    "operator": "操作人",
}


def _label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


def _compliant(rule: dict, evidence: Optional[List[str]] = None) -> Conclusion:
    basis = rule.get("basis", {})
    if not evidence:
        evidence = [("%s %s" % (basis.get("standard", ""),
                                basis.get("clause", ""))).strip()]
    return Conclusion(
        rule_id=rule["id"],
        name=rule["name"],
        verdict=VERDICT_COMPLIANT,
        basis=basis,
        evidence=evidence,
        suggestion=rule.get("suggestion", ""),
        check_type=rule.get("check_type", ""),
    )


def _violation(rule: dict, evidence: List[str]) -> Conclusion:
    return Conclusion(
        rule_id=rule["id"],
        name=rule["name"],
        verdict=VERDICT_VIOLATION,
        risk=rule.get("risk"),
        basis=rule.get("basis"),
        evidence=evidence,
        suggestion=rule.get("suggestion", ""),
        check_type=rule.get("check_type", ""),
    )


def _manual(rule: dict, evidence: List[str]) -> Conclusion:
    return Conclusion(
        rule_id=rule["id"],
        name=rule["name"],
        verdict=VERDICT_MANUAL,
        basis=rule.get("basis"),
        evidence=evidence,
        suggestion=rule.get("suggestion", ""),
        check_type=rule.get("check_type", ""),
    )


def check_required_field(rule: dict, card: TicketCard) -> List[Conclusion]:
    fields = rule.get("params", {}).get("fields", [])
    missing = [
        name for name in fields
        if name not in card.fields or not str(card.fields[name].value).strip()
    ]
    if missing:
        return [_violation(rule, ["缺失字段: %s（%s）" % (name, _label(name))
                                  for name in missing])]
    return [_compliant(rule)]


def _parse_iso(value) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def check_time_order(rule: dict, card: TicketCard) -> List[Conclusion]:
    """时间逻辑：``interval``（默认，start<end）/ ``in_window``（target 落区间）。"""
    params = rule.get("params", {})
    if params.get("mode", "interval") == "in_window":
        return _time_in_window(rule, card, params)
    return _time_interval(rule, card, params)


def _time_interval(rule: dict, card: TicketCard, params: dict) -> List[Conclusion]:
    start_field = params.get("start", "start_time")
    end_field = params.get("end", "end_time")
    missing = [name for name in (start_field, end_field) if name not in card.fields]
    if missing:
        return [_manual(rule, ["字段缺失，无法校核: %s" % name for name in missing])]
    start = _parse_iso(card.fields[start_field].value)
    end = _parse_iso(card.fields[end_field].value)
    if start is None or end is None:
        return [_manual(rule, ["时间值无法解析为合法时刻"])]
    if start >= end:
        return [_violation(rule, [
            "%s %s 晚于/等于 %s %s，时间先后逻辑不成立"
            % (_label(start_field), start.isoformat(), _label(end_field), end.isoformat())
        ])]
    return [_compliant(rule)]


def _time_in_window(rule: dict, card: TicketCard, params: dict) -> List[Conclusion]:
    target_field = params.get("target", "permit_start")
    start_field = params.get("start", "plan_start")
    end_field = params.get("end", "plan_end")
    missing = [name for name in (target_field, start_field, end_field)
               if name not in card.fields]
    if missing:
        return [_manual(rule, ["字段缺失，无法校核: %s" % name for name in missing])]
    target = _parse_iso(card.fields[target_field].value)
    start = _parse_iso(card.fields[start_field].value)
    end = _parse_iso(card.fields[end_field].value)
    if target is None or start is None or end is None:
        return [_manual(rule, ["时间值无法解析为合法时刻"])]
    if start <= target <= end:
        return [_compliant(rule)]
    detail = ("%s %s 落在 %s %s 至 %s %s 区间之外"
              % (_label(target_field), target.isoformat(), _label(start_field),
                 start.isoformat(), _label(end_field), end.isoformat()))
    if params.get("on_violation") == "manual":
        return [_manual(rule, [detail + "，超出计划工作时间应办理工作变更/延期手续"])]
    return [_violation(rule, [detail])]


def check_process_signature(rule: dict, card: TicketCard) -> List[Conclusion]:
    """签字链缺环：签发 / 许可 / 终结环节人员留空。"""
    fields = rule.get("params", {}).get("fields", [])
    missing = [
        name for name in fields
        if name not in card.fields or not str(card.fields[name].value).strip()
    ]
    if missing:
        return [_violation(rule, ["签字环节缺失: %s（%s）" % (_label(name), name)
                                  for name in missing])]
    chain = " → ".join(_label(name) for name in fields)
    return [_compliant(rule, evidence=["签字链完整: %s" % chain])]


def check_ticket_type_match(rule: dict, card: TicketCard) -> List[Conclusion]:
    """票种与停电需求匹配：第二种工作票的任务不得含需停电作业表述。"""
    params = rule.get("params", {})
    field = params.get("field", "task")
    field_value = card.fields.get(field)
    if field_value is None or not str(field_value.value).strip():
        # 任务缺失时本项跳过：缺失语义归 required_field，避免同一缺陷归因双计
        return []
    text = str(field_value.value)
    if any(term in text for term in params.get("exempt_terms", [])):
        return [_compliant(rule, evidence=["任务未见停电作业表述: %s" % text])]
    hit = next((term for term in params.get("forbidden_terms", []) if term in text), None)
    if hit:
        return [_violation(rule, [
            "任务含『%s』表述，与本票种适用范围（不需停电）冲突: %s" % (hit, text)
        ])]
    return [_compliant(rule, evidence=["任务未发现与本票种适用范围冲突的表述"])]


def check_measure_coverage(rule: dict, card: TicketCard) -> List[Conclusion]:
    """技术措施四要素覆盖（停电/验电/接地/标示牌遮栏）。"""
    elements: Dict[str, List[str]] = rule.get("params", {}).get("elements", {})
    if not card.safety_measures:
        return [_violation(rule, ["未解析到任何安全措施条目，保证安全的技术措施全部缺失"])]
    missing = [
        name for name, keywords in elements.items()
        if not any(keyword in measure.text
                   for measure in card.safety_measures for keyword in keywords)
    ]
    if missing:
        return [_violation(rule, [
            "安全措施缺少技术措施要素: %s（共 %d 条措施）"
            % ("、".join(missing), len(card.safety_measures))
        ])]
    return [_compliant(rule, evidence=[
        "技术措施要素覆盖齐全: %s（共 %d 条措施）"
        % ("、".join(elements), len(card.safety_measures))
    ])]


# ---------------------------------------------------------------------------
# 五防形式化检查（序列内可形式化判定的三类）
# ---------------------------------------------------------------------------

def _fp_load_disconnector(steps) -> List[str]:
    """防带负荷拉（合）隔离开关：拉开隔离开关前必须已断开断路器。"""
    breaker_opened = False
    issues: List[str] = []
    for step in steps:
        text = step.action
        if "断路器" in text and "断开" in text:
            breaker_opened = True
        if text.startswith("拉开") and "隔离开关" in text and not breaker_opened:
            issues.append(
                "第%d步『%s』：拉开隔离开关前未见断开断路器操作（防带负荷拉（合）隔离开关）"
                % (step.no, text)
            )
    return issues


def _fp_ground_close(steps) -> List[str]:
    """防带接地线（开关）合闸送电：合闸前先前所设接地必须已拆除/拉开。"""
    issues: List[str] = []
    ground_at: Optional[int] = None
    for step in steps:
        text = step.action
        if "接地" in text and ("拆除" in text or "拉开" in text):
            ground_at = None
        elif "接地" in text and ("装设" in text or "挂" in text or "合上" in text):
            ground_at = step.no
        if ground_at is not None and "合上" in text and ("断路器" in text or "隔离开关" in text):
            issues.append(
                "第%d步『%s』：合闸送电前第%d步所设接地线未见拆除（防带接地线（开关）合闸送电）"
                % (step.no, text, ground_at)
            )
            ground_at = None
    return issues


def _fp_grounding_after_test(steps) -> List[str]:
    """防带电挂（合）接地线：装设接地线前（含同一步）应已验电。"""
    issues: List[str] = []
    tested = False
    for step in steps:
        text = step.action
        if "验电" in text:
            tested = True
        if ("装设接地" in text or "挂接地线" in text or "合上接地" in text) and not tested:
            issues.append(
                "第%d步『%s』：装设接地线前未见验电操作（防带电挂（合）接地线（接地开关））"
                % (step.no, text)
            )
            tested = True
    return issues


FIVE_PREVENTION_VARIANTS: Dict[str, Callable] = {
    "no_load_disconnector": _fp_load_disconnector,
    "no_ground_close": _fp_ground_close,
    "grounding_after_test": _fp_grounding_after_test,
}


def check_five_prevention(rule: dict, card: TicketCard) -> List[Conclusion]:
    variants = rule.get("params", {}).get("variants", [])
    if not card.operation_sequence:
        return [_manual(rule, ["操作序列为空，无法进行五防形式化检查"])]
    issues: List[str] = []
    for variant in variants:
        handler = FIVE_PREVENTION_VARIANTS.get(variant)
        if handler:
            issues.extend(handler(card.operation_sequence))
    if issues:
        return [_violation(rule, issues)]
    return [_compliant(rule, evidence=[
        "五防形式化检查通过（共 %d 项操作，覆盖 %d 项防误口径）"
        % (len(card.operation_sequence), len(variants))
    ])]


# ---------------------------------------------------------------------------
# 一致性：设备双重名称 × 电压等级互证
# ---------------------------------------------------------------------------

# 『110kV东湖线111断路器』→（线名, 设备编号, 设备类型）与 kV 标注
_DEVICE_KV_RE = re.compile(
    r"(\d+)kV([一-鿿]{2,8}?线)([0-9\-号杆分段]{1,12}?)(断路器|隔离开关|接地开关)"
)


def check_consistency(rule: dict, card: TicketCard) -> List[Conclusion]:
    params = rule.get("params", {})
    sources = params.get("sources", ["task", "steps"])
    texts: List[str] = []
    if "task" in sources and card.fields.get("task"):
        texts.append(str(card.fields["task"].value))
    if "steps" in sources:
        texts.extend(step.action for step in card.operation_sequence)
    markings: Dict[Tuple[str, str, str], Set[str]] = {}
    for text in texts:
        for kv, line, device, kind in _DEVICE_KV_RE.findall(text):
            markings.setdefault((line, device, kind), set()).add(kv)
    conflicts = sorted(
        "设备%s 电压等级标注不一致: %s kV" % ("".join(identity), "/".join(sorted(kvs)))
        for identity, kvs in markings.items() if len(kvs) > 1
    )
    if conflicts:
        return [_violation(rule, conflicts)]
    if not markings:
        return [_compliant(rule, evidence=[
            "未发现可互证的设备电压等级标注，本项未发现冲突"
        ])]
    return [_compliant(rule, evidence=[
        "设备电压等级标注互证一致（%d 处设备标注）" % len(markings)
    ])]


CHECKS: Dict[str, Callable] = {
    "required_field": check_required_field,
    "time_order": check_time_order,
    "process_signature": check_process_signature,
    "ticket_type_match": check_ticket_type_match,
    "measure_coverage": check_measure_coverage,
    "five_prevention": check_five_prevention,
    "consistency": check_consistency,
}


__all__ = ["FIELD_LABELS", "CHECKS", "FIVE_PREVENTION_VARIANTS",
           "check_required_field", "check_time_order", "check_process_signature",
           "check_ticket_type_match", "check_measure_coverage",
           "check_five_prevention", "check_consistency"]