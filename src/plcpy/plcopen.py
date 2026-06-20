"""PLCopen XML (TC6) import/export for Ladder Diagrams.

Registers a `plcopen` language with both a frontend and a backend.

Import: walks the LD element graph (leftPowerRail / contact / coil connected by
`<connectionPointIn><connection refLocalId=.../></connectionPointIn>`) back from
each coil, turning series connections into AND, parallel connections into OR and
`negated` contacts into NOT — i.e. the same boolean `Assign` lowering the
textual LD frontend uses. So PLCopen ladders convert to/from every language and
execute in the runtime.

Export: emits a TC6 `<project>` with one program POU whose body is an `<LD>`
graph, laying out series/parallel contacts and assigning localIds + connections.
Rungs whose RHS is not contact-expressible are skipped with an XML comment.

Namespaces are ignored on read (local tag names) and the standard tc6_0201
namespace is written on export.
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from . import ir
from .registry import ParseResult, register_frontend, register_backend
from .diagnostics import Diagnostic, Severity
from .frontends._common import TYPES

_NS = "http://www.plcopen.org/xml/tc6_0201"
_TYPE_NAME = {ir.DataType.BOOL: "BOOL", ir.DataType.INT: "INT", ir.DataType.REAL: "REAL"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# ---------------------------------------------------------------------------
# Import (PLCopen XML -> IR)
# ---------------------------------------------------------------------------

def _eval_node(lid: str, nodes: dict) -> ir.Expr | None:
    n = nodes.get(lid)
    if n is None or n["tag"] == "leftPowerRail":
        return None  # identity (TRUE) for the AND chain
    upstream = _eval(n["refs"], nodes)
    if n["tag"] == "contact":
        term: ir.Expr = ir.VarRef(n["var"])
        if n["neg"]:
            term = ir.UnaryOp("not", term)
        if upstream is None:
            return term
        return ir.BinOp("and", upstream, term)
    return upstream


def _eval(refs: list[str], nodes: dict) -> ir.Expr | None:
    terms = [t for t in (_eval_node(r, nodes) for r in refs) if t is not None]
    if not terms:
        return None
    acc = terms[0]
    for t in terms[1:]:
        acc = ir.BinOp("or", acc, t)
    return acc


def parse_plcopen(text: str) -> ParseResult:
    diagnostics: list[Diagnostic] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return ParseResult(None, [Diagnostic(str(e), Severity.ERROR, code="PLCOPEN")])

    pou = next((el for el in root.iter() if _local(el.tag) == "pou"), None)
    if pou is None:
        return ParseResult(None, [Diagnostic("no <pou> element", Severity.ERROR,
                                              code="PLCOPEN")])
    name = pou.get("name", "Program")
    vars_: list[ir.VarDecl] = []
    for section, scope in (("inputVars", ir.VarScope.INPUT),
                           ("outputVars", ir.VarScope.OUTPUT),
                           ("localVars", ir.VarScope.LOCAL)):
        for sec in pou.iter():
            if _local(sec.tag) != section:
                continue
            for var in sec:
                if _local(var.tag) != "variable":
                    continue
                vn = var.get("name")
                dt = ir.DataType.BOOL
                for t in var.iter():
                    if _local(t.tag) in TYPES:
                        dt = TYPES[_local(t.tag)]
                        break
                vars_.append(ir.VarDecl(vn, dt, scope))

    body: list[ir.Stmt] = []
    ld = next((el for el in pou.iter() if _local(el.tag) == "LD"), None)
    if ld is not None:
        nodes: dict[str, dict] = {}
        for el in ld:
            lt = _local(el.tag)
            if lt not in ("leftPowerRail", "contact", "coil", "rightPowerRail"):
                continue
            variable = None
            for ch in el:
                if _local(ch.tag) == "variable":
                    variable = (ch.text or "").strip()
            negated = el.get("negated", "false") == "true"
            refs = [c.get("refLocalId") for c in el.iter()
                    if _local(c.tag) == "connection" and c.get("refLocalId")]
            nodes[el.get("localId")] = {"tag": lt, "var": variable,
                                        "neg": negated, "refs": refs}
        for lid, n in nodes.items():
            if n["tag"] == "coil":
                expr = _eval(n["refs"], nodes) or ir.Literal(True, ir.DataType.BOOL)
                if n["neg"]:
                    expr = ir.UnaryOp("not", expr)
                body.append(ir.Assign(n["var"], expr))

    return ParseResult(ir.Program(name, vars_, body), diagnostics)


# ---------------------------------------------------------------------------
# Export (IR -> PLCopen XML)
# ---------------------------------------------------------------------------

def _leaves(term: ir.Expr) -> list[tuple[str, bool]] | None:
    """Flatten a series term to (name, negated) contacts, or None if not ladder."""
    if isinstance(term, ir.VarRef):
        return [(term.name, False)]
    if isinstance(term, ir.UnaryOp) and term.op == "not" and isinstance(term.operand, ir.VarRef):
        return [(term.operand.name, True)]
    if isinstance(term, ir.BinOp) and term.op == "or":
        left = _leaves(term.left)
        right = _leaves(term.right)
        if left is None or right is None:
            return None
        return left + right
    return None


def _and_terms(e: ir.Expr) -> list[ir.Expr]:
    if isinstance(e, ir.BinOp) and e.op == "and":
        return _and_terms(e.left) + [e.right]
    return [e]


class _Ids:
    def __init__(self) -> None:
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return str(self._n)


def _conn_in(parent: ET.Element, refs: list[str]) -> None:
    cpi = ET.SubElement(parent, "connectionPointIn")
    for r in refs:
        ET.SubElement(cpi, "connection", refLocalId=r)


def _emit_rung(ld: ET.Element, assign: ir.Assign, ids: _Ids) -> bool:
    expr = assign.value
    coil_neg = "false"
    if isinstance(expr, ir.UnaryOp) and expr.op == "not":
        if all(_leaves(t) is not None for t in _and_terms(expr.operand)):
            coil_neg = "true"
            expr = expr.operand

    terms = _and_terms(expr)
    if any(_leaves(t) is None for t in terms):
        ld.append(ET.Comment(f" unsupported rung: {assign.target} "))
        return False

    rail = ids.next()
    rail_el = ET.SubElement(ld, "leftPowerRail", localId=rail)
    ET.SubElement(ET.SubElement(rail_el, "connectionPointOut"), "connection")  # placeholder
    current = [rail]
    for term in terms:
        leaves = _leaves(term)
        new_refs = []
        for vname, neg in leaves:
            cid = ids.next()
            contact = ET.SubElement(ld, "contact", localId=cid,
                                    negated="true" if neg else "false")
            var = ET.SubElement(contact, "variable")
            var.text = vname
            _conn_in(contact, current)
            new_refs.append(cid)
        current = new_refs
    cid = ids.next()
    coil = ET.SubElement(ld, "coil", localId=cid, negated=coil_neg)
    var = ET.SubElement(coil, "variable")
    var.text = assign.target
    _conn_in(coil, current)
    return True


def emit_plcopen(program: ir.Program) -> str:
    project = ET.Element("project", xmlns=_NS)
    types = ET.SubElement(project, "types")
    pous = ET.SubElement(types, "pous")
    pou = ET.SubElement(pous, "pou", name=program.name, pouType="program")
    interface = ET.SubElement(pou, "interface")
    for section, scope in (("inputVars", ir.VarScope.INPUT),
                           ("outputVars", ir.VarScope.OUTPUT),
                           ("localVars", ir.VarScope.LOCAL)):
        decls = [v for v in program.vars if v.scope is scope]
        if not decls:
            continue
        sec = ET.SubElement(interface, section)
        for v in decls:
            var = ET.SubElement(sec, "variable", name=v.name)
            ET.SubElement(ET.SubElement(var, "type"), _TYPE_NAME[v.type])

    body = ET.SubElement(pou, "body")
    ld = ET.SubElement(body, "LD")
    ids = _Ids()
    for s in program.body:
        if isinstance(s, ir.Assign):
            _emit_rung(ld, s, ids)
        else:
            ld.append(ET.Comment(f" unsupported in LD: {type(s).__name__} "))

    ET.indent(project, space="  ")
    xml = ET.tostring(project, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n"


register_frontend("plcopen", parse_plcopen)
register_backend("plcopen", emit_plcopen)
