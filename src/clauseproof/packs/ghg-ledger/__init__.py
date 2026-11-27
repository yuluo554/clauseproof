"""器官 ``ghg-ledger``：组织温室气体排放核算三维判定（GB/T 32150 双标尺 × 年度 × 行业）。

规模：判定面来自 target-map ① 行的旧仓（三维坐标与 status 门控、核算边界识别、
逐源核算与单位链、数据质量四类校核、行业配额试算）。

本器官只做一件事：**给一份企业排放档案 + 随包三维规则包，判该坐标下应核算哪些源、
逐源活动数据×因子×氧化率算出的排放量是多少、数据质量有哪些分级问题、
配额试算缺口多大**。它不打印、不读环境变量、不读时钟，也不带自己的参数解析器——
入口只有 ``clauseproof check ghg-ledger --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

====================================  ==========================================
来源结论                               本器官 verdict
====================================  =====================================
门控拦截（pending 条目）                ``fail``（必带锚点：status 门控契约；阻断 → 1）
纳入核算的源（逐源明细）                 ``pass``（锚点：核算边界契约）
依据不足被排除的源                       ``not_applicable``（锚点：核算边界契约）
双标尺差异（added/removed/adjusted）     ``pass``（锚点：核算边界契约）
校核 error                             ``fail``（锚点：校核契约）
校核 warning / info                     ``not_applicable``（预警≠阻断判定）
校核规则未执行（阈值未生效/缺基线）        ``not_applicable``（显式列出，不静默通过）
配额试算（method≠none）                  ``pass``（锚点：配额方法学契约）
配额不适用（method=none）                ``not_applicable``
====================================  ==========================================

**输入不可用**（坐标不存在/跨坐标混算/缺应核算源活动数据/因子三层不可用/
配额参数需外部输入未提供/文件非法）→ 抛 :class:`engine.GhgError` → 退出码 2
（与来源仓 0/1/2 契约逐条对齐：来源 1（门控拦截）→ 本器官 fail → 1 一致）。

条文库缺所需条款 → ``BasisMissing`` 冒到 CLI（退出码 3）；条文库版本与规则包
快照不符 → ``ContractError``（退出码 3）。

**文件读取只在装配面**：随包冻结规则包（与来源仓逐字节同 sha256）由
``registry`` 读入（与 ``Basis.from_json`` 同形态的装配），判定内核只收内存 dict。
"""

from typing import Any, Dict, Iterable, List, Mapping, Optional

from clauseproof.core.basis import Basis
from clauseproof.core.ledger import (
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Finding,
)
from clauseproof.core.registry import Pack, register

from . import calc as C
from . import engine as E
from . import quota as Q
from . import registry as reg
from . import rules as R

SLUG = "ghg-ledger"
VERSION = "0.1.0"
SUMMARY = ("组织温室气体排放核算（GB/T 32150 双标尺 × 年度 × 行业三维门控 + 逐源核算 "
           "+ 质量校核 + 配额试算）")

INPUT_FIELDS = ("profile",)

RULE_GATE = "ghg.gate"
RULE_SOURCE = "ghg.source"
RULE_LINE = "ghg.line"
RULE_BOUNDARY_DIFF = "ghg.boundary_diff"
RULE_QUALITY = "ghg.quality"
RULE_QUALITY_SKIP = "ghg.quality_skipped"
RULE_QUOTA = "ghg.quota"
RULE_RESULT = "ghg.result"

_ALL_SCOPES = ("calc", "check", "quota")
#: 缺省只跑核算路径（与来源 README 示例 `ghg calc` 同语义；校核/配额经 subject.scopes 显式开启）
_DEFAULT_SCOPES = ("calc",)


def _require_basis_version(basis: Basis) -> None:
    if basis.version != reg.PARAMS_VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据规则包快照 %s 核对，条文库实为 %s"
            % (reg.PARAMS_VERSION, basis.version))


def _gate_findings(index: R.RulesIndex, coord: E.Coordinate,
                   scopes: Iterable[str], basis: Basis) -> List[Finding]:
    findings = []
    for scope in scopes:
        report = index.gate_report(coord, scope=scope)
        if report["effective"]:
            continue
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_GATE, scope),
            verdict=FAIL,
            message="坐标 %s 的 %s 路径门控拦截：%d 项未核对（%s）"
                    % (coord.key, scope, report["pending_count"],
                       "、".join(p["entry"] for p in report["pending"][:5])),
            anchor=basis.anchor(reg.CLAUSE_GATE),
            evidence={"coordinate": coord.key, "scope": scope,
                      "pending": report["pending"]},
        ))
    return findings


def _source_findings(result: Mapping, basis: Basis) -> List[Finding]:
    findings = []
    for source in result["boundary"]["sources"]:
        if source["included"]:
            findings.append(Finding(
                rule_id="%s:%s" % (RULE_SOURCE, source["id"]),
                verdict=PASS,
                message="%s：%s" % (source["id"], source["reason"]),
                anchor=basis.anchor(reg.CLAUSE_BOUNDARY),
                evidence={"source_id": source["id"], "category": source["category"],
                          "required": source["required"], "included": True},
            ))
        else:
            findings.append(Finding(
                rule_id="%s:%s" % (RULE_SOURCE, source["id"]),
                verdict=NOT_APPLICABLE,
                message="%s：%s" % (source["id"], source["reason"]),
                anchor=basis.anchor(reg.CLAUSE_BOUNDARY),
                evidence={"source_id": source["id"], "category": source["category"],
                          "required": source["required"], "included": False},
            ))
    for line in result["lines"]:
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_LINE, line["source_id"]),
            verdict=PASS,
            message="%s：活动数据 %s %s × 因子 %s（%s）× 氧化率 %s = %s %s"
                    % (line["source_id"], line["activity"]["value"],
                       line["activity"]["unit"] or "-", line["factor"]["value"],
                       line["factor"]["source"], line["oxidation_rate"],
                       line["emission"], result["unit"]),
            anchor=basis.anchor(reg.CLAUSE_FACTOR_PRIORITY),
            evidence={"source_id": line["source_id"],
                      "activity": line["activity"],
                      "activity_base": line["activity_base"],
                      "factor": line["factor"],
                      "factor_base": line["factor_base"],
                      "oxidation_rate": line["oxidation_rate"],
                      "emission": line["emission"],
                      "unit_chain": line["unit_chain"],
                      "provenance": line["provenance"]},
        ))
    return findings


def _quality_findings(report: Mapping, basis: Basis) -> List[Finding]:
    findings = []
    for issue in report["issues"]:
        verdict = FAIL if issue["level"] == C.LEVEL_ERROR else NOT_APPLICABLE
        findings.append(Finding(
            rule_id="%s:%s:%s" % (RULE_QUALITY, issue["rule_id"],
                                  issue["source_id"] or "facility"),
            verdict=verdict,
            message="%s（%s）%s" % (issue["message"], issue["level"],
                                   "— " + issue["advice"] if issue.get("advice") else ""),
            anchor=basis.anchor(reg.CLAUSE_QUALITY),
            evidence={"rule_id": issue["rule_id"], "type": issue["type"],
                      "level": issue["level"], "source_id": issue["source_id"],
                      "clause": issue["clause"]},
        ))
    for skip in report["rules_skipped"]:
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_QUALITY_SKIP, skip["type"]),
            verdict=NOT_APPLICABLE,
            message="校核检查 %s 未执行：%s（规则 %s）"
                    % (skip["type"], skip["reason"], "、".join(skip["rule_ids"])),
            anchor=basis.anchor(reg.CLAUSE_QUALITY),
            evidence={"type": skip["type"], "reason": skip["reason"],
                      "rule_ids": skip["rule_ids"]},
        ))
    return findings


def _quota_findings(report: Mapping, basis: Basis) -> List[Finding]:
    if report["status"] == Q.STATUS_NOT_APPLICABLE:
        return [Finding(
            rule_id=RULE_QUOTA,
            verdict=NOT_APPLICABLE,
            message="配额试算不适用（method=%s）：%s"
                    % (report["method"], "；".join(report["notes"]) or "无备注"),
            anchor=basis.anchor(reg.CLAUSE_QUOTA),
            evidence={"method": report["method"], "status": report["status"],
                      "disclaimer_required": report["disclaimer_required"]},
        )]
    return [Finding(
        rule_id=RULE_QUOTA,
        verdict=PASS,
        message="配额试算（method=%s）：配额 %s %s，实际排放 %s %s，缺口 %s（%s）"
                % (report["method"], report["allocated"], report["unit"],
                   report["actual"], report["unit"], report["gap"],
                   report["gap_ratio"]),
        anchor=basis.anchor(reg.CLAUSE_QUOTA),
        evidence={"method": report["method"], "status": report["status"],
                  "allocated": report["allocated"], "actual": report["actual"],
                  "gap": report["gap"], "gap_ratio": report["gap_ratio"],
                  "parameters": report["parameters"],
                  "disclaimer_required": report["disclaimer_required"],
                  "disclaimer": report["disclaimer"]},
    )]


def _findings(payload: Mapping, coord, scopes, index, units, basis) -> List[Finding]:
    findings: List[Finding] = []
    gate = _gate_findings(index, coord, scopes, basis)
    findings.extend(gate)
    gate_blocked = {f.evidence["scope"] for f in gate}

    result = None
    if "calc" in scopes and "calc" not in gate_blocked:
        pack = index.effective_ruleset(coord, scope=R.SCOPE_CALC)
        result = C.compute(payload, coord, pack, units)
        findings.extend(_source_findings(result, basis))

        # 双标尺差异（同年度同行业的旧版坐标存在时自动对照）
        old_coord = _old_standard_coord(index, coord)
        if old_coord is not None:
            diff = R.diff_boundary(old_coord, coord, index)
            findings.append(Finding(
                rule_id=RULE_BOUNDARY_DIFF,
                verdict=PASS,
                message=("双标尺边界差异：%s → %s；新增 %d / 废止 %d / 口径调整 %d / 不变 %d")
                        % (diff["base"], diff["target"], diff["added_count"],
                           diff["removed_count"], diff["adjusted_count"],
                           diff["unchanged_count"]),
                anchor=basis.anchor(reg.CLAUSE_BOUNDARY),
                evidence={"base": diff["base"], "target": diff["target"],
                          "added": diff["added"], "removed": diff["removed"],
                          "adjusted": diff["adjusted"]},
            ))

    # 校核/配额路径依赖核算结果：未在 calc 路径算过且核算门控未拦 → 现算一次
    needs_result = bool({"check", "quota"} & set(scopes)) and "calc" not in gate_blocked
    if result is None and needs_result:
        result = C.compute(payload, coord,
                           index.effective_ruleset(coord, scope=R.SCOPE_CALC), units)

    if "check" in scopes and "check" not in gate_blocked:
        if result is None:  # 核算路径被门控拦截 → 校核依赖核算结果，不执行
            findings.append(Finding(
                rule_id="%s:%s" % (RULE_QUALITY_SKIP, "calc_dependency"),
                verdict=NOT_APPLICABLE,
                message="校核路径未执行：核算路径门控拦截，校核依赖核算结果",
                anchor=basis.anchor(reg.CLAUSE_GATE),
                evidence={"scope": "check", "reason": "calc_gate_blocked"},
            ))
        else:
            pack = index.effective_ruleset(coord, scope=R.SCOPE_CHECK)
            baseline = payload.get("baseline")
            baseline_calc = None
            if isinstance(baseline, Mapping):
                baseline_calc = C.compute(
                    baseline, coord,
                    index.effective_ruleset(coord, scope=R.SCOPE_CALC), units)
            report = C.run_checks(payload, result, coord, pack, units=units,
                                  baseline=baseline_calc)
            findings.extend(_quality_findings(report, basis))

    if "quota" in scopes and "quota" not in gate_blocked:
        if result is None:
            findings.append(Finding(
                rule_id="%s:%s" % (RULE_QUOTA, "calc_dependency"),
                verdict=NOT_APPLICABLE,
                message="配额路径未执行：核算路径门控拦截，试算依赖核算结果",
                anchor=basis.anchor(reg.CLAUSE_GATE),
                evidence={"scope": "quota", "reason": "calc_gate_blocked"},
            ))
        else:
            pack = index.effective_ruleset(coord, scope=R.SCOPE_QUOTA)
            params = dict(payload.get("quota_params") or {})
            for key, value in Q.quota_inputs_from_profile(payload).items():
                params.setdefault(key, value)
            quota_report = Q.compute_quota(pack, coord, result["total_raw"],
                                           params=params)
            findings.extend(_quota_findings(quota_report, basis))

    counts = {"pass": sum(1 for f in findings if f.verdict == PASS),
              "fail": sum(1 for f in findings if f.verdict == FAIL),
              "not_applicable": sum(1 for f in findings
                                    if f.verdict == NOT_APPLICABLE)}
    findings.append(Finding(
        rule_id=RULE_RESULT,
        verdict=PASS,
        message="三维核查完成（%s）：pass %d / fail %d / na %d"
                % (coord.key, counts["pass"], counts["fail"],
                   counts["not_applicable"]),
        anchor=basis.anchor(reg.CLAUSE_THREE_AXIS),
        evidence={"coordinate": coord.key, "scopes": list(scopes),
                  "counts": counts,
                  "total": None if result is None else result["total"],
                  "line_count": None if result is None else result["line_count"]},
    ))
    return findings


def _old_standard_coord(index, coord):
    """同年度同行业的旧版坐标（双标尺差异自动对照用）；不存在返回 None。"""
    standards = [s for s in index.standards if s != coord.standard]
    for standard in standards:
        try:
            candidate = index.resolve(standard, coord.year, coord.industry)
        except E.CoordinateError:
            continue
        return candidate
    return None


def validate_subject(subject: Mapping) -> None:
    """subject 结构校验（非法抛 :class:`E.GhgError`，内核映射 2）。"""
    if not isinstance(subject, Mapping):
        raise E.GhgError("输入必须是 JSON 对象，得到 %s" % type(subject).__name__)
    profile = subject.get("profile")
    if not isinstance(profile, Mapping):
        raise E.GhgError("缺少 profile（企业排放档案）")
    if not isinstance(profile.get("sources", []), (list, tuple)):
        raise E.GhgError("profile.sources 必须是数组")
    for item in profile.get("sources") or []:
        if not isinstance(item, Mapping) or not item.get("source_id"):
            raise E.GhgError("profile.sources 条目必须是含 source_id 的对象")
    baseline = subject.get("baseline")
    if baseline is not None and not isinstance(baseline, Mapping):
        raise E.GhgError("baseline 必须是对象（上一年度档案）")
    scopes = subject.get("scopes")
    if scopes is not None:
        if not isinstance(scopes, (list, tuple)) or not scopes:
            raise E.GhgError("scopes 必须是非空数组（calc / check / quota）")
        for scope in scopes:
            if scope not in _ALL_SCOPES:
                raise E.GhgError("未知检查路径：%r" % (scope,))


def evaluate_with_pack(subject: Mapping, basis: Basis, index, units) -> Iterable[Finding]:
    """判定用入口（测试可注入规则索引；``evaluate`` 用随包规则包走同一路径）。"""
    _require_basis_version(basis)
    validate_subject(subject)
    payload = dict(subject["profile"])
    if subject.get("baseline") is not None:
        payload["baseline"] = subject["baseline"]
    if subject.get("quota_params") is not None:
        payload["quota_params"] = subject["quota_params"]
    coord = R.parse_payload_coordinate(payload, index=index)
    scopes = list(subject.get("scopes") or _DEFAULT_SCOPES)
    return tuple(_findings(payload, coord, scopes, index, units, basis))


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_pack(subject, basis, reg.index(), reg.unit_table())


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "evaluate_with_pack",
           "validate_subject"]