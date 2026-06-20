import plcpy
from plcpy import runtime
from plcpy.frontends import sfc as sfc_fe

SRC = """PROGRAM Par
VAR_INPUT
    go : BOOL;
    aDone : BOOL;
    bDone : BOOL;
END_VAR
VAR_OUTPUT
    aRun : BOOL;
    bRun : BOOL;
    done : BOOL;
END_VAR
INITIAL_STEP Idle
    TRANSITION go TO TaskA, TaskB
END_STEP
STEP TaskA
    ACTION
        aRun := TRUE;
    END_ACTION
    TRANSITION aDone TO JoinA
END_STEP
STEP TaskB
    ACTION
        bRun := TRUE;
    END_ACTION
    TRANSITION bDone TO JoinB
END_STEP
STEP JoinA
    ACTION
        aRun := FALSE;
    END_ACTION
END_STEP
STEP JoinB
    ACTION
        bRun := FALSE;
    END_ACTION
    TRANSITION TRUE FROM JoinA, JoinB TO Finish
END_STEP
STEP Finish
    ACTION
        done := TRUE;
    END_ACTION
END_STEP
END_PROGRAM
"""


def test_divergence_and_convergence_parse():
    prog = sfc_fe.parse_sfc(SRC).program
    div = next(t for t in prog.sfc.transitions if "Idle" in t.sources)
    assert set(div.targets) == {"TaskA", "TaskB"}
    conv = next(t for t in prog.sfc.transitions if "Finish" in t.targets)
    assert set(conv.sources) == {"JoinA", "JoinB"}


def test_parallel_branches_run_then_join():
    code = plcpy.convert(SRC, "sfc", "python").code
    Par = runtime.load_pou(code, "Par")
    inst = Par()
    seq = [
        {"go": True,  "aDone": False, "bDone": False},
        {"go": False, "aDone": False, "bDone": False},
        {"go": False, "aDone": True,  "bDone": False},
        {"go": False, "aDone": False, "bDone": True},
        {"go": False, "aDone": False, "bDone": False},
    ]
    trace = runtime.run_scans(inst, seq, ["aRun", "bRun", "done"])
    # both branches active simultaneously after the divergence
    assert trace[1].outputs["aRun"] is True and trace[1].outputs["bRun"] is True
    # convergence fires once both joined
    assert trace[-1].outputs["done"] is True


def test_parallel_chart_roundtrips():
    out = plcpy.convert(SRC, "sfc", "sfc").code
    assert "TO TaskA, TaskB" in out
    assert "FROM JoinA, JoinB TO Finish" in out
    assert "_active_" not in out and "_started" not in out
