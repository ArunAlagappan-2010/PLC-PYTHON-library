def test_package_imports_and_has_version():
    import plcpy
    assert isinstance(plcpy.__version__, str)
    assert plcpy.__version__
