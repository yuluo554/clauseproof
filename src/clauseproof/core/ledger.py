"""判定账本：clauseproof 的唯一输出模型（契约见 SKELETON-SPEC §3–§6）。

一条账本行 = 一个结论 + 一条条款依据。
「无锚点不下判定」不是文档约定，而是在 :class:`Finding` 构造时就拦下的硬约束。
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

PASS = "pass"
FAIL = "fail"
NOT_APPLICABLE = "not_applicable"
VERDICTS = (PASS, FAIL, NOT_APPLICABLE)
# 会阻断发布/提交的结论（其余结论只记录、不阻断）
BLOCKING_VERDICTS = (FAIL,)

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_INPUT = 2
EXIT_CONTRACT = 3


class ContractError(Exception):
    """契约违约：缺锚点下判定、锚点字段为空、结论取值非法。"""


@dataclass(frozen=True)
class Anchor:
    """条款锚点：可点到条文库里的某一条某版本。

    ``path`` 是给人看的条款路径（如 ``广告法/第九条/第三款``），
    ``clause_id`` 是条文库里的稳定键，``version`` 是条文库版本。
    """

    clause_id: str
    path: str
    version: str
    quote: str = ""

    def __post_init__(self) -> None:
        for name, value in (
            ("clause_id", self.clause_id),
            ("path", self.path),
            ("version", self.version),
        ):
            if value is None or not str(value).strip():
                raise ContractError("条款锚点字段为空：%s" % name)

    def as_dict(self) -> dict:
        return {
            "clause_id": self.clause_id,
            "path": self.path,
            "version": self.version,
            "quote": self.quote,
        }


@dataclass(frozen=True)
class Finding:
    """一条判定。

    ``verdict`` 为 ``pass`` / ``fail`` 时必须带锚点；``not_applicable``
    允许无锚点（依据不足时应当降级为 NA，而不是猜一个结论）。
    """

    rule_id: str
    verdict: str
    message: str
    anchor: Optional[Anchor] = None
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rule_id or not str(self.rule_id).strip():
            raise ContractError("rule_id 为空")
        if self.verdict not in VERDICTS:
            raise ContractError("非法结论：%s（允许 %s）" % (self.verdict, VERDICTS))
        if self.verdict != NOT_APPLICABLE and self.anchor is None:
            raise ContractError(
                "无条款锚点不得下判定（rule=%s, verdict=%s）" % (self.rule_id, self.verdict)
            )

    @property
    def id(self) -> str:
        if self.anchor is None:
            return "%s@na" % self.rule_id
        return "%s@%s" % (self.rule_id, self.anchor.clause_id)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "verdict": self.verdict,
            "message": self.message,
            "basis_ref": self.anchor.as_dict() if self.anchor is not None else None,
            "evidence": dict(self.evidence),
        }

    def as_line(self) -> str:
        where = "%s (%s)" % (self.anchor.path, self.anchor.version) if self.anchor else "无锚点"
        return "[%s] %s — %s :: %s" % (self.verdict, self.rule_id, self.message, where)


@dataclass
class Report:
    """一次判定运行的完整账本。"""

    product: str
    organ: str
    organ_version: str
    subject: str
    findings: Tuple[Finding, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("product", self.product),
            ("organ", self.organ),
            ("organ_version", self.organ_version),
            ("subject", self.subject),
        ):
            if not value or not str(value).strip():
                raise ContractError("账本头字段为空：%s" % name)
        findings = tuple(self.findings)
        dup = _duplicate_ids(findings)
        if dup:
            raise ContractError("账本 id 冲突（同一规则命中同一锚点两次）：%s" % sorted(dup))
        # 确定性排序：同一输入无论器官按什么顺序产出，账本顺序一致
        object.__setattr__(self, "findings", tuple(sorted(findings, key=_sort_key)))

    def blocking(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.verdict in BLOCKING_VERDICTS)

    def summary(self) -> dict:
        counts = {}
        for verdict in VERDICTS:
            counts[verdict] = sum(1 for f in self.findings if f.verdict == verdict)
        return {"blocking": len(self.blocking()), "total": len(self.findings), "verdicts": counts}

    def exit_code(self) -> int:
        return EXIT_BLOCKED if self.blocking() else EXIT_OK

    def as_dict(self) -> dict:
        return {
            "product": self.product,
            "organ": self.organ,
            "organ_version": self.organ_version,
            "subject": self.subject,
            "summary": self.summary(),
            "records": [f.as_dict() for f in self.findings],
        }

    def as_lines(self) -> list:
        lines = [
            "%s :: %s %s :: %s" % (self.product, self.organ, self.organ_version, self.subject)
        ]
        lines.extend(f.as_line() for f in self.findings)
        summary = self.summary()
        lines.append(
            "合计 %d 条，阻断 %d 条（pass=%d fail=%d na=%d）"
            % (
                summary["total"],
                summary["blocking"],
                summary["verdicts"][PASS],
                summary["verdicts"][FAIL],
                summary["verdicts"][NOT_APPLICABLE],
            )
        )
        return lines


def _sort_key(finding: Finding):
    anchor = finding.anchor
    return (
        finding.rule_id,
        finding.verdict,
        anchor.clause_id if anchor is not None else "",
        finding.message,
    )


def _duplicate_ids(findings: Tuple[Finding, ...]):
    seen, dup = set(), set()
    for finding in findings:
        if finding.id in seen:
            dup.add(finding.id)
        seen.add(finding.id)
    return dup