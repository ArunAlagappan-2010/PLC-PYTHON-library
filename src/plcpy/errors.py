class PlcPyError(Exception):
    """Base class for plcpy programmer/API errors (not source errors)."""


class UnknownLanguageError(PlcPyError):
    """Raised when a language id is not registered."""
