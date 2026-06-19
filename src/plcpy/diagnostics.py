from __future__ import annotations
import enum
from dataclasses import dataclass


class Severity(enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    UNSUPPORTED = "unsupported"


@dataclass
class Diagnostic:
    message: str
    severity: Severity
    line: int = 0
    col: int = 0
    code: str = ""
