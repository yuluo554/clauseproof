# 器官 `labor-entitlement`

> 条文判定器官 · 版本 `2026-10-13` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：8 份「地区 × 年度」参数包 + 全国法定常数包（`data/*.json`，与来源仓**逐字节同 sha256**）
> + 法条条款库（17 条）+ 5 条数据契约；条文库 22 条
> 条文库坐标 = 参数包核对日期 `2026-10-13`

一句话：**给一份雇佣/解除事实 + 地区×年度坐标，算经济补偿/赔偿金、加班费、
未休年休假折算、未签书面劳动合同二倍工资，逐项挂法条锚点；未核对参数拒绝进入
计算路径。**

## 1. 输入

```bash
clauseproof check labor-entitlement \
  --input samples/labor-entitlement/case-readme.json \
  --basis src/clauseproof/packs/labor-entitlement/data/clauses.json
clauseproof check labor-entitlement \
  --input samples/labor-entitlement/case-pending.json \
  --basis src/clauseproof/packs/labor-entitlement/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `employment` | ✅ | 雇佣事实：`region_code` / `year` / `hire_date` / `terminate_date` / `monthly_wages` / `work_system` / `cumulative_service_years` / `contract_signed` / `contract_signed_date` / `overtime` / `annual_leave_taken_days` |
| `termination` | — | 解除事实：`ground`（8 种情形）/ `notified_30d_in_advance`；缺省时跳过经济补偿模块（显式记 NA） |
| `modules` | — | 计算模块子集（`severance` / `overtime` / `annual_leave` / `double_wage`）；缺省全跑；未知模块 → 退出码 2 |
| `preview` | — | 预览模式：**只在门控命中（有 pending）时生效**，仅出参数元信息、不输出金额；已核对坐标带 `preview` 照常计算 |

```json
{
  "case_id": "sample-001",
  "employment": {
    "region_code": "310000", "year": 2026,
    "hire_date": "2020-03-01", "terminate_date": "2026-06-30",
    "monthly_wages": ["12000.00", "12500.00", "…"],
    "work_system": "standard", "cumulative_service_years": "6.5",
    "contract_signed": true, "annual_leave_taken_days": "2",
    "overtime": [{"date": "2026-05-01", "hours": "8"}]
  },
  "termination": {"ground": "mutual_agreement", "notified_30d_in_advance": null}
}
```

> **数据读取只在装配面**：随包冻结的参数包由 :mod:`registry` 固定目录读入（与
> ``Basis.from_json`` 同形态的装配），判定内核只收内存对象。来源的
> `--data-dir` / `LCC_DATA_DIR` / PyInstaller `_MEIPASS` / 向上回溯链**全部留输入层**
> ——器官零环境变量、零 cwd、零时钟，同一输入在任何机器上逐字节可复现。

### 1.1 与 `income-tax`（#10）的边界

| 维度 | `labor-entitlement`（本器官） | `income-tax`（#10） |
|---|---|---|
| 对象 | **劳动关系**解除/加班/年休假/书面合同的**用人单位给付义务** | **个人所得税**的预扣/汇算/专项附加扣除/年终奖 |
| 参数 | **地区×年度**：社平工资、最低工资、节假日日历（宪法定常数包） | **年度**：个税税率表、减除费用、专项附加标准（8 册规则包） |
| 社保 | 不做（社保代扣属个税/社保联动口径） | 社保公积金联动（用户输入基数与费率） |
| 依据 | 劳动合同法 / 劳动法 / 年休假条例 / 实施办法 | 个人所得税法及实施条例 / 财税公告 |

两者 **slug / 规则代码（`labor.*` vs `tax.*`）/ 测试文件零复用**；参数包与条文库
各随各包，无共享文件。

## 2. 规则

### 2.1 status 门控（先于一切计算）

`verified` 条目才可进入计算路径；任一 `pending` → `GateError` → 退出码 2
（与来源「门控拦截 = 2」一致）。预览模式（`preview=true`）只在确有 pending 时放宽：
只展示参数元信息，**不输出任何金额**；已核对坐标不被放宽（否则等于借预览绕过门控）。

### 2.2 经济补偿 / 赔偿金（`severance`）

- 口径：解除情形 → N / N+1 / 2N / none；第 40 条**未提前 30 日通知** → N+1（代通知金，
  不是 2N）；第 39 条 → none；第 38 条 → N；
- 年限取整：完整月数 + 余日（≥15 天计半个月）；满阈值个月不满 1 年按 1 年，
  否则按半个月；
- 月工资：解除前 `avg_wage_months` 个月平均应得工资；低于最低工资时取下限；
- 三倍封顶：月工资 **严格大于** 社平 × 倍数才封顶，且年限 ≤ 上限；
- 金额：N = 基数 × 年限；N+1 = N + 上一个月工资（不受封顶/下限约束）；
  2N = 基数 × 年限 × 赔偿金倍数。

### 2.3 加班费（`overtime`）

小时工资 = 月平均工资（低于最低工资取下限）÷（月计薪天数 × 日标准工时）；
日期类型由**该年度该地区**日历单点判定（法定节假日 / 休息日 / 调休上班日 / 工作日）；
三档倍率全部取自常数包；显式 `kind != auto` 覆盖日历判定。

### 2.4 未休年休假（`annual_leave`）

应休天数按累计工作年限分档；当年度折算 = 已过日历天数（含终止当日）÷ 年天数 × 应休；
未休天数 = floor(折算应休 − 已安排)，下限 0；另付金额 = 日工资 × 未休天数 ×
（未休倍数 − 已付比例）。

### 2.5 二倍工资（`double_wage`）

起算 = 用工满 `start_after_months` 个月的**次日**；上限 = 用工满
`start_after_months + max_months` 个月之日；差额 = 月平均工资 × 区间月数 ×
差额倍数（已付一倍，另付差额）；已签书面合同 → 差额 0。

### 2.6 参数坐标与数据纪律

- 坐标精确匹配（地区码 + 年度），文件名与内部坐标必须一致，跨地区/跨年度混用
  在机制上拒绝；
- `verified` 条目必须挂齐来源字段（规则包：publisher / published_year / url /
  retrieved_at；常数包与条款库：basis + source.channel）；
- 全部法定数值只来自数据包，引擎代码零政策数值字面量（来源工具面的扫描门不迁，
  纪律保留）。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | 依据锚点 |
|---|---|---|---|
| 模块计算完成（有金额） | `pass` | 否 | 该模块法条条款（经济补偿按口径：LCL-47 / LCL-40 / LCL-87；none → 口径契约） |
| 模块因缺事实跳过 | `not_applicable` | 否 | `contract.module`（显式跳过，不硬判） |
| 预览模式（pending，不出金额） | `not_applicable` | 否 | `contract.gate` |
| status 门控拦截（非预览） | `ValueError` → 退出码 2 | — | — |

**本器官不产出 `fail`**：它计算用人单位应给付金额，不判违法；阻断只来自输入/
参数不可用（退出码 2）与条文库契约违约（退出码 3）。金额与计算过程全部进
`evidence`（`amount` / `steps` / `basis_ids`），可逐项复核。

**输入不可用**（缺 employment / 地区年度无参数包 / 门控 pending / 日期或金额非法 /
未知模块 / 未知顶层字段）→ `ValueError` → 退出码 2；条文库版本不符 →
`ContractError` → 退出码 3；条款缺失 → `BasisMissing`（本产品内核映射 2）。

### 3.2 人读（`case-readme.json`，退出码 0）

```text
clauseproof :: labor-entitlement 2026-10-13 :: case-readme.json
[pass] labor.annual_leave — 未休年休假折算：应休 5 天，未休 0 天，另付 0.00 元 :: 职工带薪年休假条例 / 第三条 (2026-10-13)
[pass] labor.double_wage — 未签书面劳动合同二倍工资：0 个月，差额 0.00 元 :: 中华人民共和国劳动合同法 / 第八十二条 (2026-10-13)
[pass] labor.overtime — 加班费：2 条加班明细，合计 2096.26 元（小时工资基数 69.87547892720306513409961684） :: 中华人民共和国劳动法 / 第四十四条 (2026-10-13)
[pass] labor.severance — 经济补偿/赔偿金：口径 N，工作年限 6.5 年，金额 79029.17 元 :: 中华人民共和国劳动合同法 / 第四十七条 (2026-10-13)
合计 4 条，阻断 0 条（pass=4 fail=0 na=0）
```

与来源 `lcc calc examples/sample-case.json` 的四模块金额**逐值一致**：
79029.17 / 2096.26 / 0.00 / 0.00。

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 计算完成（含预览 NA；本器官无 fail） |
| `1` | 本器官不产出（保留给产品级阻断） |
| `2` | 输入不合法（缺字段 / 坐标无包 / 门控 pending / 日期金额非法 / 未知模块） |
| `3` | 契约违约（条文库版本 ≠ `2026-10-13`；条文库自相矛盾） |

> **漏 `--basis`** → 条文库版本为空 → 版本不符 → **退出码 3**，是契约正确行为。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 四引擎（severance / overtime / annual_leave / double_wage） | ✅ | 公式/取整/封顶/分档/起算/上限逐条迁移 |
| status 门控 + EffectiveRuleset | ✅ | 单点门控；引擎只接受门控产物 |
| 参数包 / 常数包 / 地区主数据 / 条款库 | ✅ | `data/*.json` **逐字节同 sha256** 随包 + 漂移门 |
| 输入模型与 Decimal 口径 | ✅ | `model` / `decimalutil`（浮点零进入计算路径） |
| 编排层（唯一编排源） | ✅ | `pipeline`（模块默认集合、预览语义、逐模块结果） |
| CLI / GUI（PySide6）/ 报告导出（Markdown/XLSX） | ❌ | 交付面；入口只有 `list` / `check` |
| PyInstaller 打包 / Release 资产 / 版本元数据 | ❌ | 交付面 |
| 数据目录定位（env / `_MEIPASS` / 上溯） | ❌ | 输入层；器官固定随包目录 |
| 真值库（406 条）+ 生成器 + 基准 runner | ❌ | 产品级工具面；真值单一实现源不迁 |
| `params` / `doctor` / `calc` / `report` 子命令 | ❌ | 产品级命令面（新入口只有 `list` / `check`） |

## 5. 口径差（如实登记）

1. **数据目录定位收敛**：来源按「显式 → 环境变量 → PyInstaller → 上溯」五级定位；
   器官固定随包 `data/`（不读环境、不读 cwd）。同一输入在任何机器可复现。
2. **入口从 `calc` 变 `check`**：模块选择从 `--modules` 旗标变成 `subject.modules`；
   默认集合仍由 `pipeline.MODULES` 单点定义。
3. **账本化输出**：来源 stdout 打印金额/依据/免责声明；器官输出判定账本行（每模块
   一条 `pass`，金额、过程、依据 id 全部进 `evidence`），报告排版留产品层。
4. **预览语义**：来源 `--preview` 在门控命中时 rc 1（降级完成）；器官在 pending +
   `preview=true` 时出 4 条 NA、rc **0**（不输出金额即无阻断），已核对坐标不被放宽。
   该路径不是判据 2 的主样例；差异如实登记，不加兼容 rc。
5. **本器官不产出 `fail`**：来源把「计算成功」与「降级」用 0/1 表达；器官按账本语义
   只把输入/契约问题映射 2/3。金额结论本身不是合规违规。
6. **条款以「法律名 + 条号 + 要点」入条文库**：来源只存要点摘述（不转载全文），
   器官条文库 `text` 同样是「标题 + 要点」，锚点路径 = 法律名 / 条号。
7. **数据快照日期 = 2026-10-13**：全部 verified 条目 `retrieved_at` 为该日；
   条文库版本取此日期。
8. **与 #10 `income-tax` 零复用**：对象/参数/依据/社保边界全不同（§1.1）；
   slug、规则代码、测试文件均不复用。
9. **真值库/基准不迁**：来源 406 条真值 + splitmix64 生成器 + 基准 runner 属产品级
   工具面；其判定覆盖由本器官 158 条用例接管（判据 1/3 已过）。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 156**（10 文件）/ 新器官实跑 **N = 158** | **过**（158 ≥ 156） |
| 2 | README 示例命令 rc 相同 | 旧 `py -m lcc calc examples/sample-case.json` rc **0**（79029.17 / 2096.26 / 0.00 / 0.00）/ 新 `check labor-entitlement --input samples/labor-entitlement/case-readme.json --basis …` rc **0**（同四值） | **过**（0 = 0，逐值一致；pending 负控旧 **2** / 新 **2**；漏 basis 新 **3** 契约正确） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 158 ≥ 156；AST `test_` 函数 **144** ≥ 旧层 **140**；文件数旧 10 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（**218 条目 / 696006 B**）；`labor-entitlement/data/` **13 件 / 63407 B**；解包 `list` = **15 器官**、示例 rc **0** | **过** |

**判据 1 的命令与输出原文**（来源仓只读，`PYTHONDONTWRITEBYTECODE=1`）：

```bash
cd <来源仓>/code
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_data_paths.py tests/test_engine_m3.py tests/test_engine_severance.py \
  tests/test_gate.py tests/test_law.py tests/test_model.py tests/test_params.py \
  tests/test_pipeline_orchestration.py tests/test_repo_gates.py \
  tests/test_truth_library.py \
  -o addopts="" -q -p no:cacheprovider
# → 156 passed in 7.68s
```

逐文件 passed：data_paths 6 / engine_m3 21 / engine_severance 37 / gate 7 / law 7 /
model 15 / params 14 / pipeline_orchestration 10 / repo_gates 22 / truth_library 17 = **156**；
旧层 AST `test_` 函数 = 6+21+23+7+7+15+14+8+22+17 = **140**。

> **D1 机械口径说明**：`test_data_paths.py`（6）、`test_repo_gates.py`（22）、
> `test_truth_library.py`（17）的名字**不含** D1/D18 排除词（`paths` / `gates` /
> `library` 均不在词表），故**机械计入分母**，不按域手剔（#10 审计 §3.1 的纠正口径）。
> 其判定值由 §6.1 逐文件处置。`conftest.py` 非测试文件，不计。

### 6.1 D1 + D18 选文件与逐文件处置（10 文件 / 156 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `test_engine_severance.py` | 37 | 经济补偿/赔偿金引擎 | **已迁**（§2.2；测试 §六） |
| `test_repo_gates.py` | 22 | 仓库门（零政策字面量 / AST 分层） | **部分迁**：零政策数值纪律保留（参数全在 data/）；仓库结构/AST 分层门属产品级，不迁。D1 机械计入 X |
| `test_engine_m3.py` | 21 | 加班费/年休假/二倍工资 | **已迁**（§2.3–§2.5；测试 §七–§九） |
| `test_truth_library.py` | 17 | 406 条真值再生成/对账 | **不迁**（生成器/真值库属产品级工具面；判定覆盖由本器官引擎用例接管）。D1 机械计入 X |
| `test_model.py` | 15 | 输入模型 + Decimal 口径 | **已迁**（§二） |
| `test_params.py` | 14 | 坐标/schema/来源纪律 | **已迁**（§三；合成参数包在 tmp_path 注入） |
| `test_pipeline_orchestration.py` | 10 | 编排单点/模块默认/确定性 | **部分迁**：模块默认集合、逐模块金额一致、确定性已迁（§十）；CLI/GUI 前端不迁 |
| `test_gate.py` | 7 | status 门控 | **已迁**（§四） |
| `test_law.py` | 7 | 条款库与依据联动 | **已迁**（§五） |
| `test_data_paths.py` | 6 | 数据目录定位五级链 | **不迁**（输入层；器官固定随包目录，定位链不迁）。D1 机械计入 X |
| **合计** | **156** | — | 已迁 6 / 部分迁 2 / 不迁 2 |

**D1 + D18 剔除（不计入 X，5 文件 / 73 passed）**：

| 来源测试文件 | passed | D1 词 | 去向 |
|---|---:|---|---|
| `test_bench.py` | 19 | `bench` | 内置基准 runner（产品级基准面） |
| `test_cli_exit_codes.py` | 19 | `cli` | 旧 CLI 四子命令与退出码（新入口只有 `list`/`check`） |
| `test_gui_layer.py` | 18 | `gui` | PySide6 界面与 AST 分层门（交付面） |
| `test_packaging.py` | 9 | `packaging` | PyInstaller 双 exe 打包（交付面） |
| `test_release_assets.py` | 8 | `release` | Release 资产/确定性打包（发布面） |

### 6.2 判据 2 对撞（旧命令 vs 新入口）

| 场景 | 旧命令 → rc | 新命令 → rc | 结论 |
|---|---|---|---|
| README 示例（上海 2026，协商一致解除） | `py -m lcc calc examples/sample-case.json` → **0**（79029.17 / 2096.26 / 0.00 / 0.00） | `check labor-entitlement --input samples/labor-entitlement/case-readme.json --basis …/clauses.json` → **0**（同四值） | **过**（0 = 0，逐值一致） |
| 门控负控（广东 440000 pending） | 同输入改 `region_code=440000` → **2**（3 个 pending 条目） | `check … --input samples/labor-entitlement/case-pending.json` → **2**（同 3 条） | **过**（2 = 2） |
| 漏 `--basis` | 旧无概念 | `check labor-entitlement --input …` → **3** | 契约正确行为（条文库版本不符） |
| 缺 employment | 旧输入校验 → 2 | subject 删 `employment` → **2** | 过 |

> 旧侧输入副本在 `%TEMP%`，来源仓全程 `git status --porcelain` = 0 行。

### 6.3 判据 4 的进包清单（`%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation`）

wheel：`clauseproof-0.0.0-py3-none-any.whl`（696006 B，**218 条目**）；
`clauseproof/packs/labor-entitlement/data/` **13 件 / 63407 B**：

| 文件 | bytes | 来源 |
|---|---:|---|
| `clauses.json` | 11817 | 17 条法条 + 5 条数据契约（由随包条款库生成） |
| `constants.json` | 13204 | 来源 `data/constants/`，**逐字节相同** |
| `law-clauses.json` | 13770 | 来源 `data/law/clauses.json`，**逐字节相同** |
| `regions.json` | 2602 | 来源 `data/regions/regions.json`，**逐字节相同** |
| `ruleset-110000-2025.json` | 3763 | 来源 `data/rules/`，**逐字节相同** |
| `ruleset-110000-2026.json` | 3866 | 同上 |
| `ruleset-310000-2025.json` | 3002 | 同上 |
| `ruleset-310000-2026.json` | 3159 | 同上 |
| `ruleset-320000-2025.json` | 1604 | 同上（pending 骨架） |
| `ruleset-320000-2026.json` | 1604 | 同上（pending 骨架） |
| `ruleset-440000-2025.json` | 1604 | 同上（pending 骨架） |
| `ruleset-440000-2026.json` | 1604 | 同上（pending 骨架） |
| `manifest.json` | 1808 | 逐文件 sha256 / bytes / 条文数登记 |

解包后 `clauseproof list` = **15 器官**；示例 rc **0**（4 条 pass）。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/ruleset-*.json`（8） | 来源仓 `data/rules/` | **逐字节相同**（manifest 登记 sha256） |
| `data/constants.json` | 来源仓 `data/constants/` | **逐字节相同** |
| `data/regions.json` | 来源仓 `data/regions/` | **逐字节相同** |
| `data/law-clauses.json` | 来源仓 `data/law/clauses.json` | **逐字节相同**（17 条 verified） |
| `data/clauses.json` | 17 条法条 + 5 条数据契约 | 版本 `2026-10-13` |
| `data/manifest.json` | 本器官装配产物 | 漂移门：bytes + sha256 + clause_count |
| `samples/labor-entitlement/case-readme.json` | 来源 README 示例输入（上海 2026） | 判据 2 主样例（rc 0） |
| `samples/labor-entitlement/case-pending.json` | 同输入改广东 440000（pending） | 门控负控（rc 2） |

> 样例为演示数据，不含真实主体。