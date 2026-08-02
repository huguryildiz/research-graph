import pytest

from rgraph.cli import main


def test_version_flag_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "0.2.0" in capsys.readouterr().out


def test_bare_invocation_prints_banner(capsys):
    assert main([]) == 0
    assert "contract-gated agentic research" in capsys.readouterr().out


def test_no_banner_flag_suppresses_it(capsys):
    assert main(["--no-banner"]) == 0
    assert "contract-gated" not in capsys.readouterr().out


def test_bare_first_use_leads_with_the_clean_demo(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["--no-banner"]) == 0
    out = capsys.readouterr().out
    assert "rgraph demo --scenario 1" in out
    assert "rgraph setup" in out and "rgraph init" in out


def test_help_names_the_clean_start_and_own_study_paths(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Start here:  rgraph demo --scenario 1" in out
    assert "Own study:   rgraph setup, then rgraph init" in out


def test_unknown_command_exits_two_and_points_to_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["nosuchcommand"])
    assert exc.value.code == 2
    assert "Run next:  rgraph --help" in capsys.readouterr().err
