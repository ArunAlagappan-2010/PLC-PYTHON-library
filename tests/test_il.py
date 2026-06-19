import plcpy
from plcpy import runtime

IL_SRC = """PROGRAM Main
VAR_INPUT
    x : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    LD x
    ADD 1
    ST y
END_PROGRAM
"""


def test_il_to_python_executes():
    res = plcpy.convert(IL_SRC, "il", "python")
    assert res.diagnostics == []
    Main = runtime.load_pou(res.code, "Main")
    inst = Main()
    inst.x = 41
    inst.scan()
    assert inst.y == 42


def test_il_roundtrips_through_ir():
    # IL -> IR -> IL must reproduce the same instruction structure
    out = plcpy.convert(IL_SRC, "il", "il").code
    assert "LD x" in out
    assert "ADD 1" in out
    assert "ST y" in out


def test_st_to_il_linearizes_expression():
    st = """PROGRAM P
VAR_OUTPUT
    y : INT;
END_VAR
VAR_INPUT
    a : INT;
    b : INT;
END_VAR
    y := a + b;
END_PROGRAM
"""
    il = plcpy.convert(st, "st", "il").code
    assert "LD a" in il
    assert "ADD b" in il
    assert "ST y" in il


def test_il_control_flow_is_marked_unsupported_in_backend():
    st = """PROGRAM P
VAR_OUTPUT
    y : INT;
END_VAR
VAR_INPUT
    x : INT;
END_VAR
    IF x > 0 THEN
        y := 1;
    END_IF;
END_PROGRAM
"""
    il = plcpy.convert(st, "st", "il").code
    assert "unsupported in IL: IF" in il


def test_languages_includes_il():
    langs = plcpy.languages()
    assert langs["il"] == {"frontend": True, "backend": True}
