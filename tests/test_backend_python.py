from plcpy.backends import python as py_backend
from plcpy import ir


def _prog():
    return ir.Program(
        name="Main",
        vars=[
            ir.VarDecl("x", ir.DataType.INT, ir.VarScope.INPUT),
            ir.VarDecl("y", ir.DataType.INT, ir.VarScope.OUTPUT),
        ],
        body=[
            ir.Assign("y", ir.BinOp("+", ir.VarRef("x"), ir.Literal(1, ir.DataType.INT))),
            ir.If(ir.BinOp(">", ir.VarRef("x"), ir.Literal(0, ir.DataType.INT)),
                  [ir.Assign("y", ir.Literal(0, ir.DataType.INT))]),
        ],
    )


def test_emitted_module_executes():
    code = py_backend.emit_python(_prog())
    ns: dict = {}
    exec(compile(code, "<emitted>", "exec"), ns)
    Main = ns["Main"]
    inst = Main()
    inst.x = 5
    inst.scan()
    assert inst.y == 0
    inst.x = -3
    inst.scan()
    assert inst.y == -2
