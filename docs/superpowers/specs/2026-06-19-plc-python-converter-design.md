# PLC ↔ Python Bidirectional Converter — Design

**Date:** 2026-06-19
**Status:** Approved (architecture), pending implementation plan

## 1. Purpose

A Python library that converts between Python and all five IEC 61131-3 PLC
languages (Structured Text, Ladder Diagram, Function Block Diagram, Instruction
List, Sequential Function Chart), in **both directions**, with round-trip
fidelity. Plus a VS Code extension providing (a) synchronized side-by-side
code views and (b) an execution/flow diagram visualizer.

Non-negotiables:
- Bidirectional and symmetric — Python→PLC and PLC→Python are equal citizens.
- Wide and extensible — new languages and vendor dialects added as plugins.
- Generic IEC 61131-3 core output, with vendor export plugins layered on top.
- Python runtime model = scan-cycle simulation (read inputs → run logic →
  write outputs → repeat).

## 2. Architecture (Option B — Layered Pipeline with Plugin Registry)

Three layers: **Parse → IR → Emit**, wired through a plugin registry.

```
Frontend Parsers ──▶ IR (pivot) ──▶ Backend Emitters
   (plugins)                            (plugins)
        ▲                                   │
        └──────── Plugin Registry ──────────┘
```

- Every language (ST, LD, FBD, IL, SFC, **and Python**) registers a parser
  and an emitter. Conversion = `source_parser → IR → target_emitter`. No N×M
  converters; N parsers + M emitters.
- Vendor exports (CODESYS, TIA Portal SCL, Beckhoff TwinCAT, Rockwell L5X) are
  **emitter-only** plugins that consume the same IR.
- The VS Code extension is a separate package talking to the library through a
  Language Server (LSP). The library has no editor dependency.
- The runtime (scan-cycle simulator) executes IR or emitted Python.

## 3. Intermediate Representation (IR)

The IR is the heart of the system and must encode both textual and graphical
program structure.

**Core constructs (text-friendly):**
- `Program`, `FunctionBlock`, `Function`, `Method`
- `VariableDeclaration` (name, type, scope: INPUT/OUTPUT/IN_OUT/LOCAL/GLOBAL/
  TEMP, initial value, address e.g. `%IX0.0`)
- Types: BOOL, INT, DINT, REAL, LREAL, TIME, STRING, arrays, structs, enums,
  derived types
- Statements: assignment, if/elsif/else, case, for, while, repeat, exit,
  return, function-block invocation
- Expressions: literals, var refs, binary/unary ops, function calls

**Graph constructs (visual languages):**
- `Network` / `Rung` — a connected graph of `Node`s and `Edge`s
- Node kinds: contact (NO/NC), coil, function block instance, FBD block,
  connector, junction
- Edges carry signal flow and power-rail topology
- SFC: `Step`, `Transition`, `Action`, `Branch` (divergence/convergence),
  with step-action associations and transition conditions

**Bridging principle:** LD/FBD/SFC networks lower to the same statement/
expression IR for execution semantics, while retaining a graphical-topology
side-table so they can be re-emitted as diagrams (round-trip fidelity). The IR
node carries optional `layout` metadata (coordinates, wire routing) preserved
across round-trips when present, regenerated when absent.

## 4. Components

| Component | Responsibility |
|---|---|
| `plcpy.ir` | IR dataclasses + validation + visitor base |
| `plcpy.registry` | Plugin registration/discovery (entry points + decorators) |
| `plcpy.frontends.st` | ST parser → IR |
| `plcpy.frontends.il` | IL parser → IR |
| `plcpy.frontends.ld` / `.fbd` / `.sfc` | Visual-language parsers (from PLCopen XML) → IR |
| `plcpy.frontends.python` | Python AST → IR |
| `plcpy.backends.st` / `.il` / `.ld` / `.fbd` / `.sfc` | IR → language text/XML |
| `plcpy.backends.python` | IR → scan-cycle Python module |
| `plcpy.backends.vendors.*` | IR → vendor-specific export |
| `plcpy.runtime` | Scan-cycle simulator (POU instances, I/O image, timers) |
| `plcpy.convert` | High-level `convert(src, from_lang, to_lang)` facade |
| `plcpy.lsp` | Language Server exposing convert/diagnostics/diagram |
| `vscode-plcpy` | VS Code extension client (side-by-side + diagram webview) |

## 5. Data Flow

1. **Convert:** `convert(text, from="st", to="python")` → registry resolves ST
   frontend → IR → Python backend → string. Diagnostics collected throughout.
2. **Interchange format:** visual languages use **PLCopen XML** as the canonical
   on-disk representation (industry standard, vendor-neutral), parsed into the
   graph IR.
3. **Round-trip:** `X → IR → X` must be idempotent for supported subsets;
   golden round-trip tests enforce this.
4. **Runtime:** Python backend emits POU classes with an explicit `scan()`
   method; the simulator drives `read_inputs → scan → write_outputs` loops.

## 6. Error Handling

- **Diagnostics, not exceptions, for source errors.** Parsers produce a
  `Diagnostic` list (severity, position, message, code) so the LSP can surface
  squiggles. A parse failure yields a partial IR + diagnostics where possible.
- **Unsupported constructs** produce a `Diagnostic` of severity `unsupported`
  with a clear "not yet implemented: X" message rather than silent data loss.
- **Library exceptions** (`PlcPyError` hierarchy) are reserved for programmer
  errors (unknown language, invalid registry use).
- **Lossy conversion warnings:** when an emitter cannot represent an IR
  construct losslessly (e.g. layout-free LD), it emits a warning diagnostic.

## 7. Testing Strategy

- **Unit tests** per parser/emitter on small fixtures.
- **Golden tests:** fixture pairs (`*.st` ↔ expected `*.py`) checked both ways.
- **Round-trip property tests:** `parse → emit → parse` yields equivalent IR;
  use hypothesis for generated programs on supported subsets.
- **Semantic equivalence tests:** run the same logic through the scan-cycle
  simulator from both the original and converted form; assert identical I/O
  traces over a scan sequence.
- **Conformance corpus:** a growing set of real-world IEC 61131-3 examples.

## 8. Scope & Phasing (decomposition)

This is a large system; build as a walking skeleton then widen:

- **Phase 1 (skeleton):** IR core + registry + ST↔Python + scan-cycle runtime +
  `convert()` facade + tests. Proves the pivot architecture end-to-end.
- **Phase 2:** IL↔Python; expand ST coverage; CLI.
- **Phase 3:** Visual languages via PLCopen XML (LD first), graph IR.
- **Phase 4:** FBD, SFC.
- **Phase 5:** Vendor export plugins.
- **Phase 6:** VS Code extension (LSP + side-by-side + diagram webview).

Each phase is independently shippable and testable.

## 9. Tech Choices

- Python 3.11+, `dataclasses` for IR, `lark` for ST/IL grammars (pure-Python,
  no build step; ANTLR reserved as a fallback if performance demands it).
- `lxml` for PLCopen XML.
- `pytest` + `hypothesis` for tests.
- VS Code extension in TypeScript using `vscode-languageclient`; LSP server in
  Python via `pygls`.
