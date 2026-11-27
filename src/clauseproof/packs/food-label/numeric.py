"""数值复算内核（**零 I/O / 零时钟 / 零网络**；纯确定性，数值结论不经过 LLM）。

迁移的是来源产品的数值复算面（NRV% 复算、能量折算、声称阈值核验、到期日
推算）。基准值与系数来自随包 ``nutrient-reference.json``（与来源逐字节同
sha256；NRV 表挂 GB 28050 附录A、能量系数挂 GB 28050-2025 §2.3）：

- **NRV%**：``round(amount / NRV × 100)``，修约间隔 1（2011 A.2 / 2025 A.3.2；
  ``round`` 为五成双）；行级偏差 ``|标示-复算| > 1`` 判不一致（±1 容纳修约
  方式差异）；跳过：无 NRV% 标示的行（糖等）、per_serving 行、NRV 表外
  营养素、负含量行（非法值交人工）；
- **能量**：``E = round(17×蛋白 + 37×脂肪 + 17×碳水)``（GB 28050-2025 §2.3，
  2011 版无对应条款挂 2025 出处）；表2 允许误差只约束**低报方向**：
  复算值 > 120% × 标示值 + 1 kJ 判矛盾；
- **声称阈值**：无糖 ≤0.5g/100g(mL)、低糖 ≤5、低钠 ≤120mg（两版表C.1）；
  声称了对应成分但营养成分表无该行（或 per_serving）时转"无法复算"；
- **到期日**：生产日期 + 保质期（月单位月加法且日截断到月末、天单位按天
  加法；不做 -1 天修正——与生成器约定口径一致，GB 未明文规定推算方法）。

日期推算用自写月历表（不读时钟；``calendar.monthrange`` 等价的月末天数
由本模块计算）。
"""

from typing import Any, Dict, List, Optional

#: NRV% / 能量复算的修约容差（修约间隔 1 的两倍口径内不算矛盾）
NRV_TOLERANCE = 1
ENERGY_TOLERANCE_KJ = 1
#: 表2 允许误差上限：能量实际值 ≤120% 标示值（两版一致，已核对）
ENERGY_ALLOWED_RATIO = 1.2

#: 月末天数表（闰年规则内联；不依赖 calendar 模块也不读时钟）
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


class _Date:
    """最小不可变日期（``YYYY-MM-DD`` ISO 字符串进出；零时钟）。"""

    __slots__ = ("year", "month", "day")

    def __init__(self, year: int, month: int, day: int) -> None:
        if not (1 <= month <= 12):
            raise ValueError("month out of range: %d" % month)
        if not (1 <= day <= _month_days(year, month)):
            raise ValueError("day out of range: %04d-%02d-%02d" % (year, month, day))
        self.year = year
        self.month = month
        self.day = day

    @classmethod
    def from_iso(cls, text: str) -> "_Date":
        parts = str(text).split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("bad iso date: %r" % (text,))
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))

    def isoformat(self) -> str:
        return "%04d-%02d-%02d" % (self.year, self.month, self.day)

    def plus_days(self, days: int) -> "_Date":
        d = self
        for _ in range(days):
            d = _next_day(d)
        return d

    def plus_months(self, months: int) -> "_Date":
        """月加法，日截断到月末（生成器约定口径）。"""
        total = self.month - 1 + months
        year = self.year + total // 12
        month = total % 12 + 1
        last = _month_days(year, month)
        return _Date(year, month, min(self.day, last))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Date) and (self.year, self.month, self.day) == (
            other.year, other.month, other.day)

    def __repr__(self) -> str:
        return self.isoformat()


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _month_days(year: int, month: int) -> int:
    if month == 2 and _is_leap(year):
        return 29
    return _MONTH_DAYS[month - 1]


def _next_day(d: _Date) -> "_Date":
    if d.day < _month_days(d.year, d.month):
        return _Date(d.year, d.month, d.day + 1)
    if d.month < 12:
        return _Date(d.year, d.month + 1, 1)
    return _Date(d.year + 1, 1, 1)


class NutrientReference:
    """营养参考表内存视图（数值唯一出处 = 随包 JSON，本模块零内联）。"""

    def __init__(self, reference: Dict[str, Any]) -> None:
        self._reference = reference

    @property
    def nrv(self) -> Dict[str, Dict[str, Any]]:
        return self._reference["nrv"]

    def energy_factors(self) -> Dict[str, float]:
        return self._reference["energy_factors_kj_per_g"]

    def claim_thresholds(self) -> List[Dict[str, Any]]:
        return self._reference.get("claim_thresholds", [])

    def salt_notice_text(self) -> str:
        return self._reference["salt_oil_sugar_notice"]["text"]


def _row(card: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    for row in card.get("nutrition_table", []):
        if row.get("name") == name:
            return row
    return None


def recompute_nrv_percent(reference: NutrientReference, name: str, amount: float,
                          unit: str) -> Optional[int]:
    """单行 NRV% 复算：round(amount/NRV×100)；无 NRV 基准或单位不符返回 None。"""
    entry = reference.nrv.get(name)
    if entry is None or entry.get("unit") != unit:
        return None
    return round(amount / float(entry["value"]) * 100)


def check_nrv_rows(reference: NutrientReference, card: Dict[str, Any]) -> List[Dict[str, Any]]:
    """逐行复算 NRV%：返回不一致行列表 [{name, shown, recomputed, diff, evidence}]。"""
    mismatches: List[Dict[str, Any]] = []
    for row in card.get("nutrition_table", []):
        shown = row.get("nrv_percent")
        if shown is None or row.get("per_serving"):
            continue
        amount = row.get("amount")
        if not isinstance(amount, (int, float)) or amount < 0:
            continue
        recomputed = recompute_nrv_percent(
            reference, row.get("name", ""), float(amount), row.get("unit", ""))
        if recomputed is None:
            continue
        diff = float(shown) - recomputed
        if abs(diff) > NRV_TOLERANCE:
            mismatches.append({
                "name": row.get("name", ""),
                "shown": shown,
                "recomputed": recomputed,
                "diff": diff,
                "evidence": row.get("evidence"),
            })
    return mismatches


def recompute_energy(reference: NutrientReference, protein: float, fat: float,
                     carb: float) -> int:
    """能量折算：round(17P+37F+17C)（系数挂 GB 28050-2025 §2.3）。"""
    f = reference.energy_factors()
    return round(f["蛋白质"] * protein + f["脂肪"] * fat + f["碳水化合物"] * carb)


def check_energy_consistency(reference: NutrientReference,
                             card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """能量折算一致性三态：violation（低报超表2 容差）/ ok / None（不可复算）。"""
    energy = _row(card, "能量")
    protein = _row(card, "蛋白质")
    fat = _row(card, "脂肪")
    carb = _row(card, "碳水化合物")
    rows = [energy, protein, fat, carb]
    if any(r is None or r.get("per_serving") for r in rows):
        return None
    if energy.get("unit") != "kJ" or any(r.get("unit") != "g" for r in rows[1:]):
        return None
    amounts = [r.get("amount") for r in rows]
    if any(not isinstance(a, (int, float)) or a < 0 for a in amounts):
        return None
    shown = float(amounts[0])
    recomputed = recompute_energy(reference, float(amounts[1]), float(amounts[2]),
                                  float(amounts[3]))
    if recomputed > ENERGY_ALLOWED_RATIO * shown + ENERGY_TOLERANCE_KJ:
        return {
            "verdict": "violation",
            "shown_energy_kj": amounts[0],
            "recomputed_energy_kj": recomputed,
            "allowed_ratio": ENERGY_ALLOWED_RATIO,
            "evidence": energy.get("evidence"),
        }
    return {
        "verdict": "ok",
        "shown_energy_kj": amounts[0],
        "recomputed_energy_kj": recomputed,
        "evidence": energy.get("evidence"),
    }


def claim_threshold_checks(reference: NutrientReference,
                           card: Dict[str, Any]) -> List[Dict[str, Any]]:
    """声称阈值核验：对每条声称×每个已核对阈值给出可判定结论。

    verdict：pass（含量达阈值）/ fail（超阈值）/ no_row（缺该行）/
    per_serving（每份标示无法按每100g(mL) 复算）。
    """
    results: List[Dict[str, Any]] = []
    for claim in card.get("claims", []):
        for th in reference.claim_thresholds():
            if th.get("claim_contains") not in claim:
                continue
            row = _row(card, th["nutrient"])
            entry = {
                "claim": claim,
                "claim_contains": th["claim_contains"],
                "nutrient": th["nutrient"],
                "max_per_100": th["max_per_100"],
                "unit": th["unit"],
                "amount": None,
                "verdict": "no_row",
                "evidence": None,
            }
            if row is not None:
                entry["evidence"] = row.get("evidence")
                if row.get("per_serving"):
                    entry["verdict"] = "per_serving"
                else:
                    amount = row.get("amount")
                    if isinstance(amount, (int, float)) and amount >= 0:
                        entry["amount"] = amount
                        entry["verdict"] = (
                            "pass" if float(amount) <= float(th["max_per_100"]) else "fail")
            results.append(entry)
    return results


def compute_expected_expiry(production_iso: str, shelf_value: Any,
                            shelf_unit: str) -> _Date:
    """按生成器约定推算到期日（月加法/天加法；其他单位抛 ValueError）。"""
    prod = _Date.from_iso(production_iso)
    if shelf_unit == "个月":
        return prod.plus_months(int(shelf_value))
    if shelf_unit == "天":
        return prod.plus_days(int(shelf_value))
    raise ValueError("未知保质期单位：%s" % shelf_unit)
