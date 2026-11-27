"""器官 ``picrecall``：截图相似分组与保留建议（只读，绝不删除）。

一句话：**给一批已计算 pHash 的截图指纹，按汉明距离阈值做相似分组，给出
保留建议（分辨率 → 大小 → mtime → 路径），逐组挂数据契约锚点；只出建议，
不删除、不改名、不写回任何用户文件。**

来源判定面（``picrecall.dedupe``：单链聚类 + 保留优先级 + 只读纪律）逐条迁移；
**OCR / SQLite 索引 / 全文检索 / CSV 写盘 / GUI 都是输入或交付面，不迁**
（器官零文件 IO、零环境变量、零时钟；pHash 由输入层计算后作为指纹输入）。

判定账本口径（SKELETON-SPEC §3–§5）：

============================  ==========================================
来源结论                       本器官 verdict
============================  ==========================================
存在相似分组（≥2 张）           ``fail``（组级；检出重复建议，对齐来源 exit 1）
组内代表图（keep）               ``pass``（锚点：保留建议契约）
组内冗余图（redundant）          ``not_applicable``（仅建议，不阻断）
无相似分组                       ``pass``（汇总）
============================  ==========================================

**只读纪律**：本器官没有任何删除/改名/写回用户文件的代码路径；`fail` 只表示
「检出重复建议」，不代表任何自动动作。

依据只从条文库取：``basis.anchor(clause_id)``；条文库版本 = 数据快照日期
``2026-10-14``。版本不符 → ``ContractError``（退出码 3）；条款缺失 →
``BasisMissing``（本产品内核映射退出码 2）。

> **队列备注差异（如实登记）**：队列备注写「缺陷产品召回」，但本行来源目录的
> 实际来源是 **截图文字检索库 picrecall**（picture recall =
> 图片检索，不是产品召回）。本器官按实际仓迁移相似分组判定面；差异见 docs §5。
"""

from typing import Iterable, Mapping

from clauseproof.core.basis import Basis
from clauseproof.core.ledger import (
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Finding,
)
from clauseproof.core.registry import Pack, register

from . import engine
from . import registry as pack_data

SLUG = pack_data.SLUG
VERSION = pack_data.VERSION
SUMMARY = pack_data.SUMMARY

#: 输入必填字段（case_id = 一次判定运行的稳定标识）
INPUT_FIELDS = ("case_id",)

RULE_GROUP = "picrecall.group"
RULE_KEEP = "picrecall.keep"
RULE_SUMMARY = "picrecall.summary"

CLAUSE_DEDUPE = "contract.dedupe"
CLAUSE_KEEP = "contract.keep"
CLAUSE_READONLY = "contract.readonly"
CLAUSE_THRESHOLD = "contract.threshold"
CLAUSE_LEDGER = "contract.ledger"

_ALLOWED_KEYS = {"case_id", "dedupe", "note"}
_ALLOWED_DEDUPE_KEYS = {"threshold", "items"}


def _require_basis_version(basis: Basis) -> None:
    if basis.version != pack_data.VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据数据快照 %s，条文库实为 %s"
            % (pack_data.VERSION, basis.version))


def _validate_subject(subject: Mapping):
    if not isinstance(subject, Mapping):
        raise ValueError("输入必须是 JSON 对象")
    unknown = sorted(set(subject) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError("输入含未知字段：%s" % ", ".join(unknown))
    if not str(subject.get("case_id") or "").strip():
        raise ValueError("输入缺少 case_id（一次判定运行的稳定标识）")
    dedupe = subject.get("dedupe")
    if not isinstance(dedupe, Mapping):
        raise ValueError("输入缺少 dedupe 段（{threshold, items}）")
    unknown_dedupe = sorted(set(dedupe) - _ALLOWED_DEDUPE_KEYS)
    if unknown_dedupe:
        raise ValueError("dedupe 含未知字段：%s" % ", ".join(unknown_dedupe))
    return subject


def _group_finding(group, basis: Basis) -> Finding:
    members = group["members"]
    keep = group["representative"]["path"]
    return Finding(
        rule_id="%s:%d" % (RULE_GROUP, group["group_id"]),
        verdict=FAIL,
        message="相似截图分组 %d：%d 张，建议保留 %s（其余 %d 张为冗余建议；不删除任何文件）"
                % (group["group_id"], len(members), keep, len(members) - 1),
        anchor=basis.anchor(CLAUSE_DEDUPE),
        evidence={"group_id": group["group_id"], "keep": keep,
                  "members": list(members),
                  "max_distance": max(m["max_distance_to_rep"] for m in members)},
    )


def _member_findings(group, basis: Basis):
    findings = []
    keep = group["representative"]["path"]
    for member in sorted(group["members"], key=lambda x: x["path"]):
        is_keep = member["path"] == keep
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_KEEP, member["path"]),
            verdict=PASS if is_keep else NOT_APPLICABLE,
            message=("%s：建议保留（组 %d 代表图）" % (member["path"], group["group_id"])
                     if is_keep else
                     "%s：冗余建议（组 %d；仅建议，不删除）"
                     % (member["path"], group["group_id"])),
            anchor=basis.anchor(CLAUSE_KEEP if is_keep else CLAUSE_READONLY),
            evidence=dict(member, group_id=group["group_id"],
                          suggestion="keep" if is_keep else "redundant"),
        ))
    return findings


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    _require_basis_version(basis)
    _validate_subject(subject)
    dedupe = subject["dedupe"]
    threshold = dedupe.get("threshold", engine.DEFAULT_THRESHOLD)
    try:
        items = engine.parse_items(dedupe.get("items"))
        groups = engine.group_items(items, threshold)
    except ValueError as exc:
        raise ValueError(str(exc))
    findings = []
    for group in groups:
        findings.append(_group_finding(group, basis))
        findings.extend(_member_findings(group, basis))
    findings.append(Finding(
        rule_id=RULE_SUMMARY,
        verdict=PASS,
        message=("相似分组：%d 组（%d 张入组 / 输入 %d 张，阈值 %d）；只出建议，不删除任何文件"
                 % (len(groups), sum(len(g["members"]) for g in groups),
                    len(items), threshold)),
        anchor=basis.anchor(CLAUSE_LEDGER),
        evidence={"groups": len(groups),
                  "items": len(items),
                  "threshold": threshold,
                  "group_ids": [g["group_id"] for g in groups]},
    ))
    return tuple(findings)


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate"]