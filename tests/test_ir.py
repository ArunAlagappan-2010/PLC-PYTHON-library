from plcpy import ir


def test_build_minimal_program():
    p = ir.Program(
        name="Main",
        vars=[
            ir.VarDecl("x", ir.DataType.INT, ir.VarScope.INPUT),
            ir.VarDecl("y", ir.DataType.INT, ir.VarScope.OUTPUT),
        ],
        body=[ir.Assign("y", ir.BinOp("+", ir.VarRef("x"), ir.Literal(1, ir.DataType.INT)))],
    )
    assert p.name == "Main"
    assert p.vars[0].scope is ir.VarScope.INPUT
    assert isinstance(p.body[0], ir.Assign)
    assert p.body[0].value.op == "+"
