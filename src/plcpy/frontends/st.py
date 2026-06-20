from __future__ import annotations
from pathlib import Path
from lark import Lark, Transformer
from lark.exceptions import LarkError
from .. import ir
from ..registry import ParseResult, register_frontend
import re
from ..diagnostics import Diagnostic, Severity
from ._common import TYPES as _TYPES, FB_TYPES as _FB_TYPES

_TIME_UNIT = {"ms": 1, "s": 1000, "m": 60000, "h": 3600000}


def _parse_time(tok: str) -> int:
    """Parse an IEC TIME literal like T#1m30s into milliseconds."""
    total = 0
    for num, unit in re.findall(r"([0-9]+)(ms|s|m|h)", tok[2:]):
        total += int(num) * _TIME_UNIT[unit]
    return total

_GRAMMAR = (Path(__file__).parent / "st_grammar.lark").read_text(encoding="utf-8")
_PARSER = Lark(_GRAMMAR, parser="lalr")

_SCOPE_RULE = {"var_input": ir.VarScope.INPUT, "var_output": ir.VarScope.OUTPUT,
               "var_local": ir.VarScope.LOCAL}


class _ToIR(Transformer):
    def __init__(self, fb_names: set[str] | None = None):
        super().__init__()
        self.diagnostics: list[Diagnostic] = []
        self.enums: dict[str, dict[str, int]] = {}
        self.structs: set[str] = set()
        self.fb_types: set[str] = set(_FB_TYPES) | (fb_names or set())
        self.fb_defs: list[ir.FunctionBlockDef] = []

    # expressions
    def var_ref(self, c): return ir.VarRef(str(c[0]))

    def number(self, c):
        t = str(c[0])
        if "." in t:
            return ir.Literal(float(t), ir.DataType.REAL)
        return ir.Literal(int(t), ir.DataType.INT)

    def bool_lit(self, c): return ir.Literal(str(c[0]) == "TRUE", ir.DataType.BOOL)
    def time_lit(self, c): return ir.Literal(_parse_time(str(c[0])), ir.DataType.TIME)
    def member(self, c):
        base_name = str(c[0])
        if len(c) == 2 and base_name in self.enums:
            return ir.Literal(self.enums[base_name][str(c[1])], ir.DataType.INT)
        node: ir.Expr = ir.VarRef(base_name)
        for field in c[1:]:
            node = ir.Member(node, str(field))
        return node
    def index(self, c): return ir.Index(str(c[0]), c[1])
    def unary_not(self, c): return ir.UnaryOp("not", c[0])
    def unary_neg(self, c): return ir.UnaryOp("-", c[0])
    def binop_or(self, c): return ir.BinOp("or", c[0], c[1])
    def binop_and(self, c): return ir.BinOp("and", c[0], c[1])
    def binop_cmp(self, c): return ir.BinOp(str(c[1]), c[0], c[2])
    def binop_add(self, c): return ir.BinOp(str(c[1]), c[0], c[2])
    def binop_mul(self, c): return ir.BinOp(str(c[1]), c[0], c[2])

    # statements
    def assign(self, c): return ir.Assign(str(c[0]), c[1])
    def index_assign(self, c): return ir.IndexAssign(str(c[0]), c[1], c[2])

    def member_assign(self, c):
        *path, value = c
        node: ir.Expr = ir.VarRef(str(path[0]))
        for field in path[1:]:
            node = ir.Member(node, str(field))
        return ir.MemberAssign(node, value)
    def fb_arg(self, c): return (str(c[0]), c[1])

    def fb_call(self, c):
        instance = str(c[0])
        args = {name: expr for name, expr in c[1:]}
        return ir.FBCall(instance, args)

    def while_stmt(self, c):
        cond = c[0]
        body = [s for s in c[1:]]
        return ir.While(cond, body)

    def for_by(self, c): return ("by", c[0])

    def for_stmt(self, c):
        var = str(c[0])
        start = c[1]
        end = c[2]
        step = ir.Literal(1, ir.DataType.INT)
        rest = list(c[3:])
        if rest and isinstance(rest[0], tuple) and rest[0][0] == "by":
            step = rest.pop(0)[1]
        return ir.For(var, start, end, step, rest)

    def case_labels(self, c): return [int(str(t)) for t in c]
    def case_branch(self, c): return ("branch", c[0], [s for s in c[1:]])
    def case_else(self, c): return ("else", [s for s in c])

    def case_stmt(self, c):
        selector = c[0]
        branches: list = []
        default: list = []
        for item in c[1:]:
            if isinstance(item, tuple) and item[0] == "branch":
                branches.append((item[1], item[2]))
            elif isinstance(item, tuple) and item[0] == "else":
                default = item[1]
        return ir.Case(selector, branches, default)
    def elif_clause(self, c): return ("elif", c[0], [s for s in c[1:]])
    def else_clause(self, c): return ("else", [s for s in c])

    def if_stmt(self, c):
        cond = c[0]
        then: list = []
        elifs: list = []
        orelse: list = []
        for item in c[1:]:
            if isinstance(item, tuple) and item[0] == "elif":
                elifs.append((item[1], item[2]))
            elif isinstance(item, tuple) and item[0] == "else":
                orelse = item[1]
            else:
                then.append(item)
        return ir.If(cond, then, elifs, orelse)

    # type definitions
    def enum_def(self, c):
        name = str(c[0])
        members = {str(m): i for i, m in enumerate(c[1:])}
        self.enums[name] = members
        return ir.EnumDef(name, members)

    def struct_field(self, c): return (str(c[0]), str(c[1]))

    def struct_def(self, c):
        name = str(c[0])
        self.structs.add(name)
        return ir.StructDef(name, [f for f in c[1:]])

    def type_block(self, c): return ("types", [t for t in c])

    def fb_def(self, c):
        name = str(c[0])
        self.fb_types.add(name)
        vars_: list[ir.VarDecl] = []
        body: list = []
        for item in c[1:]:
            if isinstance(item, tuple) and item[0] in _SCOPE_RULE:
                scope = _SCOPE_RULE[item[0]]
                for decl in item[1]:
                    self._add_decl(decl, scope, vars_, [])
            else:
                body.append(item)
        fbdef = ir.FunctionBlockDef(name, vars_, body)
        self.fb_defs.append(fbdef)
        return ("fbdef", fbdef)

    # declarations
    def scalar_type(self, c): return ("scalar", str(c[0]))
    def array_type(self, c):
        lo, hi, elem = int(str(c[0])), int(str(c[1])), str(c[2])
        return ("array", lo, hi, elem)

    def _resolve_type(self, elem: str):
        dt = _TYPES.get(elem)
        if dt is None:
            self.diagnostics.append(Diagnostic(
                f"unsupported type {elem!r}", Severity.UNSUPPORTED, code="ST_TYPE"))
            dt = ir.DataType.INT
        return dt

    def var_decl(self, c):
        name = str(c[0])
        spec = c[1]
        if spec[0] == "array":
            _, lo, hi, elem = spec
            return ("array", name, self._resolve_type(elem), hi - lo + 1, lo)
        type_tok = spec[1]
        if type_tok in self.fb_types:
            return ("fb", name, type_tok)
        if type_tok in self.structs:
            return ("struct", name, type_tok)
        return ("var", name, self._resolve_type(type_tok))

    def var_input(self, c): return ("var_input", c)
    def var_output(self, c): return ("var_output", c)
    def var_local(self, c): return ("var_local", c)
    def var_section(self, c): return c[0]

    @staticmethod
    def _add_decl(decl, scope, vars_, fbs):
        kind = decl[0]
        if kind == "fb":
            fbs.append(ir.FBInstance(decl[1], decl[2]))
        elif kind == "array":
            _, vname, dt, length, lo = decl
            vars_.append(ir.VarDecl(vname, dt, scope, array_len=length, array_lo=lo))
        elif kind == "struct":
            _, vname, sname = decl
            vars_.append(ir.VarDecl(vname, ir.DataType.INT, scope, struct_type=sname))
        else:
            vars_.append(ir.VarDecl(decl[1], decl[2], scope))

    def program(self, c):
        name = str(c[0])
        vars_: list[ir.VarDecl] = []
        fbs: list[ir.FBInstance] = []
        body: list = []
        for item in c[1:]:
            if isinstance(item, tuple) and item[0] in _SCOPE_RULE:
                scope = _SCOPE_RULE[item[0]]
                for decl in item[1]:
                    self._add_decl(decl, scope, vars_, fbs)
            else:
                body.append(item)
        return ir.Program(name, vars_, body, fbs=fbs)

    def statement(self, c): return c[0]

    def start(self, c):
        prog = c[-1]
        for item in c[:-1]:
            if isinstance(item, tuple) and item[0] == "types":
                prog.types.extend(item[1])
            elif isinstance(item, tuple) and item[0] == "fbdef":
                prog.fb_defs.append(item[1])
        return prog


def parse_st(text: str) -> ParseResult:
    fb_names = set(re.findall(r"FUNCTION_BLOCK\s+(\w+)", text))
    struct_names = set(re.findall(r"(\w+)\s*:\s*STRUCT\b", text))
    try:
        tree = _PARSER.parse(text)
    except LarkError as e:
        return ParseResult(None, [Diagnostic(str(e), Severity.ERROR, code="ST_PARSE")])
    t = _ToIR(fb_names)
    t.structs |= struct_names
    program = t.transform(tree)
    return ParseResult(program, t.diagnostics)


register_frontend("st", parse_st)
