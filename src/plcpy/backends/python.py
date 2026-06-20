from __future__ import annotations
from .. import ir
from ..registry import register_backend

_DEFAULTS = {ir.DataType.BOOL: "False", ir.DataType.INT: "0", ir.DataType.REAL: "0.0",
             ir.DataType.TIME: "0"}
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
    if isinstance(e, ir.Member):
        return f"{_expr(e.base)}.{e.member}"
    if isinstance(e, ir.Index):
        return f"self.{e.base}[{_expr(e.index)}]"
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
        elif isinstance(s, ir.While):
            out.append(f"{pad}while {_expr(s.cond)}:")
            out.extend(_stmts(s.body, indent + 1) or [f"{pad}    pass"])
        elif isinstance(s, ir.For):
            # PLC FOR is inclusive of `end`; lower to a step-aware while loop
            # (correct for positive step, the common case).
            out.append(f"{pad}self.{s.var} = {_expr(s.start)}")
            out.append(f"{pad}while (self.{s.var} <= {_expr(s.end)}):")
            inner = _stmts(s.body, indent + 1)
            out.extend(inner)
            out.append(f"{pad}    self.{s.var} = (self.{s.var} + {_expr(s.step)})")
        elif isinstance(s, ir.Case):
            sel = _expr(s.selector)
            for k, (labels, body) in enumerate(s.branches):
                kw = "if" if k == 0 else "elif"
                cond = " or ".join(f"({sel} == {v})" for v in labels)
                out.append(f"{pad}{kw} {cond}:")
                out.extend(_stmts(body, indent + 1) or [f"{pad}    pass"])
            if s.default:
                out.append(f"{pad}else:")
                out.extend(_stmts(s.default, indent + 1) or [f"{pad}    pass"])
        elif isinstance(s, ir.FBCall):
            # function-block call, e.g. tmr(IN := x, PT := 5000)
            # timers are called positionally (IN, PT, dt) by the runtime classes
            in_e = s.args.get("IN")
            pt_e = s.args.get("PT")
            in_s = _expr(in_e) if in_e is not None else "False"
            pt_s = _expr(pt_e) if pt_e is not None else "0"
            out.append(f"{pad}self.{s.instance}({in_s}, {pt_s}, self._dt_ms)")
        elif isinstance(s, ir.IndexAssign):
            out.append(f"{pad}self.{s.base}[{_expr(s.index)}] = {_expr(s.value)}")
        else:
            raise TypeError(f"unhandled stmt {s!r}")
    return out


def emit_python(program: ir.Program) -> str:
    lines: list[str] = []
    if program.fbs:
        types = sorted({fb.fb_type for fb in program.fbs})
        lines.append(f"from plcpy.runtime import {', '.join(types)}")
        lines.append("")
    lines.append(f"class {program.name}:")
    lines.append("    def __init__(self):")
    has_init = bool(program.vars) or bool(program.fbs)
    if program.fbs:
        lines.append("        self._dt_ms = 100")
        for fb in program.fbs:
            lines.append(f"        self.{fb.name} = {fb.fb_type}()")
    for v in program.vars:
        if v.array_len is not None:
            # size to lo+len so absolute PLC indices (incl. non-zero lower bounds) work
            size = v.array_lo + v.array_len
            lines.append(f"        self.{v.name} = [{_DEFAULTS[v.type]}] * {size}")
        else:
            lines.append(f"        self.{v.name} = {_DEFAULTS[v.type]}")
    if not has_init:
        lines.append("        pass")
    lines.append("")
    lines.append("    def scan(self):")
    body = _stmts(program.body, 2)
    lines.extend(body or ["        pass"])
    return "\n".join(lines) + "\n"


register_backend("python", emit_python)
