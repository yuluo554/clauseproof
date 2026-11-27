# 器官 `patent-annuity`

> 条文判定器官 · 版本 `2026-10-14` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：国家知识产权局**现行专利收费标准表**（`fee_schedule@v2024`）+《专利收费减缴办法》
> 财税〔2016〕78 号 + 公告第 316 号 + 公告第 594 号（4 份规则包**逐字节同 sha256** 随包）
> 条文库 41 条：32 条规则条目锚点 + 5 条专利法实施细则条款 + 4 条数据契约
> 条文库坐标 = 规则包核对日期 `2026-10-14`

一句话：**给专利类型 + 缴费年度 + 时间事实/主体收入，算年费阶梯金额、滞纳金、
费减资格与减免额、组合排期；逐项挂政策条款坐标；未核对条目拒绝进入计算路径。**

## 1. 输入

```bash
clauseproof check patent-annuity \
  --input samples/patent-annuity/annuity.json \
  --basis src/clauseproof/packs/patent-annuity/data/clauses.json
clauseproof check patent-annuity \
  --input samples/patent-annuity/late.json \
  --basis src/clauseproof/packs/patent-annuity/data/clauses.json
clauseproof check patent-annuity \
  --input samples/patent-annuity/reduction.json \
  --basis src/clauseproof/packs/patent-annuity/data/clauses.json
clauseproof check patent-annuity \
  --input samples/patent-annuity/portfolio.json \
  --basis src/clauseproof/packs/patent-annuity/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `case_id` | ✅ | 一次判定运行的稳定标识（输入必填字段） |
| `patent` | — | 年费：`patent_type`（invention / utility_model / design / design_intl）+ `year`（第 N 年） |
| `late` | — | 滞纳金：`patent_type` / `year` / `due_on` / `paid_on`（ISO 日期） |
| `reduction` | — | 费减：`patent_type` / `year` / `as_of_year` / `applicants[]` / `open_license` |
| `portfolio` | — | 组合排期：`today`（显式基准日，器官零时钟）/ `window_months` / `items[]` |

`patent` / `late` / `reduction` / `portfolio` **至少给一个**；未知顶层字段 → 退出码 2。

```json
{
  "case_id": "full-demo",
  "patent": {"patent_no": "990000000001SYN", "patent_type": "invention", "year": 5},
  "late": {"patent_type": "invention", "year": 5,
           "due_on": "2020-05-04", "paid_on": "2020-07-04"},
  "reduction": {"patent_type": "invention", "year": 5, "as_of_year": 2026,
                "applicants": [{"kind": "individual", "monthly_avg_income": "4999.99"}]},
  "portfolio": {"today": "2026-10-14", "window_months": 3, "items": []}
}
```

> **数据读取只在装配面**：4 份规则包由 :mod:`registry` 固定目录读入，金额用
> ``parse_float=Decimal``；判定内核只收内存对象。来源的 `--data-dir` / 环境变量 /
> PyInstaller `_MEIPASS` / 上溯链**全部留输入层**——器官零环境变量、零 cwd、零时钟
> （组合排期的 `today` 必须显式提供）。

### 1.1 与既有器官的边界

| 维度 | `patent-annuity`（本器官） | 既有器官 |
|---|---|---|
| 对象 | **专利年费 / 滞纳金 / 费减 / 组合排期** | 个税（`income-tax`）/ 劳动给付（`labor-entitlement`）/ 发票（`invoice-ledger`）等 |
| 依据 | 国家知识产权局费率表 + 财税〔2016〕78 号 + 公告 316/594 | 各自法规/标准/参数包 |
| 金额口径 | 专利类型 × 年度阶梯（1-3 / 4-6 / …） | 各自规则表 |

slug / 规则代码（`patent.*`）/ 测试文件与既有 15 个器官零复用。

## 2. 规则

### 2.1 status 门控（按作用域）

| 作用域 | 引用条目 |
|---|---|
| `calc` | `annuity.<type>` 阶梯 |
| `late` | `late.monthly_rate` / `late.grace_months` / `late.month_basis` |
| `reduction` | 316 阈值 + 78 比例 + 594 开放许可/不重复享受 |
| `check` | 关联费用条目（恢复权利请求费 / 评价报告请求费） |

`verified` 才可进入计算路径；`pending` 拒绝（`--preview` 可预览但不得作为缴费依据）；
`input_required` 放行但必须显式提供。**真实 32 条规则全部 verified**（2026-10-24 复核）。

### 2.2 年费阶梯（`annuity.*`）

- 阶梯区间**双闭** `[from_year, to_year]`，恰好跳档年归新档（第 3 年 → 第 1 档；
  第 4 年 → 第 2 档）；
- 发明专利 1-3/900、4-6/1200、7-9/2000、10-12/4000、13-15/6000、16-20/8000；
  实用新型与外观设计各有独立阶梯（全部来自规则包，代码零政策数值）；
- 超出覆盖范围 → `out_of_range`（未判定，不作为 0）。

### 2.3 滞纳金（`late.*`）

- 月数口径 = `calendar_month`（自然月推进，月末夹取；不足整月不计）；
- 滞纳金 = 当年全额年费 × `late.monthly_rate`（5%）× 逾期月数；
- 补缴上限 = `late.grace_months`（6 个月）；**超上限照算金额并附风险提示**
  （warning ≠ 法律判定），应缴合计 = 年费 + 滞纳金；
- 恢复权利请求费 / 评价报告请求费按费率表条目另列（不计入滞纳金）。

### 2.4 费减（`reduction.*`）

- 资格 = **严格低于**阈值：个人月均收入**或**年收入低于阈值；单位应纳税所得额低于阈值；
- 共同主体（≥2）须逐个合格；比例按主体构成取 85%（单主体）/ 70%（共同主体）；
- 阈值按 `as_of_year` 锚定 316 号（2019-07-01）前后版本；
- 多政策择一（594 号）：候选 = {费减比例, 开放许可 15% 减免}，取**实缴额最小**者，
  全候选留痕、不叠加。

### 2.5 组合排期（`portfolio`）

逐件四态：`settled`（已缴清）/ `unpaid`（已到期未缴）/ `not_due`（未到期）/
`failed`（坏格式，失败隔离）。到期预警 = 窗口内（`window_months × 31` 天）
未到期件按剩余天数升序。`today` 由输入显式提供。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | 依据锚点 |
|---|---|---|---|
| 年费计算完成 | `pass` | 否 | `annuity.<type>` 条目 |
| 滞纳金计算完成（含超上限 warning） | `pass` | 否 | `late.monthly_rate` |
| 费减计算完成（合格/不合格均为有效结论） | `pass` | 否 | `reduction.rate.sole` / `combined` |
| 组合排期已缴清 / 未到期 | `pass` | 否 | `annuity.<type>` 或账本契约 |
| 组合排期已到期未缴 | `fail` | **是**（退出码 1） | `annuity.<type>` |
| 组合排期坏格式 / 窗口内到期 | `not_applicable` | 否 | 该类型条目 / 账本契约 |
| 门控拒绝 / 未判定 | `not_applicable` | 否 | `contract.gate` |

**输入不可用**（缺 case_id / 段全缺 / 类型或年度非法 / 日期非法 / 主体非法 /
规则集未知）→ `ValueError` → 退出码 2；条文库版本不符 → `ContractError` → 3；
条款缺失 → `BasisMissing`（本产品内核映射 2）。

### 3.2 人读（节选）

```text
clauseproof :: patent-annuity 2026-10-14 :: annuity.json
[pass] patent.annuity:invention:5 — 年费：invention 第 5 年应缴 1200.00 元（区间 4-6 年） :: 国家知识产权局专利收费标准（专利业务办理系统公示） / （七）年费 · 1.发明专利… (2026-10-14)
合计 1 条，阻断 0 条（pass=1 fail=0 na=0）

clauseproof :: patent-annuity 2026-10-14 :: late.json
[pass] patent.late:invention:5 — 滞纳金：逾期 2 个月，滞纳金 120.00 元，应缴合计 1320.00 元 :: …（八）年费滞纳金… (2026-10-14)

clauseproof :: patent-annuity 2026-10-14 :: reduction.json
[pass] patent.reduction:invention:5 — 费减：合格，1 名主体，实缴 180.00 元；选中 费减 :: 《专利收费减缴办法》财税〔2016〕78 号 / 第四条… (2026-10-14)

clauseproof :: patent-annuity 2026-10-14 :: portfolio.json
[pass] patent.portfolio:990000000001SYN#y3 — 组合排期 …：settled
[fail] patent.portfolio:990000000003SYN#y3 — 组合排期 …：unpaid
[not_applicable] patent.portfolio:item[6] — 组合排期 item[6]：failed
[pass] patent.portfolio:summary — 组合排期：7 件（已缴清 2 / 未缴 2 / 未到期 2 / 失败 1）
合计 8 条，阻断 2 条（pass=3 fail=2 na=3）
```

与来源 `patfee calc` / `calc --with-late` / `reduction` / `scan` **逐值一致**：
1200.00；120.00 / 1320.00；180.00；已缴清 2 / 未缴 2 / 未到期 2 / 失败 1。

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 计算完成且组合排期无未缴/无失败（预览/超上限仍为 0，见 §5） |
| `1` | 组合排期检出未缴清 / 窗口内到期 / 失败件 |
| `2` | 输入不合法（缺 case_id / 类型年度非法 / 门控拦截 / 日期主体非法） |
| `3` | 契约违约（条文库版本 ≠ `2026-10-14`；条文库自相矛盾） |

> **漏 `--basis`** → 条文库版本为空 → 版本不符 → **退出码 3**，是契约正确行为。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 年费阶梯（4 类型 × 双闭区间） | ✅ | `calc.compute_annuity` |
| 滞纳金（自然月/30 日口径、上限 warning、关联费用） | ✅ | `calc.compute_late` |
| 费减（阈值年度锚定、严格小于、共同主体、多政策择一） | ✅ | `calc.compute_reduction` |
| 组合排期（四态、失败隔离、到期预警） | ✅ | `calc.scan_portfolio` |
| 规则加载 + 作用域门控 | ✅ | `rules.load_library` / `evaluate_keys` |
| 4 份规则包 + 条款快照 | ✅ | `data/*.json` **逐字节同 sha256** 随包 + 漂移门 |
| 跨轮对账（reconcile） | ❌ | 输入/交付层（额外台账文件）；器官只判单轮 |
| 报告导出（Markdown/XLSX）/ GUI | ❌ | 交付面；入口只有 `list` / `check` |
| 基准 runner / 真值库 / 生成器 | ❌ | 产品级工具面 |
| 数据目录定位（env / `_MEIPASS` / 上溯） | ❌ | 输入层；器官固定随包目录 |
| 零字面量 AST 门禁（tools 侧） | ❌ | 产品级工具面；纪律保留（引擎代码零政策数值） |

## 5. 口径差（如实登记）

1. **入口收敛**：来源 `calc` / `reduction` / `scan` 等子命令 → 器官 `check` 一个入口；
   由 subject 的 `patent` / `late` / `reduction` / `portfolio` 分派。
2. **组合排期基准日显式**：来源 CLI 默认取当日；器官 `portfolio.today` 必填
   （零时钟，同输入同输出）。
3. **账本化输出**：来源 stdout 排版 → 每段/每件一条判定行，金额与过程进 `evidence`。
4. **退出码语义**：来源 `calc --preview` 与滞纳金超上限均返回 1（降级）；器官以
   `pass` + evidence.warnings 表达，rc 0。**主样例（calc 正常）0=0 未变**；
   该差异如实登记，不加兼容 rc。
5. **单轮排期**：来源 `scan` 可带上一轮台账做跨轮对账；器官只做单轮（对账输入/报告
   留产品层）。
6. **条款锚点 = 规则条目 key**：每条规则条目的 `basis.doc_no/clause/url/retrieved`
   直接成为条文库锚点；另有实施细则 5 条原文要点（第 5/110/114/115/116 条）。
7. **金额 Decimal**：`parse_float=Decimal`；测试夹具拒收 float 的纪律保留。
8. **真实规则包全 verified**：32 条规则条目 2026-10-24 复核；pending 路径仅由合成
   规则库测试覆盖（门控语义不变）。
9. **与既有器官零复用**：slug / 规则代码 / 测试文件均不复用。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 124**（8 文件）/ 新器官实跑 **N = 142** | **过**（142 ≥ 124） |
| 2 | README 示例命令 rc 相同 | 旧 `patfee calc data/samples/patent-demo.json` rc **0**（1200.00）/ 新 `check patent-annuity …/annuity.json` rc **0**（1200.00）；滞纳金旧 **0**（120.00/1320.00）/ 新 **0**；费减旧 **0**（180.00）/ 新 **0**；组合排期旧 **1**（已缴 2/未缴 2/未到期 2/失败 1）/ 新 **1**（同计数） | **过**（0=0、0=0、0=0、1=1） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 142 ≥ 124；AST `test_` 函数 **142** ≥ 旧层 **110**；文件数旧 8 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（**254 条目 / 819461 B**）；`patent-annuity/data/` **8 件 / 78615 B**；解包 `list` = **17 器官**、年费样例 rc **0** | **过** |

**判据 1 的命令与输出原文**（来源仓只读，`PYTHONDONTWRITEBYTECODE=1`）：

```bash
cd <来源仓>
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_annuity_ladder.py tests/test_literals_gate.py \
  tests/test_m1_deliverables.py tests/test_m2_engines.py \
  tests/test_m3_portfolio.py tests/test_m5_three_way.py \
  tests/test_rules_gate.py tests/test_rules_loader.py \
  -o addopts="" -q -p no:cacheprovider
# → 124 passed in 0.83s
```

逐文件 passed：annuity_ladder 24 / literals_gate 11 / m1_deliverables 16 /
m2_engines 22 / m3_portfolio 27 / m5_three_way 3 / rules_gate 9 / rules_loader 12 = **124**；
旧层 AST `test_` 函数 = 10+11+16+22+27+3+9+12 = **110**。

> **D1 机械口径说明**：`test_literals_gate.py`（11）、`test_m1_deliverables.py`（16）、
> `test_m3_portfolio.py`（27）、`test_m5_three_way.py`（3）的名字**不含** D1/D18 排除词
> （`literals` / `deliverables` / `portfolio` / `three_way` 均不在词表），故**机械计入
> 分母**，不按域手剔（#10 审计 §3.1 的纠正口径）。其判定值由 §6.1 逐文件处置。

### 6.1 D1 + D18 选文件与逐文件处置（8 文件 / 124 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `test_m3_portfolio.py` | 27 | 组合排期 / 跨轮对账 | **部分迁**：排期四态/失败隔离/到期预警已迁（§2.5）；跨轮对账不迁（`test_m5_three_way` 同） |
| `test_annuity_ladder.py` | 24 | 年费阶梯 | **已迁**（§2.2；测试 §四） |
| `test_m2_engines.py` | 22 | 滞纳金 / 费减 | **已迁**（§2.3–§2.4；测试 §五–§六） |
| `test_m1_deliverables.py` | 16 | 数据先行 / 交付物 | **部分迁**：规则包 sha256/条目不变量由 §十 接管；生成器/真值库不迁 |
| `test_rules_loader.py` | 12 | 规则加载 / schema | **已迁**（§二） |
| `test_literals_gate.py` | 11 | 零政策数值字面量门禁 | **不迁**（产品级工具面；纪律保留：引擎代码零政策数值）。D1 机械计入 X |
| `test_rules_gate.py` | 9 | status 门控 | **已迁**（§2.1；测试 §三） |
| `test_m5_three_way.py` | 3 | 三方一致性（CLI/报告/基准） | **不迁**（报告/基准交付面）。D1 机械计入 X |
| **合计** | **124** | — | 已迁 4 / 部分迁 2 / 不迁 2 |

**D1 + D18 剔除（不计入 X，6 文件 / 105 passed）**：

| 来源测试文件 | passed | D1 词 | 去向 |
|---|---:|---|---|
| `test_cli_exit_codes.py` | 34 | `cli` | 旧 CLI 子命令与退出码（新入口只有 `list`/`check`） |
| `test_repo_guards.py` | 33 | `repo`→`guard` | 仓库结构/零字面量 AST 门（产品级工具面） |
| `test_m5_gui.py` | 15 | `gui` | PySide6 桌面界面（交付面） |
| `test_benchmark.py` | 11 | `bench` | 内置基准 runner（产品级基准面） |
| `test_m5_packaging.py` | 6 | `packaging` | PyInstaller 打包（交付面） |
| `test_m5_report.py` | 6 | `report` | Markdown/XLSX 报告导出（交付面） |

### 6.2 判据 2 对撞（旧命令 vs 新入口）

| 场景 | 旧命令 → rc | 新命令 → rc | 结论 |
|---|---|---|---|
| 年费（README 主样例） | `patfee calc data/samples/patent-demo.json` → **0**（1200.00） | `check patent-annuity --input …/annuity.json --basis …` → **0**（1200.00） | **过**（0=0） |
| 滞纳金 | `patfee calc data/samples/patent-late-demo.json --with-late` → **0**（120.00 / 1320.00） | `check … --input …/late.json` → **0**（同值） | **过**（0=0） |
| 费减 | `patfee reduction data/samples/applicants-demo.json` → **0**（实缴 180.00） | `check … --input …/reduction.json` → **0**（180.00） | **过**（0=0） |
| 组合排期 | `patfee scan data/samples/portfolio-demo.json` → **1**（已缴 2 / 未缴 2 / 未到期 2 / 失败 1） | `check … --input …/portfolio.json` → **1**（同计数） | **过**（1=1） |
| 漏 `--basis` | 旧无概念 | `check … --input …/annuity.json` → **3** | 契约正确行为 |

> 旧侧输入为来源仓 samples 原文件（只读）；全程 `git status --porcelain` = 0 行。

### 6.3 判据 4 的进包清单（`%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation`）

wheel：`clauseproof-0.0.0-py3-none-any.whl`（819461 B，**254 条目**）；
`clauseproof/packs/patent-annuity/data/` **8 件 / 78615 B**：

| 文件 | bytes | 来源 |
|---|---:|---|
| `clauses.json` | 24701 | 32 规则条目 + 5 实施细则 + 4 数据契约（由随包规则/知识库生成） |
| `fee_schedule.v2024.json` | 18691 | 来源 `data/rules/`，**逐字节相同** |
| `knowledge-clauses.json` | 9505 | 来源 `data/knowledge/clauses.json`，**逐字节相同** |
| `reduction_316.v2019.json` | 7519 | 来源 `data/rules/`，**逐字节相同** |
| `reduction_594.v2024.json` | 5574 | 同上 |
| `reduction_78.v2016.json` | 5608 | 同上 |
| `rules-manifest.json` | 5952 | 来源 `data/rules/manifest.json`，**逐字节相同**（sha256 一致） |
| `manifest.json` | 1065 | 逐文件 sha256 / bytes / 条文数登记 |

解包后 `clauseproof list` = **17 器官**；年费样例 rc **0**。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/fee_schedule.v2024.json` | 来源仓 `data/rules/` | **逐字节相同**（16 条费率条目） |
| `data/reduction_78.v2016.json` | 同上 | **逐字节相同**（4 条） |
| `data/reduction_316.v2019.json` | 同上 | **逐字节相同**（7 条，含 `.prev` 历史阈值） |
| `data/reduction_594.v2024.json` | 同上 | **逐字节相同**（5 条） |
| `data/rules-manifest.json` | 来源仓 `data/rules/manifest.json` | **逐字节相同**（sha256 / 门槛） |
| `data/knowledge-clauses.json` | 来源仓 `data/knowledge/clauses.json` | **逐字节相同**（实施细则条款定位） |
| `data/clauses.json` | 32 规则条目 + 5 实施细则 + 4 数据契约 | 版本 `2026-10-14` |
| `data/manifest.json` | 本器官装配产物 | 漂移门：bytes + sha256 + clause_count |
| `samples/patent-annuity/annuity.json` | 来源 `data/samples/patent-demo.json` | 判据 2 主样例（rc 0） |
| `samples/patent-annuity/late.json` | 来源 `patent-late-demo.json` | 滞纳金样例（rc 0） |
| `samples/patent-annuity/reduction.json` | 来源 `applicants-demo.json` | 费减样例（rc 0） |
| `samples/patent-annuity/portfolio.json` | 来源 `portfolio-demo.json` 的 current 台账 | 组合排期（rc 1） |
| `samples/patent-annuity/case-full.json` | 四段合成组合 | 端到端（rc 1，11 条） |

> 样例全部为合成/演示数据，专利号均为虚构（`…SYN` 后缀）。