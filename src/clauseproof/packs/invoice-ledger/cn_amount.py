"""人民币小写金额 → 中文大写金额（迁自来源 ``cn_amount``，纯 stdlib）。

判定内核 R-ARITH-02（大写金额一致）用本模块复算票面大写；来源生成器与规则
共用同一实现，故逐条测试直接迁移（17 个已知值 + 四舍五入 + 非法输入）。

大写规则（财务惯例）：
- 数字：零壹贰叁肆伍陆柒捌玖；组内位单位：拾佰仟，组单位：万/亿/万亿；
- 中间连续零只写一个「零」，末尾零不写（105000 → 壹拾万零伍仟）；
- 角>0 写「X角」；角=0 且分>0 且有元部时先补「零」；无元部时角/分直接开头；
- 输入为 Decimal 可解析的非负金额文本，超两位小数按四舍五入取分。
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_INNER = ("", "拾", "佰", "仟")
_GROUP_UNITS = ("", "万", "亿", "万亿")


def _integer_to_cn(number: int) -> str:
    """非零正整数 → 大写（组单位挂组尾、中间零合并、末尾零丢弃）。"""
    if number < 0:
        raise ValueError("整数部必须非负: %d" % number)
    if number == 0:
        return "零"
    text = str(number)
    if len(text) > 16:
        raise ValueError("金额整数部超出可表示范围（>=万亿亿）: %s" % text)
    parts = []
    group_dirty = False
    zero_pending = False
    for index, ch in enumerate(text):
        pos = len(text) - 1 - index
        group_idx, inner_pos = divmod(pos, 4)
        if inner_pos == 3 and index > 0 and group_dirty:
            parts.append(_GROUP_UNITS[group_idx + 1])
            group_dirty = False
        digit = int(ch)
        if digit == 0:
            zero_pending = True
            continue
        if zero_pending and parts:
            parts.append("零")
        zero_pending = False
        group_dirty = True
        parts.append(_DIGITS[digit] + _INNER[inner_pos])
    return "".join(parts)


def encode_amount(value) -> str:
    """金额文本（如 ``"1130.00"``）→ 中文大写（如 ``"壹仟壹佰叁拾元整"``）。

    负数与不可解析输入抛 ``ValueError``（调用侧按「票面异常」处理，不静默）。
    """
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("金额不可解析: %r" % (value,)) from exc
    if amount < 0:
        raise ValueError("金额不能为负: %s" % amount)
    fen_total = int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))
    yuan, frac = divmod(fen_total, 100)
    jiao, fen = divmod(frac, 10)

    parts = []
    if yuan:
        parts.append(_integer_to_cn(yuan) + "元")
    if jiao:
        parts.append(_DIGITS[jiao] + "角")
    elif fen and yuan:
        parts.append("零")
    if fen:
        parts.append(_DIGITS[fen] + "分")
    if not parts:
        return "零元整"
    if not (jiao or fen):
        parts.append("整")
    return "".join(parts)