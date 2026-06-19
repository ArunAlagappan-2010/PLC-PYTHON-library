import plcpy
from plcpy import runtime

# Motor seal-in: run latches once start pressed, drops when stop pressed.
LD_SRC = """PROGRAM Motor
VAR_INPUT
    start : BOOL;
    stop : BOOL;
END_VAR
VAR_OUTPUT
    run : BOOL;
END_VAR
RUNG
    --[ start | run ]--[/ stop ]--( run )
END_RUNG
END_PROGRAM
"""


def test_ld_to_python_seal_in_behaviour():
    code = plcpy.convert(LD_SRC, "ld", "python").code
    Motor = runtime.load_pou(code, "Motor")
    inst = Motor()
    # press start -> run latches
    trace = runtime.run_scans(
        inst,
        inputs_per_cycle=[
            {"start": True, "stop": False},   # run -> True
            {"start": False, "stop": False},  # seal-in keeps run True
            {"start": False, "stop": True},   # stop -> run False
            {"start": False, "stop": False},  # stays False
        ],
        output_names=["run"],
    )
    assert [t.outputs["run"] for t in trace] == [True, True, False, False]


def test_ld_to_st_produces_boolean_logic():
    st = plcpy.convert(LD_SRC, "ld", "st").code
    assert "run := (start OR run) AND NOT stop" in st


def test_ld_roundtrips():
    out = plcpy.convert(LD_SRC, "ld", "ld").code
    assert "--[ start | run ]--[/ stop ]--( run )" in out


def test_st_boolean_to_ld_rung():
    st = """PROGRAM P
VAR_INPUT
    a : BOOL;
    b : BOOL;
END_VAR
VAR_OUTPUT
    y : BOOL;
END_VAR
    y := a AND NOT b;
END_PROGRAM
"""
    ld = plcpy.convert(st, "st", "ld").code
    assert "--[ a ]--[/ b ]--( y )" in ld


def test_languages_includes_ld():
    assert plcpy.languages()["ld"] == {"frontend": True, "backend": True}
