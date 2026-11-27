# 器官 `food-label`

> 条文判定器官 · 版本 `0.1.0` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：双标尺规则集 `gb7718-2011`（21 条，现行）+ `gb7718-2025`（26 条，过渡期）
> 与参数表 `nutrient-reference`（NRV / 能量系数 / 声称阈值；全部挂 GB 7718/GB 28050
> 条款出处与条文块，基准日 2026-10-04）
> 条文库坐标：`2026-10-04`

一句话：**给一张已解析的预包装食品标签参数卡，分别按 GB 7718-2011（现行）与
GB 7718-2025（过渡期）判合规，输出「现行合规 / 新规不合规」对照**。

> **边界（人食品 ≠ 宠物食品）**：本器官规则源为 GB 7718 / GB 28050（**人食品**标签）；
> 已吸收的 `petfood-label` 器官（GB/T 31216/31217 **宠物食品**）与本器官**零共享
> 规则、零共享测试数据**——两者各自注册、各自随包数据（见 §7 边界表）。

## 1. 输入

```bash
clauseproof check food-label \
  --input samples/food-label/label-sample.json \
  --basis src/clauseproof/packs/food-label/data/clauses.json
clauseproof check food-label \
  --input samples/food-label/label-clean.json \
  --basis src/clauseproof/packs/food-label/data/clauses.json --json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `card` | ✅ | 标签参数卡（字段-值-单位-置信度-证据）：`fields` / `nutrition_table` / `ingredients` / `claims` / `unresolved_detail` |
| `text` | — | 标签纯文本（仅作门控平文本补充；判定只看参数卡） |
| `rulesets` | — | 规则集子集（`gb7718-2011` / `gb7718-2025`；缺省双标尺全跑） |

> **解析层不进器官**：文本标签 → 参数卡（字段抽取、逐字证据、非规范日期
> 归一、unresolved 标记）留在输入层（`SKELETON-SPEC` §2：器官不得做文件 IO）。

## 2. 规则

### 2.1 双标尺（47 条规则，11 种检查类型）

| 检查类型 | 用途 | 规则示例 |
|---|---|---|
| `mandatory_field` | 强制/新增标示在位 | 食品名称 / 配料表 / 净含量 / 生产日期 / 贮存 / 生产者 / SC / 标准代号 / 盐油糖提示语（2025）/ 营养标签 |
| `conditional` | 带豁免与人工分支 | 保质期与到期日（食醋/食盐/味精/固态食糖/葡萄酒豁免；酒类转人工核验度数） |
| `format` | 日期标示格式 | 生产日期 / 到期日（YYYY年MM月DD日 全字匹配） |
| `nrv_recalc` | NRV% 行级复算 | round(含量/NRV×100)，修约间隔 1，容差 ±1 |
| `energy_consistency` | 能量折算一致性 | E=round(17P+37F+17C)；低报 >120% 表2 判矛盾 |
| `ingredient_order` | 配料递减序先验 | 品类配方先验对（受 `only_if` 门控） |
| `claim_threshold` | 声称阈值 | 无糖 ≤0.5 / 低糖 ≤5 / 低钠 ≤120（表C.1） |
| `claim_whitelist` | 声称用语 | 疾病预防/治疗类禁用语；「不添加」类受限声称（2025） |
| `date_logic` | 日期自洽 | 到期日 = 生产日期 + 保质期（月加法截月末 / 天加法） |
| `nutrition_rows` | 强制营养行完整性（2025） | 能量+6 营养素（含饱和脂肪、糖） |
| `allergen_notice` | 致敏物质提示（2025） | 八类关键词检索配料表 + 提示在位 |

三条口径原样保留：

1. **「未提供」绝不判为符合**——三级判定：合规 / 不合规 / 待人工确认；
2. **标示行存在但解析失败转待人工确认**（不误判不合规；行整体缺失仍判不合规）；
3. **依据待核对标记**：`basis.status != 已核对` 的规则产出结论自动置
   `flagged_pending_basis`（账本 `evidence` 可见）。

### 2.2 数值口径（随包 `nutrient-reference.json`，器官代码零数值字面量）

| 项 | 值 | 出处 |
|---|---|---|
| NRV 表 | 能量 8400 kJ / 蛋白 60 g / 脂肪 60 g / 饱和脂肪 20 g / 碳水 300 g / 钠 2000 mg | GB 28050 附录A 表A.1 |
| 能量系数 | 蛋白 17 / 脂肪 37 / 碳水 17 kJ/g | **GB 28050-2025 §2.3**（2011 版无对应条款，D20 挂 2025 唯一出处） |
| NRV% 修约 | 间隔 1，容差 ±1 | 2011 A.2 / 2025 A.3.2 |
| 能量允许误差 | 实际值 ≤120% 标示值（+1 kJ 修约容差） | 2011 §6.4 / 2025 §6.7 表2 |
| 声称阈值 | 无糖 ≤0.5 / 低糖 ≤5 / 低钠 ≤120 | 两版表C.1 |
| 到期日推算 | 月加法截月末、天加法（不做 -1 天修正） | 生成器约定口径（GB 未明文规定） |

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| `不合规` | `fail` | **是**（退出码 1） | 对应检查类型的契约/数值口径条目 |
| `待人工确认` | `not_applicable` | 否 | 同上（标准条款号在 evidence） |
| `合规` | `pass` | 否 | 同上 |
| 双标尺差异（new/resolved fails） | `pass` | 否 | 双标尺契约 |
| 审查完成（stats） | `pass` | 否 | 统计口径契约 |

`evidence` 携带机读判据：`ruleset_id` / `rule_id` / `level` / `standard` /
`clause` / `quote_ref` / `basis_status` / `flagged_pending_basis` / `advice`。

### 3.2 人读（label-sample.json，退出码 1）

```text
clauseproof :: food-label 0.1.0 :: label-sample.json
[fail] label.finding:gb7718-2011:MAND-NET-01 — 不合规 [gb7718-2011] 未检出『强制标示：净含量与规格』对应的标示内容（参数 net_content）。 :: 数据契约 / 三级判定 (2026-10-04)
[fail] label.finding:gb7718-2025:MAND-EXPIRY-01 — 不合规 [gb7718-2025] 未检出『强制标示：保质期到期日（新版要求，豁免情形除外）』对应的标示内容（参数 expiry_date），且不属于可豁免情形。 :: 数据契约 / 三级判定 (2026-10-04)
[pass] label.dual_diff — 双标尺对照：gb7718-2011 → gb7718-2025；新增不合规 2 项（MAND-EXPIRY-01、SALT-NOTICE-01）；消除不合规 0 项（无） :: 数据契约 / 双标尺规则集 (2026-10-04)
[pass] label.result — 双标尺审查完成：不合规 6 条 / 待人工确认 0 条；… :: 数据契约 / 统计口径 (2026-10-04)
合计 36 条，阻断 6 条（pass=30 fail=6 na=0）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无阻断（干净样卡：0 条不合规；待人工确认不阻断——「没判定」≠「判出违规」） |
| `1` | 有阻断（任一 `不合规`） |
| `2` | 输入不合法（缺 `card`、`fields` 非对象、营养表行缺 `name`、未知规则集 id、文件缺失/坏 JSON） |
| `3` | 契约违约（条文库版本与规则包快照 `2026-10-04` 不符；缺契约条目 → `BasisMissing` → 3） |

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 47 条双标尺规则 + 11 种 check_type 处理器 | ✅ | `engine`（逐字移植） |
| 层级统计（pass/fail/manual/checked/skipped/not_run） | ✅ | `engine.run_ruleset` |
| 依据待核对标记 | ✅ | `flagged_pending_basis` |
| 数值复算（NRV%/能量/声称阈值/到期日） | ✅ | `numeric`（自写月历表；零时钟） |
| 双标尺差异对照 | ✅ | `engine.dual_diff` |
| 规则集 + 营养参数表 | ✅ | `data/*.json` **逐字节同 sha256** 随包 + 漂移门 |
| 标签解析（字段抽取/证据/日期归一） | ❌ | 输入层（D18 `parse` 剔除 3 文件） |
| LLM 兜底适配器 | ❌ | 器官零网络零 LLM（`test_llm.py` 不计入判定域处置见 §6） |
| CLI / docx 报告 / Web 面板 | ❌ | 产品级交付面（入口只有 `list` / `check`） |
| 合成标签生成器 / 基准 / 冻结守门 | ❌ | 产品级工具面（真值对账改由本器官测试承载） |

## 5. 口径差（如实登记）

1. **输入从文本标签变成参数卡**：解析层（字段抽取、逐字证据、非规范日期
   归一、unresolved 标记）留输入层；样例参数卡由来源解析层只读转写生成。
2. **退出码语义差（判据 2）**：旧 `flcheck check` 恒返回 **0**（"完成即成功"，
   不合规只进 JSON）；clauseproof 契约规定 `fail` → **1**。同一 README 示例
   （`examples/sample_label.txt --ruleset both`）旧 rc **0** / 新 rc **1**
   （6 条不合规：2011 的 MAND-NET/NUTR-TABLE + 2025 的 MAND-NET/MAND-EXPIRY/
   SALT-NOTICE/NUTR-TABLE）——按 D10「接受新契约」记为**口径差**，不加兼容 rc。
   干净对照（冻结集 clean 样本）旧 **0** / 新 **0**。
3. **双标尺差异定位**：`dual_diff` 在原 stats 之外单独成一条 `pass` 记录
   （new_fails/resolved_fails 逐值与旧 CLI 一致，见 §6 对账）。
4. **LLM 兜底不迁**：`unresolved_detail=present_unparsed` 只保留「转待人工确认」
   语义；LLM 自动抽取留输入层/产品层（器官零网络）。
5. **到期日推算口径**：月加法截月末、天加法、不做 -1 天修正——来源生成器
   约定口径（GB 未明文规定），逐字保留并在 advice/契约条目中注明。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 119**（13 文件）/ 新器官实跑 **N = 125** | **过**（125 ≥ 119） |
| 2 | README 示例命令 rc 相同 | 旧 `flcheck check examples/sample_label.txt --ruleset both --format json` rc **0**（stats：2011 `15/2/4/13/2/0`、2025 `19/2/5/15/4/0`；dual_diff new=[MAND-EXPIRY-01, SALT-NOTICE-01]）/ 新 `clauseproof check food-label --input samples/food-label/label-sample.json --basis …` rc **1**（同 stats 逐值一致、同 6 条不合规、同 dual_diff；按产品契约 `fail`→1） | **口径差**（接受：旧 rc 只反映流水线完成，新按契约阻断；干净对照旧 0 / 新 0） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 125 ≥ 119；`def test_` **125** ≥ 旧层 AST **109**；文件数旧 13 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（**111 条目**）；`clauseproof/packs/food-label/data/` **4 件**：`clauses.json` 3505 B / `gb7718-2011.json` 12877 B / `gb7718-2025.json` 17182 B / `nutrient-reference.json` 6405 B（**39969 B**；三份规则资产与来源逐字节同 sha256）；解包 `list` = **11 器官**、sample rc **1** / clean rc **0** | **过** |

**判据 1 的命令与输出原文**（来源仓只读；`PYTHONPATH=src` 因来源仓未装包）：

```bash
cd <来源仓>
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_blocks.py tests/test_datagen_repro.py tests/test_engine_dual.py \
  tests/test_engine_m3.py tests/test_engine_m4.py tests/test_extras_gate.py \
  tests/test_llm.py tests/test_models.py tests/test_numeric.py \
  tests/test_pipeline_trace.py tests/test_readme_count.py \
  tests/test_review_anchor.py tests/test_rulesets_schema.py \
  -o addopts="" -q -p no:cacheprovider
# → 119 passed in 4.38s
```

### 6.1 D1 + D18 选文件与逐文件处置（13 文件 / 119 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `tests/test_engine_m3.py` | 17 | 11 种 check_type 处理器 | **已迁**（§四/§五） |
| `tests/test_numeric.py` | 13 | NRV%/能量/声称/到期日 | **已迁**（§五） |
| `tests/test_engine_m4.py` | 12 | 2025 新增（到期日/盐油糖/营养行/致敏） | **已迁**（§十） |
| `tests/test_engine_dual.py` | 5 | 双标尺装配与差异 | **已迁**（§七） |
| `tests/test_blocks.py` | 4 | 条文块知识库 | 不迁（条文块本体留来源；契约条目在 `clauses.json`） |
| `tests/test_datagen_repro.py` | 10 | 生成器位级复现 | 不迁（产品级工具面） |
| `tests/test_extras_gate.py` | 6 | 可选依赖守门 | 不迁（打包面，判据 4 与 CI 接管） |
| `tests/test_llm.py` | 25 | LLM 兜底适配器 | 不迁（器官零网络；present_unparsed 语义已保留） |
| `tests/test_models.py` | 2 | 数据模型 | **已迁**（卡片/结论字段结构由 `validate_subject` 与账本映射覆盖） |
| `tests/test_pipeline_trace.py` | 5 | pipeline 状态机 | 不迁（编排留产品层） |
| `tests/test_readme_count.py` | 1 | README 计数门 | 不迁（产品级门） |
| `tests/test_review_anchor.py` | 3 | 复核锚（next_review） | 不迁（数据台账元数据） |
| `tests/test_rulesets_schema.py` | 6 | 规则集 schema | **已迁**（§二：规则结构/唯一性/依据必挂） |
| **合计** | **119** | — | 已迁 6 / 部分迁 1 / 不迁 6 |

D1 + D18 剔除（不计入 X，12 文件）：

| 文件 | 命中词 | 处置 |
|---|---|---|
| `tests/test_bench.py` | `bench` | 基准评测 |
| `tests/test_cli.py` | `cli` | CLI 参数面 |
| `tests/test_eol_guard.py` | `guard` | EOL 守门 |
| `tests/test_parser_fields.py` | D18 `parse` | 字段解析 |
| `tests/test_parser_frozen.py` | D18 `parse` | 冻结解析回归 |
| `tests/test_parser_minimal.py` | D18 `parse` | 最小解析 |
| `tests/test_platform_guard.py` | `guard` | 平台兼容守门 |
| `tests/test_report.py` | D18 `report` | docx 报告 |
| `tests/test_version_single_source.py` | `version` | 版本单一来源门 |
| `tests/test_webapp.py` | D18 `web` | Web 面板 |
| `tests/test_webapp_smoke.py` | D18 `web` + `smoke` | Web 冒烟 |
| `tests/test_extras_gate.py` 已计入（未命中） | — | — |

## 7. 随包数据与样例出处（含人食品 ≠ 宠物食品边界）

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/gb7718-2011.json` | 来源仓 `src/food_label_checker/rules/rulesets/gb7718-2011.json` | **逐字节相同**（sha256 `3b634964…`） |
| `data/gb7718-2025.json` | 来源仓 `…/rulesets/gb7718-2025.json` | **逐字节相同**（sha256 `988b1b5e…`） |
| `data/nutrient-reference.json` | 来源仓 `src/food_label_checker/rules/nutrient_reference.json` | **逐字节相同**（sha256 `0ee24883…`） |
| `data/clauses.json` | 11 条数据契约（由 `registry.clause_specs/clause_text` 生成） | 版本 `2026-10-04` |
| `samples/food-label/label-sample.json` | 来源仓 `examples/sample_label.txt` 经来源解析层只读转写为参数卡 | 判据 2 新侧样例（rc 1） |
| `samples/food-label/label-clean.json` | 来源冻结集 `sample-0001-dairy-fermented.txt`（clean_baseline）只读转写 | 干净对照（rc 0） |
| `samples/food-label/expected-dual.json` | 旧 CLI 输出的 stats / fails / dual_diff **冻结对账判据** | 测试逐值对账 |

**人食品 ≠ 宠物食品**：

| 项 | `food-label`（本器官） | `petfood-label`（已吸收） |
|---|---|---|
| 适用对象 | 预包装**人**食品标签 | **宠物**食品标签 |
| 规则源 | GB 7718-2011/2025 + GB 28050-2011/2025 | GB/T 31216/31217 + 公告20号 |
| 共享规则 | **零**（各自随包规则集） | **零** |
| 共享测试数据 | **零**（测试 §九 断言数据文件互不共用） | **零** |