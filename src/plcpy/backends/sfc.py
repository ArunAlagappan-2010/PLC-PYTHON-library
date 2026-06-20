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

    def _synthetic(n):
        return n == "_started" or n.startswith("_active_")

    lines = [f"PROGRAM {program.name}"]
    for scope in (ir.VarScope.INPUT, ir.VarScope.OUTPUT, ir.VarScope.LOCAL):
        # hide the synthetic state variables
        decls = [v for v in program.vars
                 if v.scope is scope and not _synthetic(v.name)]
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
        for t in program.sfc.transitions:
            owner = t.sources[-1] if t.sources else None
            if owner != step.name:
                continue
            tos = ", ".join(t.targets)
            if len(t.sources) > 1:
                froms = ", ".join(t.sources)
                lines.append(f"    TRANSITION {_expr(t.cond)} FROM {froms} TO {tos}")
            else:
                lines.append(f"    TRANSITION {_expr(t.cond)} TO {tos}")
        lines.append("END_STEP")

    lines.append("END_PROGRAM")
    return "\n".join(lines) + "\n"


register_backend("sfc", emit_sfc)
