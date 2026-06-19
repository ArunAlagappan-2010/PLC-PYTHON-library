import pytest
from plcpy import registry, ir
from plcpy.errors import UnknownLanguageError


def test_register_and_get_roundtrip():
    def fe(text): return registry.ParseResult(ir.Program("P"), [])
    def be(prog): return "code"
    registry.register_frontend("demo", fe)
    registry.register_backend("demo", be)
    assert registry.get_frontend("demo") is fe
    assert registry.get_backend("demo") is be
    langs = registry.languages()
    assert langs["demo"] == {"frontend": True, "backend": True}


def test_unknown_language_raises():
    with pytest.raises(UnknownLanguageError):
        registry.get_frontend("nope-not-registered")
