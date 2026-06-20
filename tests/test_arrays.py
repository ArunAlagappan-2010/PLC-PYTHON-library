import plcpy
from plcpy import ir, runtime
from plcpy.frontends import st as st_fe

ARR_SRC = """PROGRAM Acc
VAR_INPUT
    idx : INT;
    val : INT;
END_VAR
VAR_OUTPUT
    total : INT;
END_VAR
VAR
    buf : ARRAY[0..3] OF INT;
    i : INT;
END_VAR
    buf[idx] := val;
    total := 0;
    FOR i := 0 TO 3 DO
        total := total + buf[i];
    END_FOR;
END_PROGRAM
"""


def test_array_declaration_and_index_parse():
    prog = st_fe.parse_st(ARR_SRC).program
    buf = next(v for v in prog.vars if v.name == "buf")
    assert buf.array_len == 4              # [0..3] -> 4 elements
    assert buf.type is ir.DataType.INT
    # buf[idx] := val  is an IndexAssign
    assert isinstance(prog.body[0], ir.IndexAssign)
    assert prog.body[0].base == "buf"
    # total := total + buf[i]  contains an Index read
    loop = next(s for s in prog.body if isinstance(s, ir.For))
    add = loop.body[0]
    assert isinstance(add.value.right, ir.Index)
    assert add.value.right.base == "buf"


def test_array_executes_in_python():
    code = plcpy.convert(ARR_SRC, "st", "python").code
    Acc = runtime.load_pou(code, "Acc")
    inst = Acc()
    trace = runtime.run_scans(
        inst,
        inputs_per_cycle=[
            {"idx": 0, "val": 10},   # buf=[10,0,0,0]  total=10
            {"idx": 1, "val": 20},   # buf=[10,20,0,0] total=30
            {"idx": 3, "val": 5},    # buf=[10,20,0,5] total=35
        ],
        output_names=["total"],
    )
    assert [t.outputs["total"] for t in trace] == [10, 30, 35]


def test_array_roundtrips_to_st():
    out = plcpy.convert(ARR_SRC, "st", "st").code
    assert "buf : ARRAY[0..3] OF INT;" in out
    assert "buf[idx] := val;" in out
    assert "buf[i]" in out
