import plcpy
from plcpy import runtime
from plcpy.frontends import st as st_fe
from plcpy import ir

TON_SRC = """PROGRAM DelayOn
VAR_INPUT
    trigger : BOOL;
END_VAR
VAR_OUTPUT
    out : BOOL;
END_VAR
VAR
    tmr : TON;
END_VAR
    tmr(IN := trigger, PT := T#300ms);
    out := tmr.Q;
END_PROGRAM
"""


def test_st_parses_timer_instance_call_and_member():
    prog = st_fe.parse_st(TON_SRC).program
    assert any(fb.fb_type == "TON" and fb.name == "tmr" for fb in prog.fbs)
    assert any(isinstance(s, ir.FBCall) and s.instance == "tmr" for s in prog.body)
    # the member access tmr.Q is used in the second statement
    out_assign = prog.body[1]
    assert isinstance(out_assign, ir.Assign)
    assert isinstance(out_assign.value, ir.Member)
    assert out_assign.value.base == ir.VarRef("tmr") and out_assign.value.member == "Q"


def test_time_literal_parsed_to_milliseconds():
    prog = st_fe.parse_st(TON_SRC).program
    call = next(s for s in prog.body if isinstance(s, ir.FBCall))
    pt = call.args["PT"]
    assert isinstance(pt, ir.Literal) and pt.type is ir.DataType.TIME
    assert pt.value == 300


def test_ton_executes_in_python_with_scan_time():
    code = plcpy.convert(TON_SRC, "st", "python").code
    DelayOn = runtime.load_pou(code, "DelayOn")
    inst = DelayOn()
    # 100 ms per scan; PT = 300 ms -> Q after 3 scans of held trigger
    trace = runtime.run_scans(
        inst,
        inputs_per_cycle=[
            {"trigger": True},
            {"trigger": True},
            {"trigger": True},
            {"trigger": False},
        ],
        output_names=["out"],
        dt_ms=100,
    )
    assert [t.outputs["out"] for t in trace] == [False, False, True, False]


def test_timer_roundtrips_to_st():
    out = plcpy.convert(TON_SRC, "st", "st").code
    assert "tmr : TON;" in out
    assert "tmr(IN := trigger, PT := T#300ms);" in out
    assert "out := tmr.Q;" in out


def test_every_backend_handles_timer_program_without_crashing():
    # FB calls / member access must degrade gracefully in non-Python backends,
    # never raise.
    for target in ["il", "ld", "fbd", "scl", "codesys", "twincat", "st",
                   "python", "plcopen"]:
        res = plcpy.convert(TON_SRC, "st", target)
        assert res.code is not None, target
