import xml.etree.ElementTree as ET
import plcpy
from plcpy import visualize
from plcpy.frontends import st as st_fe
from plcpy.frontends import sfc as sfc_fe

IF_SRC = """PROGRAM P
VAR_INPUT
    x : INT;
END_VAR
VAR_OUTPUT
    y : INT;
END_VAR
    y := x;
    IF x > 0 THEN
        y := 1;
    ELSE
        y := 2;
    END_IF;
END_PROGRAM
"""

SFC_SRC = """PROGRAM Latch
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
    TRANSITION go TO Running
END_STEP
STEP Running
    ACTION
        active := TRUE;
    END_ACTION
    TRANSITION go TO Idle
END_STEP
END_PROGRAM
"""


def test_flow_graph_if_has_decision_and_merge():
    prog = st_fe.parse_st(IF_SRC).program
    g = visualize.flow_graph(prog)
    kinds = [n["kind"] for n in g["nodes"]]
    assert "start" in kinds and "end" in kinds
    assert "decision" in kinds  # the IF
    # decision must have both true and false out-edges
    dec = next(n for n in g["nodes"] if n["kind"] == "decision")
    labels = {e["label"] for e in g["edges"] if e["src"] == dec["id"]}
    assert labels == {"true", "false"}


def test_flow_graph_sfc_uses_steps_and_transitions():
    prog = sfc_fe.parse_sfc(SFC_SRC).program
    g = visualize.flow_graph(prog)
    names = {n["label"] for n in g["nodes"]}
    assert names == {"Idle", "Running"}
    # transitions become labeled edges
    edge_pairs = {(e["src"], e["dst"]) for e in g["edges"]}
    assert ("Idle", "Running") in edge_pairs
    assert ("Running", "Idle") in edge_pairs


def test_render_html_is_well_formed_and_has_both_panes():
    prog = st_fe.parse_st(IF_SRC).program
    target = plcpy.convert(IF_SRC, "st", "python").code
    html = visualize.render_html(IF_SRC, "st", target, "python", prog)
    assert "<svg" in html and "</svg>" in html
    assert "st (source)".upper() in html.upper()
    assert "y := x" in html        # source pane content
    assert "def scan(self)" in html  # converted pane content
    # the inline SVG must itself be valid XML
    svg = html[html.index("<svg"):html.index("</svg>") + len("</svg>")]
    ET.fromstring(svg)


def test_cli_visualize_writes_html(tmp_path, capsys):
    from plcpy import cli
    src = tmp_path / "p.st"
    src.write_text(IF_SRC)
    out = tmp_path / "p.html"
    rc = cli.main(["visualize", "--from", "st", "--to", "python",
                   str(src), "-o", str(out)])
    assert rc == 0
    assert out.exists()
    assert "<svg" in out.read_text(encoding="utf-8")
