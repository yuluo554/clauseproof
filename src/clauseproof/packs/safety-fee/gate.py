"""status 门控（迁自来源 ``rules.gate``）：**按计算路径分作用域**。

``calc``（计提标准）/ ``check``（支出范围）/ ``progress``（进度门槛）三者互不误伤：
算某行业时不被无关行业的 pending 拖累。

**第三态 ``input_required``** 表示"本不由规则包承载、须运行时索取的外部输入"
——不阻断门控，但运行时必索，缺失即退出码 2，**绝不静默取 0/1**。
"""

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from .errors import ConfigError

SCOPES = ("calc", "check", "progress")
NON_BLOCKING = frozenset({"verified", "input_required"})


@dataclass(frozen=True)
class GateBlocker:
    path: str
    clause: str
    status: str
    reason: str


@dataclass(frozen=True)
class GateResult:
    scope: str
    ok: bool
    blockers: Tuple[GateBlocker, ...]

    def as_dict(self) -> dict:
        return {"scope": self.scope, "ok": self.ok,
                "blockers": [{"path": blocker.path, "clause": blocker.clause,
                              "status": blocker.status, "reason": blocker.reason}
                             for blocker in self.blockers]}


def _iter_statused(node, path: str) -> Iterable[Tuple[str, str, str, str]]:
    if isinstance(node, dict):
        if "status" in node:
            yield (path, str(node.get("clause", "")), str(node["status"]),
                   str(node.get("reason", "未挂原文核对")))
            return
        for key, value in node.items():
            yield from _iter_statused(value, "%s.%s" % (path, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _iter_statused(value, "%s[%d]" % (path, index))


def collect_blockers(payload, scope: str, root: str) -> Tuple[GateBlocker, ...]:
    blockers = []
    for path, clause, status, reason in _iter_statused(payload, root):
        if status in NON_BLOCKING:
            continue
        blockers.append(GateBlocker(path=path, clause=clause, status=status,
                                    reason=reason))
    return tuple(blockers)


def _calc_blockers(ruleset: dict, industry_id: Optional[str] = None):
    blockers = []
    if "mechanisms" in ruleset:
        blockers.extend(collect_blockers(ruleset["mechanisms"], "calc", "mechanisms"))
    for index, industry in enumerate(ruleset.get("industries", [])):
        if industry.get("implementation") == "deferred":
            continue
        if industry_id is not None and industry.get("industry_id") != industry_id:
            continue
        blockers.extend(collect_blockers(industry, "calc", "industries[%d]" % index))
    return tuple(blockers)


def check_scope(ruleset: dict, scope: str, *, spending: dict = None,
                progress: dict = None, industry_id: Optional[str] = None) -> GateResult:
    if scope not in SCOPES:
        raise ConfigError("未知门控作用域：%r（支持 %s）" % (scope, ", ".join(SCOPES)))
    blockers = ()
    if scope == "calc":
        blockers = _calc_blockers(ruleset, industry_id)
    elif scope == "check":
        if spending is None:
            raise ConfigError("作用域 check 需提供 spending 规则")
        blockers = collect_blockers(spending.get("entries", []), scope, "entries")
    elif scope == "progress":
        if progress is None:
            raise ConfigError("作用域 progress 需提供 progress 规则")
        blockers = collect_blockers(progress.get("thresholds", []), scope, "thresholds")
    return GateResult(scope=scope, ok=not blockers, blockers=tuple(blockers))


__all__ = ["SCOPES", "NON_BLOCKING", "GateBlocker", "GateResult",
           "collect_blockers", "check_scope"]