import plcpy
from plcpy import runtime

SRC = """FUNCTION_BLOCK Counter
VAR_INPUT
    step : INT;
END_VAR
VAR_OUTPUT
    count : INT;
END_VAR
    count := count + step;
END_FUNCTION_BLOCK
PROGRAM P
VAR_OUTPUT
    total : INT;
END_VAR
VAR
    c : Counter;
END_VAR
    c(step := 2);
    total := c.count;
END_PROGRAM
"""


def test_user_fb_accumulates_across_scans():
    code = plcpy.convert(SRC, "st", "python").code
    P = runtime.load_pou(code, "P")
    inst = P()
    trace = runtime.run_scans(inst, [{}, {}, {}], ["total"])
    assert [t.outputs["total"] for t in trace] == [2, 4, 6]


def test_user_fb_roundtrips_to_st():
    out = plcpy.convert(SRC, "st", "st").code
    assert "FUNCTION_BLOCK Counter" in out
    assert "count := count + step;" in out
    assert "c(step := 2);" in out
