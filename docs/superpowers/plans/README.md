# Implementation Plans

Build-ready, TDD-structured plans. Execute with `superpowers:executing-plans`
(inline) or `superpowers:subagent-driven-development` (one subagent per task).
Each plan is independent and produces working, tested software on its own.

## Completed (already built)

- [`2026-06-19-phase1-walking-skeleton.md`](2026-06-19-phase1-walking-skeleton.md) — ✅ IR + registry + ST↔Python + runtime + CLI.

## Deep features — ✅ all built

| Plan | Builds | Status |
|---|---|---|
| [`2026-06-20-structs-enums-fbs.md`](2026-06-20-structs-enums-fbs.md) | `STRUCT`, `ENUM`, user `FUNCTION_BLOCK`s, nested member access `a.b.c` (read + write) | ✅ |
| [`2026-06-20-il-jumps-labels.md`](2026-06-20-il-jumps-labels.md) | IL `JMP`/`JMPC`/`JMPCN` + labels; structured⇄goto lowering & raising; goto fallback interpreter | ✅ |
| [`2026-06-20-sfc-parallel-branches.md`](2026-06-20-sfc-parallel-branches.md) | SFC simultaneous (parallel) divergence/convergence via boolean-set lowering | ✅ |
| [`2026-06-20-plcopen-fbd-sfc.md`](2026-06-20-plcopen-fbd-sfc.md) | PLCopen XML for FBD & SFC bodies + diagram-layout preservation | ✅ |

All four implemented in one session (97 tests). Implementations track the plans
closely; minor deviations: the SFC lowering became boolean-set (per its plan),
and timer-vs-user-FB call dispatch is keyed on instance type.

Each plan starts with a `## Global Constraints` block and ends with a
`## Self-Review`. Run `python -m pytest -q` after every task — the ST grammar is
shared, so regressions surface immediately.
