# plcpy — VS Code extension

Convert between Python and IEC 61131-3 PLC languages (ST, IL, LD, FBD, SFC) and
visualize them with synchronized side-by-side code views and an execution-flow
diagram.

## Features

- **plcpy: Visualize (side-by-side + flow diagram)** — opens a panel beside your
  editor showing the source, the converted code, and an execution-flow diagram.
  The panel re-renders automatically when you save the file (synchronized view).
- **plcpy: Convert to another language** — pick a target language; the result
  opens in a new editor pane.

Supported source types by extension: `.st`, `.il`, `.ld`, `.fbd`, `.sfc`, `.py`.
Targets include all of those plus vendor exports `scl` (Siemens) and `l5x`
(Rockwell).

## Requirements

The extension drives the `plcpy` command-line tool. Install the Python library
so `plcpy` is on your PATH:

```bash
pip install -e /path/to/PLC-Py19062026
```

If `plcpy` is not on PATH, set `plcpy.command` to an absolute path in Settings.

## Build & run (from source)

```bash
cd vscode-extension
npm install
npm run compile
```

Then press **F5** in VS Code to launch an Extension Development Host, open a
`.st`/`.sfc`/… file, and run **plcpy: Visualize** from the Command Palette.

## Settings

| Setting | Default | Description |
|---|---|---|
| `plcpy.command` | `plcpy` | CLI command (name on PATH or absolute path). |
| `plcpy.defaultTarget` | `python` | Default target language for the side-by-side pane. |

## Roadmap

- Language Server (pygls) for live diagnostics and hover as you type.
- Interactive (clickable) ladder/SFC diagrams.
