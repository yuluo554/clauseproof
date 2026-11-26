"""规则包快照（**Python 字面量，零文件读取**）。

迁移的是来源产品随包冻结的三份城市规则包：全国层（民法典）+ 北京 + 上海。
三条纪律原样保留：

1. **零政策字面量**：本模块是器官内唯一的政策数值定义点；``engine.py`` 只出现
   运算符与派发，不出现任何阈值/期限数值。
2. **每条规则必须挂锚点**：``clause_id`` 指向条文库里的一条已核对引文（条款号 +
   法条原文逐字引用 + 来源）。缺锚点的规则**不得进入判定路径**（加载侧再拦一次，
   不只依赖上游生成器）。
3. **``status`` 是唯一判定门控**：``verified`` 参与判定，其余记入未启用清单
   （``clause_status`` 只做可证性展示，不阻断判定）。

条文坐标是**复合版本**（三份规则包各自的版本）：``cn-2021.01+bj-2024.10+sh-2023.02``。
同一条款下不同款项的引文**各自成条**（``#n`` 按来源规则声明序）——来源规则包对
「第三十六条」的不同款项各引一句原文，把三句合成一条会让 ``quote`` 不再逐字可核。

``data/rulesets.json`` 与 ``data/clauses.json`` 是来源资产的只读转写，随 wheel 进包，
并由 ``tests/test_lease_terms.py`` 的漂移门逐条比对。
"""

from typing import Any, Dict, Mapping, Tuple

#: 条文库坐标（三份规则包版本的复合值）
CLAUSES_VERSION = "cn-2021.01+bj-2024.10+sh-2023.02"

#: 城市 → (ruleset_id, 规则包版本)
CITY_RULESETS: Mapping[str, Tuple[str, str]] = {
    "全国": ("cn-2021.01", "2021.01"),
    "北京": ("bj-2024.10", "2024.10"),
    "上海": ("sh-2023.02", "2023.02"),
}

#: 规则元组的列序（固定，防按位置取错列）
RULE_COLUMNS: Tuple[str, ...] = (
    "rule_id", "title", "check_type", "scope", "param", "op", "value", "unit",
    "applies_if", "effect", "severity", "source_id", "clause", "status", "clause_id",
)

_PARTY_ANY = {"party": ("any",)}
_PARTY_ENTERPRISE = {"party": ("enterprise",)}
_AFFORDABLE_ANY = {"party": ("any",), "lease_kind": ("affordable",)}

#: 规则表（顺序 = 来源规则包声明序）
RULE_TABLE: Mapping[str, Tuple[Tuple[Any, ...], ...]] = {
    "全国": (
        ("CN-LEASE-TERM-MAX", "租赁期限不得超过二十年", "numeric_limit", "calc",
         "lease_term_years", "<=", 20, "年", _PARTY_ANY, "standing_obligation", "high",
         "SRC-CN-CIVIL-CODE", "第七百零五条", "verified", "civil-code:第七百零五条"),
        ("CN-ELEMENT-COMPLETENESS", "租赁合同应包含法定要素", "element_completeness",
         "check", "has_elements", None, None, None, _PARTY_ANY, "standing_obligation",
         "low", "SRC-CN-CIVIL-CODE", "第七百零四条", "verified",
         "civil-code:第七百零四条"),
        ("CN-RENT-PAY-PERIOD", "租金支付期限未约定时的法定补充规则",
         "deadline_obligation", "check", "rent_pay_period_declared", None, None, None,
         _PARTY_ANY, "standing_obligation", "low", "SRC-CN-CIVIL-CODE", "第七百二十一条",
         "verified", "civil-code:第七百二十一条"),
        ("CN-WRITTEN-FORM-6M", "租赁期限六个月以上的应采用书面形式",
         "element_completeness", "check", "has_elements", None, None, None, _PARTY_ANY,
         "standing_obligation", "low", "SRC-CN-CIVIL-CODE", "第七百零七条", "verified",
         "civil-code:第七百零七条"),
    ),
    "北京": (
        ("BJ-DEPOSIT-MAX-1M", "住房租赁企业收取的押金一般不得超过一个月租金",
         "numeric_limit", "calc", "deposit_months", "<=", 1, "月租金", _PARTY_ENTERPRISE,
         "standing_obligation", "high", "SRC-BJ-HOUSING-RENTAL", "第三十六条", "verified",
         "bj-rental:第三十六条#1"),
        ("BJ-RENT-PREPAY-MAX-3M", "住房租赁企业单次收取租金一般不得超过三个月租金",
         "numeric_limit", "calc", "rent_prepay_months", "<=", 3, "月租金",
         _PARTY_ENTERPRISE, "standing_obligation", "high", "SRC-BJ-HOUSING-RENTAL",
         "第三十六条", "verified", "bj-rental:第三十六条#2"),
        ("BJ-FILING-30D", "出租人应自合同订立之日起三十日内办理登记备案",
         "deadline_obligation", "calc", "filing_days", "<=", 30, "日", _PARTY_ANY,
         "periodic_obligation", "medium", "SRC-BJ-HOUSING-RENTAL", "第十五条", "verified",
         "bj-rental:第十五条#1"),
        ("BJ-LODGING-REG-3WD", "出租人应自合同订立之日起三个工作日内办理出租登记",
         "deadline_obligation", "calc", "lodging_reg_workdays", "<=", 3, "工作日",
         _PARTY_ANY, "periodic_obligation", "medium", "SRC-BJ-HOUSING-RENTAL", "第十五条",
         "verified", "bj-rental:第十五条#2"),
        ("BJ-DEPOSIT-REFUND-3WD", "应自承租人返还住房后三个工作日内退还剩余押金、租金",
         "deadline_obligation", "calc", "deposit_refund_workdays", "<=", 3, "工作日",
         _PARTY_ENTERPRISE, "periodic_obligation", "high", "SRC-BJ-HOUSING-RENTAL",
         "第三十六条", "verified", "bj-rental:第三十六条#3"),
        ("BJ-CONTRACT-ELEMENT-DEPOSIT", "住房租赁合同应载明押金数额（一般不超过一个月租金）",
         "element_completeness", "check", "has_deposit_clause", None, None, None,
         _PARTY_ANY, "standing_obligation", "medium", "SRC-BJ-HOUSING-RENTAL", "第十四条",
         "verified", "bj-rental:第十四条"),
        ("BJ-RENT-INTERVENTION", "租金明显上涨时市人民政府可采取价格干预措施（监管裁量权）",
         "text_prohibition", "quota", None, None, None, None, _PARTY_ANY,
         "conditional_institution", "advisory", "SRC-BJ-HOUSING-RENTAL", "第六十条",
         "verified", "bj-rental:第六十条"),
        ("BJ-ENTERPRISE-FILING-30D", "住房租赁企业应自领取营业执照之日起三十日内备案",
         "numeric_limit", "calc", "enterprise_filing_days", "<=", 30, "日",
         _PARTY_ENTERPRISE, "periodic_obligation", "medium", "SRC-BJ-HOUSING-RENTAL",
         "第二十七条", "verified", "bj-rental:第二十七条"),
        ("BJ-ESCROW-DEPOSIT-TERMS",
         "押金应按合同约定的支付时间、金额存入托管账户并按约定时间方式退还",
         "element_completeness", "check", "has_deposit_clause", None, None, None,
         _PARTY_ENTERPRISE, "standing_obligation", "medium", "SRC-BJ-DEPOSIT-ESCROW",
         "第九条", "verified", "bj-escrow:第九条"),
        ("BJ-ESCROW-RENT-SUPERVISION", "预收租金超过三个月租金的，全部租金应存入租金监管账户",
         "numeric_limit", "quota", "rent_prepay_months", "<=", 3, "月租金",
         _PARTY_ENTERPRISE, "conditional_institution", "medium", "SRC-BJ-DEPOSIT-ESCROW",
         "第十三条", "verified", "bj-escrow:第十三条"),
    ),
    "上海": (
        ("SH-FILING-30D", "出租人应自合同订立后三十日内办理登记备案",
         "deadline_obligation", "calc", "filing_days", "<=", 30, "日", _PARTY_ANY,
         "periodic_obligation", "medium", "SRC-SH-HOUSING-RENTAL", "第十七条", "verified",
         "sh-rental:第十七条"),
        ("SH-RENT-DEPOSIT-ESCROW", "超三个月租金部分与超一个月押金部分应存入资金监管专用账户",
         "numeric_limit", "calc", "deposit_months", "<=", 1, "月租金", _PARTY_ENTERPRISE,
         "standing_obligation", "high", "SRC-SH-HOUSING-RENTAL", "第二十九条", "verified",
         "sh-rental:第二十九条"),
        ("SH-AFFORDABLE-DEPOSIT-1M", "保障性租赁住房收取的押金不得超过一个月租金",
         "numeric_limit", "calc", "deposit_months", "<=", 1, "月租金", _AFFORDABLE_ANY,
         "standing_obligation", "high", "SRC-SH-HOUSING-RENTAL", "第三十七条", "verified",
         "sh-rental:第三十七条#1"),
        ("SH-ENTERPRISE-FILING-30D", "住房租赁企业应自领取营业执照之日起三十日内备案",
         "deadline_obligation", "calc", "enterprise_filing_days", "<=", 30, "日",
         _PARTY_ENTERPRISE, "periodic_obligation", "medium", "SRC-SH-HOUSING-RENTAL",
         "第二十二条", "verified", "sh-rental:第二十二条"),
        ("SH-AFFORDABLE-TERM-MIN-1Y", "保障性租赁住房租赁期限不得少于一年",
         "numeric_limit", "calc", "lease_term_years", ">=", 1, "年", _AFFORDABLE_ANY,
         "standing_obligation", "medium", "SRC-SH-HOUSING-RENTAL", "第三十七条",
         "verified", "sh-rental:第三十七条#2"),
        ("SH-PENALTY-AFFORDABLE-RENT-DEPOSIT",
         "收取租金或押金不符合保租房要求的，处五万元以上二十万元以下罚款",
         "numeric_limit", "quota", None, ">=", 50000, "元", _PARTY_ANY,
         "conditional_institution", "advisory", "SRC-SH-HOUSING-RENTAL", "第六十一条",
         "verified", "sh-rental:第六十一条"),
        ("SH-BAN-5Y-AFFORDABLE-APPLY",
         "转租、出借保障性租赁住房的，禁止五年内再次申请本市各类保障性住房",
         "text_prohibition", "quota", None, None, None, None, _PARTY_ANY,
         "conditional_institution", "advisory", "SRC-SH-HOUSING-RENTAL", "第五十九条",
         "verified", "sh-rental:第五十九条"),
    ),
}

#: 定性检查项的要素别名表（**没有别名表就会把「已约定但措辞不同」误判成缺失**）
ELEMENTS: Mapping[str, Tuple[Tuple[str, Tuple[str, ...]], ...]] = {
    "CN-ELEMENT-COMPLETENESS": (
        ("租赁物的名称", ("房屋", "住房", "坐落", "位于", "地址", "房产")),
        ("数量", ("面积", "套", "间", "室", "平方米")),
        ("用途", ("用途", "居住", "使用")),
        ("租赁期限", ("租赁期限", "租期", "期限")),
        ("租金及其支付期限和方式", ("租金", "支付", "付款")),
        ("租赁物维修", ("维修", "修缮", "维护")),
    ),
    "CN-WRITTEN-FORM-6M": (
        ("书面签署主体（出租人、承租人）", ("出租人", "甲方", "出租方")),
        ("书面约定的租赁期限", ("租赁期限", "租期", "期限")),
    ),
    "BJ-CONTRACT-ELEMENT-DEPOSIT": (
        ("押金数额", ("押金", "保证金")),
        ("支付期限和方式", ("支付", "付款", "交付方式")),
    ),
    "BJ-ESCROW-DEPOSIT-TERMS": (
        ("押金支付时间与金额", ("押金", "保证金")),
        ("押金退还时间与方式", ("退还", "返还", "退回")),
    ),
}

#: 来源登记（evidence 与 docs 用；不参与判定）
SOURCES: Mapping[str, Mapping[str, Any]] = {
    "SRC-CN-CIVIL-CODE": {"title": "《中华人民共和国民法典》", "doc_no": "主席令第四十五号",
                          "effective_date": "2021-01-01"},
    "SRC-BJ-HOUSING-RENTAL": {"title": "《北京市住房租赁条例》",
                              "doc_no": "北京市人民代表大会常务委员会公告〔十五届〕第 74 号",
                              "effective_date": "2022-09-01"},
    "SRC-SH-HOUSING-RENTAL": {"title": "《上海市住房租赁条例》",
                              "doc_no": "上海市人民代表大会常务委员会公告〔十五届〕第 133 号",
                              "effective_date": "2023-02-01"},
    "SRC-BJ-DEPOSIT-ESCROW": {"title": "《北京市住房租赁押金托管和租金监管暂行办法》",
                              "doc_no": "京建法〔2024〕8 号", "effective_date": "2024-10-01"},
}


def _rule(row: Tuple[Any, ...]) -> Dict[str, Any]:
    rule = dict(zip(RULE_COLUMNS, row))
    rule["elements"] = ELEMENTS.get(rule["rule_id"])
    return rule


def rules_for(city: str) -> Tuple[Dict[str, Any], ...]:
    """取某城市的规则包（**裸规则**，不含全国层叠加、不门控）。

    未登记的城市 → ``KeyError``（由器官映射为输入不合法）。
    """
    return tuple(_rule(row) for row in RULE_TABLE[city])


def rules_for_overlay(city: str) -> Tuple[Dict[str, Any], ...]:
    """城市包 + 全国层叠加（同名 ``rule_id`` 以城市包为准 = 地方规定优先）。"""
    merged = list(rules_for(city))
    if city != "全国":
        seen = {rule["rule_id"] for rule in merged}
        for rule in rules_for("全国"):
            if rule["rule_id"] not in seen:
                merged.append(rule)
    return tuple(merged)


def clause_ids() -> Tuple[str, ...]:
    """条文库应含的全部 ``clause_id``（每条规则一条，去重后排序）。"""
    ids = set()
    for city in RULE_TABLE:
        for row in RULE_TABLE[city]:
            ids.add(dict(zip(RULE_COLUMNS, row))["clause_id"])
    return tuple(sorted(ids))


def all_rule_ids() -> Tuple[str, ...]:
    ids = []
    for city in RULE_TABLE:
        for row in RULE_TABLE[city]:
            ids.append(dict(zip(RULE_COLUMNS, row))["rule_id"])
    return tuple(ids)


__all__ = [
    "CLAUSES_VERSION", "CITY_RULESETS", "RULE_COLUMNS", "RULE_TABLE", "ELEMENTS",
    "SOURCES", "rules_for", "rules_for_overlay", "clause_ids", "all_rule_ids",
]