"""冻结核查规则与条款锚点（**Python 字面量，零文件读取**）。

来源：迁自 target-map ① 行的随包规则包
``src/pflc/data/rules/ruleset-{claim,label,nutrition}.json``（共 45 条 = 5 宣称 + 8 标签 + 32 营养）。

为什么把 JSON 搬成字面量：器官**不读文件**（执行约束）。``data/`` 下逐字保存三份
来源规则包 + manifest 作为可复核出处，随 wheel 进包，并由
``tests/test_petfood_label.py`` 的「漂移门」逐条比对。

纪律（与来源 product 一致）：

- **双重门控**：``status``（数值核对）门控判定路径；``clause_status``（条款号核对）
  只管可证性展示，不阻断判定；
- 营养条目 30 条 verified、2 条 ``牛磺酸`` pending（限值未核对）→ **不进判定路径**；
- 号码/条款全部随条目走，源码不出现第二个来源。

``CLAUSES`` 的 ``text`` 是来源冻结抓取里的 OCR 原文（**逐字保留，不清理**）——
可复核性优先于可读性；看不懂的地方回查 ``doc_id`` + 抓取 sha256（见来源 manifest）。
"""

from typing import Optional, Tuple

from .engine import (
    BASIS_DRY_MATTER,
    DIM_CLAIM,
    DIM_LABEL,
    DIM_NUTRITION,
    EFFECT_CONDITIONAL,
    EFFECT_OBLIGATION,
    KIND_CLAIM_SUPPORT,
    KIND_PRESENCE,
    KIND_THRESHOLD,
    STATUS_PENDING,
    STATUS_VERIFIED,
    Rule,
)

#: 规则包版本（= 条文库坐标）
RULESET_VERSION = "2026.1"

MOA = "宠物饲料标签规定（农业农村部公告第20号 附件3）"
DOG = "全价宠物食品 犬粮"
CAT = "全价宠物食品 猫粮"

#: ``(clause_id, path, text)``
CLAUSES: Tuple[Tuple[str, str, str], ...] = (
    ("moa-annex3:5", MOA + "/第五条",
     "如不标示则默认为适用于所有生命阶段"),
    ("moa-annex3:6", MOA + "/第六条",
     "原料组成包括饲料原料和饲料添加剂两部分"),
    ("moa-annex3:9", MOA + "/第九条",
     "宠物饲料产品应当标示产品包装单位的净含量。"),
    ("moa-annex3:14", MOA + "/第十四条",
     "宠物饲料产品标签应当标示保质期，标示方法见附录6。"),
    ("moa-annex3:15", MOA + "/第十五条",
     "应当标示与许可证明文件一致的生产许可证编号、企业名称、注册地址、生产地址、联系方式"),
    ("moa-annex3:20", MOA + "/第二十条",
     "且不含有氯化钠、防腐剂或者其他饲料添加剂"),
    ("gbt312162014:t1:r2", DOG + " 表1 第2行", "粘蛋口质之22.0之18.0GB/TT6432"),
    ("gbt312162014:t1:r3", DOG + " 表1 第3行", "粗脂肪之8.0芒5.0GB/TT6433"),
    ("gbt312162014:t1:r4", DOG + " 表1 第4行", "粗灰分如10.0如10.0GB/T6438"),
    ("gbt312162014:t1:r5", DOG + " 表1 第5行", "粗纤维妙9.0女9.0GB/T6434"),
    ("gbt312162014:t1:r6", DOG + " 表1 第6行", "钨之1.0之0.6GPR/TT6436"),
    ("gbt312162014:t1:r7", DOG + " 表1 第7行", "J'l[，】亏′′_l】、蜃丨靠之0.8之0.5GB/TT6437"),
    ("gbt312162014:t1:r8", DOG + " 表1 第8行", "水溶性氯化物(以CL计〉之0.45之0.09GB/TT6439"),
    ("gbt312162014:t1:r9", DOG + " 表1 第9行", "赖氨酸之0.77之0.63GB/工18246"),
    ("gbt312172014:t1:r2", CAT + " 表1 第2行", "粗蛋白质之28.0之25.0GBy/工6432"),
    ("gbt312172014:t1:r3", CAT + " 表1 第3行", "粗胆肢之9.0之9.0GB/丁6433"),
    ("gbt312172014:t1:r4", CAT + " 表1 第4行", "粗灰分如10.0如10.0GB/工6438"),
    ("gbt312172014:t1:r5", CAT + " 表1 第5行", "粗纤维女9.0女9.0GB/TT6434"),
    ("gbt312172014:t1:r6", CAT + " 表1 第6行", "钙之1.0之0.6GB/TT6436"),
    ("gbt312172014:t1:r7", CAT + " 表1 第7行", "」'丨湮`、碾'靠之0.8之0.5GB/TT6437"),
    ("gbt312172014:t1:r8", CAT + " 表1 第8行", "水溶性氯化物(以CL计)之0.3之0.3(GB/T6439"),
    ("gbt312172014:t1:r9", CAT + " 表1 第9行",
     "牛磺酸之0童(〔〕霏鼻…'工粮)之0亡盲〈〔〕荠鼻…_亘粮)GB/T18246"),
)


def _rule(rule_id: str, dimension: str, kind: str, target: str,
          effect: str = EFFECT_OBLIGATION, op: Optional[str] = None,
          value: Optional[str] = None, unit: Optional[str] = None,
          basis: str = BASIS_DRY_MATTER, applies_if: Optional[dict] = None,
          required_support: Tuple[str, ...] = (), status: str = STATUS_VERIFIED,
          clause_id: str = "") -> Rule:
    table = {}
    for key, allowed in (applies_if or {}).items():
        table[key] = tuple(allowed)
    return Rule(
        rule_id=rule_id, dimension=dimension, kind=kind, target=target, effect=effect,
        op=op, value=value, unit=unit, basis=basis, applies_if=table,
        required_support=tuple(required_support), status=status, clause_id=clause_id,
    )


_ADULT = ("成年",)
_YOUNG = ("幼年", "妊娠哺乳期")
_CAT = ("猫粮",)
_DOG = ("犬粮",)

#: 45 条规则（顺序 = 来源规则包声明序：claim → label → nutrition）
RULES: Tuple[Rule, ...] = (
    # ---------------- 宣称支撑（A 维度）----------------
    _rule("CLAIM-001", DIM_CLAIM, KIND_CLAIM_SUPPORT, "天然",
          required_support=("ingredients", "additives"), basis="as_fed",
          clause_id="moa-annex3:20"),
    _rule("CLAIM-002", DIM_CLAIM, KIND_CLAIM_SUPPORT, "无谷",
          required_support=("ingredients",), basis="as_fed", clause_id="moa-annex3:20"),
    _rule("CLAIM-003", DIM_CLAIM, KIND_CLAIM_SUPPORT, "无添加",
          required_support=("ingredients", "additives"), basis="as_fed",
          clause_id="moa-annex3:20"),
    _rule("CLAIM-004", DIM_CLAIM, KIND_CLAIM_SUPPORT, "纯天然",
          required_support=("ingredients", "additives"), basis="as_fed",
          clause_id="moa-annex3:20"),
    _rule("CLAIM-005", DIM_CLAIM, KIND_CLAIM_SUPPORT, "鲜肉",
          required_support=("ingredients", "additives"), basis="as_fed",
          clause_id="moa-annex3:20"),
    # ---------------- 标签标示（B 维度）----------------
    _rule("LABEL-001", DIM_LABEL, KIND_PRESENCE, "product_name", basis="as_fed",
          clause_id="moa-annex3:5"),
    _rule("LABEL-002", DIM_LABEL, KIND_PRESENCE, "ingredients", basis="as_fed",
          clause_id="moa-annex3:6"),
    _rule("LABEL-003", DIM_LABEL, KIND_PRESENCE, "net_content", basis="as_fed",
          clause_id="moa-annex3:9"),
    _rule("LABEL-004", DIM_LABEL, KIND_PRESENCE, "producer", basis="as_fed",
          clause_id="moa-annex3:15"),
    _rule("LABEL-005", DIM_LABEL, KIND_PRESENCE, "product_dates", basis="as_fed",
          clause_id="moa-annex3:14"),
    _rule("LABEL-006", DIM_LABEL, KIND_PRESENCE, "additives",
          effect=EFFECT_CONDITIONAL, basis="as_fed", clause_id="moa-annex3:6"),
    _rule("LABEL-007", DIM_LABEL, KIND_PRESENCE, "category",
          effect=EFFECT_CONDITIONAL, basis="as_fed", clause_id="moa-annex3:5"),
    _rule("LABEL-008", DIM_LABEL, KIND_PRESENCE, "life_stage",
          effect=EFFECT_CONDITIONAL, basis="as_fed", clause_id="moa-annex3:5"),
    # ---------------- 猫粮理化指标（C 维度）----------------
    _rule("NUT-CAT-001", DIM_NUTRITION, KIND_THRESHOLD, "粗蛋白", op=">=", value="28.0",
          unit="%", applies_if={"category": _CAT, "life_stage": _YOUNG},
          clause_id="gbt312172014:t1:r2"),
    _rule("NUT-CAT-002", DIM_NUTRITION, KIND_THRESHOLD, "粗蛋白", op=">=", value="25.0",
          unit="%", applies_if={"category": _CAT, "life_stage": _ADULT},
          clause_id="gbt312172014:t1:r2"),
    _rule("NUT-CAT-003", DIM_NUTRITION, KIND_THRESHOLD, "粗脂肪", op=">=", value="9.0",
          unit="%", applies_if={"category": _CAT, "life_stage": _YOUNG},
          clause_id="gbt312172014:t1:r3"),
    _rule("NUT-CAT-004", DIM_NUTRITION, KIND_THRESHOLD, "粗脂肪", op=">=", value="9.0",
          unit="%", applies_if={"category": _CAT, "life_stage": _ADULT},
          clause_id="gbt312172014:t1:r3"),
    _rule("NUT-CAT-005", DIM_NUTRITION, KIND_THRESHOLD, "粗灰分", op="<=", value="10.0",
          unit="%", applies_if={"category": _CAT, "life_stage": _YOUNG},
          clause_id="gbt312172014:t1:r4"),
    _rule("NUT-CAT-006", DIM_NUTRITION, KIND_THRESHOLD, "粗灰分", op="<=", value="10.0",
          unit="%", applies_if={"category": _CAT, "life_stage": _ADULT},
          clause_id="gbt312172014:t1:r4"),
    _rule("NUT-CAT-007", DIM_NUTRITION, KIND_THRESHOLD, "粗纤维", op="<=", value="9.0",
          unit="%", applies_if={"category": _CAT, "life_stage": _YOUNG},
          clause_id="gbt312172014:t1:r5"),
    _rule("NUT-CAT-008", DIM_NUTRITION, KIND_THRESHOLD, "粗纤维", op="<=", value="9.0",
          unit="%", applies_if={"category": _CAT, "life_stage": _ADULT},
          clause_id="gbt312172014:t1:r5"),
    _rule("NUT-CAT-009", DIM_NUTRITION, KIND_THRESHOLD, "钙", op=">=", value="1.0",
          unit="%", applies_if={"category": _CAT, "life_stage": _YOUNG},
          clause_id="gbt312172014:t1:r6"),
    _rule("NUT-CAT-010", DIM_NUTRITION, KIND_THRESHOLD, "钙", op=">=", value="0.6",
          unit="%", applies_if={"category": _CAT, "life_stage": _ADULT},
          clause_id="gbt312172014:t1:r6"),
    _rule("NUT-CAT-011", DIM_NUTRITION, KIND_THRESHOLD, "总磷", op=">=", value="0.8",
          unit="%", applies_if={"category": _CAT, "life_stage": _YOUNG},
          clause_id="gbt312172014:t1:r7"),
    _rule("NUT-CAT-012", DIM_NUTRITION, KIND_THRESHOLD, "总磷", op=">=", value="0.5",
          unit="%", applies_if={"category": _CAT, "life_stage": _ADULT},
          clause_id="gbt312172014:t1:r7"),
    _rule("NUT-CAT-013", DIM_NUTRITION, KIND_THRESHOLD, "水溶性氯化物", op=">=", value="0.3",
          unit="%", applies_if={"category": _CAT, "life_stage": _YOUNG},
          clause_id="gbt312172014:t1:r8"),
    _rule("NUT-CAT-014", DIM_NUTRITION, KIND_THRESHOLD, "水溶性氯化物", op=">=", value="0.3",
          unit="%", applies_if={"category": _CAT, "life_stage": _ADULT},
          clause_id="gbt312172014:t1:r8"),
    _rule("NUT-CAT-015", DIM_NUTRITION, KIND_THRESHOLD, "牛磺酸", op=">=", value=None,
          unit="%", applies_if={"category": _CAT, "life_stage": _YOUNG},
          status=STATUS_PENDING, clause_id="gbt312172014:t1:r9"),
    _rule("NUT-CAT-016", DIM_NUTRITION, KIND_THRESHOLD, "牛磺酸", op=">=", value=None,
          unit="%", applies_if={"category": _CAT, "life_stage": _ADULT},
          status=STATUS_PENDING, clause_id="gbt312172014:t1:r9"),
    # ---------------- 犬粮理化指标（C 维度）----------------
    _rule("NUT-DOG-001", DIM_NUTRITION, KIND_THRESHOLD, "粗蛋白", op=">=", value="22.0",
          unit="%", applies_if={"category": _DOG, "life_stage": _YOUNG},
          clause_id="gbt312162014:t1:r2"),
    _rule("NUT-DOG-002", DIM_NUTRITION, KIND_THRESHOLD, "粗蛋白", op=">=", value="18.0",
          unit="%", applies_if={"category": _DOG, "life_stage": _ADULT},
          clause_id="gbt312162014:t1:r2"),
    _rule("NUT-DOG-003", DIM_NUTRITION, KIND_THRESHOLD, "粗脂肪", op=">=", value="8.0",
          unit="%", applies_if={"category": _DOG, "life_stage": _YOUNG},
          clause_id="gbt312162014:t1:r3"),
    _rule("NUT-DOG-004", DIM_NUTRITION, KIND_THRESHOLD, "粗脂肪", op=">=", value="5.0",
          unit="%", applies_if={"category": _DOG, "life_stage": _ADULT},
          clause_id="gbt312162014:t1:r3"),
    _rule("NUT-DOG-005", DIM_NUTRITION, KIND_THRESHOLD, "粗灰分", op="<=", value="10.0",
          unit="%", applies_if={"category": _DOG, "life_stage": _YOUNG},
          clause_id="gbt312162014:t1:r4"),
    _rule("NUT-DOG-006", DIM_NUTRITION, KIND_THRESHOLD, "粗灰分", op="<=", value="10.0",
          unit="%", applies_if={"category": _DOG, "life_stage": _ADULT},
          clause_id="gbt312162014:t1:r4"),
    _rule("NUT-DOG-007", DIM_NUTRITION, KIND_THRESHOLD, "粗纤维", op="<=", value="9.0",
          unit="%", applies_if={"category": _DOG, "life_stage": _YOUNG},
          clause_id="gbt312162014:t1:r5"),
    _rule("NUT-DOG-008", DIM_NUTRITION, KIND_THRESHOLD, "粗纤维", op="<=", value="9.0",
          unit="%", applies_if={"category": _DOG, "life_stage": _ADULT},
          clause_id="gbt312162014:t1:r5"),
    _rule("NUT-DOG-009", DIM_NUTRITION, KIND_THRESHOLD, "钙", op=">=", value="1.0",
          unit="%", applies_if={"category": _DOG, "life_stage": _YOUNG},
          clause_id="gbt312162014:t1:r6"),
    _rule("NUT-DOG-010", DIM_NUTRITION, KIND_THRESHOLD, "钙", op=">=", value="0.6",
          unit="%", applies_if={"category": _DOG, "life_stage": _ADULT},
          clause_id="gbt312162014:t1:r6"),
    _rule("NUT-DOG-011", DIM_NUTRITION, KIND_THRESHOLD, "总磷", op=">=", value="0.8",
          unit="%", applies_if={"category": _DOG, "life_stage": _YOUNG},
          clause_id="gbt312162014:t1:r7"),
    _rule("NUT-DOG-012", DIM_NUTRITION, KIND_THRESHOLD, "总磷", op=">=", value="0.5",
          unit="%", applies_if={"category": _DOG, "life_stage": _ADULT},
          clause_id="gbt312162014:t1:r7"),
    _rule("NUT-DOG-013", DIM_NUTRITION, KIND_THRESHOLD, "水溶性氯化物", op=">=", value="0.45",
          unit="%", applies_if={"category": _DOG, "life_stage": _YOUNG},
          clause_id="gbt312162014:t1:r8"),
    _rule("NUT-DOG-014", DIM_NUTRITION, KIND_THRESHOLD, "水溶性氯化物", op=">=", value="0.09",
          unit="%", applies_if={"category": _DOG, "life_stage": _ADULT},
          clause_id="gbt312162014:t1:r8"),
    _rule("NUT-DOG-015", DIM_NUTRITION, KIND_THRESHOLD, "赖氨酸", op=">=", value="0.77",
          unit="%", applies_if={"category": _DOG, "life_stage": _YOUNG},
          clause_id="gbt312162014:t1:r9"),
    _rule("NUT-DOG-016", DIM_NUTRITION, KIND_THRESHOLD, "赖氨酸", op=">=", value="0.63",
          unit="%", applies_if={"category": _DOG, "life_stage": _ADULT},
          clause_id="gbt312162014:t1:r9"),
)

#: 待核对条目（限值未核对，不进判定路径）
PENDING_RULE_IDS: Tuple[str, ...] = tuple(
    rule.rule_id for rule in RULES if not rule.is_effective)

#: 宣称词表（来源规则包的 claim 目标集，供档案抽取时对齐）
CLAIM_VOCAB: Tuple[str, ...] = tuple(
    rule.target for rule in RULES if rule.kind == KIND_CLAIM_SUPPORT)


def clause_ids() -> Tuple[str, ...]:
    return tuple(sorted(clause_id for clause_id, _path, _text in CLAUSES))


__all__ = ["RULESET_VERSION", "CLAUSES", "RULES", "PENDING_RULE_IDS", "CLAIM_VOCAB",
           "clause_ids"]