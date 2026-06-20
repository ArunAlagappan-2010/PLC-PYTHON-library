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
import re
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
    sfc_obj = None
    body_el = next((el for el in pou.iter() if _local(el.tag) == "body"), None)
    child = next((c for c in body_el), None) if body_el is not None else None
    kind = _local(child.tag) if child is not None else None
    if kind == "LD":
        body = _parse_ld_body(child)
    elif kind == "FBD":
        body, extra = _parse_fbd_body(child)
        vars_.extend(extra)
    elif kind == "SFC":
        sfc_obj, sfc_vars, body = _parse_sfc_body(child)
        vars_.extend(sfc_vars)

    return ParseResult(ir.Program(name, vars_, body, sfc=sfc_obj), diagnostics)


def _parse_ld_body(ld) -> list[ir.Stmt]:
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
    out: list[ir.Stmt] = []
    for lid, n in nodes.items():
        if n["tag"] == "coil":
            expr = _eval(n["refs"], nodes) or ir.Literal(True, ir.DataType.BOOL)
            if n["neg"]:
                expr = ir.UnaryOp("not", expr)
            out.append(ir.Assign(n["var"], expr))
    return out


_FBD_NARY = {"ADD": "+", "MUL": "*", "AND": "and", "OR": "or"}
_FBD_BINARY = {"SUB": "-", "DIV": "/", "GT": ">", "GE": ">=", "LT": "<",
               "LE": "<=", "EQ": "=", "NE": "<>"}


def _operand(tok: str) -> ir.Expr:
    tok = (tok or "").strip()
    if tok in ("TRUE", "FALSE"):
        return ir.Literal(tok == "TRUE", ir.DataType.BOOL)
    if re.fullmatch(r"[0-9]+\.[0-9]+", tok):
        return ir.Literal(float(tok), ir.DataType.REAL)
    if re.fullmatch(r"[0-9]+", tok):
        return ir.Literal(int(tok), ir.DataType.INT)
    return ir.VarRef(tok)


def _parse_fbd_body(fbd):
    nodes: dict[str, dict] = {}
    for el in fbd:
        lid = el.get("localId")
        kind = _local(el.tag)
        if kind in ("inVariable", "outVariable"):
            expr_el = next((c for c in el.iter() if _local(c.tag) == "expression"), None)
            text = (expr_el.text or "").strip() if expr_el is not None else ""
            refs = [c.get("refLocalId") for c in el.iter()
                    if _local(c.tag) == "connection" and c.get("refLocalId")]
            nodes[lid] = {"kind": kind, "text": text, "refs": refs}
        elif kind == "block":
            inputs = []
            invs = next((c for c in el if _local(c.tag) == "inputVariables"), None)
            if invs is not None:
                for v in invs:
                    if _local(v.tag) != "variable":
                        continue
                    r = next((c.get("refLocalId") for c in v.iter()
                              if _local(c.tag) == "connection" and c.get("refLocalId")), None)
                    inputs.append(r)
            nodes[lid] = {"kind": "block", "type": (el.get("typeName") or "").upper(),
                          "inputs": inputs}

    def build(lid):
        n = nodes.get(lid)
        if n is None:
            return None
        if n["kind"] in ("inVariable", "outVariable"):
            return _operand(n["text"])
        if n["kind"] == "block":
            args = [build(r) for r in n["inputs"]]
            args = [a for a in args if a is not None]
            t = n["type"]
            if t == "NOT" and args:
                return ir.UnaryOp("not", args[0])
            if t in _FBD_NARY and args:
                acc = args[0]
                for a in args[1:]:
                    acc = ir.BinOp(_FBD_NARY[t], acc, a)
                return acc
            if t in _FBD_BINARY and len(args) == 2:
                return ir.BinOp(_FBD_BINARY[t], args[0], args[1])
        return None

    stmts: list[ir.Stmt] = []
    for lid, n in nodes.items():
        if n["kind"] == "outVariable":
            expr = build(n["refs"][0]) if n["refs"] else None
            if expr is not None:
                stmts.append(ir.Assign(n["text"], expr))
    return stmts, []


def _parse_sfc_body(sfc_el):
    from .frontends.sfc import _lower, _parse_stmts, _parse_expr
    steps: list[ir.SfcStep] = []
    ordered_steps: list[tuple[str, ir.SfcStep]] = []  # (localId, step)
    last_step: ir.SfcStep | None = None
    trans: list[ir.SfcTransition] = []
    for el in sfc_el:
        lt = _local(el.tag)
        if lt == "step":
            act = next((c for c in el.iter() if _local(c.tag) == "ST"), None)
            actions = _parse_stmts(act.text) if act is not None and act.text else []
            pos = next((c for c in el if _local(c.tag) == "position"), None)
            layout = ({"x": int(pos.get("x", 0)), "y": int(pos.get("y", 0))}
                      if pos is not None else None)
            s = ir.SfcStep(el.get("name"), initial=el.get("initialStep") == "true",
                           actions=actions)
            s.layout = layout
            steps.append(s)
            ordered_steps.append((el.get("localId"), s))
            last_step = s
        elif lt == "transition":
            cond_el = next((c for c in el.iter() if _local(c.tag) == "ST"), None)
            cond = _parse_expr((cond_el.text or "").strip()) if cond_el is not None else None
            target = el.get("target")
            src_name = el.get("source")
            source = (next((s for s in steps if s.name == src_name), None)
                      if src_name else last_step)
            if cond is not None and target and source is not None:
                trans.append(ir.SfcTransition(cond, [source.name], [target]))
                source.transitions.append((cond, target))
    steps.sort(key=lambda s: 0 if s.initial else 1)
    sfc = ir.Sfc(steps, trans)
    decls, body = _lower(sfc)
    return sfc, decls, body


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


def _operand_text(e: ir.Literal) -> str:
    if e.type is ir.DataType.BOOL:
        return "TRUE" if e.value else "FALSE"
    return str(e.value)


_FUNC_NAME = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "and": "AND",
              "or": "OR", ">": "GT", ">=": "GE", "<": "LT", "<=": "LE",
              "=": "EQ", "<>": "NE"}


def _emit_expr_fbd(parent: ET.Element, e: ir.Expr, ids: _Ids) -> str | None:
    if isinstance(e, (ir.VarRef, ir.Literal)):
        lid = ids.next()
        iv = ET.SubElement(parent, "inVariable", localId=lid)
        ET.SubElement(iv, "expression").text = (
            e.name if isinstance(e, ir.VarRef) else _operand_text(e))
        return lid
    if isinstance(e, ir.UnaryOp) and e.op == "not":
        src = _emit_expr_fbd(parent, e.operand, ids)
        if src is None:
            return None
        lid = ids.next()
        blk = ET.SubElement(parent, "block", localId=lid, typeName="NOT")
        v = ET.SubElement(ET.SubElement(blk, "inputVariables"), "variable",
                          formalParameter="IN")
        ET.SubElement(ET.SubElement(v, "connectionPointIn"), "connection", refLocalId=src)
        ET.SubElement(ET.SubElement(blk, "outputVariables"), "variable",
                      formalParameter="OUT")
        return lid
    if isinstance(e, ir.BinOp) and e.op in _FUNC_NAME:
        left = _emit_expr_fbd(parent, e.left, ids)
        right = _emit_expr_fbd(parent, e.right, ids)
        if left is None or right is None:
            return None
        lid = ids.next()
        blk = ET.SubElement(parent, "block", localId=lid, typeName=_FUNC_NAME[e.op])
        invs = ET.SubElement(blk, "inputVariables")
        for fp, ref in (("IN1", left), ("IN2", right)):
            v = ET.SubElement(invs, "variable", formalParameter=fp)
            ET.SubElement(ET.SubElement(v, "connectionPointIn"), "connection", refLocalId=ref)
        ET.SubElement(ET.SubElement(blk, "outputVariables"), "variable",
                      formalParameter="OUT")
        return lid
    return None


def _emit_fbd_body(fbd: ET.Element, program: ir.Program, ids: _Ids) -> None:
    for s in program.body:
        if isinstance(s, ir.Assign):
            src = _emit_expr_fbd(fbd, s.value, ids)
            if src is None:
                fbd.append(ET.Comment(f" unsupported network: {s.target} "))
                continue
            ov = ET.SubElement(fbd, "outVariable", localId=ids.next())
            ET.SubElement(ov, "expression").text = s.target
            ET.SubElement(ET.SubElement(ov, "connectionPointIn"), "connection", refLocalId=src)
        else:
            fbd.append(ET.Comment(f" unsupported in FBD: {type(s).__name__} "))


def _emit_sfc_body(sfc_el: ET.Element, program: ir.Program, ids: _Ids) -> None:
    from .backends.st import _stmts as _st_stmts, _expr as _st_expr
    for i, step in enumerate(program.sfc.steps):
        attrs = {"localId": ids.next(), "name": step.name}
        if step.initial:
            attrs["initialStep"] = "true"
        st = ET.SubElement(sfc_el, "step", **attrs)
        lay = step.layout or {"x": 100, "y": 40 + i * 80}
        ET.SubElement(st, "position", x=str(lay["x"]), y=str(lay["y"]))
        if step.actions:
            inline = ET.SubElement(
                ET.SubElement(ET.SubElement(ET.SubElement(st, "actionBlock"), "action"),
                              "inline"), "ST")
            inline.text = "\n".join(_st_stmts(step.actions, 0))
    for t in program.sfc.transitions:
        owner = t.sources[-1] if t.sources else None
        # one transition element per target (PLCopen target attr is singular here)
        for target in t.targets:
            tr = ET.SubElement(sfc_el, "transition", localId=ids.next(),
                               target=target, **({"source": owner} if owner else {}))
            cnd = ET.SubElement(ET.SubElement(ET.SubElement(tr, "condition"), "inline"), "ST")
            cnd.text = _st_expr(t.cond)


def _is_ladder_expressible(program: ir.Program) -> bool:
    if not program.body:
        return True
    for s in program.body:
        if not isinstance(s, ir.Assign):
            return False
        expr = s.value
        if isinstance(expr, ir.UnaryOp) and expr.op == "not":
            expr = expr.operand
        if any(_leaves(t) is None for t in _and_terms(expr)):
            return False
    return True


def emit_plcopen(program: ir.Program, body: str = "auto") -> str:
    project = ET.Element("project", xmlns=_NS)
    types = ET.SubElement(project, "types")
    pous = ET.SubElement(types, "pous")
    pou = ET.SubElement(pous, "pou", name=program.name, pouType="program")

    def _synthetic(n):
        return n == "_started" or n.startswith("_active_")

    interface = ET.SubElement(pou, "interface")
    for section, scope in (("inputVars", ir.VarScope.INPUT),
                           ("outputVars", ir.VarScope.OUTPUT),
                           ("localVars", ir.VarScope.LOCAL)):
        decls = [v for v in program.vars
                 if v.scope is scope and not (program.sfc is not None and _synthetic(v.name))]
        if not decls:
            continue
        sec = ET.SubElement(interface, section)
        for v in decls:
            var = ET.SubElement(sec, "variable", name=v.name)
            ET.SubElement(ET.SubElement(var, "type"), _TYPE_NAME.get(v.type, "INT"))

    body_el = ET.SubElement(pou, "body")
    ids = _Ids()
    kind = body
    if kind == "auto":
        if program.sfc is not None:
            kind = "sfc"
        elif _is_ladder_expressible(program):
            kind = "ld"
        else:
            kind = "fbd"

    if kind == "sfc" and program.sfc is not None:
        _emit_sfc_body(ET.SubElement(body_el, "SFC"), program, ids)
    elif kind == "fbd":
        _emit_fbd_body(ET.SubElement(body_el, "FBD"), program, ids)
    else:
        ld = ET.SubElement(body_el, "LD")
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
