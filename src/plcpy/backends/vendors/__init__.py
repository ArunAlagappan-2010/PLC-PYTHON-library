"""Vendor export plugins.

Vendor backends are emitter-only plugins that consume the same generic IEC
61131-3 IR as the core backends and produce vendor-specific output. They are
registered under their own language ids (e.g. "scl", "l5x"), so
`convert(src, from_lang, "scl")` works from any frontend.
"""
