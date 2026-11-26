"""器官 ``cost-card``：菜品成本卡判定（进货单三态 → 净料换算 → 成本卡 → 定价 → 波动预警）。

规模：判定面来自 target-map ① 行的旧仓（进货单三态、换算公式 F1–F5、参数门控
按作用域、行级失败不中断整批、两期快照波动）。

本器官只做一件事：**给一份进货行 + 菜品配方 + 参数包，判这套成本卡能不能成立、
哪一步不成立、以及哪几道菜被价格波动波及**。它不打印、不读文件、不读环境变量、
不读时钟，也不带自己的参数解析器——入口只有
``clauseproof check cost-card --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

============================  ==================================================
来源结论                       本器官 verdict
============================  ==================================================
进货行 ``invalid``              ``fail``（必带锚点：进货单列名契约；阻断 → 退出码 1）
进货行 ``unknown``              ``not_applicable``（"没登记"≠"没问题"，必带锚点）
菜品成本卡成立                  ``pass``（锚点：净料率章节）
菜品被行级问题排除              ``fail``（锚点：出问题的净料率条目）
定价成立                        ``pass``（锚点：目标毛利率条目）
价格波动（超阈值/未超）          ``not_applicable``（**预警 ≠ 判定**，锚点：阈值条目）
============================  ==================================================

依据只从条文库取：``basis.anchor(clause_id)``。**本器官的依据是参数包条目与进货单
列名契约，不是法规条文**——来源仓 `data/README.md` 实测「《餐饮业成本核算规范》
SB/T 10573」查证失败（检索无此类标准），故不引用、不编造文号；参数条目的来源类型
（内置经验值 / 用户配置 / 快照）逐条写进 ``basis_ref.quote`` 与 ``evidence``。

条文库缺所需条款 → ``BasisMissing`` 冒到 CLI（退出码 3）；条文库版本与参数包快照
不符 → ``ContractError``（退出码 3）。
"""

from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Tuple

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
    CLAUSE_IMPORT_MAP,
    CLAUSE_SECTION_ALERT,
    CLAUSE_SECTION_PRICING,
    CLAUSE_SECTION_YIELD,
    PARAMS,
    PARAMS_VERSION,
)

SLUG = "cost-card"
VERSION = "0.2.0"
SUMMARY = "菜品成本卡判定（进货行三态 + 净料换算 + 毛利率定价 + 波动预警；依据=参数包条目）"

#: 输入必填字段
INPUT_FIELDS: Tuple[str, ...] = ("purchase_ledger",)

#: 规则单号（一条结论 = 规则 + 锚点）
RULE_ROW = "purchase.row"
RULE_DUPLICATE = "purchase.duplicate"
RULE_FILE = "purchase.file"
RULE_DISH = "dish.cost"
RULE_PRICING = "pricing.price"
RULE_ALERT_FOOD = "alert.food"
RULE_ALERT_DISH = "alert.dish"


def _require_basis_version(basis: Basis) -> None:
    if basis.version != PARAMS_VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据参数包快照 %s 核对，条文库实为 %s"
            % (PARAMS_VERSION, basis.version)
        )


def _num(value: Any) -> Any:
    """证据里的数值一律转字符串：Decimal 不进 JSON（避免浮点尾差与序列化歧义）。"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return value


# ------------------------------------------------------------------ 输入校验
def validate_subject(subject: Mapping) -> None:
    """输入结构校验（不合法抛 :class:`engine.CostError`，内核映射 2）。"""
    if not isinstance(subject, Mapping):
        raise engine.CostError("输入必须是 JSON 对象，得到 %s" % type(subject).__name__)

    ledger = subject.get("purchase_ledger")
    if not isinstance(ledger, Mapping):
        raise engine.CostError("缺少 purchase_ledger（进货单表头 + 行数组 + 来源）")
    header = ledger.get("header")
    if not isinstance(header, (list, tuple)):
        raise engine.CostError("purchase_ledger.header 必须是数组")
    rows = ledger.get("rows")
    if not isinstance(rows, (list, tuple)):
        raise engine.CostError("purchase_ledger.rows 必须是数组的数组")
    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)):
            raise engine.CostError(
                "purchase_ledger.rows[%d] 必须是数组（字段值按表头顺序排列）" % index)
    engine.validate_source(ledger.get("source"))

    dishes = subject.get("dishes")
    if dishes is not None:
        if not isinstance(dishes, (list, tuple)) or not dishes:
            raise engine.CostError("dishes 必须是非空数组")
        seen = set()
        for dish in dishes:
            if not isinstance(dish, Mapping) or not dish.get("name"):
                raise engine.CostError("BOM 中存在缺少 name 的菜品条目")
            if dish["name"] in seen:
                raise engine.CostError("BOM 中菜品名重复：%s" % dish["name"])
            seen.add(dish["name"])
            items = dish.get("items")
            if not isinstance(items, (list, tuple)):
                raise engine.CostError("菜品「%s」的 items 必须是数组" % dish.get("name"))
            for item in items:
                if not isinstance(item, Mapping) or not item.get("food"):
                    raise engine.CostError(
                        "菜品「%s」存在缺少 food 的配方行" % dish.get("name"))
        engine.validate_source(subject.get("dishes_source"))

    snapshots = subject.get("snapshots")
    if snapshots is not None:
        if not isinstance(snapshots, Mapping):
            raise engine.CostError("snapshots 必须是对象（old / new）")
        for key in ("old", "new"):
            snap = snapshots.get(key)
            if not isinstance(snap, Mapping):
                raise engine.CostError("snapshots.%s 缺失" % key)
            if not isinstance(snap.get("prices"), Mapping):
                raise engine.CostError("snapshots.%s.prices 必须是对象" % key)
            engine.validate_source(snap.get("source"))


# ------------------------------------------------------------------ 半成品判定
def _row_findings(parsed: Mapping, basis: Basis) -> List[Finding]:
    findings = []
    for issue in parsed["issues"]:
        verdict = FAIL if issue["status"] == engine.STATUS_INVALID else NOT_APPLICABLE
        findings.append(Finding(
            rule_id="%s:L%s:%s" % (RULE_ROW, issue["line"], issue["code"]),
            verdict=verdict,
            message=issue["reason"],
            anchor=basis.anchor(CLAUSE_IMPORT_MAP),
            evidence={
                "line": issue["line"],
                "code": issue["code"],
                "status": issue["status"],
            },
        ))
    return findings


def _dish_findings(parsed: Mapping, subject: Mapping, basis: Basis,
                   params: Mapping) -> Tuple[List[Finding], List[Dict[str, Any]]]:
    findings: List[Finding] = []
    dishes = subject.get("dishes")
    if not dishes or not parsed["rows"]:
        return findings, []

    library = engine.build_food_library(parsed["rows"])
    cost_params = _effective(params, "cost")
    result = engine.compute_costcard(dishes, library, cost_params,
                                     subject.get("dishes_source"))
    excluded = {}
    for issue in result["issues"]:
        excluded.setdefault(issue["where"], []).append(issue)

    for dish in dishes:
        where = "菜品「%s」·食材" % dish["name"]
        issues = []
        for key, items in sorted(excluded.items()):
            if key.startswith(where):
                issues.extend(items)
        if issues:
            food = issues[0]["where"].split("食材「")[-1].rstrip("」")
            findings.append(Finding(
                rule_id="%s:%s" % (RULE_DISH, dish["name"]),
                verdict=FAIL,
                message="菜品「%s」有 %d 行不成立，整道菜排除出成本卡：%s"
                        % (dish["name"], len(issues),
                           "；".join(item["reason"] for item in issues)),
                anchor=basis.anchor("param:yield-rate:%s" % food),
                evidence={"dish": dish["name"],
                          "issues": [{"code": item["code"], "where": item["where"],
                                      "reason": item["reason"]} for item in issues]},
            ))
        else:
            card = [c for c in result["cards"] if c["dish"] == dish["name"]][0]
            findings.append(Finding(
                rule_id="%s:%s" % (RULE_DISH, dish["name"]),
                verdict=PASS,
                message="菜品「%s」单份成本 %s 元（%d 行净料换算 + BOM 汇总）"
                        % (dish["name"], card["cost"], len(card["lines"])),
                anchor=basis.anchor(CLAUSE_SECTION_YIELD),
                evidence={"dish": dish["name"], "cost": _num(card["cost"]),
                          "lines": len(card["lines"]),
                          "foods": [line["food"] for line in card["lines"]]},
            ))

    if not result["cards"]:
        findings.append(Finding(
            rule_id="%s:no_usable_dishes" % RULE_FILE,
            verdict=FAIL,
            message="BOM 中 %d 道菜全部存在行级问题——成本卡为空" % len(dishes),
            anchor=basis.anchor(CLAUSE_SECTION_YIELD),
            evidence={"dishes": len(dishes), "cards": 0},
        ))
        return findings, []

    return findings, result["cards"]


def _pricing_findings(cards: List[Dict[str, Any]], basis: Basis,
                      params: Mapping) -> List[Finding]:
    if not cards:
        return []
    pricing_params = _effective(params, "pricing")
    rows = engine.compute_pricing(cards, pricing_params)
    findings = []
    for row in rows:
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_PRICING, row["dish"]),
            verdict=PASS,
            message="菜品「%s」建议售价 %s 元（成本 %s / 目标毛利率 %s / 实际毛利率 %s）"
                    % (row["dish"], row["suggested_price"], row["cost"],
                       row["target_margin"], row["actual_margin"]),
            anchor=basis.anchor(CLAUSE_SECTION_PRICING),
            evidence={"dish": row["dish"], "cost": _num(row["cost"]),
                      "target_margin": _num(row["target_margin"]),
                      "suggested_price": _num(row["suggested_price"]),
                      "actual_margin": _num(row["actual_margin"])},
        ))
    return findings


def _alert_findings(subject: Mapping, cards: List[Dict[str, Any]],
                    basis: Basis, params: Mapping) -> List[Finding]:
    snapshots = subject.get("snapshots")
    if not snapshots or not cards:
        return []

    old = snapshots["old"]
    new = snapshots["new"]
    engine.require_distinct_periods(old.get("date"), new.get("date"))
    alert_params = _effective(params, "alert")
    entry = alert_params.get("threshold") or {}
    if "value" not in entry:
        raise engine.FormulaError("参数包缺少波动预警阈值（需显式提供）")
    threshold = engine.to_decimal(entry["value"])

    changes = engine.diff_prices(old["prices"], new["prices"])
    by_name = {row["name"]: row for row in changes}

    # 判定域 = 本张菜单引用的食材（整份快照的 439 条市场价不属本次判定域）
    menu_foods = []
    for dish in subject.get("dishes") or []:
        for item in dish.get("items") or []:
            food = item["food"]
            if food not in menu_foods:
                menu_foods.append(food)

    findings = []
    for food in menu_foods:
        row = by_name.get(food)
        if row is None:
            continue
        flagged = row["change_rate"] is not None and abs(row["change_rate"]) >= threshold
        if row["change_rate"] is None:
            message = ("食材「%s」%s——缺对比基准，不臆造涨跌幅（预警不等于判定）"
                       % (food, "仅新期有" if row["status"] == "new" else "仅旧期有"))
        elif flagged:
            message = ("食材「%s」涨跌幅 %s 达阈值 %s（状态 %s）——预警项，需复核进价"
                       % (food, row["change_rate"], engine.quantize_rate(threshold),
                          row["status"]))
        else:
            message = ("食材「%s」涨跌幅 %s 未达阈值 %s（状态 %s）"
                       % (food, row["change_rate"], engine.quantize_rate(threshold),
                          row["status"]))
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_ALERT_FOOD, food),
            verdict=NOT_APPLICABLE,
            message=message,
            anchor=basis.anchor(CLAUSE_SECTION_ALERT),
            evidence={"food": food, "status": row["status"],
                      "old_price": _num(row["old_price"]),
                      "new_price": _num(row["new_price"]),
                      "change_rate": _num(row["change_rate"]),
                      "threshold": _num(engine.quantize_rate(threshold)),
                      "flagged": flagged,
                      "periods": [old.get("date"), new.get("date")]},
        ))

    for row in engine.impacted_dishes(cards, changes, old["prices"], new["prices"]):
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_ALERT_DISH, row["dish"]),
            verdict=NOT_APPLICABLE,
            message=("菜品「%s」受 %d 个食材价格变动影响：成本 %s → %s（差 %s，涨跌幅 %s）"
                     % (row["dish"], len(row["touched_foods"]), row["old_cost"],
                        row["new_cost"], row["delta"], row["change_rate"])),
            anchor=basis.anchor(CLAUSE_SECTION_ALERT),
            evidence={"dish": row["dish"],
                      "touched_foods": row["touched_foods"],
                      "old_cost": _num(row["old_cost"]),
                      "new_cost": _num(row["new_cost"]),
                      "delta": _num(row["delta"]),
                      "change_rate": _num(row["change_rate"])},
        ))
    return findings


def _effective(params: Mapping, scope: str) -> Mapping:
    """取作用域可用参数；``pending`` 条目 = 依据不完备 → 契约违约（退出码 3）。"""
    try:
        return engine.effective_params(params, scope)
    except engine.ParamsPending as exc:
        raise ContractError("依据包不完备：%s" % exc)


# ------------------------------------------------------------------ 器官入口
def evaluate_with_params(subject: Mapping, basis: Basis, params: Mapping) -> Iterable[Finding]:
    """判定用入口（测试可注入参数包；``evaluate`` 用随包参数包走同一路径）。"""
    _require_basis_version(basis)
    validate_subject(subject)

    parsed = engine.judge_rows(subject["purchase_ledger"]["header"],
                               subject["purchase_ledger"]["rows"],
                               source=subject["purchase_ledger"]["source"])
    findings = _row_findings(parsed, basis)

    if not parsed["rows"] and not parsed["issues"]:
        # 有表头却一行数据都没有：不是「判定成功 0 行」，是输入不可用（旧仓同口径）
        raise engine.CostError("进货单只有表头，无数据行")

    if not parsed["rows"]:
        # 文件级结论：整份进货单零可用行——不是某一行的错，是全行皆异常
        findings.append(Finding(
            rule_id="%s:no_usable_rows" % RULE_FILE,
            verdict=FAIL,
            message="进货单无任何可用行（%d 条异常）——食材库为空，成本卡无法成立"
                    % len(parsed["issues"]),
            anchor=basis.anchor(CLAUSE_IMPORT_MAP),
            evidence={"usable_rows": 0,
                      "status_counts": dict(parsed["status_counts"])},
        ))

    for food in engine.duplicate_names(parsed["rows"]):
        findings.append(Finding(
            rule_id="%s:%s" % (RULE_DUPLICATE, food),
            verdict=NOT_APPLICABLE,
            message="品名「%s」在进货单出现多次——食材库取最后一条价（取舍已登记）" % food,
            anchor=basis.anchor(CLAUSE_IMPORT_MAP),
            evidence={"food": food},
        ))

    dish_findings, cards = _dish_findings(parsed, subject, basis, params)
    findings.extend(dish_findings)
    findings.extend(_pricing_findings(cards, basis, params))
    findings.extend(_alert_findings(subject, cards, basis, params))
    return tuple(findings)


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    return evaluate_with_params(subject, basis, PARAMS)


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "evaluate_with_params",
           "validate_subject"]