# 器官 `lease-terms`

> 条文判定器官 · 版本 `0.1.1` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：三份城市规则包（全国层《民法典》+ 北京 + 上海，共 **21 条规则**，全部 `verified`）
> 条文库坐标：`cn-2021.01+bj-2024.10+sh-2023.02`（三份规则包版本的复合值）

一句话：**给一张合同卡片，逐条判「约定值 vs 法条限值」，并说明依据是哪一条哪一款的原文**。

## 1. 输入

```bash
clauseproof check lease-terms \
  --input samples/lease-terms/card-demo-bj.json \
  --basis src/clauseproof/packs/lease-terms/data/clauses.json
clauseproof check lease-terms \
  --input samples/lease-terms/card-demo-bj.json \
  --basis src/clauseproof/packs/lease-terms/data/clauses.json --json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `city` | ✅ | `北京` / `上海` / `全国`；城市包**叠加在全国层之上**（同名 `rule_id` 以城市包为准） |
| `party` | — | `enterprise` / `individual` / `unknown`（缺省 `unknown`）；决定企业类规则是否适用 |
| `lease_kind` | — | `ordinary` / `affordable`（缺省 `ordinary`）；决定保障性租赁住房规则是否适用 |
| `fields` | — | 要素名 → 取值（`deposit_months` / `filing_days` / `has_deposit_clause` …）；**缺键或 `null` = 未观测** |
| `contract_text` | — | 合同原文（定性检查项按要素别名表在原文里匹配） |
| `clauses` | — | 已切分的条款 `[{number, text}]`；「是否可识别为租赁合同」用它 + 关键词判断 |

```json
{
  "city": "北京",
  "party": "enterprise",
  "lease_kind": "ordinary",
  "fields": {"deposit_months": "1", "filing_days": "15", "lodging_reg_workdays": "5"},
  "contract_text": "北京住房租赁合同 …",
  "clauses": [{"number": "第一条", "text": "甲方将位于北京西城区的住房出租给乙方居住使用…"}]
}
```

> **合同的物理解析不进器官**：条款切分、要素抽取（正则 + 证据逐字校验）、编码回落都留在
> 输入层（`SKELETON-SPEC` §2：器官不得做文件 IO）。`samples/lease-terms/cards.json` 的 12
> 张卡片是**用来源解析层只读生成**的，供真值对账；器官只吃卡片。

## 2. 规则

### 2.1 五态判定（`engine`）

| 状态 | 触发 | 含义 |
|---|---|---|
| `compliant` | 观测值满足规则 | 符合 |
| `noncompliant` | 观测值违反规则 / 法定要素缺失 | **不合规**（阻断） |
| `skipped` | `applies_if` **已知**不满足（主体/房屋类型） | 不适用（原文明确了适用情形限制） |
| `unknown` | 未观测到要素 / 主体未知 / 非可识别合同 / 无数值阈值 | 无法判定（拒判） |
| `not_assessed` | 仅用于**整体**口径：一条有效判定都没有 | 未评估（绝不输出 `compliant`） |

三条语义铁律（来源仓纪律，原样保留）：

1. **主体未知 ≠ 不适用**：`applies_if` 的主体条件遇到 `party=unknown` 判
   `unknown`（不是 `skipped`）——把「没确认」记成「不用管」会让合规结论虚高。
2. **无条件义务缺失 = `noncompliant`**：绝不记 `skipped`。
3. **`unknown` 存在时整体绝不报 `compliant`**（保守口径）。

### 2.2 四类判定

| `check_type` | 判什么 | 关键口径 |
|---|---|---|
| `numeric_limit` | 约定值 vs 限值（`<=` / `>=`） | 方向措辞由运算符决定（上限/下限**不混用**）；缺要素 → `unknown` 且**照挂限值** |
| `deadline_obligation` | 期限义务；无阈值时看「是否已约定」 | 已约定 → `compliant`；明确未约定 → `unknown`（法定补充规则，**非法定违反**） |
| `element_completeness` | 法定要素是否载明 | 按**别名表**在原文里匹配；非租赁合同文本 → `unknown`（不是「缺失」） |
| `text_prohibition` | 监管裁量/提示性条款 | `skipped` 并归条件触发栏，**不作为相对人义务** |

### 2.3 门控（加载侧再拦一次）

| 条件 | 处置 |
|---|---|
| `status != verified` | 不参与判定，记入未启用清单（`reason=数值核对状态非 verified`） |
| 缺**条款号 / 条文锚点 / 来源** | 不参与判定，记入未启用清单（`reason=缺锚点（…）`） |
| `scope = quota` | `calc` 路径下不作为义务，进**条件触发栏**（`not_applicable` + 「仅作提示」） |

> 锚点门是硬约束：缺锚点的规则被引擎加载生效，报告就会给出一条「看起来有依据」的判定，
> 而读者找不到原文核对——比不判更危险。故生成器断言之外，加载侧再拦一次。

## 3. 输出

### 3.1 账本映射

| 来源状态 | `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| `compliant` | `pass` | 否 | 该规则的条款引文 |
| `noncompliant` | `fail` | **是**（退出码 1） | 同上（**必带**） |
| `skipped` | `not_applicable` | 否 | 同上（判断「为何不适用」也要依据） |
| `unknown` | `not_applicable` | 否 | 同上（限值一并写进 `evidence`） |
| `scope=quota` | `not_applicable` | 否 | 同上（message 写明「仅作提示」） |
| 门控拦下 | `not_applicable` | 否 | **无**（无锚点可引正是它被拦下的原因） |

`evidence` 固定携带 `status` / `check_type` / `effect` / `severity` / `scope` / `param` /
`observed` / `limit` / `op` / `unit` / `clause` / `source_id` / `source_title` / `doc_no`。

### 3.2 人读（demo，退出码 1）

```text
clauseproof :: lease-terms 0.1.1 :: card-demo-bj.json
[pass] BJ-DEPOSIT-MAX-1M — 住房租赁企业收取的押金一般不得超过一个月租金 — 约定 1.00月租金，未超过规则上限 1月租金 :: 《北京市住房租赁条例》 / 第三十六条 (cn-2021.01+bj-2024.10+sh-2023.02)
[fail] BJ-LODGING-REG-3WD — 出租人应自合同订立之日起三个工作日内办理出租登记 — 约定 5.00工作日，超过规则上限 3工作日 :: 《北京市住房租赁条例》 / 第十五条 (cn-2021.01+bj-2024.10+sh-2023.02)
...
合计 14 条，阻断 1 条（pass=10 fail=1 na=3）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无阻断（`compliant` / `skipped` / `unknown` / quota 提示） |
| `1` | 有阻断（`noncompliant`） |
| `2` | 输入不合法（城市未登记、`party`/`lease_kind` 未知、`fields` 非对象、条款缺 `number`） |
| `3` | 契约违约（条文库缺条款、条文库版本与规则包坐标不符、参数包存在 pending 条目） |

> 漏 `--basis` 时条文库版本为空 → 版本不符 → **退出码 3**，是契约的正确行为。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 规则包门控（status / 锚点 / 作用域 / 全国层叠加） | ✅ | `engine.gate_rules` / `effective_rules` |
| 五态判定 + 适用域三态 | ✅ | `engine.judge_rule` / `applicability` |
| 四类判定（数值 / 期限 / 要素 / 禁止） | ✅ | `engine.check_*` |
| 义务分栏（quota → 条件触发栏） | ✅ | `engine.reference_findings` |
| 整体等级（保守口径） | ✅ | `engine.overall_status` |
| 条款切分 + 要素抽取（正则/证据逐字校验） | ❌ | 输入层（D18 `parse` 剔除）；卡片由输入提供 |
| 编码回落 / 文件定位 / 数据目录发现 | ❌ | 输入层（器官不读文件/环境） |
| 报告（Markdown / XLSX 双轨）与 CLI | ❌ | 输出排版属产品层 |
| GUI（PySide6）/ 打包 / 安装冒烟 | ❌ | 交付面 |
| 基准 runner / 门槛 manifest / 覆盖度登记 | ❌ | 产品级基准；判据 1 用 12 张样例卡片真值对账承接 |

## 5. 口径差（如实登记）

1. **输入从合同文本变成卡片**：器官收已抽取的 `fields` + `clauses` + `contract_text`；
   「要素抽取」与「条款切分」留在输入层（D18 把 `parse` 剔出判定层，正是因为它是 I/O 面）。
2. **`fields` 只带取值**：来源卡片的 `unit` / `confidence` / `evidence`（抽取层产物）不迁；
   判定只用取值，缺键或 `null` = 未观测。
3. **同一条款不同款项各自成条**：来源规则包对「第三十六条」的不同款项各引一句原文，
   条文库把它们登记为 `bj-rental:第三十六条#1/#2/#3`——合成一条会让 `quote` 不再逐字可核。
4. **非数值取值拒判而非崩溃**：来源 `_as_decimal` 遇到字符串会抛 `TypeError`（逃出 CLI）；
   器官记 `unknown`（「约定值不是数值」）——**拒判优于崩**，也不猜「一个月 → 1」的换算。
5. **`quota` 作用域保留条目**：来源仓在 `scope="quota"` 下实际返回空集（分支先 `continue`）；
   器官保留 quota 条目供「只查裁量条款」用途。`calc` 路径行为不变（进 `reference`）。
6. **整体等级不是逐条账本行**：来源 `overall_status` 的三态（`compliant` /
   `noncompliant` / `not_assessed`）在本产品由「有无 `fail`」+「是否有 `pass`」自然表达；
   `unknown` 一律记 `not_applicable`，故**不会**被读成合规。
7. **样例卡片由来源解析层生成**：12 张卡片的字段是只读调来源 `build_card` 得到的
   （解析层不迁），冻结进 `samples/lease-terms/cards.json` 供逐条对账。
8. **样例里的联系电话已脱敏**：来源样例的合成手机号会被本仓脱敏门（`tools/audit_repo.py`）
   判为个人数据，已统一替换为 `<联系电话已脱敏>`——**不影响任何判定**（要素匹配与数值规则
   都不依赖联系电话）。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 111**（6 文件，全部通过）/ 新器官实跑 **N = 158** | **过**（158 ≥ 111） |
| 2 | README 示例命令 rc 相同 | 旧 `python -m rca.cli check --input src/rca/data/samples/demo-contract-bj.txt --city 北京` rc **1** / 新 `clauseproof check lease-terms --input samples/lease-terms/card-demo-bj.json --basis …/data/clauses.json` rc **1**；12 条判定逐条同态（10 符合 / 1 不符合 / 1 无法判定）+ 2 条监管裁量提示 | **过**（rc 1 = 1） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 158 ≥ 111；`def test_` **158** ≥ 旧层 AST **85**；文件数旧 6 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（67 条目）；`clauseproof/packs/lease-terms/data/` **2 件**：`clauses.json` 8820 B / `rulesets.json` 29917 B；解包后 `list` = **5 器官**、demo `check` rc **1** | **过** |

**判据 1 的命令与输出原文**（来源仓只读；`PYTHONDONTWRITEBYTECODE=1` 防写旧仓缓存）：

```bash
cd <来源仓>
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_ci_wiring.py tests/test_engine_semantics.py tests/test_gating_and_data.py \
  tests/test_m3_knowledge_rules.py tests/test_m5_dual_entry.py \
  tests/test_readme_runnability.py \
  -p no:cacheprovider
# → 111 passed in 1.27s
```

> **baseline 158 必须先剔除脚手架目录再采信**：`158` 把 `.venv`（**93** 个 `test*.py`）与
> `_scratch`（**76** 个，含 `cleanenv/` / `fc2/` / `final/` 三份整树拷贝）算了进去。
> 仓库根 `tests/` 实为 **16** 个 `test_*.py`；D1 + D18 机械选 **6** 个、实跑 **111 passed**。

### 6.1 D1 + D18 选文件与逐文件处置（6 文件 / 111 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `tests/test_m3_knowledge_rules.py` | 44 | 规则包逐条 / 锚点 / 别名表 | **已迁**（§二/§三 漂移门 + §六 判定） |
| `tests/test_engine_semantics.py` | 22 | 五态 / 数值 / 期限 / 要素 | **已迁**（§六 判定用例） |
| `tests/test_gating_and_data.py` | 21 | 门控 / 规则包结构 / 叠加 | **已迁**（§四 门控 + §二 结构） |
| `tests/test_ci_wiring.py` | 9 | CI 脚手架 | 不迁（仓库 CI 接管） |
| `tests/test_readme_runnability.py` | 8 | README 可跑性门 | 不迁（产品级文档门） |
| `tests/test_m5_dual_entry.py` | 7 | CLI/GUI 双入口装配 | **部分迁**：入口职责分离由 §一 AST 门（无 argparse / 无 IO / 无 print）承接 |
| **合计** | **111** | — | 已迁 3 / 部分迁 1 / 不迁 2 |

D1 + D18 剔除（不计入 X，10 文件）：

| 文件 | 命中词 | 处置 |
|---|---|---|
| `tests/test_cli_contract.py` | `cli` | CLI 参数面（器官无 CLI） |
| `tests/test_install_smoke.py` | `smoke` | 装真 wheel 的装态门（本仓判据 4 与 CI 接管） |
| `tests/test_release_tools.py` | `release` | 发布工具链 |
| `tests/test_repo_guardrails.py` | `guard` | 仓库护栏门 |
| `tests/test_gui_layering.py` | `gui` | 桌面界面分层 |
| `tests/test_parser.py` | D18 `parse` | 条款切分/要素抽取（I/O 面，留输入层） |
| `tests/test_report.py` | D18 `report` | 报告双轨排版 |
| `tests/test_benchmark.py` | `bench` | 基准套件 |
| `tests/test_m4_benchmark.py` | `bench` | 基准套件 |
| `tests/test_m5_packaging.py` | `packaging` | 打包与产物验收 |

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/rulesets.json` | 来源仓 `src/rca/data/rules/ruleset-{cn,bj,sh}.json` | 只读合并（含 sources / 门槛 / 覆盖登记），wheel 进包 |
| `data/clauses.json` | 规则包的 `clause` + `quote` + `sources` | 21 条锚点（同一条款多款项各自成条），版本 `cn-2021.01+bj-2024.10+sh-2023.02` |
| `samples/lease-terms/card-demo-bj.json` | 来源仓 `demo-contract-bj.txt` 经来源解析层只读生成 | 判据 2 的新侧样例（rc 1） |
| `samples/lease-terms/cards.json` | 来源仓 `samples.json` 12 例 + 解析层只读生成卡片 | 12 例逐条真值对账（`expect` / `also_expect` 原样保留） |