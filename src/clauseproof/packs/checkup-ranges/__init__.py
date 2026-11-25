"""器官 ``checkup-ranges``：体检指标判定（区间越界标记 + 条款锚点）。

规模：判定面来自 target-map ① 行的旧仓（19 条内置区间条目、
四态比较、三级优先选区间、主体适用域硬门）。

本器官只做一件事：**给一条测量记录，判它是否落在参考区间内，并说明依据是谁**。
它不打印、不读文件、不读环境变量、不读时钟，也不带自己的参数解析器——入口只有
``clauseproof check checkup-ranges --input <file|-> --basis <file>``。

判定账本口径（SKELETON-SPEC §3–§5）：

==============  ==========================================================
来源四态         本器官 verdict
==============  ==========================================================
``normal``       ``pass``（必带锚点：区间来源）
``high``/``low`` ``fail``（必带锚点；阻断 → 退出码 1）
``not_assessed`` ``not_applicable`` + message 写明**为什么拒判**（无锚点）
==============  ==========================================================

依据只从条文库取：``basis.anchor(clause_id)``。报告自印区间的锚点是
``range:report-printed``（"以报告单/LIS 印制区间为准"）；内置区间条目的锚点是
``wst:<指标名>``（该指标的标准分册），且**只有已核对条目**才会走到这条锚点。
条文库缺所需条款 → ``BasisMissing`` 冒到 CLI（退出码 3）；条文库版本与区间库快照
不符 → ``ContractError``（退出码 3，即 SKELETON-SPEC §5「依据包版本缺失」）。
"""

from typing import Iterable, Mapping, Sequence, Tuple

from clauseproof.core.basis import Basis
from clauseproof.core.ledger import (
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ContractError,
    Finding,
)
from clauseproof.core.registry import Pack, register

from .engine import (
    FLAG_HIGH,
    FLAG_LOW,
    FLAG_NORMAL,
    RawJudgement,
    judge_measurement,
    validate_subject,
)
from .registry import INDICATORS, REGISTRY_VERSION

SLUG = "checkup-ranges"
VERSION = "0.2.0"
SUMMARY = "体检指标区间判定（报告自印区间优先，内置区间须已核对；越界即拦截）"

#: 输入必填字段（与来源 ``Measurement`` 的硬性要求一致）
INPUT_FIELDS: Tuple[str, ...] = ("canonical_name", "value", "unit")

#: 规则单号：一条测量 = 一个结论，规则 id 由来源四态派生
RULE_JUDGE = "measurement.range"


def _require_basis_version(basis: Basis) -> None:
    if basis.version != REGISTRY_VERSION:
        raise ContractError(
            "条文库版本不符：本器官依据区间库快照 %s 核对，条文库实为 %s"
            % (REGISTRY_VERSION, basis.version)
        )


def _message(raw: RawJudgement) -> str:
    if raw.flag in (FLAG_NORMAL, FLAG_HIGH, FLAG_LOW):
        return raw.message
    return "未判定（%s）：%s" % (raw.code, raw.message)


def _to_finding(raw: RawJudgement, basis: Basis) -> Finding:
    anchor = basis.anchor(raw.clause_id) if raw.clause_id else None
    evidence = {
        "flag": raw.flag,
        "code": raw.code,
        "range_source": raw.range_source,
    }
    evidence.update(raw.evidence)
    if raw.flag == FLAG_NORMAL:
        verdict = PASS
    elif raw.flag in (FLAG_HIGH, FLAG_LOW):
        verdict = FAIL
    else:
        verdict = NOT_APPLICABLE
    return Finding(
        rule_id="%s:%s" % (RULE_JUDGE, raw.canonical_name),
        verdict=verdict,
        message=_message(raw),
        anchor=anchor,
        evidence=evidence,
    )


def judge(subject: Mapping, indicators: Sequence = INDICATORS) -> RawJudgement:
    """判定用的纯函数入口（测试与 ``evaluate`` 共用同一条路径）。"""
    validate_subject(subject)
    return judge_measurement(subject, tuple(indicators))


def evaluate(subject: Mapping, basis: Basis) -> Iterable[Finding]:
    """器官入口（签名固定，见 SKELETON-SPEC §2）。"""
    raw = judge(subject)
    _require_basis_version(basis)
    return (_to_finding(raw, basis),)


PACK = register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary=SUMMARY,
        input_fields=INPUT_FIELDS,
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "PACK", "evaluate", "judge"]