"""规则包快照（**Python 字面量，零文件读取**）。

迁移的是来源产品随包冻结的规则包 ``rules/``（manifest + aliases + keywords）：
去重窗口、订阅参数、周期表、平台次序、表头定位参数、列别名与商户别名表、
关键词规则。三条纪律原样保留：

1. **业务数值只在规则包**：本模块是器官内唯一的业务数值定义点；``engine.py``
   只出现结构性端点（``0`` / ``1`` / ``2`` 等），不出现任何口径数值。
2. **每条参数必须挂来源**：全部默认值为**经验示例值（非官方）**，用户可覆盖——
   来源标注逐条保留（``source`` / ``notes``），不冒充官方口径。
3. **列名表/别名表/关键词表随包冻结**：表头定位锚定列、规范列名映射、归一化
   别名与关键词规则都在本模块内声明；``data/params.json`` / ``data/aliases.json``
   / ``data/keywords.json`` 逐字节保存来源资产作为可复核出处，随 wheel 进包，
   并由 ``tests/test_expense_ledger.py`` 的漂移门逐条比对（手改任一侧即红）。

规则包版本 = 条文库坐标 ``PARAMS_VERSION``（与来源冻结件 ``ruleset_version``
及真值基准日对应）。规则或别名口径变化时此值必须同步。
"""

from typing import Any, Dict, Mapping, Sequence, Tuple

#: 规则包快照版本（= 条文库坐标）。来源真值库基准日 2026-10-15、
#: ``ruleset_version`` 3。参数或别名口径变化时此值必须同步。
PARAMS_VERSION = "2026-10-15"
RULESET_VERSION = 3

#: 依据锚点 id（条文库必须具备的全部条目；缺一即 ``BasisMissing`` → 退出码 3）
CLAUSE_IMPORT_MAP = "import:column-map"
CLAUSE_DEDUP_WINDOW = "param:dedup-window"
CLAUSE_SUB_MIN_REPEATS = "param:subscription-min-repeats"
CLAUSE_SUB_TOLERANCE = "param:subscription-tolerance"
CLAUSE_PRICE_CHANGE = "param:price-change-threshold"
CLAUSE_PLATFORM_PRIORITY = "param:platform-priority"
CLAUSE_PERIOD_TABLE = "param:period-table"
CLAUSE_HEADER_LOCATE = "param:header-locate"
CLAUSE_ALIAS_TABLE = "contract:alias-table"
CLAUSE_KEYWORD_RULES = "contract:keyword-rules"
CLAUSE_UNKNOWN_FIRST_CLASS = "contract:unknown-first-class"

#: 规则包来源标注（全部条目共用；「经验默认（非官方）」措辞逐字保留）
SOURCE_NOTE = "经验默认（非官方）：全部默认值为经验示例值，用户可经 CLI flag 覆盖"

# ---------------------------------------------------------------------------
# 平台列名表（表头定位锚定列 / 预期列名全集 / 规范字段映射）
# ---------------------------------------------------------------------------
EXPECTED_COLUMNS: Mapping[str, Tuple[str, ...]] = {
    "wechat": ("交易时间", "交易类型", "交易对方", "商品", "收/支", "金额(元)",
               "支付方式", "当前状态", "交易单号", "商户单号"),
    "alipay": ("交易号", "交易创建时间", "交易对方", "商品说明", "金额（元）",
               "收/支", "交易状态"),
    "bank": ("交易日期", "交易时间", "摘要", "对方户名", "支出金额", "收入金额",
             "账户尾号"),
}

HEADER_ANCHORS: Mapping[str, Tuple[str, ...]] = {
    "wechat": ("交易时间", "交易对方", "金额(元)", "收/支", "商品"),
    "alipay": ("交易创建时间", "交易对方", "金额（元）", "收/支", "商品说明"),
    "bank": ("交易日期", "交易时间", "对方户名", "支出金额", "收入金额"),
}

CANONICAL_BY_COLUMN: Mapping[str, str] = {
    "交易时间": "交易时间",
    "交易创建时间": "交易时间",
    "交易日期": "交易时间",
    "交易对方": "对手方",
    "对方户名": "对手方",
    "商品": "商品说明",
    "商品说明": "商品说明",
    "摘要": "商品说明",
    "收/支": "收支类型",
    "金额(元)": "金额",
    "金额（元）": "金额",
    "金额": "金额",
    "支出金额": "金额",
    "收入金额": "金额",
}

# ---------------------------------------------------------------------------
# 列别名表（表头同义/空格变体；与 data/aliases.json 的 column_aliases 同源）
# ---------------------------------------------------------------------------
COLUMN_ALIASES: Tuple[Dict[str, Any], ...] = (
    {"canonical": "对手方", "variants": ["交易对象"],
     "platforms": ["alipay", "wechat", "bank"],
     "notes": "同义列名变体（col_synonym_variant 形态）"},
    {"canonical": "金额", "variants": ["金额(元)", "金额（元）", "金额"],
     "platforms": ["alipay", "wechat", "bank"],
     "notes": "金额列写法变体（半角/全角括号）"},
    {"canonical": "交易时间", "variants": ["交易创建时间"],
     "platforms": ["alipay"],
     "notes": "支付宝创建时间列即交易时间"},
    {"canonical": "商品说明", "variants": ["商品"],
     "platforms": ["alipay", "wechat"],
     "notes": "商品说明列写法变体"},
    {"canonical": "收支类型", "variants": ["收/支"],
     "platforms": ["alipay", "wechat"],
     "notes": "收支类型列写法变体"},
)

# ---------------------------------------------------------------------------
# 商户归一化表（后缀剥离白名单 / 全半角映射 / 别名条目；与 data/aliases.json 同源）
# ---------------------------------------------------------------------------
SUFFIX_STRIP: Tuple[str, ...] = (
    "有限公司", "有限责任公司", "股份有限公司", "集团有限公司",
)

FULLWIDTH_MAP: Tuple[Tuple[str, str], ...] = (
    ("！", "!"), ("＂", "\""), ("＃", "#"), ("＄", "$"), ("％", "%"),
    ("＆", "&"), ("＇", "'"), ("（", "("), ("）", ")"), ("＊", "*"),
    ("＋", "+"), ("，", ","), ("－", "-"), ("．", "."), ("／", "/"),
    ("０", "0"), ("１", "1"), ("２", "2"), ("３", "3"), ("４", "4"),
    ("５", "5"), ("６", "6"), ("７", "7"), ("８", "8"), ("９", "9"),
    ("：", ":"), ("；", ";"), ("＜", "<"), ("＝", "="), ("＞", ">"),
    ("？", "?"), ("＠", "@"), ("Ａ", "A"), ("Ｂ", "B"), ("Ｃ", "C"),
    ("Ｄ", "D"), ("Ｅ", "E"), ("Ｆ", "F"), ("Ｇ", "G"), ("Ｈ", "H"),
    ("Ｉ", "I"), ("Ｊ", "J"), ("Ｋ", "K"), ("Ｌ", "L"), ("Ｍ", "M"),
    ("Ｎ", "N"), ("Ｏ", "O"), ("Ｐ", "P"), ("Ｑ", "Q"), ("Ｒ", "R"),
    ("Ｓ", "S"), ("Ｔ", "T"), ("Ｕ", "U"), ("Ｖ", "V"), ("Ｗ", "W"),
    ("Ｘ", "X"), ("Ｙ", "Y"), ("Ｚ", "Z"), ("［", "["), ("＼", "\\"),
    ("］", "]"), ("＾", "^"), ("＿", "_"), ("｀", "`"), ("ａ", "a"),
    ("ｂ", "b"), ("ｃ", "c"), ("ｄ", "d"), ("ｅ", "e"), ("ｆ", "f"),
    ("ｇ", "g"), ("ｈ", "h"), ("ｉ", "i"), ("ｊ", "j"), ("ｋ", "k"),
    ("ｌ", "l"), ("ｍ", "m"), ("ｎ", "n"), ("ｏ", "o"), ("ｐ", "p"),
    ("ｑ", "q"), ("ｒ", "r"), ("ｓ", "s"), ("ｔ", "t"), ("ｕ", "u"),
    ("ｖ", "v"), ("ｗ", "w"), ("ｘ", "x"), ("ｙ", "y"), ("ｚ", "z"),
    ("｛", "{"), ("｜", "|"), ("｝", "}"), ("～", "~"), ("　", " "),
)

ALIAS_ENTRIES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("示例便利店甲", ("示例便利店甲（有限）公司", "示例 便利店甲")),
    ("示例快餐乙", ("示例快餐乙外卖店",)),
    ("示例超市丙", ("示例超市丙 旗舰店",)),
    ("示例咖啡丁", ("示例咖啡丁（五道口店）",)),
)

# ---------------------------------------------------------------------------
# 关键词规则（子串匹配、区分大小写；priority 升序评估；与 data/keywords.json 同源）
# ---------------------------------------------------------------------------
KEYWORD_RULES: Tuple[Tuple[str, str, str, int, Tuple[str, ...]], ...] = (
    ("R10_refund", "退款", "income", 10, ("退款",)),
    ("R20_aa_collection", "AA回款", "income", 20, ("AA回款", "AA收款")),
    ("R30_reimbursement", "报销", "income", 30, ("报销",)),
    ("R40_self_transfer", "本人转账", "any", 40, ("示例本人卡A", "示例本人卡B")),
    ("R50_consumption_retail", "消费", "expense", 50,
     ("示例便利店甲", "示例快餐乙", "示例超市丙", "示例咖啡丁")),
    ("R51_consumption_travel", "消费", "expense", 50, ("示例打车平台",)),
    ("R52_consumption_topup", "消费", "expense", 50, ("示例话费充值",)),
    ("R53_consumption_subscription", "消费", "expense", 50,
     ("示例健身月卡", "示例视频会员", "示例音乐会员", "示例云盘会员")),
)

# ---------------------------------------------------------------------------
# 数值参数（规则包快照；全部「经验默认（非官方）」，用户可覆盖）
# ---------------------------------------------------------------------------
DEDUP_WINDOW_SECONDS = 120
SUBSCRIPTION_MIN_REPEATS = 3
SUBSCRIPTION_INTERVAL_TOLERANCE_DAYS = 2
PRICE_CHANGE_MIN_PERCENT = 2.0
PLATFORM_PRIORITY: Tuple[str, ...] = ("wechat", "alipay", "bank")
HEADER_LOCATE_K = 2
HEADER_LOCATE_MAX_SCAN_LINES = 20

#: 周期表（相邻间隔落在 interval_days ± tolerance_days 内即视为同周期）
PERIOD_TABLE: Tuple[Dict[str, Any], ...] = (
    {"id": "monthly", "label": "月付", "interval_days": 30, "tolerance_days": 2},
    {"id": "quarterly", "label": "季付", "interval_days": 91, "tolerance_days": 3},
    {"id": "yearly", "label": "年付", "interval_days": 365, "tolerance_days": 5},
)


def params() -> Dict[str, Any]:
    """规则包参数 → dict（``engine.run_ledger`` 的唯一取数口）。"""
    return {
        "dedup_window_seconds": DEDUP_WINDOW_SECONDS,
        "subscription_min_repeats": SUBSCRIPTION_MIN_REPEATS,
        "subscription_interval_tolerance_days": SUBSCRIPTION_INTERVAL_TOLERANCE_DAYS,
        "price_change_min_percent": PRICE_CHANGE_MIN_PERCENT,
        "platform_priority": list(PLATFORM_PRIORITY),
        "header_locate_k": HEADER_LOCATE_K,
        "header_locate_max_scan_lines": HEADER_LOCATE_MAX_SCAN_LINES,
        "period_table": [dict(p) for p in PERIOD_TABLE],
    }


def aliases_doc() -> Dict[str, Any]:
    """别名表 → dict（``engine`` 归一化与列映射的唯一取数口）。"""
    return {
        "suffix_strip": list(SUFFIX_STRIP),
        "fullwidth_map": [{"full": full, "half": half} for full, half in FULLWIDTH_MAP],
        "aliases": [{"canonical": canonical, "variants": list(variants)}
                    for canonical, variants in ALIAS_ENTRIES],
        "column_aliases": [dict(entry) for entry in COLUMN_ALIASES],
    }


def keywords_doc() -> Dict[str, Any]:
    """关键词规则 → dict（``engine.classify_ledger`` 的唯一取数口）。"""
    return {
        "rules": [
            {"id": rule_id, "label": label, "direction_condition": condition,
             "keywords": list(keywords), "priority": priority}
            for rule_id, label, condition, priority, keywords in KEYWORD_RULES
        ],
    }


def clause_specs() -> Tuple[Tuple[str, str], ...]:
    """条文库应含的 ``(clause_id, path)``：8 条契约条目（数据契约，不冒充法规文号）。"""
    return (
        (CLAUSE_IMPORT_MAP, "数据契约 / 列名映射"),
        (CLAUSE_DEDUP_WINDOW, "参数包 / 去重时间窗口"),
        (CLAUSE_SUB_MIN_REPEATS, "参数包 / 订阅最小重复次数"),
        (CLAUSE_SUB_TOLERANCE, "参数包 / 订阅间隔容差"),
        (CLAUSE_PRICE_CHANGE, "参数包 / 涨价判定阈值"),
        (CLAUSE_PLATFORM_PRIORITY, "参数包 / 平台次序"),
        (CLAUSE_PERIOD_TABLE, "参数包 / 周期表"),
        (CLAUSE_HEADER_LOCATE, "参数包 / 表头定位"),
        (CLAUSE_ALIAS_TABLE, "数据契约 / 商户别名表"),
        (CLAUSE_KEYWORD_RULES, "数据契约 / 关键词规则"),
        (CLAUSE_UNKNOWN_FIRST_CLASS, "数据契约 / 未知一等结论"),
    )


def clause_text(clause_id: str) -> str:
    """契约条目正文（数值与词面以本模块为准；不冒充法规条文）。"""
    if clause_id == CLAUSE_IMPORT_MAP:
        return ("已登记列名：交易时间/交易创建时间/交易日期 → 交易时间；交易对方/对方户名"
                " → 对手方；商品/商品说明/摘要 → 商品说明；收/支 → 收支类型；金额(元)/"
                "金额（元）/金额/支出金额/收入金额 → 金额；未登记列名记 unknown（不猜）；"
                "必填列：交易时间、金额、对手方")
    if clause_id == CLAUSE_DEDUP_WINDOW:
        return ("跨平台去重时间窗口：闭区间 |Δt| ≤ W；恰好等于 W 应合并"
                "（%s）" % SOURCE_NOTE)
    if clause_id == CLAUSE_SUB_MIN_REPEATS:
        return "周期订阅最小重复次数（含首期）（%s）" % SOURCE_NOTE
    if clause_id == CLAUSE_SUB_TOLERANCE:
        return "周期表内各周期未单独覆盖时的间隔容差默认值（%s）" % SOURCE_NOTE
    if clause_id == CLAUSE_PRICE_CHANGE:
        return "涨价判定阈值：相邻周期金额变化 ≥ 该百分比记一条涨价记录（%s）" % SOURCE_NOTE
    if clause_id == CLAUSE_PLATFORM_PRIORITY:
        return "去重簇代表笔选择排序键（时间最早 → 本次序 → 来源行号）（%s）" % SOURCE_NOTE
    if clause_id == CLAUSE_PERIOD_TABLE:
        return ("订阅周期判定表：相邻间隔落在 interval_days ± tolerance_days 内即视为"
                "同周期；monthly 30±2 / quarterly 91±3 / yearly 365±5（%s）" % SOURCE_NOTE)
    if clause_id == CLAUSE_HEADER_LOCATE:
        return ("表头定位：候选行命中的预期列名数 ≥ K 即判为表头；只在前 N 行内找表头，"
                "超出即文件级失败（%s）" % SOURCE_NOTE)
    if clause_id == CLAUSE_ALIAS_TABLE:
        return ("商户归一化动作序列写死：去空白 → 全半角统一（映射表）→ 后缀剥离"
                "（白名单、剥离后非空才生效）→ 别名表命中（variants 过同一管线后建索引）；"
                "未命中任何规则则原样保留")
    if clause_id == CLAUSE_KEYWORD_RULES:
        return ("关键词按子串匹配、区分大小写；作用域 = 交易对方 + 商品说明；规则按 "
                "priority 升序评估，方向条件不满足即跳过；全部未命中 → 『未知』"
                "（一等结论，不得 fallthrough 为消费）")
    if clause_id == CLAUSE_UNKNOWN_FIRST_CLASS:
        return ("『未知』是一等结论：未知行入显式清单且不混入消费；同平台候选簇显式"
                "不合并、待人工复核（绝不静默合并）；invalid 行绝不入库")
    raise KeyError(clause_id)


__all__ = [
    "PARAMS_VERSION", "RULESET_VERSION", "EXPECTED_COLUMNS", "HEADER_ANCHORS",
    "CANONICAL_BY_COLUMN", "COLUMN_ALIASES", "SUFFIX_STRIP", "FULLWIDTH_MAP",
    "ALIAS_ENTRIES", "KEYWORD_RULES", "DEDUP_WINDOW_SECONDS",
    "SUBSCRIPTION_MIN_REPEATS", "SUBSCRIPTION_INTERVAL_TOLERANCE_DAYS",
    "PRICE_CHANGE_MIN_PERCENT", "PLATFORM_PRIORITY", "HEADER_LOCATE_K",
    "HEADER_LOCATE_MAX_SCAN_LINES", "PERIOD_TABLE", "params", "aliases_doc",
    "keywords_doc", "clause_specs", "clause_text",
]
