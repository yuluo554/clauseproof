# 器官 `picrecall`

> 条文判定器官 · 版本 `2026-10-14` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：截图相似分组的**只读判定契约**（5 条数据契约：分组 / 保留 / 只读 / 阈值 / 账本）
> 条文库坐标 = 数据快照日期 `2026-10-14`

一句话：**给一批已计算 pHash 的截图指纹，按汉明距离阈值做相似分组，给出保留建议
（分辨率 → 大小 → mtime → 路径），逐组挂数据契约锚点；只出建议，不删除、不改名、
不写回任何用户文件。**

> **队列备注差异（如实登记）**：队列备注写「缺陷产品召回」，但本行来源目录
> 的实际来源是**截图文字检索库 picrecall**（picture recall =
> 图片检索，不是产品召回：`index` / `ocr` / `search` / `dedupe` 四命令）。
> 本器官按实际仓的**判定层**（相似分组 + 保留建议 + 只读纪律）迁移；
> 若队列原意是另一个「缺陷产品召回」来源仓，需另派一行（见 §5.1）。

## 1. 输入

```bash
clauseproof check picrecall \
  --input samples/picrecall/dedupe-dupes.json \
  --basis src/clauseproof/packs/picrecall/data/clauses.json
clauseproof check picrecall \
  --input samples/picrecall/dedupe-clean.json \
  --basis src/clauseproof/packs/picrecall/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `case_id` | ✅ | 一次判定运行的稳定标识（输入必填字段） |
| `dedupe.threshold` | — | 汉明距离阈值（非负整数；缺省 8） |
| `dedupe.items[]` | ✅ | 截图指纹：`path`（稳定身份键）+ `phash`（16 位十六进制）+ `width` / `height` / `size` / `mtime_ns` |

```json
{
  "case_id": "dupes-demo",
  "dedupe": {
    "threshold": 8,
    "items": [
      {"path": "dup_0001_base.png", "phash": "f85a8e2895b5cc8e",
       "width": 543, "height": 204, "size": 19867, "mtime_ns": 1},
      {"path": "dup_0001_hi_res.png", "phash": "f87a8e2895b5c88e",
       "width": 624, "height": 235, "size": 56716, "mtime_ns": 2}
    ]
  }
}
```

> **pHash 计算留在输入层**：图片解码、pHash（imagehash/PIL）与 SQLite 索引都不迁；
> 器官只收**已计算指纹**。这使判定纯整数运算、可逐字节复现，且零文件 IO。

## 2. 规则

### 2.1 相似分组

- 判据 = pHash **汉明距离 ≤ threshold**（默认 8；阈值单一来源，不读环境）；
- **单链聚类**：以 path 排序为起点，成员集合内任一成员与候选距离 ≤ 阈值即并入；
- 组内成员与组顺序按 `path` 排序（确定性）；读不出图的条目不参与、不中断。

### 2.2 保留建议优先级

每组恰一条 `keep`，其余 `redundant`。优先级：

```
分辨率（width × height，降序）
  → 文件大小（降序）
  → mtime_ns（降序）
  → path（字典序升序）
```

### 2.3 只读纪律

- 本器官**没有任何**删除/改名/写回用户文件的代码路径；
- 唯一写盘动作（CSV 建议清单）属交付层，不迁；
- `fail` 只表示「检出重复建议」，不代表任何自动动作。

### 2.4 阈值与数据

- 阈值默认 8，可被 `dedupe.threshold` 覆盖；负数/非整数 → 退出码 2；
- 随包 `phash-cases.json`（18 张 / 6 个近似重复族）与 `phash-clean.json`
  （3 张互不相似）由来源合成重复族图片**计算 pHash 后冻结**（图片二进制不入包）；
- 每条指纹必须 16 位十六进制（hash_size=8），否则退出码 2。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | 依据锚点 |
|---|---|---|---|
| 存在相似分组（≥2 张） | `fail`（组级） | **是**（退出码 1，对齐来源 `dedupe` 检出即 1） | `contract.dedupe` |
| 组内代表图（keep） | `pass` | 否 | `contract.keep` |
| 组内冗余图（redundant） | `not_applicable` | 否 | `contract.readonly` |
| 无相似分组（汇总） | `pass` | 否 | `contract.ledger` |

**输入不可用**（缺 case_id / 缺 dedupe / 指纹非法 / 阈值非法）→ `ValueError` →
退出码 2；条文库版本不符 → `ContractError` → 3；条款缺失 → `BasisMissing`
（本产品内核映射 2）。

### 3.2 人读（节选）

```text
clauseproof :: picrecall 2026-10-14 :: dedupe-dupes.json
[fail] picrecall.group:1 — 相似截图分组 1：3 张，建议保留 dup_0001_hi_res.png（其余 2 张为冗余建议；不删除任何文件） :: 数据契约 / 相似分组 (2026-10-14)
[fail] picrecall.group:2 — 相似截图分组 2：3 张，建议保留 dup_0002_hi_res.png（其余 2 张为冗余建议；不删除任何文件） :: 数据契约 / 相似分组 (2026-10-14)
[fail] picrecall.group:3 — 相似截图分组 3：3 张，建议保留 dup_0003_hi_res.png（其余 2 张为冗余建议；不删除任何文件） :: 数据契约 / 相似分组 (2026-10-14)
[fail] picrecall.group:4 … 5 … 6 …
[pass] picrecall.summary — 相似分组：6 组（18 张入组 / 输入 18 张，阈值 8）；只出建议，不删除任何文件 :: 数据契约 / 账本口径 (2026-10-14)
合计 25 条，阻断 6 条（pass=7 fail=6 na=12）

clauseproof :: picrecall 2026-10-14 :: dedupe-clean.json
[pass] picrecall.summary — 相似分组：0 组（0 张入组 / 输入 3 张，阈值 8）；只出建议，不删除任何文件 :: 数据契约 / 账本口径 (2026-10-14)
合计 1 条，阻断 0 条（pass=1 fail=0 na=0）
```

与来源 `picrecall dedupe` 的**6 组**输出一致（每组 3 张，hi_res 保留）。

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 无相似分组（或无组可判） |
| `1` | 存在相似分组（组级 `fail`；与来源 dedupe 检出即 1 对齐） |
| `2` | 输入不合法（缺 case_id / 指纹非法 / 阈值非法） |
| `3` | 契约违约（条文库版本 ≠ `2026-10-14`；条文库自相矛盾） |

> **漏 `--basis`** → 条文库版本为空 → 版本不符 → **退出码 3**，是契约正确行为。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| pHash 相似分组（单链聚类） | ✅ | `engine.group_items`（整数汉明距离，纯函数） |
| 保留建议优先级 | ✅ | `engine.choose_representative` |
| 只读纪律 | ✅ | 引擎无删除/改名/写回调用（AST 守门） |
| 阈值单一来源 | ✅ | 输入 `dedupe.threshold`；随包样例记录默认 8 |
| 建议清单 CSV | ❌ | 交付层（唯一写盘动作，留产品层） |
| 图片解码 / pHash 计算（PIL/imagehash） | ❌ | 输入层；器官只收指纹 |
| SQLite 索引 / 增量扫描 | ❌ | 输入/存储层 |
| OCR（RapidOCR）与全文检索（FTS5） | ❌ | 输入/交付层；判定面与分组无关 |
| CLI / GUI / 基准 / 自检 | ❌ | 交付面；入口只有 `list` / `check` |
| 数据目录定位 | ❌ | 输入层；器官固定随包目录 |

## 5. 口径差（如实登记）

1. **队列备注与实际仓不符**：备注「缺陷产品召回」，实际为截图检索库（picture recall）。
   本器官按实际仓迁移**相似分组判定面**；如队列原意另有来源仓，需另派一行。
2. **输入从图片文件变成指纹**：pHash 计算（PIL/imagehash）留输入层；器官纯整数运算。
3. **CSV 写盘不迁**：来源 `dedupe --out keep-suggestions.csv` 是唯一写盘动作；器官只出账本。
4. **账本化输出**：组级 `fail` + 每张图的 keep/redundant 记录 + 汇总；
   `fail` 只表示「检出重复建议」，不触发任何删除。
5. **阈值入输入**：来源阈值来自 `config.PHASH_MAX_DISTANCE`；器官由
   `dedupe.threshold` 显式提供（缺省 8），不读环境。
6. **数据为来源合成族计算快照**：`phash-cases.json` 的 18 条指纹由来源
   `data/synthetic_dupes/` 图片计算后冻结（图片二进制不入包）；族内距离 ≤6、族间 ≥56。
7. **与既有器官零复用**：slug / 规则代码 / 测试文件均不复用。

### 5.1 待拍板

- 若「缺陷产品召回」是独立来源仓（例如 product-recall 类工具），请给出来源目录；
  本行来源目录不含召回判定逻辑（README 是截图索引/检索）。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 101**（12 文件；`test_readme_gate` 12 函数中 1 条 quickstart 子进程门在本机未安装态失败，passed 计 11） | **过**（102 ≥ 101） |
| 2 | README 示例命令 rc 相同 | 旧 `picrecall index data/synthetic_dupes --db <tmp>` → **0**；随后 `picrecall dedupe --db <tmp> --out <tmp>` → **1**（6 组，每组建议保留 hi_res）/ 新 `check picrecall …/dedupe-dupes.json` → **1**（6 组，同保留建议）；干净对照旧 `index data/synthetic` + `dedupe` → **0**（0 组）/ 新 `…/dedupe-clean.json` → **0**（0 组） | **过**（1=1，6 组一致；0=0） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 102 ≥ 101；AST `test_` 函数 **102** ≥ 旧层 **100**；文件数旧 12 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（**261 条目 / 828486 B**）；`picrecall/data/` **4 件 / 6863 B**；解包 `list` = **18 器官**、干净样例 rc **0** | **过** |

**判据 1 的命令与输出原文**（来源仓只读，`PYTHONDONTWRITEBYTECODE=1`）：

```bash
cd <来源仓>
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_data_ledger.py tests/test_dedupe_groups.py \
  tests/test_dedupe_readonly.py tests/test_index_incremental.py \
  tests/test_k10_threshold_single_source.py tests/test_ocr_pipeline.py \
  tests/test_readme_gate.py tests/test_regression_m0.py \
  tests/test_schema_notes.py tests/test_search_end_to_end.py \
  tests/test_segment.py tests/test_serialize.py \
  -o addopts="" -q -p no:cacheprovider
# → 1 failed, 101 passed, 2 skipped in 3.91s
```

逐文件 passed：data_ledger 7 / dedupe_groups 6 / dedupe_readonly 6 /
index_incremental 13 / k10 4 / ocr_pipeline 11 / readme_gate 11（1 条 quickstart
子进程门因本机未安装态失败）/ regression_m0 6 / schema_notes 8 / search_end_to_end 12 /
segment 11 / serialize 6 = **101**；旧层 AST `test_` 函数 = **100**。

> **D1 机械口径说明**：`test_readme_gate.py`（12）、`test_data_ledger.py`（7）、
> `test_schema_notes.py`（8）等名字不含 D1/D18 排除词，**机械计入分母**，不按域手剔
> （#10 审计 §3.1 的纠正口径）。其判定值由 §6.1 逐文件处置。

### 6.1 D1 + D18 选文件与逐文件处置（12 文件 / 101 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `test_index_incremental.py` | 13 | 增量索引状态机 | **不迁**（输入/存储层；器官只收指纹） |
| `test_search_end_to_end.py` | 12 | FTS 检索语义 | **不迁**（检索交付面） |
| `test_readme_gate.py` | 11（1 failed） | README/命令面门 | **不迁**（产品级文档门；失败条为未安装态子进程） |
| `test_ocr_pipeline.py` | 11 | OCR 流水线 | **不迁**（输入层；依赖重） |
| `test_segment.py` | 11（2 skipped） | 中文分词 | **不迁**（检索交付面） |
| `test_schema_notes.py` | 8 | 数据 schema 说明 | **不迁**（数据文档门） |
| `test_data_ledger.py` | 7 | 数据台账 | **不迁**（数据文档门） |
| `test_dedupe_groups.py` | 6 | 重复族分组 | **已迁**（§2.1；测试 §三/§五） |
| `test_dedupe_readonly.py` | 6 | 只读纪律（AST + 文件不变） | **已迁**（§2.3；测试 §六） |
| `test_serialize.py` | 6 | CSV 写盘 | **不迁**（交付层）；组行结构由 §四 接管 |
| `test_regression_m0.py` | 6 | M0 回归 | **部分迁**：数据/命令契约由 §八 接管 |
| `test_k10_threshold_single_source.py` | 4 | 阈值单一来源 | **已迁**（§2.4；测试 §五） |
| **合计** | **101** | — | 已迁 3 / 部分迁 1 / 不迁 8 |

**D1 + D18 剔除（不计入 X，3 文件 / 54 passed）**：

| 来源测试文件 | passed | D1 词 | 去向 |
|---|---:|---|---|
| `test_bench_rules.py` | 22 | `bench` | 基准规则（产品级基准面） |
| `test_cli_contract.py` | 20 | `cli` | 旧 CLI 子命令/退出码（新入口只有 `list`/`check`） |
| `test_bench_check.py` | 12 | `bench` | 基准一致性检查（产品级基准面） |

### 6.2 判据 2 对撞（旧命令 vs 新入口）

| 场景 | 旧命令 → rc | 新命令 → rc | 结论 |
|---|---|---|---|
| 近似重复族（6 族 × 3） | `picrecall index data/synthetic_dupes --db <tmp>` → **0**；`picrecall dedupe --db <tmp> --out <tmp>` → **1**（6 组） | `check picrecall --input …/dedupe-dupes.json --basis …` → **1**（6 组，同 hi_res 保留） | **过**（1=1） |
| 干净对照（60 张独立截图） | `picrecall index data/synthetic --db <tmp>` → **0**；`picrecall dedupe …` → **0**（0 组） | `check … --input …/dedupe-clean.json` → **0**（0 组） | **过**（0=0） |
| 漏 `--basis` | 旧无概念 | `check … --input …/dedupe-clean.json` → **3** | 契约正确行为 |

> 旧侧索引库与 CSV 均在 `%TEMP%`；来源仓全程 `git status --porcelain` = 0 行。

### 6.3 判据 4 的进包清单（`%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation`）

wheel：`clauseproof-0.0.0-py3-none-any.whl`（828486 B，**261 条目**）；
`clauseproof/packs/picrecall/data/` **4 件 / 6863 B**：

| 文件 | bytes | 来源 |
|---|---:|---|
| `clauses.json` | 1830 | 5 条数据契约 |
| `phash-cases.json` | 3968 | 来源合成重复族 18 张的 pHash 计算快照 |
| `phash-clean.json` | 591 | 来源合成集 3 张独立截图 |
| `manifest.json` | 474 | 逐文件 sha256 / bytes / 条文数登记 |

解包后 `clauseproof list` = **18 器官**；干净样例 rc **0**。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/phash-cases.json` | 来源 `data/synthetic_dupes/`（18 张 / 6 族） | pHash 计算后冻结；族内距离 ≤6、族间 ≥56 |
| `data/phash-clean.json` | 来源 `data/synthetic/`（3 张独立） | 两两距离 >8，无组 |
| `data/clauses.json` | 5 条数据契约 | 版本 `2026-10-14` |
| `data/manifest.json` | 本器官装配产物 | 漂移门：bytes + sha256 + clause_count |
| `samples/picrecall/dedupe-dupes.json` | `phash-cases.json` 的输入形态 | 判据 2 主样例（rc 1，6 组） |
| `samples/picrecall/dedupe-clean.json` | `phash-clean.json` 的输入形态 | 干净对照（rc 0） |

> 指纹来自来源仓**合成**截图（白名单文本、假号码），不含真实用户截图。