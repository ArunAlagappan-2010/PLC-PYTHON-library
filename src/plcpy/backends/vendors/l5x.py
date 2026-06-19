"""Rockwell L5X export (IR -> L5X XML).

Produces a minimal RSLogix 5000 / Studio 5000 L5X document with the program
body as a Structured Text routine and one tag per variable. Rockwell type names
(BOOL/DINT/REAL) differ from IEC, so they are mapped here. Built with
ElementTree so the output is always well-formed XML.
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from ... import ir
from ...registry import register_backend
from ..st import _stmts

_L5X_TYPE = {ir.DataType.BOOL: "BOOL", ir.DataType.INT: "DINT", ir.DataType.REAL: "REAL"}


def emit_l5x(program: ir.Program) -> str:
    root = ET.Element("RSLogix5000Content", SchemaRevision="1.0", TargetType="Program")
    controller = ET.SubElement(root, "Controller", Name=program.name)
    programs = ET.SubElement(controller, "Programs")
    prog = ET.SubElement(programs, "Program", Name=program.name)

    tags = ET.SubElement(prog, "Tags")
    for v in program.vars:
        ET.SubElement(tags, "Tag", Name=v.name, DataType=_L5X_TYPE[v.type])

    routines = ET.SubElement(prog, "Routines")
    routine = ET.SubElement(routines, "Routine", Name="MainRoutine", Type="ST")
    st_content = ET.SubElement(routine, "STContent")
    for n, line in enumerate(_stmts(program.body, 0)):
        ln = ET.SubElement(st_content, "Line", Number=str(n))
        ln.text = line.strip()

    ET.indent(root, space="  ")
    xml = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n"


register_backend("l5x", emit_l5x)
