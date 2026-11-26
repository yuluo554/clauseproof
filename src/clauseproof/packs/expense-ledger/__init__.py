"""器官 ``expense-ledger``：多平台账单真实支出对账（行三态 → 归一化 → 去重 → 语义 → 订阅）。

规模：判定面来自 target-map ① 行的旧仓（五段流水线判定内核：表头定位、行级
三态、商户名归一化、跨平台去重、语义识别、订阅识别与涨价追踪）。

本器官只做一件事：**给三平台导出的已解码账单行 + 规则包快照，判哪些行可用、
哪些行报废、哪些消费是跨平台重复、净支出/净收入是多少、哪些行是周期订阅、
哪里涨价了**。它不打印、不读文件、不读环境变量、不读时钟，也不带自己的参数
解析器——入口只有
``clauseproof check expense-ledger --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

====================================  ==========================================
来源结论                               本器官 verdict
====================================  =====================================
行级 ``invalid``（报废行）              ``fail``（必带锚点：列名映射契约；阻断 → 退出码 1）
文件级失败（表头/必填列/空文件/平台）    ``fail``（必带锚点：表头定位参数契约）
行级 ``unknown``（未登记收支取值）       ``not_applicable``（"没登记"≠"没问题"）
未登记列名                              ``not_applicable``
跨平台重复簇（非代表笔被排除）           ``pass``（锚点：去重窗口参数）
同平台候选簇（显式不合并）               ``not_applicable``（待人工复核，不阻断）
语义「未知」行（一等结论）               ``not_applicable``（必带锚点：未知一等结论契约）
订阅识别成立                             ``pass``（锚点：订阅参数条目）
订阅内涨价（观测到的变动）               ``pass``（锚点：涨价阈值条目）
对账完成（汇总）                         ``pass``（锚点：列名映射契约；不阻断与否由 fail 决定）
====================================  ==========================================

依据只从条文库取：``basis.anchor(clause_id)``。**本器官的依据是规则包参数条目
与数据契约，不是法规条文**——去重窗口、订阅周期、涨价阈值都是**经验默认值
（非官方）**，来源仓逐条标注；器官不冒充法规文号，参数来源类型逐条写进
``basis_ref.quote`` 与 ``evidence``。

条文库缺所需条款 → ``BasisMissing`` 冒到 CLI（退出码 3）；条文库版本与规则包
快照不符 → ``ContractError``（退出码 3）。

**解析层不进器官**：编码探测（BOM/UTF-8/GB18030 顺序）、XLSX 容器解包、
文件读取都留在输入层（`SKELETON-SPEC` §2：器官不得做文件 IO）——subject 收
**已解码的文本行**（``lines``）或**已解包的表格行**（xlsx 通道 ``table``）。
"""

from typing import Any, Dict, Iterable, List, Mapping

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
from . import registry as rules

SLUG = "expense-ledger"
VERSION = "0.1.0"
SUMMARY = ("多平台账单真实支出对账（行三态 + 商户归一化 + 跨平台去重 + 语义识别 "
           "+ 订阅识别；依据=规则包参数条目）")

#: 输入必填字段
INPUT_FIELDS = ("files",)

#: 规则单号（一条结论 = 规则 + 锚点）
RULE_ROW_INVALID = "ledger.row.invalid"
RULE_ROW_UNKNOWN = "ledger.row.unknown"
RULE_FILE = "ledger.file"
RULE_COLUMN_UNKNOWN = "ledger.column.unknown"
RULE_CLUSTER = "dedup.cluster"
RULE_UNKNOWN_ROW = "semantic.unknown"
RULE_SUBSCRIPTION = "subscription.item"
RULE_PRICE_CHANGE = "subscription.price_change"
RULE_RESULT = "ledger.result"


def _require_basis_version(basis: Basis) -> None:
    if basis.version != rules.PARAMS_VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据规则包快照 %s 核对，条文库实为 %s"
            % (rules.PARAMS_VERSION, basis.version)
        )


def _cents(amount_text) -> int:
    from decimal import Decimal, InvalidOperation
    try:
        return int((Decimal(str(amount_text)) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return 0


def _yuan(cents: int) -> str:
    return "%.2f" % (cents / 100)


# ------------------------------------------------------------------ 账本映射
def _findings(ledger: Mapping, basis: Basis) -> List[Finding]:
    findings: List[Finding] = []

    # ① 文件级失败：表头/必填列/空文件/平台不可识别（"这份文件不可用"= fail）
    for issue in ledger["file_issues"]:
        findings.append(Finding(
            rule_id="%s:%s:%s" % (RULE_FILE, issue["file"], issue["code"]),
            verdict=FAIL,
            message="%s：%s" % (issue["file"], issue["detail"]),
            anchor=basis.anchor(rules.CLAUSE_HEADER_LOCATE if issue["code"]
                                in ("header_not_found", "required_column_missing")
                                else rules.CLAUSE_IMPORT_MAP),
            evidence={"file": issue["file"], "code": issue["code"]},
        ))

    # ② 行级 invalid：报废行（宁可少一行，不可错位入库）
    for issue in ledger["issues"]:
        if issue["kind"] == "invalid":
            findings.append(Finding(
                rule_id="%s:%s" % (RULE_ROW_INVALID, issue["row_id"]),
                verdict=FAIL,
                message="%s：%s" % (issue["row_id"], issue["detail"]),
                anchor=basis.anchor(rules.CLAUSE_IMPORT_MAP),
                evidence={"row_id": issue["row_id"], "code": issue["code"],
                          "detail": issue["detail"]},
            ))
        elif issue["kind"] == "unknown" and issue.get("row_id"):
            # ③ 行级 unknown：入库且显式列出（"未知"是可用的行，不阻断）
            findings.append(Finding(
                rule_id="%s:%s" % (RULE_ROW_UNKNOWN, issue["row_id"]),
                verdict=NOT_APPLICABLE,
                message="%s：%s" % (issue["row_id"], issue["detail"]),
                anchor=basis.anchor(rules.CLAUSE_UNKNOWN_FIRST_CLASS),
                evidence={"row_id": issue["row_id"], "code": issue["code"]},
            ))
        elif issue.get("column"):
            # ④ 未登记列名：该列不入规范字段（原值保留在 raw_fields）
            findings.append(Finding(
                rule_id="%s:%s:%s" % (RULE_COLUMN_UNKNOWN, issue["source_file"],
                                      issue["column"]),
                verdict=NOT_APPLICABLE,
                message="%s：未登记列名 %s（原值保留，不参与判定）"
                        % (issue["source_file"], issue["column"]),
                anchor=basis.anchor(rules.CLAUSE_IMPORT_MAP),
                evidence={"file": issue["source_file"], "column": issue["column"]},
            ))

    # ⑤ 去重簇：跨平台重复 = pass（重复被识别、非代表笔已排除出净额）；
    #    同平台候选 = not_applicable（显式不合并，待人工复核）
    for cluster in ledger["dedup"]["clusters"]:
        if cluster["verdict"] == engine.VERDICT_CROSS:
            findings.append(Finding(
                rule_id="%s:%s" % (RULE_CLUSTER, cluster["cluster_id"]),
                verdict=PASS,
                message="跨平台重复簇 %s：%s 在 %d 个平台 %s 元（代表笔 %s，其余已排除出净额）"
                        % (cluster["cluster_id"], cluster["counterparty"],
                           len(cluster["platforms"]), cluster["amount"],
                           cluster["representative"]),
                anchor=basis.anchor(rules.CLAUSE_DEDUP_WINDOW),
                evidence={"cluster_id": cluster["cluster_id"],
                          "members": cluster["members"],
                          "platforms": cluster["platforms"],
                          "representative": cluster["representative"],
                          "amount": cluster["amount"],
                          "time_span_seconds": cluster["time_span_seconds"]},
            ))
        else:
            findings.append(Finding(
                rule_id="%s:%s" % (RULE_CLUSTER, cluster["cluster_id"]),
                verdict=NOT_APPLICABLE,
                message="同平台候选簇 %s：%s %s 元相邻两笔——不合并，待人工复核"
                        % (cluster["cluster_id"], cluster["counterparty"],
                           cluster["amount"]),
                anchor=basis.anchor(rules.CLAUSE_UNKNOWN_FIRST_CLASS),
                evidence={"cluster_id": cluster["cluster_id"],
                          "members": cluster["members"],
                          "amount": cluster["amount"]},
            ))

    # ⑥ 语义未知行（一等结论：不混入消费，也不假装不存在）
    for row in ledger["classify"]["unknown_rows"]:
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_UNKNOWN_ROW, row["id"]),
            verdict=NOT_APPLICABLE,
            message="语义未知行 %s（%s %s 元）：%s"
                    % (row["id"], row.get("counterparty"), row.get("amount"),
                       row["reason"]),
            anchor=basis.anchor(rules.CLAUSE_UNKNOWN_FIRST_CLASS),
            evidence={"row_id": row["id"], "reason": row["reason"],
                      "amount": row.get("amount")},
        ))

    # ⑦ 订阅识别成立 + 涨价记录（涨价只记观测到的变动，不做预测）
    for sub in ledger["subscription"]["subscriptions"]:
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_SUBSCRIPTION, sub["subscription_id"]),
            verdict=PASS,
            message="订阅 %s：%s 周期 %s，%d 期 %s → %s（金额 %s）"
                    % (sub["subscription_id"], sub["merchant"], sub["period_id"],
                       sub["repeats"], sub["first_time"], sub["last_time"],
                       "/".join(sub["amounts"])),
            anchor=basis.anchor(rules.CLAUSE_SUB_MIN_REPEATS),
            evidence={"subscription_id": sub["subscription_id"],
                      "merchant": sub["merchant"],
                      "period_id": sub["period_id"],
                      "repeats": sub["repeats"],
                      "entries": sub["entries"],
                      "gaps": sub["gaps"]},
        ))
        for change in sub["price_changes"]:
            findings.append(Finding(
                rule_id="%s:%s:%s" % (RULE_PRICE_CHANGE, sub["subscription_id"],
                                      change["entry"]),
                verdict=PASS,
                message="订阅 %s 涨价：%s %s 元 → %s 元（%s，变化 %s%%）"
                        % (sub["subscription_id"], change["entry"],
                           change["from_amount"], change["to_amount"],
                           change["to_time"], change["change_percent"]),
                anchor=basis.anchor(rules.CLAUSE_PRICE_CHANGE),
                evidence={"subscription_id": sub["subscription_id"],
                          "entry": change["entry"],
                          "from_amount": change["from_amount"],
                          "to_amount": change["to_amount"],
                          "change_percent": change["change_percent"]},
            ))

    # ⑧ 汇总（对账完成：净额 + 未知行合计；随 fail 与否决定退出码）
    net = ledger["net"]
    findings.append(Finding(
        rule_id=RULE_RESULT,
        verdict=PASS,
        message=("对账完成：%d 条记录（净支出 %s 元 / 净收入 %s 元）；"
                 "跨平台重复排除 %d 笔；语义未知 %d 行（合计 %s 元，未计入净额）；"
                 "订阅 %d 个、干扰行 %d 条；文件级失败 %d 个、报废行 %d 条")
                % (len(ledger["records"]), _yuan(net["net_expense_cents"]),
                   _yuan(net["net_income_cents"]),
                   len(net["excluded_duplicate_ids"]),
                   len(ledger["classify"]["unknown_rows"]),
                   _yuan(net["unknown_amount_cents"]),
                   len(ledger["subscription"]["subscriptions"]),
                   len(ledger["subscription"]["distractors"]),
                   len(ledger["file_issues"]),
                   sum(1 for i in ledger["issues"] if i["kind"] == "invalid")),
        anchor=basis.anchor(rules.CLAUSE_IMPORT_MAP),
        evidence={
            "records": len(ledger["records"]),
            "net_expense_cents": net["net_expense_cents"],
            "net_income_cents": net["net_income_cents"],
            "excluded_duplicate_ids": net["excluded_duplicate_ids"],
            "unknown_rows": len(ledger["classify"]["unknown_rows"]),
            "unknown_amount_cents": net["unknown_amount_cents"],
            "subscriptions": len(ledger["subscription"]["subscriptions"]),
            "distractors": len(ledger["subscription"]["distractors"]),
            "file_issues": len(ledger["file_issues"]),
            "invalid_rows": sum(1 for i in ledger["issues"] if i["kind"] == "invalid"),
        },
    ))
    return findings


# ------------------------------------------------------------------ 器官入口
def evaluate_with_rules(subject: Mapping, basis: Basis,
                        params: Mapping, aliases_doc: Mapping,
                        keywords_doc: Mapping) -> Iterable[Finding]:
    """判定用入口（测试可注入规则包；``evaluate`` 用随包规则包走同一路径）。"""
    _require_basis_version(basis)
    ledger = engine.run_ledger(subject, params, aliases_doc, keywords_doc)
    return tuple(_findings(ledger, basis))


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_rules(subject, basis, rules.params(),
                               rules.aliases_doc(), rules.keywords_doc())


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "evaluate_with_rules"]
