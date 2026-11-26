# 器官 `policy-intake`

> 条文判定器官 · 版本 `0.2.0` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：数据契约 `2026-10-15`（8 条契约条目：统一字段 / 日期 / 快照白名单 / 文号 /
> 未解析哨兵 / 部门别名 / 双键去重 / 规范序）
> 条文库坐标：`2026-10-15`

一句话：**给一批已抓到的政策条目和上次快照，判这批条目能不能作为本期日报的数据源——
哪条缺字段、哪条文号解析不了、哪个部门认不出、哪些是新增哪些是重复**。

> **依据是数据契约，不是法规条文**。本器官判的是「这批元数据能不能进日报」，没有可引的
> 法律条款，故契约条目的 `path` 一律写「数据契约 / …」，**不冒法条名与文号**。

## 1. 输入

```bash
clauseproof check policy-intake \
  --input samples/policy-intake/pair-a-b.json \
  --basis src/clauseproof/packs/policy-intake/data/clauses.json
clauseproof check policy-intake \
  --input samples/policy-intake/pair-a-b.json \
  --basis src/clauseproof/packs/policy-intake/data/clauses.json --json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `current.items[]` | ✅ | 本次条目（十字段：`source`/`id`/`index`/`pcode`/`title`/`pubtimeStr`/`puborg`/`url`/`summary`/`channel`） |
| `previous.items[]` | — | 上次快照条目；**缺省或 `null` = 首次运行**（全部计入新增） |

```json
{
  "previous": {"items": [{"id": "26270093", "pcode": "国函〔2026〕61号", "…": "…"}]},
  "current": {"items": [{"id": "26270094", "pcode": "国办发〔2026〕28号",
                          "title": "关于示例事项的通知", "pubtimeStr": "2026.10.08",
                          "puborg": "财政部 民政部", "url": "https://…",
                          "summary": "摘要", "source": "gwy"}]}
}
```

> **抓取与产物解析不进器官**：HTTP 抓取、按 `format` 分派（fetch / snapshot / diff）、
> 文件定位与写盘都留在输入层（`SKELETON-SPEC` §2）。器官只吃**已解析的条目清单**。

## 2. 规则

### 2.1 条目 schema（十个字段 / 七个必填）

必填：`source` / `id` / `title` / `pubtimeStr` / `puborg` / `url` / `summary`。
**空白字符串同样算缺失**；缺任一必填 → 该条不得落库、不得进日报。
字段白名单是**允许清单**：白名单之外的字段一律记违规；出现
`content`/`body`/`fulltext`/`full_text`/`html`/`text`/`article` 任一字段即拒
（不做全文归档）。

### 2.2 发布日期（两步校验）

1. 形态 `YYYY.MM.DD`（`2026-10-08` / `2026.1.8` 不得放过）；
2. **真实日历**校验组合（`2026.13.45` / `2026.02.30` / 平年 `2026.02.29` 必须被挡下；
   闰年 `2028.02.29` 放行，世纪年按 400 年规则）。

### 2.3 文号三态

| 形态 | 代字 | 年份 | 序号 | 状态 |
|---|---|---|---|---|
| `国办发〔2026〕28号` / `﹝…﹞` 全角 | 左括号前全部非空字符 | 括号内四位数字 | 右括号后到「号」前数字串 | `parsed` |
| `国令第847号` | 「第」前字符 | **`未解析`**（可靠来源缺失，不编造） | 「第」与「号」之间数字串 | `partial` |
| 其它 / 空 | `未解析` | `未解析` | `未解析` | `unparsed` |

哨兵串 = `未解析`；**部分字段失败不得当全字段成功**，`partial` 不等于 `parsed`。

### 2.4 部门归一（前缀 + 最长优先）

- 拆分按 `\s` 类空白（含 U+2002 / U+00A0 一类）；
- 逐 token 查别名表（39 条，`match_rule = longest_first`）；
- 匹配 = **前缀匹配 + 最长优先**（`国务院` 不得把 `国务院办公厅` 读成 `国务院`）；
- 认不出的**原样保留** + `alias_missing`（不猜）。

### 2.5 新增 / 重复（双键）与规范序

- `id` 相同 → 重复；否则 `pcode` 相同**且非空** → 重复；两键任一命中即重复，
  命中键写进 `matched_by`（供回溯）；
- `pcode` 为空只按 `id` 判；
- 规范序 = `pubtimeStr` 倒序、同级 `id` 升序；**产物无时间戳**。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| 必填齐 / 日期真实 / 字段白名单通过 | `pass` | 否 | 统一字段 / 日期 / 快照白名单契约 |
| 必填缺失 / 日期不真实 / 白名单违规 | `fail` | **是**（退出码 1） | 同上（**必带**） |
| 文号 `partial` / `unparsed` | `not_applicable` | 否 | 未解析哨兵契约 |
| 部门 `alias_missing` | `not_applicable` | 否 | 部门别名契约 |
| 快照判定为新增 | `pass` | 否 | 双键契约 |
| 快照判定为重复 | `not_applicable` | 否 | 双键契约 |
| 首跑（无上次快照） | `not_applicable` | 否 | 双键契约 |
| 输入未按规范序 | `not_applicable` | 否 | 规范序契约 |

`evidence` 携带机读事实：`missing` / `date_valid` / `forbidden` / `extra` /
`parse`{agency_code,year,serial,status} / `raw`+`canonical`+`alias_missing` /
`category`+`matched_by`。

### 3.2 人读（pair A→B，退出码 0）

```text
clauseproof :: policy-intake 0.2.0 :: pair-a-b.json
[pass] diff.item:26385742 — 相对上次快照为新增条目 :: 数据契约 / 新增与重复判定双键 (2026-10-15)
[not_applicable] diff.item:26276349 — 相对上次快照为重复（命中键 pcode），不计入本期新增 :: 数据契约 / 新增与重复判定双键 (2026-10-15)
[not_applicable] entry.pcode:… — 文号未完整解析（status=partial），显式标记不编造 :: 数据契约 / 未解析哨兵与三态 (2026-10-15)
[not_applicable] snapshot.order — 输入未按规范序（pubtimeStr 倒序 / id 升序）；产物须按规范序输出 :: 数据契约 / 规范序 (2026-10-15)
合计 136 条，阻断 0 条（pass=116 fail=0 na=20）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无阻断（缺字段/日期/白名单违规都没有；文号未解析、部门未命中、重复都不阻断） |
| `1` | 有阻断（必填缺失、日期不真实、字段白名单违规） |
| `2` | 输入不合法（缺 `current`、`items` 非数组、条目非对象） |
| `3` | 契约违约（条文库缺条款、条文库版本与契约坐标不符） |

> 漏 `--basis` 时条文库版本为空 → 版本不符 → **退出码 3**，是契约的正确行为。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 统一 schema + 必填校验 | ✅ | `engine.normalize_item` / `required_missing` |
| 发布日期两步校验 | ✅ | `engine.date_valid`（自写闰年表，不读时钟） |
| 文号三态 + 哨兵 | ✅ | `engine.parse_pcode` |
| 部门归一（最长优先） | ✅ | `engine.parse_orgs` / `sorted_alias_keys` |
| 双键新增/重复 + 命中键 | ✅ | `engine.detect_new` |
| 规范序 | ✅ | `engine.canonical_order` / `is_canonical_order` |
| 字段白名单门（禁正文） | ✅ | `engine.forbidden_fields` / `field_violations` |
| HTTP 抓取 / 重试 / 频道对账 | ❌ | 输入层（器官不联网） |
| 产物格式分派 / 文件定位 / 写盘 | ❌ | 输入层（器官不读文件） |
| 日报 / 订阅（关键词命中与排除） | ❌ | 产品层输出面；订阅另有真值套件，未纳入本器官判定域 |
| 基准 runner / 门槛 manifest / verify-data | ❌ | 产品级基准；判据 1 用真值库（11 文号 + 21 条目）逐条对账承接 |

## 5. 口径差（如实登记）

1. **输入从抓取产物变成条目清单**：`current` / `previous` 是已解析的十字段条目；
   HTTP、`format` 分派、写盘、数据根定位都留输入层。器官不读文件 / 不读环境 / 不读时钟 / 不联网。
2. **依据是数据契约**：8 条契约条目（`contract:*`）替代来源仓的 `data/` 口径文档；
   `path` 写「数据契约 / …」，**不冒法条名与文号**。
3. **部门别名表是器官内字面量**（`registry.ORG_ALIASES`，39 条），
   `data/org-aliases.json` 逐字节随包并由漂移门逐条比对；覆盖入口只给测试
   （`evaluate_with_aliases`），不暴露为输入字段。
4. **订阅（subscribe）不迁**：关键词命中/排除与日报渲染属产品层输出面；
   其真值套件（40 比对）不在本器官判定域内，判据 1 不借此充数。
5. **首跑语义保留**：`previous` 缺省/`null` = 首次运行（全部计新增），并额外记一条
   `diff.first-run`；给了 `previous` 但 `items` 缺失 → 输入不合法（不静默回落成首跑）。
6. **规范序是观测项**：输入未按规范序时记一条 `not_applicable`（提醒产物须排序），
   不因此阻断——排序是输出义务，不是条目缺陷。
7. **日期校验不读时钟**：自写闰年表（4/100/400 规则），不 import `datetime`。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 229**（10 文件）/ 新器官实跑 **N = 243** | **过**（243 ≥ 229） |
| 2 | README 示例命令 rc 相同 | 旧 `python -m policy_radar.cli diff --snapshot data/snapshots/pair-A.json --current data/snapshots/pair-B.json` rc **0**（上次 20 → 本次 21；新增 6 / 重复 15；命中键 id 14 / pcode 1）/ 新 `clauseproof check policy-intake --input samples/policy-intake/pair-a-b.json --basis …/data/clauses.json` rc **0**（新增 6 / 重复 15 / 命中键 id 14 + pcode 1；文号 17 parsed / 2 partial / 2 unparsed；部门 token 30 个、未识别 0 个） | **过**（rc 0 = 0） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 243 ≥ 229；`def test_` **243** ≥ 旧层 AST **193**；文件数旧 10 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（72 条目）；`clauseproof/packs/policy-intake/data/` **2 件**：`clauses.json` 2751 B / `org-aliases.json` 3318 B；解包后 `list` = **6 器官**、pair `check` rc **0** | **过** |

**判据 2 的旧侧输出原文**（来源仓只读）：

```text
  diff: 上次快照 20 条 → 本次 21 条；新增 6 条 / 重复 15 条（命中键 id 14 / pcode 1）
```

**判据 1 的命令与输出原文**（来源仓只读；`PYTHONDONTWRITEBYTECODE=1` 防写旧仓缓存）：

```bash
cd <来源仓>
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_cases_independence.py tests/test_fetch.py tests/test_model.py \
  tests/test_plan_count_gate.py tests/test_readme_gate.py tests/test_repo_hygiene.py \
  tests/test_samples_regression.py tests/test_serialize.py tests/test_snapshot_diff.py \
  tests/test_truth_gate.py -p no:cacheprovider
# → 229 passed in 4.94s
```

> **baseline 里的 `.venv` 5 条必须先剔除**：仓库 `.venv` 里唯一的 `test*.py` 是
> `pygments/lexers/testing.py`（第三方词法器，不是本仓测试）。剔除后仓库根 `tests/`
> 实为 **16** 个 `test_*.py`；D1 + D18 机械选 **10** 个、实跑 **229 passed**。

### 6.1 D1 + D18 选文件与逐文件处置（10 文件 / 229 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `tests/test_samples_regression.py` | 46 | 样例回归 / 真值对账 | **已迁**（§八/§九 逐条对账） |
| `tests/test_fetch.py` | 38 | HTTP 抓取 / 响应结构 | **部分迁**：条目归一（`item_from_api` 口径）已迁；HTTP/重试不迁 |
| `tests/test_model.py` | 31 | schema / 必填 / 日期真实性 | **已迁**（§四） |
| `tests/test_snapshot_diff.py` | 29 | 规范序 / 双键 / 字段白名单 | **已迁**（§七） |
| `tests/test_readme_gate.py` | 28 | README ↔ CLI 反射 | 不迁（产品级文档门） |
| `tests/test_truth_gate.py` | 19 | 真值库结构 / 覆盖登记 | **部分迁**：真值用例逐条对账；台账结构不迁 |
| `tests/test_serialize.py` | 15 | JSON 读写确定性 | 不迁（输入/输出层；本仓内核统一序列化） |
| `tests/test_repo_hygiene.py` | 9 | 仓库卫生 | 不迁（仓库纪律） |
| `tests/test_cases_independence.py` | 8 | 源码扫描（包内不得 import 对账器） | **已迁其精神**：本器官不 import 任何对账器（§一 AST 门） |
| `tests/test_plan_count_gate.py` | 6 | 计划文档计数门 | 不迁（计划文档） |
| **合计** | **229** | — | 已迁 3 / 部分迁 2 / 不迁 5 |

D1 + D18 剔除（不计入 X，6 文件）：

| 文件 | 命中词 | 处置 |
|---|---|---|
| `tests/test_cli_contract.py` | `cli` | CLI 参数面（器官无 CLI） |
| `tests/test_generators_check.py` | `generat` | 生成器一致性门 |
| `tests/test_parse_pcode.py` | D18 `parse` | 文号解析**文件级**用例；其判定逻辑仍迁入 §五（不从 X 借数） |
| `tests/test_report_pipeline.py` | D18 `report` | 日报渲染管线 |
| `tests/test_selftest.py` | `selftest` | 自检命令 |
| `tests/test_subscribe_bench.py` | `bench` | 订阅基准 |

> `test_parse_pcode.py` 虽被 D18 剔出 X，其 **11 条手标文号真值**仍逐条迁入 §五——
> 剔除的是分母，不是知识。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/org-aliases.json` | 来源仓 `data/config/org-aliases.json` | **逐字节相同**，wheel 进包（39 条别名 + `match_rule`） |
| `data/clauses.json` | 本器官 `registry.clause_specs()` | 8 条数据契约锚点，版本 `2026-10-15` |
| `samples/policy-intake/pair-a-b.json` | 来源仓 `data/snapshots/pair-A.json` + `pair-B.json` | 判据 2 的新侧样例（rc 0） |
| `samples/policy-intake/pcode-truth.json` | 来源仓 `data/truth/pcode-truth.json` | 只读拷贝（11 例文号真值） |
| `samples/policy-intake/diff-truth.json` | 来源仓 `data/truth/diff-truth.json` | 只读拷贝（21 条新增/重复真值） |