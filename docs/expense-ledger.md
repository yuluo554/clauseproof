# 器官 `expense-ledger`

> 条文判定器官 · 版本 `0.1.0` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：规则包快照 `2026-10-15`（`ruleset_version` 3；**11 条数据契约**，全部为
> 参数包/数据契约条目，**不冒充法规文号**）
> 条文库坐标：`2026-10-15`

一句话：**给三平台导出的已解码账单行，判哪些行可用、哪些行报废、哪些消费是
跨平台重复、净支出/净收入是多少、哪些行是周期订阅、哪里涨价了**。

## 1. 输入

```bash
clauseproof check expense-ledger \
  --input samples/expense-ledger/ledger-readme.json \
  --basis src/clauseproof/packs/expense-ledger/data/clauses.json
clauseproof check expense-ledger \
  --input samples/expense-ledger/ledger-clean.json \
  --basis src/clauseproof/packs/expense-ledger/data/clauses.json --json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `files` | ✅ | 文件名 → 已解码文本行对象：`{encoding, lines}`（CSV/TSV 通道）或 `{encoding:"xlsx", table}`（已解包二维数组） |

```json
{
  "files": {
    "wechat-demo-01.csv": {"encoding": "utf-8", "lines": ["微信支付账单明细", "交易时间\t交易类型\t…", "2026-04-03 08:00:00\t…"]},
    "bank-demo-03.xlsx": {"encoding": "xlsx", "table": [["交易日期", "…"], ["2024-10-05", "…"]]}
  }
}
```

> **解析层不进器官**：文件读取、编码探测（BOM → UTF-8 → GB18030 顺序）、
> XLSX zip 容器解包都留在输入层（`SKELETON-SPEC` §2：器官不得做文件 IO）。
> 样例 `lines`/`table` 由来源解析层只读转写冻结样例生成，见 §7。

## 2. 规则

### 2.1 五段确定性管线（全链复算）

| 段 | 检查 | 结论 |
|---|---|---|
| 表头定位 | 前 N 行内找「锚定列命中 ≥ K」的表头行；列映射精确层 → 别名层；必填列（交易时间/金额/对手方）缺失 → 文件级失败 | `fail`（文件） |
| 行三态 | `ok` 入库 / `invalid` 报废（金额空/非数值、时间不可解析、列数不匹配、银行两列同非空）/ `unknown` 入库且显式列出（未登记收支取值、未登记列名） | `fail`（invalid）/ `not_applicable`（unknown） |
| 商户归一化 | 动作序列写死：去空白 → 全半角（映射表）→ 后缀剥离（白名单、剥离后非空才生效）→ 别名表命中（variants 过同一管线后建索引）；未命中原样保留 | （进 record，不单独成账） |
| 跨平台去重 | 金额 Decimal 精确相等 + `\|Δt\| ≤ W` 闭区间 + 归一对手方相等；同方向链式相邻聚类；簇内 ≥2 平台判重复（代表笔 = 时间最早 → 平台次序 → 行号；非代表笔排除出净额）；单平台候选**显式不合并** | `pass`（跨平台簇）/ `not_applicable`（候选簇） |
| 语义识别 | 关键词子串匹配（区分大小写）+ 收支方向组合；priority 升序评估、同优先级按 id 升序；命中多条取首个但全部命中都记录；**「未知」是一等结论**，绝不 fallthrough 为「消费」 | `not_applicable`（未知行） |
| 订阅识别 | 只对语义=消费的支出行判定；同商户链式聚类 → 连续 min_repeats 期落周期容差带（允许漏一期）作种子 → 逐期续链；涨价续链（金额变化 ≥ 阈值、间隔落单期带内）合并两段；涨价只记观测到的变动 | `pass`（订阅/涨价） |

三条口径原样保留：

1. **invalid 行绝不入库**（宁可少一行，不可错位入库）；unknown 行/列入 issues
   不拒行（「未知」是可用的行）；
2. **同平台候选绝不静默合并**（待人工复核；成员照常计入净额）；
3. **未知不混入消费**（主口径不计入净额；未知行合计单列，防「真实支出」虚高）。

### 2.2 数值口径（全部来自规则包快照，器官代码零口径数值）

| 参数 | 值 | 来源 |
|---|---|---|
| `dedup_window_seconds` | 120 | 经验默认（非官方），用户可覆盖 |
| `subscription_min_repeats` | 3 | 经验默认（非官方），用户可覆盖 |
| `subscription_interval_tolerance_days` | 2 | 经验默认（非官方），用户可覆盖 |
| `price_change_min_percent` | 2.0 | 经验默认（非官方），用户可覆盖 |
| `platform_priority` | wechat → alipay → bank | 经验默认（非官方） |
| `header_locate_k` / `max_scan_lines` | 2 / 20 | 经验默认（非官方） |
| `period_table` | monthly 30±2 / quarterly 91±3 / yearly 365±5 | 经验默认（非官方） |

### 2.3 依据关联（单一路径）

| 依据形态 | 锚点 |
|---|---|
| 规则包参数（去重窗口/订阅参数/涨价阈值/表头定位） | `param:*` 数据契约条目 |
| 列名映射 / 别名表 / 关键词规则 / 未知一等结论 | `import:column-map` / `contract:*` 数据契约条目 |

**不冒充法规文号**：去重窗口、订阅周期、涨价阈值都是经验默认值（非官方），
来源仓逐条标注；本器官把这一事实写进条文库条目正文（`basis_ref.quote`）。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| 行级 `invalid` / 文件级失败 | `fail` | **是**（退出码 1） | 列名映射 / 表头定位契约（必带） |
| 行级 `unknown` / 未登记列名 / 语义未知 / 同平台候选簇 | `not_applicable` | 否 | 未知一等结论 / 列名映射契约 |
| 跨平台重复簇 / 订阅成立 / 涨价记录 / 对账完成 | `pass` | 否 | 对应参数条目 |

`evidence` 携带机读判据：行级 `code`（`amount_missing` / `amount_not_numeric` /
`time_unparseable` / `column_count_mismatch` / `amount_ambiguous` /
`unmapped_direction`）、簇成员与代表笔、订阅成员与 gaps、净额分账。

### 3.2 人读（ledger-readme.json，退出码 1）

```text
clauseproof :: expense-ledger 0.1.0 :: ledger-readme.json
[pass] dedup.cluster:D001 — 跨平台重复簇 D001：示例便利店甲 在 2 个平台 12.50 元（代表笔 wechat-demo-01.csv#10，其余已排除出净额） :: 参数包 / 去重时间窗口 (2026-10-15)
[fail] ledger.row.invalid:bank-demo-01.csv#5 — bank-demo-01.csv#5：金额非数值：abc :: 数据契约 / 列名映射 (2026-10-15)
[pass] subscription.item:SUB003 — 订阅 SUB003：示例音乐会员 周期 monthly，5 期 2026-05-10 10:30:00 → 2026-09-10 10:30:00（金额 15.00/18.00） :: 参数包 / 订阅最小重复次数 (2026-10-15)
[pass] subscription.price_change:SUB003:alipay-demo-01.csv#10 — 订阅 SUB003 涨价：alipay-demo-01.csv#10 15.00 元 → 18.00 元（2026-08-10 10:30:00，变化 20.0%） :: 参数包 / 涨价判定阈值 (2026-10-15)
[pass] ledger.result — 对账完成：40 条记录（净支出 6443.91 元 / 净收入 3538.00 元）；跨平台重复排除 4 笔；语义未知 3 行（合计 3860.00 元，未计入净额）；订阅 3 个、干扰行 21 条；文件级失败 0 个、报废行 4 条 :: 数据契约 / 列名映射 (2026-10-15)
合计 16 条，阻断 4 条（pass=8 fail=4 na=4）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无阻断（干净对照组 ledger-clean.json：0 条 invalid / 0 个文件级失败；unknown 与候选簇不阻断） |
| `1` | 有阻断（任一行级 invalid 或文件级失败） |
| `2` | 输入不合法（缺 `files`、`lines` 非字符串数组、`table` 非二维数组、文件缺失/坏 JSON） |
| `3` | 契约违约（条文库版本与规则包快照 `2026-10-15` 不符；条文库缺契约条目 → `BasisMissing` → 3） |

> 漏 `--basis` 时条文库版本为空 → 版本不符 → **退出码 3**，是契约的正确行为。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 行三态 / 金额·时间严格解析 / 列映射 | ✅ | `engine`（逐字移植；问题码机读不变） |
| 商户归一化（四步动作序列） | ✅ | `engine.AliasIndex`（逐字移植） |
| 跨平台去重（三元组 + 链式聚类 + 代表笔） | ✅ | `engine.dedup_ledger`（逐字移植） |
| 语义识别（关键词 + 方向 + 未知一等） | ✅ | `engine.classify_ledger`（逐字移植） |
| 订阅识别（周期锚定 + 漏期补链 + 涨价续链） | ✅ | `engine.detect_subscriptions`（逐字移植） |
| 规则包（manifest/aliases/keywords） | ✅ | `registry` 字面量 + `data/*.json` 逐字节随包 + 漂移门 |
| 编码探测（BOM/UTF-8/GB18030） | ❌ | 输入层（D18 `input` 面；`SKELETON-SPEC` §2 禁止器官文件 IO） |
| XLSX zip 容器解包 | ❌ | 输入层（样例经来源 `xlsx_reader` 只读转写为 `table`） |
| CLI 八子命令 / 退出码编排 / 报告 HTML | ❌ | 产品级交付面（入口只有 `list` / `check`） |
| 基准 B1–B4 / 数据生成器 / 冻结守门 | ❌ | 产品级工具面（真值对账改由本器官测试承载） |
| 数据目录解析（环境变量向上查找） | ❌ | 产品级安装面（器官不读环境变量） |

## 5. 口径差（如实登记）

1. **输入从文件路径变成已解码行**：器官收 `lines`（CSV/TSV）/ `table`（xlsx）；
   编码探测顺序、XLSX 容器解包、文件读取留输入层。坏编码样例
   （`encoding_undetermined`）在 subject 构造时即被剔除，器官记不到该文件级
   问题码——该码的守门由输入层与产品级 CI 接管。
2. **退出码语义对齐产品契约**：旧仓「任一文件级失败 → 2 / 仅行级问题 → 1 /
   干净 → 0」的编排留在产品层；器官按 SKELETON-SPEC §5 收敛为
   `fail → 1`（行级报废与文件级失败同权重阻断）、输入不合法 → 2、契约违约 → 3。
   README 三文件样例旧 rc **1**（行级问题）/ 新 rc **1**、干净对照旧 **0** /
   新 **0**——两例 rc 相同（判据 2 过）。
3. **真值库分账**：来源真值库 `truth.json` 含生成器元数据与覆盖率登记；器官
   测试只读转写**判定面**（行三态 77 行 / 5 簇 / 5 反例 / 语义 67 行 / 5 订阅 /
   涨价 / 干扰行）冻结为 `samples/expense-ledger/truth-rows.json`，生成器面
   （`--check` 位级一致、变异验证、XLSX 重生成）不迁（产品级守门）。
4. **摘要文本由产品层渲染**：旧 `run` 的 stdout 摘要（净额行、语义分布行）在
   器官中收敛为 `ledger.result` 汇总记录的 message 与 evidence（数字逐值一致）。
5. **sha256 审计凭证不迁**：来源 `meta.sources[].sha256` 依赖文件字节，器官不读
   文件；`meta.sources` 保留行计数与编码通道标注（来自 subject 声明）。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 127**（12 文件）/ 新器官实跑 **N = 127** | **过**（127 ≥ 127） |
| 2 | README 示例命令 rc 相同 | 旧 `python -m bill_reconciler run data/samples/wechat-demo-01.csv data/samples/alipay-demo-01.csv data/samples/bank-demo-01.csv --out <tmp>/ledger.json` rc **1**（40 记录 / 净支出 6443.91 / 净收入 3538.00）/ 新 `clauseproof check expense-ledger --input samples/expense-ledger/ledger-readme.json --basis …/data/clauses.json` rc **1**（同 40 记录 / 净额逐值一致 / 3 订阅同成员 / 涨价 15.00→18.00 同 20.0%）；干净对照（2 文件）旧 **0** / 新 **0**（净支出 6287.21 / 净收入 538.00 逐值一致） | **过**（rc 1=1、0=0，同输入逐值一致） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 127 ≥ 127；`def test_` **127** ≥ 旧层 AST **126**（127 用例中含 1 处参数化）；文件数旧 12 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本（git archive HEAD + 新器官文件）`pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（**93 条目**）；`clauseproof/packs/expense-ledger/data/` **4 件**：`aliases.json` 7050 B / `clauses.json` 4067 B / `keywords.json` 2810 B / `params.json` 5300 B（**19227 B**）；解包 `list` = **9 器官**、readme 样例 `check` rc **1** / clean 样例 rc **0** | **过** |

**判据 1 的命令与输出原文**（来源仓只读；`PYTHONDONTWRITEBYTECODE=1` 防写旧仓缓存）：

```bash
cd <来源仓>
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_classify.py tests/test_datadir.py tests/test_dedup.py \
  tests/test_frozen_assets.py tests/test_import.py tests/test_ingest_paths.py \
  tests/test_no_param_literals.py tests/test_normalize.py \
  tests/test_package_metadata.py tests/test_param_caliber_fallback.py \
  tests/test_readme_gate.py tests/test_subscription.py \
  -o addopts="" -q -p no:cacheprovider
# → 127 passed in 0.93s
```

**判据 2 的旧命令与输出原文**（输出全部指向 %TEMP%，来源仓 `git status` 保持 0 行）：

```bash
cd <来源仓>
py -3.12 -m bill_reconciler run data/samples/wechat-demo-01.csv \
  data/samples/alipay-demo-01.csv data/samples/bank-demo-01.csv --out <tmp>/ledger.json
# rc=1；stdout：
#   已处理 3 个文件；记录 40 条；行级问题 4 条；文件级失败 0 个
#   去重：候选簇 4 个（跨平台重复 3 / 同平台候选 1；窗口 120 秒）
#   净额（已排除跨平台重复的非代表笔）：净支出 6443.91 元；净收入 3538.00 元
#   语义分布：报销=1；未知=3；本人转账=2；消费=33；退款=1
#   未知 3 行（合计 3860.00 元；主口径未计入，若全部计入支出上限为 3860.00 元）
#   参数摘要 digest：eab79dbc…（ruleset v3）
#   （stderr：4 条行级问题清单）
# 干净对照（2 文件）：rc=0；净支出 6287.21 元；净收入 538.00 元
```

新命令：

```bash
clauseproof check expense-ledger \
  --input samples/expense-ledger/ledger-readme.json \
  --basis src/clauseproof/packs/expense-ledger/data/clauses.json   # rc 1（同 40 记录 / 同净额）
clauseproof check expense-ledger \
  --input samples/expense-ledger/ledger-clean.json \
  --basis src/clauseproof/packs/expense-ledger/data/clauses.json   # rc 0（同净额 6287.21/538.00）
```

### 6.1 D1 + D18 选文件与逐文件处置（12 文件 / 127 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `tests/test_subscription.py` | 16 | 订阅识别（真值 5 形态 + 边界） | **已迁**（§九） |
| `tests/test_dedup.py` | 13 | 跨平台去重（真值簇 + 边界） | **已迁**（§七） |
| `tests/test_ingest_paths.py` | 20 | 行解析/表头定位/列映射单元 | **部分迁**：表头定位 3、列映射 2、金额/时间 2、文件级路径 4 已迁；编码探测 5 与 XLSX 容器 6 不迁（输入层） |
| `tests/test_import.py` | 12 | 三态矩阵真值对账 | **已迁**（§五：77 行真值对齐 + 问题码 + 审计字段 + 确定性） |
| `tests/test_normalize.py` | 10 | 归一化动作序列 | **已迁**（§六） |
| `tests/test_classify.py` | 9 | 语义识别（真值 67 行 + 干扰例） | **已迁**（§八） |
| `tests/test_frozen_assets.py` | 24 | 数据生成器/冻结守门 | **部分迁**：规则包结构 3、真值引用/形态 6 已迁（改由漂移门 + truth-rows 对账承载）；生成器 `--check`/变异验证/XLSX 重生成 15 不迁（产品级守门） |
| `tests/test_datadir.py` | 6 | 数据目录解析（环境变量） | 不迁（器官不读环境变量；产品级安装面） |
| `tests/test_param_caliber_fallback.py` | 5 | 参数行为穿透 | **部分迁**：min_repeats / dedup_window 行为穿透 2 已迁；`header_locate_k` 穿透经表头定位单元覆盖；残余面登记 2 不迁（静态门禁属产品级工具面） |
| `tests/test_no_param_literals.py` | 4 | 零参数字面量静态门 | 不迁（源码 AST 门由产品级 `test_m*` 与 CI 接管；器官由「零口径数值」评审纪律约束） |
| `tests/test_readme_gate.py` | 5 | README/安装面交叉守门 | 不迁（产品级门 `test_entry_surface.py` / `test_readme_gate.py` 接管） |
| `tests/test_package_metadata.py` | 2 | 打包元数据 | 不迁（打包面，判据 4 与 CI 接管） |
| **合计** | **127** | — | 已迁 6 / 部分迁 3 / 不迁 3 |

D1 + D18 剔除（不计入 X，10 文件）：

| 文件 | 命中词 | 处置 |
|---|---|---|
| `tests/test_bench.py` | `bench` | 基准编排 |
| `tests/test_bench_b1.py` | `bench` | B1 导入基准 |
| `tests/test_cli_basics.py` | `cli` | CLI 参数面 |
| `tests/test_cli_stubs.py` | `cli` | CLI 占位 |
| `tests/test_encoding_guard.py` | `guard` | stdout 编码守卫 |
| `tests/test_import_cli.py` | `cli` | import 子命令面 |
| `tests/test_pipeline_cli.py` | `cli` | run/report 子命令面 |
| `tests/test_release_zip.py` | `release` | 发布 zip 确定性 |
| `tests/test_report.py` | D18 `report` | HTML 报告 |
| `tests/test_selftest.py` | `selftest` | 自检命令 |

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/params.json` | 来源仓 `data/rules/manifest.json` | **逐字节相同**（sha256 `a41cbf59…`），wheel 进包 |
| `data/aliases.json` | 来源仓 `data/rules/aliases.json` | **逐字节相同**（sha256 `d2a3e6bb…`），wheel 进包 |
| `data/keywords.json` | 来源仓 `data/rules/keywords.json` | **逐字节相同**（sha256 `4c447e57…`），wheel 进包 |
| `data/clauses.json` | 11 条数据契约（由 `registry.clause_specs/clause_text` 生成） | 版本 `2026-10-15`；参数值/词面与 registry 同源 |
| `samples/expense-ledger/ledger-*.json` | 来源仓冻结样例经来源解析层（`detect.decode_bytes` / `xlsx_reader.read_xlsx`）**只读转写** | 判据 2 的新侧样例：readme 3 文件（rc 1）/ clean 2 文件（rc 0）/ demo 11 文件（真值对账用） |
| `samples/expense-ledger/truth-rows.json` | 来源仓 `data/truth/truth.json` 判定面**只读转写** | 行三态 77 行 / 5 簇 / 5 反例 / 语义 67 行 / 5 订阅 / 涨价 / 干扰行（生成器元数据不迁） |
