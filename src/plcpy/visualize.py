"""Visualization: turn a program IR into an execution-flow graph and render a
standalone HTML page (side-by-side code + flow diagram).

`flow_graph(program)` returns a dict of nodes and edges:
    {"nodes": [{"id", "label", "kind"}], "edges": [{"src", "dst", "label"}]}

`render_html(...)` produces a single self-contained HTML file (no external
assets) with two code panes and an inline-SVG flowchart laid out top-to-bottom.
For SFC programs the graph is built directly from the step/transition chart.
"""
from __future__ import annotations
import html
from . import ir
from .backends.st import _expr


# ----------------------------------------------------------------------------
# Flow-graph construction
# ----------------------------------------------------------------------------

class _Flow:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self._n = 0

    def node(self, label: str, kind: str = "stmt") -> str:
        nid = f"n{self._n}"
        self._n += 1
        self.nodes.append({"id": nid, "label": label, "kind": kind})
        return nid

    def edge(self, a: str | None, b: str | None, label: str = "") -> None:
        if a and b:
            self.edges.append({"src": a, "dst": b, "label": label})

    def seq(self, stmts: list[ir.Stmt], entry: str, first_label: str = "") -> str:
        cur = entry
        label = first_label
        for s in stmts:
            cur = self.stmt(s, cur, label)
            label = ""
        return cur

    def stmt(self, s: ir.Stmt, entry: str, label: str = "") -> str:
        if isinstance(s, ir.Assign):
            n = self.node(f"{s.target} := {_expr(s.value)}", "assign")
            self.edge(entry, n, label)
            return n
        if isinstance(s, ir.If):
            d = self.node(f"IF {_expr(s.cond)}", "decision")
            self.edge(entry, d, label)
            merge = self.node("•", "merge")
            self.edge(self.seq(s.then, d, "true"), merge)
            false_src = d
            for econd, ebody in s.elifs:
                ed = self.node(f"ELSIF {_expr(econd)}", "decision")
                self.edge(false_src, ed, "false")
                self.edge(self.seq(ebody, ed, "true"), merge)
                false_src = ed
            if s.orelse:
                self.edge(self.seq(s.orelse, false_src, "false"), merge)
            else:
                self.edge(false_src, merge, "false")
            return merge
        if isinstance(s, ir.While):
            d = self.node(f"WHILE {_expr(s.cond)}", "loop")
            self.edge(entry, d, label)
            self.edge(self.seq(s.body, d, "true"), d, "loop")
            ex = self.node("•", "merge")
            self.edge(d, ex, "false")
            return ex
        if isinstance(s, ir.For):
            d = self.node(f"FOR {s.var} := {_expr(s.start)}..{_expr(s.end)}", "loop")
            self.edge(entry, d, label)
            self.edge(self.seq(s.body, d, "do"), d, "loop")
            ex = self.node("•", "merge")
            self.edge(d, ex, "done")
            return ex
        if isinstance(s, ir.Case):
            d = self.node(f"CASE {_expr(s.selector)}", "decision")
            self.edge(entry, d, label)
            merge = self.node("•", "merge")
            for labels, body in s.branches:
                lbl = ",".join(str(v) for v in labels)
                self.edge(self.seq(body, d, lbl), merge)
            if s.default:
                self.edge(self.seq(s.default, d, "else"), merge)
            return merge
        n = self.node(type(s).__name__, "stmt")
        self.edge(entry, n, label)
        return n


def _sfc_graph(sfc: ir.Sfc) -> dict:
    nodes = []
    edges = []
    for step in sfc.steps:
        kind = "initial_step" if step.initial else "step"
        nodes.append({"id": step.name, "label": step.name, "kind": kind})
    names = {s.name for s in sfc.steps}
    for step in sfc.steps:
        for cond, target in step.transitions:
            if target in names:
                edges.append({"src": step.name, "dst": target,
                              "label": _expr(cond)})
    return {"nodes": nodes, "edges": edges}


def flow_graph(program: ir.Program) -> dict:
    """Build the execution-flow graph for a program."""
    if program.sfc is not None:
        return _sfc_graph(program.sfc)
    f = _Flow()
    start = f.node("START", "start")
    last = f.seq(program.body, start)
    end = f.node("END", "end")
    f.edge(last, end)
    return {"nodes": f.nodes, "edges": f.edges}


# ----------------------------------------------------------------------------
# HTML rendering
# ----------------------------------------------------------------------------

_KIND_STYLE = {
    "start": ("#2e7d32", "#fff"), "end": ("#c62828", "#fff"),
    "decision": ("#f9a825", "#000"), "loop": ("#6a1b9a", "#fff"),
    "merge": ("#90a4ae", "#000"), "assign": ("#1565c0", "#fff"),
    "step": ("#00695c", "#fff"), "initial_step": ("#004d40", "#fff"),
    "stmt": ("#455a64", "#fff"),
}


def _svg(graph: dict) -> str:
    nodes = graph["nodes"]
    edges = graph["edges"]
    pos = {n["id"]: i for i, n in enumerate(nodes)}
    row_h = 74
    width = 520
    height = max(120, len(nodes) * row_h + 40)
    cx = width // 2
    box_w, box_h = 240, 38

    parts = [f'<svg viewBox="0 0 {width} {height}" '
             f'xmlns="http://www.w3.org/2000/svg" font-family="sans-serif" '
             f'font-size="13">']
    parts.append('<defs><marker id="arrow" markerWidth="10" markerHeight="10" '
                 'refX="8" refY="3" orient="auto" markerUnits="strokeWidth">'
                 '<path d="M0,0 L8,3 L0,6 Z" fill="#555"/></marker></defs>')

    def y(i: int) -> int:
        return 30 + i * row_h

    # edges first (so nodes draw on top)
    for e in edges:
        si, di = pos.get(e["src"]), pos.get(e["dst"])
        if si is None or di is None:
            continue
        y1 = y(si) + box_h // 2
        y2 = y(di) - box_h // 2
        if di > si:  # forward edge
            path = f'M{cx},{y1} L{cx},{y2}'
            mx, my = cx + 6, (y1 + y2) // 2
        else:        # back edge (loop) — route on the right
            side = cx + box_w // 2 + 50
            yy1 = y(si)
            yy2 = y(di)
            path = (f'M{cx + box_w // 2},{yy1} L{side},{yy1} '
                    f'L{side},{yy2} L{cx + box_w // 2},{yy2}')
            mx, my = side + 4, (yy1 + yy2) // 2
        parts.append(f'<path d="{path}" fill="none" stroke="#555" '
                     f'stroke-width="1.5" marker-end="url(#arrow)"/>')
        if e["label"]:
            parts.append(f'<text x="{mx}" y="{my}" fill="#333">'
                         f'{html.escape(e["label"])}</text>')

    for n in nodes:
        i = pos[n["id"]]
        fill, fg = _KIND_STYLE.get(n["kind"], _KIND_STYLE["stmt"])
        yc = y(i)
        label = html.escape(n["label"])
        if n["kind"] == "decision":
            # diamond
            parts.append(
                f'<polygon points="{cx},{yc - box_h // 2} '
                f'{cx + box_w // 2},{yc} {cx},{yc + box_h // 2} '
                f'{cx - box_w // 2},{yc}" fill="{fill}" stroke="#333"/>')
        else:
            rx = 18 if n["kind"] in ("step", "initial_step", "start", "end") else 4
            parts.append(
                f'<rect x="{cx - box_w // 2}" y="{yc - box_h // 2}" '
                f'width="{box_w}" height="{box_h}" rx="{rx}" '
                f'fill="{fill}" stroke="#333"/>')
        parts.append(f'<text x="{cx}" y="{yc + 4}" text-anchor="middle" '
                     f'fill="{fg}">{label}</text>')

    parts.append("</svg>")
    return "\n".join(parts)


def render_html(source: str, source_lang: str, target_code: str,
                target_lang: str, program: ir.Program, title: str = "plcpy") -> str:
    """Render a standalone HTML page: side-by-side code + flow diagram."""
    graph = flow_graph(program)
    svg = _svg(graph)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
  body {{ font-family: sans-serif; margin: 0; background: #fafafa; color: #222; }}
  header {{ background: #263238; color: #fff; padding: 10px 16px; }}
  .cols {{ display: flex; gap: 12px; padding: 12px; align-items: flex-start;
           flex-wrap: wrap; }}
  .pane {{ flex: 1 1 320px; min-width: 280px; }}
  .pane h2 {{ font-size: 13px; text-transform: uppercase; color: #607d8b;
              margin: 0 0 6px; }}
  pre {{ background: #fff; border: 1px solid #cfd8dc; border-radius: 6px;
         padding: 12px; overflow: auto; font-size: 13px; line-height: 1.4; }}
  .diagram {{ flex: 1 1 360px; min-width: 320px; background: #fff;
              border: 1px solid #cfd8dc; border-radius: 6px; padding: 8px; }}
</style></head>
<body>
<header><strong>plcpy</strong> — {html.escape(source_lang)} ↔ \
{html.escape(target_lang)} &nbsp;|&nbsp; execution-flow visualizer</header>
<div class="cols">
  <div class="pane"><h2>{html.escape(source_lang)} (source)</h2>
    <pre>{html.escape(source)}</pre></div>
  <div class="pane"><h2>{html.escape(target_lang)} (converted)</h2>
    <pre>{html.escape(target_code)}</pre></div>
  <div class="diagram"><h2 style="color:#607d8b;font-size:13px;\
text-transform:uppercase;margin:0 0 6px">execution flow</h2>{svg}</div>
</div>
</body></html>
"""
