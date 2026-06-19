from plcpy import cli


def test_cli_convert_st_to_python(tmp_path, capsys):
    f = tmp_path / "prog.st"
    f.write_text("PROGRAM Main\nVAR_OUTPUT\n y : INT;\nEND_VAR\n y := 1;\nEND_PROGRAM\n")
    rc = cli.main(["convert", "--from", "st", "--to", "python", str(f)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "class Main" in out
    assert "def scan(self)" in out
