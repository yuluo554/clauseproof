"""异常与原因码（迁自来源 ``errors`` 的判定子集）。"""


class PatfeeError(Exception):
    def __init__(self, message, reason_code="error"):
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code

    def __str__(self):
        return self.message


class UsageError(PatfeeError):
    reason_code = "usage_error"


class RulesetError(PatfeeError):
    reason_code = "ruleset_error"


class OutOfRangeError(PatfeeError):
    def __init__(self, message, reason_code="out_of_range"):
        super().__init__(message, reason_code)


__all__ = ["PatfeeError", "UsageError", "RulesetError", "OutOfRangeError"]