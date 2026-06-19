import plcpy
from plcpy import runtime

ST_SRC = """PROGRAM Main
VAR_INPUT
    x : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := x + 1;
    IF x > 5 THEN
        y := 0;
    END_IF;
END_PROGRAM
"""


def test_st_and_roundtripped_st_behave_identically():
    # ST -> Python -> run
    py1 = plcpy.convert(ST_SRC, "st", "python").code
    inst1 = runtime.load_pou(py1, "Main")()
    # ST -> Python -> ST -> Python -> run
    st2 = plcpy.convert(py1, "python", "st").code
    py2 = plcpy.convert(st2, "st", "python").code
    inst2 = runtime.load_pou(py2, "Main")()
    inputs = [{"x": i} for i in range(-3, 10)]
    t1 = runtime.run_scans(inst1, inputs, ["y"])
    t2 = runtime.run_scans(inst2, inputs, ["y"])
    assert [t.outputs for t in t1] == [t.outputs for t in t2]
