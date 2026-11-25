# 器官 `labeling-claims`

> 条文判定器官 · 版本 `0.2.0` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：《人工智能生成合成内容标识办法》（国信办通字〔2025〕2 号）+ 强制性国标 **GB 45438-2025**
> 条文库坐标：`2025-09-01`

一句话：**给一件 AI 生成合成内容（标识卡），逐条判它有没有按国标和办法做显式/隐式标识，
每条结论挂到可点的条款锚点上**。

## 1. 输入

唯一入口（器官不带自己的 CLI）：

```bash
clauseproof check labeling-claims \
  --input samples/labeling-claims/card-text-basic.json \
  --basis src/clauseproof/packs/labeling-claims/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `card_id` | ✅ | 件唯一标识（非空字符串） |
| `carrier` | ✅ | 载体：`text` / `image` / `audio` / `video` |
| `content_sha256` | ✅ | 内容指纹，64 位小写 hex |
| `explicit` | — | 显式要素数组，每项 `{element, present, position?, value?}` |
| `implicit` | — | 隐式字段字典（容器原始键 → 值），键经映射表归一 |
| `source` | — | `synthetic` / `manual` / `parsed`，默认 `manual` |
| `scenario` | — | `authored`（默认）/ `exported` / `propagated` |
| `observed` | — | `{"explicit": bool, "implicit": bool}`，默认都为 `true` |
| `implicit_duplicate_keys` | — | 解析通路据实登记的"出现多于一次"的容器键 |
| `notes` | — | 人工备注，不参与判定 |

`Pack` 声明的必填面只有前三个字段（`explicit` / `implicit` 缺省即为空，与来源产品口径一致）；
其余字段由器官在判定前校验——不合法一律退出码 **2**。

```json
{
  "card_id": "SAMPLE-TEXT-0001",
  "carrier": "text",
  "content_sha256": "31e27b3cefccd2bedc76c1e5298aacccb9af4e31003290b96579b4c60fb031b8",
  "explicit": [
    {"element": "text_explicit_notice", "present": true, "position": "head",
     "value": "本内容由人工智能生成合成"}
  ],
  "implicit": {
    "AIGC:Label": "1",
    "AIGC:ContentProducer": "SYN-0001",
    "AIGC:ProduceID": "SYN-C120797"
  }
}
```

## 2. 规则

规则表冻结在 `src/clauseproof/packs/labeling-claims/rulebook.py`（Python 字面量，
**器官不读文件**），出处逐字留档在 `data/{labeling-measures,gb45438-2025}.json`，由测试
「漂移门」逐字段比对。

**34 条 = 27 条生效（`verified`）+ 7 条待核对（`pending`）**。待核对条目**绝不进入判定路径**，
只在账本里登记一行 `ruleset.pending`（让人看见"还有 7 条没核对"，而不是当它不存在）。

| 维度 | 取值 | 语义 |
|---|---|---|
| `scope` | `explicit` / `implicit` | 显式标识（画面/文字）与隐式标识（文件元数据） |
| `carrier` | 空 = 全载体；否则精确匹配 | 载体内规则互不串台 |
| `scenario` | 空 = 全场景；否则精确匹配 | 不命中 → **不适用**（不是违规） |
| `check_type` | `presence`/`position`/`enum`/`pattern`/`type`/`range`/`unique` | 缺值时只有 `presence` 判违规，其余判"无法核验" |
| `severity` | `critical`/`major`/`minor` | **只进 evidence**：账本三态里 `fail` 一律阻断 |

字段映射（`data/national-fields.json`，5 个国标字段）：`content_property` ←
`AIGC:Label`（及 3 个别名）；`content_producer` ← `AIGC:ContentProducer`；
`content_id` ← `AIGC:ProduceID`；`content_propagator` ← `AIGC:ContentPropagator`/
`Propagator`；`propagate_id` ← `AIGC:PropagateID`/`PropagatorID`。别名**声明序敏感**：
取第一个命中者，其余记入 `evidence.alternatives`（不静默丢弃）。

四条判定纪律（来源产品口径，逐条保留）：

1. `presence` 缺值 → `fail`；其余 `check_type` 缺值 → **不判定**（缺值不臆测合规）；
2. `present: true` 但缺 `position` → 不判定（位置约束无法核验）；
3. 场景不适用 → 不判定（把"不适用"判成违规是冤枉用户）；
4. 作用域 `observed: false` → 该 scope 全部不判定（解析通路看不到渲染后的文字/语音）。

## 3. 输出

### 3.1 账本映射（SKELETON-SPEC §3–§5）

| 来源状态 | clauseproof `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| `pass` | `pass` | 否 | 必带 |
| `fail` | `fail` | **是**（退出码 1） | **必带** |
| `unknown` | `not_applicable` + message「未判定（`<code>`）：…」 | 否 | 带（条款存在，只是判不了） |
| `skipped` | `not_applicable` + message「未判定（`scenario_not_applicable`）：…」 | 否 | 带 |
| `pending` | `not_applicable` 登记行 `ruleset.pending` | 否 | 无（未核对的条目没有可引用的已核条款） |

`evidence` 固定携带 `scope` / `target` / `code` / `severity` / `scenario` 以及判定观测值
（`observed` / `expected` / `observed_key` / `alternatives` / `duplicated` / `applies_to`），
所以"来源工具的错误码与严重度"在账本里一条不丢。

### 3.2 人读

```text
clauseproof :: labeling-claims 0.2.0 :: card-text-basic.json
[pass] gb45438:explicit:text.notice.presence — 显式标识要素存在 :: GB 45438-2025/5.1 a) (2025-09-01)
[pass] gb45438:implicit:implicit_label.uniqueness — 文件元数据隐式标识仅保留一份 :: GB 45438-2025/6.1 c) (2025-09-01)
[not_applicable] measures:explicit:export.file.label.presence — 未判定（scenario_not_applicable）：场景不适用（本条仅适用于 exported）：authored :: 《人工智能生成合成内容标识办法》（国信办通字〔2025〕2 号）/第四条第二款 (2025-09-01)
[not_applicable] ruleset.pending — 7 条待核对（status=pending）条目未进入判定路径：… :: 无锚点
合计 16 条，阻断 0 条（pass=11 fail=0 na=5）
```

### 3.3 机读（`--json`，节选）

```json
{
  "product": "clauseproof",
  "organ": "labeling-claims",
  "organ_version": "0.2.0",
  "subject": "card-text-basic.json",
  "summary": {"blocking": 0, "total": 16,
              "verdicts": {"pass": 11, "fail": 0, "not_applicable": 5}},
  "records": [
    {
      "id": "gb45438:explicit:text.notice.ai_element@gb45438:5.1:b1",
      "rule_id": "gb45438:explicit:text.notice.ai_element",
      "verdict": "pass",
      "message": "格式匹配",
      "basis_ref": {
        "clause_id": "gb45438:5.1:b1",
        "path": "GB 45438-2025/5.1 b) 1)",
        "version": "2025-09-01",
        "quote": "文本内容显式标识应含人工智能要素：包含“人工智能”或“AI”"
      },
      "evidence": {
        "scope": "explicit", "target": "text_explicit_notice", "code": "",
        "severity": "major", "scenario": "authored",
        "observed": "本内容由人工智能生成合成", "expected": ".*(人工智能|AI).*"
      }
    }
  ]
}
```

同一输入两次运行**逐字节一致**（无时间戳、无绝对路径、无随机；账本由内核统一排序）。

### 3.4 退出码

| 码 | 触发 |
|---|---|
| `0` | 无 `fail`（含全部"不适用"/登记行） |
| `1` | 有 `fail`（任一条显式或隐式标识缺失/不合规） |
| `2` | 输入不合法（标识卡结构缺陷、文件缺失、JSON 坏） |
| `3` | 契约违约（条文库缺条款、条文库版本不符、器官不存在） |

## 4. 移植边界（哪些面**没有**搬过来，为什么）

来源产品是个完整交付物（CLI + GUI + 批量扫描 + 双轨报告 + 基准 runner + 打包）。
器官按 SKELETON-SPEC §2「器官不得引入自己的参数解析器、配置文件、输出排版」，
只搬**判定面**：

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 规则库 + status 双重门控 | ✅ | `rulebook.py` 字面量 + `rules_for()` 只放行 `verified` |
| 字段映射（别名归一、歧义检测） | ✅ | `engine.resolve_fields` + 漂移门 |
| 显式/隐式判定引擎 | ✅ | `engine.check_explicit` / `check_implicit`（逐条对齐） |
| 分级（`compliant`/`partial`/`non_compliant`） | ❌ | 账本只有三态；严重度进 `evidence`，`fail` 一律阻断（与来源退出码语义一致） |
| 容器解析（PNG/JPEG/MP4/M4A） | ❌ | 读字节属于输入通路（I/O），器官只收已解析的标识卡 |
| CLI / 批量扫描 / 报告渲染 / SARIF / HTML | ❌ | 产品层与零件层职责，器官不得自带 |
| GUI / 打包 / 基准 runner | ❌ | 交付面，不属于判定语义 |

## 5. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层实跑**用例数（ORGAN-PLAYBOOK §3.0） | 旧仓判定层实跑 **X = 205** / 新仓实跑 **N = 229** / **过**（N ≥ X，差 +24） | **过** |
| 2 | README 示例命令 rc 相同 | 旧：`labelcheck check data/samples/card-text-basic.json` → **0**；新：`clauseproof check labeling-claims --input samples/labeling-claims/card-text-basic.json --basis …/clauses.json` → **0**。旧：`…card-image-metadata-stripped.json --json` → **1**；新同件 → **1**（源码态与 wheel 安装态各跑一次，一致） | **过** |
| 3 | 测试文件数 / 测试函数数 | **口径乙（2026-11-25 用户裁决）**：文件数**按域计** → 本器官 **1 文件**（容器数 ≠ 覆盖数）/ 旧仓判定层 **13 文件**；函数数**按条计** → 本器官 **229** / 旧 **202**（实跑 = 229） | **过**（函数数 229 ≥ 202；**整仓 32 文件 / 472 函数**口径不适用，逐文件处置见 §6.1） |
| 4 | `pip wheel` 后 `data/` 进包 | wheel 内 `clauseproof/packs/labeling-claims/data/` **4 条**（`clauses.json` `gb45438-2025.json` `labeling-measures.json` `national-fields.json`）；装入全新 venv 后两件示例 rc=0/1 | **过** |

### 6.1 判定层口径与脚手架测试处置表

**口径**（2026-11-25 拍板）：判据 1 的分母 = 旧仓**判定层**实跑用例数；判定层 = 文件名不匹配
`cli|gui|packaging|audit|desensit|guard|bench|infra|export|version|license|generat|docs?_|health|release|selftest|smoke` 的测试文件。

旧仓判定层 **13 文件 / 202 静态函数 / 实跑 205 passed**（多出的 3 条来自参数化）。
本器官 **1 文件 / 229 函数 / 实跑 229 passed**，差值 **+24**。

补测结构（不堆重复断言）：**27 条生效规则 × `pass`/`fail`/`not_applicable` 三态 = 81 条**
（每条都走真实规则表 + 真实条文库，不是探针），加 148 条结构门/漂移门/边界/机制用例
（34 条规则结构、四载体三场景门控、位置允许集、关键词分裂、待核对登记、作用域未观测、
标识卡输入契约、字段别名归一、账本映射与锚点、退出码 0/1/2/3、样例 parity、确定性、
条文库版本与缺条款、`check_type` 机制、规则筛选）。

**判定层 13 文件（进分母）处置：**

| 旧测试文件 | 函数 | 处置 |
|---|---|---|
| `test_engine_explicit.py` | 14 | 逐条搬到本文件 §七（14 条一一对应）；另由 §十四 的 16 条覆盖四载体三态 |
| `test_engine_implicit.py` | 16 | 逐条搬到 §八（16 条对应）；`unique` 四条 → §八 末 + §十四 |
| `test_engine_integrity.py` | 12 | 6 条纯分级函数随「分级」概念取消；其**可观测后果**三条分别接管：minor 级 fail 仍阻断 → §十四 的 minor 规则三态；`unknown` 不阻断 → §十四 各 `_na` 条；"未评估"不阻断 → `test_both_scopes_unobserved_yields_zero_blocking`。余 6 条端到端分级 → §十四 四载体全绿 + 边界件三态 |
| `test_evidence.py` | 10 | evidence 字段契约 → §七/§八 的 `observed`/`alternatives`/`observed_key`/`duplicated` 断言 + §十五「每条 fail 带 severity」 |
| `test_mapping.py` | 12 | 逐条搬到 §五（12 条对应）；另加 §二 的映射漂移门（5 字段 × 别名逐条比对冻结产物） |
| `test_model.py` | 23 | `LabelCard.from_dict` 的拒绝分支 → §四（17 条）；默认值/等价形态 → §四 `test_card_is_accepted_with_required_fields_only` + §十五 `test_empty_explicit_list_equals_absent_explicit`。**舍弃 3 条**：`to_dict` 回写与 `__repr__`（器官不做回写/排版） |
| `test_parse.py` | 21 | **舍弃**：容器字节解析（PNG/JPEG/MP4）属输入通路 I/O，器官只收已解析的标识卡（`--input` 只吃 JSON）；由产品的输入层承担 |
| `test_parse_regression.py` | 7 | **舍弃**：同上（容器回归样本） |
| `test_report.py` | 17 | **舍弃**：报告渲染属输出排版（SKELETON-SPEC §2 禁止器官自带）；由内核 `Report.as_lines/as_dict` 与其契约测试接管 |
| `test_rules_gate.py` | 23 | status 双重门控 → §九/§八 的 `pending` 门（`test_pending_*`、`test_*_na`）+ §二 漂移门（34 条状态逐条比对冻结产物）。**舍弃**：registry/active/sha256 装载门（数据已冻结成字面量，装载面不存在），其守卫由 §二 的 7 条漂移门接管 |
| `test_scan.py` | 19 | **舍弃**：批量扫描是产品层能力；单件 `check` 已覆盖同一条判定路径 |
| `test_scan_diff.py` | 14 | **舍弃**：两轮对账需要历史状态，无状态产品不做 |
| `test_scenarios.py` | 14 | 逐条搬到 §九（场景门控 6 条）+ §十（观测作用域 4 条）+ §四（卡片契约 3 条）+ §十五（场景端到端 2 条） |

**被剔除的脚手架 17 文件处置（不进分母，但一条不许默默丢）：**

| 旧测试文件 | 函数 | 接管方 / 舍弃理由 |
|---|---|---|
| `test_cli.py` | 42 | 旧 CLI 参数面 → 本仓唯一入口 `clauseproof.cli` + `tests/test_clauseproof_contract.py` 接管；器官不得自带 CLI |
| `test_benchmark_cases.py` | 17 | 基准用例集合 → 旧仓 benchmark runner 自持；clauseproof 无基准面，舍弃 |
| `test_benchmark_cli.py` | 7 | 同上（`bench` 子命令）→ 舍弃 |
| `test_benchmark_runner.py` | 13 | 同上（runner 指标）→ 舍弃 |
| `test_exports_v2.py` | 20 | SARIF / HTML 导出 → 产品层旁路，舍弃（本产品输出只有人读 + `--json`） |
| `test_generators.py` | 10 | 规则/映射生成器 → 数据已冻结为字面量；其守卫由 §二 漂移门接管 |
| `test_guard_ci.py` | 10 | CI 结构门 → 本仓 `.github/workflows/ci.yml` + `tests/check_workflows.py` 接管 |
| `test_guard_data.py` | 20 | 数据资产门 → §二 漂移门 + `test_data_dir_is_present_and_non_empty` 接管 |
| `test_guard_imports.py` | 15 | 零第三方/零网络/分层门 → 本仓 `medreview` 的零网络与零字面量门接管；器官侧由 §一 的 AST 门（无 argparse / 无 env / 无时钟 / 无 print）接管 |
| `test_gui_layering.py` | 7 | GUI 分层 → 无 GUI，舍弃 |
| `test_gui_services.py` | 19 | GUI 服务层 → 无 GUI，舍弃 |
| `test_gui_tabs.py` | 16 | GUI 页签 → 无 GUI，舍弃 |
| `test_infra.py` | 25 | 仓库基础设施/布局 → 本仓 M5 交付门（`tests/test_m5_delivery.py`）与 M6 发布门接管 |
| `test_license_metadata.py` | 7 | 许可证/元数据 → 本仓 `pyproject.toml` + M6 发布门接管 |
| `test_packaging.py` | 18 | PyInstaller / dist 打包 → 本产品发布物是 wheel + 确定性源码 zip，由本仓 M6 门接管；PyInstaller 面舍弃 |
| `test_version_pointer.py` | 6 | 版本指针 → 版本改由 `clauseproof.__version__` 与 `Pack.version` 承担，由 §一 器官契约接管 |
| `test_audit_desensitize.py` | 18 | 脱敏审计器机制 → 本仓 `tools/audit_repo.py` + `tests/test_m6_release.py` 接管（本机工作区按 slug 改名规则复跑：0 硬门命中，`DESENSITIZE_AUDIT_OK`） |

## 7. 已知边界

- 条文库版本是**单一值**（`2025-09-01`）。条文库版本不符 → 退出码 3，不做"尽力而为"的判定：
  版本漂移正是本产品要消灭的东西。
- 规则表与条文库是两份资产：规则表随器官（Python 字面量），条文库由用户 `--basis` 提供；
  两者的一致性由 `tests/test_labeling_claims.py` 的漂移门锁死。