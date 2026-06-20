from __future__ import annotations
import argparse
import sys
from .convert import convert
from .registry import get_frontend


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plcpy")
    sub = parser.add_subparsers(dest="cmd", required=True)

    conv = sub.add_parser("convert", help="convert a source file between languages")
    conv.add_argument("file")
    conv.add_argument("--from", dest="from_lang", required=True)
    conv.add_argument("--to", dest="to_lang", required=True)

    vis = sub.add_parser("visualize", help="render side-by-side code + flow diagram HTML")
    vis.add_argument("file")
    vis.add_argument("--from", dest="from_lang", required=True)
    vis.add_argument("--to", dest="to_lang", default="python",
                     help="language for the side-by-side pane (default: python)")
    vis.add_argument("-o", "--out", required=True, help="output .html path")

    sub.add_parser("lsp", help="run the PLC language server over stdio")

    args = parser.parse_args(argv)

    if args.cmd == "lsp":
        from .lsp import main as lsp_main
        return lsp_main()

    if args.cmd == "convert":
        source = open(args.file, encoding="utf-8").read()
        result = convert(source, args.from_lang, args.to_lang)
        for d in result.diagnostics:
            print(f"{d.severity.value}: {d.message}", file=sys.stderr)
        if result.code is None:
            return 2
        print(result.code, end="")
        return 0

    if args.cmd == "visualize":
        from .visualize import render_html
        source = open(args.file, encoding="utf-8").read()
        parsed = get_frontend(args.from_lang)(source)
        for d in parsed.diagnostics:
            print(f"{d.severity.value}: {d.message}", file=sys.stderr)
        if parsed.program is None:
            return 2
        target = convert(source, args.from_lang, args.to_lang)
        html = render_html(source, args.from_lang, target.code or "",
                           args.to_lang, parsed.program)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"wrote {args.out}")
        return 0

    return 1
