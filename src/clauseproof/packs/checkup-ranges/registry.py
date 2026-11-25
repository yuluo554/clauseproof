"""内置区间知识库（**Python 字面量，零文件读取**）。

来源：迁自 target-map ① 行的随包白名单数据
``src/checkup_ledger/data/indicators.yaml``（19 条，全部 ``status: pending``）。

为什么把 YAML 搬成字面量：器官**不读文件**（执行约束）。``data/indicators.yaml``
仍逐字保存来源资产作为可复核出处，随 wheel 进包，并由
``tests/test_checkup_ranges.py`` 的「漂移门」逐条比对。

**19 条全部 pending**（WS/T 404/405 全文不可直连 → 区间数值无法逐条核对），
故内置默认值**一律不进判定路径**：报告未自印区间时走"拒判"。这是源产品的既定
纪律（宁拒判，不臆造），本器官原样保留。
"""

from typing import Optional, Tuple

from .engine import STATUS_PENDING, Indicator

#: 区间库快照版本（= 条文库坐标；条目转 verified 后此值必须同步）
REGISTRY_VERSION = "2026-10-16"

#: 未定位到 WS/T 分册的条目，来源如实写"未定位"（不拿方法标准冒充区间来源）
STANDARD_UNLOCATED = "未定位（WS/T 404/405 系列无对应分册）"


def _ind(canonical_name: str, display_name: str, aliases: Tuple[str, ...],
         unit: str, unit_aliases: Tuple[str, ...],
         low: Optional[float], high: Optional[float],
         sex: str, standard: str, bounds: str = "closed",
         status: str = STATUS_PENDING) -> Indicator:
    return Indicator(
        canonical_name=canonical_name,
        display_name=display_name,
        aliases=tuple(aliases),
        unit=unit,
        unit_aliases=tuple(unit_aliases),
        low=low,
        high=high,
        bounds=bounds,
        sex=sex,
        standard=standard,
        status=status,
    )


#: 19 条内置区间条目（顺序 = 来源 YAML 声明序 = 归一命中的声明序）
INDICATORS: Tuple[Indicator, ...] = (
    # ---------------- 血常规（WS/T 405-2012）----------------
    _ind("WBC", "白细胞计数", ("白细胞计数", "白细胞", "WBC", "WBC计数", "WBC 白细胞"),
         "10^9/L", ("10^9/L", "10E9/L", "×10^9/L", "10*9/L"),
         3.5, 9.5, "any", "WS/T 405-2012"),
    _ind("RBC", "红细胞计数", ("红细胞计数", "红细胞", "RBC", "RBC计数"),
         "10^12/L", ("10^12/L", "10E12/L", "×10^12/L"),
         4.3, 5.8, "male", "WS/T 405-2012"),
    _ind("HGB", "血红蛋白", ("血红蛋白", "HGB", "Hb", "血色素"),
         "g/L", ("g/L", "g/l", "G/L"),
         130.0, 175.0, "male", "WS/T 405-2012"),
    _ind("HCT", "红细胞比容", ("红细胞比容", "红细胞压积", "HCT", "Hct", "PCV"),
         "L/L", ("L/L", "l/l", "比值"),
         0.4, 0.5, "male", "WS/T 405-2012"),
    _ind("PLT", "血小板计数", ("血小板计数", "血小板", "PLT", "PLT计数"),
         "10^9/L", ("10^9/L", "10E9/L", "×10^9/L"),
         125.0, 350.0, "any", "WS/T 405-2012"),
    # ---------------- 肝功能（WS/T 404.1-2012）----------------
    _ind("ALT", "丙氨酸氨基转移酶", ("谷丙转氨酶", "ALT", "GPT", "丙氨酸氨基转移酶"),
         "U/L", ("U/L", "IU/L", "u/l", "U/L(速率法)"),
         9.0, 50.0, "any", "WS/T 404.1-2012"),
    _ind("AST", "天门冬氨酸氨基转移酶", ("谷草转氨酶", "AST", "GOT", "天门冬氨酸氨基转移酶"),
         "U/L", ("U/L", "IU/L", "u/l"),
         15.0, 40.0, "any", "WS/T 404.1-2012"),
    _ind("ALP", "碱性磷酸酶", ("碱性磷酸酶", "ALP", "AKP", "碱性磷酸酶(ALP)"),
         "U/L", ("U/L", "IU/L", "u/l"),
         45.0, 125.0, "any", "WS/T 404.1-2012"),
    _ind("GGT", "γ-谷氨酰基转移酶", ("γ-谷氨酰基转移酶", "谷氨酰转肽酶", "GGT", "γ-GT", "r-GT"),
         "U/L", ("U/L", "IU/L", "u/l"),
         11.0, 50.0, "male", "WS/T 404.1-2012"),
    # ---------------- 胆红素 / 蛋白（WS/T 404.4 / 404.2）----------------
    _ind("TBIL", "总胆红素", ("总胆红素", "胆红素", "TBIL", "TBil", "T-BIL"),
         "umol/L", ("umol/L", "μmol/L", "umol/l"),
         3.4, 20.5, "any", "WS/T 404.4-2018"),
    _ind("TP", "总蛋白", ("总蛋白", "血清总蛋白", "TP", "T-PRO"),
         "g/L", ("g/L", "g/l", "G/L"),
         65.0, 85.0, "any", "WS/T 404.2-2012"),
    # ---------------- 血脂（WS/T 系列无对应分册 → 来源如实"未定位"）----------------
    _ind("TC", "总胆固醇", ("总胆固醇", "胆固醇", "TC", "CHOL", "TCHO"),
         "mmol/L", ("mmol/L", "mM"),
         None, 5.2, "any", STANDARD_UNLOCATED),
    _ind("TG", "甘油三酯", ("甘油三酯", "三酰甘油", "TG", "TRIG"),
         "mmol/L", ("mmol/L", "mM"),
         None, 1.7, "any", STANDARD_UNLOCATED),
    _ind("HDL-C", "高密度脂蛋白胆固醇",
         ("高密度脂蛋白胆固醇", "高密度脂蛋白", "HDL-C", "HDLC", "HDL"),
         "mmol/L", ("mmol/L", "mM"),
         1.1, 1.7, "any", STANDARD_UNLOCATED),
    _ind("LDL-C", "低密度脂蛋白胆固醇",
         ("低密度脂蛋白胆固醇", "低密度脂蛋白", "LDL-C", "LDLC", "LDL"),
         "mmol/L", ("mmol/L", "mM"),
         None, 3.4, "any", STANDARD_UNLOCATED),
    # ---------------- 肾功能（WS/T 404.5-2015）----------------
    _ind("CREA", "肌酐", ("肌酐", "CREA", "Cr", "肌酸酐", "SCr"),
         "umol/L", ("umol/L", "μmol/L", "umol/l"),
         57.0, 97.0, "any", "WS/T 404.5-2015"),
    _ind("UREA", "尿素", ("尿素", "尿素氮", "UREA", "BUN", "血尿素"),
         "mmol/L", ("mmol/L", "mM"),
         2.9, 8.2, "any", "WS/T 404.5-2015"),
    _ind("UA", "尿酸", ("尿酸", "UA", "血尿酸"),
         "umol/L", ("umol/L", "μmol/L"),
         208.0, 428.0, "male", STANDARD_UNLOCATED),
    # ---------------- 血糖 ----------------
    _ind("GLU", "葡萄糖", ("葡萄糖", "血糖", "GLU", "GLU-空腹", "空腹血糖", "FBG"),
         "mmol/L", ("mmol/L", "mM"),
         3.9, 6.1, "any", STANDARD_UNLOCATED),
)

#: 已核对（可进判定路径）的条目：当前为 0（全部 pending，如实保留）
VERIFIED_INDICATORS: Tuple[Indicator, ...] = tuple(
    indicator for indicator in INDICATORS if indicator.is_effective)

#: 待核对条目（不进判定路径，只用来说明"为什么拒判"）
PENDING_INDICATORS: Tuple[Indicator, ...] = tuple(
    indicator for indicator in INDICATORS if not indicator.is_effective)


def clause_ids() -> Tuple[str, ...]:
    """条文库应含的 clause_id：报告自印区间锚点 + 每个**已核对**指标的标准条目。"""
    ids = ["range:report-printed"]
    ids.extend("wst:%s" % indicator.canonical_name for indicator in VERIFIED_INDICATORS)
    return tuple(sorted(ids))


__all__ = [
    "REGISTRY_VERSION", "STANDARD_UNLOCATED", "INDICATORS",
    "VERIFIED_INDICATORS", "PENDING_INDICATORS", "clause_ids",
]