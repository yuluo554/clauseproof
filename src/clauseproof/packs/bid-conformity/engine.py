"""符合性校核内核（**零 I/O / 零时钟 / 零网络 / 零政策数值字面量**）。

迁移的是来源产品的确定性校核面：按 ``rule_type`` 分派 handler、``only_if`` 类目门控、
否决联动、依据关联。口径原样保留：

- :func:`run_checks`（tender, bid）做**投标侧**七类检查；
  **招标侧**检查（开标早于递交截止）在 :func:`run_tender_checks`；
- 门控：分派任何 check_type 前逐条过 :func:`gates.rule_applies`（``only_if`` 类目隔离）；
- 结论：**只产非符合结论**（不符合 / 待人工确认）；符合明细由产品层报告展开；
- 依据：``Finding.basis`` 只有两类取值——法规引用「《法规名》第X条」（逐字命中条文块）
  或招标文件条款 id（``Q*``/``S*``/``R*``）；
- 查不到的确定性输入一律跳过不硬判（宁缺勿错）。

阈值参数来自 :mod:`registry`（规则包 ``params``），本模块不写死任何阈值；
金额比较容差（半分）是浮点比较精度，不是政策数值。
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from . import registry
from .amounts import render_amount, words_to_amount
from .gates import rule_applies
from .schema import (STATUS_MANUAL, STATUS_NONCONFORM, BidCard, Finding,
                     Qualification, TenderCard)

RULE_TYPES = (
    "qualification_match",
    "star_response",
    "arithmetic_consistency",
    "date_logic",
    "bond_check",
    "rejection_scan",
    "price_check",
)

#: 检查 id（规则包同名注册表）
CHK_Q_MISSING = "CHK-Q-01"
CHK_Q_EXPIRED = "CHK-Q-02"
CHK_Q_LEVEL = "CHK-Q-03"
CHK_Q_PERF = "CHK-Q-04"
CHK_Q_PERSONNEL = "CHK-Q-05"
CHK_SR_MISSING = "CHK-SR-01"
CHK_SR_DEV = "CHK-SR-02"
CHK_SR_DECLARED = "CHK-SR-03"
CHK_AR_WORDS = "CHK-AR-01"
CHK_AR_SUM = "CHK-AR-02"
CHK_AR_ITEMS = "CHK-AR-03"
CHK_BD_AMOUNT = "CHK-BD-01"
CHK_BD_FORM = "CHK-BD-02"
CHK_DT_VALIDITY = "CHK-DT-01"
CHK_DT_ORDER = "CHK-DT-02"
CHK_RJ_CAP = "CHK-RJ-01"
CHK_RJ_BOND = "CHK-RJ-02"
CHK_RJ_VALIDITY = "CHK-RJ-03"
CHK_RJ_STAR = "CHK-RJ-04"
CHK_PC_LOW = "CHK-PC-01"
CHK_CL_PAIRS = "CHK-CL-01"

CHECK_IDS = (
    CHK_Q_MISSING, CHK_Q_EXPIRED, CHK_Q_LEVEL, CHK_Q_PERF, CHK_Q_PERSONNEL,
    CHK_SR_MISSING, CHK_SR_DEV, CHK_SR_DECLARED,
    CHK_AR_WORDS, CHK_AR_SUM, CHK_AR_ITEMS,
    CHK_BD_AMOUNT, CHK_BD_FORM,
    CHK_DT_VALIDITY, CHK_DT_ORDER,
    CHK_RJ_CAP, CHK_RJ_BOND, CHK_RJ_VALIDITY, CHK_RJ_STAR,
    CHK_PC_LOW, CHK_CL_PAIRS,
)

#: 信用等级有序量表（可比较时按序比较；表外等级退化为等值比较）
LEVEL_RANK = {"C": 1, "CC": 2, "CCC": 3, "B": 4, "BB": 5, "BBB": 6,
              "A": 7, "AA": 8, "AAA": 9}

_STAR_VALUE_RE = re.compile(r"([0-9]+)\s*(个月|日内|天内|小时|分钟|天|日)")
_YEAR_RE = re.compile(r"(20[0-9]{2})年")
_AT_LEAST_RE = re.compile(r"至少\s*([0-9]+)\s*个")
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_CAP_RE = re.compile(r"人民币\s*([0-9][0-9,]*)\.([0-9]{2})\s*元")

#: 金额比较容差（半分）
_AMT_EPS = 0.005


def run_checks(tender: TenderCard, bid: BidCard, doc_text: Optional[str] = None,
               rules: Optional[List[Dict[str, Any]]] = None) -> List[Finding]:
    """``TenderCard`` + ``BidCard`` → ``List[Finding]``（投标侧确定性检查）。"""
    checker = _Checker(tender, bid, doc_text, rules)
    checker.check_qualifications()
    checker.check_star_responses()
    checker.check_arithmetic()
    checker.check_bond()
    checker.check_dates()
    checker.check_rejections()
    checker.check_price_hint()
    return checker.findings


def run_tender_checks(tender: TenderCard, doc_text: Optional[str] = None,
                      rules: Optional[List[Dict[str, Any]]] = None) -> List[Finding]:
    """``TenderCard`` → ``List[Finding]``（招标侧确定性检查：开标时间顺序）。"""
    checker = _Checker(tender, None, doc_text, rules)
    checker.check_tender_dates()
    return checker.findings


class _Checker:
    """单次校核上下文：规则注册表 + 门控文本 + 违规旗标（否决联动用）。"""

    def __init__(self, tender: TenderCard, bid: Optional[BidCard],
                 doc_text: Optional[str], rules: Optional[List[Dict[str, Any]]]):
        self.tender = tender
        self.bid = bid
        self.doc_text = doc_text or ""
        resolved = list(rules) if rules is not None else list(registry.RULES)
        self._by_id = {rule.get("id"): rule for rule in resolved
                       if isinstance(rule, dict) and rule.get("id")}
        self.findings = []
        self.flags = {}
        self._clause_cache = {}

    # ---------------------------------------------------------------- 基础设施
    def _active(self, check_id: str) -> bool:
        """分派门控：规则带 ``only_if`` 时关键词必须全部命中门控文本。"""
        rule = self._by_id.get(check_id)
        if rule is None:
            return True
        return rule_applies(rule, self.doc_text)

    def _param(self, check_id: str, key: str, default: Any) -> Any:
        rule = self._by_id.get(check_id) or {}
        params = rule.get("params") or {}
        return params.get(key, default)

    def emit(self, check_id: str, rule_type: str, status: str, risk_level: str,
             basis: List[str], message: str,
             evidence: Optional[List[Any]] = None) -> None:
        self.findings.append(Finding(
            check_id=check_id, status=status, risk_level=risk_level,
            message=message, basis=list(basis),
            evidence=[item for item in (evidence or ()) if item is not None],
        ))

    def _rejection_clause(self, *keywords: str):
        """按文本关键词定位否决条款（R1–R4 由文本语义识别，不硬编码条号顺序）。"""
        key = "|".join(keywords)
        if key not in self._clause_cache:
            self._clause_cache[key] = next(
                (row for row in self.tender.rejection_clauses
                 if any(keyword in row.text for keyword in keywords)), None)
        return self._clause_cache[key]

    def _price_cap(self) -> Optional[float]:
        """最高限价：从否决条款「最高限价（人民币x,xxx.00元）」内嵌金额抽取。"""
        clause = self._rejection_clause("最高限价")
        if clause is None:
            return None
        match = _CAP_RE.search(clause.text)
        if match is None:
            return None
        try:
            return float("%s.%s" % (match.group(1).replace(",", ""), match.group(2)))
        except ValueError:
            return None

    # ---------------------------------------------------------------- 招标侧
    def check_tender_dates(self) -> None:
        dates = self.tender.key_dates
        if not self._active(CHK_DT_ORDER):
            return
        if dates.open_time and dates.submit_deadline \
                and dates.open_time < dates.submit_deadline:
            self.emit(CHK_DT_ORDER, "date_logic", STATUS_NONCONFORM, "mid",
                      [registry.CITE_87_OPEN],
                      "开标时间 %s 早于投标文件递交截止时间 %s"
                      % (dates.open_time, dates.submit_deadline))

    # ---------------------------------------------------------------- 资格比对
    def check_qualifications(self) -> None:
        bid_rows = {row.item_id: row for row in (self.bid.qualifications or [])}
        for tender_row in self.tender.qualifications:
            bid_row = bid_rows.get(tender_row.item_id)
            if tender_row.category in ("qualification", "finance"):
                if bid_row is None:
                    if self._active(CHK_Q_MISSING):
                        self.emit(CHK_Q_MISSING, "qualification_match", STATUS_NONCONFORM,
                                  "high", [tender_row.item_id, registry.CITE_87_INVALID],
                                  "资格证明材料缺失：招标文件%s要求「%s」，投标文件未提供对应证明材料"
                                  % (tender_row.item_id, tender_row.requirement),
                                  self._qual_evidence(tender_row, bid_row))
                    continue
                self._check_qual_validity(tender_row, bid_row)
                if tender_row.level:
                    self._check_qual_level(tender_row, bid_row)
            elif tender_row.category == "performance":
                self._check_performance(tender_row)
            elif tender_row.category == "personnel":
                self._check_personnel(tender_row)

    def _qual_evidence(self, tender_row: Qualification, bid_row: Optional[Qualification]):
        evidence = []
        if bid_row is not None and bid_row.evidence is not None:
            evidence.append(bid_row.evidence)
        if tender_row.evidence is not None:
            evidence.append(tender_row.evidence)
        return evidence

    def _check_qual_validity(self, tender_row: Qualification,
                             bid_row: Qualification) -> None:
        if not self._active(CHK_Q_EXPIRED) or not bid_row.valid_until:
            return
        submit = self.tender.key_dates.submit_deadline
        deadline = submit[:10] if submit else None
        if tender_row.valid_until and (deadline is None or tender_row.valid_until < deadline):
            deadline = tender_row.valid_until
        if deadline and bid_row.valid_until < deadline:
            self.emit(CHK_Q_EXPIRED, "qualification_match", STATUS_NONCONFORM, "high",
                      [tender_row.item_id, registry.CITE_87_INVALID],
                      "%s 证明材料有效期至 %s，早于要求的生效截止 %s"
                      % (tender_row.item_id, bid_row.valid_until, deadline),
                      self._qual_evidence(tender_row, bid_row))

    def _check_qual_level(self, tender_row: Qualification, bid_row: Qualification) -> None:
        if not self._active(CHK_Q_LEVEL):
            return
        required, held = tender_row.level, bid_row.level
        if held is None:
            self.emit(CHK_Q_LEVEL, "qualification_match", STATUS_NONCONFORM, "mid",
                      [tender_row.item_id, registry.CITE_87_INVALID],
                      "%s 要求资质等级 %s，投标文件未提供等级信息"
                      % (tender_row.item_id, required),
                      self._qual_evidence(tender_row, bid_row))
            return
        required_rank, held_rank = LEVEL_RANK.get(required), LEVEL_RANK.get(held)
        if required_rank is not None and held_rank is not None:
            insufficient = held_rank < required_rank
        else:
            insufficient = held != required
        if insufficient:
            self.emit(CHK_Q_LEVEL, "qualification_match", STATUS_NONCONFORM, "mid",
                      [tender_row.item_id, registry.CITE_87_INVALID],
                      "%s 资质等级 %s 低于要求的 %s"
                      % (tender_row.item_id, held, required),
                      self._qual_evidence(tender_row, bid_row))

    def _check_performance(self, tender_row: Qualification) -> None:
        if not self._active(CHK_Q_PERF):
            return
        performance = self.bid.performance or []
        need = int(_AT_LEAST_RE.search(tender_row.requirement).group(1)) \
            if _AT_LEAST_RE.search(tender_row.requirement) else 1
        if not performance:
            self.emit(CHK_Q_PERF, "qualification_match", STATUS_NONCONFORM, "high",
                      [tender_row.item_id, registry.CITE_87_INVALID],
                      "未提供类似项目业绩（招标文件%s要求：%s）"
                      % (tender_row.item_id, tender_row.requirement))
            return
        year = _YEAR_RE.search(tender_row.requirement)
        if year is not None:
            since = "%s-01-01" % year.group(1)
            valid = [item for item in performance if (item.date or "") >= since]
            if len(valid) < need:
                self.emit(CHK_Q_PERF, "qualification_match", STATUS_NONCONFORM, "high",
                          [tender_row.item_id, registry.CITE_87_INVALID],
                          "类似业绩签订日期早于 %s 的超出允许数量：%s 要求 %s年以来至少 %d 个，"
                          "仅 %d 个符合" % (since, tender_row.item_id, year.group(1), need,
                                            len(valid)))

    def _check_personnel(self, tender_row: Qualification) -> None:
        if not self._active(CHK_Q_PERSONNEL):
            return
        people = self.bid.personnel or []
        if not people:
            self.emit(CHK_Q_PERSONNEL, "qualification_match", STATUS_NONCONFORM, "high",
                      [tender_row.item_id, registry.CITE_87_INVALID],
                      "未提供拟投入人员信息（招标文件%s要求：%s）"
                      % (tender_row.item_id, tender_row.requirement))
            return
        for token in _LATIN_TOKEN_RE.findall(tender_row.requirement):
            if not any(token in (person.cert_name or "") for person in people):
                self.emit(CHK_Q_PERSONNEL, "qualification_match", STATUS_NONCONFORM,
                          "high", [tender_row.item_id, registry.CITE_87_INVALID],
                          "未提供「%s」人员证书（招标文件%s要求：%s）"
                          % (token, tender_row.item_id, tender_row.requirement))

    # ---------------------------------------------------------------- 星号条款
    def check_star_responses(self) -> None:
        by_id = {row.star_id: row for row in (self.bid.star_responses or [])}
        for clause in self.tender.star_clauses:
            response = by_id.get(clause.item_id)
            if response is None:
                self._star_missing(clause)
                continue
            required = _star_value(clause.text)
            actual = _star_value(response.quote or "")
            if required is None or actual is None or required[1] != actual[1]:
                continue
            if not _star_violated(clause.text, required[0], actual[0]):
                continue
            declared = bool(response.deviation and response.deviation.strip() != "无偏离")
            if clause.marker == "★":
                self.flags["star_rejection"] = clause
                detail = "，且商务偏差表声明无偏离" if not declared else ""
                self.emit(CHK_SR_DEV, "star_response", STATUS_NONCONFORM, "high",
                          [clause.item_id],
                          "★条款%s响应值 %d%s 不满足要求值 %d%s%s（%s）"
                          % (clause.item_id, actual[0], actual[1], required[0], required[1],
                             detail, clause.text),
                          [clause.evidence])
            elif declared:
                self.emit(CHK_SR_DECLARED, "star_response", STATUS_MANUAL, "low",
                          [clause.item_id],
                          "▲条款%s响应值 %d%s 偏离要求值 %d%s，已声明负偏离，是否接受提请人工确认（%s）"
                          % (clause.item_id, actual[0], actual[1], required[0], required[1],
                             clause.text),
                          [clause.evidence])
            else:
                self.emit(CHK_SR_DEV, "star_response", STATUS_NONCONFORM, "mid",
                          [clause.item_id],
                          "▲条款%s响应值 %d%s 偏离要求值 %d%s，商务偏差表仍声明无偏离（%s）"
                          % (clause.item_id, actual[0], actual[1], required[0], required[1],
                             clause.text),
                          [clause.evidence])

    def _star_missing(self, clause) -> None:
        if not self._active(CHK_SR_MISSING):
            return
        if clause.marker == "★":
            self.flags["star_rejection"] = clause
            self.emit(CHK_SR_MISSING, "star_response", STATUS_NONCONFORM, "high",
                      [clause.item_id], "★条款%s未响应（%s）" % (clause.item_id, clause.text),
                      [clause.evidence])
        else:
            self.emit(CHK_SR_MISSING, "star_response", STATUS_NONCONFORM, "mid",
                      [clause.item_id], "▲条款%s未响应（%s）" % (clause.item_id, clause.text),
                      [clause.evidence])

    # ---------------------------------------------------------------- 算术复核
    def check_arithmetic(self) -> None:
        prices = self.bid.prices
        if prices is None:
            return
        if self._active(CHK_AR_WORDS) and prices.total_words \
                and prices.total_number is not None:
            try:
                words_value = words_to_amount(prices.total_words)
            except ValueError:
                words_value = None
            if words_value is not None and abs(words_value - prices.total_number) > _AMT_EPS:
                self.emit(CHK_AR_WORDS, "arithmetic_consistency", STATUS_NONCONFORM,
                          "high", [registry.CITE_87_PRICE_FIX],
                          "大写金额（%s）与小写金额（%s）不一致"
                          % (prices.total_words, render_amount(prices.total_number)))
        if self._active(CHK_AR_SUM) and prices.items_sum is not None \
                and prices.total_number is not None \
                and abs(prices.items_sum - prices.total_number) > _AMT_EPS:
            self.emit(CHK_AR_SUM, "arithmetic_consistency", STATUS_NONCONFORM, "high",
                      [registry.CITE_87_PRICE_FIX],
                      "分项合计（%s）与投标总价（%s）不一致"
                      % (render_amount(prices.items_sum), render_amount(prices.total_number)))
        if self._active(CHK_AR_ITEMS) and prices.items and prices.items_sum is not None:
            items_total = sum(float(item.amount or 0) for item in prices.items)
            if abs(items_total - prices.items_sum) > _AMT_EPS:
                self.emit(CHK_AR_ITEMS, "arithmetic_consistency", STATUS_NONCONFORM,
                          "high", [registry.CITE_87_PRICE_FIX],
                          "分项明细合计（%s）与分项合计（%s）不一致"
                          % (render_amount(items_total), render_amount(prices.items_sum)))

    # ---------------------------------------------------------------- 保证金
    def check_bond(self) -> None:
        required = self.tender.bond
        response = self.bid.bond_response
        if required is None or response is None:
            return
        clause = self._rejection_clause("保证金")
        basis = [clause.item_id, registry.CITE_87_INVALID] if clause is not None \
            else [registry.CITE_87_INVALID]
        if self._active(CHK_BD_AMOUNT) and response.amount is not None \
                and required.amount is not None \
                and response.amount < required.amount - _AMT_EPS:
            self.flags["bond"] = True
            self.emit(CHK_BD_AMOUNT, "bond_check", STATUS_NONCONFORM, "mid", basis,
                      "投标保证金 %s 低于要求的 %s"
                      % (render_amount(response.amount), render_amount(required.amount)))
        if self._active(CHK_BD_FORM) and response.forms:
            invalid = [form for form in response.forms if form not in (required.forms or [])]
            if invalid:
                self.flags["bond"] = True
                self.emit(CHK_BD_FORM, "bond_check", STATUS_NONCONFORM, "mid", basis,
                          "保证金缴纳形式「%s」不在允许形式（%s）内"
                          % ("、".join(invalid), "、".join(required.forms)))

    # ---------------------------------------------------------------- 时间逻辑
    def check_dates(self) -> None:
        required = self.tender.key_dates.validity_days
        actual = self.bid.key_dates.validity_days
        if not self._active(CHK_DT_VALIDITY):
            return
        clause = self._rejection_clause("有效期")
        if required and actual is not None and actual < required and clause is not None:
            self.flags["validity"] = True
            self.emit(CHK_DT_VALIDITY, "date_logic", STATUS_NONCONFORM, "mid",
                      [clause.item_id, registry.CITE_87_VALIDITY],
                      "投标有效期 %d 日历天，不足要求的 %d 日历天（%s）"
                      % (actual, required, clause.item_id))

    # ---------------------------------------------------------------- 否决扫描
    def check_rejections(self) -> None:
        self._check_over_cap()
        self._check_implied_bond()
        self._check_implied_validity()
        self._check_implied_star()

    def _check_over_cap(self) -> None:
        if not self._active(CHK_RJ_CAP):
            return
        cap = self._price_cap()
        prices = self.bid.prices
        if cap is None or prices is None or prices.total_number is None:
            return
        if prices.total_number > cap + _AMT_EPS:
            clause = self._rejection_clause("最高限价")
            self.emit(CHK_RJ_CAP, "rejection_scan", STATUS_NONCONFORM, "high",
                      [clause.item_id, registry.CITE_87_INVALID, registry.CITE_IMPL_REJECT],
                      "投标总价 %s 超过最高限价 %s，按 %s 投标无效"
                      % (render_amount(prices.total_number), render_amount(cap),
                         clause.item_id))

    def _check_implied_bond(self) -> None:
        if not self.flags.get("bond") or not self._active(CHK_RJ_BOND):
            return
        clause = self._rejection_clause("保证金")
        if clause is not None:
            self.emit(CHK_RJ_BOND, "rejection_scan", STATUS_NONCONFORM, "high",
                      [clause.item_id, registry.CITE_87_INVALID],
                      "未按要求提交投标保证金，命中否决条款%s（%s）"
                      % (clause.item_id, clause.text))

    def _check_implied_validity(self) -> None:
        if not self.flags.get("validity") or not self._active(CHK_RJ_VALIDITY):
            return
        clause = self._rejection_clause("有效期")
        if clause is not None:
            self.emit(CHK_RJ_VALIDITY, "rejection_scan", STATUS_NONCONFORM, "high",
                      [clause.item_id],
                      "投标有效期不足，命中否决条款%s（%s）" % (clause.item_id, clause.text))

    def _check_implied_star(self) -> None:
        if not self.flags.get("star_rejection") or not self._active(CHK_RJ_STAR):
            return
        clause = self._rejection_clause("★")
        if clause is not None:
            self.emit(CHK_RJ_STAR, "rejection_scan", STATUS_NONCONFORM, "high",
                      [clause.item_id, registry.CITE_IMPL_REJECT],
                      "★条款不满足或未响应，命中否决条款%s（%s）"
                      % (clause.item_id, clause.text))

    # ---------------------------------------------------------------- 价格提示
    def check_price_hint(self) -> None:
        if not self._active(CHK_PC_LOW):
            return
        cap = self._price_cap()
        prices = self.bid.prices
        if cap is None or prices is None or prices.total_number is None:
            return
        ratio = float(self._param(CHK_PC_LOW, "ratio", 0.8))
        clause = self._rejection_clause("最高限价")
        basis = [registry.CITE_87_LOW_PRICE] + ([clause.item_id] if clause is not None else [])
        if prices.total_number < ratio * cap - _AMT_EPS:
            self.emit(CHK_PC_LOW, "price_check", STATUS_MANUAL, "low", basis,
                      "投标总价 %s 低于最高限价的 %.0f%%，存在低于成本报价嫌疑，提请人工复核"
                      % (render_amount(prices.total_number), ratio * 100))


def _star_value(text: str) -> Optional[Tuple[int, str]]:
    """条款/响应文本 → (数值, 单位)；要求**恰好一处**「数字+单位」（多了少了都放弃）。"""
    matches = _STAR_VALUE_RE.findall(text or "")
    if len(matches) != 1:
        return None
    return int(matches[0][0]), matches[0][1]


def _star_violated(clause_text: str, required: int, actual: int) -> bool:
    """方向由条款文本限定词决定：不少于/不低于 = 下限；不超过/不高于/「X日内」= 上限。"""
    floor = any(keyword in clause_text for keyword in ("不少于", "不低于"))
    ceil = any(keyword in clause_text for keyword in ("不超过", "不高于")) \
        or "日内" in clause_text
    if floor and not ceil:
        return actual < required
    if ceil and not floor:
        return actual > required
    return False


__all__ = [
    "RULE_TYPES", "CHK_Q_MISSING", "CHK_Q_EXPIRED", "CHK_Q_LEVEL", "CHK_Q_PERF",
    "CHK_Q_PERSONNEL", "CHK_SR_MISSING", "CHK_SR_DEV", "CHK_SR_DECLARED",
    "CHK_AR_WORDS", "CHK_AR_SUM", "CHK_AR_ITEMS", "CHK_BD_AMOUNT", "CHK_BD_FORM",
    "CHK_DT_VALIDITY", "CHK_DT_ORDER", "CHK_RJ_CAP", "CHK_RJ_BOND", "CHK_RJ_VALIDITY",
    "CHK_RJ_STAR", "CHK_PC_LOW", "CHK_CL_PAIRS", "CHECK_IDS", "LEVEL_RANK",
    "run_checks", "run_tender_checks",
]