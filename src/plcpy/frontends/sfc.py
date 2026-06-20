"""Sequential Function Chart (SFC) frontend: chart text -> IR.

Produces a `Program` that carries BOTH:
  * an `ir.Sfc` graph (steps, actions, transitions) for faithful SFC round-trip
  * a lowered executable `body` (a `_step` state variable plus two CASE blocks:
    run the active step's actions, then evaluate its transitions) so the chart
    converts to Python/ST/etc. and runs in the scan-cycle runtime.

Scan semantics: the active step's actions run, then its transitions are checked
(first true wins) and the active step advances. Single active step; parallel
branches are future work.

Text form:

    INITIAL_STEP Idle
      ACTION
        active := FALSE;
      END_ACTION
      TRANSITION go TO Running
    END_STEP
    STEP Running
      ACTION
        active := TRUE;
      END_ACTION
      TRANSITION halt TO Idle
    END_STEP
"""
from __future__ import annotations
from .. import ir
from ..registry import ParseResult, register_frontend
from ..diagnostics import Diagnostic, Severity
from ._common import SCOPE, parse_var_section
from .st import parse_st

STEP_VAR = "_step"


def _parse_stmts(src_body: str) -> list[ir.Stmt]:
    res = parse_st(f"PROGRAM _\n{src_body}\nEND_PROGRAM\n")
    return res.program.body if res.program else []


def _parse_expr(text: str) -> ir.Expr | None:
    res = parse_st(f"PROGRAM _\n    __e := {text};\nEND_PROGRAM\n")
    if res.program and res.program.body and isinstance(res.program.body[0], ir.Assign):
        return res.program.body[0].value
    return None


def _active(name: str) -> str:
    return f"_active_{name}"


def _lower(sfc: ir.Sfc) -> tuple[list[ir.VarDecl], list[ir.Stmt]]:
    """Build the executable body using one boolean per step (supports multiple
    simultaneously-active steps for parallel branches)."""
    decls = [ir.VarDecl("_started", ir.DataType.BOOL, ir.VarScope.LOCAL)]
    for s in sfc.steps:
        decls.append(ir.VarDecl(_active(s.name), ir.DataType.BOOL, ir.VarScope.LOCAL))

    body: list[ir.Stmt] = []
    # first-scan init: activate initial steps once
    init = [ir.Assign(_active(s.name), ir.Literal(True, ir.DataType.BOOL))
            for s in sfc.steps if s.initial]
    init.append(ir.Assign("_started", ir.Literal(True, ir.DataType.BOOL)))
    body.append(ir.If(ir.UnaryOp("not", ir.VarRef("_started")), init, [], []))

    # actions for each active step
    for s in sfc.steps:
        if s.actions:
            body.append(ir.If(ir.VarRef(_active(s.name)), list(s.actions), [], []))

    # transitions: fire when cond AND all sources active
    names = {s.name for s in sfc.steps}
    for t in sfc.transitions:
        guard: ir.Expr = t.cond
        for src in t.sources:
            guard = ir.BinOp("and", guard, ir.VarRef(_active(src)))
        effects = [ir.Assign(_active(src), ir.Literal(False, ir.DataType.BOOL))
                   for src in t.sources if src in names]
        effects += [ir.Assign(_active(tgt), ir.Literal(True, ir.DataType.BOOL))
                    for tgt in t.targets if tgt in names]
        if effects:
            body.append(ir.If(guard, effects, [], []))
    return decls, body


def parse_sfc(text: str) -> ParseResult:
    diagnostics: list[Diagnostic] = []
    vars_: list[ir.VarDecl] = []
    steps: list[ir.SfcStep] = []
    trans: list[ir.SfcTransition] = []
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
        elif kw in ("STEP", "INITIAL_STEP"):
            step = ir.SfcStep(head[1], initial=(kw == "INITIAL_STEP"))
            while idx < len(lines):
                line = lines[idx].strip()
                idx += 1
                lk = line.split()[0].upper() if line else ""
                if lk == "END_STEP":
                    break
                if lk == "ACTION":
                    act_src = ""
                    while idx < len(lines):
                        al = lines[idx]
                        idx += 1
                        if al.strip().upper() == "END_ACTION":
                            break
                        act_src += al + "\n"
                    step.actions = _parse_stmts(act_src)
                elif lk == "TRANSITION":
                    # TRANSITION <cond...> [FROM s1, s2] TO t1, t2
                    rest = line[len("TRANSITION"):].strip()
                    to_pos = rest.upper().rfind(" TO ")
                    if to_pos < 0:
                        diagnostics.append(Diagnostic("transition missing TO",
                                                      Severity.ERROR, line=idx, code="SFC"))
                        continue
                    targets = [t.strip() for t in rest[to_pos + 4:].split(",")]
                    left = rest[:to_pos]
                    from_pos = left.upper().rfind(" FROM ")
                    if from_pos >= 0:
                        cond_txt = left[:from_pos].strip()
                        sources = [s.strip() for s in left[from_pos + 6:].split(",")]
                    else:
                        cond_txt = left.strip()
                        sources = [step.name]
                    cond = _parse_expr(cond_txt)
                    if cond is not None:
                        trans.append(ir.SfcTransition(cond, sources, targets))
                        if len(targets) == 1 and sources == [step.name]:
                            step.transitions.append((cond, targets[0]))
            steps.append(step)
        else:
            diagnostics.append(Diagnostic(f"unexpected SFC line {raw!r}",
                                          Severity.UNSUPPORTED, line=idx, code="SFC"))

    steps.sort(key=lambda s: 0 if s.initial else 1)
    sfc = ir.Sfc(steps, trans)
    decls, body = _lower(sfc)
    vars_.extend(decls)
    program = ir.Program(name, vars_, body, sfc=sfc)
    return ParseResult(program, diagnostics)


register_frontend("sfc", parse_sfc)
