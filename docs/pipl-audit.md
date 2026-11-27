# 器官 `pipl-audit`

> 条文判定器官 · 版本 `2026-10-13` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：**《个人信息保护合规审计管理办法》**（国家互联网信息办公室令**第 18 号**，
> **2025-05-01 施行**）+ **GB/T 35273-2020**《个人信息安全规范》+ **GB/T 42574-2023**
> 《个人信息处理中告知和同意的实施指南》；两份规则包与来源**逐字节同 sha256** 随包
> 条文库 50 条：3 份依据文件 + 4 条门槛 + 26 条检查项 + 2 条示例门槛 + 4 条示例检查项
> + 11 条数据契约；条文库坐标 = 规则包核对日期 `2026-10-13`

一句话：**给一张已填好的审计参数卡（+ 人工录入结论），判是否触发审计义务、
逐项过 27 项审查要点的四态、汇总到「符合 / 部分符合 / 不符合 / 未评估」，
逐条挂办法与国标的条款锚点；未核对条目拒绝进入核查路径。**

## 1. 输入

```bash
clauseproof check pipl-audit \
  --input samples/pipl-audit/card-allpass.json \
  --basis src/clauseproof/packs/pipl-audit/data/clauses.json
clauseproof check pipl-audit \
  --input samples/pipl-audit/card-thresholds.json \
  --basis src/clauseproof/packs/pipl-audit/data/clauses.json
clauseproof check pipl-audit \
  --input samples/pipl-audit/card-not-assessed.json \
  --basis src/clauseproof/packs/pipl-audit/data/clauses.json
clauseproof check pipl-audit \
  --input samples/pipl-audit/card-demo.json \
  --basis src/clauseproof/packs/pipl-audit/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `case_id` | ✅ | 一次判定运行的稳定标识（输入必填字段） |
| `input_card` | ✅ | 已填好的审计参数卡：`scale` / `breach_scale` / `breach_sensitive_scale` / 各 auto 字段 / 各 `only_if` 门控字段 |
| `manual_results` | — | 人工检查项录入：`{检查项 id: {"state": 四态, "note": 说明}}` |
| `ruleset` | — | 规则包 id：`pipl-audit-2025`（缺省）/ `pipl-audit-demo`（合成示例包） |
| `audit_scope` | — | 审计范围元数据（原样进证据，不参与判定） |

```json
{
  "case_id": "pipl-demo",
  "ruleset": "pipl-audit-demo",
  "audit_scope": {"subject": "示例企业（虚构）", "period": "示例期间"},
  "input_card": {
    "has_policy": true, "has_consent_withdraw": false,
    "scale": 6000, "sensitive": true, "subject_type": "processor"
  },
  "manual_results": {
    "CHK-DEMO-003": {"state": "partial", "note": "示例：部分字段未加密"},
    "CHK-DEMO-004": {"state": "compliant", "note": "示例：渠道已设立"}
  }
}
```

未知顶层字段 → 退出码 2；`manual_results` 指向本规则包不存在的检查项 → 退出码 2
（来源静默忽略，本器官拒绝，见 §5）。

> **文件读取只在装配面**：两份规则包由 :mod:`pipeline` 从随包目录读入（与
> ``Basis.from_json`` 同形态的装配），判定内核只收内存对象。来源的
> ``--ruleset`` 路径解析 / ``find_data_dir`` / 证据文件读取**全部留输入层**
> ——器官零环境变量、零 cwd、零时钟、零文件 IO。

### 1.1 与既有器官 / 姊妹器官的边界

| 维度 | `pipl-audit`（本器官） | 既有/姊妹器官 |
|---|---|---|
| 对象 | **组织的个人信息保护合规状态**：审计义务是否触发 + 27 项审查要点逐项四态 | 无重叠器官 |
| 输入 | 已填好的**参数卡**（规模/敏感/场景布尔）+ 人工录入结论 | 各器官各自 subject |
| 依据 | 网信办令第 18 号 + GB/T 35273-2020 + GB/T 42574-2023 | 各自法规/标准/参数包 |
| 与隐私政策文本审查（后续 ① 行） | 不读隐私政策全文、不做文本条款抽取；只判组织侧义务与检查项四态 | 那一条做**文本审查**：政策文本 → 必备要素/告知项核对 |

slug / 规则 id（`audit.*`）/ 条款 id 前缀（`pipl:*`）/ 测试文件与既有 18 个器官
**零复用**；与"隐私政策文本审查"共享 **0 条规则**（对象、输入、依据三条全不同）。

## 2. 规则

### 2.1 审计义务门槛（`pipl-audit-2025`：4 条）

| 门槛 id | 参数 × 运算符 × 阈值 | 结论码 | 义务类型 | 条款锚点 |
|---|---|---|---|---|
| `TH-SCALE-PERIODIC` | `scale > 10000000` | `trigger_periodic_audit` | 周期性义务（无条件） | 网信办令第18号 / 第四条 |
| `TH-SCALE-OFFICER` | `scale >= 1000000` | `require_personal_info_officer` | 持续性义务（无条件） | 网信办令第18号 / 第十二条 |
| `TH-BREACH-GENERAL` | `breach_scale >= 1000000` | `may_require_professional_institution` | **条件触发** | 网信办令第18号 / 第五条（三） |
| `TH-BREACH-SENSITIVE` | `breach_sensitive_scale >= 100000` | `may_require_professional_institution` | **条件触发** | 网信办令第18号 / 第五条（三） |

- 比较在整数域进行；门槛值一律读自规则包，引擎源码**零门槛字面量**；
- **义务分栏**：命中的门槛按 `effect` 分「无条件义务」与「条件触发」两栏，
  结论不混同；`triggered` 只表示命中任一门槛；
- 命中按 `severity` 降序、同级按义务类型序（周期性 → 持续性 → 条件触发）；
- 参数缺失 / 类型不可比 → **显式登记为未判定**（不静默跳过，见 §5）。

### 2.2 检查单四态（26 条）

办法附件《审计指引》第 2–27 项共 **26 条**（第 1 项为制定依据前言，不建检查项）：

| 层 | 条数 | 例 |
|---|---:|---|
| 制度层 | 6 | 内部管理制度 / 培训计划 / 负责人履职 / 平台规则 / 社会责任报告 |
| 流程层 | 12 | 合法性基础 / 处理规则 / 告知 / 共同处理 / 委托 / 转移 / 向他人提供 / 公开 / 敏感 / 未成年人 / 出境 / 影响评估 |
| 技术层 | 3 | 自动化决策 / 公共场所设备 / 安全技术措施 |
| 响应层 | 5 | 删除权 / 权利保障 / 规则解释 / 应急预案 / 事件处置 |

- **四态**：`compliant` / `partial` / `noncompliant` / `not_applicable`；未观测记 `unknown`；
- **auto 项**（9 条）：读 `input_card[auto_field]`，按规则包 `auto_mapping`
  声明的「取值 → 四态」**有序首个命中**求值；规则包未给映射时退化为来源旧口径
  （非空 → 符合 / 否则不符合），兼容未细化的规则包；
- **manual 项**：读 `manual_results[id]`；缺失 → `unknown`（待人工确认，不计违规）；
  非法状态值归一为 `unknown`；
- **`only_if` 门控**：任一条件不满足 → `not_applicable`（不适用 ≠ 违规）。

### 2.3 汇总语义（不误报合规）

汇总只按**适用项**（`compliant` / `partial` / `noncompliant`）计算：

1. 任一 `noncompliant` → **不符合**；
2. 否则任一 `partial` → **部分符合**；
3. 全部 `compliant` → **符合**；
4. **一条适用项都没有 → 未评估（`not_assessed`）**，绝不输出「符合」。

`未评估` 按**阻断**处理（退出码 1）："没评" 与 "评过且合规" 不是一回事。

### 2.4 status 门控（唯一生效门）

- `status != verified` 的条目（依据 / 门槛 / 检查项）→ 拒绝进入判定路径（退出码 2）；
- `status=verified` 但缺出处（`channel` / `checked_at` 任一为空）→ 同样拒绝
  （"已核对"必须可追溯；标准全文公开页需登录，故 `url` 可空）；
- 本器官随包两包**全部 verified 且出处齐全**，无 pending 条目（§2.6）；
  门控本身用内存注入的合成 pending / 缺出处规则包实测拦截。

### 2.5 规则包坐标与合成示例包

| 规则包 | 用途 | 坐标 |
|---|---|---|
| `pipl-audit-2025` | **权威**（缺省） | id `pipl-audit-2025` / version `2025.1` / 3 依据 + 4 门槛 + 26 检查项 |
| `pipl-audit-demo` | **合成示例**（复现来源快速开始） | id `pipl-audit-demo` / version `2025.0` / 2 依据 + 2 门槛 + 4 检查项 |

- 示例包的条款坐标一律以 `示例（合成） / …` 前缀登记，条款 `text` 明写
  **【合成示例值，非法规原文，不得据以作出合规结论】**；
- 选中示例包时账本额外产出一条 `audit.pack.synthetic`（NA，无锚点）醒目提示；
- 报告头固定列出**规则包坐标**（`audit.pack` 记录），两包结论不混用。

### 2.6 条款 pending 登记（本器官：无 pending）

两包**全部条目 `verified` 且出处齐全**（出处 = 渠道 + 核对日 `2026-10-13`）：
依据 3 / 门槛 4 / 检查项 26 + 示例 2 / 2 / 4。**不存在「未核对却参与判定」的条目**；
若后续换包出现 pending，门控会在装配期拒绝并给出条目清单（退出码 2），
不会静默放行，也不会手填推测值。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | 依据锚点 |
|---|---|---|---|
| 规则包坐标（每次运行一条） | `pass` | 否 | `contract.pack` |
| 门槛命中（无条件义务 / 条件触发） | `pass` | 否 | 该门槛条款（`pipl:th:<id>`） |
| 门槛未触发 / 参数未提供 / 类型不可比 | `not_applicable` | 否 | 该门槛条款 |
| 门槛汇总（触发 / 分栏 / 频次） | `pass` | 否 | `contract.threshold` |
| 检查项 `compliant` | `pass` | 否 | 该检查项条款（`pipl:chk:<id>`） |
| 检查项 `partial` / `noncompliant` | `fail` | **是**（退出码 1） | 该检查项条款 + `evidence.risk` |
| 检查项 `not_applicable` / `unknown` | `not_applicable` | 否 | 该检查项条款 |
| 汇总 `compliant` | `pass` | 否 | `contract.summary` |
| 汇总 `partial` / `noncompliant` | `fail` | **是** | `contract.summary` |
| 汇总 `not_assessed` | `fail` | **是** | `contract.not_assessed` |
| 合成示例包提示 | `not_applicable` | 否 | 无锚点（提示项） |

**输入不可用**（缺 case_id / 缺 input_card / 未知字段 / 未知规则包 /
未知人工检查项 / 规则包门控拦截）→ `ValueError` → 退出码 2；
条文库版本不符 / 条款缺失 → `ContractError` → 退出码 3。

### 3.2 人读（节选）

```text
clauseproof :: pipl-audit 2026-10-13 :: card-allpass.json
[pass] audit.pack — 规则包 pipl-audit-2025 版本 2025.1：依据 3 份 / 门槛 4 条 / 检查项 26 条（全部 verified 且出处齐全） :: 数据契约 / 规则包坐标 (2026-10-13)
[pass] audit.summary — 汇总 符合：适用项 9（符合 9 / 部分符合 0 / 不符合 0）；不适用 14、未观测 3 :: 数据契约 / 汇总语义 (2026-10-13)
[pass] audit.threshold.result — 门槛结论：未触发；无条件义务 0 条；条件触发 0 条（分栏呈现，结论不混同） :: 数据契约 / 门槛判定与义务分栏 (2026-10-13)
[not_applicable] audit.threshold:TH-SCALE-PERIODIC — 输入未提供参数，未判定（TH-SCALE-PERIODIC：scale > 10000000） :: 网信办令第18号 / 第四条 (2026-10-13)
合计 33 条，阻断 0 条（pass=12 fail=0 na=21）

clauseproof :: pipl-audit 2026-10-13 :: card-thresholds.json
[pass] audit.threshold.result — 门槛结论：触发；无条件义务 2 条（频次：每两年至少开展一次合规审计）；条件触发 2 条（分栏呈现，结论不混同）；结论码：may_require_professional_institution、trigger_periodic_audit、require_personal_info_officer :: 数据契约 / 门槛判定与义务分栏 (2026-10-13)
[fail] audit.summary — 未评估：无任何适用项被评（适用项 0 / 检查项 26；不适用 14、未观测 12）——未评估不得冒充合规 :: 数据契约 / 未评估 (2026-10-13)
合计 33 条，阻断 1 条（pass=6 fail=1 na=26）

clauseproof :: pipl-audit 2026-10-13 :: card-demo.json
[fail] audit.item:CHK-DEMO-002 — CHK-DEMO-002【流程层】示例：撤回同意入口：不符合（自动核查未通过）；问题分级 high :: 示例（合成） / 示例条4 (2026-10-13)
[fail] audit.item:CHK-DEMO-003 — CHK-DEMO-003【技术层】示例：敏感信息加密：部分符合（示例：部分字段未加密）；问题分级 medium :: 示例（合成） / 示例条5 (2026-10-13)
[not_applicable] audit.pack.synthetic — 当前使用合成示例规则包 pipl-audit-demo：门槛值为合成示例值、非法规门槛，不得据以作出任何合规结论 :: 无锚点
合计 10 条，阻断 3 条（pass=5 fail=3 na=2）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 汇总符合（全部适用项 compliant；NA/unknown 不计） |
| `1` | 检出不符合（`partial` / `noncompliant`）或**未评估**（`not_assessed`） |
| `2` | 输入不合法（缺字段 / 未知规则包 / 未知人工检查项 / 规则包门控拦截） |
| `3` | 契约违约（条文库版本不符 / 条款缺失） |

> **漏 `--basis`** → 条文库版本为空 → 版本不符 → **退出码 3**，是契约正确行为。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 门槛判定 + 义务三分分栏 + 频次 | ✅ | `engine.evaluate_thresholds` |
| 检查单四态 + `auto_mapping` + `only_if` 门控 | ✅ | `engine.evaluate_item` |
| 汇总语义（含 not_assessed）+ 状态计数 | ✅ | `engine.summarize` / `counts` |
| 问题分级（noncompliant→high / partial→medium） | ✅ | 进 `evidence.risk` + 汇总计数 |
| status 门控（pending / 缺出处） | ✅ | `rules.effective` |
| 规则包坐标 + schema 校验（id 唯一/运算符/效应） | ✅ | `rules.validate` / `RulePack.coordinate` |
| 两份规则包 + 真值库快照 | ✅ | `data/*.json`（规则包**逐字节相同**；真值库只含输入与期望） |
| 底稿导出/导入 + 证据 sha256 指纹 | ❌ | 交付面；器官不读任何文件 |
| 整改台账（owner/due/status、CSV 导出） | ❌ | 工具面；分级进账本，责任落实不迁 |
| 报告导出（MD/DOCX/XLSX、模板两版） | ❌ | 交付面 |
| GUI 四页签 / PyInstaller 双 exe | ❌ | 交付面 |
| 内置基准 runner / 指标聚合 | ❌ | 产品级工具面（真值库 42 例改作测试对账） |
| 真值库生成器（独立 oracle） | ❌ | 工具面；快照随包，生成逻辑不迁 |
| `check/bench/report/evidence/draft/ledger/gui` 子命令 | ❌ | 产品级命令面（新入口只有 `list` / `check`） |

## 5. 口径差（如实登记）

1. **入口收敛**：来源七个命令面 → 器官 `check` 一个入口；规则包选择从
   `--ruleset <路径>` 变为 subject 的 `ruleset` id（两包随包固定，路径解析不迁）。
2. **退出码对齐**：来源 `0=全部符合 / 1=不符合或未评估 / 2=输入不可用`；
   本器官 `0` 同、`1` 同（`partial`/`noncompliant`/`not_assessed` 均阻断）、
   `2` 同（含规则包门控拦截）；新增 `3`=契约违约（条文库版本/条款缺失），
   **主样例 1=1、干净对照 0=0 未变**（判据 2 实测）。
3. **类型不可比不再静默跳过**：来源对 `TypeError` 直接 `continue`（该门槛既不触发
   也不留痕，输入质量问题被吞掉）；本器官登记 `type_mismatch` 的
   `not_applicable` 记录并写 `evidence`。**退出码不变**（来源也不阻断）。
4. **bool 视为类型不可比**：来源按 Python 语义把 `True` 当 `1` 参与比较；
   本器官把布尔值记 `type_mismatch`（`scale=True` 不应命中"100 万人"）。
5. **未知人工检查项拒绝**：来源对 `manual_results` 里不相干的 id 静默忽略；
   本器官报输入不合法（退出码 2）——防"换了规则包但旧录入被悄悄丢掉"。
6. **账本化输出**：来源底稿（`summary`/`counts`/`item_results`/`findings`）→
   每门槛 / 每检查项 / 每汇总一条判定行，四态、风险、条款坐标全部进 `evidence`；
   底稿结构与证据指纹不迁。
7. **义务分栏保留**：`obligations` / `conditional_triggers` 两栏在账本
   `audit.threshold.result.evidence` 中分开呈现，结论码按来源顺序（severity 降序）。
8. **汇总 not_assessed 映射为 `fail`**：来源 rc 1 的语义是"未评估也要报"；
   账本无"未评估"这一 verdict，故映射 `fail` 并在消息里写明
   **未评估不得冒充合规**（`contract.not_assessed` 锚点），不写成"不符合"。
9. **合成示例包随包**：来源 `data/samples/` 的示例规则包逐字节随包，只为复现
   来源快速开始；条款坐标带 `示例（合成）` 前缀 + 合成声明，选中时另有醒目记录。
   示例门槛值（5000/50000）**不是法规门槛**。
10. **真值库快照**：来源 42 例 × 26 项（仅 `input_card` + `manual_results` +
    `expected`，无 `observed`）聚合为 `truth-cases.json` 随包，作为本器官
   测试对账面；真值库生成器不迁。
11. **与既有器官零复用**：slug / 规则 id / 条款 id / 测试文件均不复用；
    与"隐私政策文本审查"共享 0 条规则（§1.1）。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 122**（12 文件）/ 新器官实跑 **N = 288** | **过**（288 ≥ 122） |
| 2 | README 示例命令 rc 相同 | 旧 `python -m paudit check data/samples/card-demo.json --ruleset data/samples/ruleset-pipl-audit-demo.json --out <tmp> --draft --evidence "CHK-DEMO-001=data/samples/evidence-demo.txt" --evidence-owner 审计员A` rc **1** / 新 `check pipl-audit --input samples/pipl-audit/card-demo.json --basis …` rc **1**（4 项状态、汇总、门槛结论逐条同态）；干净对照旧 `check data/truth/case-all-auto-pass.json --ruleset data/rules/ruleset-pipl-audit-2025.json` rc **0** / 新 `…/card-allpass.json` rc **0**；未评估对照旧 rc **1** / 新 rc **1** | **过**（1=1、0=0、1=1） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 288 ≥ 122；AST `test_` 函数 **165** ≥ 旧层 **122**；文件数旧 12 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（**273 条目 / 863943 B**）；`pipl-audit/data/` **5 件 / 179747 B**；解包 `list` = **19 器官**、demo rc **1** / allpass rc **0** | **过** |

**判据 1 的命令与输出原文**（来源仓只读，`PYTHONDONTWRITEBYTECODE=1`）：

```bash
cd <来源仓>
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_engine.py tests/test_evidence.py tests/test_gate_frozen.py \
  tests/test_gate_layering.py tests/test_gate_literals.py tests/test_gate_m1_data.py \
  tests/test_gate_m3_wiring.py tests/test_gate_m4_metrics.py tests/test_gate_m5_package.py \
  tests/test_ledger.py tests/test_repo_gate.py tests/test_rules_loader.py \
  -o addopts="" -q -p no:cacheprovider
# → 122 passed in 1.25s
```

逐文件 passed：engine 21 / evidence 17 / gate_frozen 9 / gate_layering 5 /
gate_literals 3 / gate_m1_data 9 / gate_m3_wiring 6 / gate_m4_metrics 9 /
gate_m5_package 14 / ledger 14 / repo_gate 4 / rules_loader 11 = **122**；
旧层 AST `test_` 函数同为 **122**。

> **D1 + D18 机械口径说明**：`test_gate_m5_package.py` 的文件名含 `package`
> 但**不含** `packaging`（`p-a-c-k-a-g-i-n-g`），故**机械计入分母**，不按域手剔；
> `test_repo_gate` / `test_gate_frozen` / `test_gate_literals` 同样不含排除词。
> 与 #10 审计 §3.1 的纠正口径一致。

### 6.1 D1 + D18 选文件与逐文件处置（12 文件 / 122 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `test_engine.py` | 21 | 门槛 / 检查单 / 汇总 | **已迁**（§2.1–§2.3；测试 §二–§四） |
| `test_evidence.py` | 17 | 证据链 / 底稿 | **部分迁**：四态判定与 `evidence_required` 字段迁入；sha256 指纹、底稿导出/导入、往返一致性不迁（交付面） |
| `test_gate_frozen.py` | 9 | 规则包冻结 / 坐标 | **部分迁**：规则包坐标与 sha256 漂移门迁入（`manifest` + 测试 §八）；来源仓冻结门属产品级 |
| `test_gate_layering.py` | 5 | 分层纪律（表现层零判定） | **已迁**：本器官无 CLI / 无文件 IO，结构断言见 §六/§八 |
| `test_gate_literals.py` | 3 | 引擎零门槛字面量 | **已迁**：门槛值全部读规则包（`TH-*` 来自随包数据） |
| `test_gate_m1_data.py` | 9 | 数据登记 / 出处核对 | **部分迁**：依据文件与出处进入条款书架 + `manifest` 登记；数据台账文档属产品级 |
| `test_gate_m3_wiring.py` | 6 | CLI/GUI 接线 | **部分迁**：产品入口只剩 `list`/`check`（产品级 `test_entry_surface` 接管）；器官侧由 `BUILTIN_MODULES` + 注册表实测 |
| `test_gate_m4_metrics.py` | 9 | 基准指标口径 | **部分迁**：42 例真值逐项对账迁入（测试 §九 ×3 参数化）；指标聚合与门值属产品级 |
| `test_gate_m5_package.py` | 14 | 打包 / 数据白名单 | **不迁**（发行门属产品级；数据进包由判据 4 实测）。D1 机械计入 X |
| `test_ledger.py` | 14 | 整改台账 / 风险分级 | **部分迁**：问题分级（high/medium）迁入账本证据；owner/due/status 与 CSV 导出不迁（工具面） |
| `test_repo_gate.py` | 4 | 仓库级门 | **不迁**（产品级 `tools/audit_repo.py` 与 CI）。D1 机械计入 X |
| `test_rules_loader.py` | 11 | schema / 门控 / 规则包坐标 | **已迁**（§2.4–§2.5；测试 §一） |
| **合计** | **122** | — | 已迁 4 / 部分迁 6 / 不迁 2 |

**D1 + D18 剔除（不计入 X，8 文件 / 120 passed）**：

| 来源测试文件 | passed | D1 词 | 去向 |
|---|---:|---|---|
| `test_cli.py` | 31 | `cli` | 旧七子命令与退出码（新入口只有 `list`/`check`；产品级入口门接管） |
| `test_gui_session.py` | 11 | `gui` | GUI 数据面（交付面） |
| `test_gui_smoke.py` | 3 | `gui` + `smoke` | GUI 冒烟（交付面） |
| `test_benchmark.py` | 18 | `bench` | 内置基准 runner（产品级工具面） |
| `test_report_formats.py` | 19 | `report` | 报告渲染（交付面） |
| `test_report_md.py` | 10 | `report` | 报告渲染（交付面） |
| `test_gate_m6_release.py` | 21 | `release` | 发行/发布门（产品级 CI） |
| `test_license_metadata.py` | 7 | `license` | 发行元数据（产品级） |

### 6.2 判据 2 对撞（旧命令 vs 新入口）

| 场景 | 旧命令 → rc | 新命令 → rc | 结论 |
|---|---|---|---|
| README 快速开始（示例包） | `python -m paudit check data/samples/card-demo.json --ruleset data/samples/ruleset-pipl-audit-demo.json --out <tmp> --draft --evidence "CHK-DEMO-001=data/samples/evidence-demo.txt" --evidence-owner 审计员A` → **1** | `check pipl-audit --input …/card-demo.json --basis …` → **1** | **过**（1=1；4 项状态 compliant/noncompliant/partial/compliant、汇总 noncompliant、门槛 `trigger_periodic_audit` 逐条同态） |
| 干净对照（全自动核查通过） | `python -m paudit check data/truth/case-all-auto-pass.json --ruleset data/rules/ruleset-pipl-audit-2025.json` → **0** | `check pipl-audit --input …/card-allpass.json --basis …` → **0** | **过**（0=0；汇总 compliant，9 项符合） |
| 未评估对照 | 同上 `case-none-applicable-not-assessed.json` → **1** | `check pipl-audit --input …/card-not-assessed.json` → **1** | **过**（1=1；汇总 not_assessed） |
| 门槛全命中（自定义卡） | —（旧侧同输入卡 `scale=10000001` + 两条 breach 未单列样例） | `check pipl-audit --input …/card-thresholds.json` → **1**（4 门槛全命中，2 无条件 + 2 条件） | 器官侧观测（旧侧无对应卡；不作为判据 2 依据） |
| 漏 `--basis` | 旧无概念（`--ruleset` 必填） | `check … --input …/card-demo.json` → **3** | 契约正确行为 |

> 旧侧输出重定向到 `%TEMP%`；旧侧输入为来源样本/真值文件（只读）；
> 全程 `git status --porcelain` = 0 行。

### 6.3 判据 4 的进包清单（`%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation`）

wheel：`clauseproof-0.0.0-py3-none-any.whl`（863943 B，**273 条目**）；
`clauseproof/packs/pipl-audit/data/` **5 件 / 179747 B**：

| 文件 | bytes | 来源 |
|---|---:|---|
| `clauses.json` | 15893 | 由两包 + 11 条数据契约装配（50 条） |
| `ruleset-pipl-audit-2025.json` | 40249 | 来源 `data/rules/`，**逐字节相同**（sha256 `da8aa7a6…`） |
| `ruleset-pipl-audit-demo.json` | 4368 | 来源 `data/samples/`，**逐字节相同**（sha256 `2941b48f…`） |
| `truth-cases.json` | 118053 | 来源真值库 42 例聚合（仅输入与期望） |
| `manifest.json` | 1184 | 逐文件 sha256 / bytes / 条文数登记 |

解包后 `clauseproof list` = **19 器官**；`card-demo` rc **1**、`card-allpass` rc **0**、
`card-not-assessed` rc **1**（与 §6.2 一致）。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/ruleset-pipl-audit-2025.json` | 来源 `data/rules/` | **逐字节相同**（3 依据 + 4 门槛 + 26 检查项，全部 verified） |
| `data/ruleset-pipl-audit-demo.json` | 来源 `data/samples/` | **逐字节相同**（合成示例包；门槛值非法规门槛） |
| `data/clauses.json` | 本器官装配产物 | 50 条：依据 3 / 门槛 4 / 检查项 26 / 示例 6 / 数据契约 11 |
| `data/truth-cases.json` | 来源 `data/truth/` 42 例 | 仅 `input_card` + `manual_results` + `expected`（无 `observed`） |
| `data/manifest.json` | 本器官装配产物 | 漂移门：bytes + sha256 + clause_count + 规则包计数 |
| `samples/pipl-audit/card-demo.json` | 来源快速开始参数卡（示例包） | 判据 2 主样例（rc 1） |
| `samples/pipl-audit/card-allpass.json` | 来源真值用例"全自动核查通过" | 干净对照（rc 0） |
| `samples/pipl-audit/card-not-assessed.json` | 来源真值用例"全部不适用/未观测" | 未评估对照（rc 1） |
| `samples/pipl-audit/card-thresholds.json` | 合成组合（4 门槛全命中） | 义务分栏演示（rc 1，未评估） |

> 样例全部为合成/演示数据，不含真实个人信息；示例规则包的门槛值是合成示例值，
> 不得据以作出任何合规结论。