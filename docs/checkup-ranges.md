# 器官 `checkup-ranges`

> 条文判定器官 · 版本 `0.2.0` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：内置区间知识库快照 `2026-10-16`（19 条，**全部 `pending`**）+ 报告单/LIS 印制区间
> 条文库坐标：`2026-10-16`

一句话：**给一条测量记录，判它是否落在参考区间内，并说明依据是谁**（报告单印的区间 /
已核对的标准区间 / 无依据 → 拒判）。

## 1. 输入

```bash
clauseproof check checkup-ranges \
  --input samples/checkup-ranges/measurement-high-alt.json \
  --basis src/clauseproof/packs/checkup-ranges/data/clauses.json
clauseproof check checkup-ranges \
  --input samples/checkup-ranges/measurement-normal-tc.json \
  --basis src/clauseproof/packs/checkup-ranges/data/clauses.json --json
```

> `samples/checkup-ranges/measurements.json` 是**集合**样例（20 条记录，来自来源仓
> `data/samples/truth/case-*.json` 的只读转写），供 §十一 的逐条 parity 测试使用；
> 单条记录样例见上面两条命令。

| 字段 | 必填 | 说明 |
|---|---|---|
| `canonical_name` | ✅ | 指标名：规范名或任一别名（`白细胞计数`/`WBC`…），按知识库声明序归一 |
| `value` | ✅ | 数值（int/float；**bool 与字符串一律拒收**） |
| `unit` | ✅ | 单位：规范单位或单位别名（`10^9/L`/`10E9/L`…），认不出 → 拒判 |
| `range` | — | 报告自印区间 `{low, high, bounds}`；`bounds` ∈ `closed`/`open`；可只给一侧 |
| `subject_sex` | — | `male`/`female`/`any`；用于内置区间的适用域判断 |

```json
{
  "canonical_name": "ALT",
  "value": 43.0,
  "unit": "U/L",
  "range": {"low": 9.0, "high": 40.0, "bounds": "closed"},
  "subject_sex": "male"
}
```

## 2. 规则

**三级优先选区间**（口径唯一源，来源产品 `data/README.md` 第五节）：

1. **报告自印区间**最优先（报告上印的才是该受检者的有效区间，主体天然适用）；
2. 否则用**内置来源标注默认值**——但两条硬门：条目必须 `status=verified`，
   且 `applies_to.sex` 必须适用于该样本主体（主体未知 → 不适用）；
3. 都没有 → **拒判**（`not_assessed`），只记事实数值。

**四态比较**（`engine.compare`）：

| 情形 | flag |
|---|---|
| `low`/`high` 都缺 | `not_assessed` |
| `value > high`；或 `bounds=open` 且 `value == high` | `high` |
| `value < low`；或 `bounds=open` 且 `value == low` | `low` |
| 其余 | `normal` |

边界语义**由区间自带**（`closed` 含端点 / `open` 不含端点），不在代码里硬编码
某个标准的习惯；单侧区间对缺失的那一侧不设限。

**知识库现状（必须知道）**：19 条全部 `status: pending`（WS/T 404/405 全文不可直连，
区间数值无法逐条核对）→ **内置默认值不进判定路径**。所以：报告未自印区间时一律
"拒判"，`code=builtin_pending`。这是来源产品的既定纪律（宁拒判，不臆造），本器官原样保留。
其中 6 条（TC/TG/HDL-C/LDL-C/UA/GLU）在 WS/T 404/405 系列里**没有对应分册**，
`source.standard` 如实写"未定位"，不拿方法标准冒充区间来源。

## 3. 输出

### 3.1 账本映射

| 来源四态 | `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| `normal` | `pass` | 否 | 区间来源：`range:report-printed` 或 `wst:<指标>` |
| `high` / `low` | `fail` | **是**（退出码 1） | 同上（**必带**） |
| `not_assessed` | `not_applicable` | 否 | 无（**拒判没有依据可引**），message 写明 `code` |

`evidence` 固定携带 `flag` / `code` / `range_source` / `range_low` / `range_high` /
`bounds` / `canonical_name` / `value` / `unit` / `standard` / `applies_to_sex` /
`subject_sex` / `registry_status`（拒判时另有 `refused_reason`）。

### 3.2 人读

```text
clauseproof :: checkup-ranges 0.2.0 :: measurements.json
[fail] measurement.range:ALT — 高于参考区间上限 40.0（区间 9.0–40.0，来源 report_printed） :: 报告单 / LIS 印制参考区间 (2026-10-16)
合计 1 条，阻断 1 条（pass=0 fail=1 na=0）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | `normal` 或 `not_assessed` |
| `1` | `high` / `low`（区间外） |
| `2` | 输入不合法（缺 `canonical_name`/`value`、`value` 非数值、区间结构缺陷） |
| `3` | 契约违约（条文库缺条款、条文库版本不符、器官不存在） |

> ⚠️ **与来源工具的退出码差**：来源产品把 H/L 视为**成功执行 + 业务结果**（rc 0，
> "业务结果不是错误"）；clauseproof 契约（SKELETON-SPEC §5）规定 `fail` → 退出码 1。
> 新入口一律 1。这是**产品级语义差**，不是移植缺陷（见 §5 判据 2）。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 四态比较 + 边界语义 | ✅ | `engine.compare`（逐条对齐） |
| 三级优先选区间 | ✅ | `engine.select_range` |
| 主体适用域硬门 | ✅ | `engine.range_applies_to` |
| 名称/单位归一 | ✅ | `engine.normalize_name` / `normalize_unit`（声明序、不做子串匹配） |
| 区间结构门 | ✅ | `engine.validate_range`（缺陷显式抛错，不降级成"拒判"） |
| 知识库 + status 门控 | ✅ | `registry.py` 字面量 + `is_effective` |
| 趋势三态（升/降/平稳） | ❌ | 是**事实归类**不是合规结论，无条款可锚；留在产品层台账 |
| SQLite 台账 / 唯一键 upsert | ❌ | 存储层（I/O），器官不做持久化 |
| PDF 文本层 / OCR 摄取 | ❌ | 输入通路 I/O |
| 报告/HTML/图表/导出 | ❌ | 输出排版属产品层 |
| GUI / 打包 / PII 门 / 冻结与发布门 | ❌ | 交付面 |

## 5. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层实跑**用例数（ORGAN-PLAYBOOK §3.0） | 旧仓判定层实跑 **X = 424** / 新仓实跑 **N = 481** / **过**（N ≥ X，差 +57） | **过** |
| 2 | README 示例命令 rc 相同 | **结构不可比**：来源 README 的示例全部以**文件**为输入（`normalize 报告.pdf` / `ledger 报告.pdf` / `export 报告.pdf` …），器官按 SKELETON-SPEC §2 只收**已解析的结构化记录**；实测 `normalize data/samples/cases/case-006-boundary-closed.txt` → **rc 1**（"无法识别的输入类型（.txt）"），即来源工具自己也不吃样例的 txt。替代实测：来源 `data/samples/truth` 的 **20 条真值记录逐条判定一致**（§11）；另 `indicators` / `bench` → rc 0 属产品层命令，无器官对应物。rc 差异的产品级原因见 §3.3 | **不过（不可比）** |
| 3 | 测试文件数 / 测试函数数 | **口径乙（2026-11-25 用户裁决）**：文件数**按域计** → 本器官 **1 文件**（容器数 ≠ 覆盖数）/ 旧仓判定层 **20 文件**（`test_export.py` 属导出面，按 §6.1 口径排除；`audits/` 里记的 21 是未过滤数）；函数数**按条计** → 本器官 **481** / 旧 **392** | **过**（函数数 481 ≥ 392；实跑 = 函数数 = 481） |
| 4 | `pip wheel` 后 `data/` 进包 | wheel 内 `clauseproof/packs/checkup-ranges/data/` **2 条**（`clauses.json` `indicators.yaml`） | **过** |

### 6.1 判定层 20 文件处置表（进分母）

| 旧测试文件 | 函数 | 处置 |
|---|---|---|
| `test_engine.py` | 25 | **逐条搬**：四态比较/边界/单侧/三级优先/sex 门 → §四/§五/§六/§七（25 条对应） |
| `test_loader.py` | 33 | 知识库装载门 → **漂移门 §二**（19 条 × 字段/别名/单位/来源/状态）+ `test_registry_standard_is_explicit_for_every_entry`；**舍弃** YAML 解析器自身的容错分支（器官不读 YAML，解析面不存在） |
| `test_samples.py` | 24 | **搬**：20 条真值逐条判定 → §十一（参数化 20 条）+ 3 条结构门 |
| `test_normalize.py` | 32 | 名称/单位归一 → §三（别名 89 条、单位 52 条参数化）；**舍弃**：报告行解析正文（原始文本切分是摄取层，非判定） |
| `test_ledger.py` | 17 | **舍弃**：SQLite schema/唯一键/upsert（存储层）。其判定侧不变量（flag 取值、range_source 三态）由 §四/§九 接管 |
| `test_exit_codes.py` | 17 | **部分搬**：0/1/2/3 四条通路 → §十二（7 条）；**舍弃**：`version`/`selftest`/`bench`/`ingest` 等子命令的码面（器官无子命令） |
| `test_report.py` | 24 | **舍弃**：报告/图表渲染（输出排版属产品层） |
| `test_ingest.py` | 30 | **舍弃**：PDF/OCR 摄取（I/O） |
| `test_ingest_fixtures.py` | 11 | **舍弃**：同上（摄取夹具） |
| `test_determinism.py` | 13 | **部分搬**：账本两次运行逐字节一致 → §九（2 条）；**舍弃**：文件写盘确定性/HTML 指纹（产品层） |
| `test_frozen.py` | 41 | **舍弃**：PyInstaller 冻结与发布面；本产品发布物是 wheel + 源码 zip，由本仓 M6 门接管 |
| `test_layering.py` | 48 | **部分搬**：内核零 I/O/零时钟/零打印的 AST 门 → §一（2 条）；**舍弃**：跨模块分层矩阵（本器官只有 3 个模块，无分层可言） |
| `test_no_literal_thresholds.py` | 9 | **搬其精神**：区间数值只许在 `registry.py`（本文件用漂移门 + `engine.py` 无区间字面量的 AST 断言代替；区间字面量扫描面 = `engine.py`） |
| `test_pii_gate.py` | 14 | **舍弃**：PII 脱敏门（器官收结构化数据，不含姓名/身份证；脱敏在摄取层） |
| `test_paths.py` | 15 | **舍弃**：数据目录定位/环境变量解析（器官不读环境、不定位路径；由内核 `--basis` 参数取代） |
| `test_config.py` | 10 | **舍弃**：配置加载（器官无配置） |
| `test_readme_gate.py` | 12 | **舍弃**：README↔CLI 五面对账；由本仓 `tests/test_readme_gate.py`（旧包门）与本器官 docs 承接 |
| `test_encoding.py` | 8 | **舍弃**：编码探测/解码（摄取层） |
| `test_line_endings.py` | 5 | **舍弃**：行尾归一（摄取层） |
| `test_no_stub_sentinels.py` | 4 | **搬其精神**：本器官无 `TODO/NotImplemented` 桩，由 §一 的 AST 门（无 argparse/无 I/O/无 print）+ 全量测试覆盖保证 |
| `test_export.py`（判定层外） | 17 | **剔除**（文件名含 `export`）：CSV/MD 导出属产品层 |

**为什么旧仓 392 条里有 239 条搬不过来**：`test_frozen` 41 + `test_layering` 48 + `test_pii_gate` 14 +
`test_paths` 15 + `test_config` 10 + `test_encoding` 8 + `test_line_endings` 5 +
`test_readme_gate` 12 + `test_no_stub_sentinels` 4 + `test_ledger` 17 + `test_report` 24 +
`test_ingest` 30 + `test_ingest_fixtures` 11 = **239**，测的是 I/O、存储、渲染、PII、路径、编码与发布面——
器官按执行约束一律不能承载。可承载的 153 条（`test_engine` 25 + `test_loader` 33 + `test_samples` 24 +
`test_normalize` 32 + `test_exit_codes` 17 + `test_determinism` 13 + `test_no_literal_thresholds` 9）
**已全部搬完**，并把每条规则的数据门**逐条展开为具名用例**（19 条目 × 数据门/三态/边界、
105 条指标名、52 条单位别名、24 条主体适用域、20 条来源真值），因此新仓 **481 条全部是具名
`def test_`**，本文件不再使用 `parametrize`。