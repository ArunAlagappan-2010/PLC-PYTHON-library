from __future__ import annotations
from .. import ir
from ..registry import register_backend

_SCOPE_KW = {ir.VarScope.INPUT: "VAR_INPUT", ir.VarScope.OUTPUT: "VAR_OUTPUT",
             ir.VarScope.LOCAL: "VAR"}


def _expr(e: ir.Expr) -> str:
    if isinstance(e, ir.Literal):
        if e.type is ir.DataType.BOOL:
            return "TRUE" if e.value else "FALSE"
        return str(e.value)
    if isinstance(e, ir.VarRef):
        return e.name
    if isinstance(e, ir.UnaryOp):
        op = "NOT " if e.op == "not" else "-"
        return f"{op}{_expr(e.operand)}"
    if isinstance(e, ir.BinOp):
        op = {"and": "AND", "or": "OR"}.get(e.op, e.op)
        return f"{_expr(e.left)} {op} {_expr(e.right)}"
    raise TypeError(f"unhandled expr {e!r}")


def _stmts(stmts: list[ir.Stmt], indent: int) -> list[str]:
    pad = "    " * indent
    out: list[str] = []
    for s in stmts:
        if isinstance(s, ir.Assign):
            out.append(f"{pad}{s.target} := {_expr(s.value)};")
        elif isinstance(s, ir.If):
            out.append(f"{pad}IF {_expr(s.cond)} THEN")
            out.extend(_stmts(s.then, indent + 1))
            for cond, body in s.elifs:
                out.append(f"{pad}ELSIF {_expr(cond)} THEN")
                out.extend(_stmts(body, indent + 1))
            if s.orelse:
                out.append(f"{pad}ELSE")
                out.extend(_stmts(s.orelse, indent + 1))
            out.append(f"{pad}END_IF;")
        else:
            raise TypeError(f"unhandled stmt {s!r}")
    return out


def emit_st(program: ir.Program) -> str:
    lines = [f"PROGRAM {program.name}"]
    for scope in (ir.VarScope.INPUT, ir.VarScope.OUTPUT, ir.VarScope.LOCAL):
        decls = [v for v in program.vars if v.scope is scope]
        if not decls:
            continue
        lines.append(_SCOPE_KW[scope])
        for v in decls:
            lines.append(f"    {v.name} : {v.type.value};")
        lines.append("END_VAR")
    lines.extend(_stmts(program.body, 1))
    lines.append("END_PROGRAM")
    return "\n".join(lines) + "\n"


register_backend("st", emit_st)
