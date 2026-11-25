"""clauseproof 内核契约测试（Stage 1 · 骨架）。

锁三件事：
1. 无锚点不下判定（构造即拦，不靠文档）；
2. 账本输出确定性（同一输入两次运行字节一致，无时间戳/绝对路径）；
3. 退出码 0/1/2/3 的边界。
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from clauseproof import cli  # noqa: E402
from clauseproof.core import (  # noqa: E402
    EXIT_BLOCKED,
    EXIT_CONTRACT,
    EXIT_INPUT,
    EXIT_OK,
    FAIL,
    NOT_APPLICABLE,
    PASS,
    Anchor,
    Basis,
    BasisMissing,
    Clause,
    ContractError,
    Finding,
    Pack,
    Report,
    all_packs,
    get,
    register,
)

ANCHOR = Anchor(clause_id="demo-1", path="示例法/第一条", version="2026.1")


# --------------------------------------------------------------------------
# 注册表
# --------------------------------------------------------------------------
def _noop_evaluate(subject, basis):
    return ()


def test_register_and_get_pack():
    pack = Pack(
        slug="probe-alpha",
        version="0.0.1",
        summary="测试用器官",
        input_fields=("text",),
        evaluate=_noop_evaluate,
    )
    assert register(pack) is pack
    assert get("probe-alpha") is pack
    slugs = [p.slug for p in all_packs()]
    assert slugs == sorted(slugs), "all_packs 必须按 slug 排序"
    assert "probe-alpha" in slugs


def test_duplicate_register_is_rejected():
    with pytest.raises(ValueError):
        register(
            Pack(
                slug="probe-alpha",
                version="0.0.2",
                summary="重复",
                input_fields=("text",),
                evaluate=_noop_evaluate,
            )
        )


def test_pack_rejects_bad_slug_and_empty_fields():
    with pytest.raises(ValueError):
        Pack(slug="Bad Slug", version="1", summary="x", input_fields=("a",), evaluate=_noop_evaluate)
    with pytest.raises(ValueError):
        Pack(slug="probe-beta", version="1", summary="x", input_fields=(), evaluate=_noop_evaluate)
    with pytest.raises(ValueError):
        Pack(slug="probe-beta", version="", summary="x", input_fields=("a",), evaluate=_noop_evaluate)


def test_missing_pack_is_reported():
    from clauseproof.core import PackMissing

    with pytest.raises(PackMissing):
        get("no-such-pack")


def test_builtin_manifest_is_sorted_and_loadable():
    """器官清单必须字典序（输出可复现），且 ``load_builtin()`` 不因空表报错。"""
    from clauseproof.packs import BUILTIN_MODULES, load_builtin

    assert list(BUILTIN_MODULES) == sorted(BUILTIN_MODULES)
    load_builtin()


# --------------------------------------------------------------------------
# 账本：无锚点不下判定
# --------------------------------------------------------------------------
def test_fail_without_anchor_is_contract_violation():
    with pytest.raises(ContractError):
        Finding(rule_id="r1", verdict=FAIL, message="不合格")


def test_pass_without_anchor_is_contract_violation():
    with pytest.raises(ContractError):
        Finding(rule_id="r1", verdict=PASS, message="合格")


def test_not_applicable_without_anchor_is_allowed():
    finding = Finding(rule_id="r1", verdict=NOT_APPLICABLE, message="条文库缺该条款")
    assert finding.anchor is None
    assert finding.id == "r1@na"


def test_illegal_verdict_is_rejected():
    with pytest.raises(ContractError):
        Finding(rule_id="r1", verdict="maybe", message="x", anchor=ANCHOR)


def test_anchor_rejects_empty_fields():
    with pytest.raises(ContractError):
        Anchor(clause_id="c1", path="", version="2026.1")


def test_report_is_deterministic_and_sorted():
    findings = (
        Finding(rule_id="r2", verdict=PASS, message="第二条", anchor=ANCHOR),
        Finding(rule_id="r1", verdict=FAIL, message="第一条", anchor=ANCHOR),
    )
    report = Report(product="clauseproof", organ="o", organ_version="1", subject="s", findings=findings)
    assert [f.rule_id for f in report.findings] == ["r1", "r2"]
    first = json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=False)
    second = json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=False)
    assert first == second
    assert set(report.as_dict()) == {"product", "organ", "organ_version", "subject", "summary", "records"}


def test_report_exit_code_and_summary():
    blocking = Report(
        product="clauseproof",
        organ="o",
        organ_version="1",
        subject="s",
        findings=(Finding(rule_id="r1", verdict=FAIL, message="x", anchor=ANCHOR),),
    )
    assert blocking.exit_code() == EXIT_BLOCKED
    assert blocking.summary()["blocking"] == 1

    clean = Report(
        product="clauseproof",
        organ="o",
        organ_version="1",
        subject="s",
        findings=(Finding(rule_id="r1", verdict=PASS, message="x", anchor=ANCHOR),),
    )
    assert clean.exit_code() == EXIT_OK
    assert clean.summary()["blocking"] == 0


def test_report_rejects_duplicate_record_ids():
    finding = Finding(rule_id="r1", verdict=FAIL, message="x", anchor=ANCHOR)
    with pytest.raises(ContractError):
        Report(product="clauseproof", organ="o", organ_version="1", subject="s", findings=(finding, finding))


# --------------------------------------------------------------------------
# 条文库
# --------------------------------------------------------------------------
def test_basis_from_dict_and_anchor():
    basis = Basis.from_dict(
        {
            "version": "2026.1",
            "clauses": [{"clause_id": "demo-1", "path": "示例法/第一条", "text": "原文"}],
        }
    )
    assert len(basis) == 1
    anchor = basis.anchor("demo-1")
    assert anchor.version == "2026.1"
    assert anchor.path == "示例法/第一条"
    assert anchor.quote == "原文"


def test_basis_missing_clause():
    basis = Basis.empty(version="2026.1")
    with pytest.raises(BasisMissing):
        basis.anchor("demo-1")


def test_basis_rejects_version_mismatch_and_duplicates():
    with pytest.raises(ContractError):
        Basis(version="2026.1", clauses=(Clause(clause_id="c1", path="p", version="2025.1"),))
    with pytest.raises(ContractError):
        Basis(
            version="2026.1",
            clauses=(
                Clause(clause_id="c1", path="p", version="2026.1"),
                Clause(clause_id="c1", path="q", version="2026.1"),
            ),
        )
    with pytest.raises(ContractError):
        Basis(version="")


def test_basis_as_dict_roundtrip():
    basis = Basis(version="2026.1", clauses=(Clause(clause_id="c1", path="p", version="2026.1"),))
    assert Basis.from_dict(basis.as_dict()).clause_ids() == ["c1"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _probe_evaluate(subject, basis):
    clause = basis.clause("demo-1")
    if clause is None:
        return (Finding(rule_id="demo-rule", verdict=NOT_APPLICABLE, message="条文库缺 demo-1"),)
    verdict = FAIL if "保证治愈" in subject.get("text", "") else PASS
    return (
        Finding(
            rule_id="demo-rule",
            verdict=verdict,
            message="命中禁用表述" if verdict == FAIL else "未命中禁用表述",
            anchor=basis.anchor("demo-1"),
            evidence={"matched": verdict == FAIL},
        ),
    )


@pytest.fixture(scope="module", autouse=True)
def probe_pack():
    register(
        Pack(
            slug="demo-probe",
            version="0.0.1",
            summary="契约测试用器官（非真实条文）",
            input_fields=("text",),
            evaluate=_probe_evaluate,
        )
    )


def test_cli_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert "clauseproof" in capsys.readouterr().out


def test_cli_list(capsys):
    assert cli.main(["list"]) == EXIT_OK
    assert "demo-probe" in capsys.readouterr().out
    assert cli.main(["list", "--json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)


def test_cli_unknown_pack_is_contract_error(capsys, tmp_path):
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"text": "x"}), encoding="utf-8")
    assert cli.main(["check", "no-such", "--input", str(target)]) == EXIT_CONTRACT
    assert "PackMissing" in capsys.readouterr().err


def test_cli_missing_input_file_is_input_error(capsys, tmp_path):
    assert cli.main(["check", "demo-probe", "--input", str(tmp_path / "nope.json")]) == EXIT_INPUT


def test_cli_missing_required_field_is_input_error(capsys, tmp_path):
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"other": "x"}), encoding="utf-8")
    assert cli.main(["check", "demo-probe", "--input", str(target)]) == EXIT_INPUT
    assert "text" in capsys.readouterr().err


def test_cli_end_to_end_blocking_and_deterministic(capsys, tmp_path):
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"text": "本品保证治愈"}), encoding="utf-8")
    basis_path = tmp_path / "basis.json"
    basis_path.write_text(
        json.dumps(
            {"version": "2026.1", "clauses": [{"clause_id": "demo-1", "path": "示例法/第一条"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert cli.main(["check", "demo-probe", "--input", str(target), "--basis", str(basis_path), "--json"]) == EXIT_BLOCKED
    first = capsys.readouterr().out
    assert str(tmp_path) not in first, "输出不得含绝对路径"
    payload = json.loads(first)
    assert payload["summary"]["blocking"] == 1
    assert payload["records"][0]["basis_ref"]["clause_id"] == "demo-1"

    cli.main(["check", "demo-probe", "--input", str(target), "--basis", str(basis_path), "--json"])
    assert capsys.readouterr().out == first, "同一输入两次运行必须字节一致"


def test_cli_without_basis_degrades_to_not_applicable(capsys, tmp_path):
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"text": "本品保证治愈"}), encoding="utf-8")
    assert cli.main(["check", "demo-probe", "--input", str(target)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "not_applicable" in out
    assert "阻断 0 条" in out