# 器官 `cost-card`

> 条文判定器官 · 版本 `0.2.0` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：参数包快照 `2026-10-14`（10 条净料率 + 目标毛利率 + 波动预警阈值，**全部 `verified`**）
> 条文库坐标：`2026-10-14`

一句话：**给一份进货行 + 菜品配方 + 参数包，判这套成本卡能不能成立、哪一步不成立、
哪几道菜被价格波动波及**。

> **依据不是法规条文**。净料率全部是「内置经验默认值（非官方数据）」，目标毛利率与
> 阈值是「用户配置项」。来源仓 `data/README.md` 实测《餐饮业成本核算规范》SB/T 10573
> **查证失败**（检索 43 条无成本核算类标准），故本器官**不引用、不编造文号**：
> 条款锚点登记为**参数包条目**（`param:*`）与**进货单列名契约**（`import:column-map`），
> 条目的来源类型（内置经验值 / 用户配置 / 快照）逐条写进 `basis_ref.quote`。

## 1. 输入

```bash
clauseproof check cost-card \
  --input samples/cost-card/ledger-demo.json \
  --basis src/clauseproof/packs/cost-card/data/clauses.json
clauseproof check cost-card \
  --input samples/cost-card/ledger-clean.json \
  --basis src/clauseproof/packs/cost-card/data/clauses.json --json
clauseproof check cost-card \
  --input samples/cost-card/ledger-demo-alert.json \
  --basis src/clauseproof/packs/cost-card/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `purchase_ledger.header` | ✅ | 表头（**已解码字符串**）；必填列 `品名`/`数量`/`单价`，未登记列记 `unknown` |
| `purchase_ledger.rows` | ✅ | 行数组的数组（字段值按表头顺序）；行号 = 下标 + 2（表头占第 1 行） |
| `purchase_ledger.source` | ✅ | 进货单来源标记 `{kind, ref, date?, note?}`；`kind` ∈ `snapshot`/`user`/`builtin_experience` |
| `dishes[]` | — | 菜品配方 `{name, items:[{food, qty}]}`；缺省时只判进货单（对应旧仓 `check --purchases`） |
| `dishes_source` | 有 `dishes` 时必填 | 用量的来源标记（文件级，逐行共享同一出处） |
| `snapshots.old` / `snapshots.new` | — | 两期价格快照 `{date, prices:{name: 价}, source}`；两期数据日相同 → 输入不合法 |

```json
{
  "purchase_ledger": {
    "header": ["日期", "品名", "类别", "数量", "单位", "单价", "金额"],
    "rows": [["2026-10-01", "大白菜", "蔬菜", "10", "斤", "1.20", "12.00"]],
    "source": {"kind": "user", "ref": "purchases.csv"}
  },
  "dishes": [{"name": "醋溜白菜", "items": [{"food": "大白菜", "qty": "1.5"}]}],
  "dishes_source": {"kind": "user", "ref": "bom.json"}
}
```

> **CSV 文件本身不进器官**：器官收的是「已解码的表头 + 行数组」。文件读取、CSV 引号/
> 换行处理、以及**只收 UTF-8（含 BOM）的编码门**都留在输入层（`SKELETON-SPEC` §2：
> 器官不得做文件 IO）。来源仓的编码口径原样保留在输入层，见 §5。

## 2. 规则

### 2.1 进货行三态（`engine.judge_rows`）

| 状态 | 触发 | 计入异常清单 | 该行可用 |
|---|---|---|---|
| `ok` | 列名白名单命中 + 类型校验通过 | 否 | 是 |
| `invalid` | 必填列为空 / 数值非数值 / 数量或单价为负 | 是（`fail`，阻断） | 否 |
| `unknown` | 未登记列名（表头级）/ 整行结构不可解析 / 单位未登记 | 是（`not_applicable`） | 见下 |

两种 `unknown` 的行是否可用**是分开的口径**：未登记列名只是「多了一列不认识的」，
已登记列照常解析，**行仍可用**；整行结构不可解析（字段数多于表头 → 列对齐不可信）
该行**不入库**——宁可少一行可用数据，不可把错位的值当成对的。单位未登记只提示，
**行仍可用**（首期不做单位换算）。

其余已登记口径：金额列属留档参考，**不参与计算、不校验数值性**；空白行不是记录；
短行缺失的格子按空串处理（缺 `品名` 即 `invalid`）；同名列取最后一列的值。

### 2.2 换算公式 F1–F5（`engine`）

| 公式 | 定义 | 前提 |
|---|---|---|
| F1 净料单价 | `net_unit_price = purchase_unit_price / yield_rate` | `price ≥ 0`；`0 < rate ≤ 1` |
| F1′ 损耗率（呈现） | `loss_rate = 1 - yield_rate` | 同上 |
| F2 单份成本 | `dish_cost = Σ_i (net_unit_price_i × qty_i)` | BOM 非空；单价/用量 ≥ 0 |
| F3 建议售价 | `suggested_price = dish_cost / (1 - target_margin)`，**先量化到分** | `cost ≥ 0`；`0 ≤ margin < 1` |
| F4 实际毛利率 | `actual_margin = (price - dish_cost) / price` | `price > 0`；`cost ≥ 0` |
| F5 涨跌幅 | `change_rate = (new_price - old_price) / old_price` | `old_price > 0`；`new_price ≥ 0` |

全程 `Decimal`（`float` 先经 `str` 转换，避免二进制尾差）；金额两位、比率四位，
`ROUND_HALF_UP`。负毛利**如实报负**，不夹断为 0。

### 2.3 参数门控（`engine.effective_params`）

按计算路径分作用域——`cost`（净料率）/ `pricing`（目标毛利率）/ `alert`（波动阈值），
各只校验自己引用的条目。**不用「整包全 verified」当唯一门**：与核算无关的 `pending`
不该阻断整条路径。

| 条目状态 | 语义 | 本器官表现 |
|---|---|---|
| `verified` | 放行 | 值进入计算路径 |
| `pending` | 「未核对」 | 该作用域判定路径阻断 → **契约违约（退出码 3）** |
| `input_required` | 「本不由参数包承载」 | 放行门控，但取数点必索 → 缺值即 **输入不合法（退出码 2）** |

每个条目的 `source` 在**消费点**校验（不只在构造期）：未挂来源的参数不得进入计算路径。
随包 12 条目全部 `verified`；`pending` / `input_required` 两条分支只由测试构造。

### 2.4 成本卡与波动预警

- **行级失败不中断整批**：某道菜任一行不成立（净料率越界 / 用量非法）→ **整道菜**排除
  并逐条列原因。丢掉一行再报出「看起来完整」的合计，等于把自洽但偏低的数字当成对的。
- **BOM 引用了不存在于食材库的食材** → 输入不合法（退出码 2），不静默跳过。
- **同品名取最后一条价**（= 最新进货价），重复品名可观测（记一条 `not_applicable`）。
- **波动预警**：两期快照逐食材分类 `up`/`down`/`flat`/`new`/`gone`；缺旧价记 `new`、
  缺新价记 `gone`，**都不臆造涨跌幅**。`|涨跌幅| ≥ 阈值`（含等于）标记为预警项。
- **预警 ≠ 判定**：预警项记 `not_applicable`（结论是「需复核」，不是「不合规」），
  故波动本身**不增加阻断计数**。
- **判定域 = 本张菜单**：只对 BOM 引用的食材与菜品出账；整份快照的市场价（demo 两期
  439 个品名 / 141 项超阈值）不属本次判定域。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| 进货行 `invalid` | `fail` | **是**（退出码 1） | `import:column-map` |
| 进货行 `unknown` / 重复品名 | `not_applicable` | 否 | `import:column-map` |
| 零可用行 / 零可用菜品 | `fail` | **是** | `import:column-map` / `param:yield-rate` |
| 菜品成本卡成立 | `pass` | 否 | `param:yield-rate`（章节） |
| 菜品被行级问题排除 | `fail` | **是** | `param:yield-rate:<食材>`（出问题的条目） |
| 定价成立 | `pass` | 否 | `param:target-margin` |
| 价格波动（超/未超阈值） | `not_applicable` | 否 | `param:alert-threshold` |

`evidence` 携带机读事实：`line`/`code`/`status`（行）、`dish`/`cost`/`foods`（菜）、
`cost`/`suggested_price`/`actual_margin`（定价）、`food`/`status`/`change_rate`/
`threshold`/`flagged`/`periods`（预警）。数值一律字符串化（`Decimal` 不进 JSON）。

### 3.2 人读（demo，退出码 1）

```text
clauseproof :: cost-card 0.2.0 :: ledger-demo.json
[pass] dish.cost:醋溜白菜 — 菜品「醋溜白菜」单份成本 55.04 元（2 行净料换算 + BOM 汇总） :: 参数包 / 净料率 (2026-10-14)
[pass] pricing.price:醋溜白菜 — 菜品「醋溜白菜」建议售价 137.61 元（成本 55.04 / 目标毛利率 0.6000 / 实际毛利率 0.6000） :: 参数包 / 目标毛利率 (2026-10-14)
...
[fail] purchase.row:L13:not_numeric — 数量非数值: 'abc' :: 进货单 / 列名白名单 (2026-10-14)
合计 17 条，阻断 3 条（pass=10 fail=3 na=4）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无阻断（全部 `pass` / `not_applicable`；预警项不阻断） |
| `1` | 有阻断（进货行 `invalid`、菜品被排除、零可用行/菜品） |
| `2` | 输入不合法（缺 `purchase_ledger`、表头缺必填列、BOM 形态问题、引用不存在食材、两期同数据日、缺净料率条目） |
| `3` | 契约违约（条文库版本与参数包快照不符、参数包存在 `pending` 条目） |

> **条文库缺某条依据时**，内核抛 `BasisMissing` 并把它归入「输入不可用」→ **退出码 2**
> （`ORG-PLAYBOOK` §4 的口径是 3；本产品内核实现为 2，未改内核，此处如实登记）。

> 漏 `--basis` 时条文库版本为空 → 版本不符 → **退出码 3**，是契约的正确行为。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 进货单三态判定 | ✅ | `engine.judge_rows`（含行级/表头级两种 `unknown` 的分开口径） |
| 换算公式 F1–F5 | ✅ | `engine`（唯一实现处） |
| 参数包三态门控（分作用域） | ✅ | `engine.effective_params` / `scope_report` |
| 参数来源标记（消费点校验） | ✅ | `engine._sourced` |
| 成本卡 / 定价 / 波动 / 受影响菜品 | ✅ | `engine.compute_*` / `diff_prices` / `flag` / `impacted_dishes` |
| 两期同数据日拒绝 | ✅ | `engine.require_distinct_periods` |
| CSV 物理解析 / 编码判定 / 文件发现 | ❌ | 输入层；器官收已解码的表头与行数组 |
| 快照文件读取 / sha256 台账 | ❌ | 输入层；快照价格与来源由 subject 提供 |
| 报告（Markdown / XLSX）与 CLI | ❌ | 输出排版属产品层（`SKELETON-SPEC` §2） |
| GUI（PySide6）/ PyInstaller 打包 | ❌ | 交付面 |
| 基准 runner / 门槛 manifest / 覆盖度登记 | ❌ | 产品级基准；判据 1 用真值库 41 用例活跃对账承接 |
| 仓库门（EOL / 零字面量 / 冻结产物 / 布局 / stdlib 兼容） | ❌ | 仓库纪律；本产品由 `tests/` 全量门与本器官 §一 AST 门接管 |

## 5. 口径差（如实登记）

1. **输入从文件变成 subject**：`purchase_ledger`（表头 + 行数组 + 来源）、`dishes`、
   `snapshots` 由输入提供。器官不读文件 / 不读环境 / 不读时钟，**不做编码判定**。
   来源仓只收 UTF-8（含 BOM）的编码门留在输入层；器官对**字节表头**显式拒收
   （`validate_header`），不把未解码字节当列名静默解成乱码。
2. **参数包是器官内的字面量**（`registry.PARAMS`），来源 `params.json` 逐字节随包
   （sha256 `4d7c4c55…8db9c`，与来源件相同）并由漂移门逐条比对。来源仓允许用户覆盖
   参数；本器官的 `evaluate` 只用随包参数包，覆盖入口仅供测试
   （`evaluate_with_params`），不暴露为输入字段——**依据不从输入取**。
3. **`input_required` 语义差**：来源仓「该作用域有 input_required → 放行，取数点必索」；
   本器官同样放行，但缺值表现为 `FormulaError` → **退出码 2**（来源仓亦为 2）。
4. **零可用菜品**：来源仓 `run` 直接 `exit 2`（无法继续定价）；本器官按 `check` 语义
   **出账**（每道菜一条 `fail` + 一条文件级 `fail`），退出码 1。选 `check` 是因为
   clauseproof 只有 `list` / `check` 两个子命令，出账比抛错更能说明「哪里不成立」。
5. **预警记 `not_applicable` 而非 `fail`**：来源仓「预警 ≠ 判定，不自动改价」；
   本器官保留该语义（预警项不阻断），但把「超阈值」写进 `evidence.flagged`
   与 message，故不会退化成「无异常」。
6. **判定域收敛到菜单**：来源仓 `flagged` 覆盖整份快照（demo 141 项）；本器官只对
   BOM 引用的食材/菜品出账——否则 439 个市场品名会淹没本次核算结论。整份快照的
   统计口径由真值库用例（`total:439` / `count:up=128` / `flagged:141`）活跃对账保留。
7. **单位不换算**：来源仓首期即不换算，未登记单位只提示；本器官原样保留。
8. **交易所与数据日**：快照价格与 `date` 由输入提供；器官不读 `.meta.json`、
   不核 sha256（判据 4 与真值库只读拷贝承担可复核性）。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 270**（16 文件，271 collected / **1 failed**）/ 新器官实跑 **N = 336** | **过**（336 ≥ 270） |
| 2 | README 示例命令 rc 相同 | 旧 `python -m rcc.cli run --purchases src/rcc/data/samples/purchases-demo.csv --bom src/rcc/data/samples/bom-demo.json` rc **1** / 新 `clauseproof check cost-card --input samples/cost-card/ledger-demo.json --basis …/data/clauses.json` rc **1**；五道菜成本与建议售价**逐值一致**（55.04/137.61、7.62/19.05、16.84/42.09、100.12/250.30、10.44/26.10），异常 6 条同码 | **过**（rc 1 = 1） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 336 ≥ 270；`def test_` **336** ≥ 旧层 AST **261**；文件数旧 16 → 新 **2**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（62 条目）；`clauseproof/packs/cost-card/data/` **2 件**：`clauses.json` 4347 B / `params.json` 4318 B；解包后 `list` = **4 器官**、demo `check` rc **1** | **过** |

**判据 1 的命令与输出原文**（来源仓只读；`PYTHONDONTWRITEBYTECODE=1` 防写旧仓缓存）：

```bash
cd <来源仓>
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/benchmark/test_runner.py tests/guards/test_eol_gate.py \
  tests/guards/test_formula_single_source.py tests/guards/test_gates.py \
  tests/guards/test_import_dispatch.py tests/guards/test_pack_gate.py \
  tests/guards/test_repo_gates.py tests/guards/test_snapshot_ledger.py \
  tests/guards/test_stdlib_compat.py tests/guards/test_truth_frozen.py \
  tests/gui/test_layering_behavior.py tests/gui/test_main_window.py \
  tests/unit/test_csv_import.py tests/unit/test_engine_m3.py \
  tests/unit/test_formulas.py tests/unit/test_params_gate.py \
  -q -p no:cacheprovider
# → 1 failed, 270 passed in 9.13s
```

**那 1 个 failed 是来源仓自身的漂移，不是本次迁移引入**：
`tests/guards/test_repo_gates.py::test_readme_test_count_matches_collection` 断言
「README 写 329 项，实测收集 336 项（差 +7）」。X 取**实跑 passed 270**（不取 271，
也不采信 queue 里的静态 22 文件）。

### 6.1 D1 + D18 选文件与逐文件处置（16 文件 / 270 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `tests/unit/test_csv_import.py` | 40 | 进货单三态 | **已迁**（§2.1 / §5 测试 45 条） |
| `tests/unit/test_formulas.py` | 27 | F1–F5 与量化 | **已迁**（§2.2 测试 40 条） |
| `tests/unit/test_engine_m3.py` | 25 | 成本卡 / 定价 / 预警 | **已迁**（§2.3–§2.4 测试 60 条） |
| `tests/unit/test_params_gate.py` | 24 | 参数门控三态 | **已迁**（§2.3 测试 20 条） |
| `tests/guards/test_pack_gate.py` | 22 | 参数包结构/三态/来源 | **部分迁**：结构、三态、来源校验已迁；生成器与冻结产物门不迁 |
| `tests/guards/test_repo_gates.py` | 19（+1 failed） | 仓库文档/布局门 | 不迁（仓库纪律；failed 项见上） |
| `tests/guards/test_gates.py` | 17 | 端到端门禁矩阵 | **部分迁**：门控三态语义已迁；CLI/GUI/打包矩阵不迁 |
| `tests/guards/test_truth_frozen.py` | 14 | 来源仓真值冻结门 | 不迁（生成器门）；真值库以**只读拷贝 + 41 用例活跃对账**承接 |
| `tests/guards/test_snapshot_ledger.py` | 11 | 快照台账 / sha256 | **部分迁**：两期区分与分类已迁；台账与字节核验不迁（输入层） |
| `tests/guards/test_import_dispatch.py` | 8 | 单一分派点 | **已迁其精神**：`judge_rows` 是 `check`/成本卡唯一的分派点 |
| `tests/guards/test_stdlib_compat.py` | 7 | Python 版本兼容 | 不迁（本产品底线 3.8，由仓库 CI 矩阵与 AST 门承担） |
| `tests/gui/test_main_window.py` | 7 | 桌面界面 | 不迁（GUI 属交付面） |
| `tests/guards/test_formula_single_source.py` | 6 | 公式单一定义点 | **已迁其精神**：`engine` 是唯一实现处 + §一 AST 门（无 IO/时钟/打印） |
| `tests/guards/test_eol_gate.py` | 4 | 行尾守卫 | 不迁（仓库纪律；`.gitattributes` 与本仓 CI 门承担） |
| `tests/gui/test_layering_behavior.py` | 3 | 编排层零判定 | **已迁其精神**：本器官无表现层，判定只在 `engine` |
| `tests/benchmark/test_runner.py` | 36 | 基准 runner | 不迁（产品级基准编排）；其**对账语义**由 `tests/test_cost_card_extra.py` 的 41 例活跃对账承接 |
| **合计** | **270** | — | 已迁 4 文件 / 部分迁 5 / 不迁 7 |

D1 + D18 剔除（不计入 X，4 文件）：

| 文件 | 命中词 | 处置 |
|---|---|---|
| `tests/integration/test_cli.py` | `cli` | CLI 参数面（器官无 CLI） |
| `tests/guards/test_install_smoke.py` | `smoke` | 装真 wheel 的装态门（本仓判据 4 与 CI 接管） |
| `tests/guards/test_release_tooling.py` | `release` | 发布工具链 |
| `tests/guards/test_audit.py` | `audit` | 脱敏审计（本仓 `tools/audit_repo.py` + CI 接管） |

> **D1 是按文件名机械选**：`tests/gui/test_main_window.py`、`tests/benchmark/test_runner.py`
> 的文件名不含 `gui`/`bench`，故仍计入 X；器官**不复刻**这些产品级路径，判据 1 用
> 336 条判定用例满足 `≥270`。未改 D1、未删来源仓文件。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/params.json` | 来源仓 `src/rcc/data/rules/params.json` | **逐字节相同**（sha256 `4d7c4c55…8db9c`），wheel 进包 |
| `data/clauses.json` | 本器官 `registry.clause_specs()` | 14 条锚点（3 章节 + 10 净料率 + 进货单列名契约），版本 `2026-10-14` |
| `samples/cost-card/ledger-demo.json` | 来源仓 `purchases-demo.csv` + `bom-demo.json` | 判据 2 的新侧样例（rc 1） |
| `samples/cost-card/ledger-clean.json` | 同形态、无异常行 | rc 0 样例 |
| `samples/cost-card/ledger-demo-alert.json` | 追加两期快照（数据日 2026-08-06 / 2026-10-06） | 预警样例 |
| `samples/cost-card/snapshots.json` | 来源仓三份快照 + `.meta.json` 的只读转写 | 仅测试用，不进 wheel |
| `samples/cost-card/truth-*.json` | 来源仓 `src/rcc/data/truth/{import,costcard,alert}.json` | 只读拷贝（输入 + 期望），41 用例活跃对账 |