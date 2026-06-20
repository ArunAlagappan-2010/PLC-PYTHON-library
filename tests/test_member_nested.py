from plcpy.frontends import st as st_fe
from plcpy import ir


def test_two_level_member_access_parses_nested():
    src = (
        "PROGRAM P\nVAR_OUTPUT\n s : INT;\nEND_VAR\n"
        "VAR\n a : SomeFB;\nEND_VAR\n"
        " s := a.cfg.speed;\n"
        "END_PROGRAM\n"
    )
    prog = st_fe.parse_st(src).program
    val = prog.body[0].value
    assert isinstance(val, ir.Member) and val.member == "speed"
    assert isinstance(val.base, ir.Member) and val.base.member == "cfg"
    assert isinstance(val.base.base, ir.VarRef) and val.base.base.name == "a"
