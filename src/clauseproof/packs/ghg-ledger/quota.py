"""行业配额试算（来源 quota 模块）。

**方法学切换即切换公式分支**——公式分支由规则包 ``quota.method`` 决定，代码不内联
方法学名与公式：

- ``benchmark``（发电：碳排放强度基准法）A = Qe × Be × Ff；
- ``intensity_coefficient``（钢铁/水泥/铝冶炼：强度系数法）A = E × (1 + α)，
  α 由偏离度 X = (BP − Ii) / BP 经规则包 ``quota.derivation`` 分段系数推出；
- ``historical_intensity``（历史强度法）A = 产量 × 历史强度；
- ``none``：不试算（显式「不适用」，而非静默给 0）。

参数纪律：``verified`` → 规则包值；``input_required`` → 必须由调用方显式提供
（未提供即抛 :class:`QuotaUnavailable`，绝不静默取 0 或 1）；``pending`` 由门控拦截。

免责声明强制：返回结构 ``disclaimer_required`` 恒为 ``True`` —— 渲染层必须输出。
"""

from typing import Any, Dict, Mapping, Optional

from . import engine as E
from . import rules

SCHEMA_QUOTA = "ghg-quotaresult/v1"
UNIT_EMISSION = "tCO2e"

METHOD_BENCHMARK = "benchmark"
METHOD_INTENSITY_COEFFICIENT = "intensity_coefficient"
METHOD_HISTORICAL_INTENSITY = "historical_intensity"
METHOD_NONE = "none"

STATUS_OK = "ok"
STATUS_NOT_APPLICABLE = "not_applicable"

QUOTA_PLACES = 3
PERCENT_PLACES = 2


def _plain(value):
    return E.to_text(value, QUOTA_PLACES)


def _entry_of(pack, path):
    node = pack
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _verified(entry, label):
    if not isinstance(entry, dict):
        raise E.QuotaUnavailable("配额参数缺失：%s" % label)
    if entry.get("status") != rules.STATUS_VERIFIED or entry.get("value") is None:
        raise E.QuotaUnavailable("配额参数 %s 未核对（不得参与试算）" % label)
    return E.as_decimal(entry["value"])


def _resolve(entry, label, supplied):
    """``verified`` → 规则包值；``input_required`` → 索取外部输入（未提供即抛）。"""
    if isinstance(entry, dict) and entry.get("status") == rules.STATUS_VERIFIED \
            and entry.get("value") is not None:
        return E.as_decimal(entry["value"]), "ruleset"
    if supplied is not None:
        return E.as_decimal(supplied), "caller"
    if isinstance(entry, dict) and entry.get("status") == rules.STATUS_INPUT_REQUIRED:
        note = ((entry.get("clause") or {}).get("note") or "").strip()
        raise E.QuotaUnavailable(
            "配额参数 %s 需外部提供（规则包不承载该数值%s）；"
            "试算层不得静默取 0 —— 请通过参数显式给出"
            % (label, ("：" + note) if note else ""))
    raise E.QuotaUnavailable("配额参数 %s 不可用（未核对或缺失）" % label)


def _resolve_method(pack, override):
    quota = pack.get("quota", {}) or {}
    allowed = list(quota.get("allowed_methods") or ())
    method = override or quota.get("method")
    if not method:
        raise E.QuotaUnavailable("规则包未声明配额方法学（quota.method）")
    if allowed and method not in allowed:
        raise E.InputError("配额方法学 %r 不在规则包允许集合内：%s" % (method, allowed))
    return method


def _derive_alpha(pack, benchmark_value, intensity):
    """由偏离度 X = (BP − Ii) / BP 推出强度系数 α（分段常数取自规则包）。"""
    derivation = (pack.get("quota", {}) or {}).get("derivation") or {}
    slope = _verified(derivation.get("slope"), "quota.derivation.slope")
    band = _verified(derivation.get("band"), "quota.derivation.band")
    cap = _verified(derivation.get("cap"), "quota.derivation.cap")
    if benchmark_value == 0:
        raise E.QuotaUnavailable("行业平衡值（BP）为 0，无法计算碳排放强度偏离度")
    x = (benchmark_value - intensity) / benchmark_value
    if x >= band:
        return cap, x
    if x <= -band:
        return -cap, x
    return slope * x, x


def _scalar(value, label):
    """把试算输入规整为可计算标量（不得静默取 0）。"""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value")
        if value is None:
            raise E.QuotaUnavailable("配额试算输入 %s 缺少 value 字段" % label)
    if isinstance(value, bool) or not isinstance(value, (str, int, E.Decimal)):
        raise E.QuotaUnavailable(
            "配额试算输入 %s 类型非法：%r" % (label, type(value).__name__))
    try:
        return E.as_decimal(value)
    except (ArithmeticError, ValueError):
        raise E.QuotaUnavailable("配额试算输入 %s 无法解析为数值：%r" % (label, value))


def _trial_inputs(params):
    params = params or {}
    return {key: _scalar(params.get(key), key)
            for key in ("benchmark_value", "correction_factor", "output",
                        "historical_intensity")}


def quota_inputs_from_profile(profile):
    """从企业档案抽取试算输入（产量 / 历史强度 / 档案自报参数）。"""
    profile = profile or {}
    explicit = dict(profile.get("quota_inputs") or {})
    output = profile.get("output")
    if output is not None and explicit.get("output") is None:
        explicit["output"] = output
    return {key: _scalar(value, key) for key, value in explicit.items()}


def compute_quota(pack, coord, actual, params=None):
    """按规则包方法学试算配额（``method == "none"`` 时显式不适用，不是 0）。"""
    quota = pack.get("quota", {}) or {}
    method = _resolve_method(pack, (params or {}).get("method"))
    supplied = _trial_inputs(params)
    actual_value = E.as_decimal(actual)

    notes = []
    allocated = None
    parameters = {}
    deviation = None

    if method == METHOD_NONE:
        notes.append("规则包声明本坐标不适用配额试算（method=none），未产生配额量")
    elif method == METHOD_BENCHMARK:
        output = supplied["output"]
        if output is None:
            raise E.QuotaUnavailable(
                "基准法试算需要产量/发电量（output）——试算层不得静默取 0")
        benchmark, bm_source = _resolve(
            _entry_of(pack, "quota.params.benchmark_value"),
            "quota.params.benchmark_value", supplied["benchmark_value"])
        factor, ff_source = _resolve(
            _entry_of(pack, "quota.params.correction_factor"),
            "quota.params.correction_factor", supplied["correction_factor"])
        allocated = E.as_decimal(output) * benchmark * factor
        parameters = {"output": _plain(E.as_decimal(output)),
                      "benchmark_value": {"value": _plain(benchmark), "source": bm_source},
                      "correction_factor": {"value": _plain(factor), "source": ff_source}}
    elif method == METHOD_INTENSITY_COEFFICIENT:
        explicit_alpha = supplied["correction_factor"]
        if explicit_alpha is not None:
            alpha = E.as_decimal(explicit_alpha)
            alpha_source = "caller"
            notes.append("强度系数 α 由调用方显式给定（未按偏离度分段推导）")
        else:
            output = supplied["output"]
            if output is None:
                raise E.QuotaUnavailable(
                    "强度系数法推导 α 需要产量（output）以计算企业实际强度 Ii；"
                    "或直接显式给出 correction_factor")
            benchmark, bm_source = _resolve(
                _entry_of(pack, "quota.params.benchmark_value"),
                "quota.params.benchmark_value", supplied["benchmark_value"])
            intensity = actual_value / E.as_decimal(output)
            alpha, deviation = _derive_alpha(pack, benchmark, intensity)
            alpha_source = "derived"
            parameters["benchmark_value"] = {"value": _plain(benchmark),
                                             "source": bm_source}
            parameters["output"] = _plain(E.as_decimal(output))
            parameters["intensity"] = _plain(intensity)
            parameters["deviation"] = _plain(deviation)
        allocated = actual_value * (E.as_decimal(1) + alpha)
        parameters["correction_factor"] = {"value": _plain(alpha), "source": alpha_source}
    elif method == METHOD_HISTORICAL_INTENSITY:
        output = supplied["output"]
        if output is None:
            raise E.QuotaUnavailable(
                "历史强度法试算需要产量（output）——试算层不得静默取 0")
        intensity = supplied["historical_intensity"]
        if intensity is None:
            raise E.QuotaUnavailable(
                "历史强度法试算需要历史强度（historical_intensity）——试算层不得静默取 0")
        allocated = E.as_decimal(output) * E.as_decimal(intensity)
        parameters = {"output": _plain(E.as_decimal(output)),
                      "historical_intensity": {"value": _plain(E.as_decimal(intensity)),
                                               "source": "caller"}}
    else:
        raise E.InputError("未实现的配额方法学：%r" % method)

    if allocated is None:
        gap = None
        gap_ratio = None
        status = STATUS_NOT_APPLICABLE
    else:
        gap = allocated - actual_value
        gap_ratio = (gap / actual_value) if actual_value != 0 else None
        status = STATUS_OK

    disclaimer = (pack.get("report", {}) or {}).get("disclaimer")
    return {
        "schema": SCHEMA_QUOTA, "coordinate": coord.key, "method": method,
        "method_clause": quota.get("method_clause"), "status": status,
        "actual": _plain(actual_value),
        "allocated": None if allocated is None else _plain(allocated),
        "gap": None if gap is None else _plain(gap),
        "gap_ratio": None if gap_ratio is None else _plain(gap_ratio),
        "actual_raw": str(actual_value),
        "allocated_raw": None if allocated is None else str(allocated),
        "gap_raw": None if gap is None else str(gap),
        "gap_ratio_raw": None if gap_ratio is None else str(gap_ratio),
        "unit": UNIT_EMISSION, "parameters": parameters, "notes": notes,
        "disclaimer_required": True, "disclaimer": disclaimer,
    }


__all__ = [
    "METHOD_BENCHMARK", "METHOD_INTENSITY_COEFFICIENT", "METHOD_HISTORICAL_INTENSITY",
    "METHOD_NONE", "STATUS_OK", "STATUS_NOT_APPLICABLE", "compute_quota",
    "quota_inputs_from_profile", "SCHEMA_QUOTA",
]