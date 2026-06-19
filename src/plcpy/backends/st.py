from __future__ import annotations
from .. import ir
from ..registry import register_backend

_SCOPE_KW = {ir.VarScope.INPUT: "VAR_INPUT", ir.VarScope.OUTPUT: "VAR_OUTPUT",
             ir.VarScope.LOCAL: "VAR"}


# operator precedence (higher binds tighter), used to insert only the
# parentheses needed to preserve expression structure on round-trip
_PREC = {"or": 1, "and": 2,
         "=": 3, "<>": 3, "<": 3, "<=": 3, ">": 3, ">=": 3,
         "+": 4, "-": 4, "*": 5, "/": 5}


def _render(e: ir.Expr, threshold: int) -> str:
    if isinstance(e, ir.Literal):
        if e.type is ir.DataType.BOOL:
            return "TRUE" if e.value else "FALSE"
        return str(e.value)
    if isinstance(e, ir.VarRef):
        return e.name
    if isinstance(e, ir.UnaryOp):
        op = "NOT " if e.op == "not" else "-"
        return f"{op}{_render(e.operand, 6)}"
    if isinstance(e, ir.BinOp):
        p = _PREC[e.op]
        op = {"and": "AND", "or": "OR"}.get(e.op, e.op)
        s = f"{_render(e.left, p)} {op} {_render(e.right, p + 1)}"
        return f"({s})" if p < threshold else s
    raise TypeError(f"unhandled expr {e!r}")


def _expr(e: ir.Expr) -> str:
    return _render(e, 0)


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
        elif isinstance(s, ir.While):
            out.append(f"{pad}WHILE {_expr(s.cond)} DO")
            out.extend(_stmts(s.body, indent + 1))
            out.append(f"{pad}END_WHILE;")
        elif isinstance(s, ir.For):
            by = ""
            if not (isinstance(s.step, ir.Literal) and s.step.value == 1):
                by = f" BY {_expr(s.step)}"
            out.append(f"{pad}FOR {s.var} := {_expr(s.start)} TO {_expr(s.end)}{by} DO")
            out.extend(_stmts(s.body, indent + 1))
            out.append(f"{pad}END_FOR;")
        elif isinstance(s, ir.Case):
            out.append(f"{pad}CASE {_expr(s.selector)} OF")
            for labels, body in s.branches:
                out.append(f"{pad}{','.join(str(v) for v in labels)}:")
                out.extend(_stmts(body, indent + 1))
            if s.default:
                out.append(f"{pad}ELSE")
                out.extend(_stmts(s.default, indent + 1))
            out.append(f"{pad}END_CASE;")
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
