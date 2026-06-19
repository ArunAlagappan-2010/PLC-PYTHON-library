"""Sequential Function Chart (SFC) backend: IR -> chart text.

Reconstructs the chart from the `ir.Sfc` graph the SFC frontend attaches to the
program. If a program has no attached chart (e.g. it came from another
language), emits a comment — re-deriving a chart from arbitrary lowered code is
out of scope.
"""
from __future__ import annotations
from .. import ir
from ..registry import register_backend
from .st import _stmts, _expr

_SCOPE_KW = {ir.VarScope.INPUT: "VAR_INPUT", ir.VarScope.OUTPUT: "VAR_OUTPUT",
             ir.VarScope.LOCAL: "VAR"}


def emit_sfc(program: ir.Program) -> str:
    if program.sfc is None:
        return (f"PROGRAM {program.name}\n"
                f"(* no SFC chart available for this program *)\n"
                f"END_PROGRAM\n")

    lines = [f"PROGRAM {program.name}"]
    for scope in (ir.VarScope.INPUT, ir.VarScope.OUTPUT, ir.VarScope.LOCAL):
        # hide the synthetic _step state variable
        decls = [v for v in program.vars
                 if v.scope is scope and v.name != "_step"]
        if not decls:
            continue
        lines.append(_SCOPE_KW[scope])
        for v in decls:
            lines.append(f"    {v.name} : {v.type.value};")
        lines.append("END_VAR")

    for step in program.sfc.steps:
        kw = "INITIAL_STEP" if step.initial else "STEP"
        lines.append(f"{kw} {step.name}")
        if step.actions:
            lines.append("    ACTION")
            lines.extend(_stmts(step.actions, 2))
            lines.append("    END_ACTION")
        for cond, target in step.transitions:
            lines.append(f"    TRANSITION {_expr(cond)} TO {target}")
        lines.append("END_STEP")

    lines.append("END_PROGRAM")
    return "\n".join(lines) + "\n"


register_backend("sfc", emit_sfc)
