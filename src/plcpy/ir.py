from __future__ import annotations
import enum
from dataclasses import dataclass, field
from typing import Union


class VarScope(enum.Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    LOCAL = "LOCAL"


class DataType(enum.Enum):
    BOOL = "BOOL"
    INT = "INT"
    REAL = "REAL"
    TIME = "TIME"  # stored as integer milliseconds


@dataclass
class Literal:
    value: object
    type: DataType


@dataclass
class VarRef:
    name: str


@dataclass
class BinOp:
    op: str
    left: "Expr"
    right: "Expr"


@dataclass
class UnaryOp:
    op: str
    operand: "Expr"


@dataclass
class Member:
    """Member access on an instance/struct, e.g. tmr.Q or motor.cfg.speed"""
    base: "Expr"
    member: str


@dataclass
class Index:
    """Array element read, e.g. buf[i]"""
    base: str
    index: "Expr"


Expr = Union[Literal, VarRef, BinOp, UnaryOp, Member, Index]


@dataclass
class Assign:
    target: str
    value: "Expr"


@dataclass
class If:
    cond: "Expr"
    then: list["Stmt"]
    elifs: list[tuple["Expr", list["Stmt"]]] = field(default_factory=list)
    orelse: list["Stmt"] = field(default_factory=list)


@dataclass
class While:
    cond: "Expr"
    body: list["Stmt"] = field(default_factory=list)


@dataclass
class For:
    var: str
    start: "Expr"
    end: "Expr"
    step: "Expr"
    body: list["Stmt"] = field(default_factory=list)


@dataclass
class Case:
    selector: "Expr"
    branches: list[tuple[list[int], list["Stmt"]]] = field(default_factory=list)
    default: list["Stmt"] = field(default_factory=list)


@dataclass
class FBCall:
    """Invoke a function-block instance, e.g. tmr(IN := x, PT := T#5s);"""
    instance: str
    args: dict[str, "Expr"] = field(default_factory=dict)


@dataclass
class IndexAssign:
    """Array element assignment, e.g. buf[i] := x;"""
    base: str
    index: "Expr"
    value: "Expr"


@dataclass
class MemberAssign:
    """Struct/FB member assignment, e.g. motor.speed := x;"""
    target: "Member"
    value: "Expr"


Stmt = Union[Assign, If, While, For, Case, FBCall, IndexAssign, MemberAssign]


@dataclass
class FBInstance:
    """A function-block instance variable, e.g. tmr : TON;"""
    name: str
    fb_type: str


@dataclass
class SfcStep:
    name: str
    initial: bool = False
    actions: list["Stmt"] = field(default_factory=list)
    # each transition is (condition, target step name)
    transitions: list[tuple["Expr", str]] = field(default_factory=list)


@dataclass
class Sfc:
    steps: list[SfcStep] = field(default_factory=list)


@dataclass
class EnumDef:
    name: str
    members: dict[str, int] = field(default_factory=dict)


@dataclass
class StructDef:
    name: str
    fields: list[tuple[str, str]] = field(default_factory=list)  # (field, type_name)


@dataclass
class FunctionBlockDef:
    name: str
    vars: list["VarDecl"] = field(default_factory=list)
    body: list["Stmt"] = field(default_factory=list)


@dataclass
class VarDecl:
    name: str
    type: DataType
    scope: VarScope
    initial: object | None = None
    # for arrays: number of elements and the lower bound (e.g. ARRAY[0..3] -> len 4, lo 0)
    array_len: int | None = None
    array_lo: int = 0
    # for struct instances: the struct type name
    struct_type: str | None = None


@dataclass
class Program:
    name: str
    vars: list[VarDecl] = field(default_factory=list)
    body: list[Stmt] = field(default_factory=list)
    # function-block instance declarations (timers etc.)
    fbs: list[FBInstance] = field(default_factory=list)
    # user-defined type definitions (EnumDef | StructDef)
    types: list = field(default_factory=list)
    # user-defined function block definitions
    fb_defs: list[FunctionBlockDef] = field(default_factory=list)
    # set by the SFC frontend so the SFC backend can reconstruct the chart;
    # all other backends ignore it and use the lowered `body`.
    sfc: Sfc | None = None
