"""clauseproof 唯一入口：``clauseproof <subcommand> ...``。

子命令只有两个（器官不得自带 CLI，新增能力一律作为 pack 注册）：

    clauseproof list [--json]
    clauseproof check <slug> --input <file|-> [--basis <file>] [--json]

退出码见 :mod:`clauseproof.core.ledger`：0 无阻断 / 1 有阻断 / 2 输入不合法 / 3 契约违约。
"""

import argparse
import json
import os
import sys

from clauseproof import __version__
from clauseproof.core.basis import Basis, BasisMissing
from clauseproof.core.ledger import (
    EXIT_CONTRACT,
    EXIT_INPUT,
    EXIT_OK,
    ContractError,
    Report,
)
from clauseproof.core.registry import PackMissing, all_packs, get
from clauseproof.packs import load_builtin

PRODUCT = "clauseproof"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clauseproof",
        description="条文判定引擎：中文法规/国标条文 → 可复算判定 + 条款锚点",
    )
    parser.add_argument("--version", action="version", version="%s %s" % (PRODUCT, __version__))
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="列出已注册的器官")
    list_parser.add_argument("--json", action="store_true", help="机器可读输出")

    check_parser = subparsers.add_parser("check", help="用某个器官做一次判定")
    check_parser.add_argument("slug", help="器官 slug")
    check_parser.add_argument("--input", required=True, help="输入 JSON 路径；- 表示 stdin")
    check_parser.add_argument("--basis", help="条文库 JSON 路径（缺省=空条文库）")
    check_parser.add_argument("--json", action="store_true", help="机器可读输出")
    return parser


def main(argv=None) -> int:
    load_builtin()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_OK
    try:
        if args.command == "list":
            return _cmd_list(args)
        if args.command == "check":
            return _cmd_check(args)
    except (ContractError, PackMissing) as exc:
        # 契约违约：无锚点下判定、条文库自相矛盾、器官不存在
        print("%s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return EXIT_CONTRACT
    except (OSError, ValueError, BasisMissing) as exc:
        # 输入不合法：文件缺失、JSON 解析失败、必填字段缺
        print("输入不合法：%s" % exc, file=sys.stderr)
        return EXIT_INPUT
    return EXIT_INPUT


def _cmd_list(args) -> int:
    packs = all_packs()
    if args.json:
        print(json.dumps([pack.as_dict() for pack in packs], ensure_ascii=False, indent=2))
        return EXIT_OK
    if not packs:
        print("（未注册任何器官）")
        return EXIT_OK
    for pack in packs:
        print("%-28s %-10s %s" % (pack.slug, pack.version, pack.summary))
    return EXIT_OK


def _cmd_check(args) -> int:
    pack = get(args.slug)
    subject = _load_subject(args.input)
    missing = [name for name in pack.input_fields if name not in subject]
    if missing:
        raise ValueError("输入缺少必填字段：%s" % ", ".join(missing))
    basis = Basis.from_json(args.basis) if args.basis else Basis.empty()

    report = Report(
        product=PRODUCT,
        organ=pack.slug,
        organ_version=pack.version,
        subject=_subject_label(args.input),
        findings=tuple(pack.evaluate(subject, basis)),
    )
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        for line in report.as_lines():
            print(line)
    return report.exit_code()


def _load_subject(source: str) -> dict:
    if source == "-":
        data = json.load(sys.stdin)
    else:
        with open(source, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("输入必须是 JSON 对象")
    return data


def _subject_label(source: str) -> str:
    if source == "-":
        return "<stdin>"
    return os.path.basename(source)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())