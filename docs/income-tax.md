# 器官 `income-tax`

> 条文判定器官 · 版本 `0.1.0` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：八个年度规则包（2019–2026，`data/rules/ruleset-*.json`）+ 算例真值库，与来源仓
> **逐字节同 sha256**；条文库坐标 = 来源仓核对日期 `2026-10-07`
> 条文库 38 条：34 条来自规则包 `ref` 节点并集（8 个来源文号）+ 4 条数据契约

一句话：**给一份工资薪金年度档案 + 随包年度规则包，判该年度应预扣多少、年终奖单独
计税与并入综合所得哪一方案更省、申报的七项专项附加扣除是否成立**。

## 1. 输入

```bash
clauseproof check income-tax \
  --input samples/income-tax/readme-example.json \
  --basis src/clauseproof/packs/income-tax/data/clauses.json
clauseproof check income-tax \
  --input samples/income-tax/claims-reject.json \
  --basis src/clauseproof/packs/income-tax/data/clauses.json --json
clauseproof check income-tax \
  --input samples/income-tax/trap-2024.json \
  --basis src/clauseproof/packs/income-tax/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `year` | ✅ | 纳税年度（整数；须命中随包八册之一，否则退出码 2）。**来源的 `--year` 旗标在器官里移入 subject** |
| `months` / `uniform_month` + `month_count` | 二选一 | 月度输入；缺月按 0 补足到 12 期并显式出账 `tax.months.padded` |
| `social` | — | 社保公积金联动：`base_input` / `base_lower` / `base_upper` / `rates`（费率与基数**全部用户输入**） |
| `special_additional_claims` | — | 七项专项附加扣除申报清单（违规**整单拒绝**，不产出部分结果） |
| `bonus_income` | — | 全年一次性奖金（正金额；提供后同时出账单独计税、双方案择优与临界区间落点） |
| `settlement` | — | 年度汇算覆盖字段；优先级最高（缺省 = 月度输入聚合 + 预扣结果） |

```json
{
  "year": 2019,
  "uniform_month": {"gross": "20000.00", "special_deduction": "0.00"},
  "month_count": 12,
  "social": {"base_input": "10000.00", "base_lower": "4000.00", "base_upper": "25000.00",
             "rates": {"养老": "0.08", "医疗": "0.02", "失业": "0.005", "公积金": "0.12"}},
  "bonus_income": "36001.00",
  "special_additional_claims": [
    {"item": "child_education", "children": 1, "share_ratio": "1.0"},
    {"item": "housing_loan", "months": 12},
    {"item": "support_elderly", "only_child": true}
  ]
}
```

> **文件读取只在装配面**：随包冻结的八册规则包与真值库由 `registry` 读入（与
> `Basis.from_json` 同形态），判定内核只收内存 dict。器官不读环境变量、不读时钟、
> 不做数据目录上溯——来源的 `--data-dir` / `INCOMETAX_DATA_DIR` 定位链留输入层。

## 2. 规则

### 2.1 status 门控（先于一切计算）

八册规则包全部数值条目（含两张税率表逐行）必须 `已核对`；任一 `待核对` →
`fail` + 退出码 1，`未出账` 显式记一条 `not_applicable`（不静默按已核对计算）。
`status` 缺失按待核对处理（宁缺勿错）。

### 2.2 累计预扣逐月（`monthly`）

```
累计应纳税所得额 = 累计收入 − 累计免税收入 − 累计减除费用(月度减除 × 月序号，查规则包)
                   − 累计专项扣除 − 累计专项附加扣除 − 累计其他扣除
累计应预扣税额   = 累计应纳税所得额 × 预扣率 − 速算扣除数
本期应预扣       = 累计应预扣 − 累计已预扣
```

- 级距**上界闭**（「不超过 X 元」含 X）：顺序查到第一个 `taxable ≤ upper` 的级次；
- 累计应纳税所得额 ≤ 0 → 当期税额 0，级次 `None`；
- 本期应预扣为负 → 按 0（暂不退税、负数不滚存），余额留汇算。

### 2.3 社保联动（`social`）

缴费基数自动夹取到 `[下限, 上限]`，逐险种个人部分 = 基数 × 费率（两位小数，
`ROUND_HALF_UP`），合计并入每月专项扣除并回链标注。**规则包不存全国社保参数**。

### 2.4 七项专项附加扣除（`deductions`）

- 子女教育/婴幼儿照护：每孩标准 × 孩数 × 分摊比例（100% 或 50%）；
- 继续教育：学历按月（同一学位月数上限查规则包）/ 职业资格年度定额（仅汇算链）；
- 大病医疗：仅汇算链，自付累计 − 起付线后与年度限额取低；预扣链月额恒 0；
- 住房贷款利息 / 住房租金**互斥**（规则包显式 `mutually_exclusive` 标记 + 条款）；
- 赡养老人：独生定额 / 非独生本人月额 + 每人上限 + 全体合计上限；
- 未知项目、重复申报、分档/月数/分摊/上限违规 → 收集全部违规一次性抛出，
  **整单拒绝，不产出部分结果（误放行 0）**。

标准值全部查规则包：年度切换即标准切换（如子女教育提标、婴幼儿照护自设立年度起适用）。

### 2.5 年度汇算（`settlement`）

```
应纳税所得额 = 收入额合计 − 减除费用(月度减除 × 12) − 专项扣除 − 专项附加扣除 − 其他扣除
应纳税额     = 应纳税所得额 × 税率 − 速算扣除数
应退/应补    = 已预扣预缴合计 − 应纳税额   （正 = 应退，负 = 应补）
```

### 2.6 年终奖（`bonus`）

- 单独计税：商数 = 奖金 ÷ 规则包月份数，`ROUND_HALF_UP` 两位**仅用于定档**，税基仍是奖金全额；
- 双方案择优：A 全年总税负 = 工资汇算应纳税额 + 奖金单独税额；B = 奖金并入后重跑汇算；
  差（A−B）≤ 申报精度即并列；政策到期年度 A 标不可用，强制推荐 B；
- 临界区间：由按月换算表逐边界推导 `B* = (b·(1−r₁) + q₁ − q₂) / (1 − r₂)`，
  端点全部来自规则表，代码零政策数值字面量。落入区间记 `[!!]` 预警，**不阻断**。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| status 门控拦截（待核对条目） | `fail` | **是**（退出码 1） | status 门控契约 |
| 社保公积金个人部分合计 | `pass` | 否 | 社保参数属用户输入契约 |
| 逐月累计预扣（每期一条） | `pass` | 否 | 减除费用条款（级次/税率在 evidence） |
| 专项附加扣除逐项成立 | `pass` | 否 | 该项标准条款 |
| 年度汇算应退/应补 | `pass` | 否 | 减除费用条款 |
| 年终奖单独计税 | `pass` | 否 | 按月换算税率表附件 |
| 单独计税政策有效 / 已到期 | `pass` / `not_applicable` | 否 | 政策条款 |
| 双方案择优 | `pass` | 否 | 择优/优惠衔接政策条款 |
| 临界区间（未落入 / 落入预警） | `not_applicable` | 否 | 按月换算税率表附件 |
| 缺月补足 | `not_applicable` | 否 | 缺月补足契约 |
| 计算完成（汇总） | `pass` | 否 | 账本口径契约 |

**输入不可用**（年度不在册/字段不认识/数值非法/月数为空或超限/社保参数缺成对上下限/
扣除申报违规整单拒绝/奖金非正/已预扣为负）→ 抛 `ValueError` → 退出码 2
（与来源「用法与输入错误 = 2」逐条对齐）。

### 3.2 人读（`readme-example.json`，退出码 0，节选）

```text
clauseproof :: income-tax 0.1.0 :: readme-example.json
[pass] tax.social — 社保公积金个人部分合计 2250.00 元/月（缴费基数 10000.00，用户输入区间 [4000.00, 25000.00]；养老 800.00、医疗 200.00、失业 50.00、公积金 1200.00） :: 数据契约 / 社保参数属用户输入 (2026-10-07)
[pass] tax.claim:child_education — 子女教育（预扣+汇算）：1000.00 元/孩/月 × 1 孩 × 分摊 100% → 年额 12000.00 元 :: 个人所得税专项附加扣除暂行办法 / 第五条第一款（每个子女每月1000元） (2026-10-07)
[pass] tax.month:01 — 第 1 月：累计收入 20000.00 − 累计减除 5000.00 − 累计专项 2250.00 − 累计专项附加 4000.00 − 累计其他 0.00 = 累计应纳税所得额 8750.00；第 1 级 3.00%（速算 0.00）→ 累计应预扣 262.50；本期应预扣 262.50（注：含社保公积金个人部分 2250.00 元/月（社保联动计算）；含专项附加扣除申报计入（明细见申报清单）） :: 个人所得税扣缴申报管理办法（试行） / 第六条（…） (2026-10-07)
[pass] tax.settlement — 年度汇算：减除费用 60000.00，应纳税所得额 105000.00 → 第 2 级 10.00%（速算 2520.00）→ 年应纳税额 7980.00；已预扣 7980.00 → 应退税额 0.00 :: 个人所得税扣缴申报管理办法（试行） / 第六条（…） (2026-10-07)
[pass] tax.bonus — 全年一次性奖金 36001.00 ÷ 12 = 3000.08（商数定档，税基全额）→ 第 2 级 10.00%（速算 210.00）→ 应纳税额 3390.10；税后 32610.90 :: 财税〔2018〕164号 / 附件1：按月换算后的综合所得税率表 (2026-10-07)
[pass] tax.bonus.compare — 方案 A 全年总税负 11370.10 / 方案 B 11580.10；差额（A−B）-210.00 → 推荐方案 A：单独计税全年少缴 210.00 :: 财税〔2018〕164号 / 第一条（一） (2026-10-07)
[not_applicable] tax.bonus.trap — [!!] 奖金落入临界区间 (36000.00, 38566.67)：区间内税后奖金低于左端锚点处（税率表级距机制客观呈现，非避税建议） :: 财税〔2018〕164号 / 附件1：按月换算后的综合所得税率表 (2026-10-07)
合计 22 条，阻断 0 条（pass=21 fail=0 na=1）
```

与来源仓 `incometax calc --year 2019 --input calc-input.json` 的输出**逐值一致**：
社保 2250.00（800/200/50/1200）、三项申报月额 1000/1000/2000、12 期已预扣 7980.00、
汇算应纳税额 7980.00 / 应退 0.00、奖金税额 3390.10 / 税后 32610.90、
方案 A 11370.10 vs B 11580.10、临界区间 (36000.00, 38566.67)。

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无阻断（全部计算行 `pass`，预警/缺月记 `not_applicable`） |
| `1` | 规则包存在待核对条目 → `fail`（与来源 1 = 运行期门控拦截一致） |
| `2` | 输入不合法（年度不在册/字段不认识/数值非法/月数问题/社保参数/扣除申报违规/奖金非正/已预扣为负） |
| `3` | 契约违约（条文库版本与规则包快照 `2026-10-07` 不符；规则包 schema 自相矛盾） |

> **漏 `--basis`** → 条文库版本为空 → 版本不符 → **退出码 3**，是契约正确行为。
> 条文库缺某条款 → `BasisMissing` 在本产品内核映射 **退出码 2**（`ORG-PLAYBOOK` §4
> 的口径是 3；未改内核，此处如实登记，与 `docs/cost-card.md` §3.3 同）。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 年度规则包 8 册 + 算例真值库 | ✅ | `data/*.json` **逐字节同 sha256** 随包 + 漂移门 |
| schema v1 + status 门控 | ✅ | `rules`（结构/日期/review/值节点 ref 全迁；文件 IO 不迁） |
| 累计预扣逐月状态机 | ✅ | `monthly`（上界闭区间、负值按 0 留汇算） |
| 社保公积金联动 | ✅ | `social`（参数全部用户输入，零政策数值） |
| 七项专项附加校验/分档/分链 | ✅ | `deductions`（整单拒绝 + 两链聚合） |
| 年度汇算 + 应退/应补符号 | ✅ | `settlement` |
| 年终奖单独计税/择优/临界区间 | ✅ | `bonus`（端点全由规则表推导） |
| calc 全链路编排 | ✅ | `pipeline`（社保 → 申报 → 预扣 → 汇算 → 奖金） |
| 真值库 4 算例逐字段对账 | ✅ | `tests/test_income_tax.py` §八（字符串/Decimal 同构） |
| 报告排版（表格/依据图例/免责声明横幅） | ❌ | 输出排版属产品层（`SKELETON-SPEC` §2） |
| CLI / GUI（PySide6）/ PyInstaller 打包 | ❌ | 交付面；入口只有 `list` / `check` |
| `--data-dir` / 环境变量 / 上溯找数据目录 | ❌ | 输入层；器官零文件 IO、零环境、零时钟 |
| 基准 runner / 生成器 / 冻结守门 / 脱敏审计 | ❌ | 产品级工具面；sha256 + schema + 零字面量门接管 |
| `benchmark` / `rules` / `selftest` 子命令 | ❌ | 产品级命令面（新入口只有 `list` / `check`） |

## 5. 口径差（如实登记）

1. **年度旗标移入 subject**：来源 `incometax calc --year 2019 --input …` 的 `--year`
   在器官里变成 `subject.year`（入口只有 `list` / `check`）。同参数重跑见 §6 判据 2。
2. **输入从文件变成内存档案**：月度输入 / 社保参数 / 申报清单 / 奖金 / 汇算覆盖字段
   由 subject 提供；编码、文件发现、路径解析留输入层。
3. **缺月补足显式出账**：来源 CLI 静默按 0 补足 12 期；器官补 0 后额外出账一条
   `tax.months.padded`（`not_applicable`）。累计口径下补 0 不改变税额。
4. **扣除申报违规 = 输入不合法（rc 2）**：来源 `DeductionViolationError` → `CliUsageError`
   → **2**；器官同样抛 `ValueError` → **2**，且违规原因逐条带条款短引用。不改判据迁就代码。
5. **引擎级语义非法输入 rc 1 → 2（口径差，已接受）**：来源把引擎上抛的 `ValueError`
   （奖金非正、已预扣为负、社保区间倒置等）映射为 `RuntimeFailure` → **1**；
   本器官按产品契约统一映射「输入不合法」→ **2**。语义未变（都是拒绝出账，不出部分结果），
   仅退出码归类不同；未加兼容 rc，未改内核退出码表。实测对照见 §6.4。
6. **规则包自身不合法 → 契约违约 3**：来源 schema 错误为 1/2 混合；本器官规则包是随包
   冻结资产，schema 违例属契约违约（3）。真实八册全部通过，该路径只由合成包触发。
7. **临界区间预警不阻断**：落入区间来源只打印 `[!!]`（rc 仍 0）；器官记 `not_applicable`
   （预警 ≠ 判定），与 `docs/cost-card.md` 的预警口径一致。
8. **条文库坐标 = 规则包 ref 并集**：34 条 ref 条款逐字取自来源规则包（8 个文号），
   另有 4 条数据契约（社保参数来源、缺月补足、status 门控、账本口径）；不编造文号。
9. **报告头时间戳 / 免责声明排版不迁**：器官零时钟、零排版。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 107**（11 文件）/ 新器官实跑 **N = 145** | **过**（145 ≥ 107） |
| 2 | README 示例命令 rc 相同 | 旧 `incometax calc --year 2019 --input calc-input.json` rc **0** / 新 `clauseproof check income-tax --input samples/income-tax/readme-example.json --basis …/clauses.json` rc **0**，逐值一致（2250 / 7980 / 3390.10 / -210.00）；负控：申报互斥旧 **2** / 新 **2**、坏字段旧 **2** / 新 **2**、年度缺失旧 **2** / 新 **2**、门控待核对旧 **1** / 新 **1** | **过**（0=0；负控见 §6.4，rc 1→2 一项已登记为口径差） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 145 ≥ 107；AST `test_` 函数 **145** ≥ 旧层 **107**；文件数旧 11 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（**181 条目**）；`clauseproof/packs/income-tax/data/` **11 件 / 145818 B**（8 规则包 + 真值库 + clauses + manifest）；解包 `list` = **13 器官**、`check` rc **0** | **过** |

**判据 1 的命令与输出原文**（来源仓只读，`PYTHONDONTWRITEBYTECODE=1`）：

```bash
cd <来源仓>
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_engine_bonus.py tests/test_engine_deductions.py tests/test_engine_monthly.py \
  tests/test_engine_settlement.py tests/test_engine_social.py tests/test_gen_rulesets.py \
  tests/test_package.py tests/test_rules_loader.py tests/test_truth.py \
  tests/test_truth_reconciliation.py tests/test_zero_policy_literals.py \
  -o addopts="" -q -p no:cacheprovider
# → 107 passed in 44.72s
```

> **X 口径**：上一会话曾按域手工剔除 `test_gen_rulesets.py`（4）与 `test_package.py`（3），
> 得 9 文件 / 100 passed —— **那是偏差，不是 D1 机械结果**（两文件名均不含排除词
> `generat` / `packaging`，D1 按文件名子串匹配，必须计入）。本器官按审计复算的
> **11 文件 / 107 / AST 107** 执行；`docs` 与台账均记此值，**未静默沿用 100**。

### 6.1 D1 + D18 选文件与逐文件处置（11 文件 / 107 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `test_engine_deductions.py` | 31 | 七项扣除校验/分档/分链 | **已迁**（§二.4 / 测试 §六） |
| `test_rules_loader.py` | 24 | schema / 门控 / review / 合成拦截 | **部分迁**：结构/门控/日期/合成拦截 21 条已迁；数据目录定位 3 条不迁（器官不读环境变量、不扫盘） |
| `test_engine_bonus.py` | 15 | 单独计税/择优/临界区间 | **已迁**（§二.6 / 测试 §七） |
| `test_engine_monthly.py` | 8 | 累计预扣状态机 | **已迁**（§二.2 / 测试 §三） |
| `test_truth_reconciliation.py` | 6 | 4 算例逐字段对账 | **已迁**（真值库随包 / 测试 §八） |
| `test_engine_settlement.py` | 5 | 年度汇算 | **已迁**（§二.5 / 测试 §四） |
| `test_truth.py` | 5 | 真值库 schema | **已迁**（测试 §八） |
| `test_engine_social.py` | 4 | 社保联动 | **已迁**（§二.3 / 测试 §五） |
| `test_gen_rulesets.py` | 4 | 生成器逐字节重生成 | **部分迁**：随包 sha256 + 年度清单 + 值节点 ref/verified 3 条由漂移门/测试 §一、§二接管；生成器重生成 1 条不迁（产品级工具面） |
| `test_package.py` | 3 | 包级冒烟 | 不迁（产品级打包门；判据 4 的 wheel 解包接管） |
| `test_zero_policy_literals.py` | 2 | 零政策数值字面量 | **已迁**（测试 §九；扫描面收窄为判定内核 8 模块，装配面 rules/registry 不在扫描范围） |
| **合计** | **107** | — | 已迁 8 / 部分迁 2 / 不迁 1 |

**D1 + D18 剔除（不计入 X，5 文件 / 65 passed）**：`test_benchmark.py`（bench → 产品级
基准面）、`test_cli.py`（cli → 入口只有 `list` / `check`）、`test_desensitize.py`
（desensit → 脱敏审计器）、`test_gui.py`（gui → GUI 交付面）、
`test_license_metadata.py`（license → 发行元数据）。`conftest.py` 非测试文件。

### 6.2 判据 2 对撞（旧命令 vs 新入口）

| 场景 | 旧命令 → rc | 新命令 → rc | 结论 |
|---|---|---|---|
| README 示例 | `incometax calc --year 2019 --input calc-input.json` → **0** | `check income-tax --input samples/income-tax/readme-example.json --basis …/clauses.json` → **0** | **过**（0=0，逐值一致） |
| 申报互斥 | `calc --year 2024 --input calc-conflict.json` → **2** | `check … --input samples/income-tax/claims-reject.json --basis …` → **2** | **过**（2=2，同条款 S41·第二十条） |
| 坏数值 | `calc --year 2019 --input calc-badfield.json` → **2** | subject `uniform_month.gross="abc"` → **2** | **过** |
| 年度缺失 | `calc --year 1999 …` → **2** | subject `year=1999` → **2** | **过** |
| 门控待核对 | `--data-dir <tmp> calc --year 2099 …`（合成包）→ **1** | `evaluate_with_rulesets`（合成包）→ `Report.exit_code()` **1** | **过**（1=1） |
| 奖金非正 | `calc --year 2019 … bonus_income="0.00"` → **1** | subject `bonus_income="0.00"` → **2** | **口径差（接受）**：旧把引擎 `ValueError` 归运行期失败 1，新按输入不合法 2；不改内核、不加兼容 rc（§5.5） |
| 漏 basis | 旧无概念 | `check income-tax --input …`（无 `--basis`）→ **3** | 契约正确行为（条文库版本不符） |

> 旧侧输入文件与合成规则包均在 `%TEMP%` 副本内，来源仓全程 `git status --porcelain` = 0 行。

### 6.3 判据 4 的进包清单（`%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation`）

wheel：`clauseproof-0.0.0-py3-none-any.whl`（618046 B，**181 条目**）；
`clauseproof/packs/income-tax/data/` **11 件 / 145818 B**：

| 文件 | bytes | 来源 |
|---|---:|---|
| `clauses.json` | 15892 | 34 条规则包 ref + 4 条数据契约（由随包规则包生成） |
| `manifest.json` | 2591 | 逐文件 sha256 / bytes / 核对日期登记 |
| `ruleset-2019.json` | 13839 | 来源 `data/rules/`，逐字节相同 |
| `ruleset-2020.json` | 13839 | 同上 |
| `ruleset-2021.json` | 13839 | 同上 |
| `ruleset-2022.json` | 15659 | 同上 |
| `ruleset-2023.json` | 16115 | 同上 |
| `ruleset-2024.json` | 16115 | 同上 |
| `ruleset-2025.json` | 16115 | 同上 |
| `ruleset-2026.json` | 16115 | 同上 |
| `truth-cases.json` | 5699 | 来源 `data/truth/cases.json`，逐字节相同（4 算例） |

解包后 `clauseproof list` = **13 器官**（12 + `income-tax`）；`check income-tax` 示例 rc **0**。

### 6.4 全量回归与接线

- `BUILTIN_MODULES` 字典序 **13 项**（`income-tax` 插在 `ghg-ledger` 与 `labeling-claims` 之间）；
- README 器官表 13 行 + 2 条新示例；
- 全量回归（`.venv-test/Scripts/python.exe -m pytest tests -q`）：**3037 passed**
  = 2892 + 145，既有 12 个器官不红。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/ruleset-2019..2026.json` | 来源仓 `data/rules/` | **逐字节相同**（manifest 登记 sha256） |
| `data/truth-cases.json` | 来源仓 `data/truth/cases.json` | **逐字节相同**（4 算例真值） |
| `data/clauses.json` | 8 册 ref 并集 + 4 条数据契约 | 版本 `2026-10-07` |
| `samples/income-tax/readme-example.json` | README 示例输入格式 + 真值月口径 | 判据 2 主样例（rc 0） |
| `samples/income-tax/claims-reject.json` | 来源互斥校验语义 | 负控（rc 2） |
| `samples/income-tax/trap-2024.json` | 真值库奖金临界对 | 预警样例（rc 0，na 落点） |
