"""票面参数卡与审核结论模型（迁自来源 ``models.card`` / ``models.conclusion``）。

**参数卡是解析层的产物**：票面文本 → 字段-值-置信度-证据（票面区域 + 原文摘录）。
本器官只收这张卡（零文件 IO、零 OCR、零 LLM）；解析与证据抽取留在输入层。

三级结论（来源既定口径）：

- ``合规`` → 账本 ``pass``；
- ``不合规`` → 账本 ``fail``（阻断）；
- ``待人工确认`` → 账本 ``not_applicable``（非结论；含依据待核对降级）。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

TICKET_TYPE_NAMES = {
    "operating": "变电站倒闸操作票",
    "line_operating": "电力线路倒闸操作票",
    "work_first": "变电站（发电厂）第一种工作票",
    "work_second": "变电站（发电厂）第二种工作票",
    "line_work_first": "电力线路第一种工作票",
    "line_work_second": "电力线路第二种工作票",
    "emergency_repair": "事故紧急抢修单",
}

VERDICT_COMPLIANT = "合规"
VERDICT_VIOLATION = "不合规"
VERDICT_MANUAL = "待人工确认"
VERDICTS = (VERDICT_COMPLIANT, VERDICT_VIOLATION, VERDICT_MANUAL)

STATUS_VERIFIED = "已核对"
STATUS_PENDING = "待核对"
BASIS_STATUSES = (STATUS_VERIFIED, STATUS_PENDING)

# 来源 7 类 check_type（规则库 schema 的一部分）
CHECK_TYPES = (
    "required_field",
    "time_order",
    "process_signature",
    "ticket_type_match",
    "measure_coverage",
    "five_prevention",
    "consistency",
)


@dataclass
class Evidence:
    """证据：票面区域 + 原文逐字摘录。"""

    region: str
    quote: str


@dataclass
class FieldValue:
    value: Any
    confidence: float = 1.0
    evidence: Optional[Evidence] = None


@dataclass
class OperationStep:
    no: int
    action: str
    evidence: Optional[Evidence] = None


@dataclass
class SafetyMeasure:
    no: int
    text: str
    evidence: Optional[Evidence] = None


@dataclass
class TicketCard:
    """一张已解析的票面参数卡。"""

    ticket_type: str
    fields: Dict[str, FieldValue] = field(default_factory=dict)
    operation_sequence: List[OperationStep] = field(default_factory=list)
    safety_measures: List[SafetyMeasure] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_type": self.ticket_type,
            "ticket_type_name": TICKET_TYPE_NAMES.get(self.ticket_type, "未知票种"),
            "fields": {
                key: {
                    "value": item.value,
                    "confidence": item.confidence,
                    "evidence": (None if item.evidence is None else
                                 {"region": item.evidence.region,
                                  "quote": item.evidence.quote}),
                }
                for key, item in sorted(self.fields.items())
            },
            "operation_sequence": [
                {"no": step.no, "action": step.action} for step in self.operation_sequence
            ],
            "safety_measures": [
                {"no": measure.no, "text": measure.text}
                for measure in self.safety_measures
            ],
        }


@dataclass
class Conclusion:
    """一条审核结论（rule_id + 三级判定 + 风险 + 依据 + 证据 + 整改建议）。"""

    rule_id: str
    name: str
    verdict: str
    risk: Optional[str] = None
    basis: Optional[Dict[str, Any]] = None
    evidence: List[str] = field(default_factory=list)
    suggestion: str = ""
    downgraded: bool = False
    check_type: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "check_type": self.check_type,
            "verdict": self.verdict,
            "risk": self.risk,
            "basis": dict(self.basis or {}),
            "evidence": list(self.evidence),
            "suggestion": self.suggestion,
            "downgraded": self.downgraded,
        }


__all__ = [
    "TICKET_TYPE_NAMES", "VERDICT_COMPLIANT", "VERDICT_VIOLATION",
    "VERDICT_MANUAL", "VERDICTS", "STATUS_VERIFIED", "STATUS_PENDING",
    "BASIS_STATUSES", "CHECK_TYPES", "Evidence", "FieldValue", "OperationStep",
    "SafetyMeasure", "TicketCard", "Conclusion",
]