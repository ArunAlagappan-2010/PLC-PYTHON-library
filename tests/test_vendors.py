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


def test_scl_export_from_st():
    scl = plcpy.convert(ST_SRC, "st", "scl").code
    assert 'FUNCTION_BLOCK "Main"' in scl
    assert "x : Int;" in scl          # SCL type names
    assert "BEGIN" in scl
    assert "y := x + 1;" in scl
    assert "END_FUNCTION_BLOCK" in scl


def test_scl_export_from_ladder():
    # vendor export works from ANY frontend, not just ST
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
    scl = plcpy.convert(ld, "ld", "scl").code
    assert "a : Bool;" in scl
    assert "y := a AND NOT b;" in scl


def test_l5x_export_is_valid_xml():
    l5x = plcpy.convert(ST_SRC, "st", "l5x").code
    root = ET.fromstring(l5x)  # raises if malformed
    assert root.tag == "RSLogix5000Content"
    tags = {t.get("Name"): t.get("DataType") for t in root.iter("Tag")}
    assert tags == {"x": "DINT", "y": "DINT"}   # Rockwell type mapping
    lines = [ln.text for ln in root.iter("Line")]
    assert "y := x + 1;" in lines


def test_languages_includes_vendors():
    langs = plcpy.languages()
    # emitter-only: backend True, frontend False
    assert langs["scl"] == {"frontend": False, "backend": True}
    assert langs["l5x"] == {"frontend": False, "backend": True}
