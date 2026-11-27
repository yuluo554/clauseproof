# 器官 `invoice-ledger`

> 条文判定器官 · 版本 `0.1.0` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：三份法规知识库快照（`data/knowledge-*.json`，与来源仓逐字节同 sha256）+ 4 条数据契约
> 条文库坐标 = 来源知识库核对日期 `2026-10-06`；条文库 20 条（16 条法规条目 + 4 条数据契约）

一句话：**给一批已解析的发票参数卡 + 时间基准，判重复报销（精确/联合键/模糊）、连号拆分、
票面算术、大写金额与时间逻辑异常，逐条挂法规条款锚点。**

## 1. 输入

```bash
clauseproof check invoice-ledger \
  --input samples/invoice-ledger/ledger-readme.json \
  --basis src/clauseproof/packs/invoice-ledger/data/clauses.json
clauseproof check invoice-ledger \
  --input samples/invoice-ledger/ledger-clean.json \
  --basis src/clauseproof/packs/invoice-ledger/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `cards` | ✅ | 发票参数卡数组（**已解析**；空数组 = 输入不合法 → 退出码 2） |
| `anchors` | ✅ | 时间基准：`default`（ISO 日期，必填）+ `batches`（批次 → 报销基准日）。**器官不读时钟** |
| `params` | — | 判定参数（见 §2.9）；未知键 → 输入不合法 |
| `existing_numbers` | — | 台账既有发票号码（旧 SQLite 台账的持久判重输入改由输入提供） |

卡字段（与来源 `InvoiceCard` 同构）：`invoice_number` / `invoice_type` / `issue_date`
（主键三要素，任一缺失 → 退出码 2）；`buyer_*` / `seller_*` / `items` / `amount` /
`tax_amount` / `total_with_tax` / `total_with_tax_cn` / `remark` / `batch_id` /
`confidence` / `field_flags` / `evidence`。

```json
{
  "ledger_id": "readme-demo-3-batches",
  "anchors": {"default": "2026-09-30",
              "batches": {"batch_01": "2026-07-15", "batch_02": "2026-08-15"}},
  "params": {"dup_date_window_days": 1, "time_n_period": 3},
  "existing_numbers": [],
  "cards": [{"invoice_number": "25910000000000123456", "invoice_type": "数电普票",
             "issue_date": "2026-06-01", "seller_tax_id": "…", "seller_name": "…",
             "amount": "1000.00", "tax_amount": "130.00", "total_with_tax": "1130.00",
             "total_with_tax_cn": "壹仟壹佰叁拾元整", "batch_id": "batch_01"}]
}
```

> **文件读取只在输入面**：XML / PDF / OFD 解析、编码探测、批次扫描（一级子目录名）、
> SQLite 入库都在产品层；器官只收内存卡。时间基准全部来自 `anchors`——来源的
> 「导入时刻」兜底留输入层，因此同一输入在任何机器上逐字节可复现。

### 1.1 与 `expense-ledger`（#6）的边界

| 维度 | `invoice-ledger`（本器官） | `expense-ledger`（#6） |
|---|---|---|
| 对象 | **发票票面 + 发票号码**（数电票 20 位号码） | **账单流水 + 真实支出**（支付宝/微信/银行 CSV） |
| 判定 | 精确/联合键/模糊重复、连号拆分、价税合计、大写金额、开票/报销时间逻辑 | 行三态、商户归一化、跨平台去重、语义识别、订阅识别 |
| 依据 | 发票管理办法（764 号令）+ 11 号公告原文 | 规则包参数条目（经验默认非官方） |

两者 **slug / 规则代码（`invoice.*` vs `expense.*`）/ 测试文件零复用**；金额/日期
文本解析各自实现，不共享模块。

## 2. 规则

### 2.1 执行顺序与门控

规则族按注册顺序执行：`duplicate.exact → duplicate.joint → duplicate.fuzzy →
series → arithmetic.total → arithmetic.cn → time.future → time.stale`。
`duplicate.fuzzy` 门控互斥：排除已命中 `duplicate.exact` / `duplicate.joint` 的号码
组合（同号副本不参与模糊配对，与来源 `plan/04 §3.1` 一致）。

### 2.2 `duplicate.exact`（R-DUP-01）

同一 `invoice_number` 在本次卡集合出现 ≥2 次，或号码已在 `existing_numbers` →
`error`（`fail`，阻断）。证据：`occurrences` / `batches` / `pre_existing_in_ledger`。

### 2.3 `duplicate.joint`（R-DUP-02）

同号 + 同价税合计 + 同开票日期、**批次不同**、且两卡语义字段不全等（纯复制件由
R-DUP-01 完整覆盖）→ `error`。证据：逐对 `batches` / `total_with_tax` / `issue_date`。

### 2.4 `duplicate.fuzzy`（R-DUP-03）

同 `seller_tax_id`、`|日期差| ≤ dup_date_window_days`（默认 1）、
`|价税合计差| ≤ dup_amount_tol`（默认 0.00）、不同号码 → `suspicious`。
门控互斥见 §2.1。

### 2.5 `series`（R-SEQ-01）

同 `seller_tax_id` 分组；号码末 `seq_suffix_len` 位（默认 8）为纯数字、按数值连续
≥ `seq_min_len` 张（默认 3）、日期跨度 ≤ `seq_date_window_days`（默认 7）、
且前缀一致 → `suspicious`。前缀不同只警示不产出记录（来源 M3 定稿，防误报）。

### 2.6 `arithmetic.total`（R-ARITH-01）

- 子检查 1（明细聚合）：`Σ明细金额 = amount` 且 `Σ明细税额 = tax_amount`（容差内）；
  仅当每行明细的金额/税额都可数值化才复核；部分行缺失时不硬判；
- 子检查 2：`amount + tax_amount = total_with_tax`（容差内）；
- 任一不符 → `error`；金额字段不可解析 → `review`（待人工确认，不硬判）。

### 2.7 `arithmetic.cn`（R-ARITH-02）

`total_with_tax_cn ≡ encode_amount(total_with_tax)`（人民币小写 → 大写，纯 stdlib
财务惯例：组单位挂组尾、中间零合并、角分补零）。不符 → `error`；
`total_with_tax` 不可解析 → `review`。

### 2.8 `time.future`（R-TIME-01）/ `time.stale`（R-TIME-02）

- `time.future`：`issue_date > anchors.batches[batch_id]`（无映射回退
  `anchors.default`）→ `error`；
- `time.stale`：`(anchor.year*12+anchor.month) − (issue.year*12+issue.month) >
  time_n_period`（默认 3）→ `review`。**仅追溯方向**——未来票只报
  `time.future`，不双报（来源方向定稿）。

### 2.9 判定参数（全部用户输入，零政策数值）

| 参数 | 默认 | 说明 |
|---|---:|---|
| `arith_tolerance` | `"0.01"` | 票面算术容差（Decimal 文本） |
| `dup_date_window_days` | `1` | 模糊重复日期窗口（天） |
| `dup_amount_tol` | `"0.00"` | 模糊重复金额容差 |
| `seq_suffix_len` | `8` | 连号判定取号码末 N 位 |
| `seq_min_len` | `3` | 连号簇最少张数 |
| `seq_date_window_days` | `7` | 连号簇日期跨度（天） |
| `time_n_period` | `3` | 跨期阈值（月） |

未知参数键 → `ValueError` → 退出码 2（防拼写漂移静默取默认）。

## 3. 输出

### 3.1 账本映射

| 来源级别 / 结论 | `verdict` | 阻断 | 依据锚点 |
|---|---|---|---|
| `error`（确认异常） | `fail` | **是**（退出码 1） | 该规则族法规条款 |
| `suspicious`（疑似） | `not_applicable` | 否 | 该规则族法规条款；`evidence.level` 保留 `suspicious` |
| `review`（待人工确认） | `not_applicable` | 否 | 同上；`evidence.check`/`months_behind` 留证 |
| 整族未命中 | `pass` | 否 | 该规则族法规条款 |
| 整族因缺字段未检查 | `not_applicable` | 否 | 同上；`evidence.skipped` 记卡数 |

**疑似 ≠ 确认**：只有 `error` 阻断；疑似与待人工确认记 `not_applicable` 并保留来源
级别（与 `cost-card` / `income-tax` 的「预警不阻断」口径一致）。

**输入不可用**（卡缺主键、`cards` 为空、`anchors` 缺失/非法、参数非法/未知、
`existing_numbers` 非法）→ `ValueError` → 退出码 2（与来源「用法与输入错误 = 2」
对齐）；条文库版本不符 / 条款缺失见 §3.3。

### 3.2 人读（`ledger-readme.json`，退出码 1，节选）

```text
clauseproof :: invoice-ledger 0.1.0 :: ledger-readme.json
[fail] invoice.arithmetic.cn:14410000000010000164 — 大写金额与小写价税合计不符：大写 陆万贰仟叁佰伍拾捌元肆角玖分，按小写 62353.49 应为 陆万贰仟叁佰伍拾叁元肆角玖分 :: 发票管理办法（2023 修订） / 第二十一条第一款 (2026-10-06)
[fail] invoice.arithmetic.total:08100000000010000157:total — 票面算术不符：金额 7896.53 + 税额 473.79 ≠ 价税合计 8380.32 :: 发票管理办法（2023 修订） / 第二十一条第一款 (2026-10-06)
[fail] invoice.duplicate.exact:14410000000010000106 — 发票号码重复：本次导入中出现 2 次，疑似重复报销 :: 11 号公告（数电票推广应用） / 第一条 (2026-10-06)
[not_applicable] invoice.duplicate.fuzzy:26910000000010000116|26910000000010000120 — 同销售方 兰台档案服务股份有限公司 在 1 天内出现价税合计相同的不同发票，疑似近似重复报销 :: 发票管理办法（2023 修订） / 第二十一条第二款 (2026-10-06)
[not_applicable] invoice.series:25910000000010000121|25910000000010000122|25910000000010000123|25910000000010000124|25910000000010000125 — 同销售方 兰台档案服务股份有限公司 的 5 张发票号码连续（日期跨度 7 天），疑似连号拆分报销 :: 11 号公告（数电票推广应用） / 第四条 (2026-10-06)
[fail] invoice.time.future:08200000000010000177 — 开票日期 2027-10-12 晚于批次 batch_01 报销基准日 2026-07-15，时间逻辑异常 :: 发票管理办法（2023 修订） / 第二十一条第一款 (2026-10-06)
合计 13 条，阻断 9 条（pass=0 fail=9 na=4）
```

与来源 `check data/invoices --anchor-manifest …` 的 **13 条异常逐条同态**：
error 9 / suspicious 2 / review 2；本器官 fail 9 / na 4（疑似与待确认合并记 NA，
`evidence.level` 区分）。干净样例 `ledger-clean.json`：8 条 `pass`、退出码 0。

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无阻断（全部规则 pass 或 NA；疑似/待人工不阻断） |
| `1` | 存在 `fail`（`error` 级命中） |
| `2` | 输入不合法（卡缺主键 / cards 为空 / anchors 非法 / 参数非法 / 条文库缺条款） |
| `3` | 契约违约（条文库版本 ≠ `2026-10-06`；条文库自相矛盾） |

> **漏 `--basis`** → 条文库版本为空 → 版本不符 → **退出码 3**，是契约正确行为。
> 条文库缺某条款 → `BasisMissing` 在本产品内核映射 **退出码 2**
> （`ORG-PLAYBOOK` §4 的口径是 3；未改内核，与 `docs/cost-card.md` §3.3 同）。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 八规则判定语义 | ✅ | 精确/联合键/模糊重复、连号拆分、票面算术、大写金额、时间逻辑逐条迁移 |
| 中文大写金额转换 | ✅ | `cn_amount`（纯 stdlib；17 个已知值逐条测试） |
| 金额/日期 Decimal 与 ISO 解析 | ✅ | 判定层自持；浮点零参与 |
| 发票卡中间表示 | ✅ | `model`（主键三要素校验 + 未知键忽略 + 往返一致） |
| 三份法规知识库快照 | ✅ | `data/knowledge-*.json` **逐字节同 sha256** 随包 + 漂移门 |
| 条文库 | ✅ | 16 条法规条目 + 4 条数据契约；不编造文号 |
| XML / PDF / OFD 解析 | ❌ | 输入层；器官只收已解析卡（编码/依赖探测留产品层） |
| SQLite 台账 / 批次登记 / 幂等入库 | ❌ | 存储交付面；持久判重改由 `existing_numbers` 输入 |
| GUI（PySide6）/ Excel 导出 / 技术报告 | ❌ | 交付面；入口只有 `list` / `check` |
| 合成数据生成器 / 基准 runner / 发布脱敏扫描 | ❌ | 产品级工具面；sha256 + schema 门接管数据面 |
| `demo` / `parse` / `generate` / `benchmark` / `export` / `app` 子命令 | ❌ | 产品级命令面（新入口只有 `list` / `check`） |

## 5. 口径差（如实登记）

1. **输入从目录变成内存卡数组**：XML/PDF/OFD 解析、编码探测、批次扫描（一级子目录名）
   全部留输入层；器官零文件 IO。
2. **时间基准必须显式输入**：来源 `check` 缺省 `anchor = 导入时刻`（读时钟）；器官
   `anchors.default` 必填、批次可覆盖。语义未变，但同一输入在任何日期跑结果一致。
3. **退出码 0 → 1（接受为口径差，D10）**：来源 `check` 的 rc 只反映流水线失败
   （有异常也返回 0）；本器官按产品契约 `fail → 1`。**不加兼容 rc**，不改内核退出码表。
   见 §6.2 实测。
4. **级别映射**：`error → fail`（阻断）；`suspicious` / `review → not_applicable`
   （疑似/待人工 ≠ 确认）。来源三级原值保留在 `evidence.level`，不丢信息。
5. **疑似/待确认也挂条款锚点**：账本允许 `not_applicable` 带锚点；本器官统一挂该规则族
   法规条款，避免「无锚点下判定」。
6. **整族汇总记录**：整族未命中 → 一条 `pass`；整族因缺字段未检查 → 一条
   `not_applicable` 并记 `skipped` 卡数。来源对缺字段**静默跳过**，本器官显式出账。
7. **持久判重输入化**：来源用 SQLite `existing_numbers()` 提供台账既有号码；器官由
   `subject.existing_numbers` 提供——判定语义不变，存储留产品层。
8. **未知参数即输入不合法**：来源 `params` 只在 GUI 设置页出现、未知键被忽略；
   器官拒绝未知键（防拼写漂移静默取默认）。
9. **知识库为快照**：三份 JSON 逐字节随包（`manifest.json` 记 sha256/bytes）；
   `clauses.json` 由条目并集 + 4 条数据契约生成。条文库版本 = 核对日期 `2026-10-06`。
10. **弱关联规则如实披露**：`series` / `time.future` / `time.stale` 的 evidence 带
    `heuristic_note`（「工程口径：法规无直接禁止条款；条号仅挂同类义务上位条款」），
    与来源 `format_basis` 的工程口径标记同义。
11. **与 #6 `expense-ledger` 零复用**：对象/判定/依据全不同（§1.1）；slug、规则代码、
    测试文件均不复用。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 137**（11 文件）/ 新器官实跑 **N = 140** | **过**（140 ≥ 137） |
| 2 | README 示例命令 rc 相同 | 旧 `check data/invoices --db <tmp>/ledger.db --anchor-manifest data/ground_truth/manifest.json` rc **0**（13 条：error 9 / suspicious 2 / review 2）/ 新 `check invoice-ledger --input samples/invoice-ledger/ledger-readme.json --basis …/clauses.json` rc **1**（13 条：fail 9 / na 4，逐条同态） | **口径差（接受，D10）**：旧 rc 只反映流水线失败；新按 `fail → 1`。干净对照旧 **0**（0 条）/ 新 **0**（8 条 pass） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 140 ≥ 137；AST `test_` 函数 **140** ≥ 旧层 **110**；文件数旧 11 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（**191 条目 / 644755 B**）；`clauseproof/packs/invoice-ledger/data/` **5 件 / 26082 B**；解包 `list` = **14 器官**、干净样例 rc **0** | **过** |

**判据 1 的命令与输出原文**（来源仓只读，`PYTHONDONTWRITEBYTECODE=1`）：

```bash
cd <来源仓>
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_app.py tests/test_baseline_detection.py tests/test_ci_workflow.py \
  tests/test_cn_amount.py tests/test_extras.py tests/test_knowledge.py \
  tests/test_ledger.py tests/test_models.py tests/test_package.py \
  tests/test_parsing.py tests/test_rules.py \
  -o addopts="" -q -p no:cacheprovider
# → 137 passed in 4.04s
```

逐文件 passed：app 10 / baseline_detection 4 / ci_workflow 3 / cn_amount 19 /
extras 8 / knowledge 12 / ledger 6 / models 4 / package 3 / parsing 27 / rules 41 = **137**；
旧层 AST `test_` 函数 = 10+4+3+3+8+12+6+4+3+16+41 = **110**。

> **D1 机械口径说明**：`test_parsing.py`（27）、`test_app.py`（10）、
> `test_ci_workflow.py`（3）、`test_extras.py`（8）、`test_package.py`（3）的名字
> **不含** D1/D18 排除词（`parsing` 不含字面 `parse`；`package` 不含 `packaging`；
> `app` / `ci_workflow` / `extras` 不在词表），故**机械计入分母**。本器官不按域
> 手剔（#10 审计 §3.1 的纠正口径），其判定值由 §6.1 逐文件处置。
> `conftest.py` 非测试文件，不计。

### 6.1 D1 + D18 选文件与逐文件处置（11 文件 / 137 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `test_rules.py` | 41 | 引擎 + 八规则语义 | **已迁**（§二 全部规则；测试 §五–§十二） |
| `test_parsing.py` | 27 | XML/PDF 解析 | **不迁**（输入层；器官只收已解析卡）。D1 机械计入 X |
| `test_cn_amount.py` | 19 | 中文大写金额 | **已迁**（§2.7；测试 §二 逐值 17 + 舍入 + 非法） |
| `test_knowledge.py` | 12 | 知识库结构 / 依据一致性 | **部分迁**：结构/逐字 quote/弱关联 note/强关联无 note 由 §一 + §十四 接管；`next_review` 逾期警告读时钟，不迁 |
| `test_app.py` | 10 | Qt GUI 标签页/对话框 | **不迁**（GUI 交付面；入口只有 `list`/`check`）。D1 机械计入 X |
| `test_extras.py` | 8 | 可选依赖体检 | **不迁**（extras 交付面）。D1 机械计入 X |
| `test_ledger.py` | 6 | SQLite 台账 | **不迁**（存储交付面）；持久判重由 `existing_numbers` 输入契约接管（测试 §四/§十三） |
| `test_baseline_detection.py` | 4 | 60 文件真值对拍 | **部分迁**：13 条 finding 形态/计数在端到端用例（§十三）；60 文件解析对账不迁（解析/基准面） |
| `test_ci_workflow.py` | 3 | CI workflow 门 | **不迁**（产品级 CI 门）。D1 机械计入 X |
| `test_models.py` | 4 | 发票卡序列化 | **已迁**（§三） |
| `test_package.py` | 3 | 包级冒烟 | **不迁**（产品级打包门；判据 4 wheel 解包接管）。D1 机械计入 X |
| **合计** | **137** | — | 已迁 3 / 部分迁 2 / 不迁 6 |

**D1 + D18 剔除（不计入 X，8 文件 / 62 passed + 2 skipped）**：

| 来源测试文件 | passed | D1 词 | 去向 |
|---|---:|---|---|
| `test_generator.py` | 17 (+2 skip) | `generat` | 合成数据生成器（产品级工具面；不入器官） |
| `test_cli.py` | 16 | `cli` | 旧六子命令入口（新入口只有 `list`/`check`） |
| `test_benchmark.py` | 6 | `bench` | 内置评测基准（产品级基准面） |
| `test_packaging.py` | 6 | `packaging` | PyInstaller 双 exe 打包（交付面） |
| `test_doc_counts.py` | 5 | `docs?_` | README/文档计数守门（产品级文档门） |
| `test_release_scan.py` | 5 | `release` | 发布脱敏扫描（产品级发布门） |
| `test_export.py` | 4 | `export` | Excel 双 sheet 导出（交付面） |
| `test_version_single_source.py` | 3 | `version` | 版本单一来源（产品级发行元数据门） |

### 6.2 判据 2 对撞（旧命令 vs 新入口）

| 场景 | 旧命令 → rc | 新命令 → rc | 结论 |
|---|---|---|---|
| README 示例（3 批次 / 57 张卡） | `py -m invoice_ledger_checker check data/invoices --db <tmp>/ledger.db --anchor-manifest data/ground_truth/manifest.json` → **0**（13 条：error 9 / suspicious 2 / review 2） | `check invoice-ledger --input samples/invoice-ledger/ledger-readme.json --basis …/clauses.json` → **1**（13 条：fail 9 / na 4） | **口径差（接受，D10）**：逐条同态；旧 rc 只反映流水线失败 |
| 干净对照 | 单张基线 XML + 临时 manifest（anchor = 开票日）→ **0**（0 条） | `check invoice-ledger --input samples/invoice-ledger/ledger-clean.json --basis …` → **0**（8 条 pass） | 过（0 = 0） |
| 漏 `--basis` | 旧无概念 | `check invoice-ledger --input …/ledger-clean.json` → **3** | 契约正确行为（条文库版本不符） |
| 卡缺主键 | 旧解析层拒收文件 → 2 | subject 卡删 `invoice_number` → **2** | 过 |
| 空卡集合 | 旧「目录内无可解析文件」→ 2 | subject `cards=[]` → **2** | 过 |

> 旧侧输入与临时台账/清单均在 `%TEMP%` 副本内，来源仓全程 `git status --porcelain` = 0 行。

### 6.3 判据 4 的进包清单（`%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation`）

wheel：`clauseproof-0.0.0-py3-none-any.whl`（644755 B，**191 条目**）；
`clauseproof/packs/invoice-ledger/data/` **5 件 / 26082 B**：

| 文件 | bytes | 来源 |
|---|---:|---|
| `clauses.json` | 8784 | 16 条法规条目 + 4 条数据契约（由随包知识库生成） |
| `knowledge-11.json` | 6708 | 来源 `data/knowledge/11号公告.json`，**逐字节相同** |
| `knowledge-56.json` | 5947 | 来源 `data/knowledge/56号令.json`，**逐字节相同** |
| `knowledge-764.json` | 3525 | 来源 `data/knowledge/764号令.json`，**逐字节相同** |
| `manifest.json` | 1118 | 逐文件 sha256 / bytes / 条文数 / 规则→条款映射登记 |

解包后 `clauseproof list` = **14 器官**；`check invoice-ledger` 干净样例 rc **0**。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/knowledge-11.json` / `-56` / `-764` | 来源仓 `data/knowledge/` | **逐字节相同**（manifest 登记 sha256） |
| `data/clauses.json` | 三份知识库条目并集 + 4 条数据契约 | 版本 `2026-10-06` |
| `data/manifest.json` | 本器官装配产物 | 漂移门：bytes + sha256 + clause_count + rule_clauses |
| `samples/invoice-ledger/ledger-readme.json` | 来源 README 示例目录（57 张非 OFD 卡，批次锚点取自来源 manifest） | 判据 2 主样例（rc 1，13 条同态） |
| `samples/invoice-ledger/ledger-clean.json` | 手写干净对照（3 张卡） | 干净对照（rc 0，8 条 pass） |

> 样例全部为合成/演示数据，不含真实主体；卡内金额、号码、公司名均为虚构。