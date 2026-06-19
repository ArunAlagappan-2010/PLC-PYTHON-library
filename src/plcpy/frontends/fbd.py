"""Function Block Diagram (FBD) frontend: block netlist -> IR.

Each network line assigns a signal from a function block:

    t1 := ADD(a, b)        t1 := a + b
    y  := MUL(t1, c)       y  := t1 * c
    f  := AND(p, q, r)     f  := p AND q AND r
    g  := NOT(f)           g  := NOT f
    z  := a                z  := a            (buffer / MOVE)

Blocks: ADD SUB MUL DIV (arithmetic), AND OR (boolean, n-ary), NOT (unary),
GT GE LT LE EQ NE (compare). Intermediate signals not in a VAR section are
declared as locals. Each line lowers to an `Assign`, so FBD converts to/from
every other language and executes in the runtime.
"""
from __future__ import annotations
import re
from .. import ir
from ..registry import ParseResult, register_frontend
from ..diagnostics import Diagnostic, Severity
from ._common import SCOPE, parse_var_section

_NARY = {"ADD": "+", "MUL": "*", "AND": "and", "OR": "or"}
_BINARY = {"SUB": "-", "DIV": "/", "GT": ">", "GE": ">=", "LT": "<", "LE": "<=",
           "EQ": "=", "NE": "<>"}
_BOOL_FUNCS = {"AND", "OR", "NOT", "GT", "GE", "LT", "LE", "EQ", "NE"}
_CALL = re.compile(r"^([A-Za-z_]\w*)\s*:=\s*(.+)$")
_FUNC = re.compile(r"^([A-Za-z_]\w*)\s*\((.*)\)$")
_NAME = re.compile(r"[A-Za-z_]\w*")


def _operand(tok: str) -> ir.Expr | None:
    tok = tok.strip()
    if tok in ("TRUE", "FALSE"):
        return ir.Literal(tok == "TRUE", ir.DataType.BOOL)
    if re.fullmatch(r"[0-9]+\.[0-9]+", tok):
        return ir.Literal(float(tok), ir.DataType.REAL)
    if re.fullmatch(r"[0-9]+", tok):
        return ir.Literal(int(tok), ir.DataType.INT)
    if _NAME.fullmatch(tok):
        return ir.VarRef(tok)
    return None


def _split_args(s: str) -> list[str]:
    args, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            args.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        args.append(cur)
    return [a.strip() for a in args]


def _build(expr_text: str, diagnostics: list, lineno: int) -> tuple[ir.Expr | None, bool]:
    """Return (expr, is_bool). is_bool drives temp-variable typing."""
    expr_text = expr_text.strip()
    fm = _FUNC.match(expr_text)
    if not fm:
        e = _operand(expr_text)
        if e is None:
            diagnostics.append(Diagnostic(f"bad FBD operand {expr_text!r}",
                                          Severity.ERROR, line=lineno, code="FBD"))
        is_bool = isinstance(e, ir.Literal) and e.type is ir.DataType.BOOL
        return e, is_bool
    func = fm.group(1).upper()
    args = [_build(a, diagnostics, lineno)[0] for a in _split_args(fm.group(2))]
    args = [a for a in args if a is not None]
    is_bool = func in _BOOL_FUNCS
    if func == "NOT" and len(args) == 1:
        return ir.UnaryOp("not", args[0]), True
    if func in _NARY and args:
        acc = args[0]
        for a in args[1:]:
            acc = ir.BinOp(_NARY[func], acc, a)
        return acc, is_bool
    if func in _BINARY and len(args) == 2:
        return ir.BinOp(_BINARY[func], args[0], args[1]), is_bool
    diagnostics.append(Diagnostic(f"unsupported FBD block {func!r}",
                                  Severity.UNSUPPORTED, line=lineno, code="FBD"))
    return None, False


def parse_fbd(text: str) -> ParseResult:
    diagnostics: list[Diagnostic] = []
    vars_: list[ir.VarDecl] = []
    declared: set[str] = set()
    body: list[ir.Stmt] = []
    name = "Program"
    lines = text.splitlines()
    idx = 0
    while idx < len(lines):
        raw = lines[idx].strip()
        idx += 1
        if not raw:
            continue
        kw = raw.split()[0].upper()
        if kw == "PROGRAM":
            parts = raw.split()
            name = parts[1] if len(parts) > 1 else "Program"
        elif kw == "END_PROGRAM":
            break
        elif kw in SCOPE:
            before = len(vars_)
            idx = parse_var_section(kw, lines, idx, vars_, diagnostics)
            declared.update(v.name for v in vars_[before:])
        elif kw in ("NETWORK", "END_NETWORK"):
            continue
        else:
            m = _CALL.match(raw)
            if not m:
                diagnostics.append(Diagnostic(f"bad FBD line {raw!r}",
                                              Severity.UNSUPPORTED, line=idx, code="FBD"))
                continue
            target = m.group(1)
            expr, is_bool = _build(m.group(2), diagnostics, idx)
            if expr is None:
                continue
            if target not in declared:
                dt = ir.DataType.BOOL if is_bool else ir.DataType.INT
                vars_.append(ir.VarDecl(target, dt, ir.VarScope.LOCAL))
                declared.add(target)
            body.append(ir.Assign(target, expr))
    return ParseResult(ir.Program(name, vars_, body), diagnostics)


register_frontend("fbd", parse_fbd)
