"""版本锚定（迁自来源 ``rules.version``）：按体检日期选规则版本。

锚定键 = 体检日期 exam_date（不是编制年度、不是「年度」）；
切口日之前 → cutover.before；切口日当日及之后 → cutover.after。
只给年度且该年度包含切口日 → AmbiguousYearError（宁报错不猜）。
切口日与版本号一律读自 manifest（代码零年份字面量）。
"""

import datetime as _dt

from ..errors import AmbiguousYearError, InputError
from ..model import parse_iso_date


def parse_cutover_date(manifest):
    return parse_iso_date(manifest.cutover_date_text, "manifest.cutover.date")


def resolve_ruleset_id(exam_date, manifest):
    cutover = parse_cutover_date(manifest)
    if isinstance(exam_date, int) and not isinstance(exam_date, bool):
        if exam_date == cutover.year:
            raise AmbiguousYearError(exam_date, cutover.isoformat())
        return manifest.cutover["after"] if exam_date > cutover.year \
            else manifest.cutover["before"]
    if isinstance(exam_date, str):
        text = exam_date.strip()
        if len(text) == 4 and text.isdigit():
            return resolve_ruleset_id(int(text), manifest)
        exam_date = parse_iso_date(text)
    if not isinstance(exam_date, _dt.date):
        raise InputError("exam_date 必须是 ISO 日期字符串、date 或年份整数，实际 %r"
                         % (exam_date,))
    return manifest.cutover["after"] if exam_date >= cutover \
        else manifest.cutover["before"]


def describe_anchor(exam_date, manifest):
    cutover = parse_cutover_date(manifest)
    ruleset_id = resolve_ruleset_id(exam_date, manifest)
    return {
        "exam_date": exam_date if isinstance(exam_date, str) else str(exam_date),
        "cutover_date": cutover.isoformat(),
        "ruleset_id": ruleset_id,
        "rule": "exam_date >= cutover_date ? after : before",
    }


__all__ = ["parse_cutover_date", "resolve_ruleset_id", "describe_anchor"]