# 器官 `petfood-label`

> 条文判定器官 · 版本 `0.2.0` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：GB/T 31216—2014（犬粮）、GB/T 31217—2014（猫粮）、农业农村部公告第 20 号 附件 3
> 条文库坐标：`2026.1`（规则包版本）

一句话：**给一份结构化标签档案，逐条判它合不合规，每条结论挂可点的条款锚点**
（45 条规则 = 5 宣称支撑 + 8 标签标示 + 32 理化指标；43 条生效、2 条待核对）。

## 1. 输入

```bash
clauseproof check petfood-label \
  --input samples/petfood-label/card-ok.json \
  --basis src/clauseproof/packs/petfood-label/data/clauses.json
clauseproof check petfood-label \
  --input samples/petfood-label/card-missing.json \
  --basis src/clauseproof/packs/petfood-label/data/clauses.json --json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `category` | ✅ | `猫粮` / `犬粮`；营养维度的适用域画像**依赖它**（缺 → 该维度未评估） |
| `life_stage` | — | `成年` / `幼年` / `妊娠哺乳期`；缺 → 营养规则一律不适用（宁可不判） |
| `fields` | — | 已标示的标签字段：`product_name` `category` `life_stage` `ingredients` `additives` `net_content` `producer` `product_dates`（键不在白名单 → 输入错误） |
| `guaranteed` | — | 成分分析保证值：`指标 → {value, unit}`；数值可为数字或数值字符串（全程 `Decimal`） |
| `claims` | — | 已宣称的宣称词（词表来自规则包：天然/无谷/无添加/纯天然/鲜肉） |

```json
{
  "card_id": "SAMPLE-PET-OK",
  "category": "猫粮",
  "life_stage": "成年",
  "fields": {"product_name": "测试粮A", "ingredients": "鸡肉、糙米、鱼油",
             "additives": "维生素A、硫酸锌", "net_content": "2kg",
             "producer": "某合成宠物食品有限公司", "product_dates": "生产日期 2026-01-01"},
  "guaranteed": {"水分": {"value": 12, "unit": "%"},
                 "粗蛋白": {"value": 23, "unit": "%"}},
  "claims": ["天然"]
}
```

## 2. 规则

| `kind` | 语义 | 判定 |
|---|---|---|
| `presence` | 标示项是否提供 | 提供了 → `compliant`；缺失：`obligation` → **`noncompliant`**，`conditional` → `unknown`（待人工确认） |
| `threshold` | 保证值 vs 限值 | 保证值缺失 → `not_provided`；比较成立 → `compliant`，否则 `noncompliant` |
| `claim_support` | 宣称的条件信息是否齐备 | 未宣称 → `skipped`（前提不成立）；支撑缺失 → `noncompliant`；齐备 → `compliant` |

**干物质基准**：GB/T 31216/31217 的理化指标表头是"以干物质计"，而标签保证值按标示状态给。
`干基 = 标示值 / (1 - 水分% / 100)`；水分缺失或不在 `(0,100)` 开区间 → `unknown(basis_undetermined)`，
**绝不拿未换算的值直接比**（高水分湿粮会被误判为不合格——来源实测踩过）。

**适用域画像**：`applies_if` 支持 `category` / `life_stage`；**未提供的输入不满足任何分支**
（缺生命阶段就不套具体阶段的限值）。某维度**有生效规则但一条不适用** → 该维度"未评估"，
在账本里给一条 `dimension.<维度>` 登记行——**绝不输出合规**。

**双重门控**：`status`（数值核对）决定是否进判定路径；`clause_status`（条款号核对）只管
可证性展示。营养条目 30 条 verified、2 条 `牛磺酸` pending（限值未核对）→ 不进判定路径，
账本里留一行 `ruleset.pending` 登记。

## 3. 输出

### 3.1 账本映射

| 来源五态 | `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| `compliant` | `pass` | 否 | 必带（规则锚点） |
| `noncompliant` | `fail` | **是**（退出码 1） | **必带** |
| `not_provided` | `not_applicable` | 否 | 带（条款在，只是没值可比） |
| `skipped` | `not_applicable` | 否 | 带 |
| `unknown` | `not_applicable` | 否 | 带 |

另有两类登记行（`not_applicable` + 无锚点 + 永不阻断）：`ruleset.pending`（2 条待核对）、
`dimension.<维度>`（该维度未评估）。`evidence` 携带 `dimension`/`kind`/`target`/`effect`/
`source_verdict`/`observed`/`expected`（threshold 另有 `basis`/`op`/`limit`），**来源五态与
干基换算说明一条不丢**。

### 3.2 人读（节选）

```text
clauseproof :: petfood-label 0.2.0 :: card-missing.json
[fail] LABEL-003 — 未提供(not_found) :: 宠物饲料标签规定…/第九条 (2026.1)
[not_applicable] NUT-DOG-006 — 未判定（not_provided）：观测=未提供；要求=<= 10.0 % :: 全价宠物食品 犬粮 表1 第4行 (2026.1)
[not_applicable] ruleset.pending — 2 条待核对（status=pending）条目未进入判定路径：NUT-CAT-015、NUT-CAT-016 :: 无锚点
合计 21 条，阻断 1 条（pass=13 fail=1 na=7）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无 `fail` |
| `1` | 有 `fail`（无条件义务缺失 / 理化指标越限 / 宣称支撑不齐） |
| `2` | 输入不合法（未知字段、保证值无法解析、`claims` 非字符串数组、缺 `category`） |
| `3` | 契约违约（条文库缺条款、条文库版本不符、器官不存在） |

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 五态判定（presence/threshold/claim_support） | ✅ | `engine.judge_rule`（逐条对齐） |
| 干物质基准换算 | ✅ | `engine.to_dry_matter`（含水分越界/缺失 → unknown） |
| 适用域画像 + 未评估 | ✅ | `applies_to` / `dimension_assessed` |
| 双重门控（status / clause_status） | ✅ | `Rule.is_effective`（只放行 verified） |
| 规则包与条款锚点 | ✅ | `registry.py` 字面量 + 漂移门 |
| 文本解析（标签 → 档案） | ❌ | 摄取层（I/O + 词表抽取）；器官只收结构化档案 |
| CLI / 批量扫描 / 两轮对账 | ❌ | 产品层（`compare_rounds`/`scan_dir`） |
| 报告 / 图表 / CSV / HTML / SARIF | ❌ | 输出排版 |
| GUI / PyInstaller 打包 / 发布冻结门 | ❌ | 交付面 |

## 5. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层实跑**用例数（ORGAN-PLAYBOOK §3.0） | 旧仓判定层实跑 **X = 207** / 新仓实跑 **N = 315** / **过**（N ≥ X，差 +108） | **过** |
| 2 | README 示例命令 rc 相同 | 旧：`python -m pflc.cli check src/pflc/data/samples/label-demo-ok.txt` → **0**；新：`clauseproof check petfood-label --input samples/petfood-label/card-ok.json --basis …/clauses.json` → **0**。旧：`…label-demo-missing.txt` → **1**；新 `card-missing.json`（同一份样例的等价结构化档案）→ **1** | **过** |
| 3 | 测试文件数 / 测试函数数 | 旧仓判定层 **10 文件 / 196 `def test_`**；本器官 **1 文件 / 228 `def test_`**（判定面详表 + 3 条保留参数化的状态矩阵） | **过**（函数数 228 ≥ 196；实跑 315） |
| 4 | `pip wheel` 后 `data/` 进包 | wheel 内 `clauseproof/packs/petfood-label/data/` **5 条**（`clauses.json` `manifest.json` `ruleset-claim.json` `ruleset-label.json` `ruleset-nutrition.json`） | **过** |

### 6.1 判定层 10 文件处置表（进分母）

| 旧测试文件 | 函数 | 处置 |
|---|---|---|
| `test_engine.py` | 26 | **逐条搬**：五态判定/干基换算/适用域 → §三～§七（45 条规则 × 五态参数化 + 单点实算） |
| `test_rules.py` | 13 | 规则包与门控 → **漂移门 §二**（45 条 × 字段 + 22 条 × 锚点 + 门控） |
| `test_model.py` | 15 | `LabelCard`/`Field` 契约 → §九 输入校验（11 条）+ §三 三态 |
| `test_gates.py` | 45 | **部分搬**：零限值字面量门 → `test_engine_has_no_limit_literals`；规则/条款完整性 → §二。**舍弃**：冻结包 sha256/发布标记门（属交付面，由本仓 M6 门接管） |
| `test_m1_data.py` | 17 | 条款抓取资产门 → **漂移门 §二**（锚点逐条比对冻结规则包）；**舍弃**：原始全文 sha256 台账（资产本体未搬） |
| `test_m2_parse.py` | 29 | **舍弃**：标签文本 → 档案的抽取（词表/低置信/待映射队列），属摄取层 |
| `test_parse.py` | 16 | **舍弃**：同上（解析器） |
| `test_pipeline.py` | 11 | **部分搬**：维度编排 + 未评估 → §七；**舍弃**：`check_file` 分派与批量路径（I/O） |
| `test_report.py` | 17 | **舍弃**：报告/图表渲染（输出排版） |
| `test_verify_frozen.py` | 7 | **舍弃**：冻结规则包重建校验（交付面）；其守卫由 §二 漂移门接管 |

**被剔除的脚手架 6 文件（不进分母）：**

| 旧测试文件 | 函数 | 接管方 / 舍弃理由 |
|---|---|---|
| `test_benchmark.py` | 38 | 基准四套件 runner → 产品层；本器官无基准面，舍弃 |
| `test_cli.py` | 16 | 旧 CLI 参数面 → 本仓唯一入口 `clauseproof.cli` + `tests/test_clauseproof_contract.py` 接管 |
| `test_gui.py` | 9 | GUI → 无 GUI，舍弃 |
| `test_packaging_install.py` | 5 | PyInstaller/安装冒烟 → 本仓 M6 发布门接管 |
| `test_readme_bench_metrics.py` | 6 | README 基准指标对账 → 基准面取消，舍弃 |
| `test_release.py` | 22 | 发布冻结/标记门（九个 OK 标记） → 本仓 M6 发布门接管 |

**为什么旧仓 196 条里有 131 条搬不过来**：`test_m2_parse` 29 + `test_parse` 16 + `test_report` 17 +
`test_gates` 45 + `test_m1_data` 17 + `test_verify_frozen` 7 = **131**，测的是标签文本抽取、报告渲染
与冻结/发布门。可承载的判定面（`test_engine` 26 + `test_rules` 13 + `test_model` 15 +
`test_pipeline` 11 = 65）**已全部搬完**，并把 45 条规则 × 两态/三态、22 条条款锚点
**逐条展开为具名用例**（228 条具名 + 3 条参数化状态矩阵 → 实跑 315）。