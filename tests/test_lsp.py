import io
import json
from plcpy import lsp


def _frame(msg: dict) -> bytes:
    data = json.dumps(msg).encode("utf-8")
    return b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data


def _read_frames(raw: bytes) -> list[dict]:
    msgs = []
    while raw:
        header, _, rest = raw.partition(b"\r\n\r\n")
        length = int(dict(
            line.split(b":", 1) for line in header.split(b"\r\n") if b":" in line
        )[b"Content-Length"])
        msgs.append(json.loads(rest[:length].decode("utf-8")))
        raw = rest[length:]
    return msgs


def test_lang_for_uri():
    assert lsp.lang_for_uri("file:///x/foo.st") == "st"
    assert lsp.lang_for_uri("file:///x/foo.sfc") == "sfc"
    assert lsp.lang_for_uri("file:///x/foo.txt") is None


def test_diagnostics_for_unsupported_type():
    text = "PROGRAM P\n VAR z : STRING; END_VAR\nEND_PROGRAM\n"
    diags = lsp.lsp_diagnostics(text, "st")
    assert diags
    assert diags[0]["severity"] == 2          # warning
    assert diags[0]["source"] == "plcpy"
    assert "STRING" in diags[0]["message"]
    assert "range" in diags[0]


def test_clean_program_has_no_diagnostics():
    text = "PROGRAM P\nVAR_OUTPUT\n y : INT;\nEND_VAR\n y := 1;\nEND_PROGRAM\n"
    assert lsp.lsp_diagnostics(text, "st") == []


def test_server_publishes_diagnostics_on_open():
    msgs = (
        _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + _frame({"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {
            "textDocument": {
                "uri": "file:///bad.st",
                "languageId": "st",
                "version": 1,
                "text": "PROGRAM P\n VAR z : STRING; END_VAR\nEND_PROGRAM\n",
            }
        }})
        + _frame({"jsonrpc": "2.0", "method": "exit", "params": {}})
    )
    out = io.BytesIO()
    lsp.LSPServer(io.BytesIO(msgs), out).serve_forever()
    frames = _read_frames(out.getvalue())

    # initialize result
    assert frames[0]["id"] == 1
    assert frames[0]["result"]["capabilities"]["textDocumentSync"] == 1
    # publishDiagnostics with the unsupported-type warning
    publish = next(f for f in frames if f.get("method") == "textDocument/publishDiagnostics")
    assert publish["params"]["uri"] == "file:///bad.st"
    assert publish["params"]["diagnostics"]
    assert publish["params"]["diagnostics"][0]["severity"] == 2
