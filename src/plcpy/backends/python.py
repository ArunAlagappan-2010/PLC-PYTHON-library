from __future__ import annotations
from .. import ir
from ..registry import register_backend

_DEFAULTS = {ir.DataType.BOOL: "False", ir.DataType.INT: "0", ir.DataType.REAL: "0.0"}
_BINOP = {"and": "and", "or": "or", "=": "==", "<>": "!=",
          "<": "<", "<=": "<=", ">": ">", ">=": ">=",
          "+": "+", "-": "-", "*": "*", "/": "/"}


def _expr(e: ir.Expr) -> str:
    if isinstance(e, ir.Literal):
        if e.type is ir.DataType.BOOL:
            return "True" if e.value else "False"
        return repr(e.value)
    if isinstance(e, ir.VarRef):
        return f"self.{e.name}"
    if isinstance(e, ir.UnaryOp):
        if e.op == "not":
            return f"(not {_expr(e.operand)})"
        return f"(-{_expr(e.operand)})"
    if isinstance(e, ir.BinOp):
        return f"({_expr(e.left)} {_BINOP[e.op]} {_expr(e.right)})"
    raise TypeError(f"unhandled expr {e!r}")


def _stmts(stmts: list[ir.Stmt], indent: int) -> list[str]:
    pad = "    " * indent
    out: list[str] = []
    for s in stmts:
        if isinstance(s, ir.Assign):
            out.append(f"{pad}self.{s.target} = {_expr(s.value)}")
        elif isinstance(s, ir.If):
            out.append(f"{pad}if {_expr(s.cond)}:")
            out.extend(_stmts(s.then, indent + 1) or [f"{pad}    pass"])
            for cond, body in s.elifs:
                out.append(f"{pad}elif {_expr(cond)}:")
                out.extend(_stmts(body, indent + 1) or [f"{pad}    pass"])
            if s.orelse:
                out.append(f"{pad}else:")
                out.extend(_stmts(s.orelse, indent + 1) or [f"{pad}    pass"])
        else:
            raise TypeError(f"unhandled stmt {s!r}")
    return out


def emit_python(program: ir.Program) -> str:
    lines = [f"class {program.name}:", "    def __init__(self):"]
    if program.vars:
        for v in program.vars:
            lines.append(f"        self.{v.name} = {_DEFAULTS[v.type]}")
    else:
        lines.append("        pass")
    lines.append("")
    lines.append("    def scan(self):")
    body = _stmts(program.body, 2)
    lines.extend(body or ["        pass"])
    return "\n".join(lines) + "\n"


register_backend("python", emit_python)
