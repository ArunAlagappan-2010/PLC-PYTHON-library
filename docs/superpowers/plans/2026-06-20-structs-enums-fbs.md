# STRUCT / ENUM / User Function Blocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add user-defined composite types (`STRUCT`, `ENUM`) and user-defined function blocks (`FUNCTION_BLOCK` with `VAR_INPUT`/`VAR_OUTPUT`/`VAR` and a body) to the ST↔Python pipeline, with nested member access (`a.b.c`) working as both read and write through the IR, ST, and Python.

**Architecture:** Extend the existing IR with `TypeDef` (struct/enum) records and a generalised member-access model. The current `ir.Member` only handles `instance.field` for FB outputs; this plan generalises member access into a recursive `Member(base_expr, field)` so `motor.cfg.speed` works, and adds an `lvalue` form for assignment targets. Structs become Python classes (or nested dicts); enums become integer constants; user FBs become Python classes with a `scan()`-like call method. The pivot stays the IR — no new languages.

**Tech Stack:** Python 3.11+, `lark` (extend `st_grammar.lark`), stdlib only. Mirrors existing patterns in `src/plcpy/frontends/st.py` and `src/plcpy/backends/{st,python}.py`.

## Global Constraints

- Package `plcpy`, `src/` layout, editable install already present (`pip install -e ".[test]"`).
- IR is the only contract between frontends and backends.
- Source errors are `Diagnostic` objects, never exceptions.
- Run the FULL suite (`python -m pytest -q`) after each task — the grammar is shared, so regressions surface there.
- Match existing code style: dataclasses for IR, precedence-aware `_render` in the ST backend, `self.<name>` attribute model in the Python backend.

---

### Task 1: Generalise member access to nested expressions

**Files:**
- Modify: `src/plcpy/ir.py` (the `Member` dataclass)
- Modify: `src/plcpy/frontends/st.py` (the `member` transformer + grammar use)
- Modify: `src/plcpy/frontends/st_grammar.lark` (the `member` atom rule)
- Modify: `src/plcpy/backends/st.py` (the `Member` branch of `_render`)
- Modify: `src/plcpy/backends/python.py` (the `Member` branch of `_expr`)
- Test: `tests/test_member_nested.py`

**Interfaces:**
- Consumes: existing `ir.VarRef`, `ir.Member(instance: str, member: str)`.
- Produces: `ir.Member(base: Expr, member: str)` — `base` is now a full expression (was a bare `instance: str`). A single-level access `tmr.Q` becomes `Member(VarRef("tmr"), "Q")`. Nested `a.b.c` becomes `Member(Member(VarRef("a"), "b"), "c")`.
- **Migration note:** every existing reader of `Member.instance` must change to `Member.base`. Grep first: `rg "\.instance" src/plcpy` — the FB-timer code in `backends/python.py`, `backends/st.py`, `backends/fbd.py`, `frontends/st.py` and the `lsp`/`visualize` paths use `Member.instance`. Update each to render `base` recursively.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_member_nested.py
from plcpy.frontends import st as st_fe
from plcpy import ir

def test_two_level_member_access_parses_nested():
    src = (
        "PROGRAM P\nVAR_OUTPUT\n s : INT;\nEND_VAR\n"
        "VAR\n a : SomeFB;\nEND_VAR\n"
        " s := a.cfg.speed;\n"
        "END_PROGRAM\n"
    )
    prog = st_fe.parse_st(src).program
    val = prog.body[0].value
    assert isinstance(val, ir.Member) and val.member == "speed"
    assert isinstance(val.base, ir.Member) and val.base.member == "cfg"
    assert isinstance(val.base.base, ir.VarRef) and val.base.base.name == "a"
```

(Note: `a : SomeFB;` will emit an `unsupported type` diagnostic since `SomeFB` isn't a known type yet — that's fine; this task only proves nested member *parsing*, not type resolution. Task 4 adds user FB types.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_member_nested.py -v`
Expected: FAIL (`Member` has no `base`, or nested access not parsed)

- [ ] **Step 3: Change the IR**

In `src/plcpy/ir.py`, replace the `Member` dataclass:

```python
@dataclass
class Member:
    """Member access on an instance/struct, e.g. tmr.Q or motor.cfg.speed"""
    base: "Expr"
    member: str
```

- [ ] **Step 4: Update the grammar for chained member access**

In `src/plcpy/frontends/st_grammar.lark`, replace the `member` atom alternative. Member access must chain, so make it a postfix on a primary:

```lark
?atom: NAME "[" expr "]"          -> index
     | postfix
     | TIME_LIT                   -> time_lit
     | NUMBER                     -> number
     | BOOL_LIT                   -> bool_lit
     | "(" expr ")"
postfix: NAME ("." NAME)+         -> member
       | NAME                     -> var_ref
```

- [ ] **Step 5: Update the ST frontend transformer**

In `src/plcpy/frontends/st.py`, replace the `member` method:

```python
    def member(self, c):
        # c is [NAME, NAME, ...]; first is the base var, rest are field hops
        node = ir.VarRef(str(c[0]))
        for field in c[1:]:
            node = ir.Member(node, str(field))
        return node
```

- [ ] **Step 6: Update the ST backend**

In `src/plcpy/backends/st.py`, replace the `Member` branch of `_render`:

```python
    if isinstance(e, ir.Member):
        return f"{_render(e.base, 6)}.{e.member}"
```

- [ ] **Step 7: Update the Python backend and FBD backend**

In `src/plcpy/backends/python.py`, replace the `Member` branch of `_expr`:

```python
    if isinstance(e, ir.Member):
        return f"{_expr(e.base)}.{e.member}"
```

In `src/plcpy/backends/fbd.py`, replace the `Member` branch of `_fbd`:

```python
    if isinstance(e, ir.Member):
        return f"{_fbd(e.base)}.{e.member}"
```

- [ ] **Step 8: Fix the FB-timer call sites that used `Member.instance`**

The timer feature builds `ir.Member(instance, "Q")` with a string. Search and fix: `rg "ir.Member\(" src/plcpy`. In `frontends/st.py` the timer `member` path already routes through Step 5 (chained), so `tmr.Q` now yields `Member(VarRef("tmr"), "Q")`. The Python backend Step 7 renders that as `self.tmr.Q` — verify the timer test still passes.

- [ ] **Step 9: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS (existing timer tests must still pass with the new nested `Member`)

- [ ] **Step 10: Commit**

```bash
git add src/plcpy tests/test_member_nested.py
git commit -m "refactor: generalise Member access to nested expressions"
```

---

### Task 2: ENUM type definitions

**Files:**
- Modify: `src/plcpy/ir.py` (add `EnumDef`, `Program.types`)
- Modify: `src/plcpy/frontends/st_grammar.lark` (TYPE…END_TYPE block)
- Modify: `src/plcpy/frontends/st.py` (parse enum defs, resolve enum member refs)
- Modify: `src/plcpy/backends/st.py` (emit TYPE…END_TYPE)
- Modify: `src/plcpy/backends/python.py` (emit integer constants)
- Test: `tests/test_enum.py`

**Interfaces:**
- Consumes: `ir.Program`, `ir.VarRef`, `ir.Literal`.
- Produces:
  - `@dataclass class EnumDef: name: str; members: dict[str, int]` (member name → integer value).
  - `Program.types: list[EnumDef | StructDef] = field(default_factory=list)` (StructDef added in Task 3; add the field now typed as `list` to avoid churn).
  - Enum member references in code (e.g. `Color.Red`) resolve to `ir.Literal(<int>, ir.DataType.INT)` at parse time when the base name is a known enum.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enum.py
import plcpy
from plcpy.frontends import st as st_fe
from plcpy import ir, runtime

SRC = """TYPE
    Color : (Red, Green, Blue);
END_TYPE
PROGRAM P
VAR_INPUT
    sel : INT;
END_VAR
VAR_OUTPUT
    out : INT;
END_VAR
    out := Color.Green;
END_PROGRAM
"""

def test_enum_member_resolves_to_int():
    prog = st_fe.parse_st(SRC).program
    assert any(isinstance(t, ir.EnumDef) and t.name == "Color" for t in prog.types)
    # Color.Green -> literal 1 (Red=0, Green=1, Blue=2)
    assert isinstance(prog.body[0].value, ir.Literal)
    assert prog.body[0].value.value == 1

def test_enum_executes():
    code = plcpy.convert(SRC, "st", "python").code
    P = runtime.load_pou(code, "P")
    inst = P(); inst.scan()
    assert inst.out == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_enum.py -v`
Expected: FAIL (no `EnumDef`, `TYPE` block not parsed)

- [ ] **Step 3: Add the IR records**

In `src/plcpy/ir.py`, add above `Program`:

```python
@dataclass
class EnumDef:
    name: str
    members: dict[str, int] = field(default_factory=dict)
```

And add to `Program`:

```python
    types: list = field(default_factory=list)   # EnumDef | StructDef
```

- [ ] **Step 4: Add the grammar**

In `src/plcpy/frontends/st_grammar.lark`, change `start` to allow type blocks before programs, and add the enum rule:

```lark
start: type_block* program
type_block: "TYPE" type_def+ "END_TYPE"
type_def: NAME ":" "(" NAME ("," NAME)* ")" ";"   -> enum_def
```

- [ ] **Step 5: Update the transformer**

In `src/plcpy/frontends/st.py`, give `_ToIR` an enum registry and handlers. Add to `__init__`:

```python
        self.enums: dict[str, dict[str, int]] = {}
```

Add methods:

```python
    def enum_def(self, c):
        name = str(c[0])
        members = {str(m): i for i, m in enumerate(c[1:])}
        self.enums[name] = members
        return ir.EnumDef(name, members)

    def type_block(self, c):
        return ("types", [t for t in c])
```

Change `member` (from Task 1) so that when the base is a single `VarRef` naming a known enum, it resolves to a literal:

```python
    def member(self, c):
        base_name = str(c[0])
        if len(c) == 2 and base_name in self.enums:
            return ir.Literal(self.enums[base_name][str(c[1])], ir.DataType.INT)
        node = ir.VarRef(base_name)
        for field in c[1:]:
            node = ir.Member(node, str(field))
        return node
```

Change `start` and `program` handling: `start` now receives type_blocks then the program. Update:

```python
    def start(self, c):
        prog = c[-1]
        for item in c[:-1]:
            if isinstance(item, tuple) and item[0] == "types":
                prog.types.extend(item[1])
        return prog
```

- [ ] **Step 6: Update the ST backend**

In `src/plcpy/backends/st.py`, in `emit_st`, prepend a TYPE block when `program.types` is non-empty (handle `EnumDef`; `StructDef` added in Task 3):

```python
    head = []
    enums = [t for t in program.types if isinstance(t, ir.EnumDef)]
    if enums:
        head.append("TYPE")
        for e in enums:
            names = ", ".join(e.members.keys())
            head.append(f"    {e.name} : ({names});")
        head.append("END_TYPE")
    lines = head + [f"PROGRAM {program.name}"]
```

(Replace the existing `lines = [f"PROGRAM {program.name}"]` line with the block above.)

- [ ] **Step 7: Run the test**

Run: `python -m pytest tests/test_enum.py -v`
Expected: PASS (Python backend needs no change — enums are already literals by emit time)

- [ ] **Step 8: Run the full suite & commit**

```bash
python -m pytest -q
git add src/plcpy tests/test_enum.py
git commit -m "feat: add ENUM type definitions"
```

---

### Task 3: STRUCT type definitions

**Files:**
- Modify: `src/plcpy/ir.py` (add `StructDef`)
- Modify: `src/plcpy/frontends/st_grammar.lark` (struct in `type_def`, struct var type)
- Modify: `src/plcpy/frontends/st.py` (parse struct defs; struct-typed vars)
- Modify: `src/plcpy/backends/python.py` (emit a dataclass-like init for struct vars)
- Modify: `src/plcpy/backends/st.py` (emit struct TYPE defs)
- Test: `tests/test_struct.py`

**Interfaces:**
- Consumes: `ir.Program`, `ir.VarDecl`, `ir.Member`, `ir.Assign`.
- Produces:
  - `@dataclass class StructDef: name: str; fields: list[tuple[str, str]]` — ordered `(field_name, type_name)`.
  - `ir.VarDecl.struct_type: str | None = None` — when set, the var is an instance of that struct.
  - Python backend emits each struct var as a `types.SimpleNamespace(field=default, ...)` so `self.motor.speed = x` works for read and write.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_struct.py
import plcpy
from plcpy.frontends import st as st_fe
from plcpy import ir, runtime

SRC = """TYPE
    Motor : STRUCT
        speed : INT;
        running : BOOL;
    END_STRUCT;
END_TYPE
PROGRAM P
VAR_INPUT
    cmd : INT;
END_VAR
VAR_OUTPUT
    rpm : INT;
END_VAR
VAR
    m : Motor;
END_VAR
    m.speed := cmd;
    m.running := cmd > 0;
    rpm := m.speed;
END_PROGRAM
"""

def test_struct_def_and_member_write():
    prog = st_fe.parse_st(SRC).program
    assert any(isinstance(t, ir.StructDef) and t.name == "Motor" for t in prog.types)
    m = next(v for v in prog.vars if v.name == "m")
    assert m.struct_type == "Motor"
    # m.speed := cmd  is an Assign whose target is a Member lvalue
    assert isinstance(prog.body[0], ir.Assign)
    assert isinstance(prog.body[0].target, ir.Member)

def test_struct_executes():
    code = plcpy.convert(SRC, "st", "python").code
    P = runtime.load_pou(code, "P")
    inst = P(); inst.cmd = 42; inst.scan()
    assert inst.rpm == 42
```

> **Design decision this test forces:** `Assign.target` must accept a `Member` (or `Index`) lvalue, not just `str`. Implement by adding a new statement `MemberAssign(target: Member, value: Expr)` rather than widening `Assign.target` (keeps existing `Assign` readers working — same approach the array `IndexAssign` used). The grammar routes `NAME "." NAME ... ":=" ...` to `member_assign`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_struct.py -v`
Expected: FAIL

- [ ] **Step 3: Add IR records**

In `src/plcpy/ir.py`:

```python
@dataclass
class StructDef:
    name: str
    fields: list[tuple[str, str]] = field(default_factory=list)  # (field, type_name)

@dataclass
class MemberAssign:
    target: "Member"
    value: "Expr"
```

Add `MemberAssign` to the `Stmt` union, and add to `VarDecl`:

```python
    struct_type: str | None = None
```

- [ ] **Step 4: Grammar — struct def + struct-typed var + member assignment**

In `src/plcpy/frontends/st_grammar.lark`, extend `type_def` and the statement/type rules:

```lark
type_def: NAME ":" "(" NAME ("," NAME)* ")" ";"          -> enum_def
        | NAME ":" "STRUCT" struct_field+ "END_STRUCT" ";" -> struct_def
struct_field: NAME ":" NAME ";"
```

Add a member-assignment statement (place alongside `index_assign`):

```lark
statement: assign | index_assign | member_assign | if_stmt | while_stmt | for_stmt | case_stmt | fb_call
member_assign: NAME ("." NAME)+ ":=" expr ";"
```

`type_spec`'s `scalar_type` (`NAME`) already accepts a struct name as a type — resolution happens in the transformer.

- [ ] **Step 5: Transformer — struct defs, struct var typing, member_assign**

In `src/plcpy/frontends/st.py`, add a struct registry in `__init__`:

```python
        self.structs: set[str] = set()
```

Add handlers:

```python
    def struct_field(self, c): return (str(c[0]), str(c[1]))
    def struct_def(self, c):
        name = str(c[0])
        self.structs.add(name)
        return ir.StructDef(name, [f for f in c[1:]])

    def member_assign(self, c):
        # c = [NAME, NAME, ..., expr]; last child is the value
        *path, value = c
        node = ir.VarRef(str(path[0]))
        for field in path[1:]:
            node = ir.Member(node, str(field))
        return ir.MemberAssign(node, value)
```

In `_resolve_type` (added by the array plan), make struct names resolve without a diagnostic by treating any name in `self.structs` as a struct marker. Update `var_decl` so a struct-typed var sets `struct_type`:

```python
        if type_tok in self.structs:
            return ("struct", name, type_tok)
```

and in `program`, route `("struct", name, sname)` to `ir.VarDecl(name, ir.DataType.INT, scope, struct_type=sname)` (the `type` field is unused for structs).

**Ordering caveat:** `start` parses `type_block*` before `program`, but lark transforms bottom-up, so `struct_def`/`enum_def` run before `program`/`member`. That means `self.structs`/`self.enums` are populated before the program body is transformed. Confirm by running the test; if the body transforms first, switch the frontend to a two-pass approach (transform types, then re-run with registries populated) — but bottom-up order makes this unnecessary.

- [ ] **Step 6: Python backend — struct init + MemberAssign**

In `src/plcpy/backends/python.py`, add at the top of the emitted module when any struct vars exist:

```python
    if any(v.struct_type for v in program.vars):
        lines.insert(0, "import types as _types")
        lines.insert(1, "")
```

In `__init__` emission, for a struct var build a namespace from its `StructDef`:

```python
        if v.struct_type is not None:
            sd = next(t for t in program.types
                      if isinstance(t, ir.StructDef) and t.name == v.struct_type)
            fields = ", ".join(f"{fn}={_DEFAULTS[_TYPES_BY_NAME[ftn]]}" for fn, ftn in sd.fields)
            lines.append(f"        self.{v.name} = _types.SimpleNamespace({fields})")
```

Add a `_TYPES_BY_NAME` map at module top (`{"INT": ir.DataType.INT, "BOOL": ir.DataType.BOOL, "REAL": ir.DataType.REAL}`; default INT for unknown). Add a `MemberAssign` branch to `_stmts`:

```python
        elif isinstance(s, ir.MemberAssign):
            out.append(f"{pad}{_expr(s.target)} = {_expr(s.value)}")
```

(`_expr(Member)` already renders `self.m.speed` via Task 1.)

- [ ] **Step 7: ST backend — struct TYPE defs + MemberAssign**

In `src/plcpy/backends/st.py`, in the TYPE head block (Task 2), also emit structs:

```python
    structs = [t for t in program.types if isinstance(t, ir.StructDef)]
    if enums or structs:
        head.append("TYPE")
        for e in enums:
            head.append(f"    {e.name} : ({', '.join(e.members)});")
        for sd in structs:
            head.append(f"    {sd.name} : STRUCT")
            for fn, ftn in sd.fields:
                head.append(f"        {fn} : {ftn};")
            head.append("    END_STRUCT;")
        head.append("END_TYPE")
```

Add the `MemberAssign` branch to `_stmts`:

```python
        elif isinstance(s, ir.MemberAssign):
            out.append(f"{pad}{_expr(s.target)} := {_expr(s.value)};")
```

And in `emit_st`'s var-section loop, render a struct var as `name : StructType;` (when `v.struct_type` is set, use it instead of `v.type.value`).

- [ ] **Step 8: Run tests + full suite + commit**

```bash
python -m pytest tests/test_struct.py -v
python -m pytest -q
git add src/plcpy tests/test_struct.py
git commit -m "feat: add STRUCT type definitions with member lvalues"
```

---

### Task 4: User-defined function blocks

**Files:**
- Modify: `src/plcpy/ir.py` (add `FunctionBlockDef`, `Program.fb_defs`)
- Modify: `src/plcpy/frontends/st_grammar.lark` (`FUNCTION_BLOCK` … `END_FUNCTION_BLOCK`)
- Modify: `src/plcpy/frontends/st.py` (parse FB defs; register names as FB types)
- Modify: `src/plcpy/backends/python.py` (emit a class per FB def; instance calls)
- Modify: `src/plcpy/backends/st.py` (emit FB defs)
- Test: `tests/test_user_fb.py`

**Interfaces:**
- Consumes: `ir.Program`, `ir.VarDecl`, `ir.FBInstance`, `ir.FBCall`, `ir.Member` (Task 1).
- Produces:
  - `@dataclass class FunctionBlockDef: name: str; vars: list[VarDecl]; body: list[Stmt]`.
  - `Program.fb_defs: list[FunctionBlockDef] = field(default_factory=list)`.
  - The ST frontend registers each FB def name into `_FB_TYPES` (per-parse), so `m : Counter;` is recognised as an FB instance, and `m(EN := x)` is an `FBCall`, and `m.count` is `Member(VarRef("m"), "count")`.
  - Python backend emits one class per FB def with an `__init__` (inputs/outputs/locals default) and a `__call__(self, **kwargs)` that assigns inputs then runs the body; member reads pull outputs back.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_user_fb.py
import plcpy
from plcpy import runtime

SRC = """FUNCTION_BLOCK Counter
VAR_INPUT
    step : INT;
END_VAR
VAR_OUTPUT
    count : INT;
END_VAR
    count := count + step;
END_FUNCTION_BLOCK
PROGRAM P
VAR_OUTPUT
    total : INT;
END_VAR
VAR
    c : Counter;
END_VAR
    c(step := 2);
    total := c.count;
END_PROGRAM
"""

def test_user_fb_accumulates_across_scans():
    code = plcpy.convert(SRC, "st", "python").code
    P = runtime.load_pou(code, "P")
    inst = P()
    trace = runtime.run_scans(inst, [{}, {}, {}], ["total"])
    # count += 2 each scan -> 2, 4, 6
    assert [t.outputs["total"] for t in trace] == [2, 4, 6]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_user_fb.py -v`
Expected: FAIL

- [ ] **Step 3: Add the IR record**

In `src/plcpy/ir.py`:

```python
@dataclass
class FunctionBlockDef:
    name: str
    vars: list[VarDecl] = field(default_factory=list)
    body: list[Stmt] = field(default_factory=list)
```

Add to `Program`: `fb_defs: list[FunctionBlockDef] = field(default_factory=list)`.

- [ ] **Step 4: Grammar — FUNCTION_BLOCK before program**

In `src/plcpy/frontends/st_grammar.lark`:

```lark
start: type_block* fb_def* program
fb_def: "FUNCTION_BLOCK" NAME var_section* statement* "END_FUNCTION_BLOCK"
```

- [ ] **Step 5: Transformer — collect FB defs, register names**

In `src/plcpy/frontends/st.py`, the `_ToIR` instance needs a mutable FB-type set per parse. Replace the module-level `_FB_TYPES` use with an instance copy in `__init__`:

```python
        self.fb_types = set(_FB_TYPES)   # TON/TOF plus any user FBs
        self.fb_defs: list[ir.FunctionBlockDef] = []
```

Change `var_decl`'s FB check from `type_tok in _FB_TYPES` to `type_tok in self.fb_types`. Add the handler:

```python
    def fb_def(self, c):
        name = str(c[0])
        self.fb_types.add(name)
        vars_: list[ir.VarDecl] = []
        body: list = []
        for item in c[1:]:
            if isinstance(item, tuple) and item[0] in _SCOPE_RULE:
                scope = _SCOPE_RULE[item[0]]
                for decl in item[1]:
                    if decl[0] == "var":
                        vars_.append(ir.VarDecl(decl[1], decl[2], scope))
            else:
                body.append(item)
        fbdef = ir.FunctionBlockDef(name, vars_, body)
        self.fb_defs.append(fbdef)
        return ("fbdef", fbdef)
```

**Registration-order caveat:** `var_decl` for the *program*'s `c : Counter;` must see `Counter` in `self.fb_types`. Bottom-up transform runs `fb_def` (which registers the name) before the `program` rule's `var_decl`s only if lark visits children left-to-right depth-first — which it does for `Transformer`. Verify with the test; if the program's vars resolve before the FB def registers, switch to a pre-scan: before `_PARSER.parse`, regex-scan for `FUNCTION_BLOCK\s+(\w+)` and seed `self.fb_types`. Include that regex pre-scan in `parse_st` as the robust path:

```python
    import re as _re
    fb_names = set(_re.findall(r"FUNCTION_BLOCK\s+(\w+)", text))
```

and pass into `_ToIR` (add a constructor arg `fb_names`). This avoids any ordering fragility.

In `start`, collect `("fbdef", ...)` items into `prog.fb_defs`.

- [ ] **Step 6: Python backend — class per FB def, call semantics**

In `src/plcpy/backends/python.py`, before emitting the program class, emit each FB def as a class:

```python
def _emit_fb(fb: ir.FunctionBlockDef) -> list[str]:
    lines = [f"class {fb.name}:", "    def __init__(self):"]
    body_vars = fb.vars or []
    if body_vars:
        for v in body_vars:
            lines.append(f"        self.{v.name} = {_DEFAULTS[v.type]}")
    else:
        lines.append("        pass")
    lines.append("    def __call__(self, **kw):")
    lines.append("        for _k, _v in kw.items(): setattr(self, _k, _v)")
    inner = _stmts(fb.body, 2)
    lines.extend(inner or ["        pass"])
    return lines
```

In `emit_python`, prepend the FB classes (and the `from plcpy.runtime import TON, TOF` line only if a TON/TOF instance is used — keep the existing logic). The `FBCall` emission must support user FBs (kwargs) as well as timers (positional). Change the `FBCall` branch: if `s.instance` refers to a TON/TOF instance, use positional `(IN, PT, dt)`; otherwise emit `self.<inst>(<k>=<v>, ...)`. Track timer instance names from `program.fbs` whose `fb_type in {"TON","TOF"}`:

```python
        elif isinstance(s, ir.FBCall):
            timer_names = {fb.name for fb in program.fbs if fb.fb_type in ("TON", "TOF")}
            if s.instance in timer_names:
                in_s = _expr(s.args.get("IN")) if "IN" in s.args else "False"
                pt_s = _expr(s.args.get("PT")) if "PT" in s.args else "0"
                out.append(f"{pad}self.{s.instance}({in_s}, {pt_s}, self._dt_ms)")
            else:
                kw = ", ".join(f"{k}={_expr(v)}" for k, v in s.args.items())
                out.append(f"{pad}self.{s.instance}({kw})")
```

> `_stmts` is module-level and doesn't currently receive `program`. Pass timer names down: change `_stmts(stmts, indent)` to `_stmts(stmts, indent, timer_names=frozenset())` and thread `timer_names` through recursive calls; compute it once in `emit_python` and `_emit_fb` passes an empty set. Update every internal `_stmts(...)` call to forward `timer_names`.

In `emit_python` `__init__`, create user-FB instances the same way as timers but with the FB class name: the existing `self.<fb.name> = <fb.fb_type>()` line already does this for any `fb.fb_type`, so user FB instances are constructed correctly once their classes are emitted above.

- [ ] **Step 7: ST backend — emit FB defs**

In `src/plcpy/backends/st.py`, before `PROGRAM`, emit each `FunctionBlockDef`:

```python
    for fb in program.fb_defs:
        head.append(f"FUNCTION_BLOCK {fb.name}")
        for scope in (ir.VarScope.INPUT, ir.VarScope.OUTPUT, ir.VarScope.LOCAL):
            decls = [v for v in fb.vars if v.scope is scope]
            if not decls:
                continue
            head.append(_SCOPE_KW[scope])
            for v in decls:
                head.append(f"    {v.name} : {v.type.value};")
            head.append("END_VAR")
        head.extend(_stmts(fb.body, 1))
        head.append("END_FUNCTION_BLOCK")
```

- [ ] **Step 8: Run tests + full suite + commit**

```bash
python -m pytest tests/test_user_fb.py -v
python -m pytest -q
git add src/plcpy tests/test_user_fb.py
git commit -m "feat: add user-defined function blocks"
```

---

## Self-Review

- **Spec coverage:** nested member access (Task 1), ENUM (Task 2), STRUCT + member lvalues (Task 3), user FBs (Task 4). All four sub-features covered.
- **Type consistency:** `Member.base` is used uniformly after Task 1 (Tasks 3/4 build `Member` via `VarRef`/chaining). `MemberAssign.target` is always a `Member`. `Program.types`/`fb_defs` introduced once and reused. `_stmts` signature change (adding `timer_names`) is called out explicitly in Task 4 Step 6 — apply it consistently or the recursion drops the param.
- **Ordering risk** (registries populated before use) is the main hazard; each affected task includes a regex pre-scan fallback so it can't deadlock.
- **Placeholders:** none — every code step is concrete.
- **Other backends:** IL/LD/PLCopen/vendors will hit `MemberAssign`/struct vars and should comment-mark or skip them; add a one-line guard in each `else`/fallback if a backend raises (the array/timer tasks established this pattern — reuse `test_*_handles_..._without_crashing` style matrix tests).
