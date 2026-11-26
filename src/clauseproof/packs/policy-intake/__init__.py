"""器官 ``policy-intake``：政策条目入库判定（schema + 日期 + 文号三态 + 部门归一 + 双键去重）。

规模：判定面来自 target-map ① 行的旧仓（统一 schema、发布日期真实性、文号三态、
部门别名最长优先、快照双键新增/重复、规范序）。

本器官只做一件事：**给一批已抓到的政策条目和上次快照，判这批条目能不能作为本期日报
的数据源——哪条缺字段、哪条文号解析不了、哪个部门认不出、哪些是新增哪些是重复**。
它不打印、不读文件、不读环境变量、不读时钟、不联网，也不带自己的参数解析器——入口只有
``clauseproof check policy-intake --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

=================================  ============================================
来源结论                             本器官 verdict
=================================  ============================================
必填字段齐 / 日期真实                 ``pass``（锚点：统一字段契约 / 日期契约）
必填缺失 / 日期不真实 / 出现禁字段     ``fail``（**必带锚点**；阻断 → 退出码 1）
文号 ``partial`` / ``unparsed``       ``not_applicable``（显式「未解析」，不阻断入库）
部门别名未命中（``alias_missing``）    ``not_applicable``（原样保留，不猜）
快照判定为**新增**                    ``pass``（锚点：双键契约）
快照判定为**重复**                    ``not_applicable``（不计入本期新增）
=================================  ============================================

依据只从条文库取：``basis.anchor(clause_id)``。**本器官的依据是数据契约条目，不是法规
条文**——它判的是「这批元数据能不能进日报」，没有可引的法律条款，故条目的 ``path`` 一律
写「数据契约 / …」，不冒法条名与文号。

条文库缺所需条款 → ``BasisMissing`` 冒到 CLI（退出码 3）；条文库版本与契约坐标不符 →
``ContractError``（退出码 3）。
"""

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

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
from .registry import (
    CLAUSE_DATE,
    CLAUSE_DIFF_KEYS,
    CLAUSE_ORDER,
    CLAUSE_ORG_ALIASES,
    CLAUSE_PCODE,
    CLAUSE_PCODE_SENTINEL,
    CLAUSE_SCHEMA,
    CLAUSE_SNAPSHOT_FIELDS,
    CONTRACT_VERSION,
    ORDER_RULE,
    STATUS_PARSED,
)

SLUG = "policy-intake"
VERSION = "0.2.0"
SUMMARY = "政策条目入库判定（schema + 日期真实性 + 文号三态 + 部门最长优先 + 双键去重）"

#: 输入必填字段
INPUT_FIELDS: Tuple[str, ...] = ("current",)

RULE_SCHEMA = "entry.schema"
RULE_DATE = "entry.date"
RULE_FIELDS = "entry.fields"
RULE_PCODE = "entry.pcode"
RULE_ORG = "org.alias"
RULE_DIFF = "diff.item"
RULE_FIRST_RUN = "diff.first-run"
RULE_ORDER = "snapshot.order"


def _require_basis_version(basis: Basis) -> None:
    if basis.version != CONTRACT_VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据契约坐标 %s 核对，条文库实为 %s"
            % (CONTRACT_VERSION, basis.version)
        )


def _entry_findings(record: Mapping, basis: Basis) -> List[Finding]:
    item_id = record["item_id"]
    findings = []

    missing = list(record["missing"])
    findings.append(Finding(
        rule_id="%s:%s" % (RULE_SCHEMA, item_id),
        verdict=FAIL if missing else PASS,
        message=("必填字段缺失 %d 项：%s（该条不得落库、不得进日报）"
                 % (len(missing), "、".join(missing))) if missing
                else "必填字段齐备",
        anchor=basis.anchor(CLAUSE_SCHEMA),
        evidence={"item_id": item_id, "missing": missing},
    ))

    findings.append(Finding(
        rule_id="%s:%s" % (RULE_DATE, item_id),
        verdict=PASS if record["date_valid"] else FAIL,
        message="发布日期真实（YYYY.MM.DD）" if record["date_valid"]
                else "发布日期不真实或形态不符（须 YYYY.MM.DD 且组合存在）",
        anchor=basis.anchor(CLAUSE_DATE),
        evidence={"item_id": item_id, "date_valid": record["date_valid"]},
    ))

    violations = list(record["forbidden"]) + list(record["extra"])
    findings.append(Finding(
        rule_id="%s:%s" % (RULE_FIELDS, item_id),
        verdict=FAIL if violations else PASS,
        message=("字段白名单违规 %d 项：%s（不做全文归档）"
                 % (len(violations), "、".join(violations))) if violations
                else "字段白名单通过",
        anchor=basis.anchor(CLAUSE_SNAPSHOT_FIELDS),
        evidence={"item_id": item_id, "forbidden": list(record["forbidden"]),
                  "extra": list(record["extra"])},
    ))

    parsed = record["pcode_parse"]
    status = parsed["status"]
    findings.append(Finding(
        rule_id="%s:%s" % (RULE_PCODE, item_id),
        verdict=PASS if status == STATUS_PARSED else NOT_APPLICABLE,
        message=("文号已解析：代字 %s / 年份 %s / 序号 %s"
                 % (parsed["agency_code"], parsed["year"], parsed["serial"]))
                if status == STATUS_PARSED
                else "文号未完整解析（status=%s），显式标记不编造" % status,
        anchor=basis.anchor(CLAUSE_PCODE if status == STATUS_PARSED
                            else CLAUSE_PCODE_SENTINEL),
        evidence={"item_id": item_id, "pcode": record["pcode"], "parse": dict(parsed)},
    ))

    for position, org in enumerate(record["orgs"]):
        findings.append(Finding(
            rule_id="%s:%s#%d" % (RULE_ORG, item_id, position),
            verdict=NOT_APPLICABLE if org["alias_missing"] else PASS,
            message=("部门「%s」未在别名表命中，原样保留（不猜）" % org["raw"])
                    if org["alias_missing"]
                    else "部门「%s」归一为「%s」" % (org["raw"], org["canonical"]),
            anchor=basis.anchor(CLAUSE_ORG_ALIASES),
            evidence={"item_id": item_id, "raw": org["raw"],
                      "canonical": org["canonical"], "alias_missing": org["alias_missing"]},
        ))
    return findings


def _diff_findings(result: Mapping, basis: Basis) -> List[Finding]:
    findings = []
    for record in result["records"]:
        duplicate = record["category"] == engine.CLASS_DUPLICATE
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_DIFF, record["item_id"]),
            verdict=NOT_APPLICABLE if duplicate else PASS,
            message=("相对上次快照为重复（命中键 %s），不计入本期新增"
                     % record["matched_by"]) if duplicate
                    else "相对上次快照为新增条目",
            anchor=basis.anchor(CLAUSE_DIFF_KEYS),
            evidence={"item_id": record["item_id"], "category": record["category"],
                      "matched_by": record["matched_by"],
                      "pcode": record["pcode"]},
        ))
    if not result["first_run"] and not result["order_observed"]:
        findings.append(Finding(
            rule_id=RULE_ORDER,
            verdict=NOT_APPLICABLE,
            message="输入未按规范序（pubtimeStr 倒序 / id 升序）；产物须按规范序输出",
            anchor=basis.anchor(CLAUSE_ORDER),
            evidence={"order_rule": ORDER_RULE},
        ))
    return findings


def _first_run_finding(result: Mapping, basis: Basis) -> List[Finding]:
    if not result["first_run"]:
        return []
    return [Finding(
        rule_id=RULE_FIRST_RUN,
        verdict=NOT_APPLICABLE,
        message="首次运行（无上次快照）→ 本次 %d 条全部计入新增" % result["current_count"],
        anchor=basis.anchor(CLAUSE_DIFF_KEYS),
        evidence={"current_count": result["current_count"]},
    )]


def evaluate_with_aliases(subject: Mapping, basis: Basis,
                          aliases: Optional[Mapping[str, str]] = None) -> Iterable[Finding]:
    """判定用入口（测试可注入别名表；``evaluate`` 用随包别名表走同一路径）。"""
    _require_basis_version(basis)
    result = engine.judge_intake(subject, aliases)

    findings: List[Finding] = []
    for record in result["records"]:
        findings.extend(_entry_findings(record, basis))
    findings.extend(_diff_findings(result, basis))
    findings.extend(_first_run_finding(result, basis))
    return tuple(findings)


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_aliases(subject, basis, None)


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "evaluate_with_aliases"]