"""Function Block Diagram (FBD) backend: IR -> block netlist.

Renders each `Assign` as `target := FUNC(args)`, nesting blocks for nested
expressions. Control-flow statements have no FBD network form and emit an
`(* unsupported ... *)` comment.
"""
from __future__ import annotations
from .. import ir
from ..registry import register_backend

_SCOPE_KW = {ir.VarScope.INPUT: "VAR_INPUT", ir.VarScope.OUTPUT: "VAR_OUTPUT",
             ir.VarScope.LOCAL: "VAR"}
_FUNC = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "and": "AND", "or": "OR",
         ">": "GT", ">=": "GE", "<": "LT", "<=": "LE", "=": "EQ", "<>": "NE"}


def _fbd(e: ir.Expr) -> str:
    if isinstance(e, ir.Literal):
        if e.type is ir.DataType.BOOL:
            return "TRUE" if e.value else "FALSE"
        return str(e.value)
    if isinstance(e, ir.VarRef):
        return e.name
    if isinstance(e, ir.UnaryOp):
        if e.op == "not":
            return f"NOT({_fbd(e.operand)})"
        return f"SUB(0, {_fbd(e.operand)})"
    if isinstance(e, ir.BinOp):
        return f"{_FUNC[e.op]}({_fbd(e.left)}, {_fbd(e.right)})"
    if isinstance(e, ir.Member):
        return f"{e.instance}.{e.member}"
    raise TypeError(f"unhandled expr {e!r}")


def emit_fbd(program: ir.Program) -> str:
    lines = [f"PROGRAM {program.name}"]
    for scope in (ir.VarScope.INPUT, ir.VarScope.OUTPUT, ir.VarScope.LOCAL):
        decls = [v for v in program.vars if v.scope is scope]
        if not decls:
            continue
        lines.append(_SCOPE_KW[scope])
        for v in decls:
            lines.append(f"    {v.name} : {v.type.value};")
        lines.append("END_VAR")
    lines.append("NETWORK")
    for s in program.body:
        if isinstance(s, ir.Assign):
            lines.append(f"    {s.target} := {_fbd(s.value)}")
        else:
            lines.append(f"    (* unsupported in FBD: {type(s).__name__} *)")
    lines.append("END_NETWORK")
    lines.append("END_PROGRAM")
    return "\n".join(lines) + "\n"


register_backend("fbd", emit_fbd)
