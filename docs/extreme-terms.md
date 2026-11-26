# 器官 `extreme-terms`

> 条文判定器官 · 版本 `0.0.1` · 迁自 target-map ① 行（只读迁移，来源仓一字未改）
> 依据：词表快照 `2026-10-15`（133 条词条，**全部 `verified`**）+ 五条《广告法》条款原文 +
> 《医疗广告管理办法》第七条
> 法条坐标：`2026-10-15`

一句话：**给一段广告文案，判命中哪些绝对化/违禁用语，并把每条命中挂到法条原文锚点上**。

> 词表是**公开整理的非官方快照**（来源仓 README 明示），本器官不把它称作「官方违禁词库」；
> 判定依据是条款原文，词表只是**待匹配的措辞集合**。

## 1. 输入

```bash
clauseproof check extreme-terms \
  --input samples/extreme-terms/readme-example.json \
  --basis src/clauseproof/packs/extreme-terms/data/clauses.json
clauseproof check extreme-terms \
  --input samples/extreme-terms/multi-category.json \
  --basis src/clauseproof/packs/extreme-terms/data/clauses.json --json
clauseproof check extreme-terms \
  --input samples/extreme-terms/clean.json \
  --basis src/clauseproof/packs/extreme-terms/data/clauses.json
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `text` | ✅ | 待扫描文案（字符串；BOM 剥离、CRLF/CR 归一为 LF 后计数） |
| `context_window` | — | 命中上下文窗口（词面左右各取多少码点；缺省 10，0 = 只回词面） |

```json
{"text": "本款产品是全效之王，销量第一。", "context_window": 10}
```

> **文件读取不进器官**：编码判定（只收 UTF-8）、stdin 通路、stdout 排版都留在输入层
> （`SKELETON-SPEC` §2：器官不得做文件 IO）。器官只吃**已解码文本**。

## 2. 规则

### 2.1 词条门控（四步，加载侧再拦一次）

| 步骤 | 条件 | 不满足 |
|---|---|---|
| 1 | `status == verified` | 不生效 |
| 2 | 锚点字段齐全 | 不生效 |
| 3 | 锚点条款在条文库里 | 不生效 |
| 4 | `basis=literal` 时**词面逐字出现在条款原文** | 不生效 |

不生效的词条**必须列进未启用清单**（记一条 `not_applicable`），绝不静默按最宽松规则扫。
随包 133 条全部通过四步（`literal` 12 条 / `variant` 121 条）。

### 2.2 扫描语义

- **左→右、长词优先、非重叠**（前缀树编译；`第一品牌` 命中不回退成 `第一`）；
- **同位置同词多类别各记一条**；同词同类别只记一次；
- 位置按 **Unicode 码点**、行号列号 **1 起**，CRLF/CR 先归一为 LF；
- 输出排序稳定：`(line, col, category, word)`；
- `suggestion` **只来自词表内置字段**，不做自由生成。

## 3. 输出

### 3.1 账本映射

| 来源结论 | `verdict` | 阻断 | `basis_ref` |
|---|---|---|---|
| 命中词条 | `fail` | **是**（退出码 1） | 该词条的法条条款（`广告法/第九条` 等） |
| 零命中（汇总记录） | `pass` | 否 | 词表契约 |
| 词条未生效 | `not_applicable` | 否 | **无**（无锚点可引正是它被拦下的原因） |

`evidence` 携带机读事实：`word` / `category` / `risk` / `line` / `col` / `context` /
`suggestion`；汇总记录另带 `hits` / `active` / `inactive` / `risk_counts`。

### 3.2 人读（README 示例，退出码 1）

```text
clauseproof :: extreme-terms 0.0.1 :: readme-example.json
[fail] scan.result — 命中 1 条（生效词条 133 条；风险分布 high=1） :: 数据契约 / 词表门控 (2026-10-15)
[fail] term:绝对化用语:销量第一:L1C11 — 命中极限/违禁用语「销量第一」（类别 绝对化用语，风险 high；上下文：本款产品是全效之王，销量第一。）——删除绝对化表述，改为可核实的客观描述（如具体数据并附出处） :: 《中华人民共和国广告法》 / 第九条 (2026-10-15)
合计 2 条，阻断 2 条（pass=0 fail=2 na=0）
```

### 3.3 退出码

| 码 | 触发 |
|---|---|
| `0` | 零命中（含全部词条未生效的情形） |
| `1` | 有命中（每条命中 + 一条汇总记录都阻断） |
| `2` | 输入不合法（缺 `text`、`text` 非字符串、`context_window` 非法、文件缺失） |
| `3` | 契约违约（条文库版本与词表坐标不符、词表契约条款缺失） |

> 漏 `--basis` 时条文库版本为空 → 版本不符 → **退出码 3**，是契约的正确行为。
> 注：条文库**已有版本但缺某条法条**时，词条只会「不生效」而不是让整次扫描失败；
> 只有**词表契约**本身缺失才会以 `BasisMissing` 冒到 CLI。

## 4. 移植边界

| 来源面 | 是否搬 | 说明 |
|---|---|---|
| 词条门控（status / 锚点 / literal 自证） | ✅ | `engine.load_entries` |
| 前缀树编译 + 左→右长词优先非重叠 | ✅ | `engine.build_dfa` / `scan_line` |
| 命中位置 / 上下文 / 建议 | ✅ | `engine.make_hit`（字段序固定） |
| 条文库版本与词表坐标对齐 | ✅ | 版本不符 → 契约违约 |
| 文件读取 / 编码判定 / stdin | ❌ | 输入层（器官不读文件） |
| stdout 排版（JSON / 文本两轨） | ❌ | 输出排版属产品层 |
| LLM 分层判定（语境豁免 / 品类识别 / 改写生成） | ❌ | 不迁：器官零 LLM；`suggestion` 只取词表字段 |
| Skill 包装（SKILL.md / 安装演练 / 交付三件套） | ❌ | 交付面 |
| 真值基准（148 cases exact-match） | ❌ | 产品级基准；判据 2 用 README 示例逐值对账 |

## 5. 口径差（如实登记）

1. **输入从文件变成文本**：器官收已解码 `text`；文件读取、UTF-8 编码门、stdin 通路留输入层。
2. **零命中有一条汇总记录**：来源是无命中则输出空数组；器官额外记 `scan.result`
   （`pass`）——否则「空账本」无法区分「跑过没命中」与「没跑」。
3. **未生效词条显式入账**：来源把未启用清单打到 stderr；器官记 `not_applicable`
   （无锚点 + 理由），**不影响退出码**。
4. **LLM 分层判定不迁**：语境豁免、品类识别、合规改写建议都在会话内由 LLM 完成
   （来源 `references/judgment-protocol.md`），器官只做确定性扫描；`suggestion`
   仍只取词表字段，不自由生成。
5. **条文库缺法条 ≠ 整次失败**：缺某条法条时该条款下的词条「不生效」并显式列出
   （来源同口径）；只有词表契约条款缺失才会 `BasisMissing` → 退出码 2（内核把它归入
   「输入不可用」；`ORG-PLAYBOOK` §4 的口径是 3，实际实现为 2，未改内核）。
6. **词表是非官方整理**：来源 README 明示「公开整理的非官方快照，判定以法条原文为准」；
   本器官原样保留该声明，不把它写成官方清单。

## 6. §7.3 四项判据（实测留档）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓**判定层**实跑用例数（D1 + **D18**） | 旧仓判定层实跑 **X = 50**（5 文件）/ 新器官实跑 **N = 114** | **过**（114 ≥ 50） |
| 2 | README 示例命令 rc 相同 | 旧 `python scripts/check.py 文案.txt`（文案 = `本款产品是全效之王，销量第一。`）rc **1**，命中 `销量第一` line 1 col 11 / 新 `clauseproof check extreme-terms --input samples/extreme-terms/readme-example.json --basis …/data/clauses.json` rc **1**，同一词面同一位置 | **过**（rc 1 = 1） |
| 3 | 用例数 / 函数数（**口径乙**） | 用例 114 ≥ 50；`def test_` **114** ≥ 旧层 AST **50**；文件数旧 5 → 新 **1**（按域计，只记录） | **过** |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `pip wheel --no-deps --no-build-isolation` → `clauseproof-0.0.0-py3-none-any.whl`（77 条目）；`clauseproof/packs/extreme-terms/data/` **2 件**：`clauses.json` 5319 B / `wordlists.json` 97320 B；解包后 `check` rc **1** | **过** |

**判据 1 的命令与输出原文**（来源仓只读；`PYTHONDONTWRITEBYTECODE=1` 防写旧仓缓存）：

```bash
cd <来源仓>
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_check.py tests/test_judgment_protocol.py tests/test_real_wordlist.py \
  tests/test_repo_gates.py tests/test_scan_dfa.py -p no:cacheprovider
# → 50 passed in 2.24s
```

### 6.1 D1 + D18 选文件与逐文件处置（5 文件 / 50 passed）

| 来源测试文件 | passed | 域 | 器官处置 |
|---|---:|---|---|
| `tests/test_check.py` | 17 | CLI 契约 / 扫描端到端 / 退出码 | **部分迁**：扫描端到端与退出码语义已迁（§七/§八）；CLI 参数面不迁 |
| `tests/test_judgment_protocol.py` | 14 | 判定协议（LLM 分层）文档与结构 | **部分迁**：`verdict` 层级与「只注释不改位置」语义由账本证据位承载；LLM 调用不迁 |
| `tests/test_real_wordlist.py` | 6 | 真实词表逐条门控 | **已迁**（§二 漂移门 + §五 门控） |
| `tests/test_repo_gates.py` | 5 | 仓库门（零字面量 / 文档一致） | **已迁其精神**：§一 AST 门（engine 零词面 / 无 IO / 无网络 / 无 LLM） |
| `tests/test_scan_dfa.py` | 8 | 前缀树与旧实现等价对拍 | **已迁**（§六 长词优先 / 非重叠 / 位置 / 排序） |
| **合计** | **50** | — | 已迁 2 / 部分迁 2 / 不迁 0（按文件计 4 类） |

D1 + D18 剔除（不计入 X，2 文件）：

| 文件 | 命中词 | 处置 |
|---|---|---|
| `tests/test_cases_bench.py` | `bench` | 真值基准（148 cases exact-match；产品级） |
| `tests/test_delivery_packaging.py` | `packaging` | 交付包装（Skill 三件套 / 发布门） |

> `test_check.py` 的 **17 条**里含 CLI 参数面与 stdout 两轨排版；器官按 §2 只承载判定，
> 判据 1 另用 §七/§八 的 114 条判定用例满足 `≥50`。未改 D1、未删来源仓文件。

## 7. 随包数据与样例出处

| 文件 | 来源 | 说明 |
|---|---|---|
| `data/wordlists.json` | 来源仓 `references/wordlists/*.json` 四份 | 只读合并（含 anchor / source / status 全字段），wheel 进包 |
| `data/clauses.json` | 来源仓 `references/statutes/advertising-law.txt` / `medical-ad-measures.txt` + 词表契约 | 7 条锚点（6 条法条原文块 + 1 条词表契约），版本 `2026-10-15` |
| `samples/extreme-terms/readme-example.json` | 来源 README 示例文案 | 判据 2 的新侧样例（rc 1） |
| `samples/extreme-terms/multi-category.json` | 合成文案（多类别） | 7 条命中样例 |
| `samples/extreme-terms/clean.json` | 合成文案（零命中） | rc 0 对照 |