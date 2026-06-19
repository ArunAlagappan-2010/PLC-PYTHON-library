# PLC↔Python Phase 1 (Walking Skeleton) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the end-to-end pivot architecture for a small but real subset: parse Structured Text → IR → emit Python (a scan-cycle module) and the reverse (Python → IR → ST), proving the Parse→IR→Emit design with a plugin registry, a runtime simulator, and tests.

**Architecture:** A shared dataclass-based Intermediate Representation (IR) sits between language frontends (parsers) and backends (emitters), both discovered through a plugin registry. Phase 1 implements the IR, the registry, the ST frontend/backend (via a `lark` grammar), the Python frontend/backend (via the stdlib `ast` module), a scan-cycle runtime, and a `convert()` facade. Conversion of any pair is always `frontend → IR → backend`.

**Tech Stack:** Python 3.11+, `lark` 1.x (ST grammar), stdlib `ast` (Python frontend), `dataclasses`, `pytest`, `hypothesis` (optional property tests).

## Global Constraints

- Python 3.11+ (local interpreter is 3.11.8).
- Package name: `plcpy`. Source under `src/plcpy/`. Tests under `tests/`.
- IR is the only contract between frontends and backends — a backend never imports a frontend and vice-versa.
- Source-level errors are reported as `Diagnostic` objects, not raised exceptions. Exceptions (`PlcPyError` subclasses) are for programmer/API misuse only.
- Use `src/` layout with an editable install (`pip install -e .`).
- Supported Phase-1 ST subset: `PROGRAM` blocks; `VAR_INPUT`/`VAR_OUTPUT`/`VAR` declarations of `BOOL`/`INT`/`REAL`; `:=` assignment; `IF/ELSIF/ELSE/END_IF`; binary ops `+ - * / AND OR` and comparisons `= <> < <= > >=`; `NOT`; parenthesised expressions; integer/real/boolean literals. Anything outside the subset → `unsupported` diagnostic, never a silent drop.

---

### Task 1: Project scaffold & packaging

**Files:**
- Create: `pyproject.toml`
- Create: `src/plcpy/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: importable `plcpy` package with `plcpy.__version__: str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
def test_package_imports_and_has_version():
    import plcpy
    assert isinstance(plcpy.__version__, str)
    assert plcpy.__version__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'plcpy'`

- [ ] **Step 3: Create the package files**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "plcpy"
version = "0.1.0"
description = "Bidirectional PLC (IEC 61131-3) <-> Python converter"
requires-python = ">=3.11"
dependencies = ["lark>=1.1"]

[project.optional-dependencies]
test = ["pytest>=7", "hypothesis>=6"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```python
# src/plcpy/__init__.py
__version__ = "0.1.0"
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Install editable and run the test**

Run: `python -m pip install -e ".[test]" && python -m pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/plcpy/__init__.py tests/__init__.py tests/test_smoke.py
git commit -m "chore: scaffold plcpy package"
```

---

### Task 2: IR core dataclasses

**Files:**
- Create: `src/plcpy/ir.py`
- Test: `tests/test_ir.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the IR node types used by every other task. Exact definitions:
  - `class VarScope(enum.Enum)` with members `INPUT`, `OUTPUT`, `LOCAL`.
  - `class DataType(enum.Enum)` with members `BOOL`, `INT`, `REAL`.
  - `@dataclass class VarDecl: name: str; type: DataType; scope: VarScope; initial: object | None = None`
  - `@dataclass class Literal: value: object; type: DataType`
  - `@dataclass class VarRef: name: str`
  - `@dataclass class BinOp: op: str; left: Expr; right: Expr` (op ∈ `+ - * / and or = <> < <= > >=`)
  - `@dataclass class UnaryOp: op: str; operand: Expr` (op ∈ `not -`)
  - `Expr = Literal | VarRef | BinOp | UnaryOp` (a `typing.Union` alias)
  - `@dataclass class Assign: target: str; value: Expr`
  - `@dataclass class If: cond: Expr; then: list[Stmt]; elifs: list[tuple[Expr, list[Stmt]]]; orelse: list[Stmt]`
  - `Stmt = Assign | If` (a `typing.Union` alias)
  - `@dataclass class Program: name: str; vars: list[VarDecl]; body: list[Stmt]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ir.py
from plcpy import ir

def test_build_minimal_program():
    p = ir.Program(
        name="Main",
        vars=[
            ir.VarDecl("x", ir.DataType.INT, ir.VarScope.INPUT),
            ir.VarDecl("y", ir.DataType.INT, ir.VarScope.OUTPUT),
        ],
        body=[ir.Assign("y", ir.BinOp("+", ir.VarRef("x"), ir.Literal(1, ir.DataType.INT)))],
    )
    assert p.name == "Main"
    assert p.vars[0].scope is ir.VarScope.INPUT
    assert isinstance(p.body[0], ir.Assign)
    assert p.body[0].value.op == "+"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ir.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'plcpy.ir'`

- [ ] **Step 3: Write the IR module**

```python
# src/plcpy/ir.py
from __future__ import annotations
import enum
from dataclasses import dataclass, field
from typing import Union


class VarScope(enum.Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    LOCAL = "LOCAL"


class DataType(enum.Enum):
    BOOL = "BOOL"
    INT = "INT"
    REAL = "REAL"


@dataclass
class Literal:
    value: object
    type: DataType


@dataclass
class VarRef:
    name: str


@dataclass
class BinOp:
    op: str
    left: "Expr"
    right: "Expr"


@dataclass
class UnaryOp:
    op: str
    operand: "Expr"


Expr = Union[Literal, VarRef, BinOp, UnaryOp]


@dataclass
class Assign:
    target: str
    value: "Expr"


@dataclass
class If:
    cond: "Expr"
    then: list["Stmt"]
    elifs: list[tuple["Expr", list["Stmt"]]] = field(default_factory=list)
    orelse: list["Stmt"] = field(default_factory=list)


Stmt = Union[Assign, If]


@dataclass
class VarDecl:
    name: str
    type: DataType
    scope: VarScope
    initial: object | None = None


@dataclass
class Program:
    name: str
    vars: list[VarDecl] = field(default_factory=list)
    body: list[Stmt] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ir.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/plcpy/ir.py tests/test_ir.py
git commit -m "feat: add IR core dataclasses"
```

---

### Task 3: Diagnostics & error types

**Files:**
- Create: `src/plcpy/diagnostics.py`
- Create: `src/plcpy/errors.py`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class Severity(enum.Enum)` → `ERROR`, `WARNING`, `UNSUPPORTED`.
  - `@dataclass class Diagnostic: message: str; severity: Severity; line: int = 0; col: int = 0; code: str = ""`
  - `class PlcPyError(Exception)` base; `class UnknownLanguageError(PlcPyError)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_diagnostics.py
from plcpy.diagnostics import Diagnostic, Severity
from plcpy import errors

def test_diagnostic_defaults():
    d = Diagnostic("oops", Severity.ERROR)
    assert d.line == 0 and d.col == 0 and d.code == ""
    assert d.severity is Severity.ERROR

def test_error_hierarchy():
    assert issubclass(errors.UnknownLanguageError, errors.PlcPyError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_diagnostics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'plcpy.diagnostics'`

- [ ] **Step 3: Write the modules**

```python
# src/plcpy/diagnostics.py
from __future__ import annotations
import enum
from dataclasses import dataclass


class Severity(enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    UNSUPPORTED = "unsupported"


@dataclass
class Diagnostic:
    message: str
    severity: Severity
    line: int = 0
    col: int = 0
    code: str = ""
```

```python
# src/plcpy/errors.py
class PlcPyError(Exception):
    """Base class for plcpy programmer/API errors (not source errors)."""


class UnknownLanguageError(PlcPyError):
    """Raised when a language id is not registered."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_diagnostics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/plcpy/diagnostics.py src/plcpy/errors.py tests/test_diagnostics.py
git commit -m "feat: add diagnostics and error types"
```

---

### Task 4: Plugin registry

**Files:**
- Create: `src/plcpy/registry.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Consumes: `plcpy.ir.Program`, `plcpy.diagnostics.Diagnostic`, `plcpy.errors.UnknownLanguageError`.
- Produces:
  - `@dataclass class ParseResult: program: Program | None; diagnostics: list[Diagnostic]`
  - `Frontend = Callable[[str], ParseResult]`
  - `Backend = Callable[[Program], str]`
  - `def register_frontend(lang: str, fn: Frontend) -> None`
  - `def register_backend(lang: str, fn: Backend) -> None`
  - `def get_frontend(lang: str) -> Frontend` (raises `UnknownLanguageError`)
  - `def get_backend(lang: str) -> Backend` (raises `UnknownLanguageError`)
  - `def languages() -> dict[str, dict[str, bool]]` → `{lang: {"frontend": bool, "backend": bool}}`
  - Module-level dicts are private (`_FRONTENDS`, `_BACKENDS`); the functions are the API.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_registry.py
import pytest
from plcpy import registry, ir
from plcpy.errors import UnknownLanguageError

def test_register_and_get_roundtrip():
    def fe(text): return registry.ParseResult(ir.Program("P"), [])
    def be(prog): return "code"
    registry.register_frontend("demo", fe)
    registry.register_backend("demo", be)
    assert registry.get_frontend("demo") is fe
    assert registry.get_backend("demo") is be
    langs = registry.languages()
    assert langs["demo"] == {"frontend": True, "backend": True}

def test_unknown_language_raises():
    with pytest.raises(UnknownLanguageError):
        registry.get_frontend("nope-not-registered")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'plcpy.registry'`

- [ ] **Step 3: Write the registry**

```python
# src/plcpy/registry.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
from .ir import Program
from .diagnostics import Diagnostic
from .errors import UnknownLanguageError


@dataclass
class ParseResult:
    program: Program | None
    diagnostics: list[Diagnostic]


Frontend = Callable[[str], "ParseResult"]
Backend = Callable[[Program], str]

_FRONTENDS: dict[str, Frontend] = {}
_BACKENDS: dict[str, Backend] = {}


def register_frontend(lang: str, fn: Frontend) -> None:
    _FRONTENDS[lang] = fn


def register_backend(lang: str, fn: Backend) -> None:
    _BACKENDS[lang] = fn


def get_frontend(lang: str) -> Frontend:
    try:
        return _FRONTENDS[lang]
    except KeyError:
        raise UnknownLanguageError(f"no frontend registered for {lang!r}")


def get_backend(lang: str) -> Backend:
    try:
        return _BACKENDS[lang]
    except KeyError:
        raise UnknownLanguageError(f"no backend registered for {lang!r}")


def languages() -> dict[str, dict[str, bool]]:
    keys = set(_FRONTENDS) | set(_BACKENDS)
    return {
        k: {"frontend": k in _FRONTENDS, "backend": k in _BACKENDS}
        for k in sorted(keys)
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/plcpy/registry.py tests/test_registry.py
git commit -m "feat: add plugin registry"
```

---

### Task 5: ST grammar & frontend (ST → IR)

**Files:**
- Create: `src/plcpy/frontends/__init__.py`
- Create: `src/plcpy/frontends/st_grammar.lark`
- Create: `src/plcpy/frontends/st.py`
- Test: `tests/test_frontend_st.py`

**Interfaces:**
- Consumes: `plcpy.ir.*`, `plcpy.registry.ParseResult`, `plcpy.diagnostics.*`.
- Produces:
  - `def parse_st(text: str) -> ParseResult`
  - Side effect on import: `register_frontend("st", parse_st)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_frontend_st.py
from plcpy.frontends import st
from plcpy import ir

SRC = """
PROGRAM Main
VAR_INPUT
    x : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := x + 1;
    IF x > 0 THEN
        y := 0;
    END_IF;
END_PROGRAM
"""

def test_parse_program_structure():
    res = st.parse_st(SRC)
    assert res.diagnostics == []
    p = res.program
    assert p.name == "Main"
    names = {v.name: v.scope for v in p.vars}
    assert names["x"] is ir.VarScope.INPUT
    assert names["y"] is ir.VarScope.OUTPUT
    assert isinstance(p.body[0], ir.Assign)
    assert p.body[0].target == "y"
    assert isinstance(p.body[1], ir.If)
    assert p.body[1].cond.op == ">"

def test_unsupported_construct_reports_diagnostic():
    res = st.parse_st("PROGRAM P\n VAR z : WORD; END_VAR\nEND_PROGRAM\n")
    assert any(d.severity.name == "UNSUPPORTED" for d in res.diagnostics)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_frontend_st.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'plcpy.frontends'`

- [ ] **Step 3: Write the grammar**

```lark
// src/plcpy/frontends/st_grammar.lark
start: program
program: "PROGRAM" NAME var_section* statement* "END_PROGRAM"

var_section: var_input | var_output | var_local
var_input: "VAR_INPUT" var_decl* "END_VAR"
var_output: "VAR_OUTPUT" var_decl* "END_VAR"
var_local: "VAR" var_decl* "END_VAR"
var_decl: NAME ":" TYPE ";"

statement: assign | if_stmt
assign: NAME ":=" expr ";"
if_stmt: "IF" expr "THEN" statement* elif_clause* else_clause? "END_IF" ";"
elif_clause: "ELSIF" expr "THEN" statement*
else_clause: "ELSE" statement*

?expr: or_expr
?or_expr: or_expr "OR" and_expr  -> binop_or
       | and_expr
?and_expr: and_expr "AND" cmp_expr -> binop_and
        | cmp_expr
?cmp_expr: cmp_expr CMP add_expr  -> binop_cmp
        | add_expr
?add_expr: add_expr ADD term      -> binop_add
        | term
?term: term MUL factor            -> binop_mul
     | factor
?factor: "NOT" factor             -> unary_not
       | "-" factor               -> unary_neg
       | atom
?atom: NAME                       -> var_ref
     | NUMBER                     -> number
     | BOOL_LIT                   -> bool_lit
     | "(" expr ")"

TYPE: "BOOL" | "INT" | "REAL" | /[A-Za-z_][A-Za-z0-9_]*/
CMP: "<=" | ">=" | "<>" | "<" | ">" | "="
ADD: "+" | "-"
MUL: "*" | "/"
BOOL_LIT: "TRUE" | "FALSE"
NAME: /[A-Za-z_][A-Za-z0-9_]*/
NUMBER: /[0-9]+(\.[0-9]+)?/

%import common.WS
%ignore WS
```

Note: `TYPE` deliberately matches any identifier so unknown types reach the transformer, which emits an `unsupported` diagnostic (rather than a hard parse error). Lark resolves the known-type alternations first by priority of literal terminals.

- [ ] **Step 4: Write the frontend transformer**

```python
# src/plcpy/frontends/__init__.py
```

```python
# src/plcpy/frontends/st.py
from __future__ import annotations
from pathlib import Path
from lark import Lark, Transformer, Token
from lark.exceptions import LarkError
from .. import ir
from ..registry import ParseResult, register_frontend
from ..diagnostics import Diagnostic, Severity

_GRAMMAR = (Path(__file__).parent / "st_grammar.lark").read_text(encoding="utf-8")
_PARSER = Lark(_GRAMMAR, parser="lalr")

_TYPES = {"BOOL": ir.DataType.BOOL, "INT": ir.DataType.INT, "REAL": ir.DataType.REAL}
_SCOPE_RULE = {"var_input": ir.VarScope.INPUT, "var_output": ir.VarScope.OUTPUT,
               "var_local": ir.VarScope.LOCAL}


class _ToIR(Transformer):
    def __init__(self):
        super().__init__()
        self.diagnostics: list[Diagnostic] = []

    # expressions
    def var_ref(self, c): return ir.VarRef(str(c[0]))
    def number(self, c):
        t = str(c[0])
        if "." in t:
            return ir.Literal(float(t), ir.DataType.REAL)
        return ir.Literal(int(t), ir.DataType.INT)
    def bool_lit(self, c): return ir.Literal(str(c[0]) == "TRUE", ir.DataType.BOOL)
    def unary_not(self, c): return ir.UnaryOp("not", c[0])
    def unary_neg(self, c): return ir.UnaryOp("-", c[0])
    def binop_or(self, c): return ir.BinOp("or", c[0], c[1])
    def binop_and(self, c): return ir.BinOp("and", c[0], c[1])
    def binop_cmp(self, c): return ir.BinOp(str(c[1]), c[0], c[2])
    def binop_add(self, c): return ir.BinOp(str(c[1]), c[0], c[2])
    def binop_mul(self, c): return ir.BinOp(str(c[1]), c[0], c[2])

    # statements
    def assign(self, c): return ir.Assign(str(c[0]), c[1])
    def elif_clause(self, c): return ("elif", c[0], [s for s in c[1:]])
    def else_clause(self, c): return ("else", [s for s in c])
    def if_stmt(self, c):
        cond = c[0]
        then: list = []
        elifs: list = []
        orelse: list = []
        for item in c[1:]:
            if isinstance(item, tuple) and item[0] == "elif":
                elifs.append((item[1], item[2]))
            elif isinstance(item, tuple) and item[0] == "else":
                orelse = item[1]
            else:
                then.append(item)
        return ir.If(cond, then, elifs, orelse)

    # declarations
    def var_decl(self, c):
        name = str(c[0]); type_tok = str(c[1])
        dt = _TYPES.get(type_tok)
        if dt is None:
            self.diagnostics.append(Diagnostic(
                f"unsupported type {type_tok!r}", Severity.UNSUPPORTED,
                line=getattr(c[1], "line", 0), code="ST_TYPE"))
            dt = ir.DataType.INT  # placeholder so structure survives
        return (name, dt)

    def var_input(self, c): return ("var_input", c)
    def var_output(self, c): return ("var_output", c)
    def var_local(self, c): return ("var_local", c)
    def var_section(self, c): return c[0]

    def program(self, c):
        name = str(c[0])
        vars_: list[ir.VarDecl] = []
        body: list = []
        for item in c[1:]:
            if isinstance(item, tuple) and item[0] in _SCOPE_RULE:
                scope = _SCOPE_RULE[item[0]]
                for decl in item[1]:
                    vname, dt = decl
                    vars_.append(ir.VarDecl(vname, dt, scope))
            else:
                body.append(item)
        return ir.Program(name, vars_, body)

    def statement(self, c): return c[0]
    def start(self, c): return c[0]


def parse_st(text: str) -> ParseResult:
    try:
        tree = _PARSER.parse(text)
    except LarkError as e:
        return ParseResult(None, [Diagnostic(str(e), Severity.ERROR, code="ST_PARSE")])
    t = _ToIR()
    program = t.transform(tree)
    return ParseResult(program, t.diagnostics)


register_frontend("st", parse_st)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_frontend_st.py -v`
Expected: PASS (both tests)

- [ ] **Step 6: Commit**

```bash
git add src/plcpy/frontends/ tests/test_frontend_st.py
git commit -m "feat: add ST frontend (ST -> IR)"
```

---

### Task 6: ST backend (IR → ST)

**Files:**
- Create: `src/plcpy/backends/__init__.py`
- Create: `src/plcpy/backends/st.py`
- Test: `tests/test_backend_st.py`

**Interfaces:**
- Consumes: `plcpy.ir.*`, `plcpy.registry.register_backend`.
- Produces:
  - `def emit_st(program: Program) -> str`
  - Side effect on import: `register_backend("st", emit_st)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backend_st.py
from plcpy.backends import st as st_backend
from plcpy.frontends import st as st_frontend

SRC = """PROGRAM Main
VAR_INPUT
    x : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := x + 1;
    IF x > 0 THEN
        y := 0;
    END_IF;
END_PROGRAM
"""

def test_roundtrip_st_to_st_is_stable():
    prog = st_frontend.parse_st(SRC).program
    out = st_backend.emit_st(prog)
    # Re-parse the emitted text; structure must match.
    prog2 = st_frontend.parse_st(out).program
    assert prog2.name == prog.name
    assert [v.name for v in prog2.vars] == [v.name for v in prog.vars]
    assert len(prog2.body) == len(prog.body)
    assert "y := x + 1" in out
    assert "IF x > 0 THEN" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backend_st.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'plcpy.backends'`

- [ ] **Step 3: Write the backend**

```python
# src/plcpy/backends/__init__.py
```

```python
# src/plcpy/backends/st.py
from __future__ import annotations
from .. import ir
from ..registry import register_backend

_SCOPE_KW = {ir.VarScope.INPUT: "VAR_INPUT", ir.VarScope.OUTPUT: "VAR_OUTPUT",
             ir.VarScope.LOCAL: "VAR"}
_CMP = {"=", "<>", "<", "<=", ">", ">="}


def _expr(e: ir.Expr) -> str:
    if isinstance(e, ir.Literal):
        if e.type is ir.DataType.BOOL:
            return "TRUE" if e.value else "FALSE"
        return str(e.value)
    if isinstance(e, ir.VarRef):
        return e.name
    if isinstance(e, ir.UnaryOp):
        op = "NOT " if e.op == "not" else "-"
        return f"{op}{_expr(e.operand)}"
    if isinstance(e, ir.BinOp):
        op = {"and": "AND", "or": "OR"}.get(e.op, e.op)
        return f"{_expr(e.left)} {op} {_expr(e.right)}"
    raise TypeError(f"unhandled expr {e!r}")


def _stmts(stmts: list[ir.Stmt], indent: int) -> list[str]:
    pad = "    " * indent
    out: list[str] = []
    for s in stmts:
        if isinstance(s, ir.Assign):
            out.append(f"{pad}{s.target} := {_expr(s.value)};")
        elif isinstance(s, ir.If):
            out.append(f"{pad}IF {_expr(s.cond)} THEN")
            out.extend(_stmts(s.then, indent + 1))
            for cond, body in s.elifs:
                out.append(f"{pad}ELSIF {_expr(cond)} THEN")
                out.extend(_stmts(body, indent + 1))
            if s.orelse:
                out.append(f"{pad}ELSE")
                out.extend(_stmts(s.orelse, indent + 1))
            out.append(f"{pad}END_IF;")
        else:
            raise TypeError(f"unhandled stmt {s!r}")
    return out


def emit_st(program: ir.Program) -> str:
    lines = [f"PROGRAM {program.name}"]
    # group vars by scope, preserving scope order INPUT, OUTPUT, LOCAL
    for scope in (ir.VarScope.INPUT, ir.VarScope.OUTPUT, ir.VarScope.LOCAL):
        decls = [v for v in program.vars if v.scope is scope]
        if not decls:
            continue
        lines.append(_SCOPE_KW[scope])
        for v in decls:
            lines.append(f"    {v.name} : {v.type.value};")
        lines.append("END_VAR")
    lines.extend(_stmts(program.body, 1))
    lines.append("END_PROGRAM")
    return "\n".join(lines) + "\n"


register_backend("st", emit_st)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backend_st.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/plcpy/backends/ tests/test_backend_st.py
git commit -m "feat: add ST backend (IR -> ST)"
```

---

### Task 7: Python backend (IR → scan-cycle module)

**Files:**
- Create: `src/plcpy/backends/python.py`
- Test: `tests/test_backend_python.py`

**Interfaces:**
- Consumes: `plcpy.ir.*`, `plcpy.registry.register_backend`.
- Produces:
  - `def emit_python(program: Program) -> str`
  - Side effect on import: `register_backend("python", emit_python)`.
  - Emitted module shape: a class named after the program with `__init__`
    setting every var to a zero-value default, and a `scan(self)` method whose
    body is the translated statements operating on `self.<var>`. Inputs/outputs
    are plain attributes (the runtime reads/writes them around `scan()`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backend_python.py
from plcpy.backends import python as py_backend
from plcpy import ir

def _prog():
    return ir.Program(
        name="Main",
        vars=[
            ir.VarDecl("x", ir.DataType.INT, ir.VarScope.INPUT),
            ir.VarDecl("y", ir.DataType.INT, ir.VarScope.OUTPUT),
        ],
        body=[
            ir.Assign("y", ir.BinOp("+", ir.VarRef("x"), ir.Literal(1, ir.DataType.INT))),
            ir.If(ir.BinOp(">", ir.VarRef("x"), ir.Literal(0, ir.DataType.INT)),
                  [ir.Assign("y", ir.Literal(0, ir.DataType.INT))]),
        ],
    )

def test_emitted_module_executes():
    code = py_backend.emit_python(_prog())
    ns: dict = {}
    exec(compile(code, "<emitted>", "exec"), ns)
    Main = ns["Main"]
    inst = Main()
    inst.x = 5
    inst.scan()
    # x=5 -> y = 6, then x>0 -> y=0
    assert inst.y == 0
    inst.x = -3
    inst.scan()
    # x=-3 -> y = -2, x>0 false -> y stays -2
    assert inst.y == -2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backend_python.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'plcpy.backends.python'`

- [ ] **Step 3: Write the backend**

```python
# src/plcpy/backends/python.py
from __future__ import annotations
from .. import ir
from ..registry import register_backend

_DEFAULTS = {ir.DataType.BOOL: "False", ir.DataType.INT: "0", ir.DataType.REAL: "0.0"}
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
        else:
            raise TypeError(f"unhandled stmt {s!r}")
    return out


def emit_python(program: ir.Program) -> str:
    lines = [f"class {program.name}:", "    def __init__(self):"]
    if program.vars:
        for v in program.vars:
            lines.append(f"        self.{v.name} = {_DEFAULTS[v.type]}")
    else:
        lines.append("        pass")
    lines.append("")
    lines.append("    def scan(self):")
    body = _stmts(program.body, 2)
    lines.extend(body or ["        pass"])
    return "\n".join(lines) + "\n"


register_backend("python", emit_python)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backend_python.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/plcpy/backends/python.py tests/test_backend_python.py
git commit -m "feat: add Python scan-cycle backend (IR -> Python)"
```

---

### Task 8: Python frontend (Python → IR)

**Files:**
- Create: `src/plcpy/frontends/python.py`
- Test: `tests/test_frontend_python.py`

**Interfaces:**
- Consumes: `plcpy.ir.*`, `plcpy.registry.ParseResult`, `plcpy.diagnostics.*`. Uses stdlib `ast`.
- Produces:
  - `def parse_python(text: str) -> ParseResult`
  - Side effect on import: `register_frontend("python", parse_python)`.
  - Recognises the exact module shape emitted by Task 7: a single class with
    `__init__` (attribute defaults → `VarDecl`s, scope `LOCAL` by default) and a
    `scan` method (statements → IR). Type is inferred from default literal
    (`False`→BOOL, `int`→INT, `float`→REAL). Constructs outside the subset →
    `unsupported` diagnostic.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_frontend_python.py
from plcpy.frontends import python as py_frontend
from plcpy import ir

CODE = """class Main:
    def __init__(self):
        self.x = 0
        self.y = 0

    def scan(self):
        self.y = (self.x + 1)
        if (self.x > 0):
            self.y = 0
"""

def test_parse_python_class_to_ir():
    res = py_frontend.parse_python(CODE)
    assert res.diagnostics == []
    p = res.program
    assert p.name == "Main"
    assert {v.name for v in p.vars} == {"x", "y"}
    assert isinstance(p.body[0], ir.Assign)
    assert p.body[0].target == "y"
    assert isinstance(p.body[1], ir.If)
    assert p.body[1].cond.op == ">"

def test_unsupported_python_reports_diagnostic():
    res = py_frontend.parse_python(
        "class P:\n    def __init__(self):\n        self.a = 0\n"
        "    def scan(self):\n        while self.a:\n            self.a = 0\n")
    assert any(d.severity.name == "UNSUPPORTED" for d in res.diagnostics)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_frontend_python.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'plcpy.frontends.python'`

- [ ] **Step 3: Write the frontend**

```python
# src/plcpy/frontends/python.py
from __future__ import annotations
import ast
from .. import ir
from ..registry import ParseResult, register_frontend
from ..diagnostics import Diagnostic, Severity

_CMP = {ast.Eq: "=", ast.NotEq: "<>", ast.Lt: "<", ast.LtE: "<=",
        ast.Gt: ">", ast.GtE: ">="}
_BIN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_BOOL = {ast.And: "and", ast.Or: "or"}


class _Conv:
    def __init__(self):
        self.diagnostics: list[Diagnostic] = []

    def unsupported(self, node, what):
        self.diagnostics.append(Diagnostic(
            f"unsupported Python construct: {what}", Severity.UNSUPPORTED,
            line=getattr(node, "lineno", 0), code="PY"))

    def expr(self, node) -> ir.Expr | None:
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id == "self":
            return ir.VarRef(node.attr)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return ir.Literal(node.value, ir.DataType.BOOL)
            if isinstance(node.value, int):
                return ir.Literal(node.value, ir.DataType.INT)
            if isinstance(node.value, float):
                return ir.Literal(node.value, ir.DataType.REAL)
            self.unsupported(node, f"literal {node.value!r}")
            return None
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return ir.UnaryOp("not", self.expr(node.operand))
            if isinstance(node.op, ast.USub):
                return ir.UnaryOp("-", self.expr(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            return ir.BinOp(_BIN[type(node.op)], self.expr(node.left), self.expr(node.right))
        if isinstance(node, ast.BoolOp) and type(node.op) in _BOOL:
            acc = self.expr(node.values[0])
            for v in node.values[1:]:
                acc = ir.BinOp(_BOOL[type(node.op)], acc, self.expr(v))
            return acc
        if isinstance(node, ast.Compare) and len(node.ops) == 1 \
                and type(node.ops[0]) in _CMP:
            return ir.BinOp(_CMP[type(node.ops[0])], self.expr(node.left),
                            self.expr(node.comparators[0]))
        self.unsupported(node, type(node).__name__)
        return None

    def stmt(self, node) -> ir.Stmt | None:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Attribute) \
                and isinstance(node.targets[0].value, ast.Name) \
                and node.targets[0].value.id == "self":
            return ir.Assign(node.targets[0].attr, self.expr(node.value))
        if isinstance(node, ast.If):
            cond = self.expr(node.test)
            then = [s for s in (self.stmt(x) for x in node.body) if s]
            orelse = [s for s in (self.stmt(x) for x in node.orelse) if s]
            return ir.If(cond, then, [], orelse)
        self.unsupported(node, type(node).__name__)
        return None


def parse_python(text: str) -> ParseResult:
    conv = _Conv()
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return ParseResult(None, [Diagnostic(str(e), Severity.ERROR, code="PY_SYNTAX")])
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef)), None)
    if cls is None:
        return ParseResult(None, [Diagnostic("no class found", Severity.ERROR, code="PY")])
    vars_: list[ir.VarDecl] = []
    body: list[ir.Stmt] = []
    for item in cls.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            for s in item.body:
                if isinstance(s, ast.Assign) and isinstance(s.targets[0], ast.Attribute):
                    name = s.targets[0].attr
                    val = s.value
                    dt = ir.DataType.INT
                    if isinstance(val, ast.Constant):
                        if isinstance(val.value, bool):
                            dt = ir.DataType.BOOL
                        elif isinstance(val.value, float):
                            dt = ir.DataType.REAL
                    vars_.append(ir.VarDecl(name, dt, ir.VarScope.LOCAL))
        elif isinstance(item, ast.FunctionDef) and item.name == "scan":
            for s in item.body:
                conv_stmt = conv.stmt(s)
                if conv_stmt:
                    body.append(conv_stmt)
    program = ir.Program(cls.name, vars_, body)
    return ParseResult(program, conv.diagnostics)


register_frontend("python", parse_python)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_frontend_python.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add src/plcpy/frontends/python.py tests/test_frontend_python.py
git commit -m "feat: add Python frontend (Python -> IR)"
```

---

### Task 9: Convert facade & plugin auto-loading

**Files:**
- Create: `src/plcpy/convert.py`
- Modify: `src/plcpy/__init__.py`
- Test: `tests/test_convert.py`

**Interfaces:**
- Consumes: `plcpy.registry.*`, the four plugin modules (imported for their
  registration side effects).
- Produces:
  - `@dataclass class ConvertResult: code: str | None; diagnostics: list[Diagnostic]`
  - `def convert(source: str, from_lang: str, to_lang: str) -> ConvertResult`
  - `plcpy.convert`, `plcpy.ConvertResult`, `plcpy.languages` re-exported from the package root.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_convert.py
import plcpy

ST_SRC = """PROGRAM Main
VAR_INPUT
    x : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := x + 1;
END_PROGRAM
"""

def test_st_to_python_executes():
    res = plcpy.convert(ST_SRC, "st", "python")
    assert res.diagnostics == []
    ns: dict = {}
    exec(compile(res.code, "<c>", "exec"), ns)
    m = ns["Main"]()
    m.x = 41
    m.scan()
    assert m.y == 42

def test_python_to_st_roundtrips():
    py = plcpy.convert(ST_SRC, "st", "python").code
    st = plcpy.convert(py, "python", "st").code
    assert "PROGRAM Main" in st
    assert "y := self.x + 1" in st or "y := x + 1" in st

def test_languages_lists_all_four():
    langs = plcpy.languages()
    assert langs["st"] == {"frontend": True, "backend": True}
    assert langs["python"] == {"frontend": True, "backend": True}
```

Note: `python→st` will render var refs as their plain names (the Python
frontend strips `self.`), so the expected substring is `y := x + 1`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_convert.py -v`
Expected: FAIL with `AttributeError: module 'plcpy' has no attribute 'convert'`

- [ ] **Step 3: Write the facade and wire up the package**

```python
# src/plcpy/convert.py
from __future__ import annotations
from dataclasses import dataclass
from .registry import get_frontend, get_backend, languages
from .diagnostics import Diagnostic, Severity

# Import plugins for their registration side effects.
from .frontends import st as _st_fe       # noqa: F401
from .frontends import python as _py_fe   # noqa: F401
from .backends import st as _st_be        # noqa: F401
from .backends import python as _py_be    # noqa: F401


@dataclass
class ConvertResult:
    code: str | None
    diagnostics: list[Diagnostic]


def convert(source: str, from_lang: str, to_lang: str) -> ConvertResult:
    frontend = get_frontend(from_lang)
    backend = get_backend(to_lang)
    parsed = frontend(source)
    if parsed.program is None:
        return ConvertResult(None, parsed.diagnostics)
    code = backend(parsed.program)
    return ConvertResult(code, parsed.diagnostics)
```

```python
# src/plcpy/__init__.py
__version__ = "0.1.0"

from .convert import convert, ConvertResult  # noqa: E402
from .registry import languages              # noqa: E402

__all__ = ["__version__", "convert", "ConvertResult", "languages"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_convert.py -v`
Expected: PASS (all three)

- [ ] **Step 5: Commit**

```bash
git add src/plcpy/convert.py src/plcpy/__init__.py tests/test_convert.py
git commit -m "feat: add convert() facade and plugin auto-loading"
```

---

### Task 10: Scan-cycle runtime simulator

**Files:**
- Create: `src/plcpy/runtime.py`
- Test: `tests/test_runtime.py`

**Interfaces:**
- Consumes: a compiled POU instance (any object with a `scan()` method and
  public attributes), `plcpy.convert.convert`.
- Produces:
  - `def load_pou(python_code: str, class_name: str) -> type` — compiles emitted
    code and returns the POU class.
  - `@dataclass class ScanTrace: cycle: int; outputs: dict[str, object]`
  - `def run_scans(instance, inputs_per_cycle: list[dict], output_names: list[str]) -> list[ScanTrace]`
    — for each input dict: set those attributes, call `scan()`, snapshot the
    named outputs. Implements read-inputs → scan → write/snapshot-outputs.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runtime.py
import plcpy
from plcpy import runtime

ST_SRC = """PROGRAM Main
VAR_INPUT
    x : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := x + 1;
END_PROGRAM
"""

def test_run_scans_produces_trace():
    code = plcpy.convert(ST_SRC, "st", "python").code
    Main = runtime.load_pou(code, "Main")
    inst = Main()
    trace = runtime.run_scans(
        inst,
        inputs_per_cycle=[{"x": 1}, {"x": 10}, {"x": 100}],
        output_names=["y"],
    )
    assert [t.outputs["y"] for t in trace] == [2, 11, 101]
    assert [t.cycle for t in trace] == [0, 1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'plcpy.runtime'`

- [ ] **Step 3: Write the runtime**

```python
# src/plcpy/runtime.py
from __future__ import annotations
from dataclasses import dataclass


def load_pou(python_code: str, class_name: str) -> type:
    ns: dict = {}
    exec(compile(python_code, "<plcpy-pou>", "exec"), ns)
    return ns[class_name]


@dataclass
class ScanTrace:
    cycle: int
    outputs: dict


def run_scans(instance, inputs_per_cycle: list[dict], output_names: list[str]) -> list[ScanTrace]:
    traces: list[ScanTrace] = []
    for cycle, inputs in enumerate(inputs_per_cycle):
        for name, value in inputs.items():   # read inputs
            setattr(instance, name, value)
        instance.scan()                      # execute logic
        snap = {n: getattr(instance, n) for n in output_names}  # write/snapshot outputs
        traces.append(ScanTrace(cycle, snap))
    return traces
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runtime.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/plcpy/runtime.py tests/test_runtime.py
git commit -m "feat: add scan-cycle runtime simulator"
```

---

### Task 11: Semantic-equivalence test & CLI

**Files:**
- Create: `src/plcpy/cli.py`
- Modify: `pyproject.toml` (add `[project.scripts]`)
- Test: `tests/test_semantic_equivalence.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `plcpy.convert.convert`, `plcpy.runtime.*`.
- Produces:
  - `def main(argv: list[str] | None = None) -> int` — CLI entry; usage
    `plcpy convert --from st --to python <file>` prints converted code to stdout;
    returns `0` on success, `2` on diagnostics-with-no-output.
  - console script `plcpy = "plcpy.cli:main"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_semantic_equivalence.py
import plcpy
from plcpy import runtime

ST_SRC = """PROGRAM Main
VAR_INPUT
    x : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := x + 1;
    IF x > 5 THEN
        y := 0;
    END_IF;
END_PROGRAM
"""

def test_st_and_roundtripped_st_behave_identically():
    # ST -> Python -> run
    py1 = plcpy.convert(ST_SRC, "st", "python").code
    inst1 = runtime.load_pou(py1, "Main")()
    # ST -> Python -> ST -> Python -> run
    st2 = plcpy.convert(py1, "python", "st").code
    py2 = plcpy.convert(st2, "st", "python").code
    inst2 = runtime.load_pou(py2, "Main")()
    inputs = [{"x": i} for i in range(-3, 10)]
    t1 = runtime.run_scans(inst1, inputs, ["y"])
    t2 = runtime.run_scans(inst2, inputs, ["y"])
    assert [t.outputs for t in t1] == [t.outputs for t in t2]
```

```python
# tests/test_cli.py
from plcpy import cli

def test_cli_convert_st_to_python(tmp_path, capsys):
    f = tmp_path / "prog.st"
    f.write_text("PROGRAM Main\nVAR_OUTPUT\n y : INT;\nEND_VAR\n y := 1;\nEND_PROGRAM\n")
    rc = cli.main(["convert", "--from", "st", "--to", "python", str(f)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "class Main" in out
    assert "def scan(self)" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_semantic_equivalence.py tests/test_cli.py -v`
Expected: `test_semantic_equivalence` PASS (uses only existing modules);
`test_cli` FAIL with `ModuleNotFoundError: No module named 'plcpy.cli'`

(If the semantic test fails, fix the underlying converter before proceeding —
it is the acceptance gate for the whole skeleton.)

- [ ] **Step 3: Write the CLI and register the script**

```python
# src/plcpy/cli.py
from __future__ import annotations
import argparse
import sys
from .convert import convert


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plcpy")
    sub = parser.add_subparsers(dest="cmd", required=True)
    conv = sub.add_parser("convert", help="convert a source file between languages")
    conv.add_argument("file")
    conv.add_argument("--from", dest="from_lang", required=True)
    conv.add_argument("--to", dest="to_lang", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "convert":
        source = open(args.file, encoding="utf-8").read()
        result = convert(source, args.from_lang, args.to_lang)
        for d in result.diagnostics:
            print(f"{d.severity.value}: {d.message}", file=sys.stderr)
        if result.code is None:
            return 2
        print(result.code, end="")
        return 0
    return 1
```

Add to `pyproject.toml` under `[project]`:

```toml
[project.scripts]
plcpy = "plcpy.cli:main"
```

- [ ] **Step 4: Reinstall (for the new script) and run tests**

Run: `python -m pip install -e ".[test]" && python -m pytest tests/test_semantic_equivalence.py tests/test_cli.py -v`
Expected: PASS (both files)

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -v`
Expected: PASS (all tests across all task files)

- [ ] **Step 6: Commit**

```bash
git add src/plcpy/cli.py pyproject.toml tests/test_semantic_equivalence.py tests/test_cli.py
git commit -m "feat: add CLI and semantic-equivalence acceptance test"
```

---

## Self-Review

**Spec coverage (Phase 1 slice):**
- IR core → Task 2 ✓
- Plugin registry → Task 4 ✓
- ST frontend → Task 5 ✓; ST backend → Task 6 ✓
- Python backend (scan-cycle) → Task 7 ✓; Python frontend → Task 8 ✓
- Diagnostics-not-exceptions error model → Task 3 ✓ (used in Tasks 5 & 8)
- `convert()` facade → Task 9 ✓
- Scan-cycle runtime → Task 10 ✓
- Round-trip + semantic-equivalence testing → Tasks 6, 9, 11 ✓
- CLI (Phase 2 item, pulled forward as the user-facing proof) → Task 11 ✓
- Out of Phase 1 scope (deferred to later plans, per spec §8): IL, visual
  languages/PLCopen XML, FBD, SFC, vendor exports, VS Code extension/LSP.

**Type consistency:** `ParseResult` (Task 4) used by Tasks 5/8; `ConvertResult`
(Task 9); `ScanTrace` (Task 10) used by Task 11; `emit_python`/`emit_st`/
`parse_st`/`parse_python` names consistent across frontend/backend/convert.
Var-ref rendering: Python frontend yields plain names (`x`), so `python→st`
emits `y := x + 1` — reflected in Task 9's assertion and note.

**Placeholder scan:** no TBD/TODO; every code step contains full code.
