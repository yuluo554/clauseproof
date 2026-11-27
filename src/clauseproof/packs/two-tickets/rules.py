"""规则库加载与校验（迁自来源 ``rules``）。

规则库三文件（``rules-form`` / ``rules-time`` / ``rules-content``）按文件名字典序读入；
每条规则必须声明 ``id`` / ``name`` / ``check_type`` / ``applies_to`` / ``basis``，
且 ``basis.standard`` 非空——**无出处的规则不得落库**（来源结论纪律）。

与来源的一处口径差（docs §5）：未知 ``check_type`` 由「运行时跳过 + 卡片 warning」
改为**装配期拒绝**（不静默跳过任何一条规则）。
"""

import json
import os
import re

from .errors import RuleError
from .model import (BASIS_STATUSES, CHECK_TYPES, TICKET_TYPE_NAMES)

RULES_PREFIX = "rules-"
REQUIRED_KEYS = ("id", "name", "check_type", "applies_to", "basis")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class RuleLibrary:
    """一份随包规则库：39 条规则 + 依据状态计数 + 复核锚。"""

    __slots__ = ("rules", "files", "by_id")

    def __init__(self, rules, files):
        self.rules = list(rules)
        self.files = tuple(files)
        self.by_id = {rule["id"]: rule for rule in self.rules}

    @property
    def status_counts(self):
        counts = {status: 0 for status in BASIS_STATUSES}
        for rule in self.rules:
            status = rule["basis"]["status"]
            counts[status] = counts.get(status, 0) + 1
        return counts

    @property
    def check_type_counts(self):
        counts = {}
        for rule in self.rules:
            counts[rule["check_type"]] = counts.get(rule["check_type"], 0) + 1
        return counts

    @property
    def pending_rules(self):
        return [rule for rule in self.rules
                if rule["basis"]["status"] != "已核对"]

    @property
    def review_dues(self):
        return {rule["id"]: rule["basis"].get("review_due", "")
                for rule in self.rules}

    def coordinate(self):
        counts = self.status_counts
        return {
            "ruleset_label": "两票规则库（工作票/操作票 × 7 check_type）",
            "rules": len(self.rules),
            "verified": counts.get("已核对", 0),
            "pending": counts.get("待核对", 0),
            "check_types": dict(sorted(self.check_type_counts.items())),
            "files": list(self.files),
        }


def parse_rules(data, name="<rules>"):
    """单文件 JSON → 规则列表（字段缺项 / 依据无出处即报错）。"""
    if not isinstance(data, dict):
        raise RuleError("规则文件必须是 JSON 对象: %s" % name)
    raw = data.get("rules")
    if not isinstance(raw, list) or not raw:
        raise RuleError("规则文件缺少非空 rules 数组: %s" % name)
    rules = []
    for rule in raw:
        if not isinstance(rule, dict):
            raise RuleError("规则条目必须是对象: %s" % name)
        missing = [key for key in REQUIRED_KEYS if not rule.get(key)]
        if missing:
            raise RuleError("规则缺少必填字段 %s: %s" % (missing, name))
        basis = rule["basis"]
        if not isinstance(basis, dict) or not basis.get("standard"):
            raise RuleError("规则 %s 依据无出处（不得落库）: %s"
                            % (rule.get("id"), name))
        rules.append(rule)
    return rules


def validate(rules):
    """规则库校验：id 唯一、check_type / 票种 / 依据状态在册、复核锚合法。"""
    seen = set()
    for rule in rules:
        rule_id = rule["id"]
        if rule_id in seen:
            raise RuleError("规则 id 重复: %s" % rule_id)
        seen.add(rule_id)
        if rule["check_type"] not in CHECK_TYPES:
            raise RuleError("规则 %s 的 check_type 非法: %r"
                            % (rule_id, rule["check_type"]))
        applies_to = rule["applies_to"]
        if not isinstance(applies_to, list) or not applies_to:
            raise RuleError("规则 %s 的 applies_to 必须是非空数组" % rule_id)
        unknown = [ticket for ticket in applies_to if ticket not in TICKET_TYPE_NAMES]
        if unknown:
            raise RuleError("规则 %s 的票种非法: %s" % (rule_id, ", ".join(unknown)))
        basis = rule["basis"]
        if basis.get("status") not in BASIS_STATUSES:
            raise RuleError("规则 %s 的依据状态非法: %r"
                            % (rule_id, basis.get("status")))
        due = basis.get("review_due")
        if due is not None and not _ISO_DATE.match(str(due)):
            raise RuleError("规则 %s 的 review_due 不是合法 ISO 日期: %r"
                            % (rule_id, due))
        if "params" in rule and not isinstance(rule["params"], dict):
            raise RuleError("规则 %s 的 params 必须是对象" % rule_id)
    return rules


def load_library(data_dir):
    """装配面：读随包目录下的 ``rules-*.json``。"""
    if not os.path.isdir(data_dir):
        raise RuleError("规则目录不存在: %s" % data_dir)
    names = sorted(name for name in os.listdir(data_dir)
                   if name.startswith(RULES_PREFIX) and name.endswith(".json"))
    if not names:
        raise RuleError("规则目录下无 rules-*.json: %s" % data_dir)
    rules = []
    for name in names:
        path = os.path.join(data_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except OSError as exc:
            raise RuleError("无法读取规则文件: %s (%s)" % (path, exc))
        except ValueError as exc:
            raise RuleError("规则文件 JSON 解析失败: %s (%s)" % (path, exc))
        rules.extend(parse_rules(data, name))
    validate(rules)
    return RuleLibrary(rules, names)


__all__ = ["RULES_PREFIX", "REQUIRED_KEYS", "RuleLibrary", "parse_rules",
           "validate", "load_library"]