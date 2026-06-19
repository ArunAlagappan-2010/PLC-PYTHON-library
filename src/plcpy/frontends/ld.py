"""Ladder Diagram (LD) frontend: textual ladder -> IR boolean assignments.

A rung is a series of contact-groups driving a coil. Notation:

    --[ a ]--[/ b ]--( y )        y := a AND (NOT b)
    --[ a | run ]--[/ b ]--( run ) run := (a OR run) AND (NOT b)   (seal-in)
    --[ a ]--(/ y )               y := NOT a                       (negated coil)

  [ x ]    normally-open contact (x)
  [/ x ]   normally-closed contact (NOT x)
  [ a | b ] parallel contacts (a OR b)
  --       series connection (AND)
  ( y )    coil (assign);  (/ y ) negated coil

Each rung lowers to a single boolean `Assign`, so LD converts to/from every
other language and executes in the scan-cycle runtime for free.

PLCopen XML import is future work; this textual form is the Phase-3 baseline.
"""
from __future__ import annotations
import re
from .. import ir
from ..registry import ParseResult, register_frontend
from ..diagnostics import Diagnostic, Severity
from ._common import SCOPE, parse_var_section

_GROUP = re.compile(r"\[\s*(/?)\s*([^\]]+?)\s*\]")
_COIL = re.compile(r"\(\s*(/?)\s*([A-Za-z_]\w*)\s*\)")


def _parse_rung(text: str, diagnostics: list, lineno: int) -> ir.Assign | None:
    coil_m = _COIL.search(text)
    if not coil_m:
        diagnostics.append(Diagnostic("rung has no coil", Severity.ERROR,
                                      line=lineno, code="LD"))
        return None
    coil_neg = coil_m.group(1) == "/"
    coil = coil_m.group(2)
    groups = _GROUP.findall(text[:coil_m.start()])
    if not groups:
        expr: ir.Expr = ir.Literal(True, ir.DataType.BOOL)
    else:
        and_terms: list[ir.Expr] = []
        for neg, gbody in groups:
            names = [n.strip() for n in gbody.split("|") if n.strip()]
            term: ir.Expr = ir.VarRef(names[0])
            for n in names[1:]:
                term = ir.BinOp("or", term, ir.VarRef(n))
            if neg == "/":
                term = ir.UnaryOp("not", term)
            and_terms.append(term)
        expr = and_terms[0]
        for t in and_terms[1:]:
            expr = ir.BinOp("and", expr, t)
    if coil_neg:
        expr = ir.UnaryOp("not", expr)
    return ir.Assign(coil, expr)


def parse_ld(text: str) -> ParseResult:
    diagnostics: list[Diagnostic] = []
    vars_: list[ir.VarDecl] = []
    body: list[ir.Stmt] = []
    name = "Program"
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
        elif kw == "END_PROGRAM":
            break
        elif kw in SCOPE:
            idx = parse_var_section(kw, lines, idx, vars_, diagnostics)
        elif kw == "RUNG":
            rung_text = ""
            while idx < len(lines):
                line = lines[idx].strip()
                idx += 1
                if line.upper() == "END_RUNG":
                    break
                rung_text += " " + line
            stmt = _parse_rung(rung_text, diagnostics, idx)
            if stmt is not None:
                body.append(stmt)
        else:
            diagnostics.append(Diagnostic(f"unexpected LD line {raw!r}",
                                          Severity.UNSUPPORTED, line=idx, code="LD"))
    return ParseResult(ir.Program(name, vars_, body), diagnostics)


register_frontend("ld", parse_ld)
