import plcpy
from plcpy import runtime

FBD_SRC = """PROGRAM Calc
VAR_INPUT
    a : INT;
    b : INT;
    c : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
NETWORK
    t1 := ADD(a, b)
    y := MUL(t1, c)
END_NETWORK
END_PROGRAM
"""

SFC_SRC = """PROGRAM Latch
VAR_INPUT
    go : BOOL;
    halt : BOOL;
END_VAR
VAR_OUTPUT
    active : BOOL;
END_VAR
INITIAL_STEP Idle
    ACTION
        active := FALSE;
    END_ACTION
    TRANSITION go TO Running
END_STEP
STEP Running
    ACTION
        active := TRUE;
    END_ACTION
    TRANSITION halt TO Idle
END_STEP
END_PROGRAM
"""


# ---- FBD ----

def test_fbd_to_python_executes():
    res = plcpy.convert(FBD_SRC, "fbd", "python")
    assert res.diagnostics == []
    Calc = runtime.load_pou(res.code, "Calc")
    inst = Calc()
    inst.a, inst.b, inst.c = 2, 3, 4
    inst.scan()
    assert inst.y == (2 + 3) * 4  # 20


def test_fbd_to_st_uses_operators():
    st = plcpy.convert(FBD_SRC, "fbd", "st").code
    assert "t1 := a + b" in st
    assert "y := t1 * c" in st


def test_st_arithmetic_to_fbd_blocks():
    st = """PROGRAM P
VAR_INPUT
    a : INT;
    b : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := a + b * 2;
END_PROGRAM
"""
    fbd = plcpy.convert(st, "st", "fbd").code
    assert "y := ADD(a, MUL(b, 2))" in fbd


def test_languages_includes_fbd_and_sfc():
    langs = plcpy.languages()
    assert langs["fbd"] == {"frontend": True, "backend": True}
    assert langs["sfc"] == {"frontend": True, "backend": True}


# ---- SFC ----

def test_sfc_to_python_state_machine():
    code = plcpy.convert(SFC_SRC, "sfc", "python").code
    Latch = runtime.load_pou(code, "Latch")
    inst = Latch()
    trace = runtime.run_scans(
        inst,
        inputs_per_cycle=[
            {"go": True, "halt": False},    # Idle action(active=F), then go -> Running
            {"go": False, "halt": False},   # Running: active=T
            {"go": False, "halt": True},    # Running: active=T, then halt -> Idle
            {"go": False, "halt": False},   # Idle: active=F
        ],
        output_names=["active"],
    )
    assert [t.outputs["active"] for t in trace] == [False, True, True, False]


def test_sfc_roundtrips_chart():
    out = plcpy.convert(SFC_SRC, "sfc", "sfc").code
    assert "INITIAL_STEP Idle" in out
    assert "STEP Running" in out
    assert "TRANSITION go TO Running" in out
    assert "TRANSITION halt TO Idle" in out
    # the synthetic state variable must not leak into the chart
    assert "_step" not in out


def test_sfc_to_st_is_executable_state_machine():
    # lowered as a boolean per-step state machine (supports parallel branches)
    st = plcpy.convert(SFC_SRC, "sfc", "st").code
    assert "_active_Idle" in st and "_active_Running" in st
