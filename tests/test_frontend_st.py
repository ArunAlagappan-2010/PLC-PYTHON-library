from plcpy.frontends import st
from plcpy import ir

SRC = """
PROGRAM Main
VAR_INPUT
    x : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := x + 1;
    IF x > 0 THEN
        y := 0;
    END_IF;
END_PROGRAM
"""


def test_parse_program_structure():
    res = st.parse_st(SRC)
    assert res.diagnostics == []
    p = res.program
    assert p.name == "Main"
    names = {v.name: v.scope for v in p.vars}
    assert names["x"] is ir.VarScope.INPUT
    assert names["y"] is ir.VarScope.OUTPUT
    assert isinstance(p.body[0], ir.Assign)
    assert p.body[0].target == "y"
    assert isinstance(p.body[1], ir.If)
    assert p.body[1].cond.op == ">"


def test_unsupported_construct_reports_diagnostic():
    res = st.parse_st("PROGRAM P\n VAR z : WORD; END_VAR\nEND_PROGRAM\n")
    assert any(d.severity.name == "UNSUPPORTED" for d in res.diagnostics)
