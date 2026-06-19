from plcpy.backends import st as st_backend
from plcpy.frontends import st as st_frontend

SRC = """PROGRAM Main
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


def test_roundtrip_st_to_st_is_stable():
    prog = st_frontend.parse_st(SRC).program
    out = st_backend.emit_st(prog)
    prog2 = st_frontend.parse_st(out).program
    assert prog2.name == prog.name
    assert [v.name for v in prog2.vars] == [v.name for v in prog.vars]
    assert len(prog2.body) == len(prog.body)
    assert "y := x + 1" in out
    assert "IF x > 0 THEN" in out
