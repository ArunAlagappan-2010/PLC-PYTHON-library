import xml.etree.ElementTree as ET
import plcpy

ST_SRC = """PROGRAM Main
VAR_INPUT
    x : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := x + 1;
    IF x > 10 THEN
        y := 99;
    END_IF;
END_PROGRAM
"""


def test_codesys_export():
    code = plcpy.convert(ST_SRC, "st", "codesys").code
    assert "@NESTEDCOMMENTS" in code        # CODESYS pragma marker
    assert "CODESYS export" in code
    assert "PROGRAM Main" in code
    assert "y := x + 1;" in code
    assert "END_PROGRAM" in code


def test_twincat_export_is_valid_xml():
    code = plcpy.convert(ST_SRC, "st", "twincat").code
    root = ET.fromstring(code)              # raises if malformed
    assert root.tag == "TcPlcObject"
    pou = root.find("POU")
    assert pou.get("Name") == "Main"
    decl = pou.find("Declaration").text
    impl = pou.find("Implementation/ST").text
    assert "PROGRAM Main" in decl
    assert "x : INT;" in decl
    assert "y := x + 1;" in impl
    assert "IF x > 10 THEN" in impl


def test_twincat_from_ladder():
    ld = """PROGRAM M
VAR_INPUT
    a : BOOL;
    b : BOOL;
END_VAR
VAR_OUTPUT
    y : BOOL;
END_VAR
RUNG
    --[ a ]--[/ b ]--( y )
END_RUNG
END_PROGRAM
"""
    code = plcpy.convert(ld, "ld", "twincat").code
    root = ET.fromstring(code)
    impl = root.find("POU/Implementation/ST").text
    assert "y := a AND NOT b;" in impl


def test_languages_includes_new_vendors():
    langs = plcpy.languages()
    assert langs["codesys"] == {"frontend": False, "backend": True}
    assert langs["twincat"] == {"frontend": False, "backend": True}
