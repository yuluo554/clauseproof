# 器官 `occupational-surveillance`

> 条文判定器官 · 版本 `2026-10-14` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：**GBZ 188—2025《职业健康监护技术规范》**（国卫通〔2025〕10 号，**2026-08-01 施行**，
> 代替 GBZ 188—2014）+ 2014 版历史年度对照；两版规则包与条款快照**逐字节同 sha256** 随包
> 条文库 103 条：97 个因素条款 + 6 条数据契约；条文库坐标 = 知识库核对日期 `2026-10-14`

一句话：**给一份岗位画像和/或监护档案，判应检项目与周期、档案覆盖度、两版标准差异，
逐项挂 GBZ 条款号；未核对条目拒绝进入核查路径。**

## 1. 输入

```bash
clauseproof check occupational-surveillance \
  --input samples/occupational-surveillance/position-benzene.json \
  --basis src/clauseproof/packs/occupational-surveillance/data/clauses.json
clauseproof check occupational-surveillance \
  --input samples/occupational-surveillance/record-partial.json \
  --basis src/clauseproof/packs/occupational-surveillance/data/clauses.json
clauseproof check occupational-surveillance \
  --input samples/occupational-surveillance/compare-only.json \
  --basis src/clauseproof/packs/occupational-surveillance/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `case_id` | ✅ | 一次判定运行的稳定标识（输入必填字段） |
| `position` | — | 岗位画像：`position_id` / `exam_date` / `factors[]`（`factor_code` + 可选 `exposure` / `years`）/ `last_exam_dates` |
| `records` | — | 监护档案数组：`record_id` / `employee_id` / `factor_code` / `exam_date` / `exam_type`（四类时点）/ `items[]` / 可选 `last_exam_date` |
| `compare` | — | 版本对照请求：`ruleset_a`（旧）/ `ruleset_b`（新） |

`position` / `records` / `compare` **至少给一个**；未知顶层字段 → 退出码 2。

```json
{
  "case_id": "plan-benzene",
  "position": {
    "position_id": "SYN-POS-benzene",
    "exam_date": "2026-09-15",
    "factors": [{"factor_code": "GBZ188-5.19"}]
  },
  "records": [
    {"record_id": "SYN-TRUTH-018", "employee_id": "…", "factor_code": "GBZ188-6.7",
     "exam_date": "2026-09-21", "exam_type": "periodic",
     "items": ["胸部X射线摄片", "肺功能"], "last_exam_date": "2024-09-20"}
  ],
  "compare": {"ruleset_a": "GBZ188-2014", "ruleset_b": "GBZ188-2025"}
}
```

> **数据读取只在装配面**：两版规则包由 :mod:`registry` 固定目录读入（与
> ``Basis.from_json`` 同形态的装配），判定内核只收内存对象。来源的
> `--data-dir` / 环境变量 / PyInstaller `_MEIPASS` / 上溯链**全部留输入层**
> ——器官零环境变量、零 cwd、零时钟。

### 1.1 与既有器官的边界

| 维度 | `occupational-surveillance`（本器官） | 既有器官 |
|---|---|---|
| 对象 | **职业健康监护**：危害因素 × 检查项目 × 周期 + 档案覆盖度 | 无重叠器官（医疗广告 / 食品 / 环保 / 个税 / 发票 / 劳动给付各司其职） |
| 依据 | GBZ 188 双版本（国标） | 各自法规/标准/参数包 |
| 报告对象 | 用人单位监护义务（岗前/在岗/离岗/应急） | 各自业务对象 |

slug / 规则代码（`occupational.*`）/ 测试文件与既有 13 个器官零复用。

## 2. 规则

### 2.1 版本锚定（按体检日期，不按年度）

- `exam_date >= cutover.date` → **GBZ188-2025**；否则 **GBZ188-2014**；
- 只给年度且该年包含切口日（`2026`）→ **年度歧义**（宁报错不猜，退出码 2）；
- 切口日与版本号一律读自规则包 manifest，代码零年份字面量。

### 2.2 status 门控（按作用域）

| 作用域 | 深度 | 拦截 |
|---|---|---|
| `plan` / `check` | full | 因素 + 适用性 + 周期 + 四时点全部项目 |
| `compare` / `bench` | minimal | 只拦「整条因素 pending」与适用性待输入 |

`verified` 条目才可进入核查路径；`pending` 一律拦截（`GateBlocked` → 退出码 2）；
`input_required` 放行但必须显式索取：**适用性/项目级阻断**、**周期级降级为待输入**
（应检项仍可推导）。

### 2.3 监护矩阵（`plan`）

- 适用性三态：`always`（一律纳入）/ `threshold`（接触水平比较，低于阈值 →
  **不适用**，不计违规）/ `input_required`（缺接触水平 → 显式索取，绝不静默取默认值）；
- 应检项 = **required_items**（必检项）；supplementary / optional 不进判定
  （补充项含「必要时」，纳入会把临床判断误判成缺项）；
- 四时点：上岗前 / 在岗期间 / 离岗时 / 应急；周期随规则包。

### 2.4 覆盖度（`check`）

| 条件 | verdict | 账本 |
|---|---|---|
| 应检项全齐 + 周期合规 | `compliant` | `pass` |
| 缺 ≥1 项必检项 / 周期超期 | `partial` | `fail`（阻断） |
| 必检项一项未做 | `non_compliant` | `fail` |
| 因素不适用该人员 | `not_applicable` | `not_applicable`（不计违规） |
| 因素不识别 / 缺必填字段 | `unknown` / `failed` | `not_applicable`（非结论） |

实检项目归一：精确命中 → 显式别名表 → 未归一（**warning，不判缺失**，决策 D-17）。
周期判定：`上次检查日 + N 月`，due 当日合规，无基线不报超期，**不做「今天」判定**。

### 2.5 版本对照（`compare`）

五维：因素新增/删除、检查时点、必检项构成、选检项调整、周期变化。
**明细任一待核对 → 该因素只出因素级差异，条目级比较跳过并记 notes**
（避免把「未转写」误报成「标准差异」）。

### 2.6 条款 pending 如实登记（不静默放行）

GBZ 188—2025 第 8–9 章 **15 个因素**仅因素身份核对、**明细 pending**：
门控在 `plan`/`check` 引用时如实拦截；`compare` 只出因素级差异。清单：

| 章 | 因素 | 名称 | 明细状态 |
|---|---|---|---|
| 8 | 8.1 | 布鲁氏菌 | pending |
| 8 | 8.2 | 炭疽芽孢杆菌 | pending |
| 8 | 8.3 | 蜱传脑炎病毒（森林脑炎病毒） | pending |
| 8 | 8.4 | 布氏疏螺旋体（伯氏疏螺旋体） | pending |
| 8 | 8.5 | 人免疫缺陷病毒 | pending |
| 9 | 9.1 | 电工作业 | pending |
| 9 | 9.2 | 高处作业 | pending |
| 9 | 9.3 | 压力容器作业 | pending |
| 9 | 9.4 | 职业机动车驾驶作业 | pending |
| 9 | 9.5 | 高原作业 | pending |
| 9 | 9.6 | 航空作业 | pending |
| 9 | 9.7 | 刮研作业 | pending |
| 9 | 9.8 | 井下工人长期蹲跪姿、爬行、侧卧、肩扛作业 | pending |
| 9 | 9.9 | 制造业工人长时间腕部重复作业或用力作业 | pending |
| 9 | 9.10 | 参与突发事件处置的应急救援作业 | pending |

第 5–7 章 **82 个因素 / 2520 条项目明细全部 verified**（化学/粉尘/物理），可进入核查路径。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | 依据锚点 |
|---|---|---|---|
| 适用性 `applicable`（应检清单产出） | `pass` | 否 | 因素条款（`factor_id`） |
| 适用性 `not_applicable` / `input_required` | `not_applicable` | 否 | 因素条款 / `contract.version` |
| 覆盖度 `compliant` | `pass` | 否 | 因素条款 |
| 覆盖度 `partial` / `non_compliant` | `fail` | **是**（退出码 1） | 因素条款 |
| 覆盖度 `not_applicable` / `unknown` / `failed` | `not_applicable` | 否 | 因素条款 |
| 版本差异条目 / 对照汇总 | `pass` | 否 | 因素条款 / `contract.compare` |

**输入不可用**（缺 case_id / 三选一全缺 / 卡字段非法 / 年度歧义 / 门控拦截 /
版本未知）→ `ValueError` → 退出码 2；条文库版本不符 → `ContractError` → 3；
条款缺失 → `BasisMissing`（本产品内核映射 2）。

### 3.2 人读（节选）

```text
clauseproof :: occupational-surveillance 2026-10-14 :: position-benzene.json
[pass] occupational.plan:SYN-POS-benzene:GBZ188-5.19 — 苯（CAS 号：71-43-2）：该危害因素一律纳入监护；应检项 emergency 5 项 / periodic 5 项 / post_placement 5 项 / pre_placement 5 项 :: GBZ 188—2025 / 第 5.19 节 (2026-10-14)
合计 1 条，阻断 0 条（pass=1 fail=0 na=0）

clauseproof :: occupational-surveillance 2026-10-14 :: record-partial.json
[fail] occupational.coverage:SYN-TRUTH-018 — 覆盖度 partial（GBZ188-6.7/periodic）：缺项 0 项；周期 overdue :: GBZ 188—2025 / 第 6.7 节 (2026-10-14)
合计 1 条，阻断 1 条（pass=0 fail=1 na=0）

clauseproof :: occupational-surveillance 2026-10-14 :: case-full.json
[pass] occupational.compare:summary — 版本对照：GBZ188-2014 → GBZ188-2025，差异 22 条 :: 数据契约 / 版本对照 (2026-10-14)
[pass] occupational.coverage:SYN-TRUTH-001 — 覆盖度 compliant（GBZ188-5.19/periodic）：缺项 0 项；周期 compliant :: GBZ 188—2025 / 第 5.19 节 (2026-10-14)
[fail] occupational.coverage:SYN-TRUTH-018 — 覆盖度 partial（GBZ188-6.7/periodic）：缺项 0 项；周期 overdue :: GBZ 188—2025 / 第 6.7 节 (2026-10-14)
合计 26 条，阻断 1 条（pass=25 fail=1 na=0）
```

与来源 `ohscheck plan` / `ohscheck check` / `ohscheck compare` **逐值一致**：
苯 5 项 × 4 时点；SYN-TRUTH-018 partial/overdue；版本对照 22 条差异。

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无不符合（覆盖度 pass / NA；对照 pass） |
| `1` | 检出不符合（覆盖度 `partial` / `non_compliant`） |
| `2` | 输入不合法（缺 case_id / 坐标无包 / 年度歧义 / 门控拦截 / 待输入 / 未知因素） |
| `3` | 契约违约（条文库版本 ≠ `2026-10-14`；条文库自相矛盾） |

> **漏 `--basis`** → 条文库版本为空 → 版本不符 → **退出码 3**，是契约正确行为。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 监护矩阵 + 适用性三态 + 逐项溯源 | ✅ | `engine.matrix` |
| 覆盖度四态 + 缺项依据 + 别名归一 | ✅ | `engine.coverage` |
| 周期判定（月末夹取、due 当日、无基线） | ✅ | `engine.period` |
| 版本锚定（体检日期 / 年度歧义） | ✅ | `rules.version` |
| 版本差异对照（五维 + 明细 pending 跳过） | ✅ | `engine.compare` |
| status 门控（四作用域 / 输入分级） | ✅ | `rules.gate` |
| schema 校验（三态不变式 / 合成护栏） | ✅ | `rules.schema` |
| 两版规则包 + 条款快照 | ✅ | `data/*.json` **逐字节同 sha256** 随包 + 漂移门 |
| 批量扫盘（`scan`）/ 跨轮对账（`reconcile`） | ❌ | 输入/交付层；器官只收内存档案 |
| 报告导出（Markdown/XLSX）/ GUI 六页签 | ❌ | 交付面；入口只有 `list` / `check` |
| 基准 runner / 真值库 72 件 / 生成器 | ❌ | 产品级工具面 |
| 数据目录定位（env / `_MEIPASS` / 上溯） | ❌ | 输入层；器官固定随包目录 |
| `selfcheck` / `plan` / `check` / `scan` / `compare` / `report` / `bench` 子命令 | ❌ | 产品级命令面（新入口只有 `list` / `check`） |

## 5. 口径差（如实登记）

1. **入口收敛**：来源七个子命令 → 器官 `check` 一个入口；`position` / `records` /
   `compare` 由 subject 三选一。`scan`（目录）与 `report`（写盘）留产品层。
2. **时间锚定**：来源按体检日期锚定版本（本器官保留）；`scan` 的「今天」上下文不迁
   （器官零时钟）。周期判定仍以 `last_exam_date + N 月` 为准。
3. **账本化输出**：来源 stdout/报告排版 → 每因素/每档案/每差异一条判定行，金额外的
   应检项、缺项、周期、依据 id 全部进 `evidence`。
4. **覆盖度四态映射**：`partial`/`non_compliant` → `fail`（阻断）；`not_applicable`/
   `unknown`/`failed` → `not_applicable`（非结论不冒充合规）；`compliant` → `pass`。
5. **数据目录收敛**：来源五级定位链 → 随包固定目录；同一输入在任何机器可复现。
6. **条款 pending 如实登记**：第 8–9 章 15 因素明细 pending（§2.6），门控拦截；
   器官不把 pending 写成「已覆盖」，也不手填推测值。
7. **条文库 = 97 因素条款 + 6 数据契约**：条款 `text` 为「因素名 + 章节 + 子条款」
   （来源知识库只存节号与核对标记，不转载全文）；路径 = 标准号 / 第 N 节。
8. **合成规则集护栏保留**：`synthetic=true` 的规则集出处必须带 `SYNTHETIC-` 前缀、
   发布机关必须为空（测试夹具不冒充国标）。
9. **与既有器官零复用**：slug / 规则代码 / 测试文件均不复用。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 190**（9 文件）/ 新器官实跑 **N = 205** | **过**（205 ≥ 190） |
| 2 | README 示例命令 rc 相同 | 旧 `ohscheck plan examples/position-sample.json` rc **0**（苯 5 项 × 4 时点）/ 新 `check occupational-surveillance --input …/position-benzene.json --basis …` rc **0**（同 5 项 × 4）；负控旧 `ohscheck check …SYN-TRUTH-018.json` rc **1** / 新 `…/record-partial.json` rc **1**；旧 `ohscheck compare` rc **0**（22 条）/ 新 `…/compare-only.json` rc **0**（22 条） | **过**（0=0、1=1、0=0） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 205 ≥ 190；AST `test_` 函数 **205** ≥ 旧层 **190**；文件数旧 9 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（**240 条目 / 781693 B**）；`occupational-surveillance/data/` **6 件 / 1303399 B**；解包 `list` = **16 器官**、岗位样例 rc **0** | **过** |

**判据 1 的命令与输出原文**（来源仓只读，`PYTHONDONTWRITEBYTECODE=1`）：

```bash
cd <来源仓>
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_engine.py tests/test_foundation.py tests/test_m2.py tests/test_m3.py \
  tests/test_m4.py tests/test_m5.py tests/test_rules_gate.py tests/test_scaffold.py \
  tests/test_truth.py \
  -o addopts="" -q -p no:cacheprovider
# → 190 passed in 4.74s
```

逐文件 passed：engine 20 / foundation 19 / m2 27 / m3 24 / m4 15 / m5 15 /
rules_gate 23 / scaffold 30 / truth 17 = **190**；旧层 AST `test_` 函数同为 **190**。

> **D1 机械口径说明**：`test_scaffold.py`（30）、`test_truth.py`（17）、
> `test_m4.py`（15）、`test_m5.py`（15）的名字**不含** D1/D18 排除词
> （`scaffold` / `truth` / `m4` / `m5` 均不在词表），故**机械计入分母**，
> 不按域手剔（#10 审计 §3.1 的纠正口径）。其判定值由 §6.1 逐文件处置。

### 6.1 D1 + D18 选文件与逐文件处置（9 文件 / 190 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `test_scaffold.py` | 30 | 仓库骨架 / 架构门 | **部分迁**：包结构/入口/数据纪律由本器官接线与 §十三 接管；仓库级架构门属产品级。D1 机械计入 X |
| `test_m2.py` | 27 | 矩阵 / 覆盖度 / 周期 | **已迁**（§2.3–§2.4；测试 §七–§九） |
| `test_m3.py` | 24 | 批量/对账/报告 | **部分迁**：单件覆盖度与对照迁入；扫盘/跨轮对账/报告导出不迁 |
| `test_rules_gate.py` | 23 | schema / 门控 / 版本 | **已迁**（§2.1–§2.2；测试 §二–§五） |
| `test_engine.py` | 20 | 矩阵 / 覆盖度 / 周期边界 | **已迁**（§七–§九） |
| `test_foundation.py` | 19 | 数据/模型/加载 | **已迁**（§三/§六） |
| `test_truth.py` | 17 | 72 件真值库对账 | **不迁**（真值库/生成器属产品级工具面；判定覆盖由本器官 205 条用例接管）。D1 机械计入 X |
| `test_m4.py` | 15 | 内置基准 | **不迁**（基准 runner 产品级工具面）。D1 机械计入 X |
| `test_m5.py` | 15 | GUI/报告/打包 | **不迁**（交付面）。D1 机械计入 X |
| **合计** | **190** | — | 已迁 4 / 部分迁 2 / 不迁 3 |

**D1 + D18 剔除（不计入 X，4 文件 / 58 passed）**：

| 来源测试文件 | passed | D1 词 | 去向 |
|---|---:|---|---|
| `test_cli.py` | 25 | `cli` | 旧七子命令与退出码（新入口只有 `list`/`check`） |
| `test_report.py` | 14 | `report` | Markdown/XLSX 报告导出（交付面） |
| `test_benchmark.py` | 12 | `bench` | 内置基准 runner（产品级基准面） |
| `test_license_metadata.py` | 7 | `license` | 发行元数据（产品级） |

### 6.2 判据 2 对撞（旧命令 vs 新入口）

| 场景 | 旧命令 → rc | 新命令 → rc | 结论 |
|---|---|---|---|
| README 示例（岗位应检） | `ohscheck plan examples/position-sample.json` → **0**（4 时点各 5 项） | `check occupational-surveillance --input …/position-benzene.json --basis …` → **0**（同 5 项 × 4） | **过**（0=0） |
| 覆盖度负控（周期超期） | `ohscheck check data/truth/records/SYN-TRUTH-018.json` → **1**（partial / overdue） | `check … --input …/record-partial.json` → **1**（partial / overdue） | **过**（1=1） |
| 版本对照 | `ohscheck compare` → **0**（22 条差异） | `check … --input …/compare-only.json` → **0**（22 条 + 汇总） | **过**（0=0，条数一致） |
| 漏 `--basis` | 旧无概念 | `check … --input …/position-benzene.json` → **3** | 契约正确行为 |
| 未知规则集（对照） | 旧 CLI → 2 | subject `compare.ruleset_b="NOPE"` → **2** | 过 |

> 旧侧输入为来源仓 examples/truth 原文件（只读）；全程 `git status --porcelain` = 0 行。

### 6.3 判据 4 的进包清单（`%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation`）

wheel：`clauseproof-0.0.0-py3-none-any.whl`（781693 B，**240 条目**）；
`clauseproof/packs/occupational-surveillance/data/` **6 件 / 1303399 B**：

| 文件 | bytes | 来源 |
|---|---:|---|
| `clauses.json` | 33220 | 97 因素条款 + 6 条数据契约（由随包知识库生成） |
| `knowledge-clauses.json` | 68606 | 来源 `data/knowledge/clauses.json`，**逐字节相同** |
| `rules-manifest.json` | 1331 | 来源 `data/rules/manifest.json`，**逐字节相同** |
| `ruleset-2014.json` | 191153 | 来源 `data/rules/`，**逐字节相同**（sha256 一致） |
| `ruleset-2025.json` | 1008282 | 来源 `data/rules/`，**逐字节相同**（sha256 一致） |
| `manifest.json` | 807 | 逐文件 sha256 / bytes / 条文数登记 |

解包后 `clauseproof list` = **16 器官**；岗位样例 rc **0**（1 条 pass）。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/ruleset-2025.json` | 来源仓 `data/rules/` | **逐字节相同**（sha256 `99be71c8…`） |
| `data/ruleset-2014.json` | 来源仓 `data/rules/` | **逐字节相同**（sha256 `d484508e…`） |
| `data/rules-manifest.json` | 来源仓 `data/rules/manifest.json` | **逐字节相同**（切口日 / 门槛 / sha256） |
| `data/knowledge-clauses.json` | 来源仓 `data/knowledge/clauses.json` | **逐字节相同**（97 因素核对记录） |
| `data/clauses.json` | 97 因素条款 + 6 条数据契约 | 版本 `2026-10-14` |
| `data/manifest.json` | 本器官装配产物 | 漂移门：bytes + sha256 + clause_count |
| `samples/occupational-surveillance/position-benzene.json` | 来源 README 示例岗位 | 判据 2 主样例（rc 0） |
| `samples/occupational-surveillance/record-partial.json` | 来源真值库 SYN-TRUTH-018 | 覆盖度负控（rc 1） |
| `samples/occupational-surveillance/compare-only.json` | 两版规则集对照 | 对照样例（rc 0，22 条） |
| `samples/occupational-surveillance/case-full.json` | 合成组合（岗位 + 两条档案 + 对照） | 端到端（rc 1，26 条） |

> 样例全部为合成/演示数据，不含真实劳动者个人信息。