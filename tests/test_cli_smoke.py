import pytest

from rgraph.cli import main


def test_version_flag_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "0.1.0" in capsys.readouterr().out


def test_bare_invocation_prints_banner(capsys):
    assert main([]) == 0
    assert "contract-gated agentic research" in capsys.readouterr().out


def test_no_banner_flag_suppresses_it(capsys):
    assert main(["--no-banner"]) == 0
    assert "contract-gated" not in capsys.readouterr().out


def test_unknown_command_exits_two():
    with pytest.raises(SystemExit) as exc:
        main(["nosuchcommand"])
    assert exc.value.code == 2
