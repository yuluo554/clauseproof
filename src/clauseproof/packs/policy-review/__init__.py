"""器官 ``policy-review``：隐私政策条款风险审查（用户侧）。

一句话：**给一份中文隐私政策/用户协议全文，切成可回溯到原文的条款，命中十类
高风险模式，把命中映射到已核对的法律条文锚点，输出「高 / 中 / 提示」三级发现，
每条发现挂硬锚点与原文区间；缺硬锚点不得判「高」。**

来源判定面（条款切分 / 影子串归一化 / 否定与中和抑制 / 十类模式匹配 /
法条锚点映射 / 三级分级 / 升级条件 / 锚点完整性）逐条迁移；**报告渲染
（Markdown 固定章节 + 免责声明）、CLI 七子命令、真值基准 runner、合成数据生成器、
条文抓取工具都是交付或工具面，不迁**（器官零文件 IO——规则包由装配面
:mod:`pipeline` 读入，判定内核只收内存文本；零环境变量、零时钟、零网络）。

判定账本口径（SKELETON-SPEC §3–§5）：

===============================  ==============================================
来源结论                         本器官 verdict
===============================  ==============================================
``high`` 发现                     ``fail``（锚点：首个硬锚点；阻断 → 退出码 1）
``medium`` 发现                   ``pass``（非阻断结论；锚点：硬锚点 / 分级契约）
``notice`` 提示                   ``pass``（锚点：提示契约）
待核锚点（不参与分级）             ``not_applicable``（无锚点）
背景锚点（CIVIL-*）               ``not_applicable``（无锚点）
规则库坐标 / 条款切分汇总           ``pass``（锚点：规则库 / 切分契约）
汇总（有高级发现 / 无）             ``fail`` / ``pass``
===============================  ==============================================

依据只从条文库取：``basis.anchor(anchor_id)``。条文库版本 = 条文包生成日
``2026-10-18``。版本不符 / 锚点缺失 → ``ContractError``（退出码 3）。
规则包不可用（manifest/sha256/正则/锚点校验失败）→ 退出码 2（口径差见 docs §5）。
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

from . import pipeline, registry
from .constants import LEVEL_LABELS, LEVEL_RANK
from .errors import PolicyError

SLUG = registry.SLUG
VERSION = registry.VERSION
SUMMARY = registry.SUMMARY

#: 输入必填字段
INPUT_FIELDS = ("case_id",)

RULE_RULES = "policy.rules"
RULE_SPLIT = "policy.split"
RULE_FINDING = "policy.finding"
RULE_ANCHOR_PENDING = "policy.anchor.pending"
RULE_ANCHOR_BACKGROUND = "policy.anchor.background"
RULE_SUMMARY = "policy.summary"

CLAUSE_VERSION = "contract.version"
CLAUSE_RULES = "contract.rules"
CLAUSE_SPLIT = "contract.split"
CLAUSE_ANCHOR = "contract.anchor"
CLAUSE_GRADING = "contract.grading"
CLAUSE_NOTICE = "contract.notice"
CLAUSE_INPUT = "contract.input"
CLAUSE_SUMMARY = "contract.summary"
CLAUSE_EVIDENCE = "contract.evidence"

_ALLOWED_KEYS = {"case_id", "text", "note"}


def _require_basis_version(basis: Basis) -> None:
    if basis.version != VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据条文包生成日 %s，条文库实为 %s"
            % (VERSION, basis.version)
        )


def _anchor(basis: Basis, clause_id: str):
    if basis.clause(clause_id) is None:
        raise ContractError("条文库缺少本器官的必要条款：%s" % clause_id)
    return basis.anchor(clause_id)


def _validate_subject(subject: Mapping) -> Mapping:
    if not isinstance(subject, Mapping):
        raise ValueError("输入必须是 JSON 对象")
    unknown = sorted(set(subject) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError("输入含未知字段：%s" % ", ".join(unknown))
    if not str(subject.get("case_id") or "").strip():
        raise ValueError("输入缺少 case_id（一次判定运行的稳定标识）")
    text = subject.get("text")
    if not isinstance(text, str):
        raise ValueError("输入缺少 text（隐私政策/用户协议全文）")
    if not text.strip():
        raise ValueError("text 为空，无法切分")
    return subject


def _load_library():
    try:
        return pipeline.load_library()
    except PolicyError as exc:
        raise ValueError("规则包不可用：%s" % exc)


def _rules_finding(library, basis: Basis) -> Finding:
    coordinate = library.coordinate()
    return Finding(
        rule_id=RULE_RULES,
        verdict=PASS,
        message=("规则库 %s：%d 类模式 / %d 部依据 / %d 条锚点（硬锚点 %d / 待核 %d）；"
                 "生成日 %s"
                 % (coordinate["ruleset_version"], coordinate["patterns"],
                    coordinate["statutes"], coordinate["anchors"],
                    coordinate["hard_anchors"], coordinate["pending_anchors"],
                    coordinate["generated_on"])),
        anchor=_anchor(basis, CLAUSE_RULES),
        evidence=coordinate,
    )


def _split_finding(analysis, basis: Basis) -> Finding:
    document = analysis.document
    kinds = {}
    for clause in analysis.clauses.get("clauses") or []:
        kinds[clause["kind"]] = kinds.get(clause["kind"], 0) + 1
    return Finding(
        rule_id=RULE_SPLIT,
        verdict=PASS,
        message=("条款切分：%d 条（字符 %d；%s）"
                 % (document.get("clause_count", 0), document.get("char_count", 0),
                    "、".join("%s=%d" % (key, kinds[key]) for key in sorted(kinds)))),
        anchor=_anchor(basis, CLAUSE_SPLIT),
        evidence=dict(document, kinds=dict(sorted(kinds.items()))),
    )


def _finding_anchor(finding, basis: Basis):
    anchor_ids = finding.get("anchor_ids") or []
    if anchor_ids:
        return _anchor(basis, anchor_ids[0])
    if finding["level"] == "notice":
        return _anchor(basis, CLAUSE_NOTICE)
    return _anchor(basis, CLAUSE_GRADING)


def _finding_records(analysis, basis: Basis):
    library = analysis.library
    records = []
    for finding in analysis.findings:
        pattern = library.pattern(finding["pattern_id"])
        name = pattern.name_zh if pattern is not None else finding["pattern_id"]
        level = finding["level"]
        verdict = FAIL if level == "high" else PASS
        records.append(Finding(
            rule_id="%s:%s:%s" % (RULE_FINDING, finding["clause_id"],
                                  finding["pattern_id"]),
            verdict=verdict,
            message=("%s级发现：%s——%s（原文 %d-%d）"
                     % (LEVEL_LABELS.get(level, level), name,
                        finding["excerpt"], finding["char_start"],
                        finding["char_end"])),
            anchor=_finding_anchor(finding, basis),
            evidence=dict(finding),
        ))
    return records


def _anchor_records(analysis):
    records = []
    for anchor_id in analysis.pending_anchor_ids:
        records.append(Finding(
            rule_id="%s:%s" % (RULE_ANCHOR_PENDING, anchor_id),
            verdict=NOT_APPLICABLE,
            message="锚点待核对（未参与分级）：%s" % anchor_id,
            anchor=None,
            evidence={"anchor_id": anchor_id, "status": "pending"},
        ))
    for anchor_id in analysis.background_anchor_ids:
        records.append(Finding(
            rule_id="%s:%s" % (RULE_ANCHOR_BACKGROUND, anchor_id),
            verdict=NOT_APPLICABLE,
            message="背景引用（CIVIL-* 不参与分级、不进 anchor_ids）：%s" % anchor_id,
            anchor=None,
            evidence={"anchor_id": anchor_id, "strength": "background"},
        ))
    return records


def _summary_finding(analysis, basis: Basis) -> Finding:
    levels = analysis.levels
    total = sum(levels.values())
    message = ("三级发现：高 %d / 中 %d / 提示 %d（共 %d 条；切分 %d 条条款）"
               % (levels["high"], levels["medium"], levels["notice"], total,
                  analysis.document.get("clause_count", 0)))
    if levels["high"]:
        message += "；存在高级发现（阻断）"
        return Finding(rule_id=RULE_SUMMARY, verdict=FAIL, message=message,
                       anchor=_anchor(basis, CLAUSE_SUMMARY),
                       evidence=dict(levels, total=total))
    message += "；无高级发现"
    return Finding(rule_id=RULE_SUMMARY, verdict=PASS, message=message,
                   anchor=_anchor(basis, CLAUSE_SUMMARY),
                   evidence=dict(levels, total=total))


def evaluate_with_library(subject: Mapping, basis: Basis, library=None) -> Iterable[Finding]:
    """判定入口（``library`` 仅供测试注入；生产通路读随包目录）。"""
    _require_basis_version(basis)
    subject = _validate_subject(subject)
    if library is None:
        library = _load_library()
    try:
        analysis = pipeline.run(subject["text"], library)
    except PolicyError as exc:
        raise ValueError("输入不可用：%s" % exc)

    findings = [_rules_finding(library, basis), _split_finding(analysis, basis)]
    findings.extend(_finding_records(analysis, basis))
    findings.extend(_anchor_records(analysis))
    findings.append(_summary_finding(analysis, basis))
    return tuple(findings)


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_library(subject, basis, None)


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "evaluate_with_library"]