# PLCopen XML for FBD & SFC (+ Layout Preservation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing `plcopen` language (currently TC6 Ladder only) to also import/export **FBD** (`<FBD>` block networks) and **SFC** (`<SFC>` step/transition charts) bodies, and preserve **diagram layout coordinates** (`<position x= y=>`) across round-trips when present.

**Architecture:** The `plcopen` frontend dispatches on the POU `<body>` child (`<LD>`, `<FBD>`, or `<SFC>`) to a body-specific parser, each lowering to the existing IR (FBD → expression `Assign`s like the textual FBD frontend; SFC → the `ir.Sfc` chart + lowered body like the textual SFC frontend). The backend mirrors this by emitting the matching body element from the IR. Layout is carried on IR nodes via an optional `layout` dict (`{"x": int, "y": int}`) populated on import and re-emitted on export; absent layout is auto-assigned.

**Tech Stack:** Python 3.11+, stdlib `xml.etree.ElementTree` (already used by `src/plcpy/plcopen.py`). Reuses `ir.Sfc`, `ir.Assign`, expression nodes.

## Global Constraints

- Package `plcpy`, `src/` layout. IR is the only frontend/backend contract.
- Reuse the existing `src/plcpy/plcopen.py` module and its `_local()` namespace-stripping helper; do not add a new language id (keep `plcopen`).
- Source errors are `Diagnostic` objects, never exceptions.
- Layout is **optional** — programs without coordinates must still import/export; never crash on a missing `<position>`.
- Run the full suite after each task. The existing `tests/test_plcopen.py` (ladder) must keep passing.

---

### Task 1: Dispatch the PLCopen body parser on LD / FBD / SFC

**Files:**
- Modify: `src/plcpy/plcopen.py` (`parse_plcopen` body handling)
- Test: `tests/test_plcopen_fbd.py`

**Interfaces:**
- Consumes: existing `parse_plcopen`, `_local`, the LD parsing already present.
- Produces: `parse_plcopen` inspects the first child of `<body>` and calls `_parse_ld_body` (existing logic, extracted), `_parse_fbd_body` (Task 1), or `_parse_sfc_body` (Task 3). Returns the same `ParseResult`.
- `_parse_fbd_body(fbd_el) -> tuple[list[VarDecl], list[Stmt]]` — wait, vars are parsed from `<interface>` already; this returns `list[Stmt]` (the `Assign`s) plus a set of temp var names to declare. Signature: `_parse_fbd_body(fbd_el, declared: set[str]) -> tuple[list[ir.Stmt], list[ir.VarDecl]]`.

PLCopen FBD network shape (subset this task supports):

```xml
<FBD>
  <inVariable localId="1"><expression>a</expression></inVariable>
  <inVariable localId="2"><expression>b</expression></inVariable>
  <block localId="3" typeName="ADD">
    <inputVariables>
      <variable formalParameter="IN1"><connectionPointIn><connection refLocalId="1"/></connectionPointIn></variable>
      <variable formalParameter="IN2"><connectionPointIn><connection refLocalId="2"/></connectionPointIn></variable>
    </inputVariables>
    <outputVariables>
      <variable formalParameter="OUT"><connectionPointOut/></variable>
    </outputVariables>
  </block>
  <outVariable localId="4"><expression>y</expression>
    <connectionPointIn><connection refLocalId="3"/></connectionPointIn>
  </outVariable>
</FBD>
```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plcopen_fbd.py
import plcpy
from plcpy import runtime

FBD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://www.plcopen.org/xml/tc6_0201">
  <types><pous>
    <pou name="Calc" pouType="program">
      <interface>
        <inputVars>
          <variable name="a"><type><INT/></type></variable>
          <variable name="b"><type><INT/></type></variable>
        </inputVars>
        <outputVars>
          <variable name="y"><type><INT/></type></variable>
        </outputVars>
      </interface>
      <body>
        <FBD>
          <inVariable localId="1"><expression>a</expression></inVariable>
          <inVariable localId="2"><expression>b</expression></inVariable>
          <block localId="3" typeName="ADD">
            <inputVariables>
              <variable formalParameter="IN1"><connectionPointIn><connection refLocalId="1"/></connectionPointIn></variable>
              <variable formalParameter="IN2"><connectionPointIn><connection refLocalId="2"/></connectionPointIn></variable>
            </inputVariables>
            <outputVariables>
              <variable formalParameter="OUT"><connectionPointOut/></variable>
            </outputVariables>
          </block>
          <outVariable localId="4"><expression>y</expression>
            <connectionPointIn><connection refLocalId="3"/></connectionPointIn>
          </outVariable>
        </FBD>
      </body>
    </pou>
  </pous></types>
</project>
"""

def test_plcopen_fbd_import_executes():
    res = plcpy.convert(FBD_XML, "plcopen", "python")
    assert res.diagnostics == []
    Calc = runtime.load_pou(res.code, "Calc")
    inst = Calc(); inst.a, inst.b = 4, 5; inst.scan()
    assert inst.y == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_plcopen_fbd.py -v`
Expected: FAIL (FBD body ignored — current parser only handles `<LD>`)

- [ ] **Step 3: Extract LD body parsing and add the dispatcher**

In `src/plcpy/plcopen.py`, refactor `parse_plcopen`: move the existing `<LD>` graph-walk into `_parse_ld_body(ld_el, diagnostics) -> list[ir.Stmt]`. Then dispatch:

```python
    body_stmts: list[ir.Stmt] = []
    extra_vars: list[ir.VarDecl] = []
    body_el = next((el for el in pou.iter() if _local(el.tag) == "body"), None)
    if body_el is not None:
        for child in body_el:
            kind = _local(child.tag)
            if kind == "LD":
                body_stmts = _parse_ld_body(child, diagnostics)
            elif kind == "FBD":
                body_stmts, extra_vars = _parse_fbd_body(child, {v.name for v in vars_})
            elif kind == "SFC":
                ...  # Task 3
            break
    vars_.extend(extra_vars)
```

- [ ] **Step 4: Implement `_parse_fbd_body`**

In `src/plcpy/plcopen.py`:

```python
_FBD_NARY = {"ADD": "+", "MUL": "*", "AND": "and", "OR": "or"}
_FBD_BINARY = {"SUB": "-", "DIV": "/", "GT": ">", "GE": ">=", "LT": "<",
               "LE": "<=", "EQ": "=", "NE": "<>"}

def _parse_fbd_body(fbd, declared):
    nodes = {}     # localId -> element kind/data
    for el in fbd:
        lid = el.get("localId")
        kind = _local(el.tag)
        if kind in ("inVariable", "outVariable"):
            expr_el = next((c for c in el.iter() if _local(c.tag) == "expression"), None)
            text = (expr_el.text or "").strip() if expr_el is not None else ""
            refs = [c.get("refLocalId") for c in el.iter()
                    if _local(c.tag) == "connection" and c.get("refLocalId")]
            nodes[lid] = {"kind": kind, "text": text, "refs": refs}
        elif kind == "block":
            inputs = []
            for v in el.iter():
                if _local(v.tag) == "variable" and v.get("formalParameter", "").startswith("IN"):
                    r = next((c.get("refLocalId") for c in v.iter()
                              if _local(c.tag) == "connection" and c.get("refLocalId")), None)
                    inputs.append(r)
            nodes[lid] = {"kind": "block", "type": el.get("typeName", "").upper(),
                          "inputs": inputs}

    def build(lid):
        n = nodes.get(lid)
        if n is None:
            return None
        if n["kind"] == "inVariable":
            return _operand(n["text"])
        if n["kind"] == "block":
            args = [build(r) for r in n["inputs"]]
            args = [a for a in args if a is not None]
            t = n["type"]
            if t == "NOT" and args:
                return ir.UnaryOp("not", args[0])
            if t in _FBD_NARY and args:
                acc = args[0]
                for a in args[1:]:
                    acc = ir.BinOp(_FBD_NARY[t], acc, a)
                return acc
            if t in _FBD_BINARY and len(args) == 2:
                return ir.BinOp(_FBD_BINARY[t], args[0], args[1])
        return None

    stmts = []
    extra = []
    for lid, n in nodes.items():
        if n["kind"] == "outVariable":
            expr = build(n["refs"][0]) if n["refs"] else None
            if expr is not None:
                stmts.append(ir.Assign(n["text"], expr))
    return stmts, extra
```

Add an `_operand(tok)` helper (reuse the one from the textual FBD frontend logic: TRUE/FALSE → BOOL literal, int/float → numeric literal, else `VarRef`).

- [ ] **Step 5: Run the test, full suite, commit**

```bash
python -m pytest tests/test_plcopen_fbd.py -v
python -m pytest -q   # existing ladder tests must still pass
git add src/plcpy/plcopen.py tests/test_plcopen_fbd.py
git commit -m "feat: import PLCopen FBD block networks"
```

---

### Task 2: Export FBD bodies + emit by body kind

**Files:**
- Modify: `src/plcpy/plcopen.py` (`emit_plcopen` body dispatch)
- Test: `tests/test_plcopen_fbd_export.py`

**Interfaces:**
- Consumes: `emit_plcopen`, `ir.Program`, `ir.Assign` with expression RHS.
- Produces: `emit_plcopen` chooses the body element by content: if the program has an `ir.Sfc`, emit `<SFC>` (Task 4); else if any assignment RHS contains arithmetic/function structure better shown as blocks, emit `<FBD>`; else emit `<LD>` (existing). Add an explicit `body` parameter so callers can force a kind: `emit_plcopen(program, body="auto"|"ld"|"fbd"|"sfc")`. Keep `"auto"` default.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plcopen_fbd_export.py
import xml.etree.ElementTree as ET
import plcpy

ST = """PROGRAM Calc
VAR_INPUT
    a : INT;
    b : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := a + b;
END_PROGRAM
"""

def test_arithmetic_exports_as_fbd_block():
    xml = plcpy.convert(ST, "st", "plcopen").code
    root = ET.fromstring(xml)
    def local(t): return t.rsplit("}", 1)[-1]
    blocks = [e for e in root.iter() if local(e.tag) == "block"]
    assert any(b.get("typeName") == "ADD" for b in blocks)
    # re-import recovers the assignment
    import plcpy as p
    py = p.convert(xml, "plcopen", "python").code
    ns = {}; exec(compile(py, "<x>", "exec"), ns)
    inst = ns["Calc"](); inst.a, inst.b = 2, 3; inst.scan()
    assert inst.y == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_plcopen_fbd_export.py -v`
Expected: FAIL (arithmetic assignment isn't ladder-expressible → currently emitted as an `<!-- unsupported rung -->` comment)

- [ ] **Step 3: Add body-kind selection + FBD emitter**

In `src/plcpy/plcopen.py`, add `_emit_fbd_body(ld_parent, program, ids)` that walks each `ir.Assign` and emits `inVariable`/`block`/`outVariable` elements (the inverse of Task 1). Decide body kind in `emit_plcopen`:

```python
def _is_ladder_expressible(program):
    # every assign RHS reduces to contacts (bool AND/OR/NOT of vars)?
    from .backends.ld import _and_terms, _contact  # reuse existing helpers
    for s in program.body:
        if not isinstance(s, ir.Assign):
            return False
        expr = s.value
        if isinstance(expr, ir.UnaryOp) and expr.op == "not":
            expr = expr.operand
        if any(_contact(t) is None for t in _and_terms(expr)):
            return False
    return True
```

```python
def emit_plcopen(program, body="auto"):
    ...
    body_el = ET.SubElement(pou, "body")
    kind = body
    if kind == "auto":
        if program.sfc is not None:
            kind = "sfc"
        elif _is_ladder_expressible(program):
            kind = "ld"
        else:
            kind = "fbd"
    if kind == "ld":
        ld = ET.SubElement(body_el, "LD")
        ids = _Ids()
        for s in program.body:
            if isinstance(s, ir.Assign):
                _emit_rung(ld, s, ids)
    elif kind == "fbd":
        fbd = ET.SubElement(body_el, "FBD")
        _emit_fbd_body(fbd, program, _Ids())
    elif kind == "sfc":
        _emit_sfc_body(ET.SubElement(body_el, "SFC"), program, _Ids())  # Task 4
    ...
```

Implement `_emit_fbd_body`: for each `ir.Assign`, recursively emit blocks. Helper `_emit_expr_fbd(parent, expr, ids) -> localId` returns the localId whose output carries the expression value:

```python
_FUNC_NAME = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "and": "AND",
              "or": "OR", ">": "GT", ">=": "GE", "<": "LT", "<=": "LE",
              "=": "EQ", "<>": "NE"}

def _emit_expr_fbd(parent, e, ids):
    if isinstance(e, (ir.VarRef, ir.Literal)):
        lid = ids.next()
        iv = ET.SubElement(parent, "inVariable", localId=lid)
        ET.SubElement(iv, "expression").text = (
            e.name if isinstance(e, ir.VarRef) else _operand_text(e))
        return lid
    if isinstance(e, ir.UnaryOp) and e.op == "not":
        src = _emit_expr_fbd(parent, e.operand, ids)
        lid = ids.next()
        blk = ET.SubElement(parent, "block", localId=lid, typeName="NOT")
        inv = ET.SubElement(ET.SubElement(blk, "inputVariables"), "variable",
                            formalParameter="IN")
        ET.SubElement(ET.SubElement(inv, "connectionPointIn"), "connection", refLocalId=src)
        ET.SubElement(ET.SubElement(blk, "outputVariables"), "variable", formalParameter="OUT")
        return lid
    if isinstance(e, ir.BinOp):
        l = _emit_expr_fbd(parent, e.left, ids)
        r = _emit_expr_fbd(parent, e.right, ids)
        lid = ids.next()
        blk = ET.SubElement(parent, "block", localId=lid, typeName=_FUNC_NAME[e.op])
        invs = ET.SubElement(blk, "inputVariables")
        for fp, ref in (("IN1", l), ("IN2", r)):
            v = ET.SubElement(invs, "variable", formalParameter=fp)
            ET.SubElement(ET.SubElement(v, "connectionPointIn"), "connection", refLocalId=ref)
        ET.SubElement(ET.SubElement(blk, "outputVariables"), "variable", formalParameter="OUT")
        return lid
    return None

def _emit_fbd_body(fbd, program, ids):
    for s in program.body:
        if isinstance(s, ir.Assign):
            src = _emit_expr_fbd(fbd, s.value, ids)
            ov = ET.SubElement(fbd, "outVariable", localId=ids.next())
            ET.SubElement(ov, "expression").text = s.target
            ET.SubElement(ET.SubElement(ov, "connectionPointIn"), "connection", refLocalId=src)
```

Add `_operand_text(literal)` (BOOL → TRUE/FALSE, else str(value)).

- [ ] **Step 4: Run tests, full suite, commit**

```bash
python -m pytest tests/test_plcopen_fbd_export.py -v
python -m pytest -q
git add src/plcpy/plcopen.py tests/test_plcopen_fbd_export.py
git commit -m "feat: export PLCopen FBD block networks"
```

---

### Task 3: Import PLCopen SFC charts

**Files:**
- Modify: `src/plcpy/plcopen.py` (`_parse_sfc_body`, wire into dispatcher)
- Test: `tests/test_plcopen_sfc.py`

**Interfaces:**
- Consumes: `_local`, `ir.Sfc`, `ir.SfcStep`, the SFC lowering. **Reuse the textual SFC lowering** by importing `from .frontends.sfc import _lower, STEP_VAR` so the executable body matches the textual SFC path exactly.
- Produces: `_parse_sfc_body(sfc_el) -> tuple[ir.Sfc, list[ir.VarDecl], list[ir.Stmt]]`. PLCopen SFC uses `<step name= initialStep="true">`, `<transition>` with `<condition>` and connections, `<actionBlock>`. This task supports the linear subset (single source/target), enough to round-trip a simple chart.

PLCopen SFC shape (subset):

```xml
<SFC>
  <step localId="1" name="Idle" initialStep="true"/>
  <transition localId="2">
    <condition><inline><ST><![CDATA[go]]></ST></inline></condition>
    <connectionPointIn><connection refLocalId="1"/></connectionPointIn>
    <connectionPointOut/>
  </transition>
  <step localId="3" name="Run"/>
</SFC>
```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plcopen_sfc.py
import plcpy
from plcpy import runtime

SFC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://www.plcopen.org/xml/tc6_0201">
  <types><pous>
    <pou name="Latch" pouType="program">
      <interface>
        <inputVars><variable name="go"><type><BOOL/></type></variable></inputVars>
        <outputVars><variable name="active"><type><BOOL/></type></variable></outputVars>
      </interface>
      <body>
        <SFC>
          <step localId="1" name="Idle" initialStep="true">
            <actionBlock><action><inline><ST><![CDATA[active := FALSE;]]></ST></inline></action></actionBlock>
          </step>
          <transition localId="2" target="Run">
            <condition><inline><ST><![CDATA[go]]></ST></inline></condition>
          </transition>
          <step localId="3" name="Run">
            <actionBlock><action><inline><ST><![CDATA[active := TRUE;]]></ST></inline></action></actionBlock>
          </step>
        </SFC>
      </body>
    </pou>
  </pous></types>
</project>
"""

def test_plcopen_sfc_executes():
    code = plcpy.convert(SFC_XML, "plcopen", "python").code
    Latch = runtime.load_pou(code, "Latch")
    inst = Latch()
    trace = runtime.run_scans(inst, [{"go": True}, {"go": False}], ["active"])
    # Idle action runs (active False), go fires -> Run; next scan Run action -> active True
    assert trace[-1].outputs["active"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_plcopen_sfc.py -v`
Expected: FAIL (SFC body ignored)

- [ ] **Step 3: Implement `_parse_sfc_body`**

In `src/plcpy/plcopen.py`, reuse the textual SFC statement/expression parsers:

```python
from .frontends.sfc import _lower, STEP_VAR, _parse_stmts, _parse_expr

def _parse_sfc_body(sfc_el):
    steps = []
    step_by_id = {}
    for el in sfc_el:
        if _local(el.tag) == "step":
            actions = []
            act = next((c for c in el.iter() if _local(c.tag) == "ST"), None)
            if act is not None and act.text:
                actions = _parse_stmts(act.text)
            s = ir.SfcStep(el.get("name"), initial=el.get("initialStep") == "true",
                           actions=actions)
            steps.append(s)
            step_by_id[el.get("localId")] = s
    # transitions: condition + target attribute (subset)
    for el in sfc_el:
        if _local(el.tag) == "transition":
            cond_el = next((c for c in el.iter() if _local(c.tag) == "ST"), None)
            cond = _parse_expr((cond_el.text or "").strip()) if cond_el is not None else None
            target = el.get("target")
            # source = nearest preceding step by document order
            src = steps[[i for i, s in enumerate(steps)].pop()] if steps else None
            if cond is not None and target:
                # attach to the most recently declared step before this transition
                steps[_last_step_index(sfc_el, el, step_by_id)].transitions.append((cond, target))
    steps.sort(key=lambda s: 0 if s.initial else 1)
    sfc = ir.Sfc(steps)
    body = _lower(sfc)
    decls = [ir.VarDecl(STEP_VAR, ir.DataType.INT, ir.VarScope.LOCAL)]
    return sfc, decls, body
```

Implement `_last_step_index(parent, trans_el, step_by_id)` by iterating `parent` in document order, tracking the last `step` seen before `trans_el`, and returning its index in `steps`. (Document order in ElementTree is preserved by iteration over a parent element.)

Wire into the dispatcher (Task 1 Step 3):

```python
            elif kind == "SFC":
                sfc_obj, sfc_vars, body_stmts = _parse_sfc_body(child)
                extra_vars = sfc_vars
                _attach_sfc = sfc_obj   # set program.sfc after construction
```

and set `program = ir.Program(name, vars_, body_stmts, sfc=_attach_sfc)` when SFC, else `sfc=None`.

- [ ] **Step 4: Run tests, full suite, commit**

```bash
python -m pytest tests/test_plcopen_sfc.py -v
python -m pytest -q
git add src/plcpy/plcopen.py tests/test_plcopen_sfc.py
git commit -m "feat: import PLCopen SFC charts"
```

---

### Task 4: Export SFC charts + layout preservation

**Files:**
- Modify: `src/plcpy/ir.py` (add optional `layout` to `SfcStep`)
- Modify: `src/plcpy/plcopen.py` (`_emit_sfc_body`; read/write `<position>`)
- Test: `tests/test_plcopen_sfc_export.py`

**Interfaces:**
- Consumes: `program.sfc`, the `_local` helper.
- Produces:
  - `ir.SfcStep.layout: dict | None = None` (e.g. `{"x": 100, "y": 40}`).
  - `_parse_sfc_body` (Task 3) populates `layout` from `<position x= y=>` when present.
  - `_emit_sfc_body(sfc_el, program, ids)` emits `<step>`/`<transition>` with `<position>` from `layout`, or auto-assigned coordinates (step i at `y = 40 + i*80`) when absent.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plcopen_sfc_export.py
import xml.etree.ElementTree as ET
import plcpy

def test_sfc_roundtrips_through_plcopen_with_layout():
    sfc_src = """PROGRAM Latch
VAR_INPUT
    go : BOOL;
END_VAR
VAR_OUTPUT
    active : BOOL;
END_VAR
INITIAL_STEP Idle
    ACTION
        active := FALSE;
    END_ACTION
    TRANSITION go TO Run
END_STEP
STEP Run
    ACTION
        active := TRUE;
    END_ACTION
END_STEP
END_PROGRAM
"""
    xml = plcpy.convert(sfc_src, "sfc", "plcopen").code
    root = ET.fromstring(xml)
    def local(t): return t.rsplit("}", 1)[-1]
    steps = [e for e in root.iter() if local(e.tag) == "step"]
    names = {s.get("name") for s in steps}
    assert names == {"Idle", "Run"}
    # every step has a position (auto-assigned)
    assert all(any(local(c.tag) == "position" for c in s) for s in steps)
    # re-import and execute
    code = plcpy.convert(xml, "plcopen", "python").code
    ns = {}; exec(compile(code, "<x>", "exec"), ns)
    from plcpy import runtime
    inst = ns["Latch"]()
    trace = runtime.run_scans(inst, [{"go": True}, {"go": False}], ["active"])
    assert trace[-1].outputs["active"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_plcopen_sfc_export.py -v`
Expected: FAIL (no SFC export; `convert(..., "st"→sfc"→"plcopen")` — note the source is `sfc`, exported to `plcopen`)

- [ ] **Step 3: Add `layout` to SfcStep + populate on import**

In `src/plcpy/ir.py`, add to `SfcStep`: `layout: dict | None = None`.

In `_parse_sfc_body` (Task 3), when reading a `<step>`, read position:

```python
            pos = next((c for c in el if _local(c.tag) == "position"), None)
            layout = {"x": int(pos.get("x", 0)), "y": int(pos.get("y", 0))} if pos is not None else None
            s = ir.SfcStep(el.get("name"), initial=el.get("initialStep") == "true",
                           actions=actions, layout=layout)
```

- [ ] **Step 4: Implement `_emit_sfc_body`**

In `src/plcpy/plcopen.py`:

```python
def _emit_sfc_body(sfc_el, program, ids):
    step_id = {}
    for i, step in enumerate(program.sfc.steps):
        lid = ids.next()
        step_id[step.name] = lid
        attrs = {"localId": lid, "name": step.name}
        if step.initial:
            attrs["initialStep"] = "true"
        st = ET.SubElement(sfc_el, "step", **attrs)
        lay = step.layout or {"x": 100, "y": 40 + i * 80}
        ET.SubElement(st, "position", x=str(lay["x"]), y=str(lay["y"]))
        if step.actions:
            ab = ET.SubElement(st, "actionBlock")
            act = ET.SubElement(ab, "action")
            inline = ET.SubElement(ET.SubElement(act, "inline"), "ST")
            from .backends.st import _stmts as _st_stmts
            inline.text = "\n".join(_st_stmts(step.actions, 0))
    # transitions
    for step in program.sfc.steps:
        for cond, target in step.transitions:
            tr = ET.SubElement(sfc_el, "transition", localId=ids.next(), target=target)
            cnd = ET.SubElement(ET.SubElement(ET.SubElement(tr, "condition"), "inline"), "ST")
            from .backends.st import _expr as _st_expr
            cnd.text = _st_expr(cond)
```

(For the parallel model from the SFC-parallel plan, iterate `program.sfc.transitions` instead; this plan targets the linear subset to keep it independent.)

- [ ] **Step 5: Run tests, full suite, commit**

```bash
python -m pytest tests/test_plcopen_sfc_export.py -v
python -m pytest -q
git add src/plcpy/ir.py src/plcpy/plcopen.py tests/test_plcopen_sfc_export.py
git commit -m "feat: export PLCopen SFC charts with layout preservation"
```

---

## Self-Review

- **Spec coverage:** FBD import (Task 1), FBD export (Task 2), SFC import (Task 3), SFC export + layout (Task 4). Ladder (existing) is untouched and dispatched alongside.
- **Reuse:** SFC lowering reuses `frontends.sfc._lower`/`STEP_VAR`/`_parse_stmts`/`_parse_expr`; FBD block maps mirror the textual FBD frontend; LD path is extracted, not rewritten.
- **Layout:** optional everywhere — `step.layout or <auto>` guarantees export never crashes on missing coords; import tolerates absent `<position>`.
- **Type consistency:** `_Ids` (existing in `plcopen.py`) reused for localId allocation across all body emitters. `_parse_*_body` all return `list[ir.Stmt]` (+ extras) consistently; the dispatcher assembles `vars_`/`body`/`sfc` uniformly.
- **Scope honesty:** FBD subset = ADD/SUB/MUL/DIV/AND/OR/NOT/compare blocks (matches the textual FBD frontend); SFC subset = linear single-source/target charts. Parallel SFC over PLCopen is the union of this plan + the SFC-parallel plan and is noted as such.
- **Placeholders:** none — `_last_step_index` and `_operand`/`_operand_text` are specified as concrete helpers to implement in-task.
