"""Ladder Diagram (LD) backend: IR boolean assignments -> textual ladder.

Renders each boolean `Assign` whose RHS is a contact-expressible boolean
formula as a rung. AND chains become series contacts, OR chains become
parallel contacts, NOT becomes a normally-closed contact (or a negated coil
when the whole RHS is negated). Anything not expressible as ladder (arithmetic,
control flow, non-BOOL assigns) emits an `(* unsupported rung *)` comment.
"""
from __future__ import annotations
from .. import ir
from ..registry import register_backend

_SCOPE_KW = {ir.VarScope.INPUT: "VAR_INPUT", ir.VarScope.OUTPUT: "VAR_OUTPUT",
             ir.VarScope.LOCAL: "VAR"}


def _or_names(e: ir.Expr) -> list[str] | None:
    if isinstance(e, ir.VarRef):
        return [e.name]
    if isinstance(e, ir.BinOp) and e.op == "or":
        left = _or_names(e.left)
        right = _or_names(e.right)
        if left is None or right is None:
            return None
        return left + right
    return None


def _contact(e: ir.Expr) -> str | None:
    neg = ""
    if isinstance(e, ir.UnaryOp) and e.op == "not":
        neg = "/"
        e = e.operand
    names = _or_names(e)
    if names is None:
        return None
    return f"[{neg} " + " | ".join(names) + " ]"


def _and_terms(e: ir.Expr) -> list[ir.Expr]:
    if isinstance(e, ir.BinOp) and e.op == "and":
        return _and_terms(e.left) + [e.right]
    return [e]


def _rung(assign: ir.Assign) -> str | None:
    expr = assign.value
    coil_neg = ""
    if isinstance(expr, ir.UnaryOp) and expr.op == "not":
        inner = _and_terms(expr.operand)
        if all(_contact(t) is not None for t in inner):
            coil_neg = "/"
            expr = expr.operand
    contacts = []
    for t in _and_terms(expr):
        c = _contact(t)
        if c is None:
            return None
        contacts.append(c)
    return "--" + "--".join(contacts) + f"--({coil_neg} {assign.target} )"


def emit_ld(program: ir.Program) -> str:
    lines = [f"PROGRAM {program.name}"]
    for scope in (ir.VarScope.INPUT, ir.VarScope.OUTPUT, ir.VarScope.LOCAL):
        decls = [v for v in program.vars if v.scope is scope]
        if not decls:
            continue
        lines.append(_SCOPE_KW[scope])
        for v in decls:
            lines.append(f"    {v.name} : {v.type.value};")
        lines.append("END_VAR")
    for s in program.body:
        if isinstance(s, ir.Assign):
            rung = _rung(s)
            if rung is None:
                lines.append(f"(* unsupported rung: {s.target} *)")
            else:
                lines.append("RUNG")
                lines.append(f"    {rung}")
                lines.append("END_RUNG")
        else:
            lines.append("(* unsupported in LD: non-assignment statement *)")
    lines.append("END_PROGRAM")
    return "\n".join(lines) + "\n"


register_backend("ld", emit_ld)
