from plcpy.frontends import python as py_frontend
from plcpy import ir

CODE = """class Main:
    def __init__(self):
        self.x = 0
        self.y = 0

    def scan(self):
        self.y = (self.x + 1)
        if (self.x > 0):
            self.y = 0
"""


def test_parse_python_class_to_ir():
    res = py_frontend.parse_python(CODE)
    assert res.diagnostics == []
    p = res.program
    assert p.name == "Main"
    assert {v.name for v in p.vars} == {"x", "y"}
    assert isinstance(p.body[0], ir.Assign)
    assert p.body[0].target == "y"
    assert isinstance(p.body[1], ir.If)
    assert p.body[1].cond.op == ">"


def test_unsupported_python_reports_diagnostic():
    # a `for` loop is outside the supported subset -> unsupported diagnostic
    res = py_frontend.parse_python(
        "class P:\n    def __init__(self):\n        self.a = 0\n"
        "    def scan(self):\n        for _ in range(3):\n            self.a = 0\n")
    assert any(d.severity.name == "UNSUPPORTED" for d in res.diagnostics)
