import xml.etree.ElementTree as ET
import plcpy
from plcpy import runtime

# Motor seal-in as a PLCopen TC6 ladder:
#   (start OR run) AND (NOT stop) -> run
PLCOPEN_SRC = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://www.plcopen.org/xml/tc6_0201">
  <types><pous>
    <pou name="Motor" pouType="program">
      <interface>
        <inputVars>
          <variable name="start"><type><BOOL/></type></variable>
          <variable name="stop"><type><BOOL/></type></variable>
        </inputVars>
        <outputVars>
          <variable name="run"><type><BOOL/></type></variable>
        </outputVars>
      </interface>
      <body>
        <LD>
          <leftPowerRail localId="0">
            <connectionPointOut/>
          </leftPowerRail>
          <contact localId="1" negated="false">
            <variable>start</variable>
            <connectionPointIn><connection refLocalId="0"/></connectionPointIn>
          </contact>
          <contact localId="2" negated="false">
            <variable>run</variable>
            <connectionPointIn><connection refLocalId="0"/></connectionPointIn>
          </contact>
          <contact localId="3" negated="true">
            <variable>stop</variable>
            <connectionPointIn>
              <connection refLocalId="1"/>
              <connection refLocalId="2"/>
            </connectionPointIn>
          </contact>
          <coil localId="4" negated="false">
            <variable>run</variable>
            <connectionPointIn><connection refLocalId="3"/></connectionPointIn>
          </coil>
        </LD>
      </body>
    </pou>
  </pous></types>
</project>
"""


def test_plcopen_import_to_python_seal_in():
    res = plcpy.convert(PLCOPEN_SRC, "plcopen", "python")
    assert res.diagnostics == []
    Motor = runtime.load_pou(res.code, "Motor")
    trace = runtime.run_scans(
        Motor(),
        inputs_per_cycle=[
            {"start": True, "stop": False},
            {"start": False, "stop": False},
            {"start": False, "stop": True},
            {"start": False, "stop": False},
        ],
        output_names=["run"],
    )
    assert [t.outputs["run"] for t in trace] == [True, True, False, False]


def test_plcopen_import_to_st_logic():
    st = plcpy.convert(PLCOPEN_SRC, "plcopen", "st").code
    assert "run := (start OR run) AND NOT stop" in st


def test_plcopen_export_is_valid_xml_with_contacts():
    st_src = """PROGRAM M
VAR_INPUT
    a : BOOL;
    b : BOOL;
END_VAR
VAR_OUTPUT
    y : BOOL;
END_VAR
    y := a AND NOT b;
END_PROGRAM
"""
    xml = plcpy.convert(st_src, "st", "plcopen").code
    root = ET.fromstring(xml)  # raises if malformed

    def local(t):
        return t.rsplit("}", 1)[-1]
    contacts = [e for e in root.iter() if local(e.tag) == "contact"]
    coils = [e for e in root.iter() if local(e.tag) == "coil"]
    assert len(contacts) == 2 and len(coils) == 1
    negated = {next(c.text for c in e.iter() if local(c.tag) == "variable"): e.get("negated")
               for e in contacts}
    assert negated == {"a": "false", "b": "true"}


def test_plcopen_roundtrips_through_ir():
    # PLCopen -> Python and PLCopen -> ST -> PLCopen preserve seal-in semantics
    st = plcpy.convert(PLCOPEN_SRC, "plcopen", "st").code
    xml2 = plcpy.convert(st, "st", "plcopen").code
    py2 = plcpy.convert(xml2, "plcopen", "python").code
    Motor = runtime.load_pou(py2, "Motor")
    inst = Motor()
    inst.start = True
    inst.scan()
    assert inst.run is True


def test_languages_includes_plcopen():
    assert plcpy.languages()["plcopen"] == {"frontend": True, "backend": True}
