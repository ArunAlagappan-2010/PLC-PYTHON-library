from __future__ import annotations
import ast
from .. import ir
from ..registry import ParseResult, register_frontend
from ..diagnostics import Diagnostic, Severity

_CMP = {ast.Eq: "=", ast.NotEq: "<>", ast.Lt: "<", ast.LtE: "<=",
        ast.Gt: ">", ast.GtE: ">="}
_BIN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_BOOL = {ast.And: "and", ast.Or: "or"}


class _Conv:
    def __init__(self):
        self.diagnostics: list[Diagnostic] = []

    def unsupported(self, node, what):
        self.diagnostics.append(Diagnostic(
            f"unsupported Python construct: {what}", Severity.UNSUPPORTED,
            line=getattr(node, "lineno", 0), code="PY"))

    def expr(self, node) -> ir.Expr | None:
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id == "self":
            return ir.VarRef(node.attr)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return ir.Literal(node.value, ir.DataType.BOOL)
            if isinstance(node.value, int):
                return ir.Literal(node.value, ir.DataType.INT)
            if isinstance(node.value, float):
                return ir.Literal(node.value, ir.DataType.REAL)
            self.unsupported(node, f"literal {node.value!r}")
            return None
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return ir.UnaryOp("not", self.expr(node.operand))
            if isinstance(node.op, ast.USub):
                return ir.UnaryOp("-", self.expr(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            return ir.BinOp(_BIN[type(node.op)], self.expr(node.left), self.expr(node.right))
        if isinstance(node, ast.BoolOp) and type(node.op) in _BOOL:
            acc = self.expr(node.values[0])
            for v in node.values[1:]:
                acc = ir.BinOp(_BOOL[type(node.op)], acc, self.expr(v))
            return acc
        if isinstance(node, ast.Compare) and len(node.ops) == 1 \
                and type(node.ops[0]) in _CMP:
            return ir.BinOp(_CMP[type(node.ops[0])], self.expr(node.left),
                            self.expr(node.comparators[0]))
        self.unsupported(node, type(node).__name__)
        return None

    def stmt(self, node) -> ir.Stmt | None:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Attribute) \
                and isinstance(node.targets[0].value, ast.Name) \
                and node.targets[0].value.id == "self":
            return ir.Assign(node.targets[0].attr, self.expr(node.value))
        if isinstance(node, ast.If):
            cond = self.expr(node.test)
            then = [s for s in (self.stmt(x) for x in node.body) if s]
            orelse = [s for s in (self.stmt(x) for x in node.orelse) if s]
            return ir.If(cond, then, [], orelse)
        if isinstance(node, ast.While):
            cond = self.expr(node.test)
            body = [s for s in (self.stmt(x) for x in node.body) if s]
            return ir.While(cond, body)
        self.unsupported(node, type(node).__name__)
        return None


def parse_python(text: str) -> ParseResult:
    conv = _Conv()
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return ParseResult(None, [Diagnostic(str(e), Severity.ERROR, code="PY_SYNTAX")])
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef)), None)
    if cls is None:
        return ParseResult(None, [Diagnostic("no class found", Severity.ERROR, code="PY")])
    vars_: list[ir.VarDecl] = []
    body: list[ir.Stmt] = []
    for item in cls.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            for s in item.body:
                if isinstance(s, ast.Assign) and isinstance(s.targets[0], ast.Attribute):
                    name = s.targets[0].attr
                    val = s.value
                    dt = ir.DataType.INT
                    if isinstance(val, ast.Constant):
                        if isinstance(val.value, bool):
                            dt = ir.DataType.BOOL
                        elif isinstance(val.value, float):
                            dt = ir.DataType.REAL
                    vars_.append(ir.VarDecl(name, dt, ir.VarScope.LOCAL))
        elif isinstance(item, ast.FunctionDef) and item.name == "scan":
            for s in item.body:
                conv_stmt = conv.stmt(s)
                if conv_stmt:
                    body.append(conv_stmt)
    program = ir.Program(cls.name, vars_, body)
    return ParseResult(program, conv.diagnostics)


register_frontend("python", parse_python)
