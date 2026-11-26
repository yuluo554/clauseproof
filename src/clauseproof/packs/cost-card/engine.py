"""成本卡判定内核（**零 I/O / 零时钟 / 零环境变量 / 零业务数值字面量**）。

迁移的是来源产品的「进货单三态 → 净料换算 → 成本卡 → 毛利率定价 → 价格波动」判定面，
只保留「输入事实 → 判定」这一段：

- **进货单三态**：``ok`` / ``invalid`` / ``unknown``，异常行一律列入清单（不静默跳过）；
- **换算公式 F1–F5**：净料单价、单份成本、建议售价、实际毛利率、涨跌幅；
- **参数门控分作用域**：``cost`` / ``pricing`` / ``alert`` 各只校验自己引用的条目；
- **参数来源标记**：每个进入计算路径的参数必须挂来源（``snapshot`` / ``user`` /
  ``builtin_experience``），**消费点**校验，不只是构造期；
- **行级失败不中断整批**：某道菜有一行不成立 → 整道菜排除并逐条列原因（不丢行求和）。

业务数值（净料率 / 目标毛利率 / 波动阈值）**只能来自** :mod:`registry`（参数包快照）；
本模块只出现数学定义域的端点（``0`` / ``1``），不出现任何口径数值。

本模块不读 CSV 文件：``judge_rows`` 收**已解码的表头与行数组**。编码判定（只收 UTF-8）
是输入层的事，属 `SKELETON-SPEC` §2 禁止的器官 I/O 面——见 ``docs/cost-card.md`` §5。
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# 呈现精度：金额/单价两位小数，比率四位小数（= 百分比两位）
MONEY_EXP = Decimal("0.01")
RATE_EXP = Decimal("0.0001")

# 参数来源类型（白名单）。未登记值一律拒绝进入计算路径。
SOURCE_KINDS = (
    "snapshot",           # 公开价格快照（含抓取日期）
    "user",               # 用户提供/配置
    "builtin_experience", # 内置经验默认值（非官方出处）
)

# 进货单行三态
STATUS_OK = "ok"
STATUS_INVALID = "invalid"
STATUS_UNKNOWN = "unknown"

# 参数条目三态（门控语义）
PARAM_VERIFIED = "verified"
PARAM_PENDING = "pending"
PARAM_INPUT_REQUIRED = "input_required"

# 计算作用域（门控按计算路径分作用域，不用「整包全 verified」当唯一门）
SCOPES = ("cost", "pricing", "alert")

#: 作用域 → 参数包分区名
SCOPE_SECTIONS = {
    "cost": "yield_rates",
    "pricing": "pricing",
    "alert": "alert",
}

# 列名白名单 → 内部字段名。**未登记的列名一律 unknown，绝不猜。**
COLUMN_MAP = {
    "日期": "date",
    "品名": "name",
    "类别": "category",
    "数量": "qty",
    "单位": "unit",
    "单价": "unit_price",
    "金额": "amount",
}

REQUIRED_FIELDS = ("name", "qty", "unit_price")

#: 表头必备列名（由 COLUMN_MAP 反查得出，**不另写一份映射**）
_FIELD_TO_COLUMN = {field: column for column, field in COLUMN_MAP.items()}
REQUIRED_COLUMNS = tuple(_FIELD_TO_COLUMN[field] for field in REQUIRED_FIELDS)

#: 单位白名单：仅作一致性提示，不做换算（换算规则属扩展项）
KNOWN_UNITS = ("斤", "公斤", "千克", "克", "个", "只", "把", "棵", "袋", "盒")

# 进货单异常代码（机读判据；测试断言它，不去匹配中文散文）
ISSUE_MAPPING_UNCERTAIN = "mapping_uncertain"
ISSUE_STRUCTURE = "structure_unparsable"
ISSUE_REQUIRED_EMPTY = "required_empty"
ISSUE_NOT_NUMERIC = "not_numeric"
ISSUE_NEGATIVE = "negative"
ISSUE_UNIT_UNREGISTERED = "unit_unregistered"
# 文件级结论：整份进货单零可用行——不是某一行的错，是全行皆异常
ISSUE_NO_USABLE_ROWS = "no_usable_rows"

# 成本卡行级异常代码
ISSUE_YIELD_OUT_OF_RANGE = "yield_rate_out_of_range"
ISSUE_QTY_INVALID = "qty_invalid"
# 文件级结论：全部菜品都因行级问题被排除 → 成本卡为空
ISSUE_NO_USABLE_DISHES = "no_usable_dishes"


class CostError(ValueError):
    """输入不合法（结构缺陷 / 形态问题）。内核映射退出码 2。"""


class FormulaError(ValueError):
    """公式前提校验失败（定义域越界 / 缺基准）。"""


class SourceMissing(ValueError):
    """参数未挂来源标记，或来源类型未登记。"""

    code = "source_missing"


class InputRequired(CostError):
    """参数包**本不承载**该值：放行门控，但取数点必须显式索取，缺失即不可算。"""


class ParamsError(CostError):
    """参数包本身不可用（缺分区 / 状态未登记 / 作用域未登记）。"""


class ParamsPending(ParamsError):
    """该作用域引用了 ``pending`` 条目 → 干预依据不完备，判定路径阻断。"""

    def __init__(self, scope: str, items: Sequence[str]) -> None:
        self.scope = scope
        self.items = tuple(items)
        super().__init__(
            "作用域 %s 存在待核对参数，判定路径已阻断: %s"
            % (scope, "、".join(self.items))
        )


# ------------------------------------------------------------------ 数值与来源
def to_decimal(value: Any) -> Decimal:
    """把输入安全转成 Decimal（float 先经 str，避免二进制尾差；bool 拒收）。"""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError("bool 不是合法数值")
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value.strip())
    raise TypeError("无法转成 Decimal 的类型: %s" % type(value).__name__)


def quantize_money(value: Any) -> Decimal:
    """金额/单价呈现口径：两位小数，ROUND_HALF_UP。"""
    return to_decimal(value).quantize(MONEY_EXP, rounding=ROUND_HALF_UP)


def quantize_rate(value: Any) -> Decimal:
    """比率呈现口径：四位小数（百分比两位），ROUND_HALF_UP。"""
    return to_decimal(value).quantize(RATE_EXP, rounding=ROUND_HALF_UP)


def make_source(kind: str, ref: str, date: Optional[str] = None,
                note: Optional[str] = None) -> Dict[str, Any]:
    """构造参数来源标记；``kind`` 不在白名单即抛错。"""
    if kind not in SOURCE_KINDS:
        raise SourceMissing("未登记的参数来源类型: %r" % (kind,))
    if not ref:
        raise SourceMissing("参数来源缺少 ref 标识")
    return {"kind": kind, "ref": ref, "date": date, "note": note}


def validate_source(source: Any) -> Mapping:
    """校验来源标记；缺失或类型未登记抛 :class:`SourceMissing`。"""
    if not isinstance(source, Mapping):
        raise SourceMissing("参数未挂来源标记")
    kind = source.get("kind")
    if kind not in SOURCE_KINDS:
        raise SourceMissing("未登记的参数来源类型: %r" % (kind,))
    if not source.get("ref"):
        raise SourceMissing("参数来源缺少 ref 标识")
    return source


# ------------------------------------------------------------------ 换算公式 F1–F5
def net_unit_price(purchase_unit_price: Any, yield_rate: Any) -> Decimal:
    """F1 净料单价：``net_unit_price = purchase_unit_price / yield_rate``。

    ``yield_rate`` 是「净料重 / 毛料重」，取值域 ``(0, 1]``——因此净料单价必然
    ≥ 毛料单价。损耗率不是第二个参数：``loss_rate = 1 - yield_rate`` 是同一参数的
    换算面，只在呈现层由它导出（避免同一事实两份真相）。
    """
    price = to_decimal(purchase_unit_price)
    rate = to_decimal(yield_rate)
    if price < 0:
        raise FormulaError("毛料单价不得为负")
    if rate <= 0:
        raise FormulaError("净料率必须大于 0")
    if rate > 1:
        raise FormulaError("净料率不得超过 1（净料重不能多于毛料重）")
    return price / rate


def loss_rate(yield_rate: Any) -> Decimal:
    """净料率的换算面：损耗率 = 1 − 净料率。仅用于呈现，不参与计算。"""
    rate = to_decimal(yield_rate)
    if rate <= 0:
        raise FormulaError("净料率必须大于 0")
    if rate > 1:
        raise FormulaError("净料率不得超过 1")
    return Decimal(1) - rate


def dish_cost(items: Sequence[Tuple[Any, Any]]) -> Decimal:
    """F2 单份成本：``dish_cost = Σ_i (net_unit_price_i × qty_i)``。

    ``items`` 为 ``(net_price, qty)`` 序列。BOM 不得为空——空 BOM 是数据缺陷，
    不是「成本为 0」。
    """
    pairs = list(items)
    if not pairs:
        raise FormulaError("菜品配方 BOM 不得为空")
    total = Decimal(0)
    for net_price, qty in pairs:
        price = to_decimal(net_price)
        quantity = to_decimal(qty)
        if price < 0:
            raise FormulaError("净料单价不得为负")
        if quantity < 0:
            raise FormulaError("用量不得为负")
        total += price * quantity
    return total


def suggested_price(cost: Any, target_margin: Any) -> Decimal:
    """F3 建议售价：``suggested_price = dish_cost / (1 - target_margin)``。

    ``target_margin = 1`` 不可解（除零）。返回值**先量化**——真实挂牌价是分位值；
    F4 据此反算实际毛利率（量化作用于中间量的唯一例外）。
    """
    cost_value = to_decimal(cost)
    margin = to_decimal(target_margin)
    if cost_value < 0:
        raise FormulaError("成本不得为负")
    if margin < 0:
        raise FormulaError("目标毛利率不得为负")
    if margin >= 1:
        raise FormulaError("目标毛利率必须小于 1（等于 1 时售价无解）")
    return quantize_money(cost_value / (Decimal(1) - margin))


def actual_margin(price: Any, cost: Any) -> Decimal:
    """F4 实际毛利率：``actual_margin = (price - dish_cost) / price``。

    售价为 0 不可解。负毛利**如实报负**，不夹断为 0。
    """
    price_value = to_decimal(price)
    cost_value = to_decimal(cost)
    if price_value <= 0:
        raise FormulaError("售价必须大于 0")
    if cost_value < 0:
        raise FormulaError("成本不得为负")
    return (price_value - cost_value) / price_value


def change_rate(old_price: Any, new_price: Any) -> Decimal:
    """F5 涨跌幅：``change_rate = (new_price - old_price) / old_price``。

    旧价为 0 不可解（不是除零错误，是缺基准）。涨为正、跌为负，符号如实。
    """
    old = to_decimal(old_price)
    new = to_decimal(new_price)
    if old <= 0:
        raise FormulaError("旧价格必须大于 0（缺对比基准）")
    if new < 0:
        raise FormulaError("新价格不得为负")
    return (new - old) / old


# ------------------------------------------------------------------ 进货单三态
def _issue(line: Any, status: str, code: str, reason: str) -> Dict[str, Any]:
    """异常清单条目。``code`` 是机读判据，``reason`` 是人读说明（两者都给）。"""
    return {"line": line, "status": status, "code": code, "reason": reason}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def validate_header(header: Sequence[Any]) -> Tuple[Tuple[str, ...], List[str]]:
    """表头形态校验：返回 ``(规范表头, 未登记列名)``；形态不可用即抛错。

    表头必须是**已解码的字符串**：字节（未解码的原始内容）一律拒收——把
    ``b"\\xd2\\xbb"`` 当列名「猜着解」只会得到一堆乱码列名，比报错危险得多。
    """
    if header is None:
        raise CostError("进货单缺少表头")
    for name in header:
        if name is not None and not isinstance(name, str):
            raise CostError(
                "进货单表头必须是已解码字符串（收到 %s）——编码由输入层判定"
                % type(name).__name__)
    names = [_text(name) for name in header]
    if not any(names):
        raise CostError("进货单缺少表头")
    missing = [column for column in REQUIRED_COLUMNS if column not in names]
    if missing:
        raise CostError(
            "进货单表头缺少必填列: %s（实际表头: %s）"
            % ("、".join(missing), "、".join(name for name in names if name) or "空"))
    unknown_cols = [name for name in names if name and name not in COLUMN_MAP]
    return tuple(names), unknown_cols


def judge_rows(header: Sequence[Any], rows: Sequence[Sequence[Any]],
               source: Optional[Mapping] = None) -> Dict[str, Any]:
    """逐行三态判定（纯函数）。

    返回 ``{"rows", "issues", "unknown_columns", "status_counts", "header"}``。

    **红线**：``unknown`` 不等于 ``ok``（「没看到」≠「没有」）；异常行一律列入清单
    并计数，绝不静默丢弃后报告「导入成功」。批量判定单行异常**不中断整批**。

    两种 ``unknown`` 的行是否仍可用是分开的口径：

    - **未登记列名**（表头级）：只是多了一列不认识的，已登记列照常解析 →
      记一条 ``line=1`` 的异常，**行仍可用**；
    - **整行结构不可解析**（行级）：字段数多于表头 → 列对齐已不可信 →
      该行记 ``unknown`` 且**不入库**（宁可少一行可用数据，不可把错位的值当成对的）。

    ``source`` 是进货单的来源标记（文件级）。**来源缺失不在这里判**：本函数只做
    三态判定，来源在消费点（``compute_costcard``）校验——构造期校验等于只守了
    自己造的那一半。
    """
    names, unknown_cols = validate_header(header)
    issues: List[Dict[str, Any]] = []
    for column in unknown_cols:
        issues.append(_issue(1, STATUS_UNKNOWN, ISSUE_MAPPING_UNCERTAIN,
                             "未登记列名（mapping_uncertain）: %s" % column))

    out: List[Dict[str, Any]] = []
    for index, raw in enumerate(rows):
        line_no = index + 2  # 表头占第 1 行
        values = list(raw or ())
        if len(values) > len(names):
            issues.append(_issue(
                line_no, STATUS_UNKNOWN, ISSUE_STRUCTURE,
                "整行结构不可解析：字段数多于表头（多余 %d 个），列对齐不可信"
                % (len(values) - len(names))))
            continue

        # 列名 → 字段名（未登记列被忽略，但已在表头级记过一条）
        row = {}
        for position, column in enumerate(names):
            value = _text(values[position]) if position < len(values) else ""
            field = COLUMN_MAP.get(column)
            if field is not None:
                row[field] = value

        name = row.get("name", "")
        if not name:
            issues.append(_issue(line_no, STATUS_INVALID, ISSUE_REQUIRED_EMPTY,
                                 "必填列「品名」为空"))
            continue

        try:
            qty = to_decimal(row.get("qty", ""))
        except (InvalidOperation, TypeError, ValueError):
            issues.append(_issue(line_no, STATUS_INVALID, ISSUE_NOT_NUMERIC,
                                 "数量非数值: %r" % row.get("qty")))
            continue

        try:
            unit_price = to_decimal(row.get("unit_price", ""))
        except (InvalidOperation, TypeError, ValueError):
            issues.append(_issue(line_no, STATUS_INVALID, ISSUE_NOT_NUMERIC,
                                 "单价非数值: %r" % row.get("unit_price")))
            continue

        if qty < 0 or unit_price < 0:
            issues.append(_issue(line_no, STATUS_INVALID, ISSUE_NEGATIVE,
                                 "数量/单价为负"))
            continue

        unit = row.get("unit", "")
        if unit and unit not in KNOWN_UNITS:
            issues.append(_issue(line_no, STATUS_UNKNOWN, ISSUE_UNIT_UNREGISTERED,
                                 "单位未登记: %s" % unit))

        entry = {
            "line": line_no,
            "date": row.get("date") or None,
            "name": name,
            "category": row.get("category") or None,
            "qty": qty,
            "unit": unit or None,
            "unit_price": unit_price,
        }
        if source is not None:
            entry["source"] = dict(source)
        out.append(entry)

    counts = {STATUS_OK: len(out), STATUS_INVALID: 0, STATUS_UNKNOWN: 0}
    for issue in issues:
        counts[issue["status"]] = counts.get(issue["status"], 0) + 1
    return {"rows": out, "issues": issues, "unknown_columns": unknown_cols,
            "status_counts": counts, "header": names}


def build_food_library(rows: Sequence[Mapping]) -> Dict[str, Dict[str, Any]]:
    """由进货行构建食材库：品名 → 类别/单位/参考价/来源。

    **同品名取舍口径（显式登记）**：同品名出现多条时，**取最后一条的价**
    （后出现者覆盖前者 = 「该品名的最新进货价」）。「取第一条」与「取最后一条」
    都能自圆其说，不登记就会在别处长出第二份实现。
    """
    library: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        library[row["name"]] = {
            "category": row.get("category"),
            "unit": row.get("unit"),
            "ref_price": to_decimal(row["unit_price"]),
            "source": row.get("source"),
        }
    return library


def duplicate_names(rows: Sequence[Mapping]) -> List[str]:
    """返回在进货单里出现多次的品名（按首次出现顺序，确定性）。

    重复不是错误（同一食材多批次进货是常态），但**必须可观测**——否则
    「同品名取最后一条」的取舍是隐性的。
    """
    seen, duplicates = set(), []
    for row in rows:
        name = row["name"]
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    return duplicates


# ------------------------------------------------------------------ 参数门控
def validate_params(params: Mapping) -> Mapping:
    """参数包形状校验：三个分区都在，条目 ``status`` 已登记。"""
    if not isinstance(params, Mapping):
        raise ParamsError("参数包根节点必须是对象")
    for scope, section in SCOPE_SECTIONS.items():
        if section not in params:
            raise ParamsError("参数包缺少分区 %r（作用域 %s）" % (section, scope))
    for section in SCOPE_SECTIONS.values():
        for name, entry in params[section].items():
            if not isinstance(entry, Mapping) or "status" not in entry:
                raise ParamsError("参数条目 %r 不成形（缺 status）" % name)
            if entry.get("status") not in (PARAM_VERIFIED, PARAM_PENDING,
                                           PARAM_INPUT_REQUIRED):
                raise ParamsError("条目 %r 的 status 未登记: %r"
                                  % (name, entry.get("status")))
    return params


def scope_report(params: Mapping, scope: str) -> Dict[str, List[str]]:
    """列出某作用域的三态清单（供「未启用清单」显式可见）。"""
    if scope not in SCOPE_SECTIONS:
        raise ParamsError("未登记的计算作用域: %r" % (scope,))
    verified, pending, input_required = [], [], []
    for name, entry in params[SCOPE_SECTIONS[scope]].items():
        status = entry.get("status")
        if status == PARAM_VERIFIED:
            verified.append(name)
        elif status == PARAM_PENDING:
            pending.append(name)
        elif status == PARAM_INPUT_REQUIRED:
            input_required.append(name)
        else:
            raise ParamsError("条目 %r 的 status 未登记: %r" % (name, status))
    return {"scope": scope, "verified": verified, "pending": pending,
            "input_required": input_required}


def effective_params(params: Mapping, scope: str) -> Dict[str, Mapping]:
    """取某作用域下**可参与判定**的参数（**只含 verified 条目**）。

    - 该作用域存在 ``pending`` 条目 → 抛 :class:`ParamsPending`（阻断该 scope）；
    - 该作用域存在 ``input_required`` 条目 → **放行门控**（不抛错）：这些条目
      **本不由参数包承载**，其值不进入可用集；取数点若真需要它们须显式索取；
    - 每个条目的 ``source`` 都经 :func:`validate_source` 校验——**未挂来源的参数
      不得进入计算路径**。

    「未核对」与「本不由参数包承载」是两回事：前者阻断，后者放行但必索。
    """
    validate_params(params)
    report = scope_report(params, scope)
    if report["pending"]:
        raise ParamsPending(scope, report["pending"])
    out: Dict[str, Mapping] = {}
    for name, entry in params[SCOPE_SECTIONS[scope]].items():
        validate_source(entry.get("source"))
        if entry.get("status") == PARAM_VERIFIED:
            out[name] = entry
    return out


def yield_rate_for(cost_params: Mapping, food: str) -> Tuple[Decimal, Mapping]:
    """取某食材的净料率（``cost_params`` = ``effective_params(params, "cost")``）。

    两种「净料率有问题」必须分开：

    - **缺条目**（本不由参数包承载）→ 缺输入 → 抛 :class:`InputRequired`；
    - **有条目但值越界** ∉ (0,1] → 该行记为行级 issue（由 ``compute_costcard`` 记），
      不在本函数抛错。
    """
    entry = cost_params.get(food)
    if not isinstance(entry, Mapping) or "value" not in entry:
        raise InputRequired(
            "食材「%s」缺少净料率（本不由参数包承载，需显式提供）" % food)
    return to_decimal(entry["value"]), entry


def _sourced(source: Any, label: str) -> Mapping:
    """在**消费点**显式校验来源标记（未挂来源的参数不得进入计算路径）。"""
    try:
        return validate_source(source)
    except SourceMissing as exc:
        raise SourceMissing("参数「%s」的来源标记不合法（%s）" % (label, exc))


# ------------------------------------------------------------------ 成本卡 / 定价 / 预警
def _line_issue(dish: str, food: str, code: str, reason: str) -> Dict[str, Any]:
    """成本卡行级异常条目：定位是「菜品·食材」，不是 CSV 行号。"""
    return {"line": None, "where": "菜品「%s」·食材「%s」" % (dish, food),
            "status": STATUS_INVALID, "code": code, "reason": reason}


def compute_costcard(dishes: Sequence[Mapping], library: Mapping,
                     cost_params: Mapping, qty_source: Mapping) -> Dict[str, Any]:
    """成本卡：F1 净料换算 → F2 BOM 汇总。逐行留痕可追溯。

    返回 ``{"cards": [...], "issues": [...]}``。

    行级前提校验失败（净料率越界 / 用量非法）→ 记一条行级 issue，**整道菜**排除出
    成本卡（成本是各行之和，丢掉一行再报出一个「看起来完整」的合计，等于把一个
    自洽但偏低的数字当成对的）。
    """
    _sourced(qty_source, "BOM 用量")
    cards, issues = [], []
    for dish in dishes:
        name = dish.get("name")
        if not name:
            raise CostError("BOM 中存在缺少 name 的菜品条目")
        items = dish.get("items") or []
        lines, pairs, dish_issues = [], [], []
        for item in items:
            food = item.get("food")
            if food not in library:
                raise CostError("菜品「%s」引用了食材库中不存在的食材: %s"
                                % (name, food))

            rate, entry = yield_rate_for(cost_params, food)
            _sourced(entry.get("source"), "净料率")
            if not (Decimal(0) < rate <= Decimal(1)):
                dish_issues.append(_line_issue(
                    name, food, ISSUE_YIELD_OUT_OF_RANGE,
                    "净料率越界（须 ∈ (0,1]，实为 %s）" % rate))
                continue

            try:
                qty = to_decimal(item.get("qty", "0"))
            except (InvalidOperation, TypeError, ValueError):
                dish_issues.append(_line_issue(
                    name, food, ISSUE_QTY_INVALID, "用量非数值: %r" % (item.get("qty"),)))
                continue
            if qty < 0:
                dish_issues.append(_line_issue(
                    name, food, ISSUE_QTY_INVALID, "用量为负: %s" % qty))
                continue

            purchase_price = library[food]["ref_price"]
            net_price = net_unit_price(purchase_price, rate)
            line_cost = net_price * qty
            lines.append({
                "food": food,
                "purchase_unit_price": quantize_money(purchase_price),
                "yield_rate": quantize_rate(rate),
                "loss_rate": quantize_rate(loss_rate(rate)),
                "net_unit_price": quantize_money(net_price),
                "qty": qty,
                "line_cost": quantize_money(line_cost),
                "yield_source": entry.get("source"),
                "price_source": _sourced(library[food].get("source"), "进货单价"),
                "qty_source": qty_source,
            })
            pairs.append((net_price, qty))

        if dish_issues:
            issues.extend(dish_issues)
            continue

        cost = dish_cost(pairs)
        cards.append({
            "dish": name,
            "lines": lines,
            "cost": quantize_money(cost),
            "cost_exact": cost,
        })
    return {"cards": cards, "issues": issues}


def compute_pricing(cards: Sequence[Mapping],
                    pricing_params: Mapping) -> List[Dict[str, Any]]:
    """毛利率定价：F3 反推建议售价 + F4 实际毛利率。"""
    entry = pricing_params.get("target_margin") or {}
    if "value" not in entry:
        raise FormulaError("参数包缺少目标毛利率（需显式提供）")
    target = to_decimal(entry["value"])
    out = []
    for card in cards:
        price = suggested_price(card["cost_exact"], target)
        margin = actual_margin(price, card["cost_exact"])
        out.append({
            "dish": card["dish"],
            "cost": card["cost"],
            "target_margin": quantize_rate(target),
            "suggested_price": price,
            "actual_margin": quantize_rate(margin),
            "margin_source": entry.get("source"),
        })
    return out


def diff_prices(old_prices: Mapping, new_prices: Mapping) -> List[Dict[str, Any]]:
    """两期快照的价格差异，按涨跌幅降序。

    逐条 ``{name, old_price, new_price, change_rate, status}``；``status`` ∈
    ``up``/``down``/``flat``/``new``（仅新期有，无对比基准）/``gone``（仅旧期有）。
    **缺旧价一律记 ``new``，不臆造涨跌幅。**
    """
    names = set(old_prices) | set(new_prices)
    rows = []
    for name in sorted(names):
        old = old_prices.get(name)
        new = new_prices.get(name)
        if old is None:
            rows.append({"name": name, "old_price": None,
                         "new_price": quantize_money(new), "change_rate": None,
                         "status": "new"})
            continue
        if new is None:
            rows.append({"name": name, "old_price": quantize_money(old),
                         "new_price": None, "change_rate": None,
                         "status": "gone"})
            continue
        rate = change_rate(old, new)
        if rate > 0:
            status = "up"
        elif rate < 0:
            status = "down"
        else:
            status = "flat"
        rows.append({"name": name, "old_price": quantize_money(old),
                     "new_price": quantize_money(new),
                     "change_rate": quantize_rate(rate), "status": status})

    def sort_key(row):
        rate = row["change_rate"]
        # 无对比基准的（new/gone）排在最后
        return (1, Decimal(0)) if rate is None else (0, -rate)

    rows.sort(key=sort_key)
    return rows


def flag(changes: Sequence[Mapping], threshold: Any) -> List[Mapping]:
    """标记超过阈值的食材（按绝对涨跌幅比较，涨跌都提示）。"""
    value = to_decimal(threshold)
    out = []
    for row in changes:
        rate = row["change_rate"]
        if rate is None:
            continue
        if abs(rate) >= value:
            out.append(row)
    return out


def impacted_dishes(cards: Sequence[Mapping], changes: Sequence[Mapping],
                    old_prices: Mapping, new_prices: Mapping,
                    cost_params: Optional[Mapping] = None) -> List[Dict[str, Any]]:
    """受影响菜品清单：BOM 含该食材者，逐菜重算前后成本差（按涨跌幅降序）。

    重算必须用与成本卡同一份净料率——否则前后成本差会把口径差异算进去。
    某期缺该食材 → 用成本卡原价（不臆造）。
    ``cost_params`` 为 ``None`` 时按成本卡行自带的净料率重算（等价口径）。
    """
    change_by_name = {row["name"]: row for row in changes}

    def dish_cost_with(prices, card):
        items = []
        for line in card["lines"]:
            food = line["food"]
            if food not in prices:
                net_price = line["net_unit_price"]
            elif cost_params is not None:
                rate, _entry = yield_rate_for(cost_params, food)
                net_price = net_unit_price(prices[food], rate)
            else:
                net_price = net_unit_price(prices[food], line["yield_rate"])
            items.append((net_price, line["qty"]))
        return dish_cost(items)

    out = []
    for card in cards:
        touched = [line["food"] for line in card["lines"]
                   if line["food"] in change_by_name]
        if not touched:
            continue
        old_cost = dish_cost_with(old_prices, card)
        new_cost = dish_cost_with(new_prices, card)
        delta = new_cost - old_cost
        rate = change_rate(old_cost, new_cost) if old_cost > 0 else None
        out.append({
            "dish": card["dish"],
            "touched_foods": sorted(touched),
            "old_cost": quantize_money(old_cost),
            "new_cost": quantize_money(new_cost),
            "delta": quantize_money(delta),
            "change_rate": quantize_rate(rate) if rate is not None else None,
        })
    out.sort(key=lambda row: (row["change_rate"] is None,
                              -(row["change_rate"] or Decimal(0))))
    return out


def require_distinct_periods(old_date: Any, new_date: Any) -> None:
    """两期必须是可区分的不同数据日。

    数据日相同即「两期退化成同一期」：涨跌幅全为 0 却会以「无异常」的面貌呈现。
    故显式拒绝（输入不合法），不静默产出无意义的「全平」结果。
    """
    if old_date == new_date:
        raise CostError("两期快照数据日相同（%s）——对比退化成同一期；"
                        "请给出不同数据日的快照（旧→新）" % (old_date,))