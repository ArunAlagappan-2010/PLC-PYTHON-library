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
END_PROGRAM
"""


def test_run_scans_produces_trace():
    code = plcpy.convert(ST_SRC, "st", "python").code
    Main = runtime.load_pou(code, "Main")
    inst = Main()
    trace = runtime.run_scans(
        inst,
        inputs_per_cycle=[{"x": 1}, {"x": 10}, {"x": 100}],
        output_names=["y"],
    )
    assert [t.outputs["y"] for t in trace] == [2, 11, 101]
    assert [t.cycle for t in trace] == [0, 1, 2]
