# Implementation Plans

Build-ready, TDD-structured plans. Execute with `superpowers:executing-plans`
(inline) or `superpowers:subagent-driven-development` (one subagent per task).
Each plan is independent and produces working, tested software on its own.

## Completed (already built)

- [`2026-06-19-phase1-walking-skeleton.md`](2026-06-19-phase1-walking-skeleton.md) — ✅ IR + registry + ST↔Python + runtime + CLI.

## Remaining deep features — ready to build

| Plan | Builds | Difficulty |
|---|---|---|
| [`2026-06-20-structs-enums-fbs.md`](2026-06-20-structs-enums-fbs.md) | `STRUCT`, `ENUM`, user `FUNCTION_BLOCK`s, nested member access `a.b.c` (read + write) | Large |
| [`2026-06-20-il-jumps-labels.md`](2026-06-20-il-jumps-labels.md) | IL `JMP`/`JMPC`/`JMPCN` + labels; structured⇄goto lowering & raising; goto fallback interpreter | Medium |
| [`2026-06-20-sfc-parallel-branches.md`](2026-06-20-sfc-parallel-branches.md) | SFC simultaneous (parallel) divergence/convergence via boolean-set lowering | Medium |
| [`2026-06-20-plcopen-fbd-sfc.md`](2026-06-20-plcopen-fbd-sfc.md) | PLCopen XML for FBD & SFC bodies + diagram-layout preservation | Medium |

**Suggested order:** STRUCT/ENUM/FBs first (most generally useful and unblocks
richer programs), then PLCopen FBD/SFC, then SFC parallel, then IL jumps.

Each plan starts with a `## Global Constraints` block and ends with a
`## Self-Review`. Run `python -m pytest -q` after every task — the ST grammar is
shared, so regressions surface immediately.
