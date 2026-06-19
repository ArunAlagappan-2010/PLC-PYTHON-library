import plcpy
from plcpy import ir, runtime
from plcpy.frontends import st as st_fe

FOR_SRC = """PROGRAM Sum
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
    FOR i := 1 TO n DO
        total := total + i;
    END_FOR;
END_PROGRAM
"""

CASE_SRC = """PROGRAM Grade
VAR_INPUT
    sel : INT;
END_VAR
VAR_OUTPUT
    out : INT;
END_VAR
    CASE sel OF
    1:
        out := 10;
    2,3:
        out := 20;
    ELSE
        out := 0;
    END_CASE;
END_PROGRAM
"""


def test_for_parses_to_ir_for():
    prog = st_fe.parse_st(FOR_SRC).program
    assert any(isinstance(s, ir.For) for s in prog.body)


def test_for_executes_in_python():
    code = plcpy.convert(FOR_SRC, "st", "python").code
    Sum = runtime.load_pou(code, "Sum")
    inst = Sum()
    inst.n = 5
    inst.scan()
    assert inst.total == 1 + 2 + 3 + 4 + 5  # 15


def test_for_roundtrips_to_st():
    out = plcpy.convert(FOR_SRC, "st", "st").code
    assert "FOR i := 1 TO n DO" in out
    assert "END_FOR;" in out


def test_case_parses_to_ir_case():
    prog = st_fe.parse_st(CASE_SRC).program
    case = next(s for s in prog.body if isinstance(s, ir.Case))
    assert case.branches[0][0] == [1]
    assert case.branches[1][0] == [2, 3]
    assert case.default  # ELSE present


def test_case_executes_in_python():
    code = plcpy.convert(CASE_SRC, "st", "python").code
    Grade = runtime.load_pou(code, "Grade")
    inst = Grade()
    for sel, expect in [(1, 10), (2, 20), (3, 20), (9, 0)]:
        inst.sel = sel
        inst.scan()
        assert inst.out == expect, (sel, inst.out)


def test_case_roundtrips_to_st():
    out = plcpy.convert(CASE_SRC, "st", "st").code
    assert "CASE sel OF" in out
    assert "2,3:" in out
    assert "END_CASE;" in out
