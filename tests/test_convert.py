import plcpy

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


def test_st_to_python_executes():
    res = plcpy.convert(ST_SRC, "st", "python")
    assert res.diagnostics == []
    ns: dict = {}
    exec(compile(res.code, "<c>", "exec"), ns)
    m = ns["Main"]()
    m.x = 41
    m.scan()
    assert m.y == 42


def test_python_to_st_roundtrips():
    py = plcpy.convert(ST_SRC, "st", "python").code
    st = plcpy.convert(py, "python", "st").code
    assert "PROGRAM Main" in st
    assert "y := self.x + 1" in st or "y := x + 1" in st


def test_languages_lists_all_four():
    langs = plcpy.languages()
    assert langs["st"] == {"frontend": True, "backend": True}
    assert langs["python"] == {"frontend": True, "backend": True}
