# plcpy — Bidirectional PLC ↔ Python Converter

Convert between Python and IEC 61131-3 PLC languages through a shared
Intermediate Representation (IR). Built as a **Parse → IR → Emit** pipeline with
a plugin registry, so any source language can be converted to any target
language without writing N×M converters — just N parsers and M emitters.

> **Status: all six languages + vendor exports + tooling working.** Python and
> all five IEC 61131-3 languages (ST, IL, LD, FBD, SFC) convert bidirectionally
> through a shared IR, with a scan-cycle runtime, an execution-flow visualizer,
> a CLI, and a VS Code extension. Vendor exports: Siemens SCL and Rockwell L5X.
> Each language is a working subset (see [Coverage](#coverage)); deepening any
> of them, plus PLCopen XML import and a live-diagnostics LSP, is future work.

## Install

```bash
python -m pip install -e ".[test]"
```

Requires Python 3.11+

## Usage

### Library

```python
import plcpy

st_source = """PROGRAM Main
VAR_INPUT
    x : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := x + 1;
    IF x > 10 THEN
        y := 99;
    END_IF;
END_PROGRAM
"""

result = plcpy.convert(st_source, from_lang="st", to_lang="python")
print(result.code)        # emitted scan-cycle Python class
print(result.diagnostics) # any unsupported-construct warnings

# Which directions are available:
print(plcpy.languages())
# python/st/il/ld/fbd/sfc: frontend+backend; scl/l5x: backend-only (vendor export)
```

Any frontend converts to any backend — e.g. Ladder → Python, SFC → ST,
ST → Siemens SCL, FBD → Rockwell L5X.

### Scan-cycle runtime

The emitted Python is a class with a `scan()` method (one PLC scan cycle). The
runtime drives **read inputs → scan → snapshot outputs** repeatedly:

```python
from plcpy import runtime

code = plcpy.convert(st_source, "st", "python").code
Main = runtime.load_pou(code, "Main")
trace = runtime.run_scans(
    Main(),
    inputs_per_cycle=[{"x": 1}, {"x": 20}],
    output_names=["y"],
)
print([t.outputs for t in trace])   # [{'y': 2}, {'y': 99}]
```

### CLI

```bash
plcpy convert --from st     --to python  program.st
plcpy convert --from python --to st      program.py
plcpy convert --from ld     --to scl     ladder.ld     # vendor export
# Side-by-side code + execution-flow diagram as a standalone HTML page:
plcpy visualize --from sfc --to python chart.sfc -o chart.html
```

## Visualizer

`plcpy.visualize.flow_graph(program)` builds a control-flow graph (and uses the
step/transition chart directly for SFC programs); `render_html(...)` emits a
self-contained HTML page with source + converted code side by side and an
inline-SVG execution-flow diagram. See `examples/latch.html` for a generated
sample, or use the `plcpy visualize` CLI command.

## VS Code extension

`vscode-extension/` contains an extension that drives the `plcpy` CLI to provide
**plcpy: Visualize** (synchronized side-by-side + flow-diagram webview that
refreshes on save) and **plcpy: Convert**. Build with `npm install && npm run
compile`, then press F5. See [`vscode-extension/README.md`](vscode-extension/README.md).

## Architecture

```
Frontend Parsers ──▶  IR (pivot)  ──▶ Backend Emitters
   (plugins)                              (plugins)
        ▲                                     │
        └──────────  Plugin Registry  ────────┘
```

- **`plcpy.ir`** — the IR dataclasses every language maps to/from.
- **`plcpy.registry`** — registers/looks up frontends and backends by language id.
- **`plcpy.frontends.*`** — `source text → IR` (ST via a `lark` grammar; Python via stdlib `ast`).
- **`plcpy.backends.*`** — `IR → source text` (ST; scan-cycle Python).
- **`plcpy.runtime`** — executes emitted POUs as scan cycles and records I/O traces.
- **`plcpy.convert`** — the `convert(source, from_lang, to_lang)` facade.
- **`plcpy.cli`** — command-line entry point.

Source-level problems are reported as `Diagnostic` objects (not exceptions);
unsupported constructs produce an `unsupported` diagnostic rather than silently
dropping data.

## Coverage

Common data: `BOOL`/`INT`/`REAL`; `VAR_INPUT`/`VAR_OUTPUT`/`VAR`; arithmetic
(`+ - * /`), logical (`AND OR NOT`), comparison (`= <> < <= > >=`); literals.

| Language | Frontend (→IR) | Backend (IR→) | Notes |
|---|---|---|---|
| ST  | ✅ | ✅ | assignment, `IF/ELSIF/ELSE`, `WHILE`, `FOR`, `CASE`; **`TON`/`TOF` timers**, **`ARRAY` + indexing**, **`STRUCT`/`ENUM`**, **user `FUNCTION_BLOCK`s**, nested `a.b.c`, `TIME` literals; IEC scalar-type aliases (DINT/WORD/SINT/LREAL/…) |
| Python | ✅ | ✅ | scan-cycle class with `scan()`; `if`/`while` recognised |
| IL  | ✅ | ✅ | accumulator ops; **`JMP`/`JMPC`/`JMPCN` + labels** (IF/WHILE lower to jumps and raise back to structured) |
| LD  | ✅ | ✅ | contacts/coils as boolean rungs (textual notation) |
| PLCopen XML | ✅ | ✅ | TC6 **ladder, FBD & SFC** graph import/export; diagram-layout preservation |
| FBD | ✅ | ✅ | block netlist (`out := FUNC(args)`) |
| SFC | ✅ | ✅ | steps/transitions, **parallel (simultaneous) branches**; lowers to an executable boolean-set state machine |
| SCL (Siemens) | — | ✅ | vendor export |
| L5X (Rockwell) | — | ✅ | vendor export (XML) |
| CODESYS | — | ✅ | vendor export (`.exp`) |
| TwinCAT (Beckhoff) | — | ✅ | vendor export (`.TcPOU` XML) |

**Live diagnostics:** `plcpy lsp` runs a dependency-free Language Server over
stdio; the VS Code extension starts it automatically for PLC files, surfacing
parse errors and unsupported-construct warnings as you type.

## Roadmap (done / next)

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | IR + registry + ST↔Python + scan-cycle runtime + CLI | ✅ |
| 2 | Instruction List (IL) ↔ Python; widen ST (CASE, FOR) | ✅ |
| 3 | Ladder Diagram (LD) | ✅ |
| 4 | Function Block Diagram (FBD), Sequential Function Chart (SFC) | ✅ |
| 5 | Vendor export plugins (Siemens SCL, Rockwell L5X) | ✅ |
| 6 | Execution-flow visualizer + VS Code extension | ✅ |
| 7 | PLCopen XML ladder import/export; CODESYS + TwinCAT exports; IEC type aliases; live-diagnostics LSP | ✅ |
| 8 | `TON`/`TOF` timers (scan-time runtime, FB instances/calls, member access, `TIME` literals); `ARRAY` declaration + indexing | ✅ |
| 9 | `STRUCT`/`ENUM` & user `FUNCTION_BLOCK`s + nested member access; IL jumps/labels; SFC parallel branches; PLCopen XML for FBD/SFC + diagram-layout preservation | ✅ |

Every feature from the original design — all five IEC 61131-3 languages, PLCopen
XML interchange, vendor exports, the runtime, the visualizer, the VS Code
extension, and the live LSP — is implemented and tested (97 tests).

Design spec: [`docs/superpowers/specs/2026-06-19-plc-python-converter-design.md`](docs/superpowers/specs/2026-06-19-plc-python-converter-design.md).

## Development

```bash
python -m pytest        # run the full test suite
```

Each language is a plugin: add a frontend by calling
`registry.register_frontend(lang, fn)` and a backend with
`registry.register_backend(lang, fn)`. Frontends return a `ParseResult`
(`program` + `diagnostics`); backends take a `Program` and return source text.
