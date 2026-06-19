import plcpy
from plcpy import ir, runtime

ST_SRC = """PROGRAM Counter
VAR_INPUT
    n : INT;
END_VAR
VAR_OUTPUT
    total : INT;
END_VAR
VAR
    i : INT;
END_VAR
    total := 0;
    i := 0;
    WHILE i < n DO
        total := total + i;
        i := i + 1;
    END_WHILE;
END_PROGRAM
"""


def test_st_frontend_parses_while():
    p = plcpy.convert(ST_SRC, "st", "python")
    assert p.diagnostics == []
    # find the While node in the parsed program via the ST frontend directly
    from plcpy.frontends import st as st_fe
    prog = st_fe.parse_st(ST_SRC).program
    assert any(isinstance(s, ir.While) for s in prog.body)


def test_st_to_python_while_executes():
    code = plcpy.convert(ST_SRC, "st", "python").code
    assert "while" in code
    Counter = runtime.load_pou(code, "Counter")
    inst = Counter()
    inst.n = 5
    inst.scan()
    assert inst.total == 0 + 1 + 2 + 3 + 4  # == 10


def test_while_roundtrip_semantics():
    py1 = plcpy.convert(ST_SRC, "st", "python").code
    st2 = plcpy.convert(py1, "python", "st").code
    assert "WHILE" in st2 and "END_WHILE" in st2
    py2 = plcpy.convert(st2, "st", "python").code
    inst1 = runtime.load_pou(py1, "Counter")()
    inst2 = runtime.load_pou(py2, "Counter")()
    inputs = [{"n": k} for k in range(0, 8)]
    t1 = runtime.run_scans(inst1, inputs, ["total"])
    t2 = runtime.run_scans(inst2, inputs, ["total"])
    assert [t.outputs for t in t1] == [t.outputs for t in t2]
