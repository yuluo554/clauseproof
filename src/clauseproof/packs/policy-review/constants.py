"""契约常量（迁自来源 ``constants``：等级 / 命中类型 / 条款类型 / 截断口径）。

退出码由产品内核统一：``0`` 无阻断 / ``1`` 检出高级发现 / ``2`` 输入不合法 /
``3`` 契约违约（规则包或条文库不可用）。
"""

LEVELS = ("high", "medium", "notice")
LEVEL_RANK = {"high": 0, "medium": 1, "notice": 2}
LEVEL_LABELS = {"high": "高", "medium": "中", "notice": "提示"}

HIT_KINDS = ("deterministic", "semantic_confirmed", "semantic_rejected", "uncertain")
GRADABLE_KINDS = ("deterministic", "semantic_confirmed")
CLAUSE_KINDS = ("heading", "paragraph", "list_item", "appendix_row")

EXCERPT_MAX_CHARS = 120
EXCERPT_ELLIPSIS = "…"

BACKGROUND_PREFIX = "CIVIL-"
ARTICLE_STATUSES = ("verified", "pending")

EXPECTED_PATTERN_IDS = tuple("P%02d" % index for index in range(1, 11))

__all__ = [
    "LEVELS", "LEVEL_RANK", "LEVEL_LABELS", "HIT_KINDS", "GRADABLE_KINDS",
    "CLAUSE_KINDS", "EXCERPT_MAX_CHARS", "EXCERPT_ELLIPSIS", "BACKGROUND_PREFIX",
    "ARTICLE_STATUSES", "EXPECTED_PATTERN_IDS",
]