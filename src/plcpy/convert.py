from __future__ import annotations
from dataclasses import dataclass
from .registry import get_frontend, get_backend, languages
from .diagnostics import Diagnostic, Severity

# Import plugins for their registration side effects.
from .frontends import st as _st_fe       # noqa: F401
from .frontends import python as _py_fe   # noqa: F401
from .frontends import il as _il_fe       # noqa: F401
from .frontends import ld as _ld_fe       # noqa: F401
from .backends import st as _st_be        # noqa: F401
from .backends import python as _py_be    # noqa: F401
from .backends import il as _il_be        # noqa: F401
from .backends import ld as _ld_be        # noqa: F401


@dataclass
class ConvertResult:
    code: str | None
    diagnostics: list[Diagnostic]


def convert(source: str, from_lang: str, to_lang: str) -> ConvertResult:
    frontend = get_frontend(from_lang)
    backend = get_backend(to_lang)
    parsed = frontend(source)
    if parsed.program is None:
        return ConvertResult(None, parsed.diagnostics)
    code = backend(parsed.program)
    return ConvertResult(code, parsed.diagnostics)
