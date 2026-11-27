"""原因码与异常（迁自来源 ``errors``；边界映射见 ``__init__.evaluate``）。"""

EXIT_OK = 0
EXIT_NONCOMPLIANT = 1
EXIT_USAGE = 2
EXIT_MISSING_DEPENDENCY = 3

REASON_READ_ERROR = "read_error"
REASON_BAD_JSON = "bad_json"
REASON_SCHEMA_INVALID = "schema_invalid"
REASON_UNKNOWN_FACTOR = "unknown_factor"
REASON_UNKNOWN_EXAM_TYPE = "unknown_exam_type"
REASON_CONTAINER_TOO_LARGE = "container_too_large"
REASON_GATE_BLOCKED = "gate_blocked"
REASON_MISSING_INPUT = "missing_input"
REASON_UNMAPPED_ITEM = "unmapped_item"

UNJUDGED_REASONS = frozenset({
    REASON_READ_ERROR, REASON_BAD_JSON, REASON_SCHEMA_INVALID,
    REASON_UNKNOWN_FACTOR, REASON_UNKNOWN_EXAM_TYPE,
    REASON_CONTAINER_TOO_LARGE, REASON_GATE_BLOCKED, REASON_MISSING_INPUT,
})


class OhsCheckError(Exception):
    reason = "error"
    exit_code = EXIT_USAGE

    def __init__(self, message, reason=None, exit_code=None):
        super().__init__(message)
        self.message = message
        if reason is not None:
            self.reason = reason
        if exit_code is not None:
            self.exit_code = exit_code


class UsageError(OhsCheckError):
    reason = "usage_error"
    exit_code = EXIT_USAGE


class InputError(OhsCheckError):
    reason = REASON_SCHEMA_INVALID
    exit_code = EXIT_USAGE


class GateBlocked(OhsCheckError):
    reason = REASON_GATE_BLOCKED
    exit_code = EXIT_USAGE

    def __init__(self, scope, blocked):
        self.scope = scope
        self.blocked = list(blocked)
        coords = ", ".join(self.blocked[:8])
        more = "" if len(self.blocked) <= 8 else "（等 %d 项）" % len(self.blocked)
        super().__init__(
            "规则包门控拦截：scope=%s 引用了 %d 个未核对条目：%s%s。"
            "未挂原文核对的条目不得进入核查路径。"
            % (scope, len(self.blocked), coords, more))


class MissingInputError(OhsCheckError):
    reason = REASON_MISSING_INPUT
    exit_code = EXIT_USAGE

    def __init__(self, items):
        self.items = list(items)
        detail = "; ".join("%s：%s" % (it["target"], it["basis"])
                           for it in self.items[:8])
        super().__init__(
            "缺少 %d 项规则包不承载的外部输入，无法完成判定（绝不静默取默认值）：%s"
            % (len(self.items), detail))


class AmbiguousYearError(OhsCheckError):
    reason = "ambiguous_year"
    exit_code = EXIT_USAGE

    def __init__(self, year, cutover_date):
        super().__init__(
            "年度 %d 内含标准切口日 %s，同一批档案分属两版规则，无法用年度锚定版本。"
            "请给出精确体检日期（exam_date）。" % (year, cutover_date))


class MissingThresholdError(OhsCheckError):
    reason = "missing_threshold"
    exit_code = EXIT_USAGE

    def __init__(self, key):
        super().__init__(
            "规则包 manifest 缺少基准验收门槛 %r——门槛是数据不是代码，"
            "不得回落到内置默认值。请重新生成规则包。" % key)


class MissingDependencyError(OhsCheckError):
    reason = "missing_dependency"
    exit_code = EXIT_MISSING_DEPENDENCY


__all__ = ["EXIT_OK", "EXIT_NONCOMPLIANT", "EXIT_USAGE", "EXIT_MISSING_DEPENDENCY",
           "REASON_READ_ERROR", "REASON_BAD_JSON", "REASON_SCHEMA_INVALID",
           "REASON_UNKNOWN_FACTOR", "REASON_UNKNOWN_EXAM_TYPE",
           "REASON_CONTAINER_TOO_LARGE", "REASON_GATE_BLOCKED",
           "REASON_MISSING_INPUT", "REASON_UNMAPPED_ITEM", "UNJUDGED_REASONS",
           "OhsCheckError", "UsageError", "InputError", "GateBlocked",
           "MissingInputError", "AmbiguousYearError", "MissingThresholdError",
           "MissingDependencyError"]