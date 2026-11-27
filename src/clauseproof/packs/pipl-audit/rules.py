"""规则包加载 / 校验 / 单点 status 门控（迁自来源 ``rules.loader``）。

纪律（来源 NFR-6）：``effective()`` 是唯一生效门——``status=pending`` 的条目与
「verified 但缺出处」的条目在此被拒，任何下游通路都拿不到未核对条目。

**装配边界**：本模块只在装配时读随包目录（与 :mod:`registry` 同一形态）。
判定内核只收内存对象；器官零环境变量、零 cwd、零时钟。
"""

import json
import os

from . import registry
from .errors import (PendingEntryError, RulesetError,
                     UnattributedEntryError)
from .model import (EFFECTS, METHOD_AUTO, METHOD_MANUAL, STATUS_VERIFIED,
                    Ruleset)

SCHEMA_RULESET = "1.0"

#: 门槛运算符白名单（与来源一致；未知运算符在装配期即拒，不静默跳过）
OPS = {
    ">": lambda actual, bound: actual > bound,
    ">=": lambda actual, bound: actual >= bound,
    "<": lambda actual, bound: actual < bound,
    "<=": lambda actual, bound: actual <= bound,
    "==": lambda actual, bound: actual == bound,
    "!=": lambda actual, bound: actual != bound,
}


class RulePack:
    """一份随包规则包（坐标 + 解析后的规则对象 + 是否合成示例）。"""

    __slots__ = ("ruleset_id", "ruleset", "file", "synthetic")

    def __init__(self, ruleset, file, synthetic):
        self.ruleset_id = ruleset.ruleset_id
        self.ruleset = ruleset
        self.file = file
        self.synthetic = bool(synthetic)

    @property
    def version(self):
        return self.ruleset.version

    @property
    def counts(self):
        return {
            "basis": len(self.ruleset.basis),
            "thresholds": len(self.ruleset.thresholds),
            "checklist": len(self.ruleset.checklist),
        }

    def coordinate(self):
        return {
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.version,
            "schema_version": self.ruleset.schema_version,
            "generated_at": self.ruleset.generated_at,
            "synthetic": self.synthetic,
        }


def parse_ruleset(data, path=None):
    """JSON 对象 → :class:`Ruleset`（字段缺项即报错，不静默丢弃条目）。"""
    if not isinstance(data, dict):
        raise RulesetError("规则包必须是 JSON 对象")
    try:
        ruleset = Ruleset.from_dict(data, path=path)
    except KeyError as exc:
        raise RulesetError("规则包条目缺少必填字段: %s" % exc)
    except (TypeError, ValueError) as exc:
        raise RulesetError("规则包字段类型非法: %s" % exc)
    validate(ruleset)
    return ruleset


def validate(ruleset):
    """schema 校验：id 唯一、运算符/状态/义务类型在册、条款坐标非空。"""
    if ruleset.schema_version != SCHEMA_RULESET:
        raise RulesetError(
            "规则包 schema_version 不符：要求 %s，实为 %r"
            % (SCHEMA_RULESET, ruleset.schema_version)
        )
    if not ruleset.ruleset_id:
        raise RulesetError("规则包缺少 ruleset_id")
    if not ruleset.version:
        raise RulesetError("规则包缺少 version（依据文件 × 版本坐标）")

    threshold_ids, item_ids = set(), set()
    for threshold in ruleset.thresholds:
        if threshold.id in threshold_ids:
            raise RulesetError("门槛 id 重复: %s" % threshold.id)
        threshold_ids.add(threshold.id)
        if threshold.op not in OPS:
            raise RulesetError("门槛 %s 的运算符非法: %r" % (threshold.id, threshold.op))
        if isinstance(threshold.value, bool) or not isinstance(threshold.value, int):
            raise RulesetError("门槛 %s 的阈值必须是整数: %r"
                               % (threshold.id, threshold.value))
        if threshold.effect not in EFFECTS:
            raise RulesetError("门槛 %s 的义务类型非法: %r"
                               % (threshold.id, threshold.effect))
        if not (threshold.clause.basis and threshold.clause.article):
            raise RulesetError("门槛 %s 缺条款坐标（basis/article）" % threshold.id)

    for item in ruleset.checklist:
        if item.id in item_ids:
            raise RulesetError("检查项 id 重复: %s" % item.id)
        item_ids.add(item.id)
        if item.method not in (METHOD_AUTO, METHOD_MANUAL):
            raise RulesetError("检查项 %s 的核查方式非法: %r" % (item.id, item.method))
        if item.method == METHOD_AUTO and not item.auto_field:
            raise RulesetError("auto 检查项 %s 缺 auto_field" % item.id)
        if item.only_if is not None and not isinstance(item.only_if, dict):
            raise RulesetError("检查项 %s 的 only_if 必须是对象" % item.id)
        if not (item.clause.basis and item.clause.article):
            raise RulesetError("检查项 %s 缺条款坐标（basis/article）" % item.id)
    return ruleset


def effective(ruleset):
    """生效门：拒绝 ``status != verified`` 与「verified 但缺出处」的条目。"""
    pending = ruleset.pending_entries()
    if pending:
        raise PendingEntryError(pending)
    unattributed = ruleset.unattributed_entries()
    if unattributed:
        raise UnattributedEntryError(unattributed)
    return ruleset


def load_ruleset_file(path):
    """读一份规则包文件（装配面；不供判定内核调用）。"""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise RulesetError("无法读取规则包: %s (%s)" % (path, exc))
    except ValueError as exc:
        raise RulesetError("规则包 JSON 解析失败: %s (%s)" % (path, exc))
    return parse_ruleset(data, path=path)


def load_packs(data_dir=None):
    """载入随包目录下的 ``ruleset-*.json``，返回 ``{ruleset_id: RulePack}``。"""
    root = data_dir or registry.data_dir()
    if not os.path.isdir(root):
        raise RulesetError("规则包目录不存在: %s" % root)
    names = sorted(name for name in os.listdir(root)
                   if name.startswith("ruleset-") and name.endswith(".json"))
    if not names:
        raise RulesetError("规则包目录下无 ruleset-*.json: %s" % root)
    packs = {}
    for name in names:
        ruleset = load_ruleset_file(os.path.join(root, name))
        synthetic = "demo" in ruleset.ruleset_id
        if ruleset.ruleset_id in packs:
            raise RulesetError("规则包 id 重复: %s" % ruleset.ruleset_id)
        packs[ruleset.ruleset_id] = RulePack(ruleset, name, synthetic)
    return packs


__all__ = [
    "SCHEMA_RULESET", "OPS", "RulePack",
    "parse_ruleset", "validate", "effective", "load_ruleset_file", "load_packs",
]