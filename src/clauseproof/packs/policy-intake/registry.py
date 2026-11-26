"""条目契约与部门别名表（**Python 字面量，零文件读取**）。

迁移的是来源产品随包冻结的三份口径资产：

1. **统一 schema**（十个字段、七个必填、禁正文类字段）——「字段白名单是允许清单，
   不是黑名单」；
2. **文号三态**（`parsed` / `partial` / `unparsed`，未解析字段显式标哨兵 `未解析`）；
3. **部门别名表**（39 条，`match_rule = longest_first`，前缀匹配 + 最长优先）。

``data/org-aliases.json`` 与 ``data/contracts.json`` 是来源资产的只读转写，随 wheel
进包，并由 ``tests/test_policy_intake.py`` 的漂移门逐条比对。

依据（``clause_id``）是**数据契约条目**，不是法规条文：本器官判定的是「条目能不能
作为本期日报的数据源」，没有可引的法律条款，故不冒法条名与文号。
"""

from typing import Dict, Mapping, Tuple

#: 契约坐标（来源仓 ``data/README.md`` 基准日 2026-10-15；抓取复测 2026-10-17）
CONTRACT_VERSION = "2026-10-15"

#: 频道标识 → 中文名
CHANNELS: Mapping[str, str] = {"gwy": "国务院", "bm": "部委"}

#: 统一 schema 的字段集合与顺序（改此常量属口径变更）
SCHEMA_FIELDS: Tuple[str, ...] = (
    "source", "id", "index", "pcode", "title", "pubtimeStr", "puborg", "url",
    "summary", "channel",
)

#: 必填字段（缺失即该条不得落库 / 不得进日报）
REQUIRED_FIELDS: Tuple[str, ...] = (
    "source", "id", "title", "pubtimeStr", "puborg", "url", "summary",
)

#: 快照字段黑名单（出现即违反「不做全文归档」边界）
FORBIDDEN_SNAPSHOT_FIELDS: Tuple[str, ...] = (
    "content", "body", "fulltext", "full_text", "html", "text", "article",
)

#: 未解析字段的哨兵值（三态契约之一）
UNPARSED = "未解析"

#: 文号解析三态
STATUS_PARSED = "parsed"
STATUS_PARTIAL = "partial"
STATUS_UNPARSED = "unparsed"
PCODE_STATUSES: Tuple[str, ...] = (STATUS_PARSED, STATUS_PARTIAL, STATUS_UNPARSED)

#: 六角括号与其全角变体（成对使用）
BRACKET_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("\u3014", "\u3015"),
    ("\ufe5d", "\ufe5e"),
)

#: 部门别名表（来源 ``org-aliases.json`` 的 ``aliases``，声明序 = 文件键序）
ORG_ALIASES: Tuple[Tuple[str, str], ...] = (
    ("中国人民银行", "中国人民银行"),
    ("中国气象局办公室", "中国气象局办公室"),
    ("中国证监会", "中国证监会"),
    ("中央网信办", "中央网信办"),
    ("交通运输部", "交通运输部"),
    ("住房和城乡建设部", "住房和城乡建设部"),
    ("住房城乡建设部", "住房和城乡建设部"),
    ("住房城乡建设部办公厅", "住房和城乡建设部办公厅"),
    ("公安部", "公安部"),
    ("农业农村部", "农业农村部"),
    ("商务部", "商务部"),
    ("国务院", "国务院"),
    ("国务院办公厅", "国务院办公厅"),
    ("国家中医药局", "国家中医药局"),
    ("国家中医药局综合司", "国家中医药局综合司"),
    ("国家医保局", "国家医保局"),
    ("国家卫生健康委", "国家卫生健康委"),
    ("国家卫生健康委办公厅", "国家卫生健康委办公厅"),
    ("国家发展改革委", "国家发展改革委"),
    ("国家发展改革委办公厅", "国家发展改革委办公厅"),
    ("国家新闻出版署", "国家新闻出版署"),
    ("国家林草局", "国家林草局"),
    ("国家版权局", "国家版权局"),
    ("国家知识产权局", "国家知识产权局"),
    ("国家网信办", "国家网信办"),
    ("国家能源局", "国家能源局"),
    ("国家药监局", "国家药监局"),
    ("国家邮政局", "国家邮政局"),
    ("国家铁路局", "国家铁路局"),
    ("工业和信息化部", "工业和信息化部"),
    ("工业和信息化部办公厅", "工业和信息化部办公厅"),
    ("市场监管总局", "市场监管总局"),
    ("市场监管总局办公厅", "市场监管总局办公厅"),
    ("应急管理部", "应急管理部"),
    ("文化和旅游部", "文化和旅游部"),
    ("民政部", "民政部"),
    ("自然资源部", "自然资源部"),
    ("财政部", "财政部"),
    ("金融监管总局", "金融监管总局"),
)

#: 别名表匹配口径（本器官只实现这一种）
MATCH_RULE = "longest_first"

#: 依赖关系坐标（快照排序 / 去重键）
ORDER_RULE = "pubtimeStr_desc_id_asc"
DEDUP_KEYS = "id; pcode_nonempty"

#: 条文库应含的契约条目
CLAUSE_SCHEMA = "contract:entry-schema"
CLAUSE_DATE = "contract:date-format"
CLAUSE_SNAPSHOT_FIELDS = "contract:snapshot-fields"
CLAUSE_PCODE = "contract:pcode-grammar"
CLAUSE_PCODE_SENTINEL = "contract:pcode-sentinel"
CLAUSE_ORG_ALIASES = "contract:org-aliases"
CLAUSE_DIFF_KEYS = "contract:diff-keys"
CLAUSE_ORDER = "contract:canonical-order"


def clause_specs() -> Tuple[Tuple[str, str], ...]:
    """条文库应含的 ``(clause_id, path)``。"""
    return (
        (CLAUSE_SCHEMA, "数据契约 / 统一字段与必填项"),
        (CLAUSE_DATE, "数据契约 / 发布日期形态"),
        (CLAUSE_SNAPSHOT_FIELDS, "数据契约 / 快照字段白名单"),
        (CLAUSE_PCODE, "数据契约 / 文号形态"),
        (CLAUSE_PCODE_SENTINEL, "数据契约 / 未解析哨兵与三态"),
        (CLAUSE_ORG_ALIASES, "数据契约 / 部门别名归一"),
        (CLAUSE_DIFF_KEYS, "数据契约 / 新增与重复判定双键"),
        (CLAUSE_ORDER, "数据契约 / 规范序"),
    )


def clause_text(clause_id: str) -> str:
    """契约条目正文（**不冒法条名与文号**）。"""
    texts = {
        CLAUSE_SCHEMA: "统一字段 %s；必填 %s；缺任一必填 → 该条不得落库、不得进日报"
                       % ("、".join(SCHEMA_FIELDS), "、".join(REQUIRED_FIELDS)),
        CLAUSE_DATE: "发布日期形态 YYYY.MM.DD，且年月日组合必须真实存在（拒绝 2026.13.45）",
        CLAUSE_SNAPSHOT_FIELDS: "快照只存元数据：字段白名单 %s；出现 %s 任一字段即拒（不做全文归档）"
                                % ("、".join(SCHEMA_FIELDS), "、".join(FORBIDDEN_SNAPSHOT_FIELDS)),
        CLAUSE_PCODE: "文号形态：〔〕/﹝﹞ 括号形态（代字 + 四位年份 + 序号）或『第…号』形态（无可靠年份）",
        CLAUSE_PCODE_SENTINEL: "解析失败显式标哨兵「未解析」；三态 parsed/partial/unparsed 不互并",
        CLAUSE_ORG_ALIASES: "部门拆分按空白类字符；匹配前缀 + 最长优先；未命中原样保留并记 alias_missing（不猜）",
        CLAUSE_DIFF_KEYS: "重复判定双键：id 相同 → 重复；否则 pcode 相同且非空 → 重复；命中键写入 matched_by",
        CLAUSE_ORDER: "规范序：pubtimeStr 倒序、同级按 id 升序；产物无时间戳",
    }
    if clause_id not in texts:
        raise KeyError(clause_id)
    return texts[clause_id]


def alias_map() -> Dict[str, str]:
    """别名表 → ``{原始名: 规范名}``（dict 保留声明序）。"""
    return dict(ORG_ALIASES)


__all__ = [
    "CONTRACT_VERSION", "CHANNELS", "SCHEMA_FIELDS", "REQUIRED_FIELDS",
    "FORBIDDEN_SNAPSHOT_FIELDS", "UNPARSED", "STATUS_PARSED", "STATUS_PARTIAL",
    "STATUS_UNPARSED", "PCODE_STATUSES", "BRACKET_PAIRS", "ORG_ALIASES", "MATCH_RULE",
    "ORDER_RULE", "DEDUP_KEYS", "CLAUSE_SCHEMA", "CLAUSE_DATE", "CLAUSE_SNAPSHOT_FIELDS",
    "CLAUSE_PCODE", "CLAUSE_PCODE_SENTINEL", "CLAUSE_ORG_ALIASES", "CLAUSE_DIFF_KEYS",
    "CLAUSE_ORDER", "clause_specs", "clause_text", "alias_map",
]