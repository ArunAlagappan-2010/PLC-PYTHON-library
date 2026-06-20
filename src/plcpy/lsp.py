"""A minimal, dependency-free Language Server for PLC files.

Speaks LSP (Content-Length framed JSON-RPC) over a pair of binary streams
(stdin/stdout by default). On open/change/save it runs the matching plcpy
frontend and publishes its diagnostics, so editors get live squiggles for
unsupported constructs and parse errors. No third-party LSP library required.

The validation core (`lsp_diagnostics`) and the message loop (`LSPServer`) are
both pure enough to unit-test without a real editor client.
"""
from __future__ import annotations
import json
from typing import BinaryIO
from .registry import get_frontend
from .errors import UnknownLanguageError
from .diagnostics import Severity

_EXT_LANG = {".st": "st", ".il": "il", ".ld": "ld", ".fbd": "fbd",
             ".sfc": "sfc", ".py": "python"}

_LSP_SEVERITY = {Severity.ERROR: 1, Severity.WARNING: 2, Severity.UNSUPPORTED: 2}


def lang_for_uri(uri: str) -> str | None:
    low = uri.lower()
    for ext, lang in _EXT_LANG.items():
        if low.endswith(ext):
            return lang
    return None


def lsp_diagnostics(text: str, lang: str) -> list[dict]:
    """Run the frontend for `lang` and return LSP diagnostic objects."""
    try:
        frontend = get_frontend(lang)
    except UnknownLanguageError:
        return []
    result = frontend(text)
    out: list[dict] = []
    for d in result.diagnostics:
        line = max(0, d.line - 1)
        ch = max(0, d.col)
        out.append({
            "range": {
                "start": {"line": line, "character": ch},
                "end": {"line": line, "character": ch + 1},
            },
            "severity": _LSP_SEVERITY.get(d.severity, 3),
            "source": "plcpy",
            "code": d.code,
            "message": d.message,
        })
    return out


class LSPServer:
    def __init__(self, rstream: BinaryIO, wstream: BinaryIO) -> None:
        self.r = rstream
        self.w = wstream
        self.docs: dict[str, str] = {}
        self.running = True

    def _read(self) -> dict | None:
        headers: dict[bytes, bytes] = {}
        line = self.r.readline()
        if not line:
            return None
        while line not in (b"\r\n", b"\n"):
            if b":" in line:
                k, v = line.split(b":", 1)
                headers[k.strip().lower()] = v.strip()
            line = self.r.readline()
            if not line:
                break
        if b"content-length" not in headers:
            return None
        body = self.r.read(int(headers[b"content-length"]))
        return json.loads(body.decode("utf-8"))

    def _write(self, msg: dict) -> None:
        data = json.dumps(msg).encode("utf-8")
        self.w.write(b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data)
        self.w.flush()

    def _publish(self, uri: str, text: str) -> None:
        lang = lang_for_uri(uri)
        diags = lsp_diagnostics(text, lang) if lang else []
        self._write({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
                     "params": {"uri": uri, "diagnostics": diags}})

    def handle(self, msg: dict) -> None:
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}
        if method == "initialize":
            self._write({"jsonrpc": "2.0", "id": mid,
                         "result": {"capabilities": {"textDocumentSync": 1}}})
        elif method == "textDocument/didOpen":
            doc = params["textDocument"]
            self.docs[doc["uri"]] = doc["text"]
            self._publish(doc["uri"], doc["text"])
        elif method == "textDocument/didChange":
            uri = params["textDocument"]["uri"]
            changes = params.get("contentChanges") or []
            if changes:
                text = changes[-1]["text"]
                self.docs[uri] = text
                self._publish(uri, text)
        elif method == "textDocument/didSave":
            uri = params["textDocument"]["uri"]
            text = params.get("text", self.docs.get(uri, ""))
            self._publish(uri, text)
        elif method == "textDocument/didClose":
            self.docs.pop(params["textDocument"]["uri"], None)
        elif method == "shutdown":
            self._write({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "exit":
            self.running = False

    def serve_forever(self) -> None:
        while self.running:
            msg = self._read()
            if msg is None:
                break
            self.handle(msg)


def main() -> int:
    import sys
    # ensure plugins are registered
    from . import convert as _convert  # noqa: F401
    LSPServer(sys.stdin.buffer, sys.stdout.buffer).serve_forever()
    return 0
