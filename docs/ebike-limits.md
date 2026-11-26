# 器官 `ebike-limits`

> 条文判定器官 · 版本 `0.1.0` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：随包规则包四册（GB 17761-2024 整车 / GB 17761-2018 整车历史 / GB 43854-2024 电池 /
> GB 42296-2022 充电器；与来源仓 `data/rules/` **逐字节同 sha256**，基准日 2026-10-14）
> 条文库坐标：`2026-10-14`

一句话：**给一份车型参数卡，判关键参数符不符合 GB 17761—2024 / GB 43854—2024 /
GB 42296—2022 的强制限值，逐条挂标准条款号，并给跨标准统一结论**。

## 1. 输入

```bash
clauseproof check ebike-limits \
  --input samples/ebike-limits/profile-readme.json \
  --basis src/clauseproof/packs/ebike-limits/data/clauses.json
clauseproof check ebike-limits \
  --input samples/ebike-limits/profile-violation.json \
  --basis src/clauseproof/packs/ebike-limits/data/clauses.json --json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `profile_id` | ✅ | 车型档案稳定身份键（跨轮对账配对主键） |
| `params` | ✅ | `{参数名: {value, unit}}`；参数值一律字符串承载（避免 JSON float 精度损失）；支持列名形态（经字段映射归一） |
| `model_design_date` / `market_date` | — | 版本锚定日（设计日期优先；无日期不猜，要求显式指定） |
| `version_key` | — | 显式版本键（优先于日期锚定） |

## 2. 规则

### 2.1 三维限值矩阵（2024 册 10 条生效规则）

| 维度 | 标准 | 生效规则 | 门控排除 |
|---|---|---:|---:|
| 整车 | GB 17761-2024 | 10（车速 6.1.1.1 / 质量 6.1.3 铅酸·其他分支 / 塑料占比 6.5.1 / 电压 6.3.5 / 功率 6.3.3.1 / 超速断电 / 防篡改×3 6.8.x） | 0 |
| 整车（历史） | GB 17761-2018 | 2（质量 55 kg / 车速 25 km/h；**条款号 pending**——废止标准官方不提供全文） | 0 |
| 电池 | GB 43854-2024 | 0（型式试验类，无可参数化固定数值限值 → **不参与聚合**） | 2 |
| 充电器 | GB 42296-2022 | 1（空载输出电压 ≤42.4 V，据 5.5.4） | 2 |

四条口径原样保留：

1. **未提供参数绝不判为符合**——一条规则都不适用时整体记 `not_assessed`，
   绝不输出 `compliant`；
2. **status 门控**：`pending` 条目零参与核查路径，只进 excluded 集合并显式列出；
   `value` 必须为 null（待核对不许预填数值）；
3. **条款号核对纪律**：`clause_status` 与 `status` 分开跟踪；verified 必有条款号、
   pending 必为 null——**绝不编造条款号**；
4. **歧义列名绝不猜**（`mapping_uncertain` 显式未提供）。

### 2.2 判定四态与统一结论

`compliant` / `non_compliant` / `not_applicable` / `not_provided`；维度与整体结论按
"最弱优先"聚合：`non_compliant > not_provided > not_assessed > compliant`。
`applies_if` 三值逻辑（白名单小语言，不用 eval）：引用参数不可解析 →
`not_provided(condition_unknown)`（「不知道是否适用」≠「不适用」）。

### 2.3 单位归一（Decimal 全链路，禁 float）

换算系数表（数学常量）+ 单位别名表（随包映射节字面量）；可显式无损换算
（kg↔g↔t、km/h↔m/s、%↔‰、V↔mV、W↔kW）→ 换算后判定并降级 `warning`；
不可换算一律 `not_provided(unit_incompatible)`，绝不臆测。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| `non_compliant` | `fail` | **是**（退出码 1） | 四态契约（标准条款号在 evidence） |
| `compliant` | `pass` | 否 | 四态契约 |
| `not_provided` / `not_applicable` | `not_applicable` | 否 | 四态契约 / status 门控 |
| 门控排除条目（pending） | `not_applicable` | 否 | status 门控契约 |
| 统一结论（聚合） | `pass` | 随 fail | 未提供不判符合契约 |

`evidence` 携带机读判据：`state` / `param` / `standard` / `clause` /
`clause_status` / `op` / `limit` / `unit` / `observed` / `reason` / `severity`。

### 3.2 人读（profile-violation.json，退出码 1）

```text
clauseproof :: ebike-limits 0.1.0 :: profile-violation.json
[fail] ebike.finding:GB17761-2024-max_design_speed — non_compliant max_design_speed（GB 17761-2024）；条款 6.1.1.1；观测 30 km/h <= 限值 25 km/h :: 数据契约 / 判定四态 (2026-10-14)
[fail] ebike.finding:GB42296-2022-charger-no-load-output-voltage — non_compliant charger_no_load_output_voltage（GB 42296-2022）；条款 5.5.4；观测 48 V <= 限值 42.4 V :: 数据契约 / 判定四态 (2026-10-14)
[not_applicable] ebike.excluded:GB43854-2024-battery-type — GB 43854-2024：条目 battery_type 状态 pending，零参与核查路径（不参与判定） :: 数据契约 / status 门控 (2026-10-14)
[pass] ebike.result — 三维核查完成：non_compliant——不符合 6 / 未提供 0 / 不适用 1 / 符合 4；门控排除 4 条（pending 不参与判定） :: 数据契约 / 未提供不判符合 (2026-10-14)
合计 16 条，阻断 6 条（pass=5 fail=6 na=5）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无阻断（readme 合规样例：overall=not_provided——「未提供」不改退出码，与旧 CLI 同语义） |
| `1` | 有阻断（任一 `non_compliant`） |
| `2` | 输入不合法（缺 `profile_id`/`params`、`params` 非对象、文件缺失/坏 JSON） |
| `3` | 契约违约（条文库版本与规则包快照 `2026-10-14` 不符；缺契约条目 → `BasisMissing` → 3） |

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 规则包 schema 校验 + status 门控 + 同目标去重 | ✅ | `engine.build_ruleset`（逐字移植） |
| `applies_if` 三值逻辑（白名单小语言） | ✅ | `engine.eval_applies_if`（逐字移植） |
| 单位归一 + Decimal 比较 + 边界枚举 | ✅ | `engine.values` 面（逐字移植；换算系数=数学常量随包） |
| 四态判定矩阵 + 统一结论聚合 | ✅ | `engine.check_param` / `dimension_overall` / `check_profile` |
| 版本锚定（窗口来自 manifest） | ✅ | `engine.anchor_version`（窗口快照随包 + 漂移门） |
| 字段映射（变体/歧义/单位别名） | ✅ | `mapping.ParamMapping` / `normalize_params`（逐字移植） |
| 批量扫描 + 跨轮对账三集合 | ✅ | `engine.scan_profiles` / `reconcile_rounds`（判定面） |
| 版本差异对照（从规则包 diff 生成） | ✅ | `engine.version_diff_params`（纯函数 diff） |
| 规则包四册 + manifest | ✅ | `data/*.json` **逐字节同 sha256** 随包 + 漂移门 |
| 文件读取 / sha256 核对 / 数据目录解析 | ❌ | 输入层（器官装配面读随包文件，与 `Basis.from_json` 同形态） |
| CLI / 报告导出 / GUI / PyInstaller | ❌ | 产品级交付面（入口只有 `list` / `check`） |
| 基准八套件 / 真值库生成器 / 冻结守门 | ❌ | 产品级工具面（真值对账改由本器官测试承载） |
| XLSX 报告 / 演示素材 / 脱敏审计 | ❌ | 产品级交付面 |

## 5. 口径差（如实登记）

1. **规则包装载形态**：来源经数据目录解析（环境变量向上查找）+ sha256 核对；
   本器官改为**随包冻结资产**（与来源仓逐字节同 sha256，漂移门核对 manifest
   登记值），数据目录解析（环境变量）不迁——器官不读环境变量。
2. **退出码语义对齐产品契约**：旧 CLI「`not_provided` 不改退出码」的编排与
   SKELETON-SPEC §5 一致（NA → 0）；readme 样例旧 rc **0**（overall=not_provided）/
   新 rc **0**；越限样例旧 **1** / 新 **1**（判据 2 过，同 6 条 non_compliant）。
3. **三值聚合口径**：`not_applicable` 不作结论参与（同一参数常有多条互斥条件
   规则，结论由适用的那条决定）；零生效规则维度（电池册）不参与聚合——
   否则会把整体结论无谓拉成「未评估」。
4. **2018 册口径**：数值经 2024 版官方问答对旧版限值的引述核对（verified），
   条款号保持 pending（openstd 对废止标准不提供全文）——如实登记，不编造。
5. **profile_sha256 不迁**：来源 `profile_sha256` 依赖文件字节；器官收内存
   参数卡（跨轮对账主键是 `profile_id`，不是内容指纹——同一纪律）。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 185**（7 文件）/ 新器官实跑 **N = 185** | **过**（185 ≥ 185） |
| 2 | README 示例命令 rc 相同 | 旧 `ebikecheck check examples/sample-profile.json --json` rc **0**（compliant 5 / not_applicable 1 / not_provided 5，overall=not_provided）/ 新 `clauseproof check ebike-limits --input samples/ebike-limits/profile-readme.json --basis …` rc **0**（同四态计数逐值一致）；越限对照件旧 rc **1**（non_compliant 6：车速/质量/塑料占比/电压/功率/充电器空载电压，条款 6.1.1.1 / 6.1.3 / 6.5.1 / 6.3.5 / 6.3.3.1 / 5.5.4）/ 新 rc **1**（同 6 条同 rule_id 同条款同观测值） | **过**（0=0、1=1，逐值一致） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 185 ≥ 185；`def test_` **185** ≥ 旧层 AST **175**；文件数旧 7 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本（git archive HEAD + 新器官文件）`pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`；`clauseproof/packs/ebike-limits/data/` **6 件**（四册规则包 + manifest + clauses；四册+manifest 与来源逐字节同 sha256）；解包 `list` = **10 器官**、readme 样例 rc **0** / violation rc **1** | **过** |

**判据 1 的命令与输出原文**（来源仓只读；`PYTHONDONTWRITEBYTECODE=1`）：

```bash
cd <来源仓>
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_engine.py tests/test_gates.py tests/test_m2_dimensions.py \
  tests/test_m2_probes_and_units.py tests/test_m3_mapping_scan_reconcile.py \
  tests/test_m4_version_diff.py tests/test_profile_and_paths.py \
  -o addopts="" -q -p no:cacheprovider
# → 185 passed in 117.15s
```

**判据 2 的旧命令**（进程内捕获 JSON；输出指向 %TEMP%，来源仓 `git status` 保持 0 行）：

```bash
cd <来源仓>
PYTHONPATH=src py -X utf8 -c "… ebikecheck.cli.main(['check','examples/sample-profile.json','--json'])"
# rc=0；counts: {'compliant': 5, 'non_compliant': 0, 'not_applicable': 1, 'not_provided': 5}
# 越限对照件（车速 30/质量 70/塑料 8%/电压 60/功率 500/充电器 48V）：rc=1；
# counts: {'compliant': 4, 'non_compliant': 6, 'not_applicable': 1, 'not_provided': 0}
```

新命令：

```bash
clauseproof check ebike-limits \
  --input samples/ebike-limits/profile-readme.json \
  --basis src/clauseproof/packs/ebike-limits/data/clauses.json   # rc 0
clauseproof check ebike-limits \
  --input samples/ebike-limits/profile-violation.json \
  --basis src/clauseproof/packs/ebike-limits/data/clauses.json   # rc 1
```

### 6.1 D1 + D18 选文件与逐文件处置（7 文件 / 185 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `tests/test_engine.py` | 30 | 规则包校验/门控/装配 | **已迁**（§三/§四） |
| `tests/test_gates.py` | 37 | 零字面量门禁/契约 | **部分迁**：零限值字面量 1、契约 4 已迁；`check_zero_literals` 工具自扫 32 不迁（产品级工具面） |
| `tests/test_m2_dimensions.py` | 15 | 三维判定矩阵 | **已迁**（§七/§十二） |
| `tests/test_m2_probes_and_units.py` | 14 | 单位归一/边界 | **已迁**（§六） |
| `tests/test_m3_mapping_scan_reconcile.py` | 28 | 映射/扫描/对账 | **已迁**（§九/§十四） |
| `tests/test_m4_version_diff.py` | 30 | 版本差异对照 | **已迁**（§十四；diff 报告渲染不迁） |
| `tests/test_profile_and_paths.py` | 21 | 档案校验/数据目录 | **部分迁**：档案 schema 5 已迁（validate_subject）；数据目录解析（环境变量）12 不迁（器官不读环境变量）；sha256 文件核对 4 不迁（输入层） |

D1 + D18 剔除（不计入 X，5 文件）：

| 文件 | 命中词 | 处置 |
|---|---|---|
| `tests/test_cli.py` | `cli` | CLI 参数面 |
| `tests/test_license_metadata.py` | `license` | 打包元数据 |
| `tests/test_m5_demo_assets.py` | `generat`（演示素材） | 产品级交付面 |
| `tests/test_m5_gui.py` | D18 `panel`（GUI 四页签） | 桌面界面 |
| `tests/test_m5_report.py` | D18 `report` | 报告导出（MD/XLSX） |

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/gb17761-2024.json` | 来源仓 `data/rules/gb17761-2024.json` | **逐字节相同**（sha256 `1d00b3f0…`），wheel 进包 |
| `data/gb17761-2018.json` | 来源仓 `data/rules/gb17761-2018.json` | **逐字节相同**（sha256 `32d018bb…`），wheel 进包 |
| `data/gb43854-2024.json` | 来源仓 `data/rules/gb43854-2024.json` | **逐字节相同**（sha256 `6fd4dabc…`），wheel 进包 |
| `data/gb42296-2022.json` | 来源仓 `data/rules/gb42296-2022.json` | **逐字节相同**（sha256 `4c64e4f6…`），wheel 进包 |
| `data/manifest.json` | 来源仓 `data/rules/manifest.json` | **逐字节相同**（sha256 `fefbdee7…`），wheel 进包 |
| `data/clauses.json` | 8 条数据契约（由 `registry.clause_specs/clause_text` 生成） | 版本 `2026-10-14` |
| `samples/ebike-limits/profile-readme.json` | 来源仓 `examples/sample-profile.json` **逐字节转写** | 判据 2 新侧样例（rc 0） |
| `samples/ebike-limits/profile-violation.json` | readme 样例 + 6 参数越限改值（迁移时构造） | 判据 2 越限对照（rc 1） |
