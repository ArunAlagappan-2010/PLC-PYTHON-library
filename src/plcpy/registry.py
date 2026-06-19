from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
from .ir import Program
from .diagnostics import Diagnostic
from .errors import UnknownLanguageError


@dataclass
class ParseResult:
    program: Program | None
    diagnostics: list[Diagnostic]


Frontend = Callable[[str], "ParseResult"]
Backend = Callable[[Program], str]

_FRONTENDS: dict[str, Frontend] = {}
_BACKENDS: dict[str, Backend] = {}


def register_frontend(lang: str, fn: Frontend) -> None:
    _FRONTENDS[lang] = fn


def register_backend(lang: str, fn: Backend) -> None:
    _BACKENDS[lang] = fn


def get_frontend(lang: str) -> Frontend:
    try:
        return _FRONTENDS[lang]
    except KeyError:
        raise UnknownLanguageError(f"no frontend registered for {lang!r}")


def get_backend(lang: str) -> Backend:
    try:
        return _BACKENDS[lang]
    except KeyError:
        raise UnknownLanguageError(f"no backend registered for {lang!r}")


def languages() -> dict[str, dict[str, bool]]:
    keys = set(_FRONTENDS) | set(_BACKENDS)
    return {
        k: {"frontend": k in _FRONTENDS, "backend": k in _BACKENDS}
        for k in sorted(keys)
    }
