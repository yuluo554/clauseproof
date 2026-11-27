# 器官 `two-tickets`

> 条文判定器官 · 版本 `2026-10-02` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：**国能发安全〔2023〕22号**《防止电力生产事故的二十五项重点要求（2023 版）》
> + **Q/GDW 1799.1-2013 / 1799.2-2013**（电力安全工作规程：变电 / 线路部分）
> + **GB 26859-2011** / **GB 26860-2011** / **DL/T 408-2023**（登记卡在册，未直接挂规则）
> 三份规则库与来源**逐字节同 sha256** 随包
> 条文库 55 条：39 条规则条款（**9 已核对 / 30 待核对**）+ 6 份依据文件 + 10 条数据契约
> 条文库坐标 = 规则库核对日期 `2026-10-02`

一句话：**给一张已解析的票面参数卡，按 7 票种 × 7 类 check_type 逐条判定，输出
「合规 / 不合规 / 待人工确认」三级结论，每条结论挂规范条款与复核锚；
依据待核对的规则不下确定性「不合规」（降级待人工确认）。**

## 1. 输入

```bash
clauseproof check two-tickets \
  --input samples/two-tickets/ticket-operating-readme.json \
  --basis src/clauseproof/packs/two-tickets/data/clauses.json
clauseproof check two-tickets \
  --input samples/two-tickets/ticket-signature-gap.json \
  --basis src/clauseproof/packs/two-tickets/data/clauses.json
clauseproof check two-tickets \
  --input samples/two-tickets/ticket-time-order-pending.json \
  --basis src/clauseproof/packs/two-tickets/data/clauses.json
clauseproof check two-tickets \
  --input samples/two-tickets/ticket-five-prevention.json \
  --basis src/clauseproof/packs/two-tickets/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `case_id` | ✅ | 一次判定运行的稳定标识（输入必填字段） |
| `ticket.ticket_type` | ✅ | 7 票种之一：`operating` / `line_operating` / `work_first` / `work_second` / `line_work_first` / `line_work_second` / `emergency_repair` |
| `ticket.fields` | ✅ | 字段 → 值；值可为标量，或 `{"value", "confidence", "evidence": {"region","quote"}}` |
| `ticket.operation_sequence` | — | 操作项数组：`{"no": 1, "action": "…"}`（也接受纯字符串，自动编号） |
| `ticket.safety_measures` | — | 安全措施条目：`{"no": 1, "text": "…"}`（也接受纯字符串） |

```json
{
  "case_id": "two-tickets-readme",
  "ticket": {
    "ticket_type": "operating",
    "fields": {
      "ticket_no": "CZ-2026-0001",
      "task": "将110kV东湖线111断路器由运行位置摇至试验位置（虚构演示数据）",
      "start_time": "2026-10-15T08:30",
      "end_time": "2026-10-15T09:40",
      "dispatcher": "王模拟（虚构）",
      "guardian": "张测试（虚构）",
      "operator": "李演示（虚构）"
    },
    "operation_sequence": [
      {"no": 1, "action": "检查110kV东湖线111断路器确在运行位置"},
      {"no": 2, "action": "断开110kV东湖线111断路器"}
    ],
    "safety_measures": []
  }
}
```

> **票面解析留在输入层**：7 票种文本解析、OCR、编码清洗、LLM 兜底抽取、
> 证据摘录与字段置信度都在产品侧完成；器官只收**已解析参数卡**。
> 票种未知 / 卡结构非法 / 字段对象含未知键 → 退出码 2。

### 1.1 与既有器官的边界

| 维度 | `two-tickets`（本器官） | 既有器官 |
|---|---|---|
| 对象 | **电力两票**：工作票 / 操作票 / 抢修单的形式与内涵合规 | 无重叠器官（医疗广告 / 食品 / 环保 / 个税 / 发票 / 劳动 / 职业健康 / 专利各司其职） |
| 依据 | 电力安全规范（国能发安全〔2023〕22号 + Q/GDW 1799 系列 + GB 26859/26860） | 各自法规/标准/参数包 |
| 输入 | 票面参数卡（字段 + 操作序列 + 安全措施） | 各自 subject |

slug / 规则 id（`R-*`）/ 条款 id 前缀（`ticket:*`）/ 测试文件与既有 19 个器官零复用。

## 2. 规则

### 2.1 规则库坐标（39 条 / 7 票种 / 7 类 check_type）

| check_type | 条数 | 语义 |
|---|---:|---|
| `time_order` | 19 | 时间先后（`interval`）与许可落在计划区间（`in_window`） |
| `required_field` | 7 | 票面必填项完整性（缺字段/空串 → 缺失） |
| `process_signature` | 5 | 签字链缺环（签发 / 许可 / 终结环节人员） |
| `measure_coverage` | 2 | 技术措施四要素覆盖（停电/验电/接地/标示牌遮栏） |
| `ticket_type_match` | 2 | 第二种工作票不得含需停电作业表述 |
| `five_prevention` | 2 | 五防形式化初查（三类可形式化口径） |
| `consistency` | 2 | 设备双重名称 × 电压等级互证 |

### 2.2 三级结论与依据闸（核心纪律）

| 来源结论 | 触发 | 账本 |
|---|---|---|
| `合规` | 确定性规则通过 | `pass` |
| `不合规` | 确定性规则未通过（**仅 `已核对` 依据**） | `fail`（阻断 → 退出码 1） |
| `待人工确认` | 字段缺失 / 值非法 / 操作序列为空 / **依据待核对降级** | `not_applicable`（非结论） |

**依据闸**（窄闸，逐条保留）：`basis.status != 已核对` 的规则，其产出的「不合规」
一律降级为「待人工确认」；「合规」与既有「待人工确认」不动。闸门在 `check()` **之后**
执行——若写成「跳过规则不执行」，`required_field` 的缺失检测会整块消失。

### 2.3 条款 pending 如实登记（30 / 39 = 77%）

本器官随包规则库中 **30 条依据待核对**——它们的「不合规」结论一律降级。
条款书架的对应条目以 **`【待核对】`** 前缀登记；账本 `ticket.pending` 每次运行
列出条数与依据文件分布，`evidence.rule_ids` 给出全部 30 条 id。

| 规则 id | check_type | 依据 | 条款 |
|---|---|---|---|
| `R-W2-007` | ticket_type_match | Q/GDW 1799.1-2013 | 第二种工作票适用范围（不需停电的工作） |
| `R-LW2-007` | ticket_type_match | Q/GDW 1799.2-2013 | 电力线路第二种工作票适用范围（不需停电的工作） |
| `R-OP-004` | consistency | Q/GDW 1799.1-2013 | 设备双重名称标注要求 |
| `R-LOP-004` | consistency | Q/GDW 1799.2-2013 | 线路名称及杆号（双重名称）标注要求 |
| `R-OP-001` | required_field | Q/GDW 1799.1-2013 | 附录 倒闸操作票格式（票样字段重构） |
| `R-LOP-001` | required_field | Q/GDW 1799.2-2013 | 附录 电力线路倒闸操作票格式（票样字段重构） |
| `R-W1-001` | required_field | Q/GDW 1799.1-2013 | 附录 第一种工作票格式（票样字段重构） |
| `R-W2-001` | required_field | Q/GDW 1799.1-2013 | 附录 第二种工作票格式（票样字段重构） |
| `R-LW1-001` | required_field | Q/GDW 1799.2-2013 | 附录 电力线路第一种工作票格式（票样字段重构） |
| `R-LW2-001` | required_field | Q/GDW 1799.2-2013 | 附录 电力线路第二种工作票格式（票样字段重构） |
| `R-ER-001` | required_field | Q/GDW 1799.1-2013 | 附录 事故紧急抢修单格式（票样字段重构） |
| `R-OP-002` | time_order | Q/GDW 1799.1-2013 | 倒闸操作票时间栏目（操作开始/结束时间先后逻辑） |
| `R-LOP-002` | time_order | Q/GDW 1799.2-2013 | 电力线路倒闸操作票时间栏目（操作开始/结束时间先后逻辑） |
| `R-W1-002` | time_order | Q/GDW 1799.1-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-W2-002` | time_order | Q/GDW 1799.1-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-LW1-002` | time_order | Q/GDW 1799.2-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-LW2-002` | time_order | Q/GDW 1799.2-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-W1-004` | time_order | Q/GDW 1799.1-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-W2-004` | time_order | Q/GDW 1799.1-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-LW1-004` | time_order | Q/GDW 1799.2-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-LW2-004` | time_order | Q/GDW 1799.2-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-W1-005` | time_order | Q/GDW 1799.1-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-W2-005` | time_order | Q/GDW 1799.1-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-LW1-005` | time_order | Q/GDW 1799.2-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-LW2-005` | time_order | Q/GDW 1799.2-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-W1-006` | time_order | Q/GDW 1799.1-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-W2-006` | time_order | Q/GDW 1799.1-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-LW1-006` | time_order | Q/GDW 1799.2-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-LW2-006` | time_order | Q/GDW 1799.2-2013 | 计划工作时间/许可开始工作时间/工作终结时间栏目（时间逻辑） |
| `R-ER-002` | time_order | Q/GDW 1799.1-2013 | 抢修单时间栏目（抢修开始/结束时间先后逻辑） |

**9 条已核对**（可确定性判不合规）：`R-W1-007` / `R-LW1-007`（四要素覆盖）、
`R-OP-003` / `R-LOP-003`（五防）、`R-W1-003` / `R-W2-003` / `R-LW1-003` /
`R-LW2-003` / `R-ER-003`（签字链），依据国能发安全〔2023〕22号 1.2.7 / 1.2.19 / 3.2.1。

> 条款 pending **不写成「已覆盖」**，也不手填推测值；文本为「【待核对】+ 工具整理要点」
> 时只在「待人工确认」路径出现，不冒充条文原文。

### 2.4 复核锚

- 每条规则 `basis.review_due = 2027-10-02`（进账本 `evidence.review_due`）；
- 依据登记卡的 `reviewed_at / next_review / review_interval` 属产品级数据台账，不迁；
- **零时钟**：器官不做「今天是否逾期」判定（逾期告警是产品层/人的动作）。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | 依据锚点 |
|---|---|---|---|
| 规则库坐标（每次运行一条） | `pass` | 否 | `contract.rules` |
| 依据待核对汇总（30 条） | `not_applicable` | 否 | `contract.gate` |
| `合规` | `pass` | 否 | 该规则条款（`ticket:rule:<id>`） |
| `不合规` | `fail` | **是**（退出码 1） | 该规则条款 + `evidence.risk` |
| `待人工确认`（自然） | `not_applicable` | 否 | 该规则条款 |
| `待人工确认`（依据闸降级） | `not_applicable` | 否 | 该规则条款 + `evidence.downgraded=true` |
| 汇总：任一不合规 | `fail` | **是** | `contract.summary` |
| 汇总：有合规且无不合规 | `pass` | 否 | `contract.summary` |
| 汇总：全部待人工确认 | `not_applicable` | 否 | `contract.manual` |

**输入不可用**（缺 case_id / 缺 ticket / 未知票种 / 卡结构非法 / 规则库不可用）
→ `ValueError` → 退出码 2；条文库版本不符 / 条款缺失 → `ContractError` → 3。

### 3.2 人读（节选）

```text
clauseproof :: two-tickets 2026-10-02 :: ticket-signature-gap.json
[not_applicable] ticket.pending — 依据待核对 30 条（占 77%）：其「不合规」结论一律降级为「待人工确认」；可确定性判定的仅 9 条规则——条款 pending 如实登记，不把待核对写成已核对 :: 数据契约 / 依据闸 (2026-10-02)
[fail] ticket.rule:R-ER-003 — R-ER-003 process_signature :: 抢修单许可签字完整：风险 一般；签字环节缺失: 工作许可人（permitor） :: 国能发安全〔2023〕22号 / 3.2.1 (2026-10-02)
[pass] ticket.rules — 规则库 39 条（已核对 9 / 待核对 30）；7 票种 × 7 类 check_type；无出处的规则不得落库 :: 数据契约 / 规则库纪律 (2026-10-02)
[fail] ticket.summary — 三级结论：合规 2 / 不合规 1 / 待人工确认 0（共 3 条；待核对降级 0 条）；检出不合规，风险分布 一般=1 :: 数据契约 / 汇总语义 (2026-10-02)
合计 6 条，阻断 2 条（pass=3 fail=2 na=1）

clauseproof :: two-tickets 2026-10-02 :: ticket-time-order-pending.json
[not_applicable] ticket.rule:R-OP-002 — R-OP-002 time_order :: 依据待核对（Q/GDW 1799.1-2013 倒闸操作票时间栏目（操作开始/结束时间先后逻辑），复核到期 2027-10-02），「不合规」降级为待人工确认：操作时间顺序合法：操作/抢修开始时间 2026-10-16T09:40:00 晚于/等于 工作终结时间 2026-10-16T08:30:00，时间先后逻辑不成立 :: Q/GDW 1799.1-2013 / 倒闸操作票时间栏目（操作开始/结束时间先后逻辑） (2026-10-02)
[pass] ticket.summary — 三级结论：合规 3 / 不合规 0 / 待人工确认 1（共 4 条；待核对降级 1 条）；无不合规结论 :: 数据契约 / 汇总语义 (2026-10-02)
合计 7 条，阻断 0 条（pass=5 fail=0 na=2）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无不合规（全合规或含待人工确认） |
| `1` | 检出不合规（`已核对` 依据的规则判不合规） |
| `2` | 输入不合法（缺字段 / 票种未知 / 卡结构非法 / 规则库不可用） |
| `3` | 契约违约（条文库版本不符 / 条款缺失） |

> **漏 `--basis`** → 条文库版本为空 → 版本不符 → **退出码 3**，是契约正确行为。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 7 类 check_type（含五防形式化初查、四要素覆盖、电压互证） | ✅ | `checks.py` 逐条迁移 |
| 票种类目门控（`applies_to`） | ✅ | `engine.run_checks` |
| 依据闸（待核对 → 降级待人工确认） | ✅ | `engine.run_checks`（窄闸，check 之后） |
| 三级结论 + 问题分级（风险） | ✅ | `model` / 账本 `evidence.risk` |
| 规则库 schema（禁无出处规则） | ✅ | `rules.parse_rules` / `validate` |
| 复核锚（`review_due`） | 部分 | 规则数据随包、进账本证据；依据登记卡的 reviewed_at/next_review 属产品级台账 |
| 票面文本解析 / OCR / 编码清洗 | ❌ | 输入层；器官只收参数卡 |
| LLM 兜底抽取（防幻觉三件套） | ❌ | 输入层（可选能力） |
| 知识库 chunks / 余弦检索 | ❌ | 规则库已把依据挂到条款坐标；检索面属产品级 |
| docx 报告 / Web 面板 / 批量目录审核 | ❌ | 交付面 |
| 内置基准 runner / 数据生成器（35 例固定 seed） | ❌ | 工具面；35 例真值改作测试对账 |
| `demo/check/run/report/web/benchmark` 子命令 | ❌ | 产品级命令面（新入口只有 `list` / `check`） |

## 5. 口径差（如实登记）

1. **入口收敛**：来源 `demo/check/run/report/web/benchmark` → 器官 `check` 一个入口；
   批量目录与报告不迁（一条 subject = 一张票）。
2. **退出码语义差（接受）**：来源 `check` 完成即 **0**（检出不合规也不改退出码）；
   本器官按产品契约 `fail → 1`。README 主样例 0=0；检出样例旧 0 / 新 1，
   **接受为口径差，不加兼容 rc**（D10 口径）。
3. **未知 check_type 改为装配期拒绝**：来源运行时跳过并追加卡片 warning；
   本器官在装配期报错（退出码 2）——规则库是随包冻结数据，不静默跳过规则。
4. **参数卡字段值宽松化**：来源只接受 `{value, confidence, evidence}` 对象；
   本器官同时接受标量简写与纯字符串操作项/措施项（编译为同一内存模型）。
5. **账本化输出**：来源 `Conclusions` + stdout 排版 → 每规则一条判定行；
   三级结论、风险、依据状态、复核锚、降级标记全部进 `evidence`。
6. **待人工确认不冒充合规**：汇总里「全部待人工确认」记 `not_applicable`（退出码 0），
   消息明写「无确定性结论」；「合规」计数不含待人工确认。
7. **条款 pending 如实登记**：30 条依据以 `【待核对】` 前缀进条款书架 +
   `ticket.pending` 每次运行列出；**不改写为已核对**（测试锁定 9/30 计数）。
8. **真值库快照**：来源 35 份带真值样例（规则 id + kind + 字段真值 + 操作序列 +
   措施 + 缺陷声明）聚合为 `ticket-cases.json` 随包，作为测试对账面；
   生成器与固定 seed 不迁。
9. **复核锚零时钟**：只登记 `review_due`，不做「今天」判定（器官不读时钟）。
10. **与既有器官零复用**：slug / 规则 id / 条款 id / 测试文件均不复用。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 82**（7 文件）/ 新器官实跑 **N = 243** | **过**（243 ≥ 82） |
| 2 | README 示例命令 rc 相同 | 旧 `py -X utf8 -m powerticket check data/samples/sample-operating-01.txt` rc **0**（4 条全合规）/ 新 `check two-tickets --input …/ticket-operating-readme.json --basis …` rc **0**（同 4 条全合规）；未评估对照旧 `check …gen-operating-004-time-order.txt` rc **0** / 新 `…/ticket-time-order-pending.json` rc **0**（同为 3 合规 + 1 待人工确认）；检出对照旧 rc **0** / 新 rc **1** | **过**（README 主样例 0=0）；检出样例 **口径差（接受，D10）**：旧"完成即 0" vs 新 `fail→1` |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 243 ≥ 82；AST `test_` 函数 **141** ≥ 旧层 **82**；文件数旧 7 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation`（暂存树 `git write-tree` 导出，非脏工作树）→ `clauseproof-0.0.0-py3-none-any.whl`（**287 条目**）；`two-tickets/data/` **6 件 / 106654 B**；解包 `list` = **20 器官**、readme rc **0** / signature rc **1** | **过** |

**判据 1 的命令与输出原文**（来源仓只读，`PYTHONDONTWRITEBYTECODE=1`）：

```bash
cd <来源仓>
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_eval.py tests/test_knowledge.py tests/test_llm.py tests/test_package.py \
  tests/test_pending_gate.py tests/test_review_anchor.py tests/test_rules.py \
  -o addopts="" -q -p no:cacheprovider
# → 82 passed in 0.34s
```

逐文件 passed：eval 9 / knowledge 12 / llm 16 / package 4 / pending_gate 6 /
review_anchor 5 / rules 30 = **82**；旧层 AST `test_` 函数同为 **82**。

> **D1 + D18 机械口径说明**：`test_package.py` 的文件名含 `package` 但**不含**
> `packaging`，`test_llm.py` / `test_pending_gate.py` / `test_review_anchor.py`
> 均不含排除词，故**机械计入分母**，不按域手剔（与 #10 审计 §3.1 一致）。

### 6.1 D1 + D18 选文件与逐文件处置（7 文件 / 82 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `test_rules.py` | 30 | 规则库 schema / 7 类 check_type | **已迁**（§2.1；测试 §三–§六） |
| `test_llm.py` | 16 | LLM 兜底（防幻觉） | **不迁**（输入层可选能力；器官零网络、零 LLM）。D1 机械计入 X |
| `test_knowledge.py` | 12 | 登记卡 / chunks / 余弦检索 / 三层联动 | **部分迁**：规则→条款坐标联动迁入（条款书架 + `manifest`）；chunks 与检索属产品级 |
| `test_eval.py` | 9 | 解析 F1 / 端到端基准 / 评分函数 | **部分迁**：35 例精确对账口径迁入（测试 §十二）；解析 F1 与 runner 属产品级 |
| `test_pending_gate.py` | 6 | 依据闸正负对照 | **已迁**（§2.2；测试 §七） |
| `test_review_anchor.py` | 5 | 复核锚（登记卡 / 规则到期 / 逾期只告警） | **部分迁**：`review_due` 进规则证据；登记卡锚与逾期告警属产品级（零时钟） |
| `test_package.py` | 4 | 版本单源 / 包元数据 | **不迁**（发行面；产品级 CI）。D1 机械计入 X |
| **合计** | **82** | — | 已迁 2 / 部分迁 3 / 不迁 2 |

**D1 + D18 剔除（不计入 X，7 文件 / 141 passed）**：

| 来源测试文件 | passed | D1 词 | 去向 |
|---|---:|---|---|
| `test_data_generator.py` | 79 | `generat` | 固定 seed 生成器门（工具面；35 例真值改作测试对账） |
| `test_cli.py` | 20 | `cli` | 旧七子命令与退出码（新入口只有 `list`/`check`；产品级入口门接管） |
| `test_parse.py` | 14 | `parse` | 票面文本解析（输入层） |
| `test_report.py` | 10 | `report` | docx 报告（交付面） |
| `test_web.py` | 10 | `web` | Web 面板（交付面） |
| `test_packaging.py` | 6 | `packaging` | 装态自足性门（产品级 CI） |
| `test_release_audit.py` | 2 | `release` + `audit` | 发布脱敏审计（产品级） |

### 6.2 判据 2 对撞（旧命令 vs 新入口）

| 场景 | 旧命令 → rc | 新命令 → rc | 结论 |
|---|---|---|---|
| README 快速开始（操作票全合规） | `py -X utf8 -m powerticket check data/samples/sample-operating-01.txt` → **0**（4 条全合规） | `check two-tickets --input …/ticket-operating-readme.json --basis …` → **0**（同 4 条全合规；R-OP-001/002/004 待核对但结论为合规，不降级） | **过**（0=0） |
| 未评估对照（时间倒挂、依据待核对） | 同上 `…gen-operating-004-time-order.txt` → **0**（3 合规 + 1 待人工确认） | `…/ticket-time-order-pending.json` → **0**（同 3 合规 + 1 待人工确认；R-OP-002 降级标记 true） | **过**（0=0；判定同态） |
| 检出对照（签字链缺环，已核对依据） | 同上 `…gen-emergency_repair-035-signature-gap-permitor.txt` → **0**（2 合规 + 1 不合规） | `…/ticket-signature-gap.json` → **1**（同 2 合规 + 1 不合规；R-ER-003 fail） | **口径差（接受，D10）**：旧 `check` 完成即 0；新 `fail→1` |
| 五防负控 | 同上 `…gen-operating-005-five-prevention.txt` → **0**（3 合规 + 1 不合规） | `…/ticket-five-prevention.json` → **1**（R-OP-003 fail） | 同上（口径差，接受） |
| 漏 `--basis` | 旧无概念（规则库路径内建） | `check … --input …` → **3** | 契约正确行为 |

> 旧侧输出重定向到 `%TEMP%`；旧侧输入为来源样例（只读）；全程 `git status --porcelain` = 0 行。

### 6.3 判据 4 的进包清单（暂存树导出 → `pip wheel --no-deps --no-build-isolation`）

wheel：`clauseproof-0.0.0-py3-none-any.whl`（**287 条目**）；
`clauseproof/packs/two-tickets/data/` **6 件 / 106654 B**：

| 文件 | bytes | 来源 |
|---|---:|---|
| `rules-form.json` | 10920 | 来源规则库，**逐字节相同**（sha256 `792970a2…`） |
| `rules-time.json` | 17715 | 来源规则库，**逐字节相同**（sha256 `cb411ff3…`） |
| `rules-content.json` | 8734 | 来源规则库，**逐字节相同**（sha256 `b574c866…`） |
| `clauses.json` | 24944 | 由规则库 + 6 份登记卡 + 10 条数据契约装配（55 条） |
| `ticket-cases.json` | 43152 | 35 例带真值样例聚合（规则 id + kind + 字段真值） |
| `manifest.json` | 1189 | 逐文件 sha256 / bytes / 规则状态计数 |

解包后 `clauseproof list` = **20 器官**；`ticket-operating-readme` rc **0**、
`ticket-signature-gap` rc **1**（与 §6.2 一致）。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/rules-form.json` | 来源 `knowledge/rules/` | **逐字节相同**（形式合规类 12 条） |
| `data/rules-time.json` | 来源 `knowledge/rules/` | **逐字节相同**（时间类 19 条） |
| `data/rules-content.json` | 来源 `knowledge/rules/` | **逐字节相同**（内涵合规类 8 条） |
| `data/clauses.json` | 本器官装配产物 | 55 条：规则 39（30 带 `【待核对】`）+ 依据文件 6 + 数据契约 10 |
| `data/ticket-cases.json` | 来源 35 份 `*.truth.json` | 仅规则 id + kind + 字段/序列/措施真值 + 缺陷声明 |
| `data/manifest.json` | 本器官装配产物 | 漂移门：bytes + sha256 + 规则计数（9/30） |
| `samples/two-tickets/ticket-operating-readme.json` | 来源 README 快速开始票面（已解析卡） | 判据 2 主样例（rc 0） |
| `samples/two-tickets/ticket-signature-gap.json` | 来源真值样例 035（签字链缺环） | 检出对照（rc 1，R-ER-003） |
| `samples/two-tickets/ticket-time-order-pending.json` | 来源真值样例 004（时间倒挂） | 依据闸对照（rc 0，降级 NA） |
| `samples/two-tickets/ticket-five-prevention.json` | 来源真值样例 005（五防） | 五防负控（rc 1，R-OP-003） |

> 样例全部为合成数据（设备名与人名均为虚构），不含真实作业人员信息。