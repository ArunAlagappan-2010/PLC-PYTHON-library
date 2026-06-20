import xml.etree.ElementTree as ET
import plcpy
from plcpy import runtime


def _local(t):
    return t.rsplit("}", 1)[-1]


FBD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://www.plcopen.org/xml/tc6_0201">
  <types><pous>
    <pou name="Calc" pouType="program">
      <interface>
        <inputVars>
          <variable name="a"><type><INT/></type></variable>
          <variable name="b"><type><INT/></type></variable>
        </inputVars>
        <outputVars>
          <variable name="y"><type><INT/></type></variable>
        </outputVars>
      </interface>
      <body>
        <FBD>
          <inVariable localId="1"><expression>a</expression></inVariable>
          <inVariable localId="2"><expression>b</expression></inVariable>
          <block localId="3" typeName="ADD">
            <inputVariables>
              <variable formalParameter="IN1"><connectionPointIn><connection refLocalId="1"/></connectionPointIn></variable>
              <variable formalParameter="IN2"><connectionPointIn><connection refLocalId="2"/></connectionPointIn></variable>
            </inputVariables>
            <outputVariables>
              <variable formalParameter="OUT"><connectionPointOut/></variable>
            </outputVariables>
          </block>
          <outVariable localId="4"><expression>y</expression>
            <connectionPointIn><connection refLocalId="3"/></connectionPointIn>
          </outVariable>
        </FBD>
      </body>
    </pou>
  </pous></types>
</project>
"""

SFC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://www.plcopen.org/xml/tc6_0201">
  <types><pous>
    <pou name="Latch" pouType="program">
      <interface>
        <inputVars><variable name="go"><type><BOOL/></type></variable></inputVars>
        <outputVars><variable name="active"><type><BOOL/></type></variable></outputVars>
      </interface>
      <body>
        <SFC>
          <step localId="1" name="Idle" initialStep="true">
            <actionBlock><action><inline><ST><![CDATA[active := FALSE;]]></ST></inline></action></actionBlock>
          </step>
          <transition localId="2" target="Run">
            <condition><inline><ST><![CDATA[go]]></ST></inline></condition>
          </transition>
          <step localId="3" name="Run">
            <actionBlock><action><inline><ST><![CDATA[active := TRUE;]]></ST></inline></action></actionBlock>
          </step>
        </SFC>
      </body>
    </pou>
  </pous></types>
</project>
"""


def test_plcopen_fbd_import_executes():
    res = plcpy.convert(FBD_XML, "plcopen", "python")
    assert res.diagnostics == []
    Calc = runtime.load_pou(res.code, "Calc")
    inst = Calc(); inst.a, inst.b = 4, 5; inst.scan()
    assert inst.y == 9


def test_arithmetic_exports_as_fbd_block():
    st = """PROGRAM Calc
VAR_INPUT
    a : INT;
    b : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := a + b;
END_PROGRAM
"""
    xml = plcpy.convert(st, "st", "plcopen").code
    root = ET.fromstring(xml)
    assert any(b.get("typeName") == "ADD" for b in root.iter() if _local(b.tag) == "block")
    py = plcpy.convert(xml, "plcopen", "python").code
    inst = runtime.load_pou(py, "Calc")(); inst.a, inst.b = 2, 3; inst.scan()
    assert inst.y == 5


def test_plcopen_sfc_import_executes():
    code = plcpy.convert(SFC_XML, "plcopen", "python").code
    Latch = runtime.load_pou(code, "Latch")
    inst = Latch()
    trace = runtime.run_scans(inst, [{"go": True}, {"go": False}], ["active"])
    assert trace[-1].outputs["active"] is True


def test_sfc_exports_with_layout():
    sfc_src = """PROGRAM Latch
VAR_INPUT
    go : BOOL;
END_VAR
VAR_OUTPUT
    active : BOOL;
END_VAR
INITIAL_STEP Idle
    ACTION
        active := FALSE;
    END_ACTION
    TRANSITION go TO Run
END_STEP
STEP Run
    ACTION
        active := TRUE;
    END_ACTION
END_STEP
END_PROGRAM
"""
    xml = plcpy.convert(sfc_src, "sfc", "plcopen").code
    root = ET.fromstring(xml)
    steps = [e for e in root.iter() if _local(e.tag) == "step"]
    assert {s.get("name") for s in steps} == {"Idle", "Run"}
    assert all(any(_local(c.tag) == "position" for c in s) for s in steps)
    # synthetic state vars must not leak into the interface
    assert not any(v.get("name", "").startswith("_active_")
                   for v in root.iter() if _local(v.tag) == "variable")
    # re-import and execute
    code = plcpy.convert(xml, "plcopen", "python").code
    inst = runtime.load_pou(code, "Latch")()
    trace = runtime.run_scans(inst, [{"go": True}, {"go": False}], ["active"])
    assert trace[-1].outputs["active"] is True
