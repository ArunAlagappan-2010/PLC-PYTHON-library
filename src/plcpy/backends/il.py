"""Instruction List (IL) backend: IR -> IL text.

Linearises expression trees into accumulator instructions. The natural target
is a left-deep expression with atomic right operands (exactly what the IL
frontend produces), so IL->IR->IL round-trips. Constructs that cannot be
expressed in linear IL (nested right operands, IF/WHILE control flow) emit an
`(* unsupported ... *)` comment rather than silently dropping.
"""
from __future__ import annotations
import itertools
from .. import ir
from ..registry import register_backend

_SCOPE_KW = {ir.VarScope.INPUT: "VAR_INPUT", ir.VarScope.OUTPUT: "VAR_OUTPUT",
             ir.VarScope.LOCAL: "VAR"}
_IL_OP = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "and": "AND", "or": "OR",
          ">": "GT", ">=": "GE", "<": "LT", "<=": "LE", "=": "EQ", "<>": "NE"}


def _atomic(e: ir.Expr) -> bool:
    return isinstance(e, (ir.Literal, ir.VarRef))


def _operand_str(e: ir.Expr) -> str:
    if isinstance(e, ir.Literal):
        if e.type is ir.DataType.BOOL:
            return "TRUE" if e.value else "FALSE"
        return str(e.value)
    if isinstance(e, ir.VarRef):
        return e.name
    raise TypeError(f"non-atomic operand {e!r}")


def _emit_expr(e: ir.Expr, indent: str) -> list[str] | None:
    if _atomic(e):
        return [f"{indent}LD {_operand_str(e)}"]
    if isinstance(e, ir.UnaryOp):
        if e.op == "not":
            inner = _emit_expr(e.operand, indent)
            return None if inner is None else inner + [f"{indent}NOT"]
        if e.op == "-" and _atomic(e.operand):
            return [f"{indent}LD 0", f"{indent}SUB {_operand_str(e.operand)}"]
        return None
    if isinstance(e, ir.BinOp) and e.op in _IL_OP and _atomic(e.right):
        left = _emit_expr(e.left, indent)
        if left is None:
            return None
        return left + [f"{indent}{_IL_OP[e.op]} {_operand_str(e.right)}"]
    return None


def _emit_stmt(s: ir.Stmt, indent: str, labels) -> list[str]:
    if isinstance(s, ir.Assign):
        expr_il = _emit_expr(s.value, indent)
        if expr_il is None:
            return [f"{indent}(* unsupported expression for {s.target} *)"]
        return expr_il + [f"{indent}ST {s.target}"]
    if isinstance(s, ir.If):
        if s.elifs or s.orelse:
            return [f"{indent}(* IL export supports IF-THEN only; ELSIF/ELSE dropped *)"]
        cond_il = _emit_expr(s.cond, indent)
        if cond_il is None:
            return [f"{indent}(* unsupported IF condition *)"]
        end = f"L{next(labels)}"
        out = list(cond_il)
        out.append(f"{indent}JMPCN {end}")
        for inner in s.then:
            out += _emit_stmt(inner, indent, labels)
        out.append(f"{end}:")
        return out
    if isinstance(s, ir.While):
        cond_il = _emit_expr(s.cond, indent)
        if cond_il is None:
            return [f"{indent}(* unsupported WHILE condition *)"]
        guard = f"L{next(labels)}"
        end = f"L{next(labels)}"
        out = [f"{guard}:"]
        out += cond_il
        out.append(f"{indent}JMPCN {end}")
        for inner in s.body:
            out += _emit_stmt(inner, indent, labels)
        out.append(f"{indent}JMP {guard}")
        out.append(f"{end}:")
        return out
    if isinstance(s, ir.For):
        return [f"{indent}(* unsupported in IL: FOR statement *)"]
    if isinstance(s, ir.Case):
        return [f"{indent}(* unsupported in IL: CASE statement *)"]
    return [f"{indent}(* unsupported statement *)"]


def emit_il(program: ir.Program) -> str:
    labels = itertools.count()
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
        lines.extend(_emit_stmt(s, "    ", labels))
    lines.append("END_PROGRAM")
    return "\n".join(lines) + "\n"


register_backend("il", emit_il)
