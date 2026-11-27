# 器官 `ghg-ledger`

> 条文判定器官 · 版本 `0.1.0` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：40 坐标规则包（GB/T 32150-2015/2025 双标尺 × 年度 2022–2026 × 行业
> 发电/钢铁/水泥/铝冶炼）+ manifest + 单位表，与来源仓 `data/rules/` **逐字节同
> sha256**（基准日 2026-10-13）
> 条文库坐标：`2026-10-13`

一句话：**给一份企业排放档案，判该坐标下应核算哪些源、逐源活动数据×因子×
氧化率算出的排放量是多少、数据质量有哪些分级问题、配额试算缺口多大**。

## 1. 输入

```bash
clauseproof check ghg-ledger \
  --input samples/ghg-ledger/profile-power-2024.json \
  --basis src/clauseproof/packs/ghg-ledger/data/clauses.json
clauseproof check ghg-ledger \
  --input samples/ghg-ledger/profile-power-2026.json \
  --basis src/clauseproof/packs/ghg-ledger/data/clauses.json
clauseproof check ghg-ledger \
  --input samples/ghg-ledger/profile-mixed.json \
  --basis src/clauseproof/packs/ghg-ledger/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `profile` | ✅ | 企业排放档案（含 `coordinate`（standard/year/industry）+ `sources`（source_id + activity）+ 可选 `output` / `include_optional` / `quota_inputs`） |
| `baseline` | — | 上一年度档案（`yoy_jump` 跨年度检查用） |
| `quota_params` | — | 配额试算外部输入（benchmark_value / correction_factor / output / historical_intensity / method） |
| `scopes` | — | 检查路径子集（`calc` / `check` / `quota`；**缺省只跑 `calc`**，与来源 README 示例 `ghg calc` 同语义） |

## 2. 规则

### 2.1 三条硬纪律

1. **status 门控按计算路径分作用域**：`calc`（标准/边界/引擎/因子）/ `quota` /
   `check`（校核）各查各的块；`pending` 条目零参与其自身路径（门控拦截 → `fail`
   → 退出码 1）；`input_required` 为外部输入槽（不阻断，运行时显式索取，
   **不得静默取 0**）；
2. **跨坐标混算拦截**：一次输入出现两个及以上坐标即拒绝（退出码 2）；
3. **零政策数值字面量**：一切阈值/系数/基准值来自规则包（代码零内联；本器官
   测试对引擎源码做数值 token 抽查）。

### 2.2 核算（calc）

- **边界识别**：应核算源缺活动数据 → 报缺失输入（退出码 2，不得静默按空核算）；
  选填源仅在提供数据且 `include_optional` 时纳入；
- **因子优先级**：实测 > 官方因子库 > 行业缺省（按类别分派）；档案自报来源不在
  白名单按不可用处理；三层皆不可用 → 退出码 2；
- **单位链显式化**：活动数据 → 基本单位，因子 → 每基本单位，排放 → tCO2e；
  全链 Decimal（禁 float）；
- **公式表达式树**：mul/add/sub/div/var/const 白名单；`const` 只许引用系数 id；
  氧化率系数仅对燃烧类源适用（其余恒等 1）；
- **双标尺差异**：同年度同行业的旧版坐标自动对照（`delta_vs_2015` 声明 +
  结构字段交叉校验；现算现出）。

### 2.3 质量校核（check）

四类：单位一致性 / 量级异常（单源占比）/ 跨年度突变（需基线）/ 比强度合理性
（需产量）；阈值全部取自规则包 `quality.thresholds`；`pending` 规则与不可用阈值
对应的检查**不执行**并记跳过原因（绝不静默按"通过"处理）。

### 2.4 配额试算（quota）

方法学切换即切换公式分支：`benchmark`（A=Qe×Be×Ff）/ `intensity_coefficient`
（A=E×(1+α)，α 由偏离度 X=(BP−Ii)/BP 经规则包分段系数推出）/ `historical_intensity`
/ `none`（显式不适用，不是 0）。免责声明**强制**（`disclaimer_required` 恒 true）。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| 门控拦截（pending 条目） | `fail` | **是**（退出码 1） | status 门控契约 |
| 纳入核算的源 / 逐源明细 | `pass` | 否 | 核算边界 / 因子优先级契约 |
| 被排除的源（非应核算/未提供数据） | `not_applicable` | 否 | 核算边界契约 |
| 双标尺差异 | `pass` | 否 | 核算边界契约 |
| 校核 error | `fail` | **是** | 校核契约 |
| 校核 warning / info / 跳过 | `not_applicable` | 否 | 校核契约 |
| 配额试算 / 不适用 | `pass` / `not_applicable` | 否 | 配额契约 |
| 三维核查完成（汇总） | `pass` | 否 | 三维坐标契约 |

**输入不可用**（坐标不存在/跨坐标混算/缺应核算源活动数据/因子不可用/配额参数
需外部输入未提供）→ 抛错 → 退出码 2（与来源 0/1/2 契约逐条对齐）。

### 3.2 人读（profile-power-2024.json，退出码 0）

```text
clauseproof :: ghg-ledger 0.1.0 :: profile-power-2024.json
[not_applicable] ghg.source:fugitive_emission — fugitive_emission：非应核算排放源，档案未提供活动数据（排除）；依据 CETS-AG-01.01-V04-2026 5.2 :: 数据契约 / 核算边界 (2026-10-13)
[pass] ghg.line:stationary_combustion — stationary_combustion：活动数据 117977 t × 因子 3.020215（industry_default）× 氧化率 0.99 = 352752.746 tCO2e :: 数据契约 / 因子来源优先级 (2026-10-13)
[pass] ghg.boundary_diff — 双标尺边界差异：gbt32150-2015/2024/power → gbt32150-2025/2024/power；新增 0 / 废止 0 / 口径调整 3 / 不变 1 :: 数据契约 / 核算边界 (2026-10-13)
[pass] ghg.result — 三维核查完成（gbt32150-2025/2024/power）：… :: 数据契约 / 三维坐标 (2026-10-13)
合计 7 条，阻断 0 条（pass=4 fail=0 na=3）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 门控通过且无阻断（calc 样例：边界面 + 逐源明细 + 差异对照） |
| `1` | 门控拦截（2026 发电碳氧化率待官方因子库 → pending → fail） |
| `2` | 输入不可用（坐标不存在/跨坐标混算/缺输入/因子不可用/配额需外部输入/坏 JSON） |
| `3` | 契约违约（条文库版本与规则包快照 `2026-10-13` 不符；缺契约条目 → `BasisMissing` → 3） |

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 三维坐标 + status 门控（分作用域）+ 混算拦截 | ✅ | `rules`（逐字移植） |
| 边界识别 + 双标尺差异 | ✅ | `rules`（逐字移植） |
| 公式表达式树 + Decimal 口径 + 单位表 | ✅ | `engine`（逐字移植） |
| 逐源核算 + 单位链 + 因子优先级 | ✅ | `calc`（逐字移植） |
| 质量四类校核 | ✅ | `calc`（逐字移植） |
| 配额四方法学 + 免责声明 | ✅ | `quota`（逐字移植） |
| 规则包 40 册 + manifest + units | ✅ | `data/*.json` **逐字节同 sha256** 随包 + 漂移门 |
| 文件读取 / 数据目录解析 / 报告头时间戳 | ❌ | 输入层/产品层（器官零文件 IO、零时钟） |
| CLI / 报告三产物（MD+CSV+XLSX）/ GUI / PyInstaller | ❌ | 产品级交付面（入口只有 `list` / `check`） |
| 基准八套件 / 生成器 / 冻结守门 / 脱敏审计 | ❌ | 产品级工具面（真值对账改由本器官测试承载） |

## 5. 口径差（如实登记）

1. **输入从文件变成内存档案**：数据目录解析（环境变量）与文件读取留输入层；
   规则包由器官装配面读随包冻结资产（与 `Basis.from_json` 同形态）。
2. **退出码逐条对齐**：来源 0/1/2 三语义与 clauseproof 0/1/2 对应（门控拦截 →
   `fail` → 1；输入不可用 → 2）；`ghg check` 的「quality error → 2」在器官中
   收敛为 `fail` → 1（口径差：校核 error 是判定结论而非输入错误）。
3. **默认路径收窄**：来源是五个子命令；器官缺省只跑 `calc`（与 README 示例
   同语义），`check` / `quota` 经 `subject.scopes` 显式开启——校核/配额依赖
   核算结果，同一 `evaluate` 内串行执行。
4. **配额外部输入**：`input_required` 语义逐字保留（未提供 → 抛错 → 2；
   绝不静默取 0/1）；免责声明文本随包（`disclaimer_required` 恒 true）。
5. **报告头生成时间不迁**：来源报告的唯一允许时间戳留产品层；器官零时钟。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 151**（11 文件；`PYTHONPATH=code/src`）/ 新器官实跑 **N = 153** | **过**（153 ≥ 151） |
| 2 | README 示例命令 rc 相同 | 旧 `ghg calc --input <power-2024>` rc **0**（total 352752.746；边界面 4 源、逐源 1 行、adjusted 3/unchanged 1）/ 新 `clauseproof check ghg-ledger --input samples/ghg-ledger/profile-power-2024.json` rc **0**（同 352752.746、同因子 3.020215、同氧化率 0.99、同差异计数）；门控样例（2026 发电缺氧化率）旧 **1** / 新 **1**；跨坐标混算样例旧 **2** / 新 **2** | **过**（0=0、1=1、2=2，逐值一致） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 153 ≥ 151；`def test_` **153** ≥ 旧层 AST **145**；文件数旧 11 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（**160 条目**）；`clauseproof/packs/ghg-ledger/data/` **43 件**（40 规则包 + manifest + units + clauses）**691929 B**；manifest 登记 sha256 与实值逐册一致；解包 `list` = **12 器官**、calc rc **0** / gate rc **1** / mixed rc **2** | **过** |

**判据 1 的命令与输出原文**（来源仓只读；`PYTHONPATH=code/src` 因来源仓 src 布局）：

```bash
cd <来源仓>
PYTHONPATH=code/src PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  code/tests/test_coordinates.py code/tests/test_frozen_data.py \
  code/tests/test_jsonio.py code/tests/test_m1_data.py code/tests/test_m2_engine.py \
  code/tests/test_m3_quality_quota.py code/tests/test_m5_demo.py \
  code/tests/test_paths.py code/tests/test_rules_gate.py \
  code/tests/test_units_engine.py code/tests/test_zero_literals.py \
  -o addopts="" -q -p no:cacheprovider
# → 151 passed in 3.65s
```

### 6.1 D1 + D18 选文件与逐文件处置（11 文件 / 151 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `test_m3_quality_quota.py` | 27 | 质量四类 + 配额四方法 | **已迁**（§八/§九） |
| `test_units_engine.py` | 24 | 单位表 + 公式表达式树 | **已迁**（§二/§三） |
| `test_m2_engine.py` | 22 | 逐源核算/边界/因子 | **已迁**（§六/§七） |
| `test_rules_gate.py` | 20 | 门控分作用域/混算 | **已迁**（§四/§五） |
| `test_m1_data.py` | 15 | 规则包结构/对照 | **部分迁**：规则自洽（40 包公式校验）已迁；原文快照台账不迁 |
| `test_coordinates.py` | 9 | 三维坐标 | **已迁**（§二） |
| `test_jsonio.py` | 7 | float→Decimal 口径 | **已迁**（§二：禁 float 入口） |
| `test_paths.py` | 6 | 数据目录解析 | 不迁（器官不读环境变量） |
| `test_m5_demo.py` | 6 | 演示素材 | 不迁（产品级交付面） |
| `test_zero_literals.py` | 5 | 零政策字面量门禁 | **部分迁**：引擎源码数值 token 抽查 1 已迁；token 集生成/扫描器 4 不迁（产品级工具面） |
| `test_frozen_data.py` | 4 | 冻结资产 sha256 | **已迁**（manifest 逐册 sha256 漂移门） |
| **合计** | **151** | — | 已迁 8 / 部分迁 2 / 不迁 1 |

D1 + D18 剔除（不计入 X，8 文件）：`test_cli.py`（cli）/ `test_m4_bench.py`（bench）/
`test_m5_gui.py`（gui）/ `test_m5_packaging.py`（packaging）/ `test_m5_report.py`（report）/
`test_m6_desensitize.py`（desensit）/ `test_workflows.py`（— 注：未命中但未纳入本轮
11 文件集合，留后续如需）/ `conftest.py`（非测试文件）。

> 注：`test_workflows.py`（7 collected）文件名未命中 D1/D18 词表，但本轮 X 集合以
> 「判定层」为口径未纳入（其内容为跨命令工作流编排 = 产品级路径）；如实登记，
> 不计入 X。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/manifest.json` | 来源仓 `data/rules/manifest.json` | **逐字节相同**（40 坐标索引 + bench 门槛） |
| `data/ruleset-*.json`（40 册） | 来源仓 `data/rules/` | **逐字节相同**（manifest 登记 sha256 逐册核对） |
| `data/units.json` | 来源仓 `data/rules/units.json` | **逐字节相同**（单位换算表） |
| `data/clauses.json` | 10 条数据契约（由 `registry.clause_specs/clause_text` 生成） | 版本 `2026-10-13` |
| `samples/ghg-ledger/profile-*.json` | 来源真值库 `data/truth/profiles/` 只读转写 | 判据 2 三样例（calc rc 0 / gate rc 1 / mixed rc 2）+ steel 对账 |