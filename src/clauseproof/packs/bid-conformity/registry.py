"""规则包与条文块登记（**Python 字面量，零文件读取**）。

迁移的是来源产品随包冻结的知识库中的**判定面**：21 条 `CHK-*` 规则（含 `only_if`
门控与 `params` 阈值）、6 条引擎引用的法规条号、信用等级有序量表。三条纪律原样保留：

1. **依据必须可解析**：引擎只引用 `已核对` 条文块（`data/clauses.json` 的 14 条）；
   `中华人民共和国招标投标法` 两条**待核对**，引擎不引用（来源仓同口径）。
2. **阈值来自规则包**：`CHK-PC-01.ratio` 是唯一参数，写进规则包而非引擎。
3. **规则必须注册**：`CHK-*` 21 条（含 M4 围标提示 `CHK-CL-01`）；引擎分派表只覆盖
   7 个 `rule_type`（`collusion` 由围标模块产出，不迁）。

``data/rules.json`` 与 ``data/blocks.json`` 是来源资产的只读转写，随 wheel 进包，
并由 ``tests/test_bid_conformity.py`` 的漂移门逐条比对。
"""

from typing import Any, Dict, List, Mapping, Tuple

#: 知识库坐标（来源仓条文块复核日 2026-10-05）
VERSION = "2026-10-05"

#: 法规名称（与条文块的 ``law`` 字段逐字一致）
LAW_TENDER_LAW = "中华人民共和国招标投标法"
LAW_IMPL_REG = "招标投标法实施条例"
LAW_87 = "政府采购货物和服务招标投标管理办法"

#: 法规引用（Finding.basis 的法规类取值；逐字命中条文块）
CITE_IMPL_REJECT = "《%s》第五十一条" % LAW_IMPL_REG
CITE_87_VALIDITY = "《%s》第二十三条" % LAW_87
CITE_87_OPEN = "《%s》第三十九条" % LAW_87
CITE_87_PRICE_FIX = "《%s》第五十九条" % LAW_87
CITE_87_LOW_PRICE = "《%s》第六十条" % LAW_87
CITE_87_INVALID = "《%s》第六十三条" % LAW_87

#: 法规名 → 条文库 clause_id 前缀
LAW_PREFIX: Mapping[str, str] = {
    LAW_87: "87-order",
    LAW_IMPL_REG: "impl-reg",
    LAW_TENDER_LAW: "tender-law",
}

#: 招标文件自设条款（Q*/S*/R*）的锚点
CLAUSE_TENDER_CLAUSE = "contract:tender-clause"
#: 规则包注册的锚点
CLAUSE_RULE_PACK = "contract:rule-pack"

#: 规则包（21 条；顺序 = 来源 rules.json 声明序）
RULES: Tuple[Dict[str, Any], ...] = (
    {
        'id': 'CHK-Q-01',
        'name': '资格证明材料存在性核对',
        'rule_type': 'qualification_match',
        'severity': 'high',
        'basis': ['《政府采购货物和服务招标投标管理办法》第六十三条', 'TenderCard.qualifications'],
        'advice': '补充提供对应资格/财务类证明材料，或核对证明材料行是否完整（资格类、财务类条款在投标文件第二章逐条对应）',
    },
    {
        'id': 'CHK-Q-02',
        'name': '资格证书有效期核对',
        'rule_type': 'qualification_match',
        'severity': 'high',
        'basis': ['《政府采购货物和服务招标投标管理办法》第六十三条', 'TenderCard.qualifications'],
        'advice': '核对证书有效期与投标截止时间；过期的要求换发新证或在有效期内提供延续证明',
    },
    {
        'id': 'CHK-Q-03',
        'name': '资质等级核对',
        'rule_type': 'qualification_match',
        'severity': 'mid',
        'basis': ['《政府采购货物和服务招标投标管理办法》第六十三条', 'TenderCard.qualifications'],
        'advice': '核对持有等级是否达到招标文件要求的等级（信用等级按 AAA>AA>A>BBB>BB>B>CCC>CC>C 有序比较）',
    },
    {
        'id': 'CHK-Q-04',
        'name': '类似业绩要求核对',
        'rule_type': 'qualification_match',
        'severity': 'high',
        'basis': ['《政府采购货物和服务招标投标管理办法》第六十三条', 'TenderCard.qualifications'],
        'advice': '按招标文件要求的业绩数量与年份下限核对投标文件类似业绩清单',
    },
    {
        'id': 'CHK-Q-05',
        'name': '人员证书要求核对',
        'rule_type': 'qualification_match',
        'severity': 'high',
        'basis': ['《政府采购货物和服务招标投标管理办法》第六十三条', 'TenderCard.qualifications'],
        'advice': '按资格条款中的证书关键词核对拟投入人员证书清单（如 PMP）',
    },
    {
        'id': 'CHK-SR-01',
        'name': '星号条款响应存在性核对',
        'rule_type': 'star_response',
        'severity': 'high',
        'basis': ['TenderCard.star_clauses', '《招标投标法实施条例》第五十一条'],
        'advice': '★条款未响应即触及否决条款，须在技术方案中逐条补充响应；▲条款未响应为重要条款缺失',
    },
    {
        'id': 'CHK-SR-02',
        'name': '星号条款响应值核对',
        'rule_type': 'star_response',
        'severity': 'mid',
        'basis': ['TenderCard.star_clauses', 'TenderCard.star_responses'],
        'advice': '响应值偏离要求值而偏差表仍声明无偏离的，要求投标人澄清或按偏差处理',
    },
    {
        'id': 'CHK-SR-03',
        'name': '星号条款负偏离声明核对',
        'rule_type': 'star_response',
        'severity': 'low',
        'basis': ['TenderCard.star_clauses', 'TenderCard.star_responses'],
        'advice': '已声明的负偏离是否可接受由评审判断，提请人工确认',
    },
    {
        'id': 'CHK-AR-01',
        'name': '大写金额与小写金额一致性核对',
        'rule_type': 'arithmetic_consistency',
        'severity': 'high',
        'basis': ['《政府采购货物和服务招标投标管理办法》第五十九条'],
        'advice': '大写金额与小写金额不一致的，按 87号令第五十九条 以大写金额为准修正（招标文件另有规定除外），并要求投标人确认',
    },
    {
        'id': 'CHK-AR-02',
        'name': '分项合计与投标总价一致性核对',
        'rule_type': 'arithmetic_consistency',
        'severity': 'high',
        'basis': ['《政府采购货物和服务招标投标管理办法》第五十九条'],
        'advice': '分项合计与投标总价不一致的，按 87号令第五十九条 修正顺序处理，并要求投标人确认',
    },
    {
        'id': 'CHK-AR-03',
        'name': '分项明细与分项合计一致性核对',
        'rule_type': 'arithmetic_consistency',
        'severity': 'high',
        'basis': ['《政府采购货物和服务招标投标管理办法》第五十九条'],
        'advice': '分项明细加总与分项合计不一致的，要求投标人澄清修正',
    },
    {
        'id': 'CHK-BD-01',
        'name': '投标保证金金额核对',
        'rule_type': 'bond_check',
        'severity': 'mid',
        'basis': ['《政府采购货物和服务招标投标管理办法》第六十三条', 'TenderCard.bond'],
        'advice': '缴纳金额低于招标文件要求的，未按要求提交投标保证金，触及否决条款',
    },
    {
        'id': 'CHK-BD-02',
        'name': '投标保证金形式核对',
        'rule_type': 'bond_check',
        'severity': 'mid',
        'basis': ['《政府采购货物和服务招标投标管理办法》第六十三条', 'TenderCard.bond'],
        'advice': '缴纳形式不在招标文件允许形式内的，未按要求提交投标保证金，触及否决条款',
    },
    {
        'id': 'CHK-DT-01',
        'name': '投标有效期核对',
        'rule_type': 'date_logic',
        'severity': 'mid',
        'basis': ['《政府采购货物和服务招标投标管理办法》第二十三条', 'TenderCard.key_dates'],
        'advice': '承诺投标有效期不得少于招标文件载明的投标有效期，不足的触及否决条款',
    },
    {
        'id': 'CHK-DT-02',
        'name': '开标时间顺序核对（招标侧）',
        'rule_type': 'date_logic',
        'severity': 'mid',
        'basis': ['《政府采购货物和服务招标投标管理办法》第三十九条', 'TenderCard.key_dates'],
        'advice': '开标时间应在投标截止同一时间；早于递交截止属招标文件内在矛盾，提请招标人澄清更正',
    },
    {
        'id': 'CHK-RJ-01',
        'name': '最高限价否决扫描',
        'rule_type': 'rejection_scan',
        'severity': 'high',
        'basis': ['《政府采购货物和服务招标投标管理办法》第六十三条', '《招标投标法实施条例》第五十一条', 'TenderCard.rejection_clauses'],
        'advice': '投标总价超过最高限价（从否决条款 R1 内嵌金额抽取）的，投标无效',
    },
    {
        'id': 'CHK-RJ-02',
        'name': '保证金否决条款联动',
        'rule_type': 'rejection_scan',
        'severity': 'high',
        'basis': ['《政府采购货物和服务招标投标管理办法》第六十三条', 'TenderCard.rejection_clauses'],
        'advice': '保证金金额/形式违规命中招标文件否决条款（未按要求提交投标保证金的，投标无效）',
    },
    {
        'id': 'CHK-RJ-03',
        'name': '有效期否决条款联动',
        'rule_type': 'rejection_scan',
        'severity': 'high',
        'basis': ['《政府采购货物和服务招标投标管理办法》第二十三条', 'TenderCard.rejection_clauses'],
        'advice': '投标有效期不足命中招标文件否决条款',
    },
    {
        'id': 'CHK-RJ-04',
        'name': '星号条款否决条款联动',
        'rule_type': 'rejection_scan',
        'severity': 'high',
        'basis': ['《招标投标法实施条例》第五十一条', 'TenderCard.rejection_clauses'],
        'advice': '★条款不满足或未响应命中招标文件否决条款（★号条款不满足或者未响应的，其投标无效）',
    },
    {
        'id': 'CHK-PC-01',
        'name': '低于成本报价嫌疑提示',
        'rule_type': 'price_check',
        'severity': 'low',
        'basis': ['《政府采购货物和服务招标投标管理办法》第六十条', 'TenderCard.rejection_clauses'],
        'advice': '报价低于最高限价规定比例（默认 80%）时提示低于成本嫌疑，提请人工复核（87号令第六十条：要求书面说明并提供证明，不能证明合理性按无效投标处理）',
        'params': {'ratio': 0.8},
    },
    {
        'id': 'CHK-CL-01',
        'name': '围标串标文本特征提示',
        'rule_type': 'collusion',
        'severity': 'mid',
        'basis': ['《招标投标法实施条例》第三十九条', '《招标投标法实施条例》第四十条', '《政府采购货物和服务招标投标管理办法》第三十六条', '《政府采购货物和服务招标投标管理办法》第三十七条'],
        'advice': '两份投标文件文本特征异常一致（同分钟编制时间戳/对照独有共享长句）时提请人工核查；仅文本特征辅助提示，不做围标定性结论',
    },
)


def rule_by_id(rule_id: str) -> Dict[str, Any]:
    """按 id 取规则（缺 → KeyError，调用方须显式处理）。"""
    for rule in RULES:
        if rule["id"] == rule_id:
            return rule
    raise KeyError(rule_id)


def clause_specs() -> Tuple[Tuple[str, str], ...]:
    """条文库应含的 ``(clause_id, path)``：已核对条文块 + 两条数据契约。"""
    specs = [
        ("87-order:第二十三条", "《政府采购货物和服务招标投标管理办法》 / 第二十三条"),
        ("87-order:第三十六条", "《政府采购货物和服务招标投标管理办法》 / 第三十六条"),
        ("87-order:第三十七条", "《政府采购货物和服务招标投标管理办法》 / 第三十七条"),
        ("87-order:第三十九条", "《政府采购货物和服务招标投标管理办法》 / 第三十九条"),
        ("87-order:第五十条", "《政府采购货物和服务招标投标管理办法》 / 第五十条"),
        ("87-order:第五十九条", "《政府采购货物和服务招标投标管理办法》 / 第五十九条"),
        ("87-order:第六十条", "《政府采购货物和服务招标投标管理办法》 / 第六十条"),
        ("87-order:第六十三条", "《政府采购货物和服务招标投标管理办法》 / 第六十三条"),
        ("impl-reg:第二十五条", "《招标投标法实施条例》 / 第二十五条"),
        ("impl-reg:第二十六条", "《招标投标法实施条例》 / 第二十六条"),
        ("impl-reg:第二十七条", "《招标投标法实施条例》 / 第二十七条"),
        ("impl-reg:第三十九条", "《招标投标法实施条例》 / 第三十九条"),
        ("impl-reg:第四十条", "《招标投标法实施条例》 / 第四十条"),
        ("impl-reg:第五十一条", "《招标投标法实施条例》 / 第五十一条"),
        (CLAUSE_TENDER_CLAUSE, "数据契约 / 招标文件自设条款"),
        (CLAUSE_RULE_PACK, "数据契约 / 规则包注册"),
    ]
    return tuple(specs)


__all__ = [
    "VERSION", "LAW_TENDER_LAW", "LAW_IMPL_REG", "LAW_87", "CITE_IMPL_REJECT",
    "CITE_87_VALIDITY", "CITE_87_OPEN", "CITE_87_PRICE_FIX", "CITE_87_LOW_PRICE",
    "CITE_87_INVALID", "LAW_PREFIX", "CLAUSE_TENDER_CLAUSE", "CLAUSE_RULE_PACK",
    "RULES", "rule_by_id", "clause_specs",
]
