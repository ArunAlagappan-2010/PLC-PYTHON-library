from __future__ import annotations
import argparse
import sys
from .convert import convert


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plcpy")
    sub = parser.add_subparsers(dest="cmd", required=True)
    conv = sub.add_parser("convert", help="convert a source file between languages")
    conv.add_argument("file")
    conv.add_argument("--from", dest="from_lang", required=True)
    conv.add_argument("--to", dest="to_lang", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "convert":
        source = open(args.file, encoding="utf-8").read()
        result = convert(source, args.from_lang, args.to_lang)
        for d in result.diagnostics:
            print(f"{d.severity.value}: {d.message}", file=sys.stderr)
        if result.code is None:
            return 2
        print(result.code, end="")
        return 0
    return 1
