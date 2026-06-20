import plcpy
from plcpy import ir, runtime
from plcpy.frontends import il as il_fe

JMPC_IL = """PROGRAM J
VAR_INPUT
    start : BOOL;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    LD start
    JMPC done
    LD 1
    ST y
done:
END_PROGRAM
"""

JMPCN_IL = """PROGRAM P
VAR_INPUT
    g : BOOL;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    LD g
    JMPCN skip
    LD 1
    ST y
skip:
END_PROGRAM
"""

ST_IF = """PROGRAM P
VAR_INPUT
    g : BOOL;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    IF g THEN
        y := 1;
    END_IF;
END_PROGRAM
"""

ST_WHILE = """PROGRAM C
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


def test_il_jmpc_executes_via_fallback_or_raise():
    code = plcpy.convert(JMPC_IL, "il", "python").code
    P = runtime.load_pou(code, "J")
    a = P(); a.start = True; a.scan(); assert a.y == 0
    b = P(); b.start = False; b.scan(); assert b.y == 1


def test_jmpcn_block_raises_to_if():
    prog = il_fe.parse_il(JMPCN_IL).program
    ifs = [s for s in prog.body if isinstance(s, ir.If)]
    assert len(ifs) == 1
    assert ifs[0].cond == ir.VarRef("g")
    assert isinstance(ifs[0].then[0], ir.Assign) and ifs[0].then[0].target == "y"


def test_il_raised_if_to_st():
    st = plcpy.convert(JMPCN_IL, "il", "st").code
    assert "IF g THEN" in st and "y := 1;" in st and "END_IF;" in st


def test_st_if_lowers_to_il_and_roundtrips():
    il = plcpy.convert(ST_IF, "st", "il").code
    assert "JMPCN" in il and "LD g" in il
    st2 = plcpy.convert(il, "il", "st").code
    assert "IF g THEN" in st2 and "y := 1;" in st2


def test_st_while_lowers_to_il_and_executes():
    il = plcpy.convert(ST_WHILE, "st", "il").code
    assert "JMP " in il and "JMPCN" in il
    # IL -> python executes the loop (sum 0..n-1)
    code = plcpy.convert(il, "il", "python").code
    C = runtime.load_pou(code, "C")
    inst = C(); inst.n = 5; inst.scan()
    assert inst.total == 0 + 1 + 2 + 3 + 4
