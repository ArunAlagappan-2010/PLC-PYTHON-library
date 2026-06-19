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


def _lower(sfc: ir.Sfc) -> list[ir.Stmt]:
    """Build the executable body from the chart."""
    index = {s.name: i for i, s in enumerate(sfc.steps)}

    action_branches: list[tuple[list[int], list[ir.Stmt]]] = []
    trans_branches: list[tuple[list[int], list[ir.Stmt]]] = []
    for i, step in enumerate(sfc.steps):
        if step.actions:
            action_branches.append(([i], step.actions))
        if step.transitions:
            conds = [(c, index[t]) for c, t in step.transitions if t in index]
            if conds:
                cond0, tgt0 = conds[0]
                elifs = [(c, [ir.Assign(STEP_VAR, ir.Literal(t, ir.DataType.INT))])
                         for c, t in conds[1:]]
                ifstmt = ir.If(cond0,
                               [ir.Assign(STEP_VAR, ir.Literal(tgt0, ir.DataType.INT))],
                               elifs, [])
                trans_branches.append(([i], [ifstmt]))

    body: list[ir.Stmt] = []
    if action_branches:
        body.append(ir.Case(ir.VarRef(STEP_VAR), action_branches, []))
    if trans_branches:
        body.append(ir.Case(ir.VarRef(STEP_VAR), trans_branches, []))
    return body


def parse_sfc(text: str) -> ParseResult:
    diagnostics: list[Diagnostic] = []
    vars_: list[ir.VarDecl] = []
    steps: list[ir.SfcStep] = []
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
                    # TRANSITION <cond...> TO <target>
                    rest = line[len("TRANSITION"):].strip()
                    upper = rest.upper()
                    pos = upper.rfind(" TO ")
                    if pos < 0:
                        diagnostics.append(Diagnostic("transition missing TO",
                                                      Severity.ERROR, line=idx, code="SFC"))
                        continue
                    cond_txt = rest[:pos].strip()
                    target = rest[pos + 4:].strip()
                    cond = _parse_expr(cond_txt)
                    if cond is not None:
                        step.transitions.append((cond, target))
            steps.append(step)
        else:
            diagnostics.append(Diagnostic(f"unexpected SFC line {raw!r}",
                                          Severity.UNSUPPORTED, line=idx, code="SFC"))

    # order steps so the initial step is index 0 (so the _step local, which
    # defaults to 0, starts in the initial step)
    steps.sort(key=lambda s: 0 if s.initial else 1)
    sfc = ir.Sfc(steps)
    vars_.append(ir.VarDecl(STEP_VAR, ir.DataType.INT, ir.VarScope.LOCAL))
    body = _lower(sfc)
    program = ir.Program(name, vars_, body, sfc=sfc)
    return ParseResult(program, diagnostics)


register_frontend("sfc", parse_sfc)
