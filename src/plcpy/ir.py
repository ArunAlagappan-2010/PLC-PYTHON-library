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


Expr = Union[Literal, VarRef, BinOp, UnaryOp]


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


Stmt = Union[Assign, If, While, For, Case]


@dataclass
class VarDecl:
    name: str
    type: DataType
    scope: VarScope
    initial: object | None = None


@dataclass
class Program:
    name: str
    vars: list[VarDecl] = field(default_factory=list)
    body: list[Stmt] = field(default_factory=list)
