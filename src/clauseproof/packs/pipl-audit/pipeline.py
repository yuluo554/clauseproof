"""编排层（迁自来源 ``engine.pipeline``）：门槛判定 → 检查单评估 → 分级汇总。

来源 ``AuditResult.to_dict()`` 产出「底稿」形态（供证据挂载 / 报告 / 台账复用）；
本器官**只出账本**——底稿、证据指纹、报告与台账 CSV 都是交付/工具面，不迁。
"""

from . import engine, registry, rules
from .errors import InputError

_PACK_CACHE = {}


class AuditResult:
    """一次判定运行的全部中间结论（供账本映射，不供写盘）。"""

    __slots__ = ("pack", "threshold_result", "item_results", "summary",
                 "counts", "input_card", "manual_results", "audit_scope")

    def __init__(self, pack, threshold_result, item_results, summary, counts,
                 input_card, manual_results, audit_scope):
        self.pack = pack
        self.threshold_result = threshold_result
        self.item_results = item_results
        self.summary = summary
        self.counts = counts
        self.input_card = input_card
        self.manual_results = manual_results
        self.audit_scope = audit_scope


def load_packs(data_dir=None):
    """装配面：载入随包规则包（按目录缓存；判定内核只收内存对象）。"""
    key = data_dir or registry.data_dir()
    if key not in _PACK_CACHE:
        _PACK_CACHE[key] = rules.load_packs(key)
    return _PACK_CACHE[key]


def reset_cache():
    """清空装配缓存（测试用；生产通路每次进程只装配一次）。"""
    _PACK_CACHE.clear()


def _validate_manual(pack, manual_results):
    known = {item.id for item in pack.ruleset.checklist}
    for item_id, record in manual_results.items():
        if item_id not in known:
            raise InputError(
                "manual_results 指向本规则包不存在的检查项：%s（规则包 %s 现有 %d 项）"
                % (item_id, pack.ruleset_id, len(known))
            )
        if not hasattr(record, "get"):
            raise InputError("manual_results[%s] 必须是对象 {state, note}" % item_id)


def compute_audit(pack, input_card, manual_results=None, audit_scope=None):
    """唯一编排：门槛 → 检查单 → 汇总 → 分级计数。"""
    manual_results = manual_results or {}
    audit_scope = audit_scope or {}
    _validate_manual(pack, manual_results)
    threshold_result = engine.evaluate_thresholds(pack.ruleset, input_card)
    item_results = [
        engine.evaluate_item(item, input_card, manual_results)
        for item in pack.ruleset.checklist
    ]
    summary = engine.summarize(item_results)
    tally = engine.counts(item_results)
    return AuditResult(pack, threshold_result, item_results, summary, tally,
                       input_card, manual_results, audit_scope)


__all__ = ["AuditResult", "load_packs", "reset_cache", "compute_audit"]