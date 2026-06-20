from plcpy import ir, runtime
from plcpy.backends import python as py_be


def test_label_goto_fallback_executes():
    # JMPC done over `y := 1`
    prog = ir.Program(
        name="J",
        vars=[ir.VarDecl("start", ir.DataType.BOOL, ir.VarScope.INPUT),
              ir.VarDecl("y", ir.DataType.INT, ir.VarScope.OUTPUT)],
        body=[
            ir.Jump("done", ir.VarRef("start"), False),
            ir.Assign("y", ir.Literal(1, ir.DataType.INT)),
            ir.Label("done"),
        ],
    )
    code = py_be.emit_python(prog)
    P = runtime.load_pou(code, "J")
    a = P(); a.start = True; a.scan(); assert a.y == 0
    b = P(); b.start = False; b.scan(); assert b.y == 1
