# IL Jumps & Labels (Control Flow) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Instruction List (IL) language real control flow — `JMP`/`JMPC`/`JMPCN` to labels — in both directions: lower structured IR (`If`/`While`) into IL jumps on export, and **reconstruct structured control flow** from IL labels+jumps on import, so IL programs with control flow convert to ST/Python and execute.

**Architecture:** Two halves. (1) **Lowering (IR → IL):** emit assignments as accumulator ops (already done) and emit `IF`/`WHILE` as labelled jump skeletons (`JMPC`/`JMP` + `label:`). (2) **Raising (IL → IR):** parse instructions + labels into a linear list, build a control-flow graph, and recognise the two structured patterns this plan supports — `if-then` (forward `JMPCN` skipping a block) and `while` (back-edge `JMP` to a guard label). Patterns that don't match a known shape stay as a flat fallback (a sequence the runtime can still execute via a small label/goto interpreter), so nothing is lost.

**Tech Stack:** Python 3.11+, stdlib only. Extends `src/plcpy/frontends/il.py` and `src/plcpy/backends/il.py`.

## Global Constraints

- Package `plcpy`, `src/` layout. IR is the only frontend/backend contract.
- Source errors are `Diagnostic` objects, never exceptions.
- The IL *frontend* must keep producing structured IR (`If`/`While`) when it recognises the patterns, so downstream ST/Python emission is unchanged.
- Scope: support **single-condition `IF … END_IF`** (no ELSIF/ELSE in IL — those raise a diagnostic) and **`WHILE … END_WHILE`** lowering/raising. This is the realistic, testable subset; document the rest as future work.
- Run the full suite after each task.

---

### Task 1: Define the labelled-IL instruction model and a flat fallback runner

**Files:**
- Create: `src/plcpy/frontends/_il_cfg.py` (instruction model + pattern matcher)
- Modify: `src/plcpy/ir.py` (add `Label` and `Jump` fallback statements)
- Modify: `src/plcpy/backends/python.py` (emit a tiny label/goto interpreter for fallback)
- Test: `tests/test_il_cfg.py`

**Interfaces:**
- Consumes: `ir.Assign`, `ir.Expr`.
- Produces:
  - `@dataclass class Label: name: str` (an IR statement marking a jump target).
  - `@dataclass class Jump: target: str; cond: Expr | None; negate: bool` (unconditional if `cond is None`; `JMPC` if `cond` set and `negate=False`; `JMPCN` if `negate=True`).
  - Both added to `ir.Stmt`. They are the *fallback* representation when structured raising fails — the Python backend executes them with a label-indexed loop.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_il_cfg.py
from plcpy import ir, runtime
from plcpy.backends import python as py_be

def test_label_goto_fallback_executes():
    # if acc(start) skip setting y; else y := 1   (modelled directly in IR)
    prog = ir.Program(
        name="J",
        vars=[ir.VarDecl("start", ir.DataType.BOOL, ir.VarScope.INPUT),
              ir.VarDecl("y", ir.DataType.INT, ir.VarScope.OUTPUT)],
        body=[
            ir.Jump("done", ir.VarRef("start"), False),  # JMPC done
            ir.Assign("y", ir.Literal(1, ir.DataType.INT)),
            ir.Label("done"),
        ],
    )
    code = py_be.emit_python(prog)
    P = runtime.load_pou(code, "J")
    a = P(); a.start = True; a.scan(); assert a.y == 0      # jumped over
    b = P(); b.start = False; b.scan(); assert b.y == 1     # fell through
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_il_cfg.py -v`
Expected: FAIL (`ir.Label`/`ir.Jump` don't exist)

- [ ] **Step 3: Add IR statements**

In `src/plcpy/ir.py`:

```python
@dataclass
class Label:
    name: str

@dataclass
class Jump:
    target: str
    cond: "Expr | None" = None
    negate: bool = False
```

Add both to the `Stmt` union.

- [ ] **Step 4: Python backend — label/goto interpreter**

In `src/plcpy/backends/python.py`, detect whether the body contains any `Label`/`Jump`. If so, emit `scan()` as a program-counter loop instead of straight-line code:

```python
def _emit_goto_scan(stmts, indent):
    # Build a flat op list: each entry is ("label", name) | ("jump", ...) | ("stmt", lines)
    pad = "    " * indent
    out = [f"{pad}_labels = {{}}"]
    # Assign integer indices to labels; compile body into a list of callables-as-strings
    flat = []
    for s in stmts:
        flat.append(s)
    # emit a dispatch loop
    out.append(f"{pad}_ops = []")
    # The simplest correct emission: render to a nested function table.
    # See Step 5 for the concrete generator.
    return out
```

The concrete generator (Step 5) replaces this placeholder.

- [ ] **Step 5: Concrete goto emitter**

Replace `_emit_goto_scan` with a program-counter machine. Emit the body as a Python list of (kind, payload) tuples and a `while pc < len(ops)` loop:

```python
def _emit_goto_scan(stmts, indent, expr_fn):
    pad = "    " * indent
    label_idx = {}
    seq = []
    for s in stmts:
        if isinstance(s, ir.Label):
            label_idx[s.name] = len(seq)
        else:
            seq.append(s)
    lines = [f"{pad}_pc = 0"]
    lines.append(f"{pad}_LBL = {label_idx!r}")
    lines.append(f"{pad}while _pc < {len(seq)}:")
    ip = pad + "    "
    for i, s in enumerate(seq):
        lines.append(f"{ip}if _pc == {i}:")
        body_pad = ip + "    "
        if isinstance(s, ir.Assign):
            lines.append(f"{body_pad}self.{s.target} = {expr_fn(s.value)}")
            lines.append(f"{body_pad}_pc += 1")
        elif isinstance(s, ir.Jump):
            if s.cond is None:
                lines.append(f"{body_pad}_pc = _LBL[{s.target!r}]")
            else:
                test = expr_fn(s.cond)
                if s.negate:
                    test = f"(not {test})"
                lines.append(f"{body_pad}_pc = _LBL[{s.target!r}] if {test} else _pc + 1")
        else:
            lines.append(f"{body_pad}_pc += 1  # unsupported in goto mode")
        lines.append(f"{ip}    continue")
    return lines
```

Note: `label_idx` must account for labels at the end (a `done:` after the last real op maps to index `len(seq)`, which terminates the loop — correct). Wire `emit_python` to call `_emit_goto_scan(program.body, 2, _expr)` for the `scan()` body when `any(isinstance(s, (ir.Label, ir.Jump)) for s in program.body)`, else use the existing `_stmts` path.

- [ ] **Step 6: Run the test, full suite, commit**

```bash
python -m pytest tests/test_il_cfg.py -v
python -m pytest -q
git add src/plcpy tests/test_il_cfg.py
git commit -m "feat: add Label/Jump IR + goto interpreter for IL fallback"
```

---

### Task 2: IL frontend — parse labels and jumps into the fallback IR

**Files:**
- Modify: `src/plcpy/frontends/il.py` (recognise `label:` lines and `JMP`/`JMPC`/`JMPCN`)
- Test: `tests/test_il_jumps_frontend.py`

**Interfaces:**
- Consumes: the IL line loop in `parse_il`, `ir.Label`, `ir.Jump`.
- Produces: `parse_il` emits `ir.Label` for `name:` lines and `ir.Jump` for jump instructions, using the current accumulator (`cr`) as the condition for `JMPC`/`JMPCN`. The result is executable via Task 1's interpreter even before structured raising (Task 3).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_il_jumps_frontend.py
import plcpy
from plcpy import runtime

IL = """PROGRAM J
VAR_INPUT
    start : BOOL;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    LD start
    JMPC done
    LD 1
    ST y
done:
END_PROGRAM
"""

def test_il_jump_executes_via_fallback():
    code = plcpy.convert(IL, "il", "python").code
    P = runtime.load_pou(code, "J")
    a = P(); a.start = True; a.scan(); assert a.y == 0
    b = P(); b.start = False; b.scan(); assert b.y == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_il_jumps_frontend.py -v`
Expected: FAIL (`JMPC` currently produces an `unsupported IL instruction` diagnostic)

- [ ] **Step 3: Handle labels and jumps in `parse_il`**

In `src/plcpy/frontends/il.py`, inside the instruction loop, before the `op == "LD"` chain:

```python
        # label line:  name:
        if raw.endswith(":") and len(head) == 1 and raw[:-1].isidentifier():
            body.append(ir.Label(raw[:-1]))
            continue
```

Add jump handling alongside the other ops:

```python
        elif op == "JMP":
            body.append(ir.Jump(arg, None, False))
        elif op == "JMPC":
            body.append(ir.Jump(arg, cr, False))
        elif op == "JMPCN":
            body.append(ir.Jump(arg, cr, True))
```

(`cr` is the current accumulator expression — already tracked.)

- [ ] **Step 4: Run the test, full suite, commit**

```bash
python -m pytest tests/test_il_jumps_frontend.py -v
python -m pytest -q
git add src/plcpy/frontends/il.py tests/test_il_jumps_frontend.py
git commit -m "feat: parse IL labels and jumps into Label/Jump IR"
```

---

### Task 3: Raise IL jump patterns to structured IR (if / while)

**Files:**
- Modify: `src/plcpy/frontends/_il_cfg.py` (pattern recogniser)
- Modify: `src/plcpy/frontends/il.py` (call the recogniser before returning)
- Test: `tests/test_il_raise.py`

**Interfaces:**
- Consumes: a `list[ir.Stmt]` containing `Assign`/`Label`/`Jump`.
- Produces: `raise_structured(body: list[ir.Stmt]) -> list[ir.Stmt]` — returns a new body where recognised patterns are replaced by `ir.If`/`ir.While`, and unrecognised label/jump regions are left as-is.
- Two patterns (exact shapes):
  - **if-then:** `Jump(target=L, cond=C, negate=True)` … straight-line stmts … `Label(L)` with no other jump to `L` and no back-edge → `If(cond=C, then=<stmts>)`. (A `JMPCN over the block` is "execute block when C true".)
  - **while:** `Label(G)` … `Jump(target=END, cond=C, negate=True)` … body … `Jump(target=G, cond=None)` … `Label(END)` → `While(cond=C, body=<body>)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_il_raise.py
from plcpy.frontends import il as il_fe
from plcpy import ir

IF_IL = """PROGRAM P
VAR_INPUT
    g : BOOL;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    LD g
    JMPCN skip
    LD 1
    ST y
skip:
END_PROGRAM
"""

def test_jmpcn_block_becomes_if():
    prog = il_fe.parse_st_il_raise(IF_IL)   # helper defined in Step 3
    # body should contain an If whose then-branch assigns y
    ifs = [s for s in prog.body if isinstance(s, ir.If)]
    assert len(ifs) == 1
    assert ifs[0].cond == ir.VarRef("g")
    assert isinstance(ifs[0].then[0], ir.Assign) and ifs[0].then[0].target == "y"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_il_raise.py -v`
Expected: FAIL (no `raise_structured` / helper)

- [ ] **Step 3: Implement the recogniser**

In `src/plcpy/frontends/_il_cfg.py`:

```python
from .. import ir

def raise_structured(body):
    out = []
    i = 0
    n = len(body)
    while i < n:
        s = body[i]
        # if-then:  JMPCN L ; <stmts...> ; L:
        if isinstance(s, ir.Jump) and s.cond is not None and s.negate:
            label = s.target
            # find the matching label, collecting only plain stmts in between
            j = i + 1
            block = []
            ok = True
            while j < n and not (isinstance(body[j], ir.Label) and body[j].name == label):
                if isinstance(body[j], (ir.Jump, ir.Label)):
                    ok = False
                    break
                block.append(body[j])
                j += 1
            if ok and j < n:
                out.append(ir.If(s.cond, block, [], []))
                i = j + 1            # skip the label
                continue
        out.append(s)
        i += 1
    return out
```

(Implement the `while` pattern as a second branch in the same loop using the shape from the Interfaces block; add a focused test `test_jmp_loop_becomes_while` mirroring the if test before implementing it.)

In `src/plcpy/frontends/il.py`, add the helper used by the test and wire raising into `parse_il`:

```python
from ._il_cfg import raise_structured

def parse_st_il_raise(text):       # test convenience wrapper
    return parse_il(text)
```

and at the end of `parse_il`, before constructing the `Program`, replace `body` with `raise_structured(body)`.

- [ ] **Step 4: Verify end-to-end raising → ST**

Add to `tests/test_il_raise.py`:

```python
import plcpy
def test_raised_if_converts_to_st():
    st = plcpy.convert(IF_IL, "il", "st").code
    assert "IF g THEN" in st
    assert "y := 1;" in st
    assert "END_IF;" in st
```

- [ ] **Step 5: Run tests, full suite, commit**

```bash
python -m pytest tests/test_il_raise.py -v
python -m pytest -q
git add src/plcpy/frontends tests/test_il_raise.py
git commit -m "feat: raise IL jump patterns to structured If/While"
```

---

### Task 4: Lower structured IR to IL jumps (export)

**Files:**
- Modify: `src/plcpy/backends/il.py` (replace the `If`/`While` comment-markers with real jump emission)
- Test: `tests/test_il_lower.py`

**Interfaces:**
- Consumes: `ir.If` (cond + then only — ELSIF/ELSE → diagnostic comment), `ir.While`, `ir.Assign`.
- Produces: `emit_il` renders `If`/`While` as labelled jump skeletons that **round-trip** back through the IL frontend's raiser (Task 3). Uses a per-program label counter.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_il_lower.py
import plcpy

ST = """PROGRAM P
VAR_INPUT
    g : BOOL;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    IF g THEN
        y := 1;
    END_IF;
END_PROGRAM
"""

def test_if_lowers_to_jmpcn_and_label():
    il = plcpy.convert(ST, "st", "il").code
    assert "JMPCN" in il
    assert "LD g" in il
    # round-trip: IL back to ST recovers the IF
    st2 = plcpy.convert(il, "il", "st").code
    assert "IF g THEN" in st2
    assert "y := 1;" in st2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_il_lower.py -v`
Expected: FAIL (`emit_il` currently emits `(* unsupported in IL: IF statement *)`)

- [ ] **Step 3: Emit jumps for If/While**

In `src/plcpy/backends/il.py`, add a label counter and replace the `If`/`While` branches of `_emit_stmt`. Thread a mutable counter via a small class or `itertools.count`:

```python
import itertools

def _emit_stmt(s, indent, labels):
    if isinstance(s, ir.Assign):
        ...  # unchanged
    if isinstance(s, ir.If):
        if s.elifs or s.orelse:
            return [f"{indent}(* IL export supports IF-THEN only; ELSIF/ELSE dropped *)"]
        end = f"L{next(labels)}"
        out = []
        cond_il = _emit_expr(s.cond, indent)
        if cond_il is None:
            return [f"{indent}(* unsupported IF condition *)"]
        out += cond_il
        out.append(f"{indent}JMPCN {end}")
        for inner in s.then:
            out += _emit_stmt(inner, indent, labels)
        out.append(f"{end}:")
        return out
    if isinstance(s, ir.While):
        guard = f"L{next(labels)}"
        end = f"L{next(labels)}"
        out = [f"{guard}:"]
        cond_il = _emit_expr(s.cond, indent)
        if cond_il is None:
            return [f"{indent}(* unsupported WHILE condition *)"]
        out += cond_il
        out.append(f"{indent}JMPCN {end}")
        for inner in s.body:
            out += _emit_stmt(inner, indent, labels)
        out.append(f"{indent}JMP {guard}")
        out.append(f"{end}:")
        return out
    ...  # For/Case unchanged (still comment-marked)
```

Update `emit_il` to create `labels = itertools.count()` and pass it into every `_emit_stmt` call.

> Note the label lines (`end:`) are emitted at indent 0 (no leading spaces) so the frontend's label detector (`raw.endswith(":")`) matches — verify the frontend strips leading whitespace (it calls `.strip()` per line, so indentation is fine either way).

- [ ] **Step 4: Run tests, full suite, commit**

```bash
python -m pytest tests/test_il_lower.py -v
python -m pytest -q
git add src/plcpy/backends/il.py tests/test_il_lower.py
git commit -m "feat: lower IF/WHILE to IL jumps with round-trip"
```

---

## Self-Review

- **Spec coverage:** fallback goto execution (Task 1), frontend label/jump parsing (Task 2), structured raising for if + while (Task 3), structured lowering for if + while (Task 4). Round-trip ST→IL→ST proven in Task 4.
- **Scope honesty:** ELSIF/ELSE, FOR, CASE in IL are explicitly comment-marked, not silently dropped. Documented as the supported subset.
- **Type consistency:** `ir.Jump(target, cond, negate)` and `ir.Label(name)` used identically in frontend, backend, and interpreter. `_emit_stmt` signature gains `labels` everywhere in Task 4.
- **Risk:** the goto interpreter (Task 1 Step 5) is the load-bearing fallback. Its label-index map must include trailing labels (`len(seq)` terminates) — covered by the if-then test where `done:` is last.
- **Placeholders:** Task 1 Step 4 intentionally shows a placeholder that Step 5 replaces — the engineer implements Step 5's concrete generator, not Step 4's stub.
