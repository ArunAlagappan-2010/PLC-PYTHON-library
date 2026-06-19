"""Instruction List (IL) frontend: IL text -> IR.

IL is a stack/accumulator language. We simulate the "current result" (CR)
register at parse time to rebuild expressions:

    LD x        ->  CR = x
    ADD 1       ->  CR = (CR + 1)
    ST y        ->  emit  y := CR

Supported instructions: LD, ST, NOT, and the binary ops
ADD SUB MUL DIV AND OR GT GE LT LE EQ NE. Control flow (jumps/labels) is
outside the Phase-2 subset and yields an `unsupported` diagnostic.
"""
from __future__ import annotations
import re
from .. import ir
from ..registry import ParseResult, register_frontend
from ..diagnostics import Diagnostic, Severity

_TYPES = {"BOOL": ir.DataType.BOOL, "INT": ir.DataType.INT, "REAL": ir.DataType.REAL}
_SCOPE = {"VAR_INPUT": ir.VarScope.INPUT, "VAR_OUTPUT": ir.VarScope.OUTPUT,
          "VAR": ir.VarScope.LOCAL}
_BINOP = {"ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/", "AND": "and", "OR": "or",
          "GT": ">", "GE": ">=", "LT": "<", "LE": "<=", "EQ": "=", "NE": "<>"}

_COMMENT = re.compile(r"\(\*.*?\*\)", re.DOTALL)
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _operand(tok: str, diagnostics: list, lineno: int) -> ir.Expr | None:
    if tok in ("TRUE", "FALSE"):
        return ir.Literal(tok == "TRUE", ir.DataType.BOOL)
    if re.fullmatch(r"[0-9]+\.[0-9]+", tok):
        return ir.Literal(float(tok), ir.DataType.REAL)
    if re.fullmatch(r"[0-9]+", tok):
        return ir.Literal(int(tok), ir.DataType.INT)
    if _NAME.fullmatch(tok):
        return ir.VarRef(tok)
    diagnostics.append(Diagnostic(f"bad IL operand {tok!r}", Severity.ERROR,
                                  line=lineno, code="IL"))
    return None


def parse_il(text: str) -> ParseResult:
    text = _COMMENT.sub(" ", text)
    diagnostics: list[Diagnostic] = []
    vars_: list[ir.VarDecl] = []
    body: list[ir.Stmt] = []
    name = "Program"
    cr: ir.Expr | None = None

    lines = text.splitlines()
    idx = 0
    while idx < len(lines):
        raw = lines[idx].strip()
        idx += 1
        if not raw:
            continue
        head = raw.split()
        kw = head[0].upper()

        if kw == "PROGRAM":
            name = head[1] if len(head) > 1 else "Program"
            continue
        if kw == "END_PROGRAM":
            break
        if kw in _SCOPE:
            scope = _SCOPE[kw]
            while idx < len(lines):
                decl = lines[idx].strip().rstrip(";").strip()
                idx += 1
                if not decl:
                    continue
                if decl.upper() == "END_VAR":
                    break
                m = re.match(r"([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)", decl)
                if not m:
                    continue
                vname, tname = m.group(1), m.group(2)
                dt = _TYPES.get(tname.upper())
                if dt is None:
                    diagnostics.append(Diagnostic(
                        f"unsupported type {tname!r}", Severity.UNSUPPORTED,
                        line=idx, code="IL_TYPE"))
                    dt = ir.DataType.INT
                vars_.append(ir.VarDecl(vname, dt, scope))
            continue

        # instruction
        op = kw
        arg = raw[len(head[0]):].strip()
        if op == "LD":
            cr = _operand(arg, diagnostics, idx)
        elif op == "ST":
            if cr is None:
                diagnostics.append(Diagnostic("ST with empty accumulator",
                                              Severity.ERROR, line=idx, code="IL"))
            else:
                body.append(ir.Assign(arg, cr))
        elif op == "NOT":
            if cr is not None:
                cr = ir.UnaryOp("not", cr)
        elif op in _BINOP:
            rhs = _operand(arg, diagnostics, idx)
            if cr is None or rhs is None:
                diagnostics.append(Diagnostic(f"{op} with empty accumulator",
                                              Severity.ERROR, line=idx, code="IL"))
            else:
                cr = ir.BinOp(_BINOP[op], cr, rhs)
        else:
            diagnostics.append(Diagnostic(
                f"unsupported IL instruction {op!r}", Severity.UNSUPPORTED,
                line=idx, code="IL"))

    program = ir.Program(name, vars_, body)
    return ParseResult(program, diagnostics)


register_frontend("il", parse_il)
