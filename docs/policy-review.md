# 器官 `policy-review`

> 条文判定器官 · 版本 `2026-10-18` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：**《中华人民共和国个人信息保护法》**（74 条）+ **《网络数据安全管理条例》**（64 条）
> + **《App 违法违规收集使用个人信息行为认定方法》**（6 条）+ **《常见类型移动互联网
> 应用程序必要个人信息范围规定》**（7 条）+ **《促进和规范数据跨境流动规定》**（14 条）
> 五源条文包 **165 条锚点全部已核对**；十类模式包与来源**逐字节同 sha256** 随包
> 条文库 174 条：165 条法条锚点 + 9 条数据契约；条文库坐标 = 条文包生成日 `2026-10-18`

一句话：**给一份中文隐私政策/用户协议全文，切成可回溯到原文的条款，命中十类
高风险模式，把命中映射到已核对的法律条文锚点，输出「高 / 中 / 提示」三级发现，
每条发现挂硬锚点与原文区间；缺硬锚点不得判「高」。**

> **与 #16 的边界**：#16 是**组织侧合规状态审计**（已填好的参数卡 + 27 项审查要点），
> 本器官是**用户侧文本审查**（政策全文 → 条款 → 模式命中 → 法条锚点）。
> 对象、输入、依据映射三条全不同，**规则零复用**（模式正则 / 锚点 / 条款 id 不共享）。

## 1. 输入

```bash
clauseproof check policy-review \
  --input samples/policy-review/policy-case-03.json \
  --basis src/clauseproof/packs/policy-review/data/clauses.json
clauseproof check policy-review \
  --input samples/policy-review/policy-case-01.json \
  --basis src/clauseproof/packs/policy-review/data/clauses.json
clauseproof check policy-review \
  --input samples/policy-review/policy-clean.json \
  --basis src/clauseproof/packs/policy-review/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `case_id` | ✅ | 一次判定运行的稳定标识（输入必填字段） |
| `text` | ✅ | 隐私政策 / 用户协议**全文**（字符串，非空） |

```json
{
  "case_id": "policy-clean",
  "text": "隐私政策\n我们仅收集您的手机号用于账号登录，并采取加密与访问控制措施保护您的个人信息。\n您可以在设置页撤回授权或注销账号，我们将在十五日内删除相应信息。\n"
}
```

未知顶层字段 → 退出码 2；`text` 非字符串或空白 → 退出码 2。

> **文本读取只在输入层**：文件读取、编码探测、docx/网页抽取都在产品侧完成；
> 器官只收字符串。判定内核**零文件 IO、零网络、零 LLM、零时钟**（结构断言守门）。

### 1.1 与既有器官的边界

| 维度 | `policy-review`（本器官） | `pipl-audit`（#16） | 其它既有器官 |
|---|---|---|---|
| 对象 | **单份政策文本**：条款 → 模式 → 法条锚点 → 三级风险 | 组织的审计义务与 27 项检查项四态 | 各自业务对象 |
| 输入 | 政策全文（字符串） | 审计参数卡 + 人工录入 | 各自 subject |
| 依据 | 五源条文包 165 条锚点（逐条原文） | 网信办令第 18 号 + 两项国标（规则包） | 各自依据 |
| 视角 | **用户 / 相对方** | 处理者 / 机构自评 | — |

slug / 模式 id（`P01`–`P10`）/ 锚点 id / 条款 id 前缀（`contract.*`）/ 测试文件与
既有 20 个器官**零复用**。

## 2. 规则

### 2.1 十类模式（`severity_base` + 硬锚点）

| 模式 | 名称 | 基础等级 | 硬锚点 | 背景锚点 |
|---|---|---|---|---|
| `P01` | 数据共享给第三方 | 高 | PIPL-23 / APP-节5 | — |
| `P02` | 单方变更权 | 中 | PIPL-14 / PIPL-17 | — |
| `P03` | 不可撤销授权 | 高 | PIPL-15 | — |
| `P04` | 仲裁与管辖 | 提示 | — | CIVIL-496/497/498 |
| `P05` | 敏感个人信息 | 高 | PIPL-28 / PIPL-29 | — |
| `P06` | 跨境传输 | 高 | PIPL-38/39 / DATA_SEC-35 / CROSS_BORDER-5 | — |
| `P07` | 自动化决策 | 高 | PIPL-24 | — |
| `P08` | 未成年人个人信息 | 高 | PIPL-31 / DATA_SEC-21 | — |
| `P09` | 账号注销与删除 | 中 | PIPL-47 / APP-节6 | — |
| `P10` | 免责与责任限制 | 提示 | — | CIVIL-496/497/498 |

- 每条模式声明 `trigger_features`（正则）/ `negation`（否定抑制）/
  `neutralizers`（中和抑制）/ `escalation`（同文档共现升级）/ `evidence_date` /
  `version`；**引擎源码零等级字面量**；
- 随包 `escalation` 全部为空（v0.1 口径）；升级条件已实现并用注入规则包实测。

### 2.2 匹配纪律

1. **影子串归一化**：全角 ASCII → 半角（中文句读标点保留）、连续空白折叠、
   大写 → 小写；原文永不改写，命中偏移经 ``Shadow.to_original_span`` 回写原文；
2. **只扫非标题条款**：标题是结构信息，不作为义务句判定对象；
3. **否定 / 中和抑制**：同一条款内任一 negation / neutralizer 命中 →
   整条 (clause, pattern) 命中被抑制；
4. **偏移可回溯**：`text[char_start:char_end] == matched_text`（测试逐条断言）。

### 2.3 三级分级

| 等级 | 来源规则 | 账本 |
|---|---|---|
| `high` | `severity_base=high` + 升级条件 + **至少一个硬锚点** | `fail`（阻断 → 退出码 1） |
| `medium` | `severity_base=medium`，或 `high` 但缺硬锚点（**降级**） | `pass`（非阻断结论） |
| `notice` | `severity_base=notice`（程序性/背景性提示） | `pass` |

- 分级只看 `severity_base` + `escalation` 共现 + 硬锚点完整性；
  **不读时钟、不用置信度、不用主观评分**；
- 背景锚点（`CIVIL-*`）只作背景引用，不进 `anchor_ids`、不支撑 `high`；
- 模板（说明 / 修改方向）按 `pattern_id` 固定，不新增或删除命中。

### 2.4 锚点：硬 / 待核 / 背景

| 类型 | 判据 | 参与分级 | 账本 |
|---|---|---|---|
| 硬锚点 | `status=verified` 且条文原文 + 出处 + 核对日齐全 | ✅ | 进 `evidence.anchor_ids`；`high` 的锚点 |
| 待核锚点 | 缺失 / 未核 | ❌ | `policy.anchor.pending:<id>`（NA） |
| 背景锚点 | `CIVIL-*` | ❌ | `policy.anchor.background:<id>`（NA） |

随包 165 条锚点**全部已核对**，待核 0 条；待核路径用注入规则包（`eligible=false`）
实测：命中降级为 `medium`，并产出一条待核锚点记录。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | 依据锚点 |
|---|---|---|---|
| 规则库坐标（每次运行一条） | `pass` | 否 | `contract.rules` |
| 条款切分汇总（每次运行一条） | `pass` | 否 | `contract.split` |
| `high` 发现 | `fail` | **是**（退出码 1） | 首个硬锚点（如 `PIPL-31`） |
| `medium` 发现 | `pass` | 否 | 首个硬锚点 / `contract.grading` |
| `notice` 提示 | `pass` | 否 | `contract.notice` |
| 待核锚点 | `not_applicable` | 否 | 无锚点 |
| 背景锚点 | `not_applicable` | 否 | 无锚点 |
| 汇总：有 `high` / 无 | `fail` / `pass` | 是 / 否 | `contract.summary` |

**输入不可用**（缺 case_id / 缺 text / text 空白 / 规则包校验失败）→ `ValueError`
→ 退出码 2；条文库版本不符 / 锚点缺失 → `ContractError` → 退出码 3。

### 3.2 人读（节选）

```text
clauseproof :: policy-review 2026-10-18 :: policy-case-03.json
[not_applicable] policy.anchor.background:CIVIL-496 — 背景引用（CIVIL-* 不参与分级、不进 anchor_ids）：CIVIL-496 :: 无锚点
[pass] policy.finding:c-d35914e66866-0003:P04 — 提示级发现：仲裁与管辖——凡因本协议引起的争议，双方协商不成的，提交示例仲裁委员会仲裁，仲裁裁决是终局的。（原文 19-59） :: 数据契约 / 提示级 (2026-10-18)
[fail] policy.finding:c-d35914e66866-0005:P08 — 高级发现：未成年人个人信息——…（原文 67-99） :: 中华人民共和国个人信息保护法 / 第31条 (2026-10-18)
[pass] policy.finding:c-d35914e66866-0009:P09 — 中级发现：账号注销与删除——…（原文 152-189） :: 中华人民共和国个人信息保护法 / 第47条 (2026-10-18)
[pass] policy.rules — 规则库 0.1.0：10 类模式 / 5 部依据 / 165 条锚点（硬锚点 165 / 待核 0）；生成日 2026-10-18 :: 数据契约 / 规则库纪律 (2026-10-18)
[pass] policy.split — 条款切分：14 条（字符 273；appendix_row=2、heading=6、list_item=3、paragraph=3） :: 数据契约 / 条款切分 (2026-10-18)
[fail] policy.summary — 三级发现：高 1 / 中 1 / 提示 2（共 4 条；切分 14 条条款）；存在高级发现（阻断） :: 数据契约 / 汇总语义 (2026-10-18)
合计 10 条，阻断 2 条（pass=5 fail=2 na=3）

clauseproof :: policy-review 2026-10-18 :: policy-clean.json
[pass] policy.summary — 三级发现：高 0 / 中 0 / 提示 0（共 0 条；切分 2 条条款）；无高级发现 :: 数据契约 / 汇总语义 (2026-10-18)
合计 3 条，阻断 0 条（pass=3 fail=0 na=0）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 分析完成且无高级发现（含只有中/提示级发现） |
| `1` | 存在高级发现（`high`，且带硬锚点） |
| `2` | 输入不合法（缺字段 / 文本空白 / 规则包校验失败） |
| `3` | 契约违约（条文库版本不符 / 锚点缺失） |

> **漏 `--basis`** → 条文库版本为空 → 版本不符 → **退出码 3**，是契约正确行为。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 条款切分（标题/正文/列表/附表 + 原文偏移） | ✅ | `splitter.split_text` |
| 影子串归一化 + 偏移映射 | ✅ | `normalize` |
| 十类模式匹配 + 否定/中和抑制 | ✅ | `matcher` |
| 锚点映射（硬/待核/背景） | ✅ | `mapping` |
| 三级分级 + 升级条件 + 硬锚点完整性 | ✅ | `grader` |
| 规则包校验（manifest sha256 / 正则 / 锚点） | ✅ | `rules.load_library` |
| 十份模式 + 五份条文包 | ✅ | `data/pattern-*.json` / `data/statute-*.json`（**逐字节相同**） |
| Markdown 报告（固定章节 + 免责声明） | ❌ | 交付面 |
| `split/match/map/report/run/bench/selftest` 七子命令 | ❌ | 产品级命令面（新入口只有 `list` / `check`） |
| `findings.json` / `clauses.json` / `hits.json` 写盘与字段序契约 | ❌ | 交付面；账本字段由产品内核固定 |
| 真值基准 runner（bench v1） | ❌ | 工具面；5 份样例真值改作测试对账 |
| 合成数据生成器 / 条文抓取工具 | ❌ | 工具面 |
| 规则包定位链（`--references-dir` / 环境变量 / 上溯） | ❌ | 输入层；器官固定随包目录 |

## 5. 口径差（如实登记）

1. **入口收敛**：来源七个子命令 → 器官 `check` 一个入口；一次判定跑完整
   split → match → map → grade 链，中间产物只在内存。
2. **规则包不可用的退出码**：来源 `3`（规则包/条文包缺失或校验失败）；
   本器官按产品契约归入**输入不可用 2**（规则包不可用不是用户输入，但内核的
   2 已覆盖"环境/输入不可用"）。条文库**版本不符 / 锚点缺失**仍为 `3`。
3. **finding 附带 `pattern_id`**：来源 `findings.json` 契约（1.4 固定字段序）不含
   该字段；本器官不产该文件，账本需要稳定的规则身份，故在内部记录中附带
   （来源 bench 用 (clause, level, span) 匹配 finding 的绕行口径不再需要）。
4. **报告与字段序契约不迁**：Markdown 六章节、免责声明、`clauses/hits/mapping/
   findings` 四个 JSON 产物与三方字段序断言都属交付面；账本由产品内核统一。
5. **切分/匹配/分级逐条同态**：5 份合成样例（12 正例 / 12 否定反例）逐条对齐，
   等级、锚点、偏移全部一致（§6.2）。
6. **纯本地纪律保留**：判定内核零网络 import、零 `open()`、零时钟；
   结构断言见测试 §十一。
7. **条文锚点 = 165 条原文**：条文包逐字节随包；`path` = `条文标题 / 第N条`，
   `text` = 条文原文；待核锚点（本包为 0）以 `【待核对】` 前缀登记。
8. **背景锚点不落条文**：`CIVIL-496/497/498` 只作背景引用（无原文快照），
   不建条款、不参与分级。
9. **升级条件已实现但随包为空**：v0.1 模式包 `escalation` 全空；
   升级逻辑用注入规则包实测（升级 / 不降级 / 需共现 三条断言）。
10. **与既有器官零复用**：slug / 模式 id / 锚点 id / 条款 id / 测试文件均不复用；
    与 `pipl-audit` 规则零共享（§1.1）。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 95**（11 文件）/ 新器官实跑 **N = 136** | **过**（136 ≥ 95） |
| 2 | README 示例命令 rc 相同 | 旧 `py -X utf8 -m ppr run data/synthetic/cases/case-03.txt --out-dir <tmp>` rc **1**（1 高 / 1 中 / 2 提示）/ 新 `check policy-review --input …/policy-case-03.json --basis …` rc **1**（同 4 条、同级）；干净对照旧 rc **0** / 新 rc **0**；`case-01` 旧 **1** / 新 **1** | **过**（1=1、0=0、1=1） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 136 ≥ 95；AST `test_` 函数 **124** ≥ 旧层 **93**；文件数旧 11 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation`（暂存树 `git write-tree` 导出，非脏工作树）→ `clauseproof-0.0.0-py3-none-any.whl`（**318 条目**）；`policy-review/data/` **18 件 / 243857 B**；解包 `list` = **21 器官**、case-03 rc **1** / clean rc **0** | **过** |

**判据 1 的命令与输出原文**（来源仓只读；**baseline 83 含 `.venv` / `out/` 整树拷贝，
已剔除后重算**）：

```bash
cd <来源仓>
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_contract.py tests/test_docs.py tests/test_m1_rules.py \
  tests/test_m2_engine.py tests/test_m5_contract.py tests/test_m5_exit_codes.py \
  tests/test_m5_local.py tests/test_privacy.py tests/test_references.py \
  tests/test_serialize.py tests/test_splitter.py \
  -o addopts="" -q -p no:cacheprovider
# → 95 passed in 2.51s
```

逐文件 passed：contract 6 / docs 5 / m1_rules 11 / m2_engine 34 / m5_contract 6 /
m5_exit_codes 12 / m5_local 6 / privacy 1 / references 5 / serialize 3 /
splitter 6 = **95**；旧层 AST `test_` 函数 **93**（`m5_exit_codes` 10 函数 / 12 用例）。

> **剔除说明**：仓库根 `tests/` 13 文件；`.venv/Lib/site-packages`（colorama /
> pygments 的 6 个 `*_test.py`）与 `out/m5-venv-src`、`out/m6-release/unpack`
> 下的整树测试拷贝**全部剔出分母**（那 83 条的来源）；D1 + D18 只对根
> `tests/` 的文件名做机械匹配，`test_docs.py` 含 `docs` 但不含 `docs_`，故**机械计入**。

### 6.1 D1 + D18 选文件与逐文件处置（11 文件 / 95 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `test_m2_engine.py` | 34 | 切分 / 归一化 / 匹配 / 分级 | **已迁**（§2.2–§2.3；测试 §二–§五） |
| `test_m5_exit_codes.py` | 12 | 退出码四语义 | **部分迁**：0/1/3 语义保留并实测；规则包缺失由 3 归 2（§5.2） |
| `test_m1_rules.py` | 11 | 规则包 manifest / sha256 / 锚点 / 正则 | **已迁**（§2.4；测试 §六） |
| `test_contract.py` | 6 | 契约常量 / 字段序 | **部分迁**：等级/命中类型/截断口径迁入；JSON 字段序不产 |
| `test_m5_contract.py` | 6 | 三方字段序断言（真实跑命令） | **部分迁**：账本记录字段由产品内核固定；命令面不迁 |
| `test_m5_local.py` | 6 | 纯本地（网络静态扫描 / 断网全链 / 不写盘） | **部分迁**：零网络 + 零文件 IO 用 AST 结构断言（测试 §十一）；断网全链属产品级 |
| `test_splitter.py` | 6 | 切分形态 / 偏移 / compound | **已迁**（§2.2；测试 §二） |
| `test_docs.py` | 5 | 仓库文档 / README 一致性 | **不迁**（产品级文档门） |
| `test_references.py` | 5 | 规则包定位链 / 环境变量 / manifest | **部分迁**：manifest 校验迁入；定位链（`--references-dir`/env/上溯）不迁 |
| `test_serialize.py` | 3 | JSON 序列化字段序 | **不迁**（写盘序列化属交付面；账本字段序由内核固定） |
| `test_privacy.py` | 1 | 核心源码无网络模块 | **已迁**（测试 §十一 的 AST 断言） |
| **合计** | **95** | — | 已迁 4 / 部分迁 5 / 不迁 2 |

**D1 + D18 剔除（不计入 X，2 文件 / 29 passed）**：

| 来源测试文件 | passed | D1 词 | 去向 |
|---|---:|---|---|
| `test_m3_report.py` | 20 | `report` | Markdown 报告渲染（交付面） |
| `test_cli.py` | 9 | `cli` | 七子命令与参数（新入口只有 `list`/`check`；产品级入口门接管） |

### 6.2 判据 2 对撞（旧命令 vs 新入口）

| 场景 | 旧命令 → rc | 新命令 → rc | 结论 |
|---|---|---|---|
| README 一条命令全链 | `py -X utf8 -m ppr run data/synthetic/cases/case-03.txt --out-dir <tmp>` → **1**（1 高 / 1 中 / 2 提示） | `check policy-review --input …/policy-case-03.json --basis …` → **1**（同 4 条；P04 提示 / P08 高 / P09 中 / P10 提示） | **过**（1=1；等级与锚点逐条一致） |
| 高级发现 ×2 | 同上 `…case-01.txt` → **1**（2 高） | `…/policy-case-01.json` → **1**（P01 / P05 高） | **过**（1=1） |
| 干净对照 | `ppr run <干净文本>` → **0** | `…/policy-clean.json` → **0**（0 条发现） | **过**（0=0） |
| 真值对账（5 例） | `ppr bench` → **0**（5/5，12 正例 / 12 否定） | 测试 §十 逐例复算 → **5/5**（偏移、等级、锚点全一致） | **过** |
| 漏 `--basis` | 旧无概念（规则包内建） | `check … --input …` → **3** | 契约正确行为 |

> 旧侧 `--out-dir` 重定向到 `%TEMP%`；旧侧输入为来源合成样例（只读）；
> 全程 `git status --porcelain` = 0 行。

### 6.3 判据 4 的进包清单（暂存树导出 → `pip wheel --no-deps --no-build-isolation`）

wheel：`clauseproof-0.0.0-py3-none-any.whl`（**318 条目**）；
`clauseproof/packs/policy-review/data/` **18 件 / 243857 B**：

| 文件 | bytes | 来源 |
|---|---:|---|
| `pattern-p01.json` … `pattern-p10.json` | 1323 / 1322 / 1052 / 896 / 856 / 863 / 961 / 839 / 1371 / 871 | 来源 `patterns/*.json`，**逐字节相同**（sha256 `edb80d96…` 等） |
| `statute-PIPL.json` | 36509 | 来源 `statutes/PIPL.json`，**逐字节相同** |
| `statute-DATA_SEC.json` | 37617 | 来源 `statutes/DATA_SEC.json`，**逐字节相同** |
| `statute-APP.json` | 6169 | 来源 `statutes/APP.json`，**逐字节相同** |
| `statute-NECESSARY.json` | 11933 | 来源 `statutes/NECESSARY.json`，**逐字节相同** |
| `statute-CROSS_BORDER.json` | 8077 | 来源 `statutes/CROSS_BORDER.json`，**逐字节相同** |
| `clauses.json` | 118259 | 由五源条文包 + 9 条数据契约装配（174 条） |
| `synthetic-cases.json` | 11378 | 5 份合成样例（文本 + 真值）聚合；示例反馈邮箱脱敏为 `[at]` |
| `manifest.json` | 3561 | 逐文件 sha256 / bytes / 锚点与条款计数 |

解包后 `clauseproof list` = **21 器官**；`policy-case-03` rc **1**、`policy-clean` rc **0**
（与 §6.2 一致）。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/pattern-p01.json` … `pattern-p10.json` | 来源 `references/patterns/` | **逐字节相同**（十类模式 v0.1.0） |
| `data/statute-*.json` | 来源 `references/statutes/` | **逐字节相同**（五源 165 条锚点，全部已核对） |
| `data/clauses.json` | 本器官装配产物 | 174 条：165 法条 + 9 数据契约 |
| `data/synthetic-cases.json` | 来源合成样例 5 例 | 仅文本 + 真值（正例 / 否定反例 / 覆盖声明）；样例中的示例反馈邮箱已脱敏为 `feedback[at]example.invalid`（不影响模式命中与条款切分） |
| `data/manifest.json` | 本器官装配产物 | 漂移门：bytes + sha256 + 锚点/条款计数 |
| `samples/policy-review/policy-case-03.json` | 来源合成样例 case-03 | 判据 2 主样例（rc 1：1 高 / 1 中 / 2 提示） |
| `samples/policy-review/policy-case-01.json` | 来源合成样例 case-01 | 高级发现 ×2（rc 1） |
| `samples/policy-review/policy-clean.json` | 合成干净文本（本器官样例） | 干净对照（rc 0） |

> 样例全部为合成数据（虚构企业、设备名与人名），不含真实个人信息。