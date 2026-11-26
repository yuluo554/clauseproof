"""极限用语词表与条款锚点（**Python 字面量，零文件读取**）。

迁移的是来源产品随包冻结的四份词表（133 条，**全部 `verified`**）：绝对化用语 50 /
保健食品违禁 22 / 行业违禁 47 / 医疗违禁 14。三条纪律原样保留：

1. **词面只在词表**：本模块是器官内唯一的词面定义点；`engine.py` 不出现任何词条字面量
   （扫描器只吃编译好的前缀树）。
2. **每条必须挂锚点**：`clause_id` 指向条文库里的一条法条原文块；`basis=literal` 时
   **词面必须逐字出现在该条款正文里**，`basis=variant` 允许是条款措辞的变体。
   **加载侧再拦一次**——缺锚点 / 锚点条款不在条文库 / literal 词面不在原文 → 该条不生效，
   并进未启用清单（绝不静默按最宽松规则扫）。
3. **`status` 是门控**：`verified` 参与扫描，其余记入未启用清单。

`data/wordlists.json` 与 `data/clauses.json` 是来源资产的只读转写，随 wheel 进包，并由
`tests/test_extreme_terms.py` 的漂移门逐条比对（词面 / 类别 / 风险 / 建议 / 锚点 / 状态）。

来源纪律（来源仓 README）：词表是**公开整理的非官方快照**，判定以法条原文为准；
本器官不把词表称作「官方违禁词库」。
"""

from typing import Any, Dict, Mapping, Tuple

#: 词表快照坐标（来源仓 README：词表快照 2026-10-15）
VERSION = "2026-10-15"

#: 命中上下文窗口（词面左右各取多少码点；展示参数，非政策数值）
CONTEXT_WINDOW = 10

#: 风险级（词表内合法值）
RISK_LEVELS: Tuple[str, ...] = ("high", "medium", "low")

#: 词条状态（唯一门控）
STATUS_VERIFIED = "verified"

#: 锚点依据类型：literal = 词面逐字在条款原文；variant = 条款措辞的变体
ANCHOR_BASES: Tuple[str, ...] = ("literal", "variant")

#: 来源四份词表（顺序 = 生效词条声明序 = 扫描编译序）
WORDLIST_FILES: Tuple[str, ...] = ("absolute-terms", "health-food", "industry", "medical")

#: 条文库里额外的一条**词表契约**（不给词面挂锚点，只约束词条门控本身）
CLAUSE_WORDLIST = "contract:wordlist"

#: 法条条款 → 人类可读路径
CLAUSE_PATHS: Mapping[str, str] = {
    "advertising-law:第九条": "《中华人民共和国广告法》 / 第九条",
    "advertising-law:第十七条": "《中华人民共和国广告法》 / 第十七条",
    "advertising-law:第十八条": "《中华人民共和国广告法》 / 第十八条",
    "advertising-law:第二十五条": "《中华人民共和国广告法》 / 第二十五条",
    "advertising-law:第二十八条": "《中华人民共和国广告法》 / 第二十八条",
    "medical-ad-measures:第七条": "《医疗广告管理办法》 / 第七条",
}

#: 词条表：(word, category, risk, suggestion, clause_id, basis)
WORD_ENTRIES: Tuple[Tuple[str, str, str, str, str, str], ...] = (
    ('100%有效', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('NO.1', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('TOP.1', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('万能', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('世界级', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('世界领先', '绝对化用语', 'medium', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('中国第一', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('仅此一家', '绝对化用语', 'medium', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('全国第一', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('全球级', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('全球首发', '绝对化用语', 'medium', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('全网最优', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('全网最低', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('全网第一', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('全网首发', '绝对化用语', 'medium', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('全能', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('史无前例', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('唯一', '绝对化用语', 'medium', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('国家级', '绝对化用语', 'high', '删除该表述，或改为可核实的客观事实描述', 'advertising-law:第九条', 'literal'),
    ('宇宙级', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('最优', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('最优秀', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('最低价', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('最佳', '绝对化用语', 'high', '删除该表述，或改为可核实的客观事实描述', 'advertising-law:第九条', 'literal'),
    ('最便宜', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('最先进', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('最好', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('最强', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('最高端', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('最高级', '绝对化用语', 'high', '删除该表述，或改为可核实的客观事实描述', 'advertising-law:第九条', 'literal'),
    ('极品', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('极致', '绝对化用语', 'medium', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('独一无二', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('空前绝后', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('第一', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('第一品牌', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('终极', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('绝对', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('绝无仅有', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('行业第一', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('行业领先', '绝对化用语', 'medium', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('销量冠军', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('销量第一', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('顶尖', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('顶级', '绝对化用语', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('领先上市', '绝对化用语', 'medium', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('首个', '绝对化用语', 'medium', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('首家', '绝对化用语', 'medium', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('首款', '绝对化用语', 'medium', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('首选', '绝对化用语', 'medium', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('丰胸', '保健食品违禁', 'high', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('减肥', '保健食品违禁', 'medium', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('增高', '保健食品违禁', 'high', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('壮阳', '保健食品违禁', 'high', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('抗癌', '保健食品违禁', 'high', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('排毒', '保健食品违禁', 'medium', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('无任何副作用', '保健食品违禁', 'high', '删除安全性断言，改为可核实成分/检测描述', 'advertising-law:第十八条', 'variant'),
    ('无副作用', '保健食品违禁', 'high', '删除安全性断言，改为可核实成分/检测描述', 'advertising-law:第十八条', 'variant'),
    ('治疗功能', '保健食品违禁', 'high', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'literal'),
    ('溶脂', '保健食品违禁', 'medium', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('燃脂', '保健食品违禁', 'medium', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('疾病预防', '保健食品违禁', 'high', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'literal'),
    ('瘦身', '保健食品违禁', 'medium', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('祛斑', '保健食品违禁', 'medium', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('祛痘', '保健食品违禁', 'medium', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('纯天然', '保健食品违禁', 'medium', '删除安全性断言，改为可核实成分/检测描述', 'advertising-law:第二十八条', 'variant'),
    ('美白', '保健食品违禁', 'medium', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('防癌', '保健食品违禁', 'high', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('降三高', '保健食品违禁', 'high', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('降血压', '保健食品违禁', 'high', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('降血糖', '保健食品违禁', 'high', '删除功效/疾病预防治疗表述；保健食品须显著标明“本品不能代替药物”', 'advertising-law:第十八条', 'variant'),
    ('零添加', '保健食品违禁', 'medium', '删除安全性断言，改为可核实成分/检测描述', 'advertising-law:第二十八条', 'variant'),
    ('CCTV推荐', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('一次通关', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('一次通过', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('专供', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('专家推荐', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('仅此一天', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('保收益', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十五条', 'literal'),
    ('保本', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十五条', 'literal'),
    ('保过', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('假一罚十', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('假一赔万', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('免抽检', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('全民免单', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('包回本', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十五条', 'variant'),
    ('包过', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('吊打同行', '行业违禁', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('国家免检', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('国家机关专供', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('国家机关推荐', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('央视上榜', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('开光', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('开运', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('必涨', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十五条', 'variant'),
    ('恭喜获奖', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('招财进宝', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('政府指定', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('无风险', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十五条', 'literal'),
    ('日入千元', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十五条', 'variant'),
    ('最后一天', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('月入过万', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十五条', 'variant'),
    ('灵验', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('点击领奖', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('特供', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('秒杀全行业', '行业违禁', 'high', '删除绝对化表述，改为可核实的客观描述（如具体数据并附出处）', 'advertising-law:第九条', 'variant'),
    ('稳赚', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十五条', 'variant'),
    ('稳赢', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十五条', 'variant'),
    ('质检推荐', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('质量免检', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('躺赚', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十五条', 'variant'),
    ('转运', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('辟邪', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('错过再等一年', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('镇宅', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('院士推荐', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十八条', 'variant'),
    ('零风险', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第二十五条', 'variant'),
    ('风水改运', '行业违禁', 'medium', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('驰名商标', '行业违禁', 'high', '删除该表述，改为可验证的具体事实（附出处或证明文件）', 'advertising-law:第九条', 'variant'),
    ('三天即愈', '医疗违禁', 'high', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'advertising-law:第十七条', 'variant'),
    ('保证治愈', '医疗违禁', 'high', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'medical-ad-measures:第七条', 'literal'),
    ('包治百病', '医疗违禁', 'high', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'advertising-law:第十七条', 'variant'),
    ('彻底康复', '医疗违禁', 'high', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'advertising-law:第十七条', 'variant'),
    ('抗菌', '医疗违禁', 'medium', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'advertising-law:第十七条', 'variant'),
    ('杀菌', '医疗违禁', 'medium', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'advertising-law:第十七条', 'variant'),
    ('根治', '医疗违禁', 'high', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'advertising-law:第十七条', 'variant'),
    ('治愈', '医疗违禁', 'high', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'medical-ad-measures:第七条', 'literal'),
    ('治疗', '医疗违禁', 'high', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'advertising-law:第十七条', 'literal'),
    ('消炎', '医疗违禁', 'high', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'advertising-law:第十七条', 'variant'),
    ('疗效', '医疗违禁', 'high', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'medical-ad-measures:第七条', 'literal'),
    ('疗效显著', '医疗违禁', 'high', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'medical-ad-measures:第七条', 'variant'),
    ('痊愈', '医疗违禁', 'high', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'advertising-law:第十七条', 'variant'),
    ('药到病除', '医疗违禁', 'high', '删除医疗功效表述；普通商品改为客观成分/质地描述，医疗商品须持证并按审查证明发布', 'advertising-law:第十七条', 'variant'),
)


def words() -> Tuple[Dict[str, Any], ...]:
    """词条 → 字典序列（`engine` 的唯一取数口）。"""
    return tuple(
        {"word": word, "category": category, "risk": risk, "suggestion": suggestion,
         "clause_id": clause_id, "basis": basis, "status": STATUS_VERIFIED}
        for word, category, risk, suggestion, clause_id, basis in WORD_ENTRIES
    )


def clause_specs() -> Tuple[Tuple[str, str], ...]:
    """条文库应含的 ``(clause_id, path)``：6 条法条 + 1 条词表契约。"""
    specs = [(clause_id, CLAUSE_PATHS[clause_id]) for clause_id in sorted(CLAUSE_PATHS)]
    specs.append((CLAUSE_WORDLIST, "数据契约 / 词表门控"))
    return tuple(specs)


def clause_text(clause_id: str) -> str:
    """词表契约正文（法条条款原文来自条文库，不由本模块复述）。"""
    if clause_id != CLAUSE_WORDLIST:
        raise KeyError(clause_id)
    return ("词条须 status=verified 且锚点可解析：锚点条款须在条文库；basis=literal 时"
            "词面须逐字出现在该条款正文；不满足即不生效并列入未启用清单")


__all__ = [
    "VERSION", "CONTEXT_WINDOW", "RISK_LEVELS", "STATUS_VERIFIED", "ANCHOR_BASES",
    "WORDLIST_FILES", "CLAUSE_WORDLIST", "CLAUSE_PATHS", "WORD_ENTRIES",
    "words", "clause_specs", "clause_text",
]
