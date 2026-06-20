# SFC Parallel (Simultaneous) Branches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend SFC support from a single active step to **simultaneous (parallel) branches** — a divergence that activates several branches at once, and a convergence that waits for all branches to finish — so charts like "run pump AND open valve in parallel, then proceed when both done" parse, execute, and round-trip.

**Architecture:** Replace the single `_step` integer with a **set of active steps** modelled as one boolean `_active_<step>` variable per step. Actions run for each active step; transitions deactivate their source step(s) and activate their target(s). A *simultaneous divergence* is one transition with multiple targets (all activated together); a *simultaneous convergence* is one transition guarded by "all source steps active" that activates a single target. The chart graph (`ir.Sfc`) gains branch metadata for round-trip; the executable lowering becomes per-step boolean state updates instead of a single `CASE`.

**Tech Stack:** Python 3.11+, stdlib only. Extends `src/plcpy/frontends/sfc.py`, `src/plcpy/backends/sfc.py`, and `src/plcpy/ir.py`.

## Global Constraints

- Package `plcpy`, `src/` layout. IR is the only frontend/backend contract.
- Source errors are `Diagnostic` objects, never exceptions.
- The lowered `body` must execute in the existing scan-cycle runtime (no runtime changes).
- Preserve backward compatibility: existing single-active-step SFC tests (`tests/test_fbd_sfc.py`) must keep passing. The new boolean-set lowering must reproduce identical behaviour for linear charts.
- Run the full suite after each task.

---

### Task 1: Re-model SFC transitions to support multiple targets and sources

**Files:**
- Modify: `src/plcpy/ir.py` (`SfcStep.transitions`, add `SfcTransition`)
- Modify: `src/plcpy/frontends/sfc.py` (parse multi-target / multi-source transitions)
- Test: `tests/test_sfc_parallel_parse.py`

**Interfaces:**
- Consumes: existing `ir.SfcStep(name, initial, actions, transitions)` where `transitions: list[tuple[Expr, str]]`.
- Produces:
  - `@dataclass class SfcTransition: cond: Expr; sources: list[str]; targets: list[str]`.
  - `ir.Sfc` gains `transitions: list[SfcTransition]` (chart-level, replacing per-step tuples for the parallel model). Keep `SfcStep.transitions` for backward compat but populate `Sfc.transitions` as the authoritative list.
  - New text syntax: `TRANSITION <cond> FROM s1, s2 TO t1, t2` (sources optional — default `[current step]`; targets comma-separated).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sfc_parallel_parse.py
from plcpy.frontends import sfc as sfc_fe
from plcpy import ir

SRC = """PROGRAM Par
VAR_INPUT
    go : BOOL;
    aDone : BOOL;
    bDone : BOOL;
END_VAR
VAR_OUTPUT
    done : BOOL;
END_VAR
INITIAL_STEP Idle
    TRANSITION go TO TaskA, TaskB
END_STEP
STEP TaskA
    TRANSITION aDone TO JoinA
END_STEP
STEP TaskB
    TRANSITION bDone TO JoinB
END_STEP
STEP JoinA
END_STEP
STEP JoinB
    TRANSITION TRUE FROM JoinA, JoinB TO Finish
END_STEP
STEP Finish
    ACTION
        done := TRUE;
    END_ACTION
END_STEP
END_PROGRAM
"""

def test_divergence_has_two_targets():
    prog = sfc_fe.parse_sfc(SRC).program
    div = next(t for t in prog.sfc.transitions if "Idle" in t.sources)
    assert set(div.targets) == {"TaskA", "TaskB"}

def test_convergence_has_two_sources():
    prog = sfc_fe.parse_sfc(SRC).program
    conv = next(t for t in prog.sfc.transitions if "Finish" in t.targets)
    assert set(conv.sources) == {"JoinA", "JoinB"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sfc_parallel_parse.py -v`
Expected: FAIL

- [ ] **Step 3: Add the IR record**

In `src/plcpy/ir.py`:

```python
@dataclass
class SfcTransition:
    cond: "Expr"
    sources: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
```

Add to `Sfc`: `transitions: list[SfcTransition] = field(default_factory=list)`.

- [ ] **Step 4: Parse FROM/TO with comma lists**

In `src/plcpy/frontends/sfc.py`, replace the `TRANSITION` parsing inside the step loop. Current code finds ` TO ` and takes a single target. Replace with:

```python
                elif lk == "TRANSITION":
                    rest = line[len("TRANSITION"):].strip()
                    up = rest.upper()
                    to_pos = up.rfind(" TO ")
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
                        # keep legacy per-step list for single-target charts
                        if len(targets) == 1 and sources == [step.name]:
                            step.transitions.append((cond, targets[0]))
```

Add `trans: list[ir.SfcTransition] = []` before the main loop and, after building `steps`, attach it: `sfc = ir.Sfc(steps); sfc.transitions = trans`.

- [ ] **Step 5: Run tests, full suite, commit**

```bash
python -m pytest tests/test_sfc_parallel_parse.py -v
python -m pytest -q
git add src/plcpy/ir.py src/plcpy/frontends/sfc.py tests/test_sfc_parallel_parse.py
git commit -m "feat: model SFC transitions with multiple sources/targets"
```

---

### Task 2: Boolean-set lowering (multiple active steps)

**Files:**
- Modify: `src/plcpy/frontends/sfc.py` (replace `_lower` with a per-step boolean model)
- Test: `tests/test_sfc_parallel_exec.py`

**Interfaces:**
- Consumes: `ir.Sfc` with `SfcTransition` list, `ir.Assign`, `ir.If`, `ir.Case`, `ir.BinOp`, `ir.VarRef`, `ir.Literal`.
- Produces: a new `_lower(sfc) -> tuple[list[VarDecl], list[Stmt]]` that:
  - declares one BOOL local `_active_<step>` per step (initial step defaults True via an init assign at the top of the body — but locals default False, so emit an explicit "first scan" init using a `_started` flag).
  - emits **actions:** for each step, `IF _active_<step> THEN <actions> END_IF`.
  - emits **transitions:** for each `SfcTransition`, `IF (cond AND all sources active) THEN <deactivate sources; activate targets> END_IF`.
- Replaces the old single-`_step` `CASE` lowering. Single-active charts still work because a linear chart is just the degenerate case (one source, one target).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sfc_parallel_exec.py
import plcpy
from plcpy import runtime

SRC = open("tests/_sfc_parallel_fixture.st").read() if False else """PROGRAM Par
VAR_INPUT
    go : BOOL;
    aDone : BOOL;
    bDone : BOOL;
END_VAR
VAR_OUTPUT
    aRun : BOOL;
    bRun : BOOL;
    done : BOOL;
END_VAR
INITIAL_STEP Idle
    TRANSITION go TO TaskA, TaskB
END_STEP
STEP TaskA
    ACTION
        aRun := TRUE;
    END_ACTION
    TRANSITION aDone TO JoinA
END_STEP
STEP TaskB
    ACTION
        bRun := TRUE;
    END_ACTION
    TRANSITION bDone TO JoinB
END_STEP
STEP JoinA
    ACTION
        aRun := FALSE;
    END_ACTION
END_STEP
STEP JoinB
    ACTION
        bRun := FALSE;
    END_ACTION
    TRANSITION TRUE FROM JoinA, JoinB TO Finish
END_STEP
STEP Finish
    ACTION
        done := TRUE;
    END_ACTION
END_STEP
END_PROGRAM
"""

def test_parallel_branches_run_then_join():
    code = plcpy.convert(SRC, "sfc", "python").code
    Par = runtime.load_pou(code, "Par")
    inst = Par()
    seq = [
        {"go": True,  "aDone": False, "bDone": False},  # Idle -> TaskA & TaskB
        {"go": False, "aDone": False, "bDone": False},  # both running
        {"go": False, "aDone": True,  "bDone": False},  # A -> JoinA, B still running
        {"go": False, "aDone": False, "bDone": True},   # B -> JoinB; both joined -> Finish
        {"go": False, "aDone": False, "bDone": False},  # Finish action
    ]
    trace = runtime.run_scans(inst, seq, ["aRun", "bRun", "done"])
    # By the last scan both tasks are done and Finish has fired
    assert trace[-1].outputs["done"] is True
    # Both branches were active simultaneously in scan index 1
    assert trace[1].outputs["aRun"] is True and trace[1].outputs["bRun"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sfc_parallel_exec.py -v`
Expected: FAIL (old `_step` lowering can't hold two active steps)

- [ ] **Step 3: Rewrite `_lower`**

In `src/plcpy/frontends/sfc.py`, replace `_lower`:

```python
def _active(name): return f"_active_{name}"

def _lower(sfc):
    decls = [ir.VarDecl("_started", ir.DataType.BOOL, ir.VarScope.LOCAL)]
    for s in sfc.steps:
        decls.append(ir.VarDecl(_active(s.name), ir.DataType.BOOL, ir.VarScope.LOCAL))

    body = []
    # first-scan init: activate initial steps once
    init_assigns = [ir.Assign(_active(s.name), ir.Literal(True, ir.DataType.BOOL))
                    for s in sfc.steps if s.initial]
    init_assigns.append(ir.Assign("_started", ir.Literal(True, ir.DataType.BOOL)))
    body.append(ir.If(ir.UnaryOp("not", ir.VarRef("_started")), init_assigns, [], []))

    # actions for each active step
    for s in sfc.steps:
        if s.actions:
            body.append(ir.If(ir.VarRef(_active(s.name)), list(s.actions), [], []))

    # transitions: fire when cond AND all sources active
    for t in sfc.transitions:
        guard = t.cond
        for src in t.sources:
            guard = ir.BinOp("and", guard, ir.VarRef(_active(src)))
        effects = [ir.Assign(_active(src), ir.Literal(False, ir.DataType.BOOL))
                   for src in t.sources]
        effects += [ir.Assign(_active(tgt), ir.Literal(True, ir.DataType.BOOL))
                    for tgt in t.targets]
        body.append(ir.If(guard, effects, [], []))
    return decls, body
```

Update `parse_sfc` to use the new return shape:

```python
    sfc = ir.Sfc(steps); sfc.transitions = trans
    decls, body = _lower(sfc)
    vars_.extend(decls)
    program = ir.Program(name, vars_, body, sfc=sfc)
```

(Remove the old single `_step` VarDecl append.)

- [ ] **Step 4: Run tests, full suite, commit**

```bash
python -m pytest tests/test_sfc_parallel_exec.py -v
python -m pytest -q   # existing single-step SFC tests must still pass
git add src/plcpy/frontends/sfc.py tests/test_sfc_parallel_exec.py
git commit -m "feat: SFC boolean-set lowering for parallel branches"
```

> If existing `tests/test_fbd_sfc.py` SFC tests fail because they assert `CASE _step OF` in the lowered ST, update those assertions to the new boolean form (`IF _active_Idle THEN` etc.) — the *behaviour* (output traces) must be unchanged; only the lowered shape differs. Make that assertion update part of this commit.

---

### Task 3: Round-trip parallel charts through the SFC backend

**Files:**
- Modify: `src/plcpy/backends/sfc.py` (emit FROM/TO transitions from `Sfc.transitions`)
- Test: `tests/test_sfc_parallel_roundtrip.py`

**Interfaces:**
- Consumes: `program.sfc.transitions: list[SfcTransition]`, `program.sfc.steps`.
- Produces: `emit_sfc` renders multi-target divergences (`TRANSITION cond TO a, b`) and multi-source convergences (`TRANSITION cond FROM x, y TO z`), so `sfc → sfc` reproduces the parallel structure.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sfc_parallel_roundtrip.py
import plcpy
from tests.test_sfc_parallel_exec import SRC   # reuse the fixture

def test_parallel_chart_roundtrips():
    out = plcpy.convert(SRC, "sfc", "sfc").code
    assert "TO TaskA, TaskB" in out
    assert "FROM JoinA, JoinB TO Finish" in out
    assert "_active_" not in out   # synthetic state must not leak
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sfc_parallel_roundtrip.py -v`
Expected: FAIL (backend emits per-step single-target transitions only)

- [ ] **Step 3: Emit from the transition list**

In `src/plcpy/backends/sfc.py`, change the per-step transition emission to use `program.sfc.transitions`. For each step, emit the transitions whose `sources == [step.name]` (single-source) inline under that step; emit multi-source convergences under the step that is the *last* listed source. Concretely, after emitting a step's actions:

```python
        for t in program.sfc.transitions:
            # emit a transition under the step that "owns" it: single-source -> its source;
            # multi-source -> the last source in the list
            owner = t.sources[-1] if t.sources else None
            if owner != step.name:
                continue
            tos = ", ".join(t.targets)
            if len(t.sources) > 1:
                froms = ", ".join(t.sources)
                lines.append(f"    TRANSITION {_expr(t.cond)} FROM {froms} TO {tos}")
            else:
                lines.append(f"    TRANSITION {_expr(t.cond)} TO {tos}")
```

Filter the synthetic `_active_*`/`_started` locals out of the emitted VAR sections (extend the existing `_step` filter to also skip names starting with `_active_` or equal to `_started`).

- [ ] **Step 4: Run tests, full suite, commit**

```bash
python -m pytest tests/test_sfc_parallel_roundtrip.py -v
python -m pytest -q
git add src/plcpy/backends/sfc.py tests/test_sfc_parallel_roundtrip.py
git commit -m "feat: round-trip SFC parallel divergence/convergence"
```

---

## Self-Review

- **Spec coverage:** multi-target divergence + multi-source convergence parse (Task 1), execute via boolean-set lowering (Task 2), round-trip (Task 3).
- **Backward compatibility:** Task 2 Step 4 explicitly flags updating the old `CASE _step` assertions; behaviour (output traces) is preserved, which the existing tests' trace assertions verify.
- **Type consistency:** `SfcTransition(cond, sources, targets)` used identically across frontend, lowering, and backend. `_active_<step>`/`_started` naming convention is consistent and filtered uniformly in the backend.
- **Placeholders:** none — every step has concrete code.
- **Limitation documented:** this supports simultaneous (parallel) branches and selection by guard; it does not model action qualifiers (P/N/S/R) or step timers — note those as future work in the README roadmap.
