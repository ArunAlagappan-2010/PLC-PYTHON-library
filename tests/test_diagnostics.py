from plcpy.diagnostics import Diagnostic, Severity
from plcpy import errors


def test_diagnostic_defaults():
    d = Diagnostic("oops", Severity.ERROR)
    assert d.line == 0 and d.col == 0 and d.code == ""
    assert d.severity is Severity.ERROR


def test_error_hierarchy():
    assert issubclass(errors.UnknownLanguageError, errors.PlcPyError)
