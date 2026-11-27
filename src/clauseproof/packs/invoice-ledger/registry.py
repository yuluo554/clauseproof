"""器官常量与条文坐标（纯常量，零 IO）。

条文库版本 = 来源知识库核对日期 ``2026-10-06``（三份法规 JSON 的
``verification.reviewed_at`` 一致，随包快照逐字节保留）。

条文库 = 三份来源知识库的条目并集（16 条，8 个文号） + 4 条数据契约。
规则族到条款的映射是**固定常量**：改映射必须同时改条文库与测试。
"""

VERSION = "0.1.0"
PARAMS_VERSION = "2026-10-06"

SLUG = "invoice-ledger"
SUMMARY = (
    "电子发票台账判定（发票参数卡 × 八规则：精确/联合键/模糊重复 + 连号拆分 + "
    "票面算术 + 大写金额 + 时间逻辑；三级语义 + 条款锚点）"
)

#: 条文库里必须存在的锚点（数据契约）
CLAUSE_LEDGER = "contract.ledger"
CLAUSE_LEVELS = "contract.levels"
CLAUSE_ANCHOR = "contract.anchor"
CLAUSE_PARAMS = "contract.params"

#: 规则族 → 条文锚点
RULE_CLAUSES = {
    "duplicate.exact": "no11-definition",
    "duplicate.joint": "764-21-2",
    "duplicate.fuzzy": "764-21-2",
    "series": "no11-number-rule",
    "arithmetic.total": "764-21-1",
    "arithmetic.cn": "764-21-1",
    "time.future": "764-21-1",
    "time.stale": "764-21-1",
}

#: 弱关联规则（法规无直接禁止条款，条号只挂同类义务上位条款）——如实披露
HEURISTIC_FAMILIES = ("series", "time.future", "time.stale")
HEURISTIC_NOTE = (
    "工程口径：本规则为启发式风险信号，法规无直接禁止条款；"
    "条号仅挂同类义务的上位条款"
)

#: 来源规则代码（evidence 留痕）
RULE_CODES = {
    "duplicate.exact": "R-DUP-01",
    "duplicate.joint": "R-DUP-02",
    "duplicate.fuzzy": "R-DUP-03",
    "series": "R-SEQ-01",
    "arithmetic.total": "R-ARITH-01",
    "arithmetic.cn": "R-ARITH-02",
    "time.future": "R-TIME-01",
    "time.stale": "R-TIME-02",
}

#: 随包数据文件（判据 4 的进包清单与 sha256 漂移门同源；manifest 自登记清单）
DATA_FILES = (
    "clauses.json",
    "knowledge-11.json",
    "knowledge-56.json",
    "knowledge-764.json",
)
MANIFEST_FILE = "manifest.json"