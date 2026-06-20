import plcpy
from plcpy.frontends import st as st_fe
from plcpy import ir, runtime

SRC = """TYPE
    Color : (Red, Green, Blue);
END_TYPE
PROGRAM P
VAR_INPUT
    sel : INT;
END_VAR
VAR_OUTPUT
    out : INT;
END_VAR
    out := Color.Green;
END_PROGRAM
"""


def test_enum_member_resolves_to_int():
    prog = st_fe.parse_st(SRC).program
    assert any(isinstance(t, ir.EnumDef) and t.name == "Color" for t in prog.types)
    assert isinstance(prog.body[0].value, ir.Literal)
    assert prog.body[0].value.value == 1


def test_enum_executes():
    code = plcpy.convert(SRC, "st", "python").code
    P = runtime.load_pou(code, "P")
    inst = P(); inst.scan()
    assert inst.out == 1


def test_enum_roundtrips_to_st():
    out = plcpy.convert(SRC, "st", "st").code
    assert "TYPE" in out and "Color : (Red, Green, Blue);" in out and "END_TYPE" in out
