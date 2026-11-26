# 器官 `bid-conformity`

> 条文判定器官 · 版本 `0.6.0` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：知识库坐标 `2026-10-05`（规则包 **21 条** `CHK-*`；条文块 16 条，其中 **14 条已核对**）
> 条文库坐标：`2026-10-05`

一句话：**给招标参数卡 + 投标参数卡，判投标响应在哪一条上不符合（或需人工确认），
并把每条结论挂到法规条号或招标文件条款 id 上**。

## 1. 输入

```bash
clauseproof check bid-conformity \
  --input samples/bid-conformity/subject-demo-goods-1.json \
  --basis src/clauseproof/packs/bid-conformity/data/clauses.json
clauseproof check bid-conformity \
  --input samples/bid-conformity/subject-demo-goods-2.json \
  --basis src/clauseproof/packs/bid-conformity/data/clauses.json --json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `tender` | ✅ | 采购需求参数卡（`TenderCard`：资格要求 / 星号条款 / 保证金 / 关键日期 / 否决条款） |
| `bid` | ✅ | 投标响应参数卡（`BidCard`：资格响应 / 星号响应 / 报价 / 保证金响应 / 人员 / 业绩） |
| `doc_text` | — | 招标文件原文（`only_if` 类目门控用；缺省视为空文本 → 带门控的规则不激活） |

```json
{
  "tender": {"qualifications": [{"item_id": "Q1", "requirement": "营业执照", "category": "qualification"}],
             "star_clauses": [{"item_id": "S1", "marker": "★", "text": "质保期不少于36个月"}],
             "key_dates": {"submit_deadline": "2026-10-19T09:30"},
             "rejection_clauses": [{"item_id": "R1", "text": "投标报价超过最高限价（人民币2,800,000.00元）的，投标无效"}]},
  "bid": {"qualifications": [], "star_responses": [], "prices": {"total_number": 2900000}},
  "doc_text": "……招标文件原文……"
}
```

> **解析层不进器官**：招标/投标文档 → 参数卡（章节切分、要素抽取、证据逐字校验）留在输入层
> （`SKELETON-SPEC` §2：器官不得做文件 IO）。样例卡片由来源解析层只读生成，见 §7。

## 2. 规则

### 2.1 七类确定性检查（21 条 `CHK-*`）

| 类 | 检查 | 结论 |
|---|---|---|
| `qualification_match` | 资格/财务材料缺失（`CHK-Q-01`）、证书过期（`Q-02`）、等级不足（`Q-03`）、业绩不满足（`Q-04`）、人员证书缺失（`Q-05`） | 不符合 / 待人工确认 |
| `star_response` | ★ 未响应（`SR-01`）、响应值偏离（`SR-02`）、▲ 已声明负偏离（`SR-03`） | 不符合 / 待人工确认 |
| `arithmetic_consistency` | 大小写金额不一致（`AR-01`）、分项合计与总价不一致（`AR-02`）、分项明细合计不一致（`AR-03`） | 不符合 |
| `bond_check` | 保证金金额不足（`BD-01`）、形式不允许（`BD-02`） | 不符合 |
| `date_logic` | 投标有效期不足（`DT-01`）、**招标侧**开标早于递交截止（`DT-02`） | 不符合 |
| `rejection_scan` | 超最高限价（`RJ-01`）+ 三条**否决联动**（`RJ-02` 保证金 / `RJ-03` 有效期 / `RJ-04` ★） | 不符合 |
| `price_check` | 低于成本嫌疑提示（`PC-01`） | 待人工确认 |

三条口径原样保留：

1. **只产非符合结论**（符合明细由产品层报告展开）；
2. **查不到的确定性输入一律跳过不硬判**（星号值抽不出数值/单位、保证金缺响应 → 不下结论）；
3. **方向由条款限定词决定**（「不少于/不低于」= 下限；「不超过/不高于/X日内」= 上限）。

### 2.2 门控与阈值

- `only_if` 类目隔离：关键词全部命中 `doc_text` 才激活；**随包 21 条规则 `only_if` 全为空**
  （即恒激活），门控代码保留；
- 唯一阈值 `CHK-PC-01.ratio = 0.8`（低于成本嫌疑比例）写在规则包里，引擎不写死。

### 2.3 依据关联（两条取值路径）

| 依据形态 | 示例 | 锚点 |
|---|---|---|
| 法规引用 | `《政府采购货物和服务招标投标管理办法》第六十三条` | 已核对条文块 `87-order:第六十三条` |
| 招标文件自设条款 | `Q1` / `S1` / `R4` | `contract:tender-clause`（条款原文在项目文件里，本产品条文库不含） |

引擎从不引用**待核对**的两条条文（`中华人民共和国招标投标法` 第三十三/三十四条）——
来源仓同口径，本器官把该纪律写进条文库：这两条**不在** `clauses.json` 里。

## 3. 输出

### 3.1 账本映射

| 来源三级结论 | `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| `不符合` | `fail` | **是**（退出码 1） | 法规条文块 / 招标条款契约（**必带**） |
| `待人工确认` | `not_applicable` | 否 | 同上 |
| （校核完成，无非符合结论） | `pass` | 否 | 规则包契约（汇总记录） |

依据不可解析时，`不符合` **降级为 `not_applicable`** 并在 message 写明「依据不可解析」——
绝不带一个解析不到的依据下阻断性结论。

`evidence` 携带 `check_id` / `status` / `risk_level` / `basis` / `evidence`（章节 + 原文摘录 + 行号）。

### 3.2 人读（demo-goods-1，退出码 1）

```text
clauseproof :: bid-conformity 0.6.0 :: subject-demo-goods-1.json
[fail] CHK-DT-02#1 — 开标时间 2026-10-19 09:00 早于投标文件递交截止时间 2026-10-19 09:30 :: 《政府采购货物和服务招标投标管理办法》 / 第三十九条 (2026-10-05)
[fail] CHK-RJ-04#1 — ★条款不满足或未响应，命中否决条款R4（★号条款不满足或者未响应的，其投标无效。） :: 《招标投标法实施条例》 / 第五十一条 (2026-10-05)
[fail] CHK-SR-01#1 — ★条款S1未响应（所投设备整体质保期不少于36个月） :: 数据契约 / 招标文件自设条款 (2026-10-05)
[fail] review.result — 校核完成：非符合结论 3 条（不符合 3 / 待人工确认 0） :: 数据契约 / 规则包注册 (2026-10-05)
合计 4 条，阻断 4 条（pass=0 fail=4 na=0）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无阻断（只 README 示例的干净对照组：结论 0 条；或全部为待人工确认） |
| `1` | 有阻断（任一 `不符合`） |
| `2` | 输入不合法（缺 `tender`/`bid`、`doc_text` 非字符串、文件缺失/坏格式） |
| `3` | 契约违约（条文库版本与知识库坐标不符；条文库缺依据时是 2，见下） |

> 漏 `--basis` 时条文库版本为空 → 版本不符 → **退出码 3**，是契约的正确行为。
> **条文库缺某条依据时**，内核抛 `BasisMissing` 并把它归入「输入不可用」→ **退出码 2**
> （`ORG-PLAYBOOK` §4 的口径是 3；本产品内核实现为 2，未改内核，此处如实登记）。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 21 条 `CHK-*` 规则包 + `only_if` 门控 + `params` | ✅ | `registry.RULES` / `gates.rule_applies` |
| 七类确定性检查 + 否决联动 | ✅ | `engine.run_checks` / `run_tender_checks` |
| 大小写金额换算与渲染 | ✅ | `amounts`（逐字移植） |
| 参数卡 IR（`TenderCard` / `BidCard`） | ✅ | `schema`（dataclass，JSON 往返） |
| 文档解析（章节切分/要素抽取/证据校验） | ❌ | 输入层（D18 `parse` 剔除） |
| 围标文本特征（`CHK-CL-01`）与图谱 HTML | ❌ | 独立模块；图谱是可视化产物 |
| LLM 兜底抽取 | ❌ | 器官零 LLM |
| 知识库 TF 余弦检索 | ❌ | 报告/兜底辅助，不参与判定 |
| 合成数据生成器 / 基准 / 报告 / Web / 打包 | ❌ | 产品级交付面 |

## 5. 口径差（如实登记）

1. **输入从项目目录变成参数卡**：器官收 `tender` / `bid` 两张卡 + 可选的 `doc_text`；
   文档解析、目录发现、写盘、报告与 Web 面板都留产品层。
2. **一次校核 = 一份投标卡**：旧仓 `run` 逐份校核一个项目下的全部投标；本器官按
   `evaluate(subject, basis)` 的单卡签名，把「多投标人」的循环留在输入层（与引擎
   `run_checks(tender, bid)` 的原语义一致）。
3. **退出码语义差（判据 2）**：旧 `run` 的 rc 只反映**流水线失败**（有结论也返回 0）；
   clauseproof 契约规定 `fail` → 1。同一示例（demo-goods-1）旧 rc **0** / 新 rc **1**，
   按 D10「接受新契约」记为**口径差**，不加兼容 rc；干净对照组（demo-goods-2）旧 **0** / 新 **0**。
4. **围标提示不迁**：`CHK-CL-01` 属 `collusion` 模块（文本特征 + 图谱），不在 7 个
   `rule_type` 分派表内；器官记不到该条，判据 1 用其余判定用例满足。
5. **待核对条文不进依据路径**：`中华人民共和国招标投标法` 第三十三/三十四条在来源仓
   标「待核对」（且复核日期已过），本器官**不把它们放进条文库**——引擎也不引用它们。
6. **依据不可解析 → 降级**：旧仓靠「依据关联率 100%」的仓库门保证不出现该情形；
   器官把它做成运行时行为（`fail` → `not_applicable` + 无锚点 + 明确 message），
   这样即使传入残缺条文库也不会造出带假依据的阻断结论。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 169**（14 文件，170 collected / **1 failed**）/ 新器官实跑 **N = 173** | **过**（173 ≥ 169） |
| 2 | README 示例命令 rc 相同 | 旧 `python -m bidchecker run examples/demo-goods-1 --out <tmp>` rc **0**（8 条结论：不符合 7 / 待人工确认 1）/ 新 `clauseproof check bid-conformity --input samples/bid-conformity/subject-demo-goods-1.json --basis …/data/clauses.json` rc **1**（3 条不符合 + 汇总；同一招标侧结论 `CHK-DT-02` 与同一投标人 ★ 的两条结论 `CHK-SR-01`/`CHK-RJ-04`）；干净对照组 demo-goods-2 旧 **0** / 新 **0** | **口径差**（接受：旧 rc 只反映流水线失败，新按产品契约 `fail`→1） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 173 ≥ 169；`def test_` **173** ≥ 旧层 AST **119**；文件数旧 14 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（86 条目）；`clauseproof/packs/bid-conformity/data/` **3 件**：`blocks.json` 13057 B / `clauses.json` 9773 B / `rules.json` 8513 B；解包后 `list` = **8 器官**、demo-goods-1 `check` rc **1** | **过** |

**判据 1 的命令与输出原文**（来源仓只读；`PYTHONDONTWRITEBYTECODE=1` 防写旧仓缓存）：

```bash
cd <来源仓>
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_amounts.py tests/test_collusion.py tests/test_collusion_graph.py \
  tests/test_datagen.py tests/test_engine.py tests/test_extras_gate.py tests/test_gates.py \
  tests/test_installed_wheel.py tests/test_knowledge.py tests/test_llm_fallback.py \
  tests/test_package.py tests/test_pipeline.py tests/test_schema.py tests/test_search.py \
  -p no:cacheprovider
# → 1 failed, 169 passed in 13.70s
```

**那 1 个 failed 是来源仓自身的**时间门**，不是本次迁移引入**：
`tests/test_knowledge.py::test_blocks_carry_review_metadata` 断言「待核对条文的
`next_review_due` 必须晚于今天」，实测 `中华人民共和国招标投标法第三十三条`
的复核期限是 **2026-11-05**、运行日为 **2026-11-26** → 已过期即红。这是数据台账
到期提醒（该条本就标「待核对」），X 取**实跑 passed 169**。

### 6.1 D1 + D18 选文件与逐文件处置（14 文件 / 169 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `tests/test_amounts.py` | 47 | 大小写金额换算 / 渲染 | **已迁**（§五） |
| `tests/test_datagen.py` | 22 | 合成数据生成器 | 不迁（产品级生成器；样例卡片另由只读解析生成） |
| `tests/test_engine.py` | 14 | 七类检查 / 否决联动 / 依据关联 | **已迁**（§七–§十一） |
| `tests/test_llm_fallback.py` | 14 | LLM 兜底抽取 | 不迁（器官零 LLM） |
| `tests/test_collusion_graph.py` | 13 | 围标图谱（shingle/Jaccard/SVG） | 不迁（可视化产物） |
| `tests/test_collusion.py` | 10 | 围标文本特征 | 不迁（`collusion` 不在分派表内） |
| `tests/test_knowledge.py` | 7（+1 failed） | 条文块 / 规则包台账 | **部分迁**（§二/§三 漂移门；复核时间门不迁，failed 见上） |
| `tests/test_pipeline.py` | 7 | 节点编排 / target 归因 | **部分迁**：校核编排（`run_tender_checks` + `run_checks`）已迁；collusion/report 节点不迁 |
| `tests/test_search.py` | 7 | TF 余弦检索 | 不迁（辅助检索，不参与判定） |
| `tests/test_extras_gate.py` | 6 | extras 打包门 | 不迁（打包面） |
| `tests/test_installed_wheel.py` | 6 | 装态门 | 不迁（判据 4 与 CI 接管） |
| `tests/test_package.py` | 6 | 打包产物 | 不迁（打包面） |
| `tests/test_gates.py` | 5 | `only_if` 门控 | **已迁**（§六） |
| `tests/test_schema.py` | 5 | IR JSON 往返 | **已迁**（§四） |
| **合计** | **169** | — | 已迁 4 / 部分迁 2 / 不迁 8 |

D1 + D18 剔除（不计入 X，8 文件）：

| 文件 | 命中词 | 处置 |
|---|---|---|
| `tests/test_bench_e2e.py` | `bench` | 端到端基准 |
| `tests/test_bench_parse.py` | `bench` + D18 `parse` | 解析基准 |
| `tests/test_cli.py` | `cli` | CLI 参数面 |
| `tests/test_parsers_bid.py` | D18 `parse` | 投标文档解析 |
| `tests/test_parsers_common.py` | D18 `parse` | 解析公共层 |
| `tests/test_parsers_tender.py` | D18 `parse` | 招标文档解析 |
| `tests/test_report.py` | D18 `report` | docx 报告 |
| `tests/test_webapp.py` | D18 `web` | Web 面板 |

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/rules.json` | 来源仓 `data/knowledge/rules.json` | **逐字节相同**（21 条规则），wheel 进包 |
| `data/blocks.json` | 来源仓 `data/knowledge/blocks.jsonl` | 只读转写（逐行对象 → 数组；`*.jsonl` 不在打包通配内） |
| `data/clauses.json` | 已核对条文块（14）+ 两条数据契约 | 16 条锚点，版本 `2026-10-05`；**待核对两条不入库** |
| `samples/bid-conformity/subject-demo-goods-1.json` | 来源仓 `examples/demo-goods-1`（tender + 首份投标）经来源解析层只读生成 | 判据 2 的新侧样例（rc 1） |
| `samples/bid-conformity/subject-demo-goods-2.json` | 来源仓 `examples/demo-goods-2`（干净对照组） | rc 0 样例 |