# 器官 `safety-fee`

> 条文判定器官 · 版本 `2026-10-14` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：**《企业安全生产费用提取和使用管理办法》**（**财资〔2022〕136号**，2022-11-21 施行，
> 第六十九条废止财企〔2012〕16号）+ **财企〔2012〕16号**（历史年度对照）
> 两份规则包（计提标准 / 支出范围 / 进度门槛）与来源**逐字节同 sha256** 随包
> 条文库 167 条：行业 21 + 变体 50 + 依据选择 2 + 进度门槛 2 + 支出条目 71 + 依据文件 8
> + 数据契约 13；条文库坐标 = 依据基准日 `2026-10-14`

一句话：**给一份企业档案（行业 / 年度 / 计提依据量），按财资〔2022〕136号
（或历史年度锚定的财企〔2012〕16号）判计提依据、算应计提金额（产量 / 超额累退 /
比例，逐段量化），逐笔核查支出范围四态、判使用进度披露义务、给出双版本差异；
结论旁挂条款锚点。**

> **与 #1 `cost-card` 的边界**：`cost-card` 是**菜品成本卡**（净料率 / 目标毛利率 /
> 波动阈值，依据 = 参数包条目）；本器官是**企业安全生产费用的计提与使用**
> （财资〔2022〕136号）。对象、输入、依据、规则**零复用**，slug / 规则 id /
> 条款 id / 测试文件均不共享。

## 1. 输入

```bash
clauseproof check safety-fee \
  --input samples/safety-fee/profile-coal.json \
  --basis src/clauseproof/packs/safety-fee/data/clauses.json
clauseproof check safety-fee \
  --input samples/safety-fee/profile-coal-ledger.json \
  --basis src/clauseproof/packs/safety-fee/data/clauses.json
clauseproof check safety-fee \
  --input samples/safety-fee/profile-coal-progress.json \
  --basis src/clauseproof/packs/safety-fee/data/clauses.json
clauseproof check safety-fee \
  --input samples/safety-fee/profile-compare.json \
  --basis src/clauseproof/packs/safety-fee/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `case_id` | ✅ | 一次判定运行的稳定标识（输入必填字段） |
| `profile` | ✅ | 企业档案：`enterprise_id` / `enterprise_name` / `industry_id` / `year` / `basis_kind` / `basis_value` / `basis_unit`，可选 `variant_id` / `mine_type` / `hazards` / `businesses` / `revenue` / `purchased_cost` / `is_contractor` |
| `ledger` | — | 支出明细数组：`{item_key, subject, summary, amount}`（给了就逐笔核查） |
| `progress` | — | 使用进度：`{used, accrued?, threshold_id?}`；`accrued` 缺省取本次计提金额 |
| `compare` | — | `true`（默认 2020→2024）或 `{from_year, to_year}` 双版本对照 |

```json
{
  "case_id": "safety-fee-coal-ledger",
  "profile": {
    "enterprise_id": "90000000SYN0000001A",
    "enterprise_name": "示例煤炭（合成）有限公司",
    "industry_id": "coal", "year": 2024,
    "basis_kind": "output", "basis_value": "120000", "basis_unit": "ton",
    "variant_id": "coal_high_gas"
  },
  "ledger": [
    {"item_key": "EXP-001", "subject": "安全费用",
     "summary": "煤矿安全改造支出", "amount": "120000.00"}
  ]
}
```

| `basis_kind` | 机制 | 依据量 |
|---|---|---|
| `output` | `by_output` | 产量（吨等） |
| `revenue` | `by_revenue_tiered` / `by_revenue_rate` | 营业收入（元） |
| `project_cost` | `by_project_cost` | 建筑安装工程造价（元） |

`basis_unit` ∈ `CNY` / `CNY10k` / `CNY100m` / `ton`（定义性换算，换算即记 warning）。
未知档案字段 / 缺必填字段 / 依据选择属性缺失 → 退出码 2。

> **数据读取只在装配面**：规则包由 :mod:`pipeline` 从随包目录读入并**逐文件核 sha256**
> （按来源 manifest 登记值）；判定内核只收内存对象。来源的
> `SAFEFEE_DATA_DIR` / 上溯定位 / CSV 读入 / GUI / 报告全部留输入/交付层
> ——器官零环境变量、零文件 IO、零时钟。

### 1.1 与既有器官的边界

| 维度 | `safety-fee`（本器官） | 既有器官 |
|---|---|---|
| 对象 | **安全生产费用**：计提金额、支出范围、使用进度、版本差异 | `cost-card` = 菜品成本；`expense-ledger` = 个人/多平台账单；`invoice-ledger` = 发票 |
| 依据 | 财资〔2022〕136号 + 财企〔2012〕16号（双版本） | 各自法规/标准/参数包 |
| 输入 | 企业档案 + 支出明细 | 各自 subject |

slug / 规则 id（`fee.*`）/ 条款 id 前缀（`fee:*`）/ 测试文件与既有 21 个器官零复用。

## 2. 规则

### 2.1 年度锚定版本（不串口径）

| 年度 | 规则集 | 文号 |
|---|---|---|
| 2012–2022（该年 1 月 1 日 ≤ 2022-11-20） | `财企-2012-16` | 财企〔2012〕16号 |
| 2022-11-21 起 | `财资-2022-136` | 财资〔2022〕136号 |

锚定日 = 该年 **1 月 1 日**；无匹配 → 退出码 2；多匹配 → 配置错误。

### 2.2 四类计提机制

| 机制 | 公式 | 行业例 |
|---|---|---|
| `by_output` | 单价 × 产量 | 煤炭（按矿井灾害类型分 4 档） |
| `by_revenue_tiered` | **超额累退逐段**：Σ 段内依据量 × 段费率 | 危险品、冶金、机械制造、电力 |
| `by_revenue_rate` | 营业收入 × 单一费率 | 交通运输（普通货运 1% / 客运等 1.5%） |
| `by_project_cost` | 工程造价 × 费率 | 建设工程（5 类工程 1.5%–3.5%） |

- **边界口径**：段区间 `[lower, upper)`，**恰好等于分段点归下一段**；
- **逐段量化到分后求和**（不是总额乘单一费率）；
- 标准值**全部读规则包**，引擎零政策数值；金额 `Decimal` + `ROUND_HALF_UP`。

### 2.3 依据选择（第五十二 / 五十三条 + 从高提取）

| 情形 | 判定 |
|---|---|
| 矿井多种灾害并存 | 取 `severity` 最大的变体（**从高提取**），被排除变体留痕 |
| 跨行业经营（第五十二条） | 能分别核算 → 各业务分别计提；不能 → 按营业收入占比最高业务对合计计提 |
| 承揽/承运净额（第五十三条） | 外购材料服务成本 **>** 营业收入 85%（阈值来自规则包）→ 可按净额计提 |
| 档案属性缺失 | `inputs_required` → **必索**（退出码 2），绝不静默取 0/1 |

### 2.4 status 门控（按计算路径分作用域）

| 作用域 | 校验条目 | 门控拦截时 |
|---|---|---|
| `calc` | 计提标准（机制 / 变体 / 分段），可收窄到本次行业 | 账本 `fail` → 退出码 1 |
| `check` | 支出范围条目 | 账本 `fail` → 退出码 1 |
| `progress` | 进度门槛 | 账本 `fail` → 退出码 1 |

`input_required`（本不由规则包承载、须运行时索取）**不阻断门控**，但运行时必索。

**条款 pending 如实登记**：2012 版 `progress.json` 的 status 为 **pending**
（原文结构与 2022 版不同、门槛未落值），条款书架以 `【待核对】` 前缀登记；
对 2012 年度请求使用进度 → progress 作用域门控**如实拦截**（退出码 1），
不静默放行、不套用 2022 门槛。随包其余条目全部 `verified`。

### 2.5 支出范围四态

| 判定 | 何时给 | 账本 |
|---|---|---|
| `符合` | 命中允许条目且无禁止命中 | `pass` |
| `部分符合` | 同时命中允许与禁止，或允许条目含限制条件 | `pass`（非阻断结论） |
| `不符合` | 命中禁止条目（红线） | `fail`（阻断 → 退出码 1） |
| `不适用` | 原文明确写了例外情形且情形成立 | `not_applicable` |
| `未评估` | **无可适用条目** | `not_applicable`（无锚点） |

**未评估不冒充符合**；`不适用` 只保留给原文明确写了例外情形的项。

### 2.6 使用进度

门槛值来自规则包（2022 版第五十一条 **60%**）；当年实际使用不足门槛 →
须按规定披露并于下一年度 4 月底前提交书面说明。**披露义务属非阻断结论**
（与来源 `progress` 命令 rc 0 一致），账本消息明示；`accrued == 0` → 不适用。

### 2.7 复核算锚

规则包 manifest 登记 `review_interval = annual` / `next_review = 2027-10-14`，
每次运行进 `fee.rules` 记录；**器官零时钟**，不做「今天是否逾期」判定
（逾期提醒属产品层）。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | 依据锚点 |
|---|---|---|---|
| 规则包坐标（每次运行一条） | `pass` | 否 | `contract.rules` |
| 门控拦截（`calc` / `check` / `progress`） | `fail` | **是**（退出码 1） | `contract.gate` |
| 依据选择留痕 | `pass` | 否 | 变体条款 / `fee:<v>:basis:<kind>` |
| 计提结果（金额 / 公式 / 分段） | `pass` | 否 | 行业/变体条款 |
| 支出 `符合` / `部分符合` | `pass` | 否 | 支出条目条款 |
| 支出 `不符合`（红线） | `fail` | **是** | 支出条目条款 |
| 支出 `未评估` | `not_applicable` | 否 | 无锚点 |
| 使用进度（须披露 / 不需披露） | `pass` | 否 | 进度条款 |
| 进度不适用（应计提 0） | `not_applicable` | 否 | 进度条款 |
| 双版本差异对照 | `pass` | 否 | `contract.diff` |
| 汇总（有阻断 / 无） | `fail` / `pass` | 是 / 否 | `contract.summary` |

**输入不可用**（缺字段 / 未知字段 / 依据选择属性缺失 / 规则包不可用）→ `ValueError`
→ 退出码 2；条文库版本不符 / 条款缺失 → `ContractError` → 退出码 3。

### 3.2 人读（节选）

```text
clauseproof :: safety-fee 2026-10-14 :: profile-coal.json
[pass] fee.accrual — 应计提 3600000.00 元（煤炭生产）：CNY/ton（30） × 120000 = 3600000.00 元；条款 第七条 :: 财资〔2022〕136号 / 第七条 (2026-10-14)
[pass] fee.rules — 规则包：财资〔2022〕136号（2022：行业 12）；财企〔2012〕16号（2012：行业 9）；复核周期 annual / 下次复核 2027-10-14 :: 数据契约 / 规则包纪律 (2026-10-14)
[pass] fee.summary — 无阻断；应计提 3600000.00 元 :: 数据契约 / 汇总语义 (2026-10-14)
合计 3 条，阻断 0 条（pass=3 fail=0 na=0）

clauseproof :: safety-fee 2026-10-14 :: profile-coal-ledger.json
[fail] fee.spending:EXP-003 — 支出 EXP-003（管理费用）：不符合；条款 第四条；命中禁止性条目（红线） :: 财资〔2022〕136号 / 第四条 (2026-10-14)
[fail] fee.summary — 检出阻断 1 条：fee.spending:EXP-003（应计提 3600000.00 元；支出 不符合=1、符合=3） :: 数据契约 / 汇总语义 (2026-10-14)
合计 7 条，阻断 2 条（pass=5 fail=2 na=0）

clauseproof :: safety-fee 2026-10-14 :: profile-coal-progress.json
[pass] fee.progress — 使用进度 0.40 低于门槛 0.6：须按规定披露并于下一年度 4 月底前提交书面说明（非阻断） :: 财资〔2022〕136号 / 第五十一条 (2026-10-14)
[pass] fee.summary — 无阻断；应计提 3600000.00 元；使用进度 0.40 低于门槛 0.6（须披露） :: 数据契约 / 汇总语义 (2026-10-14)

clauseproof :: safety-fee 2026-10-14 :: profile-compare.json
[pass] fee.diff — 财企〔2012〕16号 → 财资〔2022〕136号 差异 25 条（added=12、rate_changed=4、removed=5、value_changed=4）；已比对行业 9 个 :: 数据契约 / 双版本对照 (2026-10-14)
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无阻断（计提完成；支出无红线；进度披露属非阻断） |
| `1` | 门控拦截或支出红线（与来源 `calc`/`check`/`progress` 的 rc 1 一致） |
| `2` | 输入不合法（缺字段 / 未知行业 / 依据选择属性缺失 / 规则包不可用） |
| `3` | 契约违约（条文库版本不符 / 条款缺失） |

> **漏 `--basis`** → 条文库版本为空 → 版本不符 → **退出码 3**，是契约正确行为。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 四类计提机制 + 超额累退逐段 | ✅ | `accrual.compute` / `tiered` |
| 依据选择（从高 / 跨行业 / 净额） | ✅ | `accrual.decide_basis` |
| 单位换算（定义性 + warning） | ✅ | `units` |
| status 门控（三分作用域 + input_required） | ✅ | `gate` |
| 年度 → 版本锚定 + 文件指纹 | ✅ | `manifest`（按来源 manifest 登记 sha256 核对平铺文件） |
| 支出四态 + 红线 | ✅ | `spending.check_ledger` |
| 使用进度 + 披露要点 | ✅ | `spending.compute_progress` |
| 双版本差异（四类 + 已比对留痕） | ✅ | `diff.compare` |
| 两份规则包（6 文件）+ manifest + units | ✅ | `data/*.json`（**逐字节相同**） |
| 真值库 122 例 + 7 误报对照 | ✅ | `data/truth-cases.json`（仅输入与期望，双重记账） |
| 批量扫描 / 跨年对账 | ❌ | 交付层（台账目录 IO） |
| 报告导出（MD/XLSX/evidence） | ❌ | 交付面 |
| GUI 四页签 / 双 exe | ❌ | 交付面 |
| 内置基准 runner（三类套件） | ❌ | 工具面；真值库改作测试对账 |
| 数据生成器（固定 seed / 再生成逐字节一致） | ❌ | 工具面；产物 sha256 进器官 manifest |
| `calc/check/progress/diff/scan/bench/selfcheck/gui` 子命令 | ❌ | 产品级命令面（新入口只有 `list` / `check`） |

## 5. 口径差（如实登记）

1. **入口收敛**：来源八个命令面 → 器官 `check` 一个入口；`ledger` / `progress` /
   `compare` 由 subject 的可选块触发，一次运行可同时给多块。
2. **门控拦截映射为阻断**：来源 rc **1**；本器官产出 `fail`（`contract.gate` 锚点）
   → 退出码 1，语义与来源一致（不进入计算路径 ≠ 合规）。
3. **退出码对齐**：来源 `0/1/2`（另有 `3` 缺可选依赖）；本器官保持 `0/1/2`，
   新增 `3` = 契约违约（条文库版本/锚点缺失）。主样例 `calc` 0=0、
   支出红线 `check` 1=1、进度披露 0=0、对照 0=0（判据 2 实测）。
4. **使用进度披露不阻断**：来源 `progress` 即便触发披露也返回 0；本器官映射
   `pass` 并在消息里明示「须披露并书面说明（非阻断）」，不冒充无义务。
5. **真值库按 `ruleset_id` 直算**：来源 bench 的口径（用例显式声明规则集）；
   对外入口仍按**年度锚定**（不削弱「锚定年度即锚定版本」）。两者在测试里分别覆盖。
6. **2012 版进度门槛 pending**：来源数据本身 status=pending（结构不同、门槛未落值）；
   本器官如实登记 `【待核对】` 并由 progress 门控拦截（退出码 1），不套用 2022 门槛。
7. **`部分符合` 无自然产出**：来源 checker 只产 `符合 / 不符合 / 未评估`；
   `部分符合` 常量保留（规则包可扩展），账本映射为 `pass`（非阻断结论）。
8. **报告与批量层不迁**：docx/XLSX、evidence 指纹、扫盘/对账、基准 runner
   都属交付/工具面；器官只出账本。
9. **与既有器官零复用**：slug / 规则 id / 条款 id / 测试文件均不复用；
   与 `cost-card` 规则零共享（§1.1）。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 140**（18 文件）/ 新器官实跑 **N = 336** | **过**（336 ≥ 140） |
| 2 | README 示例命令 rc 相同 | 旧 `safefee calc data/samples/archive-coal.json` rc **0**（3,600,000.00 / 第七条）/ 新 `check safety-fee --input …/profile-coal.json --basis …` rc **0**（同金额、同条款）；支出负控旧 `safefee check data/samples/ledger-demo.csv --archive data/samples/archive-coal.json` rc **1** / 新 `…/profile-coal-ledger.json` rc **1**（同 4 笔四态：3 符合 + 1 不符合）；进度旧 `safefee progress … --accrued 100000 --used 40000` rc **0** / 新 `…/profile-coal-progress.json` rc **0**（同为须披露）；对照旧 `safefee diff --from-year 2020 --to-year 2024` rc **0** / 新 `…/profile-compare.json` rc **0**（25 条差异） | **过**（0=0、1=1、0=0、0=0） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 336 ≥ 140；AST `test_` 函数 **209** ≥ 旧层 **139**；文件数旧 18 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation`（暂存树 `git write-tree` 导出，非脏工作树）→ `clauseproof-0.0.0-py3-none-any.whl`（**340 条目**）；`safety-fee/data/` **11 件 / 320779 B**；解包 `list` = **22 器官**、coal rc **0** / ledger rc **1** | **过** |

**判据 1 的命令与输出原文**（来源仓只读，`PYTHONDONTWRITEBYTECODE=1`）：

```bash
cd <来源仓>
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_accrual.py tests/test_basis.py tests/test_ci_workflow.py \
  tests/test_data_paths.py tests/test_dessensitize.py tests/test_diff.py \
  tests/test_frozen_products.py tests/test_gate.py tests/test_manifest.py \
  tests/test_pipeline.py tests/test_policy_literals.py tests/test_readme_runnable.py \
  tests/test_reconcile.py tests/test_scan_real.py tests/test_spending.py \
  tests/test_tiered.py tests/test_truth.py tests/test_units.py \
  -o addopts="" -q -p no:cacheprovider
# → 140 passed in 3.54s
```

逐文件 passed：accrual 7 / basis 11 / ci_workflow 7 / data_paths 8 / dessensitize 7 /
diff 11 / frozen_products 11 / gate 11 / manifest 12 / pipeline 7 /
policy_literals 4 / readme_runnable 4 / reconcile 7 / scan_real 7 / spending 7 /
tiered 9 / truth 5 / units 5 = **140**；旧层 AST `test_` 函数 **139**
（`test_frozen_products` 10 函数 / 11 用例）。

> **D1 + D18 机械口径说明**：`test_dessensitize.py` 的文件名拼写是
> `d-e-s-s-e-n-s-i-t-i-z-e`，**不含**排除词 `desensit`，故**机械计入分母**
> （它本身是产品级脱敏门，处置见 §6.1）；`test_ci_workflow` /
> `test_data_paths` / `test_frozen_products` / `test_readme_runnable` /
> `test_reconcile` / `test_scan_real` / `test_truth` / `test_units`
> 同理机械计入，不按域手剔（与 #10 审计 §3.1 一致）。

### 6.1 D1 + D18 选文件与逐文件处置（18 文件 / 140 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `test_basis.py` | 11 | 依据选择（从高 / 跨行业 / 净额） | **已迁**（§2.3；测试 §六） |
| `test_diff.py` | 11 | 双版本差异 | **已迁**（§2.7；测试 §九） |
| `test_frozen_products.py` | 11 | 冻结产物再生成逐字节一致 | **部分迁**：产物 sha256 进器官 manifest 漂移门；生成器不迁 |
| `test_gate.py` | 11 | 三分作用域门控 | **已迁**（§2.4；测试 §四） |
| `test_manifest.py` | 12 | manifest / 年度锚定 / 指纹 | **已迁**（§2.1；测试 §三） |
| `test_tiered.py` | 9 | 超额累退分段与边界 | **已迁**（§2.2；测试 §一） |
| `test_data_paths.py` | 8 | 数据目录五级定位链 | **部分迁**：随包固定目录 + 装配缓存；env/上溯不迁 |
| `test_accrual.py` | 7 | 四类计提机制 | **已迁**（§2.2；测试 §五） |
| `test_ci_workflow.py` | 7 | CI 工作流门 | **不迁**（产品级 CI） |
| `test_dessensitize.py` | 7 | 脱敏审计 | **不迁**（产品级 `tools/audit_repo.py`）。D1 机械计入 X |
| `test_pipeline.py` | 7 | 编排（calc/check/progress/diff/scan） | **部分迁**：calc/check/progress/diff 迁入；scan/report/gui 不迁 |
| `test_reconcile.py` | 7 | 跨年对账 | **不迁**（批量层）。D1 机械计入 X |
| `test_scan_real.py` | 7 | 批量扫描实跑 | **不迁**（交付层）。D1 机械计入 X |
| `test_spending.py` | 7 | 支出四态 | **已迁**（§2.5；测试 §七） |
| `test_policy_literals.py` | 4 | 引擎零政策数值 | **已迁**：标准值全部读规则包（§2.2） |
| `test_readme_runnable.py` | 4 | README 示例可跑 | **不迁**（产品级文档门）。D1 机械计入 X |
| `test_truth.py` | 5 | 真值库对账 / 双重记账 | **部分迁**：122 + 7 逐例对账迁入（测试 §十三）；bench runner 不迁 |
| `test_units.py` | 5 | 定义性单位换算 | **已迁**（§2.2；测试 §二） |
| **合计** | **140** | — | 已迁 9 / 部分迁 4 / 不迁 5 |

**D1 + D18 剔除（不计入 X，7 文件 / 77 passed）**：

| 来源测试文件 | passed | D1 词 | 去向 |
|---|---:|---|---|
| `test_cli.py` | 16 | `cli` | 旧八子命令与退出码（新入口只有 `list`/`check`） |
| `test_gui_m5.py` | 16 | `gui` | GUI 交付（交付面） |
| `test_gui_layering.py` | 14 | `gui` | GUI 分层纪律（交付面） |
| `test_stdio_guard.py` | 11 | `guard` | 编码护栏（产品级） |
| `test_report.py` | 10 | `report` | 报告渲染（交付面） |
| `test_bench.py` | 8 | `bench` | 内置基准 runner（工具面） |
| `test_docs_guards.py` | 2 | `docs_` | 文档守卫（产品级） |

### 6.2 判据 2 对撞（旧命令 vs 新入口）

| 场景 | 旧命令 → rc | 新命令 → rc | 结论 |
|---|---|---|---|
| README 计提 | `safefee calc data/samples/archive-coal.json` → **0**（3,600,000.00 / 第七条） | `check safety-fee --input …/profile-coal.json --basis …` → **0**（同金额、同条款） | **过**（0=0） |
| README 支出核查（红线） | `safefee check data/samples/ledger-demo.csv --archive data/samples/archive-coal.json` → **1**（3 符合 + 1 不符合 / 第四条） | `…/profile-coal-ledger.json` → **1**（同 4 笔四态） | **过**（1=1） |
| README 使用进度 | `safefee progress data/samples/archive-coal.json --accrued 100000 --used 40000` → **0**（0.40 < 0.60，须披露） | `…/profile-coal-progress.json` → **0**（0.40 < 0.60，须披露，非阻断） | **过**（0=0） |
| README 双版本对照 | `safefee diff --from-year 2020 --to-year 2024` → **0** | `…/profile-compare.json` → **0**（25 条差异） | **过**（0=0） |
| 2012 年进度（pending 门槛） | `safefee progress`（2012 年度档案）→ **1**（门控） | 同档案 `…` → **1**（`fee.gate:progress`） | 过（1=1，条款 pending 如实拦截） |
| 漏 `--basis` | 旧无概念（规则包内建） | `check … --input …` → **3** | 契约正确行为 |

> 旧侧输出/产物重定向到 `%TEMP%`；旧侧输入为来源演示档案（只读）；
> 全程 `git status --porcelain` = 0 行。

### 6.3 判据 4 的进包清单（暂存树导出 → `pip wheel --no-deps --no-build-isolation`）

wheel：`clauseproof-0.0.0-py3-none-any.whl`（**340 条目**）；
`clauseproof/packs/safety-fee/data/` **11 件 / 320779 B**：

| 文件 | bytes | 来源 |
|---|---:|---|
| `rules-manifest.json` | 1591 | 来源 `rules/manifest.json`，**逐字节相同** |
| `units.json` | 148 | 来源 `rules/units.json`，**逐字节相同** |
| `ruleset-2022.json` | 66053 | 来源 2022 版 `ruleset.json`，**逐字节相同** |
| `spending-2022.json` | 31510 | 来源 2022 版 `spending.json`，**逐字节相同** |
| `progress-2022.json` | 1165 | 来源 2022 版 `progress.json`，**逐字节相同** |
| `ruleset-2012.json` | 48531 | 来源 2012 版 `ruleset.json`，**逐字节相同** |
| `spending-2012.json` | 22682 | 来源 2012 版 `spending.json`，**逐字节相同** |
| `progress-2012.json` | 1187 | 来源 2012 版 `progress.json`，**逐字节相同**（status=pending 如实保留） |
| `clauses.json` | 53646 | 由规则包 + 依据文件 + 13 条数据契约装配（167 条） |
| `truth-cases.json` | 91785 | 122 例 + 7 误报对照（仅输入与期望） |
| `manifest.json` | 2481 | 逐文件 sha256 / bytes / 条款与真值计数 |

解包后 `clauseproof list` = **22 器官**；`profile-coal` rc **0**、
`profile-coal-ledger` rc **1**（与 §6.2 一致）。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/ruleset-2022.json` / `spending-2022.json` / `progress-2022.json` | 来源 2022 版规则包 | **逐字节相同**（12 行业 / 41 支出条目 / 60% 门槛） |
| `data/ruleset-2012.json` / `spending-2012.json` / `progress-2012.json` | 来源 2012 版规则包 | **逐字节相同**（9 类 / 30 支出条目 / 进度门槛 pending） |
| `data/rules-manifest.json` / `units.json` | 来源 `rules/` | **逐字节相同**（坐标 + 指纹 + 换算 + 复核锚） |
| `data/clauses.json` | 本器官装配产物 | 167 条（条款要点为工具整理，来源知识库只存文件级核对记录，不转载全文） |
| `data/truth-cases.json` | 来源真值库 122 例 + 7 对照 | 仅输入与期望（金额由来源生成器独立计算路径产出） |
| `data/manifest.json` | 本器官装配产物 | 漂移门：bytes + sha256 + 条款/真值计数 |
| `samples/safety-fee/profile-coal.json` | 来源演示档案 | 判据 2 主样例（rc 0，3,600,000.00） |
| `samples/safety-fee/profile-coal-ledger.json` | 来源演示档案 + 台账 | 支出红线（rc 1，EXP-003 第四条） |
| `samples/safety-fee/profile-coal-progress.json` | 来源演示档案 + 进度 | 须披露（rc 0，0.40 < 0.60） |
| `samples/safety-fee/profile-compare.json` | 来源演示档案 + 对照 | 双版本 25 条差异（rc 0） |
| `samples/safety-fee/profile-hazardous.json` / `profile-construction.json` | 来源演示档案 | 超额累退 / 工程造价（rc 0） |

> 样例全部为合成数据（虚构企业、测试号段 `90000000…SYN`），不含真实企业产能、
> 营业收入或台账数据。