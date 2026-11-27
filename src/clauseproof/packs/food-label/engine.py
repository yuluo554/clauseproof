"""规则引擎内核（**零 I/O / 零时钟 / 零网络**）：按 ``check_type`` 分派，``only_if`` 门控。

迁移的是来源产品的双标尺规则引擎判定面（11 种检查类型全通 + 三级判定 +
依据待核对标记 + 双标尺差异对照）：

- ``check_type`` 全集：mandatory_field / format / nrv_recalc / energy_consistency /
  ingredient_order / claim_threshold / claim_whitelist / date_logic / conditional /
  nutrition_rows / allergen_notice；未知类型显式转"待人工确认"，不静默跳过；
- 处理器返回结论列表（行级结论如 NRV% 复算可一规则多结结论）；返回 ``None``
  表示前置缺失无法执行，计入 ``not_run``（不产生结论）；
- ``stats`` 口径：pass + fail + manual == checked == len(findings)；``skipped``
  为门控未命中跳过数；``not_run`` 为前置缺失未执行数；
- 门控纪律：``only_if`` 为 None 恒真；否则任一关键词命中卡片平文本即真，对
  全部 check_type 生效；
- 依据纪律：``basis.status != "已核对"`` 的规则产出结论自动置
  ``flagged_pending_basis``；
- 降级语义：``unresolved_detail[param] == "present_unparsed"``（标示行存在但
  解析失败）的强制/条件规则转"待人工确认"而非不合规——可能是解析覆盖不足
  而非标签违规；行整体缺失仍判不合规。

conditional 语义（GB 7718 豁免条款的确定性近似）：字段缺失时按 params 依次
判定——``manual_if_any`` 命中 → 待人工确认；``exempt_if_any`` 命中（且
``require_production_date`` 成立时生产日期在场）→ 豁免通过；否则不合规。

本模块收**参数卡 dict**（解析层已产出，含逐字证据）；文件读取与规则包装载
留装配面（与 ``Basis.from_json`` 同形态）。
"""

import re
from typing import Any, Dict, List, Mapping, Optional

from . import numeric

#: 结论三级判定（来源口径；账本映射在器官入口）
LEVEL_PASS = "合规"
LEVEL_FAIL = "不合规"
LEVEL_MANUAL = "待人工确认"

_LEVEL_STAT = {LEVEL_PASS: "pass", LEVEL_FAIL: "fail", LEVEL_MANUAL: "manual"}

#: 规范日期标示形式（FMT-DATE 规则的默认判定式）
CANONICAL_DATE_PATTERN = r"\d{4}年\d{2}月\d{2}日"

#: 可用的规则集（双标尺）
AVAILABLE_RULESETS = ("gb7718-2011", "gb7718-2025")

_RULESET_ALIAS = {
    "2011": ["gb7718-2011"],
    "2025": ["gb7718-2025"],
    "both": list(AVAILABLE_RULESETS),
}


class LabelError(ValueError):
    """输入不可用（卡片结构非法）；内核映射退出码 2。"""


def resolve_ruleset_ids(spec: str) -> List[str]:
    """把 ``--ruleset`` 取值解析为规则集 id 列表（2011 / 2025 / both）。"""
    ids = _RULESET_ALIAS.get(spec)
    if not ids:
        raise LabelError("未知规则集选择：%s（可选 2011 / 2025 / both）" % spec)
    return list(ids)


# ---------------------------------------------------------------------------
# 卡片视图与门控
# ---------------------------------------------------------------------------
def card_text(card: Mapping) -> str:
    """把参数卡序列化为门控匹配用的平文本。"""
    parts: List[str] = []
    for f in (card.get("fields") or {}).values():
        if isinstance(f, Mapping):
            parts.append(str(f.get("value")))
            evidence = f.get("evidence")
            if isinstance(evidence, Mapping):
                parts.append(str(evidence.get("quote", "")))
    parts.extend(card.get("ingredients") or [])
    parts.extend(card.get("claims") or [])
    parts.extend(str(row) for row in (card.get("nutrition_table") or []))
    return "\n".join(parts)


def gate_matches(only_if: Optional[Any], card: Mapping) -> bool:
    """类目隔离门控：only_if 为 None 恒真；否则任一关键词命中即真。"""
    if not only_if:
        return True
    keywords = only_if if isinstance(only_if, list) else [only_if]
    text = card_text(card)
    return any(k in text for k in keywords)


def _field(card: Mapping, key: str) -> Optional[Mapping]:
    return (card.get("fields") or {}).get(key)


def _field_evidence(card: Mapping, param: str) -> Optional[Mapping]:
    fld = _field(card, param)
    return fld.get("evidence") if fld is not None else None


def _row_evidence(row: Mapping) -> Optional[Mapping]:
    return row.get("evidence")


def _finding(rule: Mapping, ruleset_id: str, level: str, message: str,
             evidence: Optional[Mapping] = None,
             advice: Optional[str] = None) -> Dict[str, Any]:
    return {
        "rule_id": rule["id"],
        "level": level,
        "message": message,
        "ruleset_id": ruleset_id,
        "basis": dict(rule.get("basis") or {}),
        "evidence": evidence,
        "advice": advice if advice is not None else rule.get("advice", ""),
        "flagged_pending_basis": False,
    }


def _manual_present_unparsed(card: Mapping, rule: Mapping,
                             ruleset_id: str) -> Optional[Dict[str, Any]]:
    """标示行存在但结构化解析失败 → 待人工确认（区别于行整体缺失的不合规）。"""
    detail = (card.get("unresolved_detail") or {}).get(rule["param"])
    if detail != "present_unparsed":
        return None
    return _finding(
        rule, ruleset_id, LEVEL_MANUAL,
        "『%s』的标示行存在但未能解析出结构化值，转待人工确认"
        "（可启用 LLM 兜底自动抽取后重查）。" % rule["name"],
        advice=rule.get("advice", ""),
    )


# ---------------------------------------------------------------------------
# check_type 处理器（返回结论列表；返回 None = 前置缺失，not_run）
# ---------------------------------------------------------------------------
def _check_mandatory_field(card, rule, ruleset_id, reference):
    param = rule["param"]
    if param == "nutrition_table":  # 营养表为顶层列表，不在 fields
        present = bool(card.get("nutrition_table"))
        evidence = None
    else:
        fld = _field(card, param)
        present = fld is not None
        evidence = fld.get("evidence") if fld is not None else None
    if present:
        return [_finding(rule, ruleset_id, LEVEL_PASS,
                         "已标示（%s）。" % rule["name"], evidence)]
    manual = _manual_present_unparsed(card, rule, ruleset_id)
    if manual is not None:
        return [manual]
    return [_finding(
        rule, ruleset_id, LEVEL_FAIL,
        "未检出『%s』对应的标示内容（参数 %s）。" % (rule["name"], param),
    )]


def _check_conditional(card, rule, ruleset_id, reference):
    """带豁免/人工分支的标示要求（2011 §4.3.1 / 2025 §10.1 豁免条款）。"""
    params = rule.get("params") or {}
    param = rule["param"]
    fld = _field(card, param)
    if fld is not None:
        return [_finding(rule, ruleset_id, LEVEL_PASS,
                         "已标示（%s）。" % rule["name"], fld.get("evidence"))]

    manual = _manual_present_unparsed(card, rule, ruleset_id)
    if manual is not None:
        return [manual]

    text = card_text(card)
    for kw in params.get("manual_if_any", []):
        if kw in text:
            return [_finding(
                rule, ruleset_id, LEVEL_MANUAL,
                "未标示『%s』，且标签含『%s』：豁免与否需人工判定。" % (rule["name"], kw)
                + params.get("manual_note", ""),
            )]
    exempt_hit = next((kw for kw in params.get("exempt_if_any", []) if kw in text), None)
    if exempt_hit is not None:
        if params.get("require_production_date") and _field(card, "production_date") is None:
            pass  # 豁免前提（已标示生产日期）不成立 → 继续按未标示处理
        else:
            return [_finding(
                rule, ruleset_id, LEVEL_PASS,
                "未标示『%s』，但标签含『%s』，属标准豁免标示情形。"
                % (rule["name"], exempt_hit),
            )]
    return [_finding(
        rule, ruleset_id, LEVEL_FAIL,
        "未检出『%s』对应的标示内容（参数 %s），且不属于可豁免情形。"
        % (rule["name"], param),
    )]


def _check_format(card, rule, ruleset_id, reference):
    """标示格式核验：对 evidence.quote 全字匹配 params.pattern（缺省规范日期式）。"""
    fld = _field(card, rule["param"])
    if fld is None or fld.get("evidence") is None:
        return None  # 缺失由强制标示规则覆盖，格式规则不运行
    params = rule.get("params") or {}
    pattern = params.get("pattern", CANONICAL_DATE_PATTERN)
    expect_desc = params.get("expect_desc", "YYYY年MM月DD日")
    quote = fld["evidence"].get("quote", "")
    if re.fullmatch(pattern, quote):
        return [_finding(rule, ruleset_id, LEVEL_PASS,
                         "标示格式规范：『%s』。" % quote, fld["evidence"])]
    return [_finding(
        rule, ruleset_id, LEVEL_FAIL,
        "标示格式不规范：『%s』不符合%s形式（%s）。"
        % (quote, expect_desc, params.get("format_note", "应按年月日顺序、月日两位标示")),
        fld["evidence"],
    )]


def _check_nrv_recalc(card, rule, ruleset_id, reference):
    """NRV% 行级复算（修约间隔 1，容差 ±1）；每份标示行转待人工确认。"""
    if not card.get("nutrition_table"):
        return None
    findings: List[Dict[str, Any]] = []
    per_serving = [r for r in card["nutrition_table"]
                   if r.get("per_serving") and r.get("nrv_percent") is not None]
    for row in per_serving:
        findings.append(_finding(
            rule, ruleset_id, LEVEL_MANUAL,
            "营养行『%s』按每份标示，NRV%% 无法按每100g(mL)复算，转待人工确认。"
            % row.get("name"),
            _row_evidence(row),
        ))
    for m in numeric.check_nrv_rows(reference, card):
        findings.append(_finding(
            rule, ruleset_id, LEVEL_FAIL,
            "营养行『%s』NRV%% 标示 %s%%，按含量复算应为 %s%%"
            "（偏差 %+.0f 个百分点，超修约容差 ±1）。"
            % (m["name"], m["shown"], m["recomputed"], m["diff"]),
            _row_evidence(m),
        ))
    if findings:
        return findings
    checked = sum(1 for r in card["nutrition_table"] if r.get("nrv_percent") is not None)
    return [_finding(rule, ruleset_id, LEVEL_PASS,
                     "营养成分表 %d 行 NRV%% 复算一致（修约间隔 1）。" % checked)]


def _check_energy_consistency(card, rule, ruleset_id, reference):
    """能量折算一致性：E=round(17P+37F+17C) vs 标示能量（表2 低报方向）。"""
    if not card.get("nutrition_table"):
        return None
    names = ("能量", "蛋白质", "脂肪", "碳水化合物")
    rows = {n: next((r for r in card["nutrition_table"] if r.get("name") == n), None)
            for n in names}
    if any(rows[n] is None for n in names):
        return None
    if any(rows[n].get("per_serving") for n in names):
        return [_finding(rule, ruleset_id, LEVEL_MANUAL,
                         "营养成分表按每份标示，能量折算一致性无法按每100g(mL)复算，"
                         "转待人工确认。")]
    result = numeric.check_energy_consistency(reference, card)
    if result is None:  # 单位/数值形态不可复算
        return [_finding(rule, ruleset_id, LEVEL_MANUAL,
                         "能量或供能成分含量单位/数值形态无法复算，转待人工确认。",
                         _row_evidence(rows["能量"]))]
    if result["verdict"] == "violation":
        return [_finding(
            rule, ruleset_id, LEVEL_FAIL,
            "能量标示 %s kJ，按蛋白质/脂肪/碳水化合物含量折算应为 %s kJ，"
            "超出允许误差（实际值 ≤120%% 标示值，表2）。"
            % (result["shown_energy_kj"], result["recomputed_energy_kj"]),
            _row_evidence(rows["能量"]),
        )]
    return [_finding(rule, ruleset_id, LEVEL_PASS,
                     "能量标示值与折算值一致（折算 %s kJ，系数 17/37/17，2025 §2.3）。"
                     % result["recomputed_energy_kj"])]


def _check_ingredient_order(card, rule, ruleset_id, reference):
    """配料递减序先验对：规则 params.ordered_pairs 内的已知先后关系被颠倒才报。"""
    fld = _field(card, "ingredients")
    if fld is None:
        return None
    items = card.get("ingredients") or []
    pairs = (rule.get("params") or {}).get("ordered_pairs", [])
    for before, after in pairs:
        if before in items and after in items and items.index(before) > items.index(after):
            return [_finding(
                rule, ruleset_id, LEVEL_FAIL,
                "配料『%s』标示在『%s』之前：两者均属加入量 >2%% 的主配料"
                "（品类配方先验），不符合加入量递减顺序要求。" % (after, before),
                fld.get("evidence"),
            )]
    return [_finding(rule, ruleset_id, LEVEL_PASS,
                     "配料表未检出可判定的递减序错误（先验对全部有序或不适用）。",
                     fld.get("evidence"))]


def _check_claim_threshold(card, rule, ruleset_id, reference):
    """营养声称阈值核验（阈值表读随包 nutrient-reference.claim_thresholds）。"""
    if not card.get("claims"):
        return [_finding(rule, ruleset_id, LEVEL_PASS, "未检出营养声称，无需阈值核验。")]
    checks = numeric.claim_threshold_checks(reference, card)
    findings: List[Dict[str, Any]] = []
    for c in checks:
        if c["verdict"] == "fail":
            findings.append(_finding(
                rule, ruleset_id, LEVEL_FAIL,
                "声称『%s』不成立：%s含量 %s%s/100g(mL)，超过该声称阈值 ≤%s%s/100g(mL)"
                "（表C.1，已核对）。"
                % (c["claim"], c["nutrient"], c["amount"], c["unit"],
                   c["max_per_100"], c["unit"]),
                _row_evidence(c) if c.get("evidence") else None,
            ))
        elif c["verdict"] in ("no_row", "per_serving"):
            findings.append(_finding(
                rule, ruleset_id, LEVEL_MANUAL,
                "声称『%s』的 %s含量无法从营养成分表复算（%s），转待人工确认。"
                % (c["claim"], c["nutrient"],
                   "缺该行" if c["verdict"] == "no_row" else "按份标示"),
                _row_evidence(c) if c.get("evidence") else None,
            ))
    if findings:
        return findings
    hit = "、".join(sorted({c["claim_contains"] for c in checks})) or "无"
    return [_finding(rule, ruleset_id, LEVEL_PASS,
                     "声称阈值核验通过（命中阈值项：%s）。" % hit)]


def _check_claim_whitelist(card, rule, ruleset_id, reference):
    """声称用语核验：params.forbidden_terms 内的禁用语出现在声称中即不合规。"""
    if not card.get("claims"):
        return [_finding(rule, ruleset_id, LEVEL_PASS, "未检出声称用语，无需核验。")]
    params = rule.get("params") or {}
    forbidden = params.get("forbidden_terms", [])
    kind = params.get("term_kind", "禁用语")
    hits: List[str] = []
    for claim in card["claims"]:
        matched = [t for t in forbidden if t in claim]
        if matched:
            hits.append("『%s』（命中%s）" % (claim, "、".join(matched)))
    if hits:
        fld = _field(card, "claims")
        return [_finding(
            rule, ruleset_id, LEVEL_FAIL,
            "检出%s声称：%s。" % (kind, "；".join(hits)),
            fld.get("evidence") if fld is not None else None,
        )]
    return [_finding(rule, ruleset_id, LEVEL_PASS,
                     "声称用语核验通过（%d 条声称未命中%s）。" % (len(card["claims"]), kind))]


def _check_date_logic(card, rule, ruleset_id, reference):
    """日期逻辑自洽：到期日 = 生产日期 + 保质期（生成器约定口径）。"""
    prod = _field(card, "production_date")
    shelf = _field(card, "shelf_life")
    expiry = _field(card, "expiry_date")
    if prod is None or shelf is None or expiry is None:
        return None  # 缺失由强制标示规则覆盖；不自洽性缺输入不运行
    shelf_value = shelf["value"].get("value") if isinstance(shelf.get("value"), dict) else None
    shelf_unit = shelf["value"].get("unit") if isinstance(shelf.get("value"), dict) else None
    if shelf_value is None or shelf_unit is None:
        return [_finding(rule, ruleset_id, LEVEL_MANUAL,
                         "保质期标示无法解析出『数值+单位』，到期日自洽性转待人工确认。")]
    try:
        expected = numeric.compute_expected_expiry(str(prod["value"]), shelf_value, shelf_unit)
    except (ValueError, TypeError):
        return [_finding(rule, ruleset_id, LEVEL_MANUAL,
                         "保质期单位『%s』暂不支持自动推算，转待人工确认。" % shelf_unit)]
    try:
        shown = numeric._Date.from_iso(str(expiry["value"]))
    except (ValueError, TypeError):
        return [_finding(rule, ruleset_id, LEVEL_MANUAL,
                         "保质期到期日无法解析为日期，自洽性转待人工确认。")]
    if shown == expected:
        return [_finding(rule, ruleset_id, LEVEL_PASS,
                         "到期日自洽：生产日期 %s + 保质期 %s%s = %s。"
                         % (prod["value"], shelf_value, shelf_unit, expected.isoformat()),
                         expiry.get("evidence"))]
    return [_finding(
        rule, ruleset_id, LEVEL_FAIL,
        "日期逻辑矛盾：标示到期日 %s，按生产日期 %s + 保质期 %s%s 推算应为 %s。"
        % (shown.isoformat(), prod["value"], shelf_value, shelf_unit,
           expected.isoformat()),
        expiry.get("evidence"),
    )]


def _check_nutrition_rows(card, rule, ruleset_id, reference):
    """强制营养行完整性（GB 28050-2025 §4.1：能量+6 营养素）。"""
    if not card.get("nutrition_table"):
        return None
    required = (rule.get("params") or {}).get("required_rows", [])
    present = {row.get("name") for row in card["nutrition_table"]}
    findings: List[Dict[str, Any]] = []
    for name in required:
        if name not in present:
            findings.append(_finding(
                rule, ruleset_id, LEVEL_FAIL,
                "营养成分表缺『%s』行：该营养素属强制标示内容（%s）。"
                % (name, (rule.get("basis") or {}).get("clause", "")),
            ))
    if findings:
        return findings
    return [_finding(rule, ruleset_id, LEVEL_PASS,
                     "强制营养行完整（%d 项：%s）。" % (len(required), "、".join(required)))]


def _check_allergen_notice(card, rule, ruleset_id, reference):
    """致敏物质提示（GB 7718-2025 §4.12 八类致敏物质）。

    确定性近似：只检索配料表；提示行在位 → 通过；配料含八类关键词而提示
    缺失 → 不合规；无致敏配料 → 通过。
    """
    fld = _field(card, "allergen_notice")
    if fld is not None:
        return [_finding(rule, ruleset_id, LEVEL_PASS,
                         "已标示致敏物质提示信息（§4.12 / 附录D）。", fld.get("evidence"))]
    keywords = (rule.get("params") or {}).get("allergen_keywords", [])
    hits = sorted({kw for kw in keywords
                   for ing in (card.get("ingredients") or []) if kw in ing})
    if hits:
        ing_fld = _field(card, "ingredients")
        return [_finding(
            rule, ruleset_id, LEVEL_FAIL,
            "配料含致敏物质（%s，§4.12.1 八类），但未检出致敏物质提示信息。"
            % "、".join(hits),
            ing_fld.get("evidence") if ing_fld is not None else None,
        )]
    return [_finding(rule, ruleset_id, LEVEL_PASS,
                     "配料未检出八类致敏物质关键词，提示信息非强制。")]


def _check_unsupported(card, rule, ruleset_id, reference):
    return [_finding(
        rule, ruleset_id, LEVEL_MANUAL,
        "check_type『%s』尚未实现，转待人工确认。" % rule["check_type"],
        advice="该检查类型不在已迁移的 11 种之内。",
    )]


_HANDLERS = {
    "mandatory_field": _check_mandatory_field,
    "conditional": _check_conditional,
    "format": _check_format,
    "nrv_recalc": _check_nrv_recalc,
    "energy_consistency": _check_energy_consistency,
    "ingredient_order": _check_ingredient_order,
    "claim_threshold": _check_claim_threshold,
    "claim_whitelist": _check_claim_whitelist,
    "date_logic": _check_date_logic,
    "nutrition_rows": _check_nutrition_rows,
    "allergen_notice": _check_allergen_notice,
}


def run_ruleset(card: Mapping, ruleset: Mapping,
                reference: numeric.NutrientReference) -> Dict[str, Any]:
    """对参数卡跑一个规则集，输出带统计的结果。"""
    ruleset_id = ruleset["ruleset_id"]
    findings: List[Dict[str, Any]] = []
    stats = {"checked": 0, "skipped": 0, "not_run": 0,
             "pass": 0, "fail": 0, "manual": 0}

    for rule in ruleset.get("rules", []):
        if not gate_matches(rule.get("only_if"), card):
            stats["skipped"] += 1
            continue
        handler = _HANDLERS.get(rule["check_type"], _check_unsupported)
        produced = handler(card, rule, ruleset_id, reference)
        if not produced:  # None / 空列表 → 前置缺失未运行
            stats["not_run"] += 1
            continue
        pending = (rule.get("basis") or {}).get("status") != "已核对"
        for finding in produced:
            finding["flagged_pending_basis"] = pending
            findings.append(finding)
            stats[_LEVEL_STAT[finding["level"]]] += 1
        stats["checked"] += 1

    return {"ruleset_id": ruleset_id, "findings": findings, "stats": stats}


def run_dual(card: Mapping, rulesets: Mapping[str, Mapping],
             reference: numeric.NutrientReference,
             ruleset_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """同一参数卡分别跑多个规则集（双标尺）。"""
    return {rid: run_ruleset(card, rulesets[rid], reference) for rid in ruleset_ids}


def dual_diff(results: Mapping[str, Mapping], baseline_id: str,
              target_id: str) -> Dict[str, Any]:
    """新旧规则集不合规项对照：target 相对 baseline 新增/消除的不合规规则。"""
    base_fails = {f["rule_id"] for f in results[baseline_id]["findings"]
                  if f["level"] == LEVEL_FAIL}
    target_fails = {f["rule_id"] for f in results[target_id]["findings"]
                    if f["level"] == LEVEL_FAIL}
    return {
        "baseline": baseline_id,
        "target": target_id,
        "new_fails": sorted(target_fails - base_fails),
        "resolved_fails": sorted(base_fails - target_fails),
    }