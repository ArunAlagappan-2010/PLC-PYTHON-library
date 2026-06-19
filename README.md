# plcpy — Bidirectional PLC ↔ Python Converter

Convert between Python and IEC 61131-3 PLC languages through a shared
Intermediate Representation (IR). Built as a **Parse → IR → Emit** pipeline with
a plugin registry, so any source language can be converted to any target
language without writing N×M converters — just N parsers and M emitters.

> **Status: Phase 1 (walking skeleton).** Structured Text (ST) ↔ Python is fully
> working, with a scan-cycle runtime simulator and a CLI. The remaining IEC
> 61131-3 languages (IL, LD, FBD, SFC), vendor export plugins, and the VS Code
> extension are on the roadmap — see [Roadmap](#roadmap).

## Install

```bash
python -m pip install -e ".[test]"
```

Requires Python 3.11+.

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
# {'python': {'frontend': True, 'backend': True},
#  'st':     {'frontend': True, 'backend': True}}
```

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
```

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

## Supported ST subset (Phase 1)

`PROGRAM` blocks; `VAR_INPUT` / `VAR_OUTPUT` / `VAR` of `BOOL`/`INT`/`REAL`;
`:=` assignment; `IF/ELSIF/ELSE/END_IF`; `WHILE/DO/END_WHILE`; arithmetic
(`+ - * /`), logical (`AND OR NOT`) and comparison (`= <> < <= > >=`) operators;
parenthesised expressions; integer/real/boolean literals.

## Roadmap

| Phase | Scope |
|-------|-------|
| 1 ✅ | IR + registry + ST↔Python + scan-cycle runtime + CLI |
| 2 | Instruction List (IL) ↔ Python; widen ST coverage (CASE, FOR) |
| 3 | Visual languages via PLCopen XML — Ladder Diagram first (graph IR) |
| 4 | Function Block Diagram (FBD), Sequential Function Chart (SFC) |
| 5 | Vendor export plugins (CODESYS, TIA Portal SCL, TwinCAT, Rockwell L5X) |
| 6 | VS Code extension — synchronized side-by-side views + execution-flow visualizer |

Design spec: [`docs/superpowers/specs/2026-06-19-plc-python-converter-design.md`](docs/superpowers/specs/2026-06-19-plc-python-converter-design.md).

## Development

```bash
python -m pytest        # run the full test suite
```

Each language is a plugin: add a frontend by calling
`registry.register_frontend(lang, fn)` and a backend with
`registry.register_backend(lang, fn)`. Frontends return a `ParseResult`
(`program` + `diagnostics`); backends take a `Program` and return source text.
