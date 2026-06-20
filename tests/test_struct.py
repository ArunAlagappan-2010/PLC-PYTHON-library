import plcpy
from plcpy.frontends import st as st_fe
from plcpy import ir, runtime

SRC = """TYPE
    Motor : STRUCT
        speed : INT;
        running : BOOL;
    END_STRUCT;
END_TYPE
PROGRAM P
VAR_INPUT
    cmd : INT;
END_VAR
VAR_OUTPUT
    rpm : INT;
END_VAR
VAR
    m : Motor;
END_VAR
    m.speed := cmd;
    m.running := cmd > 0;
    rpm := m.speed;
END_PROGRAM
"""


def test_struct_def_and_member_write():
    prog = st_fe.parse_st(SRC).program
    assert any(isinstance(t, ir.StructDef) and t.name == "Motor" for t in prog.types)
    m = next(v for v in prog.vars if v.name == "m")
    assert m.struct_type == "Motor"
    assert isinstance(prog.body[0], ir.MemberAssign)
    assert isinstance(prog.body[0].target, ir.Member)


def test_struct_executes():
    code = plcpy.convert(SRC, "st", "python").code
    P = runtime.load_pou(code, "P")
    inst = P(); inst.cmd = 42; inst.scan()
    assert inst.rpm == 42


def test_struct_roundtrips_to_st():
    out = plcpy.convert(SRC, "st", "st").code
    assert "Motor : STRUCT" in out
    assert "speed : INT;" in out
    assert "m : Motor;" in out
    assert "m.speed := cmd;" in out
