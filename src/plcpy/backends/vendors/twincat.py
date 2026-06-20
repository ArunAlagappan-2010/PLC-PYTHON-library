"""Beckhoff TwinCAT export (IR -> .TcPOU XML).

TwinCAT stores POUs as XML with a CDATA <Declaration> (the PROGRAM header and
VAR sections) and a CDATA <Implementation><ST> body. The ST text reuses the
generic ST renderer. Built as a string with CDATA sections (no escaping needed
inside CDATA).
"""
from __future__ import annotations
from ... import ir
from ...registry import register_backend
from ..st import _stmts

_SCOPE_KW = {ir.VarScope.INPUT: "VAR_INPUT", ir.VarScope.OUTPUT: "VAR_OUTPUT",
             ir.VarScope.LOCAL: "VAR"}


def _declaration(program: ir.Program) -> str:
    lines = [f"PROGRAM {program.name}"]
    for scope in (ir.VarScope.INPUT, ir.VarScope.OUTPUT, ir.VarScope.LOCAL):
        decls = [v for v in program.vars if v.scope is scope]
        if not decls:
            continue
        lines.append(_SCOPE_KW[scope])
        for v in decls:
            lines.append(f"    {v.name} : {v.type.value};")
        lines.append("END_VAR")
    return "\n".join(lines)


def emit_twincat(program: ir.Program) -> str:
    decl = _declaration(program)
    impl = "\n".join(_stmts(program.body, 0))
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.0" ProductVersion="3.1.4024.0">\n'
        f'  <POU Name="{program.name}" SpecialFunc="None">\n'
        f'    <Declaration><![CDATA[{decl}]]></Declaration>\n'
        '    <Implementation>\n'
        f'      <ST><![CDATA[{impl}]]></ST>\n'
        '    </Implementation>\n'
        '  </POU>\n'
        '</TcPlcObject>\n'
    )


register_backend("twincat", emit_twincat)
