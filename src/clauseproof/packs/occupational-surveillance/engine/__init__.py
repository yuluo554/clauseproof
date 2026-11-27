"""判定引擎：矩阵推导 / 覆盖度 / 周期 / 版本对照。"""

from .compare import DiffEntry, DiffReport, compare_rulesets, detail_pending
from .coverage import check_record, is_noncompliant, normalize_items, verdict_reachability
from .matrix import (applicability_of, compute_plan, expected_items, plan_for_factor,
                     period_rule_of)
from .period import add_months, is_period_noncompliant, judge_period

__all__ = ["DiffEntry", "DiffReport", "compare_rulesets", "detail_pending",
           "check_record", "is_noncompliant", "normalize_items",
           "verdict_reachability", "applicability_of", "compute_plan",
           "expected_items", "plan_for_factor", "period_rule_of", "add_months",
           "is_period_noncompliant", "judge_period"]