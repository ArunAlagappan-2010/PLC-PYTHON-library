"""Shared helpers for the line-oriented text frontends (IL, LD)."""
from __future__ import annotations
import re
from .. import ir
from ..diagnostics import Diagnostic, Severity

# IEC 61131-3 elementary types, mapped onto the three types the IR models.
# Width/sign aliases canonicalise to INT/REAL on import (documented lossy step).
TYPES = {
    "BOOL": ir.DataType.BOOL,
    "INT": ir.DataType.INT, "SINT": ir.DataType.INT, "DINT": ir.DataType.INT,
    "LINT": ir.DataType.INT, "USINT": ir.DataType.INT, "UINT": ir.DataType.INT,
    "UDINT": ir.DataType.INT, "ULINT": ir.DataType.INT,
    "BYTE": ir.DataType.INT, "WORD": ir.DataType.INT, "DWORD": ir.DataType.INT,
    "LWORD": ir.DataType.INT,
    "REAL": ir.DataType.REAL, "LREAL": ir.DataType.REAL,
}
SCOPE = {"VAR_INPUT": ir.VarScope.INPUT, "VAR_OUTPUT": ir.VarScope.OUTPUT,
         "VAR": ir.VarScope.LOCAL}

_DECL = re.compile(r"([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)")


def parse_var_section(kw: str, lines: list[str], idx: int,
                      vars_: list[ir.VarDecl], diagnostics: list[Diagnostic]) -> int:
    """Consume a VAR_* ... END_VAR block starting at `idx`; return the new idx."""
    scope = SCOPE[kw]
    while idx < len(lines):
        decl = lines[idx].strip().rstrip(";").strip()
        idx += 1
        if not decl:
            continue
        if decl.upper() == "END_VAR":
            break
        m = _DECL.match(decl)
        if not m:
            continue
        vname, tname = m.group(1), m.group(2)
        dt = TYPES.get(tname.upper())
        if dt is None:
            diagnostics.append(Diagnostic(f"unsupported type {tname!r}",
                                          Severity.UNSUPPORTED, line=idx, code="VAR"))
            dt = ir.DataType.INT
        vars_.append(ir.VarDecl(vname, dt, scope))
    return idx
