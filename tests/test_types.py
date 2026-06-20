import plcpy
from plcpy.frontends import st as st_fe
from plcpy import ir

SRC = """PROGRAM P
VAR_INPUT
    a : DINT;
    b : WORD;
    c : SINT;
END_VAR
VAR_OUTPUT
    y : LREAL;
    flag : BOOL;
END_VAR
    y := a;
END_PROGRAM
"""


def test_iec_scalar_aliases_canonicalise():
    prog = st_fe.parse_st(SRC).program
    types = {v.name: v.type for v in prog.vars}
    assert types["a"] is ir.DataType.INT     # DINT  -> INT
    assert types["b"] is ir.DataType.INT     # WORD  -> INT
    assert types["c"] is ir.DataType.INT     # SINT  -> INT
    assert types["y"] is ir.DataType.REAL    # LREAL -> REAL
    assert types["flag"] is ir.DataType.BOOL


def test_aliases_parse_without_diagnostics():
    res = plcpy.convert(SRC, "st", "python")
    assert res.diagnostics == []
    assert res.code is not None
